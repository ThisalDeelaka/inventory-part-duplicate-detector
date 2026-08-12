"""Typed contracts for append-only review of immutable identity groups."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class GroupReviewDecisionType(str, Enum):
    CONFIRM_ALL_AS_ONE = "CONFIRM_ALL_AS_ONE"
    CONFIRM_SELECTED = "CONFIRM_SELECTED"
    SPLIT_PARTITIONS = "SPLIT_PARTITIONS"
    KEEP_ALL_SEPARATE = "KEEP_ALL_SEPARATE"
    UNSURE = "UNSURE"


RecordRefKey = Annotated[str, Field(min_length=64, max_length=64)]


class GroupReviewCreateRequest(BaseModel):
    projection_run_id: int = Field(gt=0)
    group_hypothesis_key: str = Field(min_length=64, max_length=64)
    decision_type: GroupReviewDecisionType
    reviewer: str = Field(min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=2000)
    supersedes_review_event_id: int | None = Field(default=None, gt=0)
    selected_record_ref_keys: list[RecordRefKey] = Field(default_factory=list, max_length=20)
    partitions: list[list[RecordRefKey]] = Field(default_factory=list, max_length=20)

    @field_validator("reviewer")
    @classmethod
    def reviewer_must_be_nonblank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("reviewer must be nonblank")
        return value

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None


class DerivedConstraintCountsResponse(BaseModel):
    must_link_count: int = Field(ge=0)
    cannot_link_count: int = Field(ge=0)


class GroupReviewEventResponse(BaseModel):
    review_event_id: int
    scan_id: int
    projection_run_id: int
    group_snapshot_id: int
    group_hypothesis_key: str
    decision_type: GroupReviewDecisionType
    reviewer: str
    comment: str | None
    created_at: datetime
    supersedes_review_event_id: int | None
    is_current: bool
    partitions: list[list[str]]
    derived_constraint_counts: DerivedConstraintCountsResponse


class GroupReviewHistoryResponse(BaseModel):
    scan_id: int
    group_snapshot_id: int
    current_review_event_id: int | None
    items: list[GroupReviewEventResponse]


class GroupReviewCurrentResponse(BaseModel):
    reviewed: bool
    current_review: GroupReviewEventResponse | None


class GroupReviewStateResponse(BaseModel):
    reviewed: bool = False
    current_decision_type: GroupReviewDecisionType | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    current_review_event_id: int | None = None
