from dataclasses import dataclass, field


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

