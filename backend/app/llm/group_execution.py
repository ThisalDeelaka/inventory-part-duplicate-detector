"""Provider-neutral, in-memory execution for one eligible G7A group request."""

import asyncio
import copy
import hashlib
import inspect
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import RLock
from typing import Any, Awaitable, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.llm.exceptions import (
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
    GROUP_ADVISORY_RESULT_VERSION,
    GroupAdvisoryOutcome,
    GroupAdvisoryRequest,
    GroupAdvisoryResult,
    canonical_group_advisory_request_json,
    group_advisory_request_fingerprint,
    validate_group_advisory_result,
)
from app.llm.provider import LLMUsageMetadata
from app.services.group_llm_eligibility import (
    GroupAdvisoryContractService,
    GroupLlmEligibilityReason,
    GroupLlmEligibilityResult,
)


GROUP_PROMPT_CONTRACT_VERSION = "group-advisory-prompt-v2"
SUPPORTED_GROUP_PROVIDER_IDS = frozenset({
    "none", "groq", "future:cerebras", "future:groq", "future:ollama",
})


class GroupExecutionStatus(str, Enum):
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    SUCCEEDED = "SUCCEEDED"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    RATE_LIMITED = "RATE_LIMITED"
    TIMED_OUT = "TIMED_OUT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    INVALID_PROVIDER_OUTPUT = "INVALID_PROVIDER_OUTPUT"


class GroupCacheStatus(str, Enum):
    DISABLED = "DISABLED"
    MISS = "MISS"
    HIT = "HIT"


class RawGroupProviderResponse(BaseModel):
    """Transport payload only; central code owns all semantic validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(min_length=1, max_length=80)
    provider_model: str | None = Field(default=None, max_length=200)
    content: dict[str, Any]
    request_id: str | None = Field(default=None, max_length=200)
    usage: LLMUsageMetadata | None = None


class GroupAdvisoryProvider(Protocol):
    """Execute one already-approved whole-group request as one inference unit."""

    provider_id: str
    provider_model: str | None
    enabled: bool

    async def execute(
        self, request: GroupAdvisoryRequest
    ) -> RawGroupProviderResponse:
        ...


class DisabledGroupAdvisoryProvider:
    """Network-free provider used for `none` and unimplemented group capability."""

    provider_id = "none"
    provider_model = None
    enabled = False

    async def execute(
        self, request: GroupAdvisoryRequest
    ) -> RawGroupProviderResponse:
        del request
        raise LLMProviderDisabledError("Group advisory provider is disabled")


class GroupAdvisoryProviderRegistry:
    """Explicit registry; future identities are reserved but not implemented."""

    def __init__(self) -> None:
        self._providers: dict[str, GroupAdvisoryProvider] = {
            "none": DisabledGroupAdvisoryProvider()
        }

    def register(self, provider: GroupAdvisoryProvider) -> None:
        if provider.provider_id not in SUPPORTED_GROUP_PROVIDER_IDS:
            raise ValueError("unsupported group advisory provider identity")
        self._providers[provider.provider_id] = provider

    def resolve(self, provider_id: str) -> GroupAdvisoryProvider:
        if provider_id not in SUPPORTED_GROUP_PROVIDER_IDS:
            raise ValueError("unsupported group advisory provider identity")
        provider = self._providers.get(provider_id)
        if provider is None:
            raise LLMProviderDisabledError(
                "Requested provider has no group advisory capability"
            )
        return provider


def group_advisory_structured_output_schema() -> dict[str, Any]:
    """Derive the provider-visible subset from the authoritative G7A result."""
    schema = copy.deepcopy(GroupAdvisoryResult.model_json_schema())
    properties = schema.get("properties", {})
    for name in ("validation_reasons",):
        properties.pop(name, None)
    schema["required"] = list(properties)
    schema["additionalProperties"] = False
    return schema


@dataclass(frozen=True)
class GroupAdvisoryMessages:
    system_prompt: str
    user_prompt: str
    structured_output_schema: dict[str, Any]


def build_group_advisory_messages(
    request: GroupAdvisoryRequest,
) -> GroupAdvisoryMessages:
    system_prompt = (
        "Assess one bounded candidate identity group as advisory evidence only. "
        "Deterministic cannot-link evidence is non-overridable. UOM and mapping "
        "differences are context, not identity authority. Allowed outcomes are "
        "SUPPORTS_SINGLE_IDENTITY, PROPOSES_PARTITION, or INCONCLUSIVE. Every "
        "answer requires human review; never merge, delete, write back, or "
        "override deterministic or human authority. Return JSON only, with no "
        "markdown, prose outside JSON, or additional fields. The object must "
        "contain exactly: contract_version, request_fingerprint, "
        "group_snapshot_id, group_hypothesis_key, outcome, proposed_partitions, "
        "confidence_band, reason_codes, rationale, mapping_observations, "
        "requires_human_review, and deterministic_result_authoritative. Set "
        f"contract_version to {GROUP_ADVISORY_RESULT_VERSION}; set "
        "requires_human_review=true and deterministic_result_authoritative=true. "
        "For SUPPORTS_SINGLE_IDENTITY, proposed_partitions must be exactly one "
        "array containing every request record_ref_key exactly once. For "
        "PROPOSES_PARTITION, return at least two non-empty arrays and include "
        "every request record_ref_key exactly once across them. For INCONCLUSIVE, "
        "return proposed_partitions as an empty array. Never invent, alter, "
        "shorten, omit, or duplicate a record_ref_key."
    )
    user_prompt = (
        "Evaluate this complete 2..N group as one inference unit. Copy the exact "
        "request_fingerprint, group_snapshot_id, and group_hypothesis_key values "
        "shown below. Do not regenerate, shorten, summarize, hash again, or alter "
        "them.\n"
        f"request_fingerprint={group_advisory_request_fingerprint(request)}\n"
        f"request={canonical_group_advisory_request_json(request)}"
    )
    return GroupAdvisoryMessages(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        structured_output_schema=group_advisory_structured_output_schema(),
    )


def group_execution_key(
    request_fingerprint: str,
    provider_id: str,
    provider_model: str | None,
    prompt_contract_version: str = GROUP_PROMPT_CONTRACT_VERSION,
) -> str:
    canonical = json.dumps({
        "request_fingerprint": request_fingerprint,
        "provider_id": provider_id,
        "provider_model": provider_model,
        "prompt_contract_version": prompt_contract_version,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class GroupAdvisoryCache(Protocol):
    enabled: bool

    def get(self, key: str) -> GroupAdvisoryResult | None:
        ...

    def set(self, key: str, value: GroupAdvisoryResult) -> None:
        ...


class NoOpGroupAdvisoryCache:
    enabled = False

    def get(self, key: str) -> GroupAdvisoryResult | None:
        del key
        return None

    def set(self, key: str, value: GroupAdvisoryResult) -> None:
        del key, value


class InMemoryGroupAdvisoryCache:
    """Process-local test/runtime seam; never stores raw provider output."""

    enabled = True

    def __init__(self, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.max_entries = max_entries
        self._values: dict[str, GroupAdvisoryResult] = {}
        self._order: list[str] = []
        self._lock = RLock()

    def get(self, key: str) -> GroupAdvisoryResult | None:
        with self._lock:
            value = self._values.get(key)
            if value is None:
                return None
            self._order.remove(key)
            self._order.append(key)
            return value.model_copy(deep=True)

    def set(self, key: str, value: GroupAdvisoryResult) -> None:
        if value.validation_reasons:
            raise ValueError("invalid normalized advisory cannot be cached")
        with self._lock:
            if key in self._values:
                self._order.remove(key)
            self._values[key] = value.model_copy(deep=True)
            self._order.append(key)
            while len(self._order) > self.max_entries:
                removed = self._order.pop(0)
                self._values.pop(removed, None)


class GroupCircuitBreaker:
    """Small provider-isolated runtime breaker; no durable or pair state."""

    def __init__(self, failure_threshold: int = 3) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        self.failure_threshold = failure_threshold
        self._failures: dict[str, int] = {}
        self._open: set[str] = set()
        self._lock = RLock()

    def is_open(self, provider_id: str) -> bool:
        with self._lock:
            return provider_id in self._open

    def record_failure(self, provider_id: str) -> None:
        with self._lock:
            count = self._failures.get(provider_id, 0) + 1
            self._failures[provider_id] = count
            if count >= self.failure_threshold:
                self._open.add(provider_id)

    def record_success(self, provider_id: str) -> None:
        with self._lock:
            self._failures.pop(provider_id, None)
            self._open.discard(provider_id)

    def force_open(self, provider_id: str) -> None:
        with self._lock:
            self._open.add(provider_id)


@dataclass(frozen=True)
class GroupExecutionPolicy:
    max_retries: int = 1
    timeout_seconds: float = 30.0
    base_retry_delay_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not 0 <= self.max_retries <= 5:
            raise ValueError("max_retries must be between zero and five")
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be in (0, 300]")
        if not 0 <= self.base_retry_delay_seconds <= 30:
            raise ValueError("retry delay must be in [0, 30]")


@dataclass
class GroupExecutionMetrics:
    eligibility_checks: int = 0
    eligible: int = 0
    ineligible: int = 0
    provider_invocations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    retry_attempts: int = 0
    timeouts: int = 0
    rate_limits: int = 0
    circuit_open: int = 0
    invalid_provider_outputs: int = 0
    successful_validated_advisories: int = 0
    normalized_inconclusive: int = 0


@dataclass(frozen=True)
class GroupAdvisoryExecutionResult:
    execution_status: GroupExecutionStatus
    eligibility: GroupLlmEligibilityResult
    request_fingerprint: str | None
    provider_id: str
    provider_model: str | None
    validated_advisory: GroupAdvisoryResult | None
    attempt_count: int
    cache_status: GroupCacheStatus
    safe_error_code: str | None
    safe_error_message: str | None
    duration_ms: float = field(compare=False)
    provider_request_id: str | None = None
    usage: LLMUsageMetadata | None = None
    response_bytes: int | None = None


def _safe_failure(exc: Exception) -> tuple[str, bool, GroupExecutionStatus]:
    if isinstance(exc, (LLMProviderTimeoutError, asyncio.TimeoutError)):
        return "PROVIDER_TIMEOUT", True, GroupExecutionStatus.TIMED_OUT
    if isinstance(exc, LLMProviderHTTPError) and exc.status_code == 429:
        return "RATE_LIMITED", True, GroupExecutionStatus.RATE_LIMITED
    if isinstance(exc, LLMProviderNetworkError):
        return "NETWORK_FAILURE", True, GroupExecutionStatus.FAILED_RETRYABLE
    if isinstance(exc, LLMProviderHTTPError) and (
        exc.status_code is None or 500 <= exc.status_code <= 599
    ):
        return "PROVIDER_RETRYABLE_FAILURE", True, GroupExecutionStatus.FAILED_RETRYABLE
    if isinstance(exc, (
        LLMProviderMalformedJSONError, LLMProviderResponseStructureError,
        LLMProviderEmptyResponseError,
    )):
        return "INVALID_PROVIDER_OUTPUT", False, GroupExecutionStatus.INVALID_PROVIDER_OUTPUT
    if isinstance(exc, LLMProviderDisabledError):
        return "PROVIDER_DISABLED", False, GroupExecutionStatus.PROVIDER_DISABLED
    if isinstance(exc, LLMProviderError):
        return "PROVIDER_TERMINAL_FAILURE", False, GroupExecutionStatus.FAILED_TERMINAL
    return "PROVIDER_TERMINAL_FAILURE", False, GroupExecutionStatus.FAILED_TERMINAL


class GroupAdvisoryExecutionService:
    """Mandatory G7A gate plus provider-neutral group execution orchestration."""

    def __init__(
        self,
        *,
        contract_service: GroupAdvisoryContractService,
        provider: GroupAdvisoryProvider,
        cache: GroupAdvisoryCache | None = None,
        circuit_breaker: GroupCircuitBreaker | None = None,
        policy: GroupExecutionPolicy | None = None,
        metrics: GroupExecutionMetrics | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.perf_counter,
        pre_invocation_hook: Callable[[], Any] | None = None,
    ) -> None:
        self.contract_service = contract_service
        self.provider = provider
        self.cache = cache or NoOpGroupAdvisoryCache()
        self.circuit_breaker = circuit_breaker or GroupCircuitBreaker()
        self.policy = policy or GroupExecutionPolicy()
        self.metrics = metrics or GroupExecutionMetrics()
        self.sleeper = sleeper
        self.clock = clock
        self.pre_invocation_hook = pre_invocation_hook

    def _result(
        self, started: float, status: GroupExecutionStatus,
        eligibility: GroupLlmEligibilityResult, fingerprint: str | None,
        *, advisory: GroupAdvisoryResult | None = None, attempts: int = 0,
        cache_status: GroupCacheStatus = GroupCacheStatus.DISABLED,
        error_code: str | None = None, error_message: str | None = None,
        provider_request_id: str | None = None,
        usage: LLMUsageMetadata | None = None,
        response_bytes: int | None = None,
    ) -> GroupAdvisoryExecutionResult:
        return GroupAdvisoryExecutionResult(
            execution_status=status, eligibility=eligibility,
            request_fingerprint=fingerprint,
            provider_id=self.provider.provider_id,
            provider_model=self.provider.provider_model,
            validated_advisory=advisory, attempt_count=attempts,
            cache_status=cache_status, safe_error_code=error_code,
            safe_error_message=error_message,
            provider_request_id=provider_request_id, usage=usage,
            response_bytes=response_bytes,
            duration_ms=max(0.0, (self.clock() - started) * 1000),
        )

    async def execute(
        self, scan_id: int, projection_run_id: int, group_snapshot_id: int,
    ) -> GroupAdvisoryExecutionResult:
        started = self.clock()
        self.metrics.eligibility_checks += 1
        eligibility, request = self.contract_service.build_request(
            scan_id, projection_run_id, group_snapshot_id
        )
        if not eligibility.eligible or request is None:
            self.metrics.ineligible += 1
            return self._result(
                started, GroupExecutionStatus.NOT_ELIGIBLE, eligibility, None,
                error_code=eligibility.reason_code.value,
                error_message="Group is not eligible for automatic advisory.",
            )
        self.metrics.eligible += 1
        initial_fingerprint = group_advisory_request_fingerprint(request)

        if not self.provider.enabled:
            return self._result(
                started, GroupExecutionStatus.PROVIDER_DISABLED, eligibility,
                initial_fingerprint, error_code="PROVIDER_DISABLED",
                error_message="Group advisory provider is disabled.",
            )

        if self.pre_invocation_hook is not None:
            hook_result = self.pre_invocation_hook()
            if inspect.isawaitable(hook_result):
                await hook_result

        # Refresh immediately before cache/transport. This is the review-race and
        # immutable-request guard; production callers cannot supply a request
        # directly or bypass the G7A builder.
        self.metrics.eligibility_checks += 1
        guarded_eligibility, guarded_request = self.contract_service.build_request(
            scan_id, projection_run_id, group_snapshot_id
        )
        if not guarded_eligibility.eligible or guarded_request is None:
            self.metrics.ineligible += 1
            return self._result(
                started, GroupExecutionStatus.NOT_ELIGIBLE, guarded_eligibility,
                initial_fingerprint, error_code=guarded_eligibility.reason_code.value,
                error_message="Group eligibility changed before provider invocation.",
            )
        guarded_fingerprint = group_advisory_request_fingerprint(guarded_request)
        if guarded_fingerprint != initial_fingerprint:
            return self._result(
                started, GroupExecutionStatus.FAILED_TERMINAL,
                guarded_eligibility, initial_fingerprint,
                error_code="IMMUTABLE_REQUEST_CHANGED",
                error_message="Immutable group request changed before invocation.",
            )
        request = guarded_request

        if self.circuit_breaker.is_open(self.provider.provider_id):
            self.metrics.circuit_open += 1
            return self._result(
                started, GroupExecutionStatus.CIRCUIT_OPEN, eligibility,
                initial_fingerprint, error_code="CIRCUIT_OPEN",
                error_message="Group advisory provider circuit is open.",
            )

        cache_key = group_execution_key(
            initial_fingerprint, self.provider.provider_id,
            self.provider.provider_model,
        )
        cache_status = GroupCacheStatus.DISABLED
        if self.cache.enabled:
            cached = self.cache.get(cache_key)
            if cached is not None:
                self.metrics.cache_hits += 1
                status = (
                    GroupExecutionStatus.INCONCLUSIVE
                    if cached.outcome == GroupAdvisoryOutcome.INCONCLUSIVE
                    else GroupExecutionStatus.SUCCEEDED
                )
                return self._result(
                    started, status, eligibility, initial_fingerprint,
                    advisory=cached, cache_status=GroupCacheStatus.HIT,
                )
            self.metrics.cache_misses += 1
            cache_status = GroupCacheStatus.MISS

        attempts = 0
        last_status = GroupExecutionStatus.FAILED_TERMINAL
        last_code = "PROVIDER_TERMINAL_FAILURE"
        for attempt in range(self.policy.max_retries + 1):
            attempts += 1
            self.metrics.provider_invocations += 1
            if attempt:
                self.metrics.retry_attempts += 1
            try:
                raw = await asyncio.wait_for(
                    self.provider.execute(request),
                    timeout=self.policy.timeout_seconds,
                )
            except Exception as exc:
                code, retryable, status = _safe_failure(exc)
                last_code, last_status = code, status
                if status == GroupExecutionStatus.TIMED_OUT:
                    self.metrics.timeouts += 1
                if status == GroupExecutionStatus.RATE_LIMITED:
                    self.metrics.rate_limits += 1
                if retryable:
                    self.circuit_breaker.record_failure(self.provider.provider_id)
                if retryable and attempt < self.policy.max_retries:
                    retry_after = getattr(exc, "retry_after_seconds", 0.0)
                    bounded_retry_after = (
                        min(300.0, max(0.0, float(retry_after)))
                        if isinstance(retry_after, (int, float)) else 0.0
                    )
                    delay = max(
                        self.policy.base_retry_delay_seconds * (2 ** attempt),
                        bounded_retry_after,
                    )
                    await self.sleeper(delay)
                    continue
                return self._result(
                    started, last_status, eligibility, initial_fingerprint,
                    attempts=attempts, cache_status=cache_status,
                    error_code=last_code,
                    error_message="Group advisory provider execution failed safely.",
                )

            if (
                raw.provider_id != self.provider.provider_id
                or raw.provider_model != self.provider.provider_model
            ):
                normalized = validate_group_advisory_result(request, {})
                self.metrics.invalid_provider_outputs += 1
                self.metrics.normalized_inconclusive += 1
                return self._result(
                    started, GroupExecutionStatus.INVALID_PROVIDER_OUTPUT,
                    eligibility, initial_fingerprint, advisory=normalized,
                    attempts=attempts, cache_status=cache_status,
                    error_code="PROVIDER_IDENTITY_MISMATCH",
                    error_message="Provider response identity did not match execution.",
                )

            normalized = validate_group_advisory_result(request, raw.content)
            response_bytes = len(json.dumps(
                raw.content, ensure_ascii=True, sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"))
            if normalized.validation_reasons:
                self.metrics.invalid_provider_outputs += 1
                self.metrics.normalized_inconclusive += 1
                return self._result(
                    started, GroupExecutionStatus.INVALID_PROVIDER_OUTPUT,
                    eligibility, initial_fingerprint, advisory=normalized,
                    attempts=attempts, cache_status=cache_status,
                    error_code="INVALID_PROVIDER_OUTPUT",
                    error_message="Provider output failed central group validation.",
                    provider_request_id=raw.request_id, usage=raw.usage,
                    response_bytes=response_bytes,
                )

            self.circuit_breaker.record_success(self.provider.provider_id)
            self.cache.set(cache_key, normalized)
            if normalized.outcome == GroupAdvisoryOutcome.INCONCLUSIVE:
                self.metrics.normalized_inconclusive += 1
                status = GroupExecutionStatus.INCONCLUSIVE
            else:
                self.metrics.successful_validated_advisories += 1
                status = GroupExecutionStatus.SUCCEEDED
            return self._result(
                started, status, eligibility, initial_fingerprint,
                advisory=normalized, attempts=attempts,
                cache_status=cache_status,
                provider_request_id=raw.request_id, usage=raw.usage,
                response_bytes=response_bytes,
            )

        raise AssertionError("bounded group execution retry loop exhausted")
