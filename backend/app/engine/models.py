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
    technical_tokens: dict[str, list[str]] = field(default_factory=dict)
    variant_attributes: dict[str, list[str]] = field(default_factory=dict)
    application_context: list[str] = field(default_factory=list)
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
    tfidf_score: float = 0.0
    fuzzy_score: float = 0.0
    description_similarity: float = 0.0
    part_no_similarity: float = 0.0
    technical_token_score: float = 0.0
    final_score: float = 0.0


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
