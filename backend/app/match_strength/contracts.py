"""Typed persistence-neutral contracts for Match Strength V2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


DETERMINISTIC_MATCH_STRENGTH_V2 = "DETERMINISTIC_MATCH_STRENGTH_V2"


class MatchBand(str, Enum):
    HIGH_MATCH = "HIGH_MATCH"
    MODERATE_MATCH = "MODERATE_MATCH"
    BORDERLINE_MATCH = "BORDERLINE_MATCH"


class MatchStrengthStatus(str, Enum):
    SCORED = "SCORED"
    UNSCORED = "UNSCORED"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"


class MatchStrengthUnscoredReason(str, Enum):
    MISSING_SUPPORTING_SCORE = "MISSING_SUPPORTING_SCORE"
    UNPROVEN_SCORE_SEMANTICS = "UNPROVEN_SCORE_SEMANTICS"
    INCOMPATIBLE_EVIDENCE_SNAPSHOT = "INCOMPATIBLE_EVIDENCE_SNAPSHOT"
    CANNOT_LINK_IN_FINAL_GROUP = "CANNOT_LINK_IN_FINAL_GROUP"
    MEMBER_WITHOUT_SUPPORT = "MEMBER_WITHOUT_SUPPORT"
    INVALID_GROUP_EVIDENCE = "INVALID_GROUP_EVIDENCE"


@dataclass(frozen=True)
class MatchStrengthEvidence:
    member_reference_1: str
    member_reference_2: str
    edge_class: str
    deterministic_score: float | None
    score_semantics_verified: bool


@dataclass(frozen=True)
class MatchStrengthResult:
    status: MatchStrengthStatus
    match_strength: float | None
    match_band: MatchBand | None
    match_strength_version: str
    unscored_reason: MatchStrengthUnscoredReason | None
    member_count: int
    possible_pair_count: int
    supporting_pair_count: int
    support_density: float | None
    lower_quartile_score: float | None
    weakest_member_anchor: float | None
    pair_score_min: float | None
    pair_score_median: float | None
    pair_score_max: float | None
    supporting_pair_scores: tuple[float, ...]

    @property
    def scored(self) -> bool:
        return self.status == MatchStrengthStatus.SCORED
