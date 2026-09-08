import json

import pytest

from app.core.config import Settings
from app.db.models import DuplicateCandidate
from app.llm.audit import LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.exceptions import LLMProviderMalformedJSONError, LLMProviderTimeoutError
from app.llm.provider import LLMProviderResult
from app.llm.runtime import (
    get_llm_audit,
    get_llm_cache,
    get_llm_provider_factory,
    get_llm_settings,
)
from app.main import app


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return LLMProviderResult(
            provider="groq", model="api-model", content=value, request_id="api-req"
        )


def _configure(provider, *, enabled=True):
    configuration = Settings(
        llm_demo_enabled=enabled,
        llm_provider="groq" if enabled else "none",
        groq_api_key="synthetic-api-test-key" if enabled else "",
        groq_model="api-model",
    )
    cache = LLMCache(enabled=True, max_entries=20, ttl_seconds=60)
    audit = LLMAuditStore(enabled=True, max_entries=50)
    app.dependency_overrides[get_llm_settings] = lambda: configuration
    app.dependency_overrides[get_llm_cache] = lambda: cache
    app.dependency_overrides[get_llm_audit] = lambda: audit
    app.dependency_overrides[get_llm_provider_factory] = lambda: (
        lambda settings: provider
    )
    return cache, audit


def _persist_candidate(db, **overrides):
    values = {
        "scan_id": 1,
        "contract_a": "S1",
        "part_no_a": "A-1",
        "description_a": "Motor 10 kW",
        "contract_b": "S1",
        "part_no_b": "A-2",
        "description_b": "10 kW motor",
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


def test_status_works_disabled_without_provider_or_secret_metadata(client):
    class ForbiddenProvider:
        def __call__(self, configuration):
            raise AssertionError("status must not construct a provider")

    _configure(ForbiddenProvider(), enabled=False)
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["provider_configured"] is False
    assert set(body["prompt_versions"]) == {
        "column_suggestion", "difficult_value", "candidate_advisory"
        , "candidate_triage"
    }
    serialized = json.dumps(body).lower()
    assert "api_key" not in serialized
    assert "authorization" not in serialized
    assert "key_length" not in serialized


def test_column_api_accepts_only_source_and_samples_and_caches(client):
    provider = FakeProvider(
        [{
            "source_column": "Mystery",
            "suggested_canonical_field": "DESCRIPTION",
            "confidence": 0.75,
            "reason": "Text samples resemble descriptions.",
            "requires_confirmation": True,
        }]
    )
    _configure(provider)
    payload = {"source_column": "Mystery", "sample_values": ["Motor"]}
    first = client.post("/api/llm/column-suggestions", json=payload)
    second = client.post("/api/llm/column-suggestions", json=payload)
    assert first.status_code == 200
    assert first.json()["suggestion"]["requires_confirmation"] is True
    assert second.json()["metadata"]["cache_hit"] is True
    assert len(provider.calls) == 1

    rejected = client.post(
        "/api/llm/column-suggestions",
        json={**payload, "allowed_canonical_fields": ["PRIVATE_FIELD"]},
    )
    assert rejected.status_code == 422


def test_column_api_rejects_empty_and_blank_samples_before_provider(client):
    provider = FakeProvider([])
    _configure(provider)
    factory_calls = []

    def forbidden_factory(configuration):
        factory_calls.append(configuration)
        raise AssertionError("invalid request must not construct a provider")

    app.dependency_overrides[get_llm_provider_factory] = lambda: forbidden_factory
    for samples in ([], ["", "   "]):
        response = client.post(
            "/api/llm/column-suggestions",
            json={"source_column": "Mystery", "sample_values": samples},
        )
        assert response.status_code == 422
        assert response.status_code != 500
    assert factory_calls == []
    assert provider.calls == []


def test_column_api_mixed_samples_share_cleaned_cache_identity(client):
    provider = FakeProvider(
        [{
            "source_column": "Mystery",
            "suggested_canonical_field": "PART_NO",
            "confidence": 0.8,
            "reason": "Identifier-shaped value.",
            "requires_confirmation": True,
        }]
    )
    _configure(provider)
    mixed = client.post(
        "/api/llm/column-suggestions",
        json={"source_column": "Mystery", "sample_values": ["", "A-100", " "]},
    )
    cleaned = client.post(
        "/api/llm/column-suggestions",
        json={"source_column": "Mystery", "sample_values": ["A-100"]},
    )
    assert mixed.status_code == 200
    assert cleaned.status_code == 200
    assert cleaned.json()["metadata"]["cache_hit"] is True
    assert json.loads(provider.calls[0][1])["sample_values"] == ["A-100"]
    assert len(provider.calls) == 1


def test_difficult_value_api_maps_timeout_safely(client):
    provider = FakeProvider([LLMProviderTimeoutError("safe timeout")])
    _configure(provider)
    response = client.post(
        "/api/llm/difficult-values/interpret",
        json={"raw_value": "MTR", "field_context": "DESCRIPTION"},
    )
    assert response.status_code == 504
    assert response.json()["detail"]["category"] == "provider_timeout"


def test_difficult_value_api_rejects_invalid_context_and_blank_raw_before_provider(client):
    provider = FakeProvider([])
    _configure(provider)
    factory_calls = []

    def forbidden_factory(configuration):
        factory_calls.append(configuration)
        raise AssertionError("invalid request must not construct a provider")

    app.dependency_overrides[get_llm_provider_factory] = lambda: forbidden_factory
    invalid_payloads = [
        {"raw_value": "MTR", "field_context": context}
        for context in (
            "ACCOUNTING_GROUP",
            "UNIT_MEAS",
            "OTHER",
            "arbitrary free text",
        )
    ]
    invalid_payloads.append(
        {"raw_value": "   ", "field_context": "DESCRIPTION"}
    )
    for payload in invalid_payloads:
        response = client.post(
            "/api/llm/difficult-values/interpret", json=payload
        )
        assert response.status_code == 422
    assert factory_calls == []
    assert provider.calls == []


def test_candidate_api_missing_and_bypass_are_safe(client, db):
    provider = FakeProvider([])
    _configure(provider)
    assert client.post("/api/llm/candidates/999/advisory").status_code == 404

    candidate = _persist_candidate(
        db, business_status="LIKELY_DUPLICATE", confidence_level="HIGH"
    )
    response = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility"]["eligible"] is False
    assert body["eligibility"]["reason"] == "INELIGIBLE_CLEAR_DUPLICATE"
    assert body["metadata"]["llm_used"] is False
    assert provider.calls == []


@pytest.mark.parametrize(
    "malformed",
    ["{not-json", '{"group":"COLOR"}', '[{"group":"COLOR"}]'],
)
def test_candidate_api_invalid_deterministic_evidence_bypasses_safely(
    client, db, malformed
):
    provider = FakeProvider([])
    _cache, audit = _configure(provider)
    candidate = _persist_candidate(db, critical_mismatches=malformed)
    before = (
        candidate.similarity_score,
        candidate.confidence_level,
        candidate.business_status,
        candidate.rule_decision,
        candidate.rejection_reason,
        candidate.review_status,
    )

    response = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility"]["reason"] == (
        "INELIGIBLE_INVALID_DETERMINISTIC_EVIDENCE"
    )
    assert body["metadata"]["llm_used"] is False
    assert provider.calls == []
    db.refresh(candidate)
    assert (
        candidate.similarity_score,
        candidate.confidence_level,
        candidate.business_status,
        candidate.rule_decision,
        candidate.rejection_reason,
        candidate.review_status,
    ) == before
    serialized = json.dumps(
        {"response": body, "audit": audit.events()[-1].model_dump(mode="json")}
    )
    assert malformed not in serialized


def test_candidate_api_uses_persisted_evidence_and_does_not_modify_candidate(client, db):
    provider = FakeProvider(
        [{
            "assessment": "INCONCLUSIVE",
            "confidence": 0.5,
            "supporting_evidence": ["Descriptions overlap."],
            "conflicting_evidence": [],
            "recommended_action": "HUMAN_REVIEW",
            "deterministic_result_authoritative": True,
        }]
    )
    _configure(provider)
    candidate = _persist_candidate(db)
    protected = {
        name: getattr(candidate, name)
        for name in (
            "similarity_score", "confidence_level", "business_status",
            "rule_decision", "rejection_reason", "review_status"
        )
    }

    response = client.post(
        f"/api/llm/candidates/{candidate.id}/advisory",
        json={"similarity_score": 100, "description_a": "client injection"},
    )
    assert response.status_code == 200
    prompt_payload = json.loads(provider.calls[0][1])
    assert prompt_payload["deterministic_score"] == 82.5
    assert "client injection" not in provider.calls[0][1]
    db.refresh(candidate)
    assert {name: getattr(candidate, name) for name in protected} == protected


def test_candidate_malformed_output_maps_safely_and_preserves_candidate(client, db):
    provider = FakeProvider([LLMProviderMalformedJSONError("malformed")])
    _configure(provider)
    candidate = _persist_candidate(db)
    before = (candidate.similarity_score, candidate.business_status, candidate.review_status)
    response = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert response.status_code == 502
    assert response.json()["detail"]["category"] == "invalid_provider_output"
    db.refresh(candidate)
    assert (candidate.similarity_score, candidate.business_status, candidate.review_status) == before


def test_candidate_timeout_maps_safely_and_preserves_candidate(client, db):
    provider = FakeProvider([LLMProviderTimeoutError("private timeout detail")])
    _configure(provider)
    candidate = _persist_candidate(db)
    protected = {
        name: getattr(candidate, name)
        for name in (
            "similarity_score", "confidence_level", "business_status",
            "rule_decision", "rejection_reason", "review_status"
        )
    }

    response = client.post(f"/api/llm/candidates/{candidate.id}/advisory")
    assert response.status_code == 504
    assert response.json()["detail"]["category"] == "provider_timeout"
    assert "private timeout detail" not in response.text
    db.refresh(candidate)
    assert {name: getattr(candidate, name) for name in protected} == protected


def test_existing_api_contracts_remain_available(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/config/fields").status_code == 200
