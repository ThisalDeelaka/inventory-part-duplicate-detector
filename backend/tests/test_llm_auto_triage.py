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
    DuplicateCandidate,
    DuplicateScan,
    LlmAdvisorySnapshot,
    LlmTriageRun,
)
from app.llm.audit import LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.exceptions import LLMProviderTimeoutError
from app.llm.provider import LLMProviderResult
from app.llm.runtime import get_llm_settings
from app.llm.service_contracts import LLMCapability
from app.main import app
from app.services.llm_triage_service import (
    LlmTriageRunner,
    automatic_triage_ready,
    candidate_is_triage_eligible,
    effective_status,
    eligible_candidate_ids,
    get_llm_triage_scheduler,
    prepare_triage_run,
)


def _settings(**overrides):
    values = {
        "llm_demo_enabled": True,
        "llm_provider": "groq",
        "groq_api_key": "synthetic-test-value",
        "groq_model": "triage-test-model",
        "llm_auto_triage_enabled": True,
        "llm_triage_concurrency": 1,
        "llm_triage_max_candidates_per_scan": 250,
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
    return {
        "assessment": assessment,
        "confidence": confidence,
        "supporting_evidence": ["Bounded synthetic evidence."],
        "conflicting_evidence": [],
        "recommended_action": "HUMAN_REVIEW",
        "deterministic_result_authoritative": True,
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


def _runner(db, provider, configuration=None, session_factory=None):
    factory = session_factory or sessionmaker(bind=db.get_bind())
    return LlmTriageRunner(
        session_factory=factory,
        configuration=configuration or _settings(),
        cache=LLMCache(enabled=True, max_entries=50, ttl_seconds=60),
        audit=LLMAuditStore(enabled=True, max_entries=100),
        provider_factory=lambda _configuration: provider,
    )


def test_triage_configuration_bounds_are_validated():
    assert _settings().llm_triage_concurrency == 1
    for values in (
        {"llm_triage_concurrency": 0},
        {"llm_triage_concurrency": 9},
        {"llm_triage_max_candidates_per_scan": 0},
        {"llm_triage_max_candidates_per_scan": 1001},
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
    candidate = _candidate(db, scan)
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
    assert failed.state == "FAILED" and failed.safe_error_category == "timeout"
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
