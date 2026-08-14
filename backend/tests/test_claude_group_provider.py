import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm.claude_group_provider import (
    ANTHROPIC_API_VERSION,
    ANTHROPIC_MESSAGES_URL,
    ClaudeGroupAdvisoryProvider,
    anthropic_group_structured_output_schema,
)
from app.llm.exceptions import (
    LLMProviderConfigurationError,
    LLMProviderEmptyResponseError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderNetworkError,
    LLMProviderResponseStructureError,
    LLMProviderTimeoutError,
)
from app.llm.group_benchmark import (
    BenchmarkExpectedResolution,
    BenchmarkFailureCategory,
    GroupAdvisoryBenchmarkRunner,
    curated_group_benchmark_cases,
    live_group_benchmark_enabled,
)
from app.llm.group_contracts import (
    GROUP_ADVISORY_RESULT_VERSION,
    GroupAdvisoryRequest,
    group_advisory_request_fingerprint,
    validate_group_advisory_result,
)
from app.llm.group_execution import (
    GroupAdvisoryProvider,
    build_group_advisory_messages,
    group_advisory_structured_output_schema,
)
from app.llm.group_provider_factory import create_group_advisory_provider
from app.llm.groq_group_provider import GroqGroupAdvisoryProvider
from app.llm.group_execution import DisabledGroupAdvisoryProvider
from app.llm.factory import create_llm_provider
from app.llm.disabled_provider import DisabledLLMProvider


def case_for_size(size):
    return next(case for case in curated_group_benchmark_cases() if case.group_size == size)


def valid_content(request, outcome="SUPPORTS_SINGLE_IDENTITY", partitions=None):
    members = tuple(member.record_ref_key for member in request.members)
    if partitions is None:
        partitions = (members,) if outcome == "SUPPORTS_SINGLE_IDENTITY" else ()
    return {
        "contract_version": GROUP_ADVISORY_RESULT_VERSION,
        "request_fingerprint": group_advisory_request_fingerprint(request),
        "group_snapshot_id": request.group_snapshot_id,
        "group_hypothesis_key": request.group_hypothesis_key,
        "outcome": outcome,
        "proposed_partitions": partitions,
        "confidence_band": "MEDIUM",
        "reason_codes": ["CURATED_TEST"],
        "rationale": "Synthetic advisory only.",
        "mapping_observations": [],
        "requires_human_review": True,
        "deterministic_result_authoritative": True,
    }


def message_response(content, *, stop_reason="end_turn", headers=None, usage=None):
    return httpx.Response(
        200,
        headers=headers,
        json={
            "id": "msg_synthetic",
            "type": "message",
            "role": "assistant",
            "model": "claude-test-model",
            "stop_reason": stop_reason,
            "content": [{"type": "text", "text": json.dumps(content)}],
            "usage": usage or {"input_tokens": 10, "output_tokens": 5},
        },
    )


def execute_with_handler(handler, *, size=2, max_tokens=2048):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ClaudeGroupAdvisoryProvider(
                api_key=SecretStr("synthetic-test-key"),
                model="claude-test-model",
                max_tokens=max_tokens,
                timeout_seconds=2,
                client=client,
            )
            request = case_for_size(size).request
            return provider, request, await provider.execute(request)
    return asyncio.run(run())


@pytest.mark.parametrize("size", [2, 7])
def test_one_whole_group_is_one_anthropic_messages_call(size):
    captured = []

    def handler(request):
        captured.append(request)
        return message_response(valid_content(case_for_size(size).request))

    provider, request, response = execute_with_handler(handler, size=size)
    assert isinstance(provider, GroupAdvisoryProvider)
    assert provider.provider_id == "claude" and provider.enabled is True
    assert len(captured) == 1 and len(request.members) == size
    assert response.provider_id == "claude"
    assert response.provider_model == "claude-test-model"


def test_messages_headers_minimized_data_schema_and_byte_accounting():
    captured = []

    def handler(request):
        captured.append(request)
        return message_response(
            valid_content(case_for_size(2).request),
            headers={"request-id": "req_safe_123"},
        )

    provider, request, response = execute_with_handler(handler, max_tokens=3072)
    http_request = captured[0]
    body = json.loads(http_request.content)
    generic = build_group_advisory_messages(request)
    assert str(http_request.url) == ANTHROPIC_MESSAGES_URL
    assert http_request.headers["x-api-key"] == "synthetic-test-key"
    assert http_request.headers["anthropic-version"] == ANTHROPIC_API_VERSION
    assert http_request.headers["content-type"] == "application/json"
    assert body == {
        "model": "claude-test-model",
        "max_tokens": 3072,
        "system": generic.system_prompt,
        "messages": [{"role": "user", "content": generic.user_prompt}],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": anthropic_group_structured_output_schema(),
            }
        },
    }
    request_payload = json.loads(generic.user_prompt.split("\nrequest=", 1)[1])
    assert set(request_payload) == set(GroupAdvisoryRequest.model_fields)
    assert provider.request_bytes(request) == len(json.dumps(
        body, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))
    assert "synthetic-test-key" not in json.dumps(body)
    assert response.request_id == "req_safe_123"


def test_structured_content_and_anthropic_usage_are_extracted_safely():
    request = case_for_size(2).request
    expected = valid_content(request)

    def handler(_request):
        return message_response(expected, usage={
            "input_tokens": 11,
            "output_tokens": 7,
            "cache_creation_input_tokens": 3,
            "cache_read_input_tokens": 5,
        })

    _, _, response = execute_with_handler(handler)
    assert response.content == json.loads(json.dumps(expected))
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 7
    assert response.usage.cache_creation_input_tokens == 3
    assert response.usage.cache_read_input_tokens == 5
    assert response.usage.total_tokens == 26


@pytest.mark.parametrize(
    ("response", "exception"),
    [
        (httpx.Response(200, json={"type":"message","role":"assistant","stop_reason":"end_turn","content":[]}), LLMProviderEmptyResponseError),
        (httpx.Response(200, json={"type":"unexpected","role":"assistant","stop_reason":"end_turn","content":[]}), LLMProviderResponseStructureError),
        (httpx.Response(200, json={"type":"message","role":"assistant","stop_reason":"end_turn","content":[{"type":"text","text":"{}"},{"type":"text","text":"{}"}]}), LLMProviderResponseStructureError),
        (httpx.Response(200, json={"type":"message","role":"assistant","stop_reason":"end_turn","content":[{"type":"text","text":"{bad"}]}), LLMProviderMalformedJSONError),
    ],
)
def test_empty_ambiguous_malformed_or_unexpected_content_fails(response, exception):
    with pytest.raises(exception):
        execute_with_handler(lambda _request: response)


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal", "tool_use", "pause_turn", "stop_sequence"])
def test_incomplete_or_non_result_stop_reasons_fail_safely(stop_reason):
    request = case_for_size(2).request
    with pytest.raises(LLMProviderResponseStructureError):
        execute_with_handler(
            lambda _request: message_response(valid_content(request), stop_reason=stop_reason)
        )


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_http_status_and_retry_after_map_to_provider_neutral_error(status):
    with pytest.raises(LLMProviderHTTPError) as caught:
        execute_with_handler(lambda _request: httpx.Response(
            status, text="private provider body", headers={"retry-after":"2"}
        ))
    assert caught.value.status_code == status
    assert caught.value.retry_after_seconds == 2
    assert "private" not in str(caught.value)


def test_timeout_and_network_failures_map_safely():
    def timeout(request):
        raise httpx.ReadTimeout("private timeout", request=request)

    def network(request):
        raise httpx.ConnectError("private network", request=request)

    with pytest.raises(LLMProviderTimeoutError):
        execute_with_handler(timeout)
    with pytest.raises(LLMProviderNetworkError):
        execute_with_handler(network)


def test_provider_facing_schema_is_derived_with_only_documented_bound_transformations():
    authoritative = group_advisory_structured_output_schema()
    claude = anthropic_group_structured_output_schema()
    assert set(claude["properties"]) == set(authoritative["properties"])
    assert claude["required"] == authoritative["required"]
    assert claude["additionalProperties"] is False
    assert claude["$defs"]["GroupAdvisoryOutcome"]["enum"] == [
        "SUPPORTS_SINGLE_IDENTITY", "PROPOSES_PARTITION", "INCONCLUSIVE"
    ]
    assert claude["properties"]["requires_human_review"]["const"] is True
    assert claude["properties"]["deterministic_result_authoritative"]["const"] is True
    serialized = json.dumps(claude)
    for unsupported in (
        '"minimum"', '"maximum"', '"exclusiveMinimum"', '"exclusiveMaximum"',
        '"minLength"', '"maxLength"', '"minItems"', '"maxItems"',
    ):
        assert unsupported not in serialized
    assert "maxLength" in json.dumps(authoritative)
    assert "Authoritative local constraint" in serialized


def _partition_case(lengths):
    return next(
        case for case in curated_group_benchmark_cases()
        if sorted(map(len, case.expected_partitions)) == sorted(lengths)
    )


@pytest.mark.parametrize("kind", ["single", "4+1", "2+2+1", "inconclusive"])
def test_valid_claude_shapes_pass_authoritative_structural_and_semantic_validation(kind):
    if kind == "single":
        case = next(c for c in curated_group_benchmark_cases() if c.expected_resolution == BenchmarkExpectedResolution.SINGLE_IDENTITY)
        raw = valid_content(case.request)
    elif kind == "inconclusive":
        case = next(c for c in curated_group_benchmark_cases() if c.expected_resolution == BenchmarkExpectedResolution.INCONCLUSIVE_ACCEPTABLE)
        raw = valid_content(case.request, "INCONCLUSIVE", ())
    else:
        case = _partition_case([4, 1] if kind == "4+1" else [2, 2, 1])
        raw = valid_content(case.request, "PROPOSES_PARTITION", case.expected_partitions)
    validated = validate_group_advisory_result(case.request, raw)
    assert validated.validation_reasons == ()


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        (lambda raw, request: raw.update(request_fingerprint="f" * 64), "REQUEST_FINGERPRINT_MISMATCH"),
        (lambda raw, request: raw.update(group_snapshot_id=request.group_snapshot_id + 1), "GROUP_SNAPSHOT_MISMATCH"),
        (lambda raw, request: raw.update(group_hypothesis_key="b" * 64), "GROUP_HYPOTHESIS_MISMATCH"),
        (lambda raw, request: raw.update(proposed_partitions=[list(tuple(m.record_ref_key for m in request.members)[:-1])]), "INCOMPLETE_PARTITION_MEMBERSHIP"),
        (lambda raw, request: raw.update(proposed_partitions=[[m.record_ref_key for m in request.members] + ["f" * 64]]), "UNKNOWN_PARTITION_MEMBER"),
        (lambda raw, request: raw.update(proposed_partitions=[[m.record_ref_key for m in request.members] + [request.members[0].record_ref_key]]), "DUPLICATE_PARTITION_MEMBER"),
        (lambda raw, request: raw.update(requires_human_review=False), "SCHEMA_MISMATCH"),
        (lambda raw, request: raw.update(deterministic_result_authoritative=False), "SCHEMA_MISMATCH"),
    ],
)
def test_invalid_identity_echo_member_and_authority_results_are_rejected(mutation, expected_reason):
    request = case_for_size(2).request
    raw = valid_content(request)
    mutation(raw, request)
    assert expected_reason in validate_group_advisory_result(request, raw).validation_reasons


def test_cannot_link_violation_is_rejected_by_g7a_not_claude():
    case = next(c for c in curated_group_benchmark_cases() if c.protected_cannot_links)
    raw = valid_content(case.request)
    validated = validate_group_advisory_result(case.request, raw)
    assert "PROTECTED_CANNOT_LINK_VIOLATION" in validated.validation_reasons


def test_group_provider_factory_selects_exact_provider_without_pair_fallback():
    assert isinstance(create_group_advisory_provider(Settings()), DisabledGroupAdvisoryProvider)
    groq = create_group_advisory_provider(Settings(
        group_llm_provider="groq", groq_api_key="synthetic", group_llm_model="groq-model"
    ))
    assert isinstance(groq, GroqGroupAdvisoryProvider)
    with pytest.raises(LLMProviderConfigurationError):
        create_group_advisory_provider(Settings(
            group_llm_provider="claude", anthropic_api_key="synthetic"
        ))
    claude = create_group_advisory_provider(Settings(
        group_llm_provider="claude", anthropic_api_key="synthetic",
        claude_group_model="claude-model", llm_provider="none",
    ))
    assert isinstance(claude, ClaudeGroupAdvisoryProvider)
    assert claude.provider_model == "claude-model"
    pair_configuration = Settings(group_llm_provider="claude")
    assert pair_configuration.llm_provider == "none"
    assert isinstance(create_llm_provider(pair_configuration), DisabledLLMProvider)


def test_live_gate_and_corpus_remain_provider_neutral_and_identical():
    cases = curated_group_benchmark_cases()
    identity = tuple((c.case_id, c.request_fingerprint, c.expected_resolution, c.expected_partitions) for c in cases)
    assert live_group_benchmark_enabled(Settings(group_llm_provider="claude"), explicit_live=True, corpus_selected=True)
    assert live_group_benchmark_enabled(Settings(group_llm_provider="groq"), explicit_live=True, corpus_selected=True)
    assert not live_group_benchmark_enabled(Settings(group_llm_provider="none"), explicit_live=True, corpus_selected=True)
    assert identity == tuple((c.case_id, c.request_fingerprint, c.expected_resolution, c.expected_partitions) for c in curated_group_benchmark_cases())


def test_benchmark_reuses_bounded_retry_and_terminal_auth_does_not_retry():
    async def scenario(first_status):
        calls = 0
        case = case_for_size(2)

        def handler(_request):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(first_status)
            return message_response(valid_content(case.request))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ClaudeGroupAdvisoryProvider(
                api_key=SecretStr("synthetic"), model="claude-model",
                max_tokens=1024, timeout_seconds=2, client=client,
            )
            report = await GroupAdvisoryBenchmarkRunner(
                provider, max_calls=3, max_retries=1,
                sleeper=lambda _delay: asyncio.sleep(0),
            ).run((case,))
            return calls, report

    retry_calls, retry_report = asyncio.run(scenario(503))
    assert retry_calls == retry_report.provider_calls == 2
    assert retry_report.successful_transport_responses == 1
    for status, category in (
        (401, BenchmarkFailureCategory.AUTHENTICATION),
        (403, BenchmarkFailureCategory.PERMISSION),
    ):
        terminal_calls, terminal_report = asyncio.run(scenario(status))
        assert terminal_calls == terminal_report.provider_calls == 1
        assert terminal_report.failure_counts[category.value] == 1


def test_benchmark_reuses_provider_neutral_d5_field_only_diagnostics():
    async def run():
        case = case_for_size(2)
        malformed = valid_content(case.request)
        malformed.pop("request_fingerprint")
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _request: message_response(malformed)
        )) as client:
            provider = ClaudeGroupAdvisoryProvider(
                api_key=SecretStr("synthetic"), model="claude-model",
                max_tokens=1024, timeout_seconds=2, client=client,
            )
            return await GroupAdvisoryBenchmarkRunner(
                provider, max_calls=1, max_retries=0
            ).run((case,))

    report = asyncio.run(run())
    item = report.cases[0]
    assert item.schema_missing_fields == ("request_fingerprint",)
    assert item.validation_reason_codes == ("SCHEMA_MISMATCH",)
    assert "Synthetic advisory only" not in json.dumps(report.model_dump())


def test_benchmark_preserves_claude_cache_usage_separately():
    async def run():
        case = case_for_size(2)
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _request: message_response(valid_content(case.request), usage={
                "input_tokens": 11, "output_tokens": 7,
                "cache_creation_input_tokens": 3,
                "cache_read_input_tokens": 5,
            })
        )) as client:
            provider = ClaudeGroupAdvisoryProvider(
                api_key=SecretStr("synthetic"), model="claude-model",
                max_tokens=1024, timeout_seconds=2, client=client,
            )
            return await GroupAdvisoryBenchmarkRunner(
                provider, max_calls=1, max_retries=0
            ).run((case,))

    report = asyncio.run(run())
    item = report.cases[0]
    assert (item.prompt_tokens, item.completion_tokens, item.total_tokens) == (11, 7, 26)
    assert item.cache_creation_input_tokens == report.cache_creation_input_tokens == 3
    assert item.cache_read_input_tokens == report.cache_read_input_tokens == 5


def test_claude_benchmark_reuses_existing_case_pacing_and_call_cap():
    async def run(max_calls, cases):
        delays = []

        async def sleeper(delay):
            delays.append(delay)

        requests = {case.request.group_snapshot_id: case.request for case in cases}

        def handler(http_request):
            body = json.loads(http_request.content)
            request_payload = json.loads(
                body["messages"][0]["content"].split("\nrequest=", 1)[1]
            )
            request = requests[request_payload["group_snapshot_id"]]
            return message_response(valid_content(request))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ClaudeGroupAdvisoryProvider(
                api_key=SecretStr("synthetic"), model="claude-model",
                max_tokens=1024, timeout_seconds=2, client=client,
            )
            report = await GroupAdvisoryBenchmarkRunner(
                provider, max_calls=max_calls, max_retries=0,
                case_delay_ms=5000, sleeper=sleeper,
            ).run(cases)
            return delays, report

    cases = curated_group_benchmark_cases()[:2]
    delays, report = asyncio.run(run(2, cases))
    capped_delays, capped = asyncio.run(run(1, cases))
    assert delays == [5.0]
    assert report.provider_calls == report.total_cases_attempted == 2
    assert capped_delays == []
    assert capped.provider_calls == capped.total_cases_attempted == 1
