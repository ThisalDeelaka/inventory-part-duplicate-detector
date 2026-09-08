"""Fixed, provider-independent benchmark harness for experimental group adapters."""

import asyncio
import hashlib
import json
import math
import time
from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Any

from app.core.config import Settings
from app.llm.exceptions import (
    LLMProviderConfigurationError,
    LLMProviderDisabledError,
    LLMProviderEmptyResponseError,
    LLMProviderError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderNetworkError,
    LLMProviderResponseStructureError,
    LLMProviderTimeoutError,
)
from app.llm.group_contracts import (
    GROUP_ADVISORY_REQUEST_VERSION,
    GROUP_ADVISORY_RESULT_VERSION,
    GroupAdvisoryEdge,
    GroupAdvisoryMember,
    GroupAdvisoryOutcome,
    GroupAdvisoryRequest,
    GroupIdentityEvidenceSummary,
    GroupUomMappingSummary,
    canonical_group_advisory_request_json,
    group_advisory_request_fingerprint,
    parse_group_advisory_result,
    validate_group_advisory_result,
)
from app.llm.group_execution import (
    GROUP_PROMPT_CONTRACT_VERSION,
    GroupAdvisoryProvider,
    RawGroupProviderResponse,
)


GROUP_BENCHMARK_VERSION = "group-advisory-benchmark-v1"


class BenchmarkExpectedResolution(str, Enum):
    SINGLE_IDENTITY = "SINGLE_IDENTITY"
    PARTITION = "PARTITION"
    INCONCLUSIVE_ACCEPTABLE = "INCONCLUSIVE_ACCEPTABLE"


class BenchmarkSourceKind(str, Enum):
    CURATED_SYNTHETIC = "CURATED_SYNTHETIC"
    VALIDATOR_SAFETY_CHALLENGE = "VALIDATOR_SAFETY_CHALLENGE"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"


class BenchmarkUsefulness(str, Enum):
    USEFUL_CORRECT = "USEFUL_CORRECT"
    SAFE_ABSTENTION = "SAFE_ABSTENTION"
    INCORRECT = "INCORRECT"
    INVALID_REJECTED = "INVALID_REJECTED"


class BenchmarkFailureCategory(str, Enum):
    AUTHENTICATION = "AUTHENTICATION"
    PERMISSION = "PERMISSION"
    INVALID_REQUEST = "INVALID_REQUEST"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    SERVER_ERROR = "SERVER_ERROR"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    SEMANTIC_VALIDATION = "SEMANTIC_VALIDATION"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


def classify_benchmark_failure(exc: Exception) -> BenchmarkFailureCategory:
    if isinstance(exc, (asyncio.TimeoutError, LLMProviderTimeoutError)):
        return BenchmarkFailureCategory.TIMEOUT
    if isinstance(exc, LLMProviderNetworkError):
        return BenchmarkFailureCategory.NETWORK
    if isinstance(exc, LLMProviderHTTPError):
        return {
            400: BenchmarkFailureCategory.INVALID_REQUEST,
            401: BenchmarkFailureCategory.AUTHENTICATION,
            403: BenchmarkFailureCategory.PERMISSION,
            404: BenchmarkFailureCategory.MODEL_UNAVAILABLE,
            429: BenchmarkFailureCategory.RATE_LIMIT,
        }.get(
            exc.status_code,
            BenchmarkFailureCategory.SERVER_ERROR
            if exc.status_code is not None and 500 <= exc.status_code <= 599
            else BenchmarkFailureCategory.UNKNOWN_PROVIDER_ERROR,
        )
    if isinstance(exc, (
        LLMProviderMalformedJSONError, LLMProviderResponseStructureError,
        LLMProviderEmptyResponseError,
    )):
        return BenchmarkFailureCategory.MALFORMED_RESPONSE
    if isinstance(exc, (LLMProviderDisabledError, LLMProviderConfigurationError)):
        return BenchmarkFailureCategory.PROVIDER_DISABLED
    return BenchmarkFailureCategory.UNKNOWN_PROVIDER_ERROR


_SAFE_FAILURE_MESSAGES = {
    category: f"Benchmark case failed safely: {category.value.lower()}."
    for category in BenchmarkFailureCategory
}


def canonical_partition(partitions) -> tuple[tuple[str, ...], ...]:
    return tuple(sorted(
        (tuple(sorted(block)) for block in partitions),
        key=lambda block: (len(block), block),
    ))


@dataclass(frozen=True)
class GroupAdvisoryBenchmarkCase:
    case_id: str
    request: GroupAdvisoryRequest
    request_fingerprint: str
    group_size: int
    expected_resolution: BenchmarkExpectedResolution
    expected_partitions: tuple[tuple[str, ...], ...]
    protected_cannot_links: tuple[tuple[str, str], ...]
    source_kind: BenchmarkSourceKind
    notes: str

    def __post_init__(self) -> None:
        actual = group_advisory_request_fingerprint(self.request)
        if self.request_fingerprint != actual:
            raise ValueError("benchmark request fingerprint mismatch")
        if self.group_size != self.request.group_size:
            raise ValueError("benchmark group size mismatch")


@dataclass(frozen=True)
class GroupBenchmarkCaseResult:
    case_id: str
    source_kind: BenchmarkSourceKind
    group_size: int
    request_fingerprint: str
    expected_resolution: BenchmarkExpectedResolution
    provider_id: str
    model_id: str | None
    execution_status: str
    attempt_count: int
    transport_succeeded: bool
    structurally_valid: bool
    semantically_valid: bool
    validated_outcome: str | None
    validity_class: str
    usefulness_class: BenchmarkUsefulness | None
    safe_error_code: str | None
    safe_error_category: BenchmarkFailureCategory | None
    http_status: int | None
    provider_error_type: str | None
    provider_error_code: str | None
    safe_error_message: str | None
    validation_reason_codes: tuple[str, ...]
    schema_missing_fields: tuple[str, ...]
    schema_unexpected_fields: tuple[str, ...]
    schema_wrong_type_fields: tuple[str, ...]
    schema_invalid_literal_fields: tuple[str, ...]
    schema_invalid_length_fields: tuple[str, ...]
    schema_invalid_format_fields: tuple[str, ...]
    schema_other_paths: tuple[str, ...]
    request_bytes: int
    response_bytes: int | None
    latency_ms: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None
    provider_declared_inconclusive: bool
    invalid_normalized_to_inconclusive: bool
    unsafe_cannot_link_rejected: bool


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


@dataclass(frozen=True)
class GroupBenchmarkReport:
    benchmark_version: str
    provider_id: str
    model_id: str | None
    prompt_contract_version: str
    request_contract_version: str
    result_contract_version: str
    total_cases_attempted: int
    eligible_production_like_cases: int
    safety_challenge_cases: int
    provider_calls: int
    successful_transport_responses: int
    structurally_valid_responses: int
    semantically_valid_responses: int
    normalized_invalid_inconclusive: int
    provider_declared_inconclusive: int
    exact_partition_matches: int
    single_identity_matches: int
    wrong_partition_results: int
    unsafe_cannot_link_proposals_rejected: int
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    retry_count: int
    rate_limit_count: int
    timeout_count: int
    failure_counts: dict[str, int]
    schema_mismatch_field_counts: dict[str, dict[str, int]]
    cache_hits: int
    cache_misses: int
    request_bytes: int
    response_bytes: int | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None
    estimated_cost: None
    usefulness_counts: dict[str, int]
    cases: tuple[GroupBenchmarkCaseResult, ...]

    def model_dump(self) -> dict[str, Any]:
        def value(item):
            if isinstance(item, Enum):
                return item.value
            if isinstance(item, tuple):
                return [value(entry) for entry in item]
            if isinstance(item, dict):
                return {key: value(entry) for key, entry in item.items()}
            if hasattr(item, "__dataclass_fields__"):
                return {
                    key: value(getattr(item, key))
                    for key in item.__dataclass_fields__
                }
            return item
        return value(self)


def _usefulness(case, validated, invalid: bool) -> BenchmarkUsefulness:
    if invalid:
        return BenchmarkUsefulness.INVALID_REJECTED
    if validated.outcome == GroupAdvisoryOutcome.INCONCLUSIVE:
        return BenchmarkUsefulness.SAFE_ABSTENTION
    actual = canonical_partition(validated.proposed_partitions)
    expected = canonical_partition(case.expected_partitions)
    if case.expected_resolution == BenchmarkExpectedResolution.SINGLE_IDENTITY:
        correct = (
            validated.outcome == GroupAdvisoryOutcome.SUPPORTS_SINGLE_IDENTITY
            and actual == expected
        )
    elif case.expected_resolution == BenchmarkExpectedResolution.PARTITION:
        correct = (
            validated.outcome == GroupAdvisoryOutcome.PROPOSES_PARTITION
            and actual == expected
        )
    else:
        correct = False
    return (
        BenchmarkUsefulness.USEFUL_CORRECT if correct
        else BenchmarkUsefulness.INCORRECT
    )


def _request_bytes(provider: GroupAdvisoryProvider, request: GroupAdvisoryRequest) -> int:
    calculator = getattr(provider, "request_bytes", None)
    if callable(calculator):
        value = calculator(request)
        if isinstance(value, int) and value > 0:
            return value
    return len(canonical_group_advisory_request_json(request).encode("utf-8"))


def _failure_result(
    case: GroupAdvisoryBenchmarkCase,
    provider: GroupAdvisoryProvider,
    exc: Exception,
    *, attempts: int,
    request_bytes: int,
    latency_ms: float,
) -> GroupBenchmarkCaseResult:
    category = classify_benchmark_failure(exc)
    status = getattr(exc, "status_code", None)
    return GroupBenchmarkCaseResult(
        case_id=case.case_id, source_kind=case.source_kind,
        group_size=case.group_size,
        request_fingerprint=case.request_fingerprint,
        expected_resolution=case.expected_resolution,
        provider_id=provider.provider_id, model_id=provider.provider_model,
        execution_status="TRANSPORT_FAILED", attempt_count=attempts,
        transport_succeeded=False, structurally_valid=False,
        semantically_valid=False, validated_outcome=None,
        validity_class="TRANSPORT_FAILED", usefulness_class=None,
        safe_error_code=category.value, safe_error_category=category,
        http_status=status if isinstance(status, int) else None,
        provider_error_type=type(exc).__name__[:120],
        provider_error_code=None,
        safe_error_message=_SAFE_FAILURE_MESSAGES[category],
        validation_reason_codes=(),
        schema_missing_fields=(), schema_unexpected_fields=(),
        schema_wrong_type_fields=(), schema_invalid_literal_fields=(),
        schema_invalid_length_fields=(), schema_invalid_format_fields=(),
        schema_other_paths=(),
        request_bytes=request_bytes, response_bytes=None,
        latency_ms=latency_ms, prompt_tokens=None,
        completion_tokens=None, total_tokens=None,
        cache_creation_input_tokens=None, cache_read_input_tokens=None,
        provider_declared_inconclusive=False,
        invalid_normalized_to_inconclusive=False,
        unsafe_cannot_link_rejected=False,
    )


class GroupAdvisoryBenchmarkRunner:
    """Explicit bounded runner; no production path imports or invokes it."""

    def __init__(
        self, provider: GroupAdvisoryProvider, *, max_calls: int = 30,
        timeout_seconds: float = 30, max_retries: int = 1,
        case_delay_ms: int = 0,
        sleeper=asyncio.sleep,
    ) -> None:
        if not 1 <= max_calls <= 35:
            raise ValueError("benchmark call cap must be between 1 and 35")
        self.provider = provider
        self.max_calls = max_calls
        self.timeout_seconds = timeout_seconds
        if not 0 <= max_retries <= 2:
            raise ValueError("benchmark retries must be between zero and two")
        self.max_retries = max_retries
        if not 0 <= case_delay_ms <= 300_000:
            raise ValueError("benchmark case delay must be between 0 and 300000 ms")
        self.case_delay_ms = case_delay_ms
        self.sleeper = sleeper

    async def run(
        self, cases: tuple[GroupAdvisoryBenchmarkCase, ...]
    ) -> GroupBenchmarkReport:
        results = []
        attempted_cases = []
        provider_calls = successful = rate_limits = timeouts = retries = 0
        for case in cases:
            if provider_calls >= self.max_calls:
                break
            if attempted_cases and self.case_delay_ms:
                await self.sleeper(self.case_delay_ms / 1000)
            attempted_cases.append(case)
            started = time.perf_counter()
            request_bytes = _request_bytes(self.provider, case.request)
            raw = None
            attempts = 0
            last_error = None
            for attempt in range(self.max_retries + 1):
                if provider_calls >= self.max_calls:
                    break
                provider_calls += 1
                attempts += 1
                try:
                    raw = await asyncio.wait_for(
                        self.provider.execute(case.request),
                        timeout=self.timeout_seconds,
                    )
                    break
                except (asyncio.TimeoutError, LLMProviderTimeoutError):
                    last_error = LLMProviderTimeoutError(
                        "Benchmark provider request timed out"
                    )
                    timeouts += 1
                    retryable = True
                except Exception as exc:
                    last_error = exc
                    status = getattr(exc, "status_code", None)
                    if status == 429:
                        rate_limits += 1
                    retryable = (
                        isinstance(exc, LLMProviderNetworkError)
                        or isinstance(exc, LLMProviderHTTPError)
                        and (status == 429 or status is None or status >= 500)
                    )
                if not retryable or attempt >= self.max_retries:
                    break
                retries += 1
                retry_after = getattr(last_error, "retry_after_seconds", 0.0)
                delay = (
                    min(300.0, max(0.0, float(retry_after)))
                    if isinstance(retry_after, (int, float)) else 0.0
                )
                await self.sleeper(delay)
            if raw is None:
                results.append(_failure_result(
                    case, self.provider,
                    last_error or LLMProviderError("Benchmark provider failed"),
                    attempts=attempts, request_bytes=request_bytes,
                    latency_ms=max(0.0, (time.perf_counter() - started) * 1000),
                ))
                continue
            successful += 1
            latency = max(0.0, (time.perf_counter() - started) * 1000)
            parsed, schema_diagnostic = parse_group_advisory_result(raw.content)
            structurally_valid = parsed is not None
            validated = validate_group_advisory_result(case.request, raw.content)
            invalid = bool(validated.validation_reasons)
            declared_inconclusive = raw.content.get("outcome") == "INCONCLUSIVE"
            unsafe_rejected = (
                "PROTECTED_CANNOT_LINK_VIOLATION" in validated.validation_reasons
            )
            usage = raw.usage
            response_bytes = len(json.dumps(
                raw.content, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("utf-8"))
            results.append(GroupBenchmarkCaseResult(
                case_id=case.case_id, source_kind=case.source_kind,
                group_size=case.group_size,
                request_fingerprint=case.request_fingerprint,
                expected_resolution=case.expected_resolution,
                provider_id=self.provider.provider_id,
                model_id=self.provider.provider_model,
                execution_status=(
                    "INVALID_PROVIDER_OUTPUT" if invalid else "SUCCEEDED"
                ),
                attempt_count=attempts, transport_succeeded=True,
                validated_outcome=validated.outcome.value,
                structurally_valid=structurally_valid,
                semantically_valid=not invalid,
                validity_class=("INVALID_REJECTED" if invalid else "VALID"),
                usefulness_class=_usefulness(case, validated, invalid),
                safe_error_code=("SEMANTIC_VALIDATION" if invalid else None),
                safe_error_category=(
                    BenchmarkFailureCategory.SEMANTIC_VALIDATION if invalid else None
                ),
                http_status=None, provider_error_type=None,
                provider_error_code=None,
                safe_error_message=(
                    _SAFE_FAILURE_MESSAGES[BenchmarkFailureCategory.SEMANTIC_VALIDATION]
                    if invalid else None
                ),
                validation_reason_codes=tuple(validated.validation_reasons),
                schema_missing_fields=schema_diagnostic.missing_fields,
                schema_unexpected_fields=schema_diagnostic.unexpected_fields,
                schema_wrong_type_fields=schema_diagnostic.wrong_type_fields,
                schema_invalid_literal_fields=schema_diagnostic.invalid_literal_fields,
                schema_invalid_length_fields=schema_diagnostic.invalid_length_fields,
                schema_invalid_format_fields=schema_diagnostic.invalid_format_fields,
                schema_other_paths=schema_diagnostic.other_schema_paths,
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                latency_ms=latency,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                cache_creation_input_tokens=(
                    usage.cache_creation_input_tokens if usage else None
                ),
                cache_read_input_tokens=(
                    usage.cache_read_input_tokens if usage else None
                ),
                provider_declared_inconclusive=declared_inconclusive,
                invalid_normalized_to_inconclusive=invalid,
                unsafe_cannot_link_rejected=unsafe_rejected,
            ))
        usefulness = {
            item.value: sum(result.usefulness_class == item for result in results)
            for item in BenchmarkUsefulness
        }
        valid_results = [r for r in results if r.validity_class == "VALID"]
        def optional_sum(name):
            values = [
                getattr(result, name) for result in results
                if getattr(result, name) is not None
            ]
            return sum(values) if values else None
        failure_counts = {
            category.value: sum(
                result.safe_error_category == category for result in results
            )
            for category in BenchmarkFailureCategory
        }
        schema_fields = {
            "missing": "schema_missing_fields",
            "unexpected": "schema_unexpected_fields",
            "wrong_type": "schema_wrong_type_fields",
            "invalid_literal": "schema_invalid_literal_fields",
            "invalid_length": "schema_invalid_length_fields",
            "invalid_format": "schema_invalid_format_fields",
            "other": "schema_other_paths",
        }
        schema_mismatch_field_counts = {
            category: {
                path: sum(path in getattr(result, attribute) for result in results)
                for path in sorted({
                    path for result in results for path in getattr(result, attribute)
                })
            }
            for category, attribute in schema_fields.items()
        }
        return GroupBenchmarkReport(
            benchmark_version=GROUP_BENCHMARK_VERSION,
            provider_id=self.provider.provider_id,
            model_id=self.provider.provider_model,
            prompt_contract_version=GROUP_PROMPT_CONTRACT_VERSION,
            request_contract_version=GROUP_ADVISORY_REQUEST_VERSION,
            result_contract_version=GROUP_ADVISORY_RESULT_VERSION,
            total_cases_attempted=len(attempted_cases),
            eligible_production_like_cases=sum(
                c.source_kind != BenchmarkSourceKind.VALIDATOR_SAFETY_CHALLENGE
                for c in attempted_cases
            ),
            safety_challenge_cases=sum(
                c.source_kind == BenchmarkSourceKind.VALIDATOR_SAFETY_CHALLENGE
                for c in attempted_cases
            ),
            provider_calls=provider_calls,
            successful_transport_responses=successful,
            structurally_valid_responses=sum(r.structurally_valid for r in results),
            semantically_valid_responses=len(valid_results),
            normalized_invalid_inconclusive=sum(
                r.invalid_normalized_to_inconclusive for r in results
            ),
            provider_declared_inconclusive=sum(
                r.provider_declared_inconclusive for r in results
            ),
            exact_partition_matches=sum(
                r.usefulness_class == BenchmarkUsefulness.USEFUL_CORRECT
                and r.expected_resolution == BenchmarkExpectedResolution.PARTITION
                for r in results
            ),
            single_identity_matches=sum(
                r.usefulness_class == BenchmarkUsefulness.USEFUL_CORRECT
                and r.expected_resolution == BenchmarkExpectedResolution.SINGLE_IDENTITY
                for r in results
            ),
            wrong_partition_results=sum(
                r.usefulness_class == BenchmarkUsefulness.INCORRECT for r in results
            ),
            unsafe_cannot_link_proposals_rejected=sum(
                r.unsafe_cannot_link_rejected for r in results
            ),
            latency_p50_ms=_percentile([
                r.latency_ms for r in results if r.latency_ms is not None
            ], .5),
            latency_p95_ms=_percentile([
                r.latency_ms for r in results if r.latency_ms is not None
            ], .95),
            retry_count=retries,
            rate_limit_count=rate_limits, timeout_count=timeouts,
            failure_counts=failure_counts,
            schema_mismatch_field_counts=schema_mismatch_field_counts,
            cache_hits=0, cache_misses=len(attempted_cases),
            request_bytes=sum(r.request_bytes for r in results),
            response_bytes=optional_sum("response_bytes"),
            prompt_tokens=optional_sum("prompt_tokens"),
            completion_tokens=optional_sum("completion_tokens"),
            total_tokens=optional_sum("total_tokens"),
            cache_creation_input_tokens=optional_sum("cache_creation_input_tokens"),
            cache_read_input_tokens=optional_sum("cache_read_input_tokens"),
            estimated_cost=None,
            usefulness_counts=usefulness, cases=tuple(results),
        )


def live_group_benchmark_enabled(
    configuration: Settings, *, explicit_live: bool, corpus_selected: bool
) -> bool:
    """No secret access: caller/factory separately validates provider configuration."""
    return bool(
        explicit_live and corpus_selected
        and configuration.group_llm_provider in {"groq", "claude"}
    )


def _curated_request(case_number: int, size: int, *, challenge=False):
    refs = tuple(
        hashlib.sha256(
            f"g7c-case-{case_number}-member-{index}".encode("utf-8")
        ).hexdigest()
        for index in range(size)
    )
    protected = frozenset((refs[0], refs[1])) if challenge else None
    edges = tuple(GroupAdvisoryEdge(
        left_record_ref_key=left, right_record_ref_key=right,
        edge_class=(
            "CANNOT_LINK" if frozenset((left, right)) == protected
            else "REVIEW_SUPPORT"
        ),
        reason_codes=(
            "CRITICAL_MISMATCH_STRUCTURAL_ROLE" if frozenset((left, right)) == protected
            else "DETERMINISTIC_REVIEW_CANDIDATE",
        ),
        evidence_source="G1_LOCAL_RESCORING",
        deterministic_status="POSSIBLE_DUPLICATE_REVIEW",
    ) for left, right in combinations(refs, 2))
    topic = (
        "mapping context" if case_number % 6 == 0 else
        "abbreviation alias" if case_number % 5 == 0 else
        "generic description" if case_number % 4 == 0 else
        "technical identity"
    )
    uoms = tuple(
        ("PCS" if case_number % 6 != 0 or index % 2 else "EA")
        for index in range(size)
    )
    same_uom_pairs = sum(
        uoms[left] == uoms[right] for left, right in combinations(range(size), 2)
    )
    convertible_pairs = len(edges) - same_uom_pairs
    request = GroupAdvisoryRequest(
        contract_version=GROUP_ADVISORY_REQUEST_VERSION,
        scan_id=9000 + case_number, projection_run_id=case_number,
        group_snapshot_id=case_number,
        group_hypothesis_key=hashlib.sha256(
            f"g7c-case-{case_number}".encode("utf-8")
        ).hexdigest(),
        projection_algorithm_version="constrained-group-projection-v1",
        group_status="POSSIBLE_DUPLICATE_GROUP_REVIEW", group_size=size,
        members=tuple(GroupAdvisoryMember(
            record_ref_key=ref, part_no=f"SAFE-{case_number}-{index}",
            normalized_part_no=f"safe {case_number} {index}",
            description=f"Synthetic {topic} component {index}",
            normalized_description=f"synthetic {topic} component {index}",
            site_or_contract="SYNTHETIC", uom=uoms[index],
            product_category="SYNTHETIC", hsn_sac=None,
        ) for index, ref in enumerate(refs)),
        internal_edges=edges,
        group_identity_evidence_summary=GroupIdentityEvidenceSummary(
            strong_support_count=0,
            review_support_count=len(edges) - int(challenge),
            non_groupable_count=0, internal_pair_count=len(edges),
            evidence_completeness=1,
            reason_codes=("DETERMINISTIC_REVIEW_CANDIDATE",),
        ),
        group_uom_mapping_summary=GroupUomMappingSummary(
            distinct_uoms=tuple(sorted(set(uoms))),
            same_uom_pair_count=same_uom_pairs,
            convertible_uom_pair_count=convertible_pairs,
            different_basis_pair_count=0,
            missing_or_wildcard_pair_count=0,
            malformed_or_unknown_pair_count=0,
            possible_mapping_error_count=0, identity_authority=False,
        ),
        unresolved_identity_questions=("DETERMINISTIC_REVIEW_CANDIDATE",),
    )
    return request, refs, (() if protected is None else (tuple(sorted(protected)),))


def curated_group_benchmark_cases() -> tuple[GroupAdvisoryBenchmarkCase, ...]:
    """Thirty documented synthetic labels; never inferred from model/G1 output."""
    cases = []
    # 12 single-identity, 8 partition, 4 hard/abstention, 6 safety challenges.
    sizes = (2, 3, 4, 5, 7, 2, 3, 4, 5, 7) * 3
    safety_notes = (
        "rotor versus stator", "top versus component", "DE versus NDE",
        "inlet versus outlet", "serial versus non-serial",
        "Circuit Board 01 versus Circuit Board 02",
    )
    for index in range(30):
        case_number = index + 1
        challenge = index >= 24
        request, refs, cannot = _curated_request(
            case_number, sizes[index], challenge=challenge
        )
        if index < 12:
            expected = BenchmarkExpectedResolution.SINGLE_IDENTITY
            partitions = (refs,)
            note = "Curated synthetic same-identity alias/mapping case."
        elif index < 20:
            expected = BenchmarkExpectedResolution.PARTITION
            if len(refs) == 5 and index in (13, 18):
                partitions = (
                    (refs[0], refs[1], refs[2], refs[3]), (refs[4],)
                ) if index == 13 else (
                    (refs[0], refs[1]), (refs[2], refs[3]), (refs[4],)
                )
            else:
                split = max(1, len(refs) // 2)
                partitions = (refs[:split], refs[split:])
            note = "Curated synthetic complete partition case."
        elif index < 24:
            expected = BenchmarkExpectedResolution.INCONCLUSIVE_ACCEPTABLE
            partitions = ()
            note = "Curated synthetic generic-description abstention case."
        else:
            expected = BenchmarkExpectedResolution.PARTITION
            partitions = ((refs[0],), tuple(refs[1:]))
            note = f"Validator safety challenge: {safety_notes[index - 24]}."
        cases.append(GroupAdvisoryBenchmarkCase(
            case_id=f"G7C-{case_number:03d}", request=request,
            request_fingerprint=group_advisory_request_fingerprint(request),
            group_size=len(refs), expected_resolution=expected,
            expected_partitions=canonical_partition(partitions),
            protected_cannot_links=cannot,
            source_kind=(
                BenchmarkSourceKind.VALIDATOR_SAFETY_CHALLENGE if challenge
                else BenchmarkSourceKind.CURATED_SYNTHETIC
            ), notes=note,
        ))
    return tuple(cases)
