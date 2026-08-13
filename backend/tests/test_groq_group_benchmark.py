import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm.exceptions import (
    LLMProviderConfigurationError, LLMProviderHTTPError,
    LLMProviderMalformedJSONError, LLMProviderNetworkError,
    LLMProviderTimeoutError,
)
from app.llm.groq_group_provider import (
    GroqGroupAdvisoryProvider, create_group_advisory_provider,
)
from app.llm.groq_provider import GroqLLMProvider
from app.llm.group_benchmark import (
    BenchmarkExpectedResolution, BenchmarkSourceKind, BenchmarkUsefulness,
    GroupAdvisoryBenchmarkRunner, canonical_partition,
    curated_group_benchmark_cases, live_group_benchmark_enabled,
)
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
    with pytest.raises(ValueError):
        asyncio.run(GroupAdvisoryBenchmarkRunner(provider, max_calls=5).run(
            curated_group_benchmark_cases()[:6]
        ))
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
