import json
import time
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.constants import FIELD_ALIASES, FIELD_DEFINITIONS
from app.engine.application_context import extract_application_context
from app.engine.domain_dictionary import (
    expand_domain_tokens,
    normalize_part_no_with_dictionary,
)
from app.engine.normalizer import extract_technical_tokens, normalize_description
from app.engine.variant_extractor import extract_variant_attributes
from app.llm.audit import LLMAuditOutcome, LLMAuditStore
from app.llm.cache import LLMCache
from app.llm.contracts import (
    CandidateAdvisoryRequest,
    CandidateAdvisoryResponse,
    CandidateEvidence,
    ColumnSuggestionRequest,
    ColumnSuggestionResponse,
    CriticalMismatchEvidence,
    DifficultValueFieldContext,
    DifficultValueRequest,
    DifficultValueResponse,
)
from app.llm.exceptions import (
    LLMProviderDisabledError,
    LLMProviderError,
    LLMProviderMalformedJSONError,
    LLMProviderResponseStructureError,
)
from app.llm.prompts import PROMPT_VERSIONS, build_prompts
from app.llm.provider import LLMProvider
from app.llm.service_contracts import (
    CandidateAdvisoryResult,
    CandidateEligibility,
    CandidateGateReason,
    ColumnSuggestionAPIRequest,
    ColumnSuggestionResult,
    DifficultValuePromptPayload,
    DifficultValueResult,
    LLMCapability,
    LLMExecutionMetadata,
    TechnicalContext,
)
from app.services.validation_service import normalize_column_name


ResponseModel = TypeVar("ResponseModel", bound=BaseModel)
ProviderFactory = Callable[[Settings], LLMProvider]


class LLMStructuredOutputError(Exception):
    """Safe public error for capability output that fails strict validation."""


def _bounded_values(values, *, limit: int = 10) -> list[str]:
    return [str(value)[:128] for value in list(values or [])[:limit] if str(value)]


class _CapabilityService:
    def __init__(
        self,
        *,
        configuration: Settings,
        cache: LLMCache,
        audit: LLMAuditStore,
        provider_factory: ProviderFactory,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.configuration = configuration
        self.cache = cache
        self.audit = audit
        self.provider_factory = provider_factory
        self.clock = clock

    @property
    def provider_name(self) -> str:
        return self.configuration.llm_provider

    @property
    def model_name(self) -> str:
        return self.configuration.groq_model

    def _request_hash(
        self, capability: LLMCapability, prompt_version: str, request: dict
    ) -> str:
        return self.cache.build_key(
            capability=capability.value,
            request=request,
            provider=self.provider_name,
            model=self.model_name,
            prompt_version=prompt_version,
        )

    def _audit(self, **fields) -> str | None:
        try:
            event = self.audit.record(**fields)
            return event.event_id if event else None
        except Exception:
            return None

    def _metadata(
        self,
        *,
        capability: LLMCapability,
        prompt_version: str,
        cache_hit: bool,
        latency_ms: float,
        audit_event_id: str | None,
        llm_used: bool,
        provider_request_id: str | None = None,
    ) -> LLMExecutionMetadata:
        return LLMExecutionMetadata(
            capability=capability,
            provider=self.provider_name,
            model=self.model_name,
            prompt_version=prompt_version,
            provider_request_id=provider_request_id,
            cache_hit=cache_hit,
            latency_ms=latency_ms,
            audit_event_id=audit_event_id,
            llm_used=llm_used,
        )

    async def _execute(
        self,
        *,
        capability: LLMCapability,
        payload: BaseModel,
        response_type: type[ResponseModel],
        validator: Callable[[ResponseModel], None] | None = None,
        candidate_id: int | None = None,
    ) -> tuple[ResponseModel, LLMExecutionMetadata]:
        prompt_version = PROMPT_VERSIONS[capability]
        request_data = payload.model_dump(mode="json")
        request_hash = self._request_hash(capability, prompt_version, request_data)
        started = self.clock()

        if not self.configuration.llm_demo_enabled:
            latency = max(0.0, (self.clock() - started) * 1000)
            self._audit(
                capability=capability,
                provider=self.provider_name,
                model=self.model_name,
                prompt_version=prompt_version,
                request_hash=request_hash,
                outcome=LLMAuditOutcome.DISABLED,
                latency_ms=latency,
                cache_hit=False,
                validation_result="not_attempted",
                failure_category="disabled",
                candidate_id=candidate_id,
            )
            raise LLMProviderDisabledError("LLM assistance is disabled")

        cached = self.cache.get(request_hash)
        if cached is not None:
            response = response_type.model_validate(cached)
            if validator:
                validator(response)
            latency = max(0.0, (self.clock() - started) * 1000)
            event_id = self._audit(
                capability=capability,
                provider=self.provider_name,
                model=self.model_name,
                prompt_version=prompt_version,
                request_hash=request_hash,
                outcome=LLMAuditOutcome.CACHE_HIT,
                latency_ms=latency,
                cache_hit=True,
                validation_result="valid",
                candidate_id=candidate_id,
                advisory_assessment=getattr(
                    getattr(response, "assessment", None), "value", None
                ),
            )
            return response, self._metadata(
                capability=capability,
                prompt_version=prompt_version,
                cache_hit=True,
                latency_ms=latency,
                audit_event_id=event_id,
                llm_used=False,
            )

        system_prompt, user_prompt = build_prompts(capability, payload)
        try:
            provider = self.provider_factory(self.configuration)
            provider_result = await provider.complete_json(
                system_prompt=system_prompt, user_prompt=user_prompt
            )
        except (LLMProviderMalformedJSONError, LLMProviderResponseStructureError) as exc:
            latency = max(0.0, (self.clock() - started) * 1000)
            self._audit(
                capability=capability,
                provider=self.provider_name,
                model=self.model_name,
                prompt_version=prompt_version,
                request_hash=request_hash,
                outcome=LLMAuditOutcome.VALIDATION_FAILURE,
                latency_ms=latency,
                cache_hit=False,
                validation_result="invalid",
                failure_category=type(exc).__name__,
                candidate_id=candidate_id,
            )
            raise
        except LLMProviderError as exc:
            latency = max(0.0, (self.clock() - started) * 1000)
            self._audit(
                capability=capability,
                provider=self.provider_name,
                model=self.model_name,
                prompt_version=prompt_version,
                request_hash=request_hash,
                outcome=LLMAuditOutcome.PROVIDER_FAILURE,
                latency_ms=latency,
                cache_hit=False,
                validation_result="not_validated",
                failure_category=type(exc).__name__,
                candidate_id=candidate_id,
            )
            raise

        try:
            response = response_type.model_validate(provider_result.content)
            if validator:
                validator(response)
        except (ValidationError, ValueError):
            latency = max(0.0, (self.clock() - started) * 1000)
            self._audit(
                capability=capability,
                provider=self.provider_name,
                model=self.model_name,
                prompt_version=prompt_version,
                request_hash=request_hash,
                outcome=LLMAuditOutcome.VALIDATION_FAILURE,
                latency_ms=latency,
                cache_hit=False,
                provider_request_id=provider_result.request_id,
                validation_result="invalid",
                failure_category="structured_output",
                candidate_id=candidate_id,
            )
            raise LLMStructuredOutputError(
                "LLM provider output failed capability validation"
            ) from None

        self.cache.set(request_hash, response.model_dump(mode="json"))
        latency = max(0.0, (self.clock() - started) * 1000)
        event_id = self._audit(
            capability=capability,
            provider=self.provider_name,
            model=self.model_name,
            prompt_version=prompt_version,
            request_hash=request_hash,
            outcome=LLMAuditOutcome.SUCCESS,
            latency_ms=latency,
            cache_hit=False,
            provider_request_id=provider_result.request_id,
            validation_result="valid",
            candidate_id=candidate_id,
            advisory_assessment=getattr(
                getattr(response, "assessment", None), "value", None
            ),
        )
        return response, self._metadata(
            capability=capability,
            prompt_version=prompt_version,
            cache_hit=False,
            latency_ms=latency,
            audit_event_id=event_id,
            llm_used=True,
            provider_request_id=provider_result.request_id,
        )


class ColumnSuggestionService(_CapabilityService):
    async def suggest(
        self, request: ColumnSuggestionAPIRequest
    ) -> ColumnSuggestionResult:
        capability = LLMCapability.COLUMN_SUGGESTION
        prompt_version = PROMPT_VERSIONS[capability]
        allowed = sorted(item["field"] for item in FIELD_DEFINITIONS)
        normalized = normalize_column_name(request.source_column)
        deterministic = FIELD_ALIASES.get(normalized, normalized)
        if deterministic in allowed:
            request_hash = self._request_hash(
                capability, prompt_version, request.model_dump(mode="json")
            )
            event_id = self._audit(
                capability=capability,
                provider=self.provider_name,
                model=self.model_name,
                prompt_version=prompt_version,
                request_hash=request_hash,
                outcome=LLMAuditOutcome.INELIGIBLE,
                latency_ms=0,
                cache_hit=False,
                validation_result="not_attempted",
                failure_category="deterministic_header_recognized",
            )
            return ColumnSuggestionResult(
                deterministic_bypass=True,
                bypass_reason="DETERMINISTIC_HEADER_RECOGNIZED",
                metadata=self._metadata(
                    capability=capability,
                    prompt_version=prompt_version,
                    cache_hit=False,
                    latency_ms=0,
                    audit_event_id=event_id,
                    llm_used=False,
                ),
            )

        samples = [value for value in request.sample_values if value.strip()]
        provider_request = ColumnSuggestionRequest(
            source_column=request.source_column,
            sample_values=samples,
            allowed_canonical_fields=allowed,
        )

        def validate(response: ColumnSuggestionResponse) -> None:
            if response.source_column != provider_request.source_column:
                raise ValueError("source column mismatch")
            if (
                response.suggested_canonical_field is not None
                and response.suggested_canonical_field not in allowed
            ):
                raise ValueError("suggestion is outside the canonical allowlist")

        response, metadata = await self._execute(
            capability=capability,
            payload=provider_request,
            response_type=ColumnSuggestionResponse,
            validator=validate,
        )
        return ColumnSuggestionResult(
            deterministic_bypass=False, suggestion=response, metadata=metadata
        )


class DifficultValueInterpretationService(_CapabilityService):
    def build_context(self, request: DifficultValueRequest) -> TechnicalContext:
        raw = request.raw_value
        is_part_number = (
            request.field_context == DifficultValueFieldContext.PART_NO
        )
        normalized = (
            normalize_part_no_with_dictionary(raw)
            if is_part_number
            else normalize_description(raw)
        )
        technical = {
            key: _bounded_values(values)
            for key, values in extract_technical_tokens(raw).items()
        }
        variants = {
            key: _bounded_values(values)
            for key, values in extract_variant_attributes(raw).items()
        }
        contexts = extract_application_context(
            raw if is_part_number else "", "" if is_part_number else raw
        )
        return TechnicalContext(
            normalized_value=normalized[:2048],
            expanded_value=expand_domain_tokens(raw)[:2048],
            technical_tokens=technical,
            variant_attributes=variants,
            application_context=_bounded_values(contexts),
        )

    async def interpret(self, request: DifficultValueRequest) -> DifficultValueResult:
        payload = DifficultValuePromptPayload(
            request=request, deterministic_context=self.build_context(request)
        )

        def validate(response: DifficultValueResponse) -> None:
            if response.raw_value != request.raw_value:
                raise ValueError("raw value mismatch")

        response, metadata = await self._execute(
            capability=LLMCapability.DIFFICULT_VALUE,
            payload=payload,
            response_type=DifficultValueResponse,
            validator=validate,
        )
        return DifficultValueResult(interpretation=response, metadata=metadata)


def _candidate_mismatches(
    candidate,
) -> tuple[list[CriticalMismatchEvidence], bool]:
    try:
        value = json.loads(candidate.critical_mismatches)
        if not isinstance(value, list) or len(value) > 10:
            return [], False
        mismatches = [
            CriticalMismatchEvidence.model_validate(item) for item in value
        ]
    except (TypeError, json.JSONDecodeError, ValidationError):
        return [], False
    return mismatches, True


def candidate_eligibility(candidate) -> CandidateEligibility:
    mismatches, mismatch_evidence_valid = _candidate_mismatches(candidate)
    if not mismatch_evidence_valid:
        return CandidateEligibility(
            eligible=False,
            reason=(
                CandidateGateReason.INELIGIBLE_INVALID_DETERMINISTIC_EVIDENCE
            ),
            explanation=(
                "Stored deterministic mismatch evidence is invalid and cannot "
                "be used for advisory assistance."
            ),
        )
    left_identity = bool(
        str(candidate.part_no_a or "").strip()
        or str(candidate.description_a or "").strip()
    )
    right_identity = bool(
        str(candidate.part_no_b or "").strip()
        or str(candidate.description_b or "").strip()
    )
    if not left_identity or not right_identity:
        return CandidateEligibility(
            eligible=False,
            reason=CandidateGateReason.INELIGIBLE_INSUFFICIENT_IDENTITY,
            explanation="Both candidate sides require part-number or description identity evidence.",
        )
    if (
        candidate.business_status == "LIKELY_DUPLICATE"
        and candidate.confidence_level == "HIGH"
    ):
        return CandidateEligibility(
            eligible=False,
            reason=CandidateGateReason.INELIGIBLE_CLEAR_DUPLICATE,
            explanation="The deterministic result is already a clear high-confidence duplicate.",
        )
    if (
        candidate.business_status == "REJECTED_BY_BUSINESS_RULE"
        or candidate.rule_decision == "REJECT"
    ):
        return CandidateEligibility(
            eligible=False,
            reason=CandidateGateReason.INELIGIBLE_HARD_REJECTION,
            explanation="A deterministic hard rejection cannot be overridden by advisory assistance.",
        )
    if (
        candidate.business_status == "CROSS_SITE_STANDARDIZATION_CANDIDATE"
        or candidate.rule_decision == "CROSS_SITE"
    ):
        return CandidateEligibility(
            eligible=False,
            reason=CandidateGateReason.INELIGIBLE_CROSS_SITE,
            explanation="Cross-site standardization is outside duplicate advisory scope.",
        )
    if (
        candidate.business_status == "RELATED_BUT_NOT_DUPLICATE"
        and mismatches
    ):
        return CandidateEligibility(
            eligible=False,
            reason=CandidateGateReason.INELIGIBLE_CRITICAL_MISMATCH,
            explanation="Deterministic critical mismatch evidence supports non-duplicate status.",
        )
    if candidate.business_status == "POSSIBLE_DUPLICATE_REVIEW":
        return CandidateEligibility(
            eligible=True,
            reason=CandidateGateReason.ELIGIBLE_REVIEW_STATUS,
            explanation="The deterministic result explicitly requires duplicate review.",
        )
    if (
        candidate.business_status == "DATA_CONFLICT_REVIEW"
        and candidate.rule_decision == "DATA_CONFLICT"
    ):
        return CandidateEligibility(
            eligible=True,
            reason=CandidateGateReason.ELIGIBLE_DATA_CONFLICT,
            explanation="The deterministic data conflict remains visible during advisory review.",
        )
    if (
        candidate.business_status == "INSUFFICIENT_DATA"
        and candidate.rule_decision == "DOWNGRADE"
        and candidate.rejection_reason == "GENERIC_DESCRIPTION"
    ):
        return CandidateEligibility(
            eligible=True,
            reason=CandidateGateReason.ELIGIBLE_AMBIGUOUS_INSUFFICIENT_DATA,
            explanation="Generic description evidence creates bounded semantic ambiguity.",
        )
    return CandidateEligibility(
        eligible=False,
        reason=CandidateGateReason.INELIGIBLE_STATUS,
        explanation="The deterministic condition is not allowlisted for LLM advisory.",
    )


def build_candidate_request(candidate) -> CandidateAdvisoryRequest:
    mismatches, mismatch_evidence_valid = _candidate_mismatches(candidate)
    if not mismatch_evidence_valid:
        raise ValueError("stored deterministic mismatch evidence is invalid")
    return CandidateAdvisoryRequest(
        left=CandidateEvidence(
            part_number=candidate.part_no_a or None,
            description=candidate.description_a or None,
            site_or_contract=candidate.contract_a or None,
        ),
        right=CandidateEvidence(
            part_number=candidate.part_no_b or None,
            description=candidate.description_b or None,
            site_or_contract=candidate.contract_b or None,
        ),
        deterministic_score=candidate.similarity_score,
        deterministic_confidence=candidate.confidence_level,
        deterministic_status=candidate.business_status,
        deterministic_rule_decision=candidate.rule_decision,
        rejection_reason=candidate.rejection_reason or None,
        critical_mismatches=mismatches,
    )


class CandidateAdvisoryService(_CapabilityService):
    async def advise(self, candidate) -> CandidateAdvisoryResult:
        capability = LLMCapability.CANDIDATE_ADVISORY
        prompt_version = PROMPT_VERSIONS[capability]
        eligibility = candidate_eligibility(candidate)
        if not eligibility.eligible:
            safe_request = {
                "candidate_id": candidate.id,
                "status": candidate.business_status,
                "rule_decision": candidate.rule_decision,
                "reason": eligibility.reason.value,
            }
            request_hash = self._request_hash(
                capability, prompt_version, safe_request
            )
            event_id = self._audit(
                capability=capability,
                provider=self.provider_name,
                model=self.model_name,
                prompt_version=prompt_version,
                request_hash=request_hash,
                outcome=LLMAuditOutcome.INELIGIBLE,
                latency_ms=0,
                cache_hit=False,
                validation_result="not_attempted",
                failure_category=eligibility.reason.value,
                candidate_id=candidate.id,
            )
            return CandidateAdvisoryResult(
                candidate_id=candidate.id,
                eligibility=eligibility,
                metadata=self._metadata(
                    capability=capability,
                    prompt_version=prompt_version,
                    cache_hit=False,
                    latency_ms=0,
                    audit_event_id=event_id,
                    llm_used=False,
                ),
            )

        request = build_candidate_request(candidate)
        response, metadata = await self._execute(
            capability=capability,
            payload=request,
            response_type=CandidateAdvisoryResponse,
            candidate_id=candidate.id,
        )
        return CandidateAdvisoryResult(
            candidate_id=candidate.id,
            eligibility=eligibility,
            advisory=response,
            metadata=metadata,
        )
