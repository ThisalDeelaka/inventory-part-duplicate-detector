import asyncio
import csv
import io
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import (
    CandidateDiscoveryMetadata,
    DuplicateCandidate,
    DuplicateScan,
    LlmAdvisorySnapshot,
    LlmTriageRun,
)
from app.llm.audit import LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.contracts import CandidateAdvisoryRequest, CandidateTriageResponse
from app.llm.exceptions import (
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderNetworkError,
    LLMProviderTimeoutError,
)
from app.llm.provider import LLMProviderResult
from app.llm.runtime import get_llm_settings
from app.llm.service_contracts import LLMCapability
from app.llm.services import validate_triage_decision
from app.main import app
from app.services.llm_triage_service import (
    LlmTriageRunner,
    automatic_triage_ready,
    candidate_is_triage_eligible,
    effective_status,
    eligible_candidate_ids,
    get_llm_triage_scheduler,
    prepare_triage_run,
    triage_failure_categories,
)
from app.services.llm_snapshot_service import safe_error_category
from app.services.llm_enhancement_service import LlmEnhancementProcessor


def _settings(**overrides):
    values = {
        "llm_demo_enabled": True,
        "llm_provider": "groq",
        "groq_api_key": "synthetic-test-value",
        "groq_model": "triage-test-model",
        "llm_auto_triage_enabled": True,
        "llm_triage_concurrency": 1,
        "llm_triage_max_candidates_per_scan": 250,
        "llm_triage_min_interval_ms": 0,
        "llm_triage_max_retries": 0,
        "llm_triage_retry_batch_size": 20,
        "llm_triage_consecutive_failure_limit": 5,
    }
    values.update(overrides)
    return Settings(**values)


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.active = 0
        self.max_active = 0

    async def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        value = self.responses.pop(0)
        self.active -= 1
        if isinstance(value, Exception):
            raise value
        return LLMProviderResult(
            provider="groq", model="triage-test-model", content=value
        )


def _advisory(assessment="INCONCLUSIVE", confidence=0.6):
    basis = {
        "SUPPORTS_DUPLICATE": ["SEMANTIC_EQUIVALENCE"],
        "SUPPORTS_NON_DUPLICATE": ["PRODUCT_TYPE_CONFLICT"],
        "INCONCLUSIVE": [],
    }[assessment]
    return {
        "assessment": assessment,
        "confidence": confidence,
        "supporting_evidence": ["Bounded synthetic evidence."],
        "conflicting_evidence": [],
        "recommended_action": "HUMAN_REVIEW",
        "deterministic_result_authoritative": True,
        "decision_basis": basis,
    }


def _scan(db, name="triage scan"):
    scan = DuplicateScan(
        scan_name=name,
        selected_fields="[]",
        threshold=75,
        model_version="test-v1",
        status="COMPLETED",
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def _candidate(db, scan, **overrides):
    values = {
        "scan_id": scan.id,
        "contract_a": "S1",
        "part_no_a": "A-1",
        "description_a": "Synthetic motor A",
        "contract_b": "S1",
        "part_no_b": "A-2",
        "description_b": "Synthetic motor B",
        "similarity_score": 82.5,
        "confidence_level": "MEDIUM",
        "description_similarity": 80,
        "tfidf_score": 80,
        "fuzzy_score": 80,
        "part_no_similarity": 70,
        "technical_token_score": 90,
        "matched_fields": "[]",
        "mismatched_fields": "[]",
        "explanation": "Deterministic explanation.",
        "recommended_action": "Manual review recommended",
        "business_status": "POSSIBLE_DUPLICATE_REVIEW",
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "scan_mode": "SAME_SITE_DUPLICATE",
        "critical_mismatches": "[]",
    }
    values.update(overrides)
    candidate = DuplicateCandidate(**values)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def _runner(
    db, provider, configuration=None, session_factory=None, **runner_overrides
):
    factory = session_factory or sessionmaker(bind=db.get_bind())
    return LlmTriageRunner(
        session_factory=factory,
        configuration=configuration or _settings(),
        cache=LLMCache(enabled=True, max_entries=50, ttl_seconds=60),
        audit=LLMAuditStore(enabled=True, max_entries=100),
        provider_factory=lambda _configuration: provider,
        **runner_overrides,
    )


def test_triage_configuration_bounds_are_validated():
    assert _settings().llm_triage_concurrency == 1
    for values in (
        {"llm_triage_concurrency": 0},
        {"llm_triage_concurrency": 9},
        {"llm_triage_max_candidates_per_scan": 0},
        {"llm_triage_max_candidates_per_scan": 1001},
        {"llm_triage_min_interval_ms": -1},
        {"llm_triage_min_interval_ms": 10001},
        {"llm_triage_max_retries": -1},
        {"llm_triage_max_retries": 6},
        {"llm_triage_retry_batch_size": 0},
        {"llm_triage_retry_batch_size": 101},
        {"llm_triage_consecutive_failure_limit": 0},
        {"llm_triage_consecutive_failure_limit": 21},
    ):
        with pytest.raises(ValidationError):
            _settings(**values)


def test_existing_eligibility_is_reused_and_only_review_candidates_are_selected(db):
    scan = _scan(db)
    review = _candidate(db, scan)
    clear = _candidate(
        db, scan, business_status="LIKELY_DUPLICATE", confidence_level="HIGH"
    )
    hard = _candidate(
        db,
        scan,
        business_status="REJECTED_BY_BUSINESS_RULE",
        rule_decision="REJECT",
    )
    assert candidate_is_triage_eligible(review) is True
    assert candidate_is_triage_eligible(clear) is False
    assert candidate_is_triage_eligible(hard) is False
    assert eligible_candidate_ids(db, scan.id) == [review.id]


@pytest.mark.parametrize(("overrides", "expected"), [
    ({"business_status": "LIKELY_DUPLICATE", "confidence_level": "HIGH"}, False),
    ({"business_status": "POSSIBLE_DUPLICATE_REVIEW"}, True),
    ({"business_status": "INSUFFICIENT_DATA", "rule_decision": "DOWNGRADE",
      "rejection_reason": "GENERIC_DESCRIPTION"}, False),
    ({"business_status": "RELATED_BUT_NOT_DUPLICATE", "rule_decision": "DOWNGRADE"}, False),
    ({"business_status": "DATA_CONFLICT_REVIEW", "rule_decision": "DATA_CONFLICT"}, False),
    ({"business_status": "CROSS_SITE_STANDARDIZATION_CANDIDATE",
      "rule_decision": "CROSS_SITE"}, False),
    ({"business_status": "REJECTED_BY_BUSINESS_RULE", "rule_decision": "REJECT"}, False),
])
def test_automatic_triage_status_matrix(db, overrides, expected):
    candidate = _candidate(db, _scan(db, str(overrides)), **overrides)
    assert candidate_is_triage_eligible(candidate) is expected


def test_automatic_gate_rejects_persisted_structural_mismatch_and_calls_no_provider(db):
    scan = _scan(db, "legacy structural mismatch")
    candidate = _candidate(
        db,
        scan,
        part_no_a="MLR-TOP-02.28.2023",
        description_a="MLR-TOP-02.28.2023",
        part_no_b="MLR-COMPONENT-02.28.2023",
        description_b="MLR-COMPONENT-02.28.2023",
        business_status="POSSIBLE_DUPLICATE_REVIEW",
        rule_decision="DOWNGRADE",
        rejection_reason="STRUCTURAL_ROLE_MISMATCH",
        critical_mismatches=json.dumps([{
            "group": "STRUCTURAL_ROLE",
            "label": "Structural role",
            "values_a": ["top"],
            "values_b": ["component"],
        }]),
    )
    run, should_schedule = prepare_triage_run(db, scan.id, _settings())
    provider = FakeProvider([])
    assert candidate_is_triage_eligible(candidate) is False
    assert eligible_candidate_ids(db, scan.id) == []
    assert should_schedule is False and run.total_eligible == 0
    assert provider.calls == []


def test_candidate_source_and_retrieval_uom_metadata_never_grant_eligibility(db):
    scan = _scan(db, "provenance independence")
    standard = _candidate(db, scan, part_no_a="STANDARD-A")
    hybrid = _candidate(db, scan, part_no_a="HYBRID-A")
    db.add_all([
        CandidateDiscoveryMetadata(candidate_id=standard.id, source="DETERMINISTIC_STANDARD"),
        CandidateDiscoveryMetadata(
            candidate_id=hybrid.id,
            source="HYBRID_RETRIEVAL",
            retrieval_tier="TIER_A",
            retrieval_priority=99.99,
            retrieval_sources_json='["EXACT_DESCRIPTION","CHAR_VECTOR"]',
            uom_relationship="DIFFERENT_DIMENSION_OR_BASIS",
            uom_penalty=20,
            mapping_quality="POSSIBLE_MAPPING_ERROR",
        ),
    ])
    db.commit()
    assert candidate_is_triage_eligible(standard) is True
    assert candidate_is_triage_eligible(hybrid) is True
    hybrid.critical_mismatches = json.dumps([{
        "group": "STRUCTURAL_ROLE", "label": "Structural role",
        "values_a": ["top"], "values_b": ["component"],
    }])
    db.commit()
    assert candidate_is_triage_eligible(hybrid) is False


def test_semantic_enhancement_preparation_reuses_central_eligibility_gate(db):
    scan = _scan(db, "semantic central gate")
    clean = _candidate(db, scan, part_no_a="CLEAN-A", part_no_b="CLEAN-B")
    blocked = _candidate(
        db,
        scan,
        part_no_a="MLR-TOP-02.28.2023",
        part_no_b="MLR-COMPONENT-02.28.2023",
        critical_mismatches=json.dumps([{
            "group": "STRUCTURAL_ROLE", "label": "Structural role",
            "values_a": ["top"], "values_b": ["component"],
        }]),
    )
    prepared_record_ids = []

    async def capture_provider_batch(_service, records):
        prepared_record_ids.extend(item.record_id for item in records)
        raise RuntimeError("synthetic provider stub")

    preparation = asyncio.run(
        LlmEnhancementProcessor(_settings(), lambda _configuration: None).prepare(
            db, scan.id, capture_provider_batch
        )
    )
    assert preparation.standard_residual_ids == [clean.id]
    assert prepared_record_ids
    assert all(f"candidate-{clean.id}-" in item for item in prepared_record_ids)
    assert all(f"candidate-{blocked.id}-" not in item for item in prepared_record_ids)


def test_prepare_is_idempotent_one_run_per_scan_and_counts_cap(db):
    scan = _scan(db)
    for index in range(3):
        _candidate(db, scan, part_no_a=f"CAP-{index}")
    configuration = _settings(llm_triage_max_candidates_per_scan=2)
    first, first_schedule = prepare_triage_run(db, scan.id, configuration)
    second, second_schedule = prepare_triage_run(
        db, scan.id, configuration, active=True
    )
    assert first.id == second.id
    assert first_schedule is True and second_schedule is False
    assert second.total_eligible == 3
    assert second.skipped_count == 1
    assert db.query(LlmTriageRun).count() == 1


def test_zero_eligible_completes_without_provider_work(db):
    scan = _scan(db)
    _candidate(db, scan, business_status="LIKELY_DUPLICATE", confidence_level="HIGH")
    run, should_schedule = prepare_triage_run(db, scan.id, _settings())
    assert should_schedule is False
    assert run.state == "COMPLETED"
    assert run.total_eligible == 0


def test_disabled_or_unconfigured_runtime_cannot_start_automatic_work():
    assert automatic_triage_ready(Settings()) is False
    assert automatic_triage_ready(_settings(groq_api_key="")) is False
    assert automatic_triage_ready(_settings(llm_auto_triage_enabled=False)) is False


@pytest.mark.parametrize(
    ("assessment", "expected_status", "counter"),
    [
        ("SUPPORTS_DUPLICATE", "LLM_LIKELY_DUPLICATE", "likely_duplicate_count"),
        ("SUPPORTS_NON_DUPLICATE", "LLM_DOWNGRADED", "downgraded_count"),
        ("INCONCLUSIVE", "HUMAN_REVIEW", "human_review_count"),
    ],
)
def test_successful_triage_maps_status_and_preserves_every_deterministic_field(
    db, assessment, expected_status, counter
):
    scan = _scan(db, assessment)
    candidate = _candidate(
        db,
        scan,
        description_a="Synthetic motor 10 kW model M100",
        description_b="10 kW synthetic motor model M100",
    )
    protected_names = (
        "similarity_score", "confidence_level", "business_status", "rule_decision",
        "rejection_reason", "critical_mismatches", "normalized_description_a",
        "normalized_description_b", "normalized_part_no_a", "normalized_part_no_b",
        "review_status",
    )
    before = {name: getattr(candidate, name) for name in protected_names}
    prepare_triage_run(db, scan.id, _settings())
    provider = FakeProvider([_advisory(assessment)])
    asyncio.run(_runner(db, provider).run(scan.id))
    snapshot = db.query(LlmAdvisorySnapshot).filter_by(
        candidate_id=candidate.id,
        capability=LLMCapability.CANDIDATE_TRIAGE.value,
    ).one()
    run = db.query(LlmTriageRun).filter_by(scan_id=scan.id).one()
    db.refresh(candidate)
    assert effective_status(snapshot, eligible=True) == expected_status
    assert getattr(run, counter) == 1
    assert run.processed_count == 1 and run.state == "COMPLETED"
    assert snapshot.llm_used is True
    assert snapshot.deterministic_result_authoritative is True
    assert {name: getattr(candidate, name) for name in protected_names} == before
    assert len(provider.calls) == 1
    prompt_payload = json.loads(provider.calls[0][1])
    assert set(prompt_payload) == {
        "critical_mismatches", "deterministic_confidence", "deterministic_rule_decision",
        "deterministic_score", "deterministic_status", "left", "rejection_reason", "right",
    }
    assert "review_status" not in provider.calls[0][1]
    assert "normalized_description" not in provider.calls[0][1]


def test_runner_enforces_candidate_cap_and_records_skips(db):
    scan = _scan(db)
    for index in range(3):
        _candidate(db, scan, part_no_a=f"RUN-CAP-{index}")
    configuration = _settings(llm_triage_max_candidates_per_scan=2)
    prepare_triage_run(db, scan.id, configuration)
    provider = FakeProvider([_advisory(), _advisory()])
    asyncio.run(_runner(db, provider, configuration=configuration).run(scan.id))
    run = db.query(LlmTriageRun).filter_by(scan_id=scan.id).one()
    assert len(provider.calls) == 2
    assert run.total_eligible == 3
    assert run.processed_count == 2
    assert run.skipped_count == 1
    assert run.state == "COMPLETED"


def test_failure_continues_and_retry_only_replaces_failed_snapshot(db):
    scan = _scan(db)
    first = _candidate(db, scan)
    second = _candidate(db, scan)
    prepare_triage_run(db, scan.id, _settings())
    provider = FakeProvider([
        LLMProviderTimeoutError("private provider detail"),
        _advisory("SUPPORTS_DUPLICATE"),
    ])
    asyncio.run(_runner(db, provider).run(scan.id))
    failed = db.query(LlmAdvisorySnapshot).filter_by(candidate_id=first.id).one()
    succeeded = db.query(LlmAdvisorySnapshot).filter_by(candidate_id=second.id).one()
    run = db.query(LlmTriageRun).filter_by(scan_id=scan.id).one()
    assert failed.state == "FAILED" and failed.safe_error_category == "provider_timeout"
    assert succeeded.state == "AVAILABLE"
    assert run.state == "COMPLETED_WITH_FAILURES" and run.failed_count == 1
    serialized = json.dumps(failed.__dict__, default=str)
    assert "private provider detail" not in serialized

    retry_provider = FakeProvider([_advisory("SUPPORTS_NON_DUPLICATE")])
    asyncio.run(_runner(db, retry_provider).run(scan.id, retry_failed=True))
    db.expire_all()
    assert db.query(LlmAdvisorySnapshot).filter_by(candidate_id=first.id).one().state == "AVAILABLE"
    assert db.query(LlmAdvisorySnapshot).count() == 2
    assert len(retry_provider.calls) == 1


def test_resume_skips_success_and_processes_missing_in_stable_id_order(db):
    scan = _scan(db)
    first = _candidate(db, scan)
    second = _candidate(db, scan)
    db.add(LlmTriageRun(scan_id=scan.id, state="RUNNING", total_eligible=2))
    db.add(LlmAdvisorySnapshot(
        candidate_id=first.id,
        capability=LLMCapability.CANDIDATE_TRIAGE.value,
        state="AVAILABLE",
        llm_used=True,
        cache_hit=False,
        assessment="INCONCLUSIVE",
        deterministic_result_authoritative=True,
    ))
    db.commit()
    provider = FakeProvider([_advisory("SUPPORTS_DUPLICATE")])
    asyncio.run(_runner(db, provider).run(scan.id))
    payload = json.loads(provider.calls[0][1])
    assert payload["left"]["part_number"] == second.part_no_a
    assert db.query(LlmAdvisorySnapshot).count() == 2


def test_runner_uses_separate_sessions_and_respects_concurrency_bound(db):
    scan = _scan(db)
    for _ in range(4):
        _candidate(db, scan)
    configuration = _settings(llm_triage_concurrency=2)
    prepare_triage_run(db, scan.id, configuration)
    provider = FakeProvider([_advisory()] * 4)
    created_sessions = []
    base_factory = sessionmaker(bind=db.get_bind())

    def tracked_factory():
        session = base_factory()
        created_sessions.append(session)
        return session

    asyncio.run(_runner(
        db, provider, configuration=configuration, session_factory=tracked_factory
    ).run(scan.id))
    assert len(created_sessions) > 4
    assert all(session is not db for session in created_sessions)
    assert provider.max_active <= 2


class CaptureScheduler:
    def __init__(self):
        self.calls = []

    def is_active(self, _scan_id):
        return False

    def schedule(self, _background_tasks, scan_id, *, retry_failed=False):
        self.calls.append((scan_id, retry_failed))
        return True


def test_scan_upload_automatically_creates_run_and_schedules_after_completion(client, db):
    configuration = _settings()
    scheduler = CaptureScheduler()
    app.dependency_overrides[get_llm_settings] = lambda: configuration
    app.dependency_overrides[get_llm_triage_scheduler] = lambda: scheduler
    csv_data = (Path(__file__).resolve().parents[2] / "data" / "llm_assisted_mvp_demo.csv").read_bytes()
    response = client.post(
        "/api/scans/upload",
        files={"file": ("synthetic.csv", csv_data, "text/csv")},
        data={
            "selected_fields": '["CONTRACT","UNIT_MEAS"]',
            "column_mapping": '{"PART_NO":"Stock Ref","DESCRIPTION":"Item Narrative"}',
            "threshold": "75",
            "product_authority": "legacy_compatibility",
        },
    )
    assert response.status_code == 200
    scan_id = response.json()["scan_id"]
    run = db.query(LlmTriageRun).filter_by(scan_id=scan_id).one()
    assert run.state == "QUEUED"
    assert scheduler.calls == [(scan_id, False)]
    assert db.query(DuplicateScan).filter_by(id=scan_id).one().status == "COMPLETED"


def test_disabled_scan_upload_creates_no_run_or_provider_work(client, db):
    scheduler = CaptureScheduler()
    app.dependency_overrides[get_llm_settings] = lambda: Settings()
    app.dependency_overrides[get_llm_triage_scheduler] = lambda: scheduler
    csv_data = b"PART_NO,DESCRIPTION\nA-1,Motor 10 kW\nA-2,10 kW motor\n"
    response = client.post(
        "/api/scans/upload",
        files={"file": ("synthetic.csv", csv_data, "text/csv")},
        data={"threshold": "60"},
    )
    assert response.status_code == 200
    assert db.query(LlmTriageRun).count() == 0
    assert scheduler.calls == []


def test_status_api_is_safe_and_candidate_api_batch_loads_triage_snapshots(client, db):
    scan = _scan(db)
    candidates = [_candidate(db, scan) for _ in range(3)]
    run = LlmTriageRun(scan_id=scan.id, state="COMPLETED", total_eligible=3)
    db.add(run)
    for candidate in candidates:
        db.add(LlmAdvisorySnapshot(
            candidate_id=candidate.id,
            capability=LLMCapability.CANDIDATE_TRIAGE.value,
            state="AVAILABLE",
            llm_used=True,
            cache_hit=False,
            provider="groq",
            model="triage-test-model",
            assessment="SUPPORTS_DUPLICATE",
            confidence=0.8,
            supporting_evidence='["bounded"]',
            conflicting_evidence="[]",
            recommended_action="HUMAN_REVIEW",
            deterministic_result_authoritative=True,
        ))
    db.commit()
    status = client.get(f"/api/scans/{scan.id}/llm-triage")
    assert status.status_code == 200
    assert "secret" not in status.text.lower()
    assert set(status.json()) == {
        "state", "total_eligible", "processed_count", "likely_duplicate_count",
        "downgraded_count", "human_review_count", "failed_count", "skipped_count",
        "progress_percent", "started_at", "completed_at", "updated_at",
        "last_safe_error_category",
        "failure_categories",
    }
    assert status.json()["updated_at"].endswith("Z")
    snapshot_selects = []

    def count_snapshot_selects(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT") and "llm_advisory_snapshot" in statement:
            snapshot_selects.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count_snapshot_selects)
    try:
        response = client.get(f"/api/scans/{scan.id}/candidates")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count_snapshot_selects)
    assert response.status_code == 200
    assert len(snapshot_selects) == 1
    old_fields = {"id", "business_status", "confidence_level", "similarity_score", "review_status"}
    new_fields = {
        "llm_triage_state", "llm_triage_assessment", "llm_triage_confidence",
        "llm_triage_recommended_action", "llm_triage_supporting_evidence",
        "llm_triage_conflicting_evidence", "llm_triage_provider", "llm_triage_model",
        "llm_triage_cache_hit", "llm_triage_generated_at", "effective_status",
        "effective_recommended_action", "deterministic_result_authoritative",
    }
    assert old_fields | new_fields <= set(response.json()[0])
    assert response.json()[0]["effective_status"] == "LLM_LIKELY_DUPLICATE"


def test_enhanced_export_prefers_triage_and_never_calls_provider(client, db):
    scan = _scan(db)
    candidate = _candidate(db, scan)
    db.add(LlmTriageRun(scan_id=scan.id, state="COMPLETED", total_eligible=1))
    db.add_all([
        LlmAdvisorySnapshot(
            candidate_id=candidate.id,
            capability=LLMCapability.CANDIDATE_ADVISORY.value,
            state="AVAILABLE", llm_used=True, cache_hit=False,
            assessment="INCONCLUSIVE", deterministic_result_authoritative=True,
        ),
        LlmAdvisorySnapshot(
            candidate_id=candidate.id,
            capability=LLMCapability.CANDIDATE_TRIAGE.value,
            state="AVAILABLE", llm_used=True, cache_hit=False, provider="groq",
            assessment="SUPPORTS_DUPLICATE", confidence=0.9,
            deterministic_result_authoritative=True,
        ),
    ])
    db.commit()
    response = client.get(f"/api/scans/{scan.id}/export-with-llm")
    row = list(csv.DictReader(io.StringIO(response.text)))[0]
    assert row["llm_assessment"] == "SUPPORTS_DUPLICATE"
    assert row["effective_status"] == "LLM_LIKELY_DUPLICATE"
    assert row["llm_triage_run_state"] == "COMPLETED"


def test_manual_candidate_advisory_endpoint_remains_bodyless(client):
    response = client.post("/api/llm/candidates/999/advisory")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("exc", "category"),
    [
        (LLMProviderHTTPError(status_code=429), "rate_limited"),
        (LLMProviderHTTPError(status_code=503), "provider_5xx"),
        (LLMProviderTimeoutError(), "provider_timeout"),
        (LLMProviderNetworkError(), "network_failure"),
        (LLMProviderMalformedJSONError(), "invalid_provider_output"),
        (LLMProviderHTTPError(status_code=400), "provider_failure"),
        (RuntimeError("private detail"), "provider_failure"),
    ],
)
def test_safe_provider_failure_classifications(exc, category):
    assert safe_error_category(exc) == category


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_minimum_interval_is_enforced_with_injectable_clock_and_sleeper(db):
    scan = _scan(db)
    for index in range(3):
        _candidate(db, scan, part_no_a=f"PACE-{index}")
    configuration = _settings(llm_triage_min_interval_ms=1000)
    prepare_triage_run(db, scan.id, configuration)
    provider = FakeProvider([_advisory()] * 3)
    fake_time = FakeTime()
    asyncio.run(_runner(
        db,
        provider,
        configuration,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        jitter=lambda _low, _high: 0,
    ).run(scan.id))
    assert len(provider.calls) == 3
    assert fake_time.sleeps == [1.0, 1.0]


def test_retryable_failures_use_bounded_backoff_and_typed_retry_after(db):
    scan = _scan(db)
    _candidate(db, scan)
    configuration = _settings(
        llm_triage_max_retries=2,
        llm_triage_consecutive_failure_limit=10,
    )
    prepare_triage_run(db, scan.id, configuration)
    provider = FakeProvider([
        LLMProviderHTTPError(status_code=429, retry_after_seconds=2),
        LLMProviderHTTPError(status_code=503),
        _advisory("SUPPORTS_DUPLICATE"),
    ])
    fake_time = FakeTime()
    asyncio.run(_runner(
        db,
        provider,
        configuration,
        clock=fake_time.clock,
        sleeper=fake_time.sleep,
        jitter=lambda _low, _high: 0,
    ).run(scan.id))
    assert len(provider.calls) == 3
    assert fake_time.sleeps == [2.0, 1.0]
    snapshot = db.query(LlmAdvisorySnapshot).one()
    assert snapshot.state == "AVAILABLE"


def test_invalid_provider_output_is_never_retried(db):
    scan = _scan(db)
    candidate = _candidate(db, scan)
    configuration = _settings(llm_triage_max_retries=2)
    prepare_triage_run(db, scan.id, configuration)
    provider = FakeProvider([LLMProviderMalformedJSONError("private output")])
    asyncio.run(_runner(db, provider, configuration).run(scan.id))
    snapshot = db.query(LlmAdvisorySnapshot).filter_by(candidate_id=candidate.id).one()
    assert len(provider.calls) == 1
    assert snapshot.state == "FAILED"
    assert snapshot.safe_error_category == "invalid_provider_output"


def test_consecutive_retryable_failures_pause_and_resume_pending_only(db):
    scan = _scan(db)
    candidates = [
        _candidate(db, scan, part_no_a=f"RESUME-{index}")
        for index in range(6)
    ]
    protected = {
        candidate.id: (
            candidate.business_status,
            candidate.similarity_score,
            candidate.review_status,
        )
        for candidate in candidates
    }
    configuration = _settings(
        llm_triage_max_retries=0,
        llm_triage_consecutive_failure_limit=2,
    )
    prepare_triage_run(db, scan.id, configuration)
    failing = FakeProvider([
        LLMProviderTimeoutError("private one"),
        LLMProviderNetworkError("private two"),
    ])
    asyncio.run(_runner(db, failing, configuration).run(scan.id))
    run = db.query(LlmTriageRun).filter_by(scan_id=scan.id).one()
    assert run.state == "PAUSED"
    assert run.processed_count == 2
    assert run.last_safe_error_category == "network_failure"
    assert db.query(LlmAdvisorySnapshot).count() == 2
    assert len(failing.calls) == 2

    resumed, should_schedule = prepare_triage_run(db, scan.id, configuration)
    assert resumed.state == "QUEUED" and should_schedule is True
    successful = FakeProvider([_advisory()] * 4)
    asyncio.run(_runner(db, successful, configuration).run(scan.id))
    db.expire_all()
    run = db.query(LlmTriageRun).filter_by(scan_id=scan.id).one()
    assert run.state == "COMPLETED_WITH_FAILURES"
    assert len(successful.calls) == 4
    assert db.query(LlmAdvisorySnapshot).count() == 6
    for candidate in candidates:
        refreshed = db.get(DuplicateCandidate, candidate.id)
        assert (
            refreshed.business_status,
            refreshed.similarity_score,
            refreshed.review_status,
        ) == protected[candidate.id]


def test_retry_failed_respects_batch_and_never_resends_success(db):
    scan = _scan(db)
    candidates = [
        _candidate(db, scan, part_no_a=f"RETRY-{index}")
        for index in range(6)
    ]
    db.add(LlmTriageRun(scan_id=scan.id, state="COMPLETED_WITH_FAILURES", total_eligible=6))
    for index, candidate in enumerate(candidates):
        db.add(LlmAdvisorySnapshot(
            candidate_id=candidate.id,
            capability=LLMCapability.CANDIDATE_TRIAGE.value,
            state="AVAILABLE" if index == 0 else "FAILED",
            llm_used=True,
            cache_hit=False,
            assessment="INCONCLUSIVE" if index == 0 else None,
            safe_error_category=None if index == 0 else "provider_5xx",
            deterministic_result_authoritative=True,
        ))
    db.commit()
    configuration = _settings(llm_triage_retry_batch_size=2)
    provider = FakeProvider([_advisory()] * 2)
    asyncio.run(_runner(db, provider, configuration).run(scan.id, retry_failed=True))
    assert len(provider.calls) == 2
    assert db.query(LlmAdvisorySnapshot).filter_by(state="AVAILABLE").count() == 3
    assert db.query(LlmAdvisorySnapshot).filter_by(state="FAILED").count() == 3
    assert db.get(LlmAdvisorySnapshot, 1).state == "AVAILABLE"


def test_failure_category_aggregation_is_safe_and_scan_scoped(db):
    scan = _scan(db)
    candidates = [_candidate(db, scan) for _ in range(3)]
    for candidate, category in zip(
        candidates, ["rate_limited", "rate_limited", "provider_timeout"]
    ):
        db.add(LlmAdvisorySnapshot(
            candidate_id=candidate.id,
            capability=LLMCapability.CANDIDATE_TRIAGE.value,
            state="FAILED",
            llm_used=True,
            cache_hit=False,
            safe_error_category=category,
            deterministic_result_authoritative=True,
        ))
    db.commit()
    assert triage_failure_categories(db, scan.id) == {
        "provider_timeout": 1,
        "rate_limited": 2,
    }


def _triage_response(assessment, basis, evidence):
    return CandidateTriageResponse(
        assessment=assessment,
        confidence=0.8,
        supporting_evidence=evidence,
        conflicting_evidence=[],
        recommended_action="KEEP_DETERMINISTIC_RESULT",
        deterministic_result_authoritative=True,
        decision_basis=basis,
    )


@pytest.mark.parametrize(
    "response",
    [
        _triage_response(
            "SUPPORTS_DUPLICATE", ["SEMANTIC_EQUIVALENCE"], ["Contract matches."]
        ),
        _triage_response(
            "SUPPORTS_NON_DUPLICATE", ["PRODUCT_TYPE_CONFLICT"], ["Part numbers differ."]
        ),
        _triage_response("SUPPORTS_DUPLICATE", [], ["Specific descriptions align."]),
        _triage_response("SUPPORTS_NON_DUPLICATE", [], ["Models conflict."]),
        _triage_response(
            "SUPPORTS_DUPLICATE",
            ["SEMANTIC_EQUIVALENCE", "MODEL_CONFLICT"],
            ["Specific model evidence."],
        ),
    ],
)
def test_weak_missing_or_contradictory_decision_basis_is_inconclusive(response):
    validated = validate_triage_decision(response)
    assert validated.assessment.value == "INCONCLUSIVE"
    assert validated.recommended_action.value == "HUMAN_REVIEW"


@pytest.mark.parametrize(
    ("assessment", "basis", "evidence"),
    [
        (
            "SUPPORTS_DUPLICATE",
            ["ABBREVIATION_OR_ALIAS"],
            ["SS cent pump and stainless steel centrifugal pump identify the same model."],
        ),
        (
            "SUPPORTS_NON_DUPLICATE",
            ["TECHNICAL_ROLE_CONFLICT"],
            ["Compressor-side bracket and top-side bracket have different technical roles."],
        ),
    ],
)
def test_valid_typed_decision_bases_pass(assessment, basis, evidence):
    validated = validate_triage_decision(_triage_response(assessment, basis, evidence))
    assert validated.assessment.value == assessment


def test_generic_description_plus_site_cannot_promote_duplicate():
    request = CandidateAdvisoryRequest(
        left={
            "part_number": "XJ-100",
            "description": "Industrial coupling",
            "site_or_contract": "SYN-W",
        },
        right={
            "part_number": "QZ-900",
            "description": "Industrial coupling",
            "site_or_contract": "SYN-W",
        },
        deterministic_score=89,
        deterministic_confidence="MEDIUM",
        deterministic_status="POSSIBLE_DUPLICATE_REVIEW",
        deterministic_rule_decision="ALLOW",
        critical_mismatches=[],
    )
    response = _triage_response(
        "SUPPORTS_DUPLICATE",
        ["SEMANTIC_EQUIVALENCE"],
        ["Both descriptions identify an industrial coupling."],
    )
    validated = validate_triage_decision(response, request)
    assert validated.assessment.value == "INCONCLUSIVE"
    assert validated.recommended_action.value == "HUMAN_REVIEW"
