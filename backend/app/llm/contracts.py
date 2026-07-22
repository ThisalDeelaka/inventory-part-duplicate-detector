from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]
EvidenceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)
]
RawText = Annotated[str, Field(min_length=1, max_length=2048)]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnSuggestionRequest(StrictContract):
    source_column: ShortText
    sample_values: list[Annotated[str, Field(max_length=512)]] = Field(
        min_length=1, max_length=5
    )
    allowed_canonical_fields: list[ShortText] = Field(min_length=1, max_length=32)

    @field_validator("source_column")
    @classmethod
    def source_column_must_be_useful(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_column must not be blank")
        return value

    @field_validator("sample_values")
    @classmethod
    def samples_must_include_useful_evidence(cls, values: list[str]) -> list[str]:
        if not any(value.strip() for value in values):
            raise ValueError("sample_values must include non-blank evidence")
        return values

    @field_validator("allowed_canonical_fields")
    @classmethod
    def canonical_fields_must_be_useful(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError(
                "allowed_canonical_fields must not contain blank values"
            )
        return values


class ColumnSuggestionResponse(StrictContract):
    source_column: ShortText
    suggested_canonical_field: ShortText | None
    confidence: float = Field(ge=0, le=1)
    reason: EvidenceText
    requires_confirmation: Literal[True]


class DifficultValueFieldContext(str, Enum):
    PART_NO = "PART_NO"
    DESCRIPTION = "DESCRIPTION"


class DifficultValueRequest(StrictContract):
    raw_value: RawText
    field_context: DifficultValueFieldContext
    item_family_context: ShortText | None = None

    @field_validator("raw_value")
    @classmethod
    def raw_value_must_be_useful(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw_value must not be blank")
        return value


class DifficultValueResponse(StrictContract):
    raw_value: RawText
    normalized_interpretation: Annotated[
        str, Field(min_length=1, max_length=2048)
    ] | None
    attributes: dict[ShortText, EvidenceText] = Field(max_length=20)
    confidence: float = Field(ge=0, le=1)
    warnings: list[EvidenceText] = Field(max_length=10)
    requires_confirmation: Literal[True]


class CandidateEvidence(StrictContract):
    part_number: ShortText | None = None
    description: RawText | None = None
    master_description: RawText | None = None
    uom: ShortText | None = None
    site_or_contract: ShortText | None = None

    @model_validator(mode="after")
    def require_identity_evidence(self) -> "CandidateEvidence":
        identity_values = (
            self.part_number,
            self.description,
            self.master_description,
        )
        if not any(value and value.strip() for value in identity_values):
            raise ValueError(
                "candidate evidence requires a part number or description"
            )
        return self


class DeterministicConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    IGNORE = "IGNORE"


class DeterministicStatus(str, Enum):
    LIKELY_DUPLICATE = "LIKELY_DUPLICATE"
    POSSIBLE_DUPLICATE_REVIEW = "POSSIBLE_DUPLICATE_REVIEW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    REJECTED_BY_BUSINESS_RULE = "REJECTED_BY_BUSINESS_RULE"
    DATA_CONFLICT_REVIEW = "DATA_CONFLICT_REVIEW"
    RELATED_BUT_NOT_DUPLICATE = "RELATED_BUT_NOT_DUPLICATE"
    CROSS_SITE_STANDARDIZATION_CANDIDATE = "CROSS_SITE_STANDARDIZATION_CANDIDATE"


class DeterministicRuleDecision(str, Enum):
    ALLOW = "ALLOW"
    DOWNGRADE = "DOWNGRADE"
    REJECT = "REJECT"
    DATA_CONFLICT = "DATA_CONFLICT"
    CROSS_SITE = "CROSS_SITE"


class CriticalMismatchEvidence(StrictContract):
    group: ShortText
    label: ShortText
    values_a: list[ShortText] = Field(min_length=1, max_length=10)
    values_b: list[ShortText] = Field(min_length=1, max_length=10)


class CandidateAdvisoryRequest(StrictContract):
    left: CandidateEvidence
    right: CandidateEvidence
    deterministic_score: float = Field(ge=0, le=100)
    deterministic_confidence: DeterministicConfidence
    deterministic_status: DeterministicStatus
    deterministic_rule_decision: DeterministicRuleDecision
    rejection_reason: ShortText | None = None
    critical_mismatches: list[CriticalMismatchEvidence] = Field(
        default_factory=list, max_length=10
    )


class AdvisoryAssessment(str, Enum):
    SUPPORTS_DUPLICATE = "SUPPORTS_DUPLICATE"
    SUPPORTS_NON_DUPLICATE = "SUPPORTS_NON_DUPLICATE"
    INCONCLUSIVE = "INCONCLUSIVE"


class AdvisoryRecommendedAction(str, Enum):
    KEEP_DETERMINISTIC_RESULT = "KEEP_DETERMINISTIC_RESULT"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class CandidateAdvisoryResponse(StrictContract):
    assessment: AdvisoryAssessment
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[EvidenceText] = Field(max_length=10)
    conflicting_evidence: list[EvidenceText] = Field(max_length=10)
    recommended_action: AdvisoryRecommendedAction
    deterministic_result_authoritative: Literal[True]
