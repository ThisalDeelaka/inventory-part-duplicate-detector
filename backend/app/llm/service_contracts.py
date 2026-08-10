from enum import Enum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.llm.contracts import (
    CandidateAdvisoryResponse,
    ColumnSuggestionResponse,
    DifficultValueRequest,
    DifficultValueResponse,
    EvidenceText,
    ShortText,
    StrictContract,
)


class LLMCapability(str, Enum):
    COLUMN_SUGGESTION = "column_suggestion"
    DIFFICULT_VALUE = "difficult_value"
    CANDIDATE_ADVISORY = "candidate_advisory"
    CANDIDATE_TRIAGE = "candidate_triage"
    INVENTORY_RECORD_ENRICHMENT = "inventory_record_enrichment"


class LLMExecutionMetadata(StrictContract):
    capability: LLMCapability
    provider: ShortText
    model: Annotated[str, Field(min_length=1, max_length=200)]
    prompt_version: ShortText
    provider_request_id: Annotated[str, Field(max_length=200)] | None = None
    cache_hit: bool
    latency_ms: float = Field(ge=0)
    audit_event_id: Annotated[str, Field(max_length=64)] | None = None
    llm_used: bool
    advisory: Literal[True] = True


class ColumnSuggestionAPIRequest(StrictContract):
    source_column: ShortText
    sample_values: list[Annotated[str, Field(max_length=512)]] = Field(
        min_length=1, max_length=5
    )

    @field_validator("sample_values")
    @classmethod
    def samples_must_include_useful_evidence(cls, values: list[str]) -> list[str]:
        if not any(value.strip() for value in values):
            raise ValueError("sample_values must include non-blank evidence")
        return values


class ColumnSuggestionResult(StrictContract):
    deterministic_bypass: bool
    bypass_reason: ShortText | None = None
    suggestion: ColumnSuggestionResponse | None = None
    metadata: LLMExecutionMetadata


class TechnicalContext(StrictContract):
    normalized_value: Annotated[str, Field(max_length=2048)]
    expanded_value: Annotated[str, Field(max_length=2048)]
    technical_tokens: dict[ShortText, list[ShortText]] = Field(max_length=10)
    variant_attributes: dict[ShortText, list[ShortText]] = Field(max_length=25)
    application_context: list[ShortText] = Field(max_length=10)


class DifficultValuePromptPayload(StrictContract):
    request: DifficultValueRequest
    deterministic_context: TechnicalContext


class DifficultValueResult(StrictContract):
    interpretation: DifficultValueResponse
    metadata: LLMExecutionMetadata


class CandidateGateReason(str, Enum):
    ELIGIBLE_REVIEW_STATUS = "ELIGIBLE_REVIEW_STATUS"
    ELIGIBLE_DATA_CONFLICT = "ELIGIBLE_DATA_CONFLICT"
    ELIGIBLE_AMBIGUOUS_INSUFFICIENT_DATA = "ELIGIBLE_AMBIGUOUS_INSUFFICIENT_DATA"
    INELIGIBLE_CLEAR_DUPLICATE = "INELIGIBLE_CLEAR_DUPLICATE"
    INELIGIBLE_HARD_REJECTION = "INELIGIBLE_HARD_REJECTION"
    INELIGIBLE_CRITICAL_MISMATCH = "INELIGIBLE_CRITICAL_MISMATCH"
    INELIGIBLE_CROSS_SITE = "INELIGIBLE_CROSS_SITE"
    INELIGIBLE_INSUFFICIENT_IDENTITY = "INELIGIBLE_INSUFFICIENT_IDENTITY"
    INELIGIBLE_INVALID_DETERMINISTIC_EVIDENCE = (
        "INELIGIBLE_INVALID_DETERMINISTIC_EVIDENCE"
    )
    INELIGIBLE_STATUS = "INELIGIBLE_STATUS"


class CandidateEligibility(StrictContract):
    eligible: bool
    reason: CandidateGateReason
    explanation: EvidenceText


class CandidateAdvisoryResult(StrictContract):
    candidate_id: int = Field(gt=0)
    eligibility: CandidateEligibility
    advisory: CandidateAdvisoryResponse | None = None
    metadata: LLMExecutionMetadata


class LLMStatusResponse(StrictContract):
    enabled: bool
    provider: ShortText
    model: Annotated[str, Field(min_length=1, max_length=200)]
    provider_configured: bool
    cache_enabled: bool
    cache_count: int = Field(ge=0)
    cache_hits: int = Field(ge=0)
    cache_misses: int = Field(ge=0)
    audit_enabled: bool
    audit_count: int = Field(ge=0)
    prompt_versions: dict[LLMCapability, ShortText]
