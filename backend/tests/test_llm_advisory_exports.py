import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.db.models import DuplicateCandidate, DuplicateScan, LlmAdvisorySnapshot, RuleExclusionAudit
from app.llm.audit import LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.exceptions import (
    LLMProviderConfigurationError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderTimeoutError,
)
from app.llm.provider import LLMProviderResult
from app.llm.runtime import get_llm_audit, get_llm_cache, get_llm_provider_factory, get_llm_settings
from app.llm.service_contracts import LLMCapability
from app.main import app
from app.services.llm_export_service import ASSISTED_FIELDS, format_utc_timestamp, sanitize_llm_csv_cell


DETERMINISTIC_CANDIDATE_FIELDS = [
    "part_no_a", "description_a", "contract_a", "part_no_b", "description_b", "contract_b",
    "similarity_score", "confidence_level", "business_status", "rule_decision", "rejection_reason",
    "scan_mode", "critical_mismatches", "generic_description_warning", "application_context_a",
    "application_context_b", "application_context_warning", "normalized_description_a",
    "normalized_description_b", "normalized_part_no_a", "normalized_part_no_b", "variant_attributes_a",
    "variant_attributes_b", "description_similarity", "tfidf_score", "fuzzy_score", "part_no_similarity",
    "technical_token_score", "matched_fields", "mismatched_fields", "explanation", "recommended_action",
    "review_status",
]

DETERMINISTIC_REJECTION_FIELDS = [
    "part_no_a", "description_a", "contract_a", "part_no_b", "description_b", "contract_b",
    "similarity_score", "confidence_level", "business_status", "rule_decision", "rejection_reason",
    "critical_mismatches", "explanation",
]

LLM_FIELDS = [
    "llm_state", "llm_used", "llm_cache_hit", "llm_provider", "llm_model", "llm_prompt_version",
    "llm_assessment", "llm_confidence", "llm_recommended_action", "llm_supporting_evidence",
    "llm_conflicting_evidence", "llm_bypass_reason", "llm_safe_error_category", "llm_generated_at",
    "deterministic_result_authoritative",
]


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return LLMProviderResult(provider="groq", model="snapshot-test-model", content=value, request_id="safe-id")


def _configure(provider, enabled=True):
    settings = Settings(
        llm_demo_enabled=enabled,
        llm_provider="groq" if enabled else "none",
        groq_api_key="synthetic-test-value" if enabled else "",
        groq_model="snapshot-test-model",
    )
    cache = LLMCache(enabled=True, max_entries=20, ttl_seconds=60)
    audit = LLMAuditStore(enabled=True, max_entries=50)
    app.dependency_overrides[get_llm_settings] = lambda: settings
    app.dependency_overrides[get_llm_cache] = lambda: cache
    app.dependency_overrides[get_llm_audit] = lambda: audit
    app.dependency_overrides[get_llm_provider_factory] = lambda: (lambda configuration: provider)


def _scan(db, name="snapshot scan"):
    scan = DuplicateScan(scan_name=name, threshold=75, model_version="test-v1", status="COMPLETED")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def _candidate(db, scan, **overrides):
    values = {
        "scan_id": scan.id, "contract_a": "S1", "part_no_a": "A-1", "description_a": "Motor 10 kW",
        "contract_b": "S1", "part_no_b": "A-2", "description_b": "10 kW motor", "similarity_score": 82.5,
        "confidence_level": "MEDIUM", "description_similarity": 80, "tfidf_score": 80, "fuzzy_score": 80,
        "part_no_similarity": 70, "technical_token_score": 90, "matched_fields": "[]", "mismatched_fields": "[]",
        "explanation": "Deterministic explanation.", "recommended_action": "Manual review recommended",
        "business_status": "POSSIBLE_DUPLICATE_REVIEW", "rule_decision": "ALLOW", "rejection_reason": "",
        "scan_mode": "SAME_SITE_DUPLICATE", "critical_mismatches": "[]",
    }
    values.update(overrides)
    candidate = DuplicateCandidate(**values)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def _rejection(db, scan, rule_decision="REJECT", rejection_reason="EXACT_PART_NO_CONFLICT"):
    item = RuleExclusionAudit(
        scan_id=scan.id, contract_a="S1", part_no_a="R-1", description_a="Rejected A",
        contract_b="S1", part_no_b="R-2", description_b="Rejected B", similarity_score=93,
        confidence_level="HIGH", business_status="REJECTED_BY_BUSINESS_RULE", rule_decision=rule_decision,
        rejection_reason=rejection_reason, critical_mismatches="[]", explanation="Deterministic exclusion.",
    )
    db.add(item)
    db.commit()
    return item


def _advisory(evidence="Descriptions overlap."):
    return {
        "assessment": "INCONCLUSIVE", "confidence": 0.61,
        "supporting_evidence": [evidence], "conflicting_evidence": ["Different identifiers."],
        "recommended_action": "HUMAN_REVIEW", "deterministic_result_authoritative": True,
    }


def _rows(response):
    return list(csv.DictReader(io.StringIO(response.text)))


def test_legacy_exports_are_unchanged_after_snapshot_and_enhanced_columns_are_appended(client, db):
    scan = _scan(db)
    candidate = _candidate(db, scan)
    _rejection(db, scan)
    candidate_before = client.get(f"/api/scans/{scan.id}/export").content
    rejection_before = client.get(f"/api/scans/{scan.id}/rejections/export").content
    assert next(csv.reader(io.StringIO(candidate_before.decode()))) == DETERMINISTIC_CANDIDATE_FIELDS
    assert next(csv.reader(io.StringIO(rejection_before.decode()))) == DETERMINISTIC_REJECTION_FIELDS
    db.add(LlmAdvisorySnapshot(candidate_id=candidate.id, capability=LLMCapability.CANDIDATE_ADVISORY.value, state="AVAILABLE", llm_used=True, cache_hit=False, deterministic_result_authoritative=True))
    db.commit()
    assert client.get(f"/api/scans/{scan.id}/export").content == candidate_before
    assert client.get(f"/api/scans/{scan.id}/rejections/export").content == rejection_before
    enhanced = client.get(f"/api/scans/{scan.id}/export-with-llm")
    assert next(csv.reader(io.StringIO(enhanced.text))) == DETERMINISTIC_CANDIDATE_FIELDS + LLM_FIELDS + ASSISTED_FIELDS
    assert enhanced.headers["content-disposition"] == f'attachment; filename="scan-{scan.id}-candidates-with-llm.csv"'


def test_no_snapshot_defaults_and_exports_need_no_provider_or_configuration(client, db):
    scan = _scan(db)
    _candidate(db, scan)
    _rejection(db, scan)

    def forbidden_factory(configuration):
        raise AssertionError("export must not instantiate a provider")

    _configure(forbidden_factory, enabled=False)
    app.dependency_overrides[get_llm_provider_factory] = lambda: forbidden_factory
    candidate_response = client.get(f"/api/scans/{scan.id}/export-with-llm")
    rejection_response = client.get(f"/api/scans/{scan.id}/rejections/export-with-llm")
    assert candidate_response.status_code == rejection_response.status_code == 200
    row = _rows(candidate_response)[0]
    assert row["llm_state"] == "NOT_REQUESTED"
    assert row["llm_used"] == "false"
    assert row["deterministic_result_authoritative"] == "true"
    assert all(row[field] == "" for field in LLM_FIELDS if field not in {"llm_state", "llm_used", "deterministic_result_authoritative"})


def test_explicit_success_then_cache_hit_updates_one_snapshot_and_export(client, db):
    scan = _scan(db)
    candidate = _candidate(db, scan)
    protected = {field: getattr(candidate, field) for field in DETERMINISTIC_CANDIDATE_FIELDS}
    provider = FakeProvider([_advisory()])
    _configure(provider)
    first = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    first_generated_at = db.query(LlmAdvisorySnapshot).one().generated_at
    second = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert first.status_code == second.status_code == 200
    snapshots = db.query(LlmAdvisorySnapshot).all()
    assert len(snapshots) == 1
    assert snapshots[0].state == "AVAILABLE"
    assert snapshots[0].cache_hit is True
    assert snapshots[0].llm_used is False
    assert snapshots[0].generated_at >= first_generated_at
    assert snapshots[0].supporting_evidence == '["Descriptions overlap."]'
    persisted = json.dumps({key: value for key, value in snapshots[0].__dict__.items() if not key.startswith("_")}, default=str).lower()
    assert all(term not in persisted for term in ("synthetic-test-value", "system_prompt", "user_prompt", "authorization", "headers", "raw_response"))
    row = _rows(client.get(f"/api/scans/{scan.id}/export-with-llm"))[0]
    assert row["llm_state"] == "AVAILABLE"
    assert row["llm_cache_hit"] == "true"
    assert row["llm_used"] == "false"
    assert row["llm_assessment"] == "INCONCLUSIVE"
    assert row["llm_confidence"] == "0.61"
    assert row["llm_recommended_action"] == "HUMAN_REVIEW"
    assert row["llm_supporting_evidence"] == '["Descriptions overlap."]'
    assert row["llm_conflicting_evidence"] == '["Different identifiers."]'
    assert row["llm_generated_at"].endswith("Z")
    assert row["deterministic_result_authoritative"] == "true"
    assert len(provider.calls) == 1
    db.refresh(candidate)
    assert {field: getattr(candidate, field) for field in DETERMINISTIC_CANDIDATE_FIELDS} == protected


def test_explicit_bypass_persists_without_provider_or_fabricated_advice(client, db):
    scan = _scan(db)
    candidate = _candidate(db, scan, business_status="LIKELY_DUPLICATE", confidence_level="HIGH")
    provider = FakeProvider([])
    _configure(provider)
    response = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert response.status_code == 200
    snapshot = db.query(LlmAdvisorySnapshot).one()
    assert snapshot.state == "INELIGIBLE"
    assert snapshot.llm_used is False
    assert snapshot.provider is snapshot.model is snapshot.prompt_version is None
    row = _rows(client.get(f"/api/scans/{scan.id}/export-with-llm"))[0]
    assert row["llm_bypass_reason"] == "INELIGIBLE_CLEAR_DUPLICATE"
    assert row["llm_assessment"] == row["llm_confidence"] == row["llm_recommended_action"] == ""
    assert provider.calls == []


def test_safe_failure_is_saved_without_raw_detail_and_later_success_replaces_it(client, db):
    scan = _scan(db)
    candidate = _candidate(db, scan)
    private_detail = "Authorization Bearer private-provider-body"
    provider = FakeProvider([LLMProviderTimeoutError(private_detail), _advisory()])
    _configure(provider)
    failed = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert failed.status_code == 504
    snapshot = db.query(LlmAdvisorySnapshot).one()
    assert snapshot.state == "FAILED"
    assert snapshot.safe_error_category == "timeout"
    serialized = json.dumps({key: value for key, value in snapshot.__dict__.items() if not key.startswith("_")}, default=str)
    assert private_detail not in serialized
    failed_csv = client.get(f"/api/scans/{scan.id}/export-with-llm").text
    assert private_detail not in failed_csv
    failed_row = _rows(client.get(f"/api/scans/{scan.id}/export-with-llm"))[0]
    assert failed_row["llm_safe_error_category"] == "timeout"
    assert failed_row["llm_assessment"] == ""
    succeeded = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert succeeded.status_code == 200
    assert db.query(LlmAdvisorySnapshot).count() == 1
    assert db.query(LlmAdvisorySnapshot).one().state == "AVAILABLE"


@pytest.mark.parametrize(
    ("category", "status", "provider_error", "enabled", "factory_failure"),
    [
        ("disabled", 503, None, False, False),
        ("configuration", 503, LLMProviderConfigurationError("private configuration detail"), True, True),
        ("timeout", 504, LLMProviderTimeoutError("private timeout detail"), True, False),
        ("provider_failure", 502, LLMProviderHTTPError("private provider response"), True, False),
        ("invalid_provider_output", 502, LLMProviderMalformedJSONError("private malformed body"), True, False),
    ],
)
def test_safe_failure_categories_persist_and_export_without_mutating_candidate(
    client, db, category, status, provider_error, enabled, factory_failure
):
    scan = _scan(db, category)
    candidate = _candidate(db, scan)
    protected_names = tuple(DETERMINISTIC_CANDIDATE_FIELDS)
    before = {name: getattr(candidate, name) for name in protected_names}
    provider = FakeProvider([] if provider_error is None or factory_failure else [provider_error])
    _configure(provider, enabled=enabled)
    if factory_failure:
        def failing_factory(_configuration):
            raise provider_error
        app.dependency_overrides[get_llm_provider_factory] = lambda: failing_factory

    response = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert response.status_code == status
    assert response.json()["detail"]["category"] == category
    snapshot = db.query(LlmAdvisorySnapshot).one()
    assert snapshot.state == "FAILED"
    assert snapshot.safe_error_category == category
    stored = json.dumps({key: value for key, value in snapshot.__dict__.items() if not key.startswith("_")}, default=str)
    raw_detail = str(provider_error) if provider_error is not None else "LLM assistance is disabled"
    assert raw_detail not in stored
    export_row = _rows(client.get(f"/api/scans/{scan.id}/export-with-llm"))[0]
    assert export_row["llm_state"] == "FAILED"
    assert export_row["llm_safe_error_category"] == category
    assert export_row["llm_assessment"] == ""
    assert export_row["llm_confidence"] == ""
    assert export_row["llm_recommended_action"] == ""
    assert raw_detail not in json.dumps(export_row)
    db.refresh(candidate)
    assert {name: getattr(candidate, name) for name in protected_names} == before


def test_snapshots_are_isolated_to_exact_scan(client, db):
    first_scan = _scan(db, "first")
    second_scan = _scan(db, "second")
    first = _candidate(db, first_scan, part_no_a="FIRST")
    second = _candidate(db, second_scan, part_no_a="SECOND")
    db.add_all([
        LlmAdvisorySnapshot(candidate_id=first.id, capability=LLMCapability.CANDIDATE_ADVISORY.value, state="AVAILABLE", llm_used=True, cache_hit=False, assessment="INCONCLUSIVE", deterministic_result_authoritative=True),
        LlmAdvisorySnapshot(candidate_id=second.id, capability=LLMCapability.CANDIDATE_ADVISORY.value, state="FAILED", llm_used=True, cache_hit=False, safe_error_category="timeout", deterministic_result_authoritative=True),
    ])
    db.commit()
    first_rows = _rows(client.get(f"/api/scans/{first_scan.id}/export-with-llm"))
    assert len(first_rows) == 1
    assert first_rows[0]["part_no_a"] == "FIRST"
    assert first_rows[0]["llm_state"] == "AVAILABLE"
    assert "SECOND" not in json.dumps(first_rows)


def test_exclusion_state_uses_rule_taxonomy_and_never_fabricates_advisory(client, db):
    scan = _scan(db)
    _rejection(db, scan, "REJECT", "HARD_RULE_REASON")
    _rejection(db, scan, "DOWNGRADE", "REVIEWABLE_REASON")
    _rejection(db, scan, "UNKNOWN", "UNKNOWN_REASON")
    response = client.get(f"/api/scans/{scan.id}/rejections/export-with-llm")
    assert response.headers["content-disposition"] == f'attachment; filename="scan-{scan.id}-rule-exclusions-with-llm.csv"'
    rows = _rows(response)
    assert next(csv.reader(io.StringIO(response.text))) == DETERMINISTIC_REJECTION_FIELDS + LLM_FIELDS
    by_reason = {row["rejection_reason"]: row for row in rows}
    assert by_reason["HARD_RULE_REASON"]["llm_state"] == "NOT_APPLICABLE_HARD_RULE"
    assert by_reason["HARD_RULE_REASON"]["llm_bypass_reason"] == "HARD_RULE_REASON"
    assert by_reason["REVIEWABLE_REASON"]["llm_state"] == "NOT_REQUESTED"
    assert by_reason["UNKNOWN_REASON"]["llm_state"] == "NOT_REQUESTED"
    for row in by_reason.values():
        assert row["llm_assessment"] == ""
        assert row["llm_confidence"] == ""
        assert row["llm_recommended_action"] == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""), ("", ""), ("ordinary safe text", "ordinary safe text"),
        ("'already safe", "'already safe"), ("=FORMULA", "'=FORMULA"),
        ("  +FORMULA", "'  +FORMULA"), ("-FORMULA", "'-FORMULA"),
        (" @FORMULA", "' @FORMULA"), ("\tFORMULA", "'\tFORMULA"),
        ("  \rFORMULA", "'  \rFORMULA"), ("\nFORMULA", "'\nFORMULA"),
        (True, "true"), (False, "false"), (0.61, "0.61"),
    ],
)
def test_llm_csv_cell_security_and_scalar_formatting(value, expected):
    actual = sanitize_llm_csv_cell(value)
    assert actual == expected
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        assert actual.startswith("'") and not actual.startswith("''")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (datetime(2026, 7, 22, 10, 11, 12, 345678), "2026-07-22T10:11:12.345678Z"),
        (datetime(2026, 7, 22, 10, 11, 12, tzinfo=timezone.utc), "2026-07-22T10:11:12Z"),
        (datetime(2026, 7, 22, 15, 41, 12, tzinfo=timezone(timedelta(hours=5, minutes=30))), "2026-07-22T10:11:12Z"),
    ],
)
def test_format_utc_timestamp_is_explicit_and_never_uses_local_time(value, expected):
    assert format_utc_timestamp(value) == expected


def test_every_stored_llm_text_field_is_formula_neutralized_in_real_csv(client, db):
    scan = _scan(db)
    candidate = _candidate(db, scan)
    db.add(LlmAdvisorySnapshot(
        candidate_id=candidate.id, capability=LLMCapability.CANDIDATE_ADVISORY.value,
        state="AVAILABLE", llm_used=True, cache_hit=False, provider="=PROVIDER",
        model="  +MODEL", prompt_version="-VERSION", assessment="@ASSESSMENT",
        confidence=0.61, recommended_action="\tACTION", supporting_evidence="\rSUPPORT",
        conflicting_evidence="\nCONFLICT", bypass_reason="  =REASON",
        safe_error_category=" @CATEGORY", deterministic_result_authoritative=True,
        generated_at=datetime(2026, 7, 22, 10, 11, 12, 123456),
    ))
    db.commit()
    row = _rows(client.get(f"/api/scans/{scan.id}/export-with-llm"))[0]
    protected_fields = (
        "llm_provider", "llm_model", "llm_prompt_version", "llm_assessment",
        "llm_recommended_action", "llm_supporting_evidence", "llm_conflicting_evidence",
        "llm_bypass_reason", "llm_safe_error_category",
    )
    for field in protected_fields:
        assert row[field].startswith("'") and not row[field].startswith("''")
    assert row["llm_model"] == "'  +MODEL"
    assert row["llm_used"] == "true"
    assert row["llm_cache_hit"] == "false"
    assert row["llm_confidence"] == "0.61"
    assert row["llm_generated_at"] == "2026-07-22T10:11:12.123456Z"


def test_snapshot_commit_failure_rolls_back_without_candidate_mutation(client, db, monkeypatch):
    scan = _scan(db)
    candidate = _candidate(db, scan)
    before = (candidate.similarity_score, candidate.business_status, candidate.review_status)
    _configure(FakeProvider([_advisory()]))
    original_commit = db.commit

    def fail_commit():
        raise RuntimeError("private database detail")

    monkeypatch.setattr(db, "commit", fail_commit)
    response = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert response.status_code == 500
    assert response.json()["detail"]["category"] == "snapshot_persistence_failure"
    assert "private database detail" not in response.text
    monkeypatch.setattr(db, "commit", original_commit)
    assert db.query(LlmAdvisorySnapshot).count() == 0
    db.refresh(candidate)
    assert (candidate.similarity_score, candidate.business_status, candidate.review_status) == before
