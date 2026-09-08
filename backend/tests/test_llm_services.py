import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.llm.audit import LLMAuditOutcome, LLMAuditStore
from app.llm.cache import LLMCache
from app.engine.domain_dictionary import normalize_part_no_with_dictionary
from app.engine.normalizer import normalize_description
from app.llm.contracts import DifficultValueRequest
from app.llm.exceptions import LLMProviderDisabledError, LLMProviderTimeoutError
from app.llm.provider import LLMProviderResult
from app.llm.service_contracts import (
    CandidateGateReason,
    ColumnSuggestionAPIRequest,
)
from app.llm.services import (
    CandidateAdvisoryService,
    ColumnSuggestionService,
    DifficultValueInterpretationService,
    LLMStructuredOutputError,
    candidate_eligibility,
)


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
            provider="groq", model="test-model", content=value, request_id="req-1"
        )


def _runtime(provider, *, cache=None, audit=None):
    return {
        "configuration": Settings(
            llm_demo_enabled=True,
            llm_provider="groq",
            groq_api_key="synthetic-test-key",
            groq_model="test-model",
        ),
        "cache": cache or LLMCache(enabled=True, max_entries=20, ttl_seconds=60),
        "audit": audit or LLMAuditStore(enabled=True, max_entries=50),
        "provider_factory": lambda configuration: provider,
    }


def _candidate(**overrides):
    values = {
        "id": 1,
        "part_no_a": "A-1",
        "description_a": "Motor 10 kW",
        "contract_a": "S1",
        "part_no_b": "A-2",
        "description_b": "10 kW motor",
        "contract_b": "S1",
        "similarity_score": 82.5,
        "confidence_level": "MEDIUM",
        "business_status": "POSSIBLE_DUPLICATE_REVIEW",
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "critical_mismatches": "[]",
        "review_status": "UNREVIEWED",
        "unrelated_financial_field": "must-not-be-sent",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_column_exact_and_alias_headers_bypass_provider_and_are_audited():
    provider = FakeProvider([])
    audit = LLMAuditStore(enabled=True, max_entries=10)
    service = ColumnSuggestionService(**_runtime(provider, audit=audit))

    for source in ("PART_NO", "Part Number"):
        result = asyncio.run(
            service.suggest(
                ColumnSuggestionAPIRequest(
                    source_column=source, sample_values=["A-1"]
                )
            )
        )
        assert result.deterministic_bypass is True
        assert result.bypass_reason == "DETERMINISTIC_HEADER_RECOGNIZED"
        assert result.metadata.llm_used is False
    assert provider.calls == []
    assert all(event.outcome == LLMAuditOutcome.INELIGIBLE for event in audit.events())


def test_column_unresolved_uses_server_allowlist_removes_blanks_and_caches():
    response = {
        "source_column": "Mystery Header",
        "suggested_canonical_field": "PART_NO",
        "confidence": 0.8,
        "reason": "Identifier-shaped values.",
        "requires_confirmation": True,
    }
    provider = FakeProvider([response])
    service = ColumnSuggestionService(**_runtime(provider))
    request = ColumnSuggestionAPIRequest(
        source_column="Mystery Header", sample_values=["", "A-1", "  "]
    )

    first = asyncio.run(service.suggest(request))
    second = asyncio.run(
        service.suggest(
            ColumnSuggestionAPIRequest(
                source_column="Mystery Header", sample_values=["A-1"]
            )
        )
    )

    payload = json.loads(provider.calls[0][1])
    assert payload["sample_values"] == ["A-1"]
    assert "PART_NO" in payload["allowed_canonical_fields"]
    assert not any(value.startswith("UNMAPPED_") for value in payload["allowed_canonical_fields"])
    assert first.suggestion.suggested_canonical_field == "PART_NO"
    assert second.metadata.cache_hit is True
    assert second.metadata.llm_used is False
    assert len(provider.calls) == 1


def test_column_api_contract_rejects_empty_and_all_blank_samples():
    with pytest.raises(ValidationError):
        ColumnSuggestionAPIRequest(source_column="Mystery", sample_values=[])
    with pytest.raises(ValidationError):
        ColumnSuggestionAPIRequest(
            source_column="Mystery", sample_values=["", "   "]
        )


@pytest.mark.parametrize(
    "response",
    [
        {
            "source_column": "Other",
            "suggested_canonical_field": "PART_NO",
            "confidence": 0.8,
            "reason": "Mismatch.",
            "requires_confirmation": True,
        },
        {
            "source_column": "Mystery",
            "suggested_canonical_field": "PRIVATE_FIELD",
            "confidence": 0.8,
            "reason": "Not allowlisted.",
            "requires_confirmation": True,
        },
        {
            "source_column": "Mystery",
            "suggested_canonical_field": "PART_NO",
            "confidence": 0.8,
            "reason": "Unsafe confirmation.",
            "requires_confirmation": False,
        },
    ],
)
def test_invalid_column_outputs_are_not_cached(response):
    provider = FakeProvider([response])
    cache = LLMCache(enabled=True, max_entries=5, ttl_seconds=60)
    service = ColumnSuggestionService(**_runtime(provider, cache=cache))
    with pytest.raises(LLMStructuredOutputError):
        asyncio.run(
            service.suggest(
                ColumnSuggestionAPIRequest(
                    source_column="Mystery", sample_values=["A-1"]
                )
            )
        )
    assert cache.stats()["count"] == 0


def test_column_abstention_is_valid():
    provider = FakeProvider(
        [{
            "source_column": "Mystery",
            "suggested_canonical_field": None,
            "confidence": 0,
            "reason": "Insufficient evidence.",
            "requires_confirmation": True,
        }]
    )
    result = asyncio.run(
        ColumnSuggestionService(**_runtime(provider)).suggest(
            ColumnSuggestionAPIRequest(
                source_column="Mystery", sample_values=["unknown"]
            )
        )
    )
    assert result.suggestion.suggested_canonical_field is None


def test_provider_failure_is_audited_and_not_cached():
    provider = FakeProvider([LLMProviderTimeoutError("timed out")])
    cache = LLMCache(enabled=True, max_entries=5, ttl_seconds=60)
    audit = LLMAuditStore(enabled=True, max_entries=5)
    service = ColumnSuggestionService(**_runtime(provider, cache=cache, audit=audit))
    with pytest.raises(LLMProviderTimeoutError):
        asyncio.run(
            service.suggest(
                ColumnSuggestionAPIRequest(
                    source_column="Mystery", sample_values=["A"]
                )
            )
        )
    assert cache.stats()["count"] == 0
    assert audit.events()[-1].outcome == LLMAuditOutcome.PROVIDER_FAILURE


def test_disabled_request_is_audited_without_constructing_provider():
    audit = LLMAuditStore(enabled=True, max_entries=5)

    def forbidden_factory(configuration):
        raise AssertionError("disabled request must not construct a provider")

    service = ColumnSuggestionService(
        configuration=Settings(),
        cache=LLMCache(enabled=True, max_entries=5, ttl_seconds=60),
        audit=audit,
        provider_factory=forbidden_factory,
    )
    with pytest.raises(LLMProviderDisabledError):
        asyncio.run(
            service.suggest(
                ColumnSuggestionAPIRequest(
                    source_column="Mystery", sample_values=["A"]
                )
            )
        )
    assert audit.events()[-1].outcome == LLMAuditOutcome.DISABLED


def test_malformed_structured_output_is_audited_as_validation_failure():
    provider = FakeProvider([{"unexpected": "shape"}])
    audit = LLMAuditStore(enabled=True, max_entries=5)
    service = ColumnSuggestionService(**_runtime(provider, audit=audit))
    with pytest.raises(LLMStructuredOutputError):
        asyncio.run(
            service.suggest(
                ColumnSuggestionAPIRequest(
                    source_column="Mystery", sample_values=["A"]
                )
            )
        )
    event = audit.events()[-1]
    assert event.outcome == LLMAuditOutcome.VALIDATION_FAILURE
    assert event.validation_result == "invalid"


def test_difficult_value_builds_context_preserves_raw_value_and_caches():
    provider = FakeProvider(
        [{
            "raw_value": "MTR 10KW",
            "normalized_interpretation": "10 kW motor",
            "attributes": {"power": "10 kW"},
            "confidence": 0.7,
            "warnings": [],
            "requires_confirmation": True,
        }]
    )
    service = DifficultValueInterpretationService(**_runtime(provider))
    request = DifficultValueRequest(
        raw_value="MTR 10KW",
        field_context="DESCRIPTION",
        item_family_context=None,
    )
    first = asyncio.run(service.interpret(request))
    second = asyncio.run(service.interpret(request))

    prompt_payload = json.loads(provider.calls[0][1])
    assert prompt_payload["request"]["raw_value"] == "MTR 10KW"
    assert prompt_payload["deterministic_context"]["normalized_value"]
    assert "technical_tokens" in prompt_payload["deterministic_context"]
    assert first.interpretation.raw_value == request.raw_value
    assert second.metadata.cache_hit is True
    assert len(provider.calls) == 1


def test_difficult_value_context_selects_exact_deterministic_path(monkeypatch):
    calls = []

    def capture_context(part_number, description):
        calls.append((part_number, description))
        return []

    monkeypatch.setattr(
        "app.llm.services.extract_application_context", capture_context
    )
    service = DifficultValueInterpretationService(
        **_runtime(FakeProvider([]))
    )
    raw = "  ABC-100  "
    part_context = service.build_context(
        DifficultValueRequest(raw_value=raw, field_context="PART_NO")
    )
    description_context = service.build_context(
        DifficultValueRequest(raw_value=raw, field_context="DESCRIPTION")
    )

    assert part_context.normalized_value == normalize_part_no_with_dictionary(raw)
    assert description_context.normalized_value == normalize_description(raw)
    assert calls == [(raw, ""), ("", raw)]


def test_difficult_value_cache_key_includes_selected_context():
    responses = [
        {
            "raw_value": "ABC-100",
            "normalized_interpretation": None,
            "attributes": {},
            "confidence": 0,
            "warnings": [],
            "requires_confirmation": True,
        },
        {
            "raw_value": "ABC-100",
            "normalized_interpretation": None,
            "attributes": {},
            "confidence": 0,
            "warnings": [],
            "requires_confirmation": True,
        },
    ]
    provider = FakeProvider(responses)
    service = DifficultValueInterpretationService(**_runtime(provider))
    asyncio.run(
        service.interpret(
            DifficultValueRequest(raw_value="ABC-100", field_context="PART_NO")
        )
    )
    asyncio.run(
        service.interpret(
            DifficultValueRequest(
                raw_value="ABC-100", field_context="DESCRIPTION"
            )
        )
    )
    assert len(provider.calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        {
            "raw_value": "different",
            "normalized_interpretation": None,
            "attributes": {},
            "confidence": 0,
            "warnings": [],
            "requires_confirmation": True,
        },
        {
            "raw_value": "MTR",
            "normalized_interpretation": None,
            "attributes": {"nested": {"bad": "value"}},
            "confidence": 0,
            "warnings": [],
            "requires_confirmation": True,
        },
    ],
)
def test_invalid_difficult_value_output_is_rejected_without_cache(response):
    provider = FakeProvider([response])
    cache = LLMCache(enabled=True, max_entries=5, ttl_seconds=60)
    service = DifficultValueInterpretationService(
        **_runtime(provider, cache=cache)
    )
    with pytest.raises(LLMStructuredOutputError):
        asyncio.run(
            service.interpret(
                DifficultValueRequest(raw_value="MTR", field_context="DESCRIPTION")
            )
        )
    assert cache.stats()["count"] == 0


@pytest.mark.parametrize(
    ("candidate", "eligible", "reason"),
    [
        (_candidate(business_status="LIKELY_DUPLICATE", confidence_level="HIGH"), False, CandidateGateReason.INELIGIBLE_CLEAR_DUPLICATE),
        (_candidate(business_status="REJECTED_BY_BUSINESS_RULE", rule_decision="REJECT"), False, CandidateGateReason.INELIGIBLE_HARD_REJECTION),
        (_candidate(business_status="RELATED_BUT_NOT_DUPLICATE", rule_decision="DOWNGRADE", critical_mismatches='[{"group":"COLOR","label":"color","values_a":["red"],"values_b":["blue"]}]'), False, CandidateGateReason.INELIGIBLE_CRITICAL_MISMATCH),
        (_candidate(business_status="CROSS_SITE_STANDARDIZATION_CANDIDATE", rule_decision="CROSS_SITE"), False, CandidateGateReason.INELIGIBLE_CROSS_SITE),
        (_candidate(part_no_a="", description_a=""), False, CandidateGateReason.INELIGIBLE_INSUFFICIENT_IDENTITY),
        (_candidate(), True, CandidateGateReason.ELIGIBLE_REVIEW_STATUS),
        (_candidate(business_status="DATA_CONFLICT_REVIEW", rule_decision="DATA_CONFLICT"), True, CandidateGateReason.ELIGIBLE_DATA_CONFLICT),
        (_candidate(business_status="INSUFFICIENT_DATA", rule_decision="DOWNGRADE", rejection_reason="GENERIC_DESCRIPTION"), True, CandidateGateReason.ELIGIBLE_AMBIGUOUS_INSUFFICIENT_DATA),
        (_candidate(business_status="INSUFFICIENT_DATA", confidence_level="IGNORE"), False, CandidateGateReason.INELIGIBLE_STATUS),
    ],
)
def test_candidate_eligibility_uses_explicit_deterministic_conditions(candidate, eligible, reason):
    result = candidate_eligibility(candidate)
    assert result.eligible is eligible
    assert result.reason == reason


def test_candidate_eligibility_does_not_use_an_arbitrary_numeric_threshold():
    low_score = candidate_eligibility(_candidate(similarity_score=1.0))
    high_score = candidate_eligibility(_candidate(similarity_score=99.0))
    assert low_score == high_score
    assert low_score.eligible is True


def test_valid_empty_candidate_mismatch_evidence_remains_eligible():
    result = candidate_eligibility(_candidate(critical_mismatches="[]"))
    assert result.eligible is True
    assert result.reason == CandidateGateReason.ELIGIBLE_REVIEW_STATUS


def test_candidate_bypass_calls_no_provider_and_is_audited():
    provider = FakeProvider([])
    audit = LLMAuditStore(enabled=True, max_entries=5)
    service = CandidateAdvisoryService(**_runtime(provider, audit=audit))
    result = asyncio.run(
        service.advise(
            _candidate(business_status="LIKELY_DUPLICATE", confidence_level="HIGH")
        )
    )
    assert result.eligibility.eligible is False
    assert result.metadata.llm_used is False
    assert provider.calls == []
    assert audit.events()[-1].outcome == LLMAuditOutcome.INELIGIBLE


@pytest.mark.parametrize(
    "malformed",
    [
        "{not-json",
        '{"group":"COLOR"}',
        '[{"group":"COLOR"}]',
        json.dumps(
            [
                {
                    "group": "COLOR",
                    "label": "Color",
                    "values_a": ["red"],
                    "values_b": ["blue"],
                }
            ]
            * 11
        ),
    ],
)
def test_malformed_candidate_mismatch_evidence_bypasses_safely(malformed):
    provider = FakeProvider([])
    audit = LLMAuditStore(enabled=True, max_entries=5)
    candidate = _candidate(critical_mismatches=malformed)
    before = dict(candidate.__dict__)
    result = asyncio.run(
        CandidateAdvisoryService(**_runtime(provider, audit=audit)).advise(
            candidate
        )
    )

    assert result.eligibility.reason == (
        CandidateGateReason.INELIGIBLE_INVALID_DETERMINISTIC_EVIDENCE
    )
    assert result.metadata.llm_used is False
    assert provider.calls == []
    assert candidate.__dict__ == before
    event = audit.events()[-1]
    assert event.outcome == LLMAuditOutcome.INELIGIBLE
    assert event.failure_category == (
        "INELIGIBLE_INVALID_DETERMINISTIC_EVIDENCE"
    )
    serialized = json.dumps(
        {
            "result": result.model_dump(mode="json"),
            "audit": event.model_dump(mode="json"),
        }
    )
    assert malformed not in serialized


def test_candidate_advisory_is_server_built_cached_and_non_mutating():
    provider = FakeProvider(
        [{
            "assessment": "INCONCLUSIVE",
            "confidence": 0.6,
            "supporting_evidence": ["Descriptions overlap."],
            "conflicting_evidence": [],
            "recommended_action": "HUMAN_REVIEW",
            "deterministic_result_authoritative": True,
        }]
    )
    candidate = _candidate()
    before = dict(candidate.__dict__)
    service = CandidateAdvisoryService(**_runtime(provider))
    first = asyncio.run(service.advise(candidate))
    second = asyncio.run(service.advise(candidate))

    payload = json.loads(provider.calls[0][1])
    assert set(payload["left"]) == {
        "part_number", "description", "master_description", "uom", "site_or_contract"
    }
    assert "unrelated_financial_field" not in provider.calls[0][1]
    assert first.advisory.deterministic_result_authoritative is True
    assert second.metadata.cache_hit is True
    assert len(provider.calls) == 1
    assert candidate.__dict__ == before


def test_candidate_data_conflict_is_preserved_in_provider_request():
    mismatch = [{
        "group": "HSN_SAC_CODE",
        "label": "HSN/SAC Code",
        "values_a": ["1000"],
        "values_b": ["2000"],
    }]
    provider = FakeProvider(
        [{
            "assessment": "SUPPORTS_NON_DUPLICATE",
            "confidence": 0.8,
            "supporting_evidence": [],
            "conflicting_evidence": ["Classification conflict."],
            "recommended_action": "KEEP_DETERMINISTIC_RESULT",
            "deterministic_result_authoritative": True,
        }]
    )
    candidate = _candidate(
        business_status="DATA_CONFLICT_REVIEW",
        rule_decision="DATA_CONFLICT",
        rejection_reason="HSN_SAC_CODE_MISMATCH",
        critical_mismatches=json.dumps(mismatch),
    )
    asyncio.run(CandidateAdvisoryService(**_runtime(provider)).advise(candidate))
    payload = json.loads(provider.calls[0][1])
    assert payload["critical_mismatches"] == mismatch
    assert payload["deterministic_rule_decision"] == "DATA_CONFLICT"
