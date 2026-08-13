import asyncio
import json
from itertools import combinations

import pytest

from app.llm.exceptions import (
    LLMProviderError,
    LLMProviderHTTPError,
    LLMProviderNetworkError,
    LLMProviderTimeoutError,
)
from app.llm.group_contracts import (
    GROUP_ADVISORY_REQUEST_VERSION,
    GROUP_ADVISORY_RESULT_VERSION,
    GroupAdvisoryConfidenceBand,
    GroupAdvisoryEdge,
    GroupAdvisoryMember,
    GroupAdvisoryRequest,
    GroupIdentityEvidenceSummary,
    GroupUomMappingSummary,
    group_advisory_request_fingerprint,
)
from app.llm.group_execution import (
    GROUP_PROMPT_CONTRACT_VERSION,
    DisabledGroupAdvisoryProvider,
    GroupAdvisoryExecutionService,
    GroupAdvisoryProviderRegistry,
    GroupCacheStatus,
    GroupCircuitBreaker,
    GroupExecutionMetrics,
    GroupExecutionPolicy,
    GroupExecutionStatus,
    InMemoryGroupAdvisoryCache,
    RawGroupProviderResponse,
    build_group_advisory_messages,
    group_advisory_structured_output_schema,
    group_execution_key,
)
from app.services.group_llm_eligibility import (
    GroupLlmEligibilityReason,
    GroupLlmEligibilityResult,
)


def refs(size):
    return tuple(f"{index:064x}" for index in range(1, size + 1))


def request_for(size=5, *, cannot_pair=None, marker=""):
    member_refs = refs(size)
    edges = []
    for left, right in combinations(member_refs, 2):
        edge_class = (
            "CANNOT_LINK" if frozenset((left, right)) == cannot_pair
            else "REVIEW_SUPPORT"
        )
        edges.append(GroupAdvisoryEdge(
            left_record_ref_key=left, right_record_ref_key=right,
            edge_class=edge_class,
            reason_codes=("DETERMINISTIC_REVIEW_CANDIDATE",),
            evidence_source="PERSISTED_CANDIDATE",
            deterministic_status="POSSIBLE_DUPLICATE_REVIEW",
        ))
    return GroupAdvisoryRequest(
        contract_version=GROUP_ADVISORY_REQUEST_VERSION,
        scan_id=21, projection_run_id=2, group_snapshot_id=3,
        group_hypothesis_key="a" * 64,
        projection_algorithm_version="constrained-group-projection-v1",
        group_status="POSSIBLE_DUPLICATE_GROUP_REVIEW", group_size=size,
        members=tuple(GroupAdvisoryMember(
            record_ref_key=ref, part_no=f"P-{index}",
            normalized_part_no=f"p {index}",
            description=f"Component {index}{marker}",
            normalized_description=f"component {index}{marker}",
            site_or_contract="S1", uom="PCS", product_category="CAT",
            hsn_sac="1000",
        ) for index, ref in enumerate(member_refs)),
        internal_edges=tuple(edges),
        group_identity_evidence_summary=GroupIdentityEvidenceSummary(
            strong_support_count=0, review_support_count=len(edges),
            non_groupable_count=0, internal_pair_count=len(edges),
            evidence_completeness=1,
            reason_codes=("DETERMINISTIC_REVIEW_CANDIDATE",),
        ),
        group_uom_mapping_summary=GroupUomMappingSummary(
            distinct_uoms=("PCS",), same_uom_pair_count=len(edges),
            convertible_uom_pair_count=0, different_basis_pair_count=0,
            missing_or_wildcard_pair_count=0,
            malformed_or_unknown_pair_count=0,
            possible_mapping_error_count=0, identity_authority=False,
        ),
        unresolved_identity_questions=("DETERMINISTIC_REVIEW_CANDIDATE",),
    )


ELIGIBLE = GroupLlmEligibilityResult(
    True, GroupLlmEligibilityReason.ELIGIBLE_IDENTITY_AMBIGUITY,
    ("DETERMINISTIC_REVIEW_CANDIDATE",),
)
INELIGIBLE = GroupLlmEligibilityResult(
    False, GroupLlmEligibilityReason.INELIGIBLE_SYSTEM_STATUS,
)
HUMAN_REVIEWED = GroupLlmEligibilityResult(
    False, GroupLlmEligibilityReason.INELIGIBLE_HUMAN_REVIEW_EXISTS,
)


class ScriptedContractService:
    def __init__(self, request, results=None):
        self.request = request
        self.results = list(results or [])
        self.calls = 0

    def build_request(self, *_args):
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return ELIGIBLE, self.request


class ScriptedProvider:
    enabled = True

    def __init__(self, script, provider_id="future:groq", model="group-test-v1"):
        self.script = list(script)
        self.provider_id = provider_id
        self.provider_model = model
        self.calls = 0
        self.requests = []

    async def execute(self, request):
        self.calls += 1
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(request)
        return RawGroupProviderResponse(
            provider_id=self.provider_id, provider_model=self.provider_model,
            content=item,
        )


def output_for(request, outcome="SUPPORTS_SINGLE_IDENTITY", partitions=None, **updates):
    members = tuple(member.record_ref_key for member in request.members)
    if partitions is None:
        partitions = (members,) if outcome == "SUPPORTS_SINGLE_IDENTITY" else ()
    value = {
        "contract_version": GROUP_ADVISORY_RESULT_VERSION,
        "request_fingerprint": group_advisory_request_fingerprint(request),
        "group_snapshot_id": request.group_snapshot_id,
        "group_hypothesis_key": request.group_hypothesis_key,
        "outcome": outcome,
        "proposed_partitions": partitions,
        "confidence_band": GroupAdvisoryConfidenceBand.MEDIUM.value,
        "reason_codes": ["SEMANTIC_IDENTITY_REVIEW"],
        "rationale": "Advisory only.",
        "mapping_observations": [],
    }
    value.update(updates)
    return value


async def no_sleep(_delay):
    return None


def run(service):
    return asyncio.run(service.execute(21, 2, 3))


def service(request, provider, **kwargs):
    return GroupAdvisoryExecutionService(
        contract_service=kwargs.pop("contract_service", ScriptedContractService(request)),
        provider=provider,
        policy=kwargs.pop("policy", GroupExecutionPolicy(
            max_retries=1, timeout_seconds=1, base_retry_delay_seconds=0,
        )),
        sleeper=no_sleep, **kwargs,
    )


def test_ineligible_and_provider_none_never_invoke_provider():
    request = request_for(2)
    fake = ScriptedProvider([output_for(request)])
    ineligible_gateway = ScriptedContractService(
        request, results=[(INELIGIBLE, None)]
    )
    blocked = run(service(request, fake, contract_service=ineligible_gateway))
    disabled = run(service(request, DisabledGroupAdvisoryProvider()))
    assert blocked.execution_status == GroupExecutionStatus.NOT_ELIGIBLE
    assert disabled.execution_status == GroupExecutionStatus.PROVIDER_DISABLED
    assert fake.calls == 0 and disabled.attempt_count == 0


@pytest.mark.parametrize("size", [2, 4, 7, 14])
def test_each_whole_group_size_is_exactly_one_provider_invocation(size):
    request = request_for(size)
    provider = ScriptedProvider([output_for(request)])
    result = run(service(request, provider))
    assert result.execution_status == GroupExecutionStatus.SUCCEEDED
    assert result.attempt_count == provider.calls == 1
    assert len(provider.requests[0].members) == size
    assert len(provider.requests[0].internal_edges) == size * (size - 1) // 2


def test_valid_partition_shapes_are_one_call_each():
    request = request_for(5); members = refs(5)
    for partitions in ((members[:4], members[4:]),
                       (members[:2], members[2:4], members[4:])):
        provider = ScriptedProvider([
            output_for(request, "PROPOSES_PARTITION", partitions)
        ])
        result = run(service(request, provider))
        assert result.execution_status == GroupExecutionStatus.SUCCEEDED
        assert provider.calls == 1


def test_human_review_race_is_rechecked_immediately_before_invocation():
    request = request_for(4)
    gateway = ScriptedContractService(request, results=[
        (ELIGIBLE, request), (HUMAN_REVIEWED, None),
    ])
    provider = ScriptedProvider([output_for(request)])
    result = run(service(
        request, provider, contract_service=gateway,
        pre_invocation_hook=lambda: None,
    ))
    assert result.execution_status == GroupExecutionStatus.NOT_ELIGIBLE
    assert result.safe_error_code == "INELIGIBLE_HUMAN_REVIEW_EXISTS"
    assert provider.calls == 0 and gateway.calls == 2


def test_immutable_request_fingerprint_change_prevents_invocation():
    initial, changed = request_for(4), request_for(4, marker=" changed")
    gateway = ScriptedContractService(initial, results=[
        (ELIGIBLE, initial), (ELIGIBLE, changed),
    ])
    provider = ScriptedProvider([output_for(initial)])
    result = run(service(initial, provider, contract_service=gateway))
    assert result.execution_status == GroupExecutionStatus.FAILED_TERMINAL
    assert result.safe_error_code == "IMMUTABLE_REQUEST_CHANGED"
    assert provider.calls == 0


def test_retryable_failure_then_success_counts_two_attempts():
    request = request_for(2)
    provider = ScriptedProvider([
        LLMProviderNetworkError("network"), output_for(request),
    ])
    metrics = GroupExecutionMetrics()
    result = run(service(request, provider, metrics=metrics))
    assert result.execution_status == GroupExecutionStatus.SUCCEEDED
    assert result.attempt_count == provider.calls == 2
    assert metrics.retry_attempts == 1


def test_terminal_failure_has_no_retry():
    request = request_for(2)
    provider = ScriptedProvider([LLMProviderError("terminal")])
    result = run(service(request, provider))
    assert result.execution_status == GroupExecutionStatus.FAILED_TERMINAL
    assert result.attempt_count == provider.calls == 1


@pytest.mark.parametrize("exception,status,code", [
    (LLMProviderTimeoutError("timeout"), GroupExecutionStatus.TIMED_OUT, "PROVIDER_TIMEOUT"),
    (LLMProviderHTTPError("limited", status_code=429), GroupExecutionStatus.RATE_LIMITED, "RATE_LIMITED"),
])
def test_exhausted_timeout_and_rate_limit_are_distinct(exception, status, code):
    request = request_for(2)
    provider = ScriptedProvider([exception, exception])
    result = run(service(request, provider))
    assert result.execution_status == status
    assert result.safe_error_code == code
    assert result.attempt_count == 2


def test_runtime_timeout_seam_is_bounded():
    request = request_for(2)

    class HangingProvider(ScriptedProvider):
        async def execute(self, request):
            self.calls += 1
            await asyncio.Event().wait()

    provider = HangingProvider([])
    result = run(service(
        request, provider,
        policy=GroupExecutionPolicy(max_retries=0, timeout_seconds=.001,
                                    base_retry_delay_seconds=0),
    ))
    assert result.execution_status == GroupExecutionStatus.TIMED_OUT
    assert provider.calls == 1


def test_circuit_open_makes_zero_calls_and_is_isolated_by_provider():
    request = request_for(2); breaker = GroupCircuitBreaker()
    breaker.force_open("future:groq")
    groq = ScriptedProvider([output_for(request)], provider_id="future:groq")
    ollama = ScriptedProvider([output_for(request)], provider_id="future:ollama")
    blocked = run(service(request, groq, circuit_breaker=breaker))
    allowed = run(service(request, ollama, circuit_breaker=breaker))
    assert blocked.execution_status == GroupExecutionStatus.CIRCUIT_OPEN
    assert groq.calls == 0
    assert allowed.execution_status == GroupExecutionStatus.SUCCEEDED
    assert ollama.calls == 1


def test_malformed_and_semantically_invalid_output_normalize_safely():
    request = request_for(5); members = refs(5)
    for content in (
        {"not": "the result contract"},
        output_for(request, "PROPOSES_PARTITION", (members[:-1],)),
    ):
        provider = ScriptedProvider([content])
        result = run(service(request, provider))
        assert result.execution_status == GroupExecutionStatus.INVALID_PROVIDER_OUTPUT
        assert result.validated_advisory.outcome.value == "INCONCLUSIVE"
        assert result.validated_advisory.requires_human_review is True
        assert result.validated_advisory.deterministic_result_authoritative is True


def test_provider_result_fingerprint_mismatch_is_centrally_rejected():
    request = request_for(4)
    content = output_for(request, request_fingerprint="f" * 64)
    result = run(service(request, ScriptedProvider([content])))
    assert result.execution_status == GroupExecutionStatus.INVALID_PROVIDER_OUTPUT
    assert "REQUEST_FINGERPRINT_MISMATCH" in result.validated_advisory.validation_reasons


def test_cannot_link_violation_is_invalid_even_with_high_confidence():
    members = refs(5); protected = frozenset((members[0], members[1]))
    request = request_for(5, cannot_pair=protected)
    content = output_for(
        request, "PROPOSES_PARTITION", (members[:4], members[4:]),
        confidence_band="HIGH",
    )
    result = run(service(request, ScriptedProvider([content])))
    assert result.execution_status == GroupExecutionStatus.INVALID_PROVIDER_OUTPUT
    assert "PROTECTED_CANNOT_LINK_VIOLATION" in result.validated_advisory.validation_reasons


def test_cache_uses_request_provider_model_and_prompt_identity():
    request = request_for(4); cache = InMemoryGroupAdvisoryCache()
    provider = ScriptedProvider([output_for(request)])
    first = run(service(request, provider, cache=cache))
    second = run(service(request, provider, cache=cache))
    assert first.cache_status == GroupCacheStatus.MISS
    assert second.cache_status == GroupCacheStatus.HIT
    assert provider.calls == 1 and second.attempt_count == 0
    fingerprint = group_advisory_request_fingerprint(request)
    assert group_execution_key(fingerprint, "future:groq", "a") != group_execution_key(
        fingerprint, "future:groq", "b"
    )
    assert group_execution_key(fingerprint, "future:groq", "a") != group_execution_key(
        fingerprint, "future:ollama", "a"
    )
    assert GROUP_PROMPT_CONTRACT_VERSION == "group-advisory-prompt-v1"


def test_invalid_provider_output_is_never_cached_as_valid():
    request = request_for(2); cache = InMemoryGroupAdvisoryCache()
    provider = ScriptedProvider([{"bad": True}, {"bad": True}])
    assert run(service(request, provider, cache=cache)).cache_status == GroupCacheStatus.MISS
    assert run(service(request, provider, cache=cache)).cache_status == GroupCacheStatus.MISS
    assert provider.calls == 2


def test_messages_and_schema_are_minimal_provider_independent_and_action_free():
    request = request_for(7, marker=" FORBIDDEN_SENTINEL_ONLY_IN_ALLOWED_DESCRIPTION")
    messages = build_group_advisory_messages(request)
    payload = json.loads(messages.user_prompt.split("request=", 1)[1])
    assert set(payload) == set(GroupAdvisoryRequest.model_fields)
    serialized = json.dumps({
        "system": messages.system_prompt,
        "request": payload,
        "schema": messages.structured_output_schema,
    }).lower()
    for forbidden in (
        "api_key", "token", "filesystem", "environment variable",
        "review_comment", "review_history", "effective_status",
        "automatic_merge", "delete_records", "writeback", "override_authority",
    ):
        assert forbidden not in serialized
    schema = group_advisory_structured_output_schema()
    assert "requires_human_review" not in schema["properties"]
    assert "deterministic_result_authoritative" not in schema["properties"]
    assert schema["additionalProperties"] is False
    assert "one bounded candidate identity group" in messages.system_prompt
    assert "UOM and mapping" in messages.system_prompt


def test_registry_reserves_future_identities_without_pair_fallback():
    registry = GroupAdvisoryProviderRegistry()
    assert registry.resolve("none").enabled is False
    with pytest.raises(LLMProviderError):
        registry.resolve("future:groq")
    with pytest.raises(ValueError):
        registry.resolve("groq-pair-fallback")
