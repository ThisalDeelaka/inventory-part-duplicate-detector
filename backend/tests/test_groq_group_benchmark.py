import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm.exceptions import (
    LLMProviderConfigurationError, LLMProviderError, LLMProviderHTTPError,
    LLMProviderMalformedJSONError, LLMProviderNetworkError,
    LLMProviderResponseStructureError, LLMProviderTimeoutError,
)
from app.llm.groq_group_provider import (
    GroqGroupAdvisoryProvider, create_group_advisory_provider,
)
from app.llm.groq_provider import GroqLLMProvider
from app.llm.group_benchmark import (
    BenchmarkExpectedResolution, BenchmarkFailureCategory,
    BenchmarkSourceKind, BenchmarkUsefulness,
    GroupAdvisoryBenchmarkRunner, canonical_partition,
    classify_benchmark_failure, curated_group_benchmark_cases,
    live_group_benchmark_enabled,
)
from app.llm.group_benchmark_cli import build_parser, select_benchmark_cases
from app.llm.group_contracts import GROUP_ADVISORY_RESULT_VERSION
from app.llm.group_execution import (
    DisabledGroupAdvisoryProvider, RawGroupProviderResponse,
    build_group_advisory_messages,
)
from app.llm.provider import LLMUsageMetadata


def provider_with_handler(handler, *, size=2, key="synthetic-secret"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            transport = GroqLLMProvider(
                api_key=SecretStr(key), model="benchmark-model",
                timeout_seconds=3, client=client,
            )
            provider = GroqGroupAdvisoryProvider(transport)
            request = next(
                case.request for case in curated_group_benchmark_cases()
                if case.group_size == size
            )
            return provider, request, await provider.execute(request)
    return asyncio.run(run())


def valid_content(request, outcome="SUPPORTS_SINGLE_IDENTITY", partitions=None):
    members = tuple(member.record_ref_key for member in request.members)
    if partitions is None:
        partitions = (members,) if outcome == "SUPPORTS_SINGLE_IDENTITY" else ()
    return {
        "contract_version": GROUP_ADVISORY_RESULT_VERSION,
        "request_fingerprint": __import__(
            "app.llm.group_contracts", fromlist=["group_advisory_request_fingerprint"]
        ).group_advisory_request_fingerprint(request),
        "group_snapshot_id": request.group_snapshot_id,
        "group_hypothesis_key": request.group_hypothesis_key,
        "outcome": outcome, "proposed_partitions": partitions,
        "confidence_band": "MEDIUM", "reason_codes": ["CURATED_TEST"],
        "rationale": "Synthetic benchmark response.",
        "mapping_observations": [],
        "requires_human_review": True,
        "deterministic_result_authoritative": True,
    }


@pytest.mark.parametrize("size", [2, 7])
def test_one_whole_group_maps_to_one_groq_transport_call(size):
    captured = []

    def handler(http_request):
        payload = json.loads(http_request.content)
        captured.append((http_request, payload))
        user = payload["messages"][1]["content"]
        request_payload = json.loads(user.split("request=", 1)[1])
        request = next(
            case.request for case in curated_group_benchmark_cases()
            if case.request.group_snapshot_id == request_payload["group_snapshot_id"]
        )
        return httpx.Response(200, json={
            "id": "group-request-1",
            "choices": [{"message": {"content": json.dumps(valid_content(request))}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    provider, request, result = provider_with_handler(handler, size=size)
    assert isinstance(provider, GroqGroupAdvisoryProvider)
    assert provider.provider_id == "groq" and provider.enabled is True
    assert len(captured) == 1
    envelope = captured[0][1]
    generic = build_group_advisory_messages(request)
    assert envelope["messages"] == [
        {"role": "system", "content": generic.system_prompt},
        {"role": "user", "content": generic.user_prompt},
    ]
    assert envelope["response_format"] == {"type": "json_object"}
    assert envelope["temperature"] == 0 and envelope["stream"] is False
    assert result.provider_id == "groq"
    assert result.provider_model == "benchmark-model"
    assert result.request_id == "group-request-1"
    assert result.usage.total_tokens == 15


def test_group_factory_is_explicit_disabled_by_default_and_secret_safe():
    configuration = Settings(
        llm_demo_enabled=True, llm_provider="groq", groq_api_key="synthetic-secret"
    )
    assert isinstance(
        create_group_advisory_provider(configuration), DisabledGroupAdvisoryProvider
    )
    with pytest.raises(LLMProviderConfigurationError) as caught:
        create_group_advisory_provider(Settings(
            group_llm_provider="groq", groq_api_key=""
        ))
    assert "key" not in str(caught.value).lower()
    enabled = create_group_advisory_provider(Settings(
        group_llm_provider="groq", groq_api_key="synthetic-secret",
        group_llm_model="group-model",
    ))
    assert isinstance(enabled, GroqGroupAdvisoryProvider)
    assert enabled.provider_model == "group-model"
    assert "synthetic-secret" not in repr(enabled._transport._api_key)


def test_groq_group_malformed_json_and_safe_http_error_mapping():
    with pytest.raises(LLMProviderMalformedJSONError):
        provider_with_handler(lambda _request: httpx.Response(200, json={
            "choices": [{"message": {"content": "{bad"}}]
        }))
    for status in (429, 503, 400):
        with pytest.raises(LLMProviderHTTPError) as caught:
            provider_with_handler(lambda _request, status=status: httpx.Response(
                status, text="private response", headers={"retry-after": "2"}
            ))
        assert caught.value.status_code == status
        assert "private" not in str(caught.value)


def test_groq_group_timeout_maps_safely():
    def handler(request):
        raise httpx.ReadTimeout("private timeout", request=request)
    with pytest.raises(LLMProviderTimeoutError):
        provider_with_handler(handler)


def test_curated_corpus_is_fixed_bounded_and_well_distributed():
    cases = curated_group_benchmark_cases()
    assert len(cases) == 30
    assert len({case.case_id for case in cases}) == 30
    assert len({case.request_fingerprint for case in cases}) == 30
    assert {2, 3, 4, 5, 7}.issubset({case.group_size for case in cases})
    assert sum(c.source_kind == BenchmarkSourceKind.CURATED_SYNTHETIC for c in cases) == 24
    assert sum(c.source_kind == BenchmarkSourceKind.VALIDATOR_SAFETY_CHALLENGE for c in cases) == 6
    assert sum(c.expected_resolution == BenchmarkExpectedResolution.SINGLE_IDENTITY for c in cases) == 12
    assert sum(c.expected_resolution == BenchmarkExpectedResolution.PARTITION for c in cases) == 14
    assert sum(c.expected_resolution == BenchmarkExpectedResolution.INCONCLUSIVE_ACCEPTABLE for c in cases) == 4
    partitions = [canonical_partition(case.expected_partitions) for case in cases]
    assert any(sorted(map(len, value)) == [1, 4] for value in partitions)
    assert any(sorted(map(len, value)) == [1, 2, 2] for value in partitions)


def test_partition_comparison_is_order_independent():
    assert canonical_partition((("A", "B", "C", "D"), ("E",))) == canonical_partition(
        (("E",), ("D", "C", "B", "A"))
    )


class BenchmarkProvider:
    provider_id = "groq"
    provider_model = "scripted-benchmark-model"
    enabled = True

    def __init__(self, behavior="expected"):
        self.behavior = behavior
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        case = next(c for c in curated_group_benchmark_cases()
                    if c.request_fingerprint == __import__(
                        "app.llm.group_contracts", fromlist=["group_advisory_request_fingerprint"]
                    ).group_advisory_request_fingerprint(request))
        if self.behavior == "invalid":
            content = {"bad": True}
        elif self.behavior == "inconclusive":
            content = valid_content(request, "INCONCLUSIVE", ())
        elif self.behavior == "unsafe" and case.protected_cannot_links:
            members = tuple(m.record_ref_key for m in request.members)
            content = valid_content(request, "SUPPORTS_SINGLE_IDENTITY", (members,))
        elif case.expected_resolution == BenchmarkExpectedResolution.SINGLE_IDENTITY:
            content = valid_content(request)
        elif case.expected_resolution == BenchmarkExpectedResolution.PARTITION:
            content = valid_content(request, "PROPOSES_PARTITION", case.expected_partitions)
        else:
            content = valid_content(request, "INCONCLUSIVE", ())
        return RawGroupProviderResponse(
            provider_id="groq", provider_model=self.provider_model,
            content=content, usage=LLMUsageMetadata(
                prompt_tokens=10, completion_tokens=5, total_tokens=15
            ),
        )


def test_benchmark_metrics_usefulness_and_machine_report_are_comparison_ready():
    cases = curated_group_benchmark_cases()[:20]
    provider = BenchmarkProvider()
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        provider, max_calls=20
    ).run(cases))
    assert provider.calls == report.provider_calls == 20
    assert report.successful_transport_responses == 20
    assert report.structurally_valid_responses == 20
    assert report.semantically_valid_responses == 20
    assert report.single_identity_matches == 12
    assert report.exact_partition_matches == 8
    assert report.usefulness_counts["USEFUL_CORRECT"] == 20
    assert report.total_tokens == 300 and report.estimated_cost is None
    encoded = json.dumps(report.model_dump(), sort_keys=True).lower()
    for forbidden in ("api_key", "authorization", "secret", "raw_description"):
        assert forbidden not in encoded


def test_abstention_wrong_invalid_and_cannot_link_are_distinct():
    cases = curated_group_benchmark_cases()
    partition_case = next(c for c in cases if c.expected_resolution == BenchmarkExpectedResolution.PARTITION and not c.protected_cannot_links)
    inconclusive_report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        BenchmarkProvider("inconclusive"), max_calls=1
    ).run((partition_case,)))
    assert inconclusive_report.usefulness_counts["SAFE_ABSTENTION"] == 1
    wrong_provider = BenchmarkProvider()
    original_execute = wrong_provider.execute
    async def wrong_execute(request):
        raw = await original_execute(request)
        members = tuple(member.record_ref_key for member in request.members)
        return raw.model_copy(update={
            "content": valid_content(request, "PROPOSES_PARTITION", (
                (members[0],), tuple(members[1:]),
            ))
        })
    wrong_provider.execute = wrong_execute
    wrong = asyncio.run(GroupAdvisoryBenchmarkRunner(
        wrong_provider, max_calls=1
    ).run((partition_case,)))
    assert wrong.usefulness_counts["INCORRECT"] == 1
    assert wrong.wrong_partition_results == 1
    invalid_report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        BenchmarkProvider("invalid"), max_calls=1
    ).run((partition_case,)))
    assert invalid_report.usefulness_counts["INVALID_REJECTED"] == 1
    assert invalid_report.structurally_valid_responses == 0
    challenge = next(c for c in cases if c.protected_cannot_links)
    unsafe = asyncio.run(GroupAdvisoryBenchmarkRunner(
        BenchmarkProvider("unsafe"), max_calls=1
    ).run((challenge,)))
    assert unsafe.unsafe_cannot_link_proposals_rejected == 1
    assert unsafe.usefulness_counts["INVALID_REJECTED"] == 1


def test_benchmark_call_cap_and_live_guard_require_explicit_group_enablement():
    provider = BenchmarkProvider()
    capped = asyncio.run(GroupAdvisoryBenchmarkRunner(provider, max_calls=5).run(
        curated_group_benchmark_cases()[:6]
    ))
    assert capped.provider_calls == capped.total_cases_attempted == 5
    pair_only = Settings(
        llm_provider="groq", llm_demo_enabled=True,
        groq_api_key="synthetic-secret", group_llm_provider="none",
    )
    assert not live_group_benchmark_enabled(
        pair_only, explicit_live=True, corpus_selected=True
    )
    group = Settings(group_llm_provider="groq")
    assert not live_group_benchmark_enabled(
        group, explicit_live=False, corpus_selected=True
    )
    assert not live_group_benchmark_enabled(
        group, explicit_live=True, corpus_selected=False
    )
    assert live_group_benchmark_enabled(
        group, explicit_live=True, corpus_selected=True
    )


def test_benchmark_bounded_retry_metrics_then_success():
    case = curated_group_benchmark_cases()[0]
    provider = BenchmarkProvider()
    original = provider.execute
    attempts = 0
    async def flaky(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise LLMProviderNetworkError("synthetic network failure")
        return await original(request)
    provider.execute = flaky
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        provider, max_calls=2, max_retries=1
    ).run((case,)))
    assert report.provider_calls == 2
    assert report.retry_count == 1
    assert report.successful_transport_responses == 1
    assert report.cases[0].attempt_count == 2


@pytest.mark.parametrize("exception,category,status", [
    (LLMProviderHTTPError(status_code=401), BenchmarkFailureCategory.AUTHENTICATION, 401),
    (LLMProviderHTTPError(status_code=403), BenchmarkFailureCategory.PERMISSION, 403),
    (LLMProviderHTTPError(status_code=400), BenchmarkFailureCategory.INVALID_REQUEST, 400),
    (LLMProviderHTTPError(status_code=404), BenchmarkFailureCategory.MODEL_UNAVAILABLE, 404),
    (LLMProviderHTTPError(status_code=429), BenchmarkFailureCategory.RATE_LIMIT, 429),
    (LLMProviderHTTPError(status_code=503), BenchmarkFailureCategory.SERVER_ERROR, 503),
    (LLMProviderTimeoutError("timeout"), BenchmarkFailureCategory.TIMEOUT, None),
    (LLMProviderNetworkError("network"), BenchmarkFailureCategory.NETWORK, None),
    (LLMProviderMalformedJSONError("bad json"), BenchmarkFailureCategory.MALFORMED_RESPONSE, None),
])
def test_transport_failures_are_one_safe_first_class_case(exception, category, status):
    case = curated_group_benchmark_cases()[0]

    class FailingProvider(BenchmarkProvider):
        async def execute(self, request):
            self.calls += 1
            raise exception

    provider = FailingProvider()
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        provider, max_calls=1, max_retries=0
    ).run((case,)))
    assert report.total_cases_attempted == len(report.cases) == 1
    result = report.cases[0]
    assert result.case_id == case.case_id
    assert result.source_kind == case.source_kind
    assert result.group_size == case.group_size
    assert result.transport_succeeded is False
    assert result.execution_status == "TRANSPORT_FAILED"
    assert result.attempt_count == 1
    assert result.safe_error_category == category
    assert result.safe_error_code == category.value
    assert result.http_status == status
    assert result.request_bytes > 0
    assert result.response_bytes is None
    assert report.request_bytes == result.request_bytes
    assert report.failure_counts[category.value] == 1
    assert classify_benchmark_failure(exception) == category


def test_retry_then_terminal_failure_is_one_case_with_two_attempts():
    case = curated_group_benchmark_cases()[0]

    class RetryThenTerminal(BenchmarkProvider):
        async def execute(self, request):
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderNetworkError("synthetic retry")
            raise LLMProviderHTTPError(status_code=401)

    provider = RetryThenTerminal()
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        provider, max_calls=2, max_retries=1
    ).run((case,)))
    assert report.provider_calls == 2 and report.retry_count == 1
    assert report.total_cases_attempted == len(report.cases) == 1
    assert report.cases[0].attempt_count == 2
    assert report.cases[0].safe_error_category == BenchmarkFailureCategory.AUTHENTICATION


def test_all_transport_failures_retain_every_attempted_case_and_aggregate_bytes():
    cases = curated_group_benchmark_cases()[:5]

    class TerminalProvider(BenchmarkProvider):
        async def execute(self, request):
            self.calls += 1
            raise LLMProviderHTTPError(status_code=403)

    provider = TerminalProvider()
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        provider, max_calls=5, max_retries=0
    ).run(cases))
    assert report.total_cases_attempted == len(report.cases) == 5
    assert report.provider_calls == provider.calls == 5
    assert report.successful_transport_responses == 0
    assert report.request_bytes == sum(case.request_bytes for case in report.cases)
    assert all(case.request_bytes > 0 for case in report.cases)
    assert report.failure_counts["PERMISSION"] == 5


def test_failure_report_serialization_is_secret_and_header_free():
    case = curated_group_benchmark_cases()[0]
    sentinel = "synthetic-sensitive-sentinel"

    class SecretBearingFailure(BenchmarkProvider):
        async def execute(self, request):
            self.calls += 1
            raise LLMProviderError(f"Authorization Bearer {sentinel}")

    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        SecretBearingFailure(), max_calls=1, max_retries=0
    ).run((case,)))
    encoded = json.dumps(report.model_dump(), sort_keys=True)
    assert sentinel not in encoded
    assert "Authorization" not in encoded
    assert "Bearer" not in encoded
    assert report.cases[0].provider_error_type == "LLMProviderError"
    assert report.cases[0].safe_error_message == (
        "Benchmark case failed safely: unknown_provider_error."
    )


def test_malformed_and_semantic_failures_are_not_transport_failures():
    case = curated_group_benchmark_cases()[0]
    malformed = BenchmarkProvider("invalid")
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        malformed, max_calls=1
    ).run((case,)))
    result = report.cases[0]
    assert result.transport_succeeded is True
    assert result.execution_status == "INVALID_PROVIDER_OUTPUT"
    assert result.safe_error_category == BenchmarkFailureCategory.SEMANTIC_VALIDATION
    assert result.usefulness_class == BenchmarkUsefulness.INVALID_REJECTED
    assert report.failure_counts["SEMANTIC_VALIDATION"] == 1
    assert classify_benchmark_failure(
        LLMProviderResponseStructureError("bad envelope")
    ) == BenchmarkFailureCategory.MALFORMED_RESPONSE


def test_groq_request_byte_accounting_excludes_authorization_header():
    request = curated_group_benchmark_cases()[0].request
    transport = GroqLLMProvider(
        api_key=SecretStr("synthetic-secret"), model="benchmark-model",
        timeout_seconds=3,
    )
    provider = GroqGroupAdvisoryProvider(transport)
    assert provider.request_bytes(request) > 0
    messages = build_group_advisory_messages(request)
    expected_payload = {
        "model": "benchmark-model",
        "messages": [
            {"role": "system", "content": messages.system_prompt},
            {"role": "user", "content": messages.user_prompt},
        ],
        "stream": False, "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    expected = len(json.dumps(
        expected_payload, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8"))
    assert provider.request_bytes(request) == expected


@pytest.mark.parametrize("mutate,reason", [
    (lambda body, _request: body.update(request_fingerprint="f" * 64),
     "REQUEST_FINGERPRINT_MISMATCH"),
    (lambda body, request: body.update(group_snapshot_id=request.group_snapshot_id + 1),
     "GROUP_SNAPSHOT_MISMATCH"),
    (lambda body, _request: body.update(group_hypothesis_key="e" * 64),
     "GROUP_HYPOTHESIS_MISMATCH"),
    (lambda body, request: body.update(proposed_partitions=[
        [member.record_ref_key for member in request.members[:-1]]
    ]), "INCOMPLETE_PARTITION_MEMBERSHIP"),
    (lambda body, request: body.update(proposed_partitions=[[
        *(member.record_ref_key for member in request.members),
        request.members[0].record_ref_key,
    ]]), "DUPLICATE_PARTITION_MEMBER"),
    (lambda body, request: body.update(proposed_partitions=[[
        *(member.record_ref_key for member in request.members[:-1]), "f" * 64,
    ]]), "UNKNOWN_PARTITION_MEMBER"),
    (lambda body, request: body.update(proposed_partitions=[
        [request.members[0].record_ref_key],
        [member.record_ref_key for member in request.members[1:]],
    ]), "SINGLE_IDENTITY_REQUIRES_ONE_SET"),
    (lambda body, request: body.update(
        outcome="INCONCLUSIVE",
        proposed_partitions=[[member.record_ref_key for member in request.members]],
    ), "INCONCLUSIVE_MUST_NOT_PARTITION"),
])
def test_benchmark_retains_exact_safe_validation_reasons(mutate, reason):
    case = curated_group_benchmark_cases()[0]

    class InvalidSemanticProvider(BenchmarkProvider):
        async def execute(self, request):
            self.calls += 1
            body = valid_content(request)
            mutate(body, request)
            return RawGroupProviderResponse(
                provider_id=self.provider_id, provider_model=self.provider_model,
                content=body,
            )

    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        InvalidSemanticProvider(), max_calls=1
    ).run((case,)))
    result = report.cases[0]
    assert result.safe_error_category == BenchmarkFailureCategory.SEMANTIC_VALIDATION
    assert reason in result.validation_reason_codes
    assert report.failure_counts["SEMANTIC_VALIDATION"] == 1


def test_benchmark_schema_diagnostics_are_bounded_and_provider_prose_free():
    case = curated_group_benchmark_cases()[0]
    sentinel = "provider-private-prose-sentinel"

    class SchemaFailure(BenchmarkProvider):
        async def execute(self, request):
            self.calls += 1
            return RawGroupProviderResponse(
                provider_id=self.provider_id, provider_model=self.provider_model,
                content={"rationale": sentinel},
            )

    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        SchemaFailure(), max_calls=1
    ).run((case,)))
    result = report.cases[0]
    assert result.validation_reason_codes == ("MISSING_REQUIRED_FIELD",)
    encoded_result = json.dumps(result.__dict__, sort_keys=True)
    assert sentinel not in encoded_result


def test_cannot_link_reason_is_retained_without_unsafe_acceptance():
    case = next(c for c in curated_group_benchmark_cases() if c.protected_cannot_links)
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        BenchmarkProvider("unsafe"), max_calls=1
    ).run((case,)))
    result = report.cases[0]
    assert result.validation_reason_codes == ("PROTECTED_CANNOT_LINK_VIOLATION",)
    assert report.unsafe_cannot_link_proposals_rejected == 1
    assert report.semantically_valid_responses == 0


def run_mocked_groq_case(case, content, *, fenced=False):
    async def run():
        def handler(_request):
            encoded = json.dumps(content)
            if fenced:
                encoded = f"```json\n{encoded}\n```"
            return httpx.Response(200, json={
                "id": "mocked-group-request",
                "choices": [{"message": {"content": encoded}}],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GroqGroupAdvisoryProvider(GroqLLMProvider(
                api_key=SecretStr("synthetic-key"), model="benchmark-model",
                timeout_seconds=3, client=client,
            ))
            return await GroupAdvisoryBenchmarkRunner(
                provider, max_calls=1
            ).run((case,))
    return asyncio.run(run())


def test_mocked_groq_exact_single_identity_contract_passes():
    case = next(c for c in curated_group_benchmark_cases()
                if c.expected_resolution == BenchmarkExpectedResolution.SINGLE_IDENTITY)
    report = run_mocked_groq_case(case, valid_content(case.request))
    result = report.cases[0]
    assert result.structurally_valid and result.semantically_valid
    assert result.validated_outcome == "SUPPORTS_SINGLE_IDENTITY"


@pytest.mark.parametrize("partition_sizes", [(1, 4), (1, 2, 2)])
def test_mocked_groq_exact_multi_partition_contract_passes(partition_sizes):
    case = next(
        c for c in curated_group_benchmark_cases()
        if sorted(map(len, c.expected_partitions)) == list(partition_sizes)
    )
    body = valid_content(
        case.request, "PROPOSES_PARTITION", case.expected_partitions
    )
    result = run_mocked_groq_case(case, body).cases[0]
    assert result.structurally_valid and result.semantically_valid
    assert result.validated_outcome == "PROPOSES_PARTITION"


def test_mocked_groq_exact_inconclusive_and_fenced_json_pass():
    case = next(c for c in curated_group_benchmark_cases()
                if c.expected_resolution == BenchmarkExpectedResolution.INCONCLUSIVE_ACCEPTABLE)
    body = valid_content(case.request, "INCONCLUSIVE", ())
    result = run_mocked_groq_case(case, body, fenced=True).cases[0]
    assert result.structurally_valid and result.semantically_valid
    assert result.validated_outcome == "INCONCLUSIVE"


def test_mocked_groq_correct_partition_with_missing_fingerprint_still_fails():
    case = next(c for c in curated_group_benchmark_cases()
                if c.expected_resolution == BenchmarkExpectedResolution.PARTITION)
    body = valid_content(case.request, "PROPOSES_PARTITION", case.expected_partitions)
    body.pop("request_fingerprint")
    result = run_mocked_groq_case(case, body).cases[0]
    assert not result.structurally_valid and not result.semantically_valid
    assert result.validation_reason_codes == ("MISSING_REQUIRED_FIELD",)


def test_mocked_groq_changed_member_ref_still_fails():
    case = next(c for c in curated_group_benchmark_cases()
                if c.expected_resolution == BenchmarkExpectedResolution.PARTITION)
    partitions = [list(block) for block in case.expected_partitions]
    partitions[0][0] = "f" * 64
    body = valid_content(case.request, "PROPOSES_PARTITION", partitions)
    result = run_mocked_groq_case(case, body).cases[0]
    assert result.structurally_valid and not result.semantically_valid
    assert {"UNKNOWN_PARTITION_MEMBER", "INCOMPLETE_PARTITION_MEMBERSHIP"}.issubset(
        result.validation_reason_codes
    )


def test_benchmark_case_pacing_defaults_zero_and_occurs_only_between_cases():
    cases = curated_group_benchmark_cases()[:3]
    delays = []

    async def sleeper(delay):
        delays.append(delay)

    default = GroupAdvisoryBenchmarkRunner(BenchmarkProvider(), max_calls=3)
    assert default.case_delay_ms == 0
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        BenchmarkProvider(), max_calls=3, case_delay_ms=250, sleeper=sleeper,
    ).run(cases))
    assert report.total_cases_attempted == 3
    assert delays == [0.25, 0.25]
    with pytest.raises(ValueError):
        GroupAdvisoryBenchmarkRunner(BenchmarkProvider(), case_delay_ms=-1)


def test_cli_pacing_and_deterministic_max_case_subset():
    parser = build_parser()
    defaults = parser.parse_args([
        "--corpus", "curated-v1", "--output", "report.json",
    ])
    assert defaults.case_delay_ms == 0 and defaults.max_cases is None
    explicit = parser.parse_args([
        "--corpus", "curated-v1", "--max-cases", "6",
        "--case-delay-ms", "500", "--output", "report.json",
    ])
    assert explicit.max_cases == 6 and explicit.case_delay_ms == 500
    with pytest.raises(SystemExit):
        parser.parse_args([
            "--corpus", "curated-v1", "--case-delay-ms", "-1",
            "--output", "report.json",
        ])
    corpus = curated_group_benchmark_cases()
    selected = select_benchmark_cases(corpus, 6)
    assert selected == corpus[:6]
    assert [case.request_fingerprint for case in selected] == [
        case.request_fingerprint for case in corpus[:6]
    ]
    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        BenchmarkProvider(), max_calls=10
    ).run(selected))
    assert report.total_cases_attempted == 6


def test_retry_after_and_case_pacing_share_bounded_benchmark_sleeper():
    cases = curated_group_benchmark_cases()[:2]
    delays = []

    async def sleeper(delay):
        delays.append(delay)

    class OnceRateLimited(BenchmarkProvider):
        async def execute(self, request):
            self.calls += 1
            if self.calls == 1:
                raise LLMProviderHTTPError(
                    status_code=429, retry_after_seconds=2,
                )
            return await super().execute(request)

    report = asyncio.run(GroupAdvisoryBenchmarkRunner(
        OnceRateLimited(), max_calls=3, max_retries=1,
        case_delay_ms=500, sleeper=sleeper,
    ).run(cases))
    assert report.total_cases_attempted == len(report.cases) == 2
    assert report.retry_count == 1
    assert delays == [2.0, 0.5]
