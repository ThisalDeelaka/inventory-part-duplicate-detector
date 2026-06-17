from dataclasses import dataclass, field
from typing import Any


STATUSES = {
    "DUPLICATE_CANDIDATE",
    "POSSIBLE_DUPLICATE_REVIEW",
    "RELATED_BUT_NOT_DUPLICATE",
    "DATA_CONFLICT_REVIEW",
    "CROSS_SITE_STANDARDIZATION_CANDIDATE",
    "INSUFFICIENT_DATA",
    "UNIQUE_NO_MATCH",
}


@dataclass
class PartRecord:
    part_no: str
    description: str
    contract: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedAttributes:
    normalized_part_no: str
    normalized_description: str
    normalized_text: str = ""
    product_class: list[str] = field(default_factory=list)
    application_context: list[str] = field(default_factory=list)
    function_or_media: list[str] = field(default_factory=list)
    color: list[str] = field(default_factory=list)
    rating: list[str] = field(default_factory=list)
    size: list[str] = field(default_factory=list)
    volume: list[str] = field(default_factory=list)
    type_code: list[str] = field(default_factory=list)
    material: list[str] = field(default_factory=list)
    packaging: list[str] = field(default_factory=list)
    generic_terms: list[str] = field(default_factory=list)
    raw_tokens: list[str] = field(default_factory=list)
    technical_tokens: dict[str, list[str]] = field(default_factory=dict)
    variant_attributes: dict[str, list[str]] = field(default_factory=dict)
    is_generic_description: bool = False


@dataclass
class CandidatePair:
    record_a: PartRecord
    record_b: PartRecord
    matched_fields: list[str] = field(default_factory=list)
    mismatched_fields: list[str] = field(default_factory=list)
    blocking_reason: str = ""


@dataclass
class SimilarityResult:
    overall_similarity: float = 0.0
    tfidf_score: float = 0.0
    fuzzy_score: float = 0.0
    description_similarity: float = 0.0
    master_description_similarity: float = 0.0
    part_no_similarity: float = 0.0
    technical_token_score: float = 0.0
    final_score: float = 0.0
    product_class_match: bool | None = None
    type_code_match: bool | None = None
    rating_match: bool | None = None
    color_match: bool | None = None
    volume_match: bool | None = None
    material_match: bool | None = None
    application_context_match: bool | None = None
    function_or_media_match: bool | None = None
    generic_description_warning: bool = False
    matched_features: list[str] = field(default_factory=list)
    mismatched_features: list[dict] = field(default_factory=list)
    missing_features: list[str] = field(default_factory=list)
    rating_a: list[str] = field(default_factory=list)
    rating_b: list[str] = field(default_factory=list)
    color_a: list[str] = field(default_factory=list)
    color_b: list[str] = field(default_factory=list)
    function_or_media_a: list[str] = field(default_factory=list)
    function_or_media_b: list[str] = field(default_factory=list)
    generic_terms_a: list[str] = field(default_factory=list)
    generic_terms_b: list[str] = field(default_factory=list)


@dataclass
class GuardrailResult:
    triggered: bool = False
    status: str = "POSSIBLE_DUPLICATE_REVIEW"
    rule_decision: str = "ALLOW"
    rejection_reason: str = ""
    score_cap: float | None = None
    explanation: str = ""
    differences: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hard_conflict: bool = False
    data_conflict: bool = False
    review_warning: bool = False
    scope_warning: bool = False
    conflict_types: list[str] = field(default_factory=list)
    warning_types: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    rule_evidence: list[dict] = field(default_factory=list)
    recommended_next_status: str = "POSSIBLE_DUPLICATE_REVIEW"


@dataclass
class DecisionResult:
    status: str
    confidence_score: float
    confidence_level: str
    explanation: str
    matched_evidence: list[str] = field(default_factory=list)
    differences: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rule_decision: str = "ALLOW"
    rejection_reason: str = ""
    normalized_part_no_a: str = ""
    normalized_part_no_b: str = ""
    normalized_description_a: str = ""
    normalized_description_b: str = ""
    extracted_attributes_a: dict[str, Any] = field(default_factory=dict)
    extracted_attributes_b: dict[str, Any] = field(default_factory=dict)


@dataclass
class Evidence:
    matched_fields: list[str] = field(default_factory=list)
    mismatched_fields: list[str] = field(default_factory=list)
    matched_attributes: list[str] = field(default_factory=list)
    differences: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class SimilarityScores:
    tfidf_score: float = 0.0
    fuzzy_score: float = 0.0
    description_similarity: float = 0.0
    part_no_similarity: float = 0.0
    technical_token_score: float = 0.0
    final_score: float = 0.0


@dataclass
class ItemProfile:
    raw: dict
    part_no: str
    description: str
    normalized_part_no: str
    normalized_description: str
    attributes: dict
    application_context: list[str]
    is_generic_description: bool


@dataclass
class Decision:
    status: str
    rule_decision: str
    rejection_reason: str
    score_cap: float | None = None
    explanation: str = ""
    differences: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
