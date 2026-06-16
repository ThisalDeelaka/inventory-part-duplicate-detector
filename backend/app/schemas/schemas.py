from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    user_decision: str = Field(pattern="^(DUPLICATE|NOT_DUPLICATE|UNSURE)$")
    user_comment: str | None = None
    created_by: str = "demo-reviewer"


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    candidate_id: int
    user_decision: str
    user_comment: str | None
    created_by: str
    created_at: datetime


class LoadTestRequest(BaseModel):
    record_count: int = Field(default=500, ge=10, le=20000)
    duplicate_rate: float = Field(default=0.15, ge=0, le=0.8)
    variation_rate: float = Field(default=0.3, ge=0, le=1)
    threshold: float = Field(default=70, ge=0, le=100)


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scan_id: int
    contract_a: str | None
    part_no_a: str
    description_a: str
    contract_b: str | None
    part_no_b: str
    description_b: str
    similarity_score: float
    confidence_level: str
    description_similarity: float
    tfidf_score: float
    fuzzy_score: float
    part_no_similarity: float
    technical_token_score: float
    matched_fields: list[str]
    mismatched_fields: list[str]
    explanation: str
    recommended_action: str
    review_status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
