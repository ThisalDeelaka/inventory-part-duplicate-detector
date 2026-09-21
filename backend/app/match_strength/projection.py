"""Pure post-GF5 Match Strength V2 projection.

This module consumes immutable signed relationship evidence. It has no imports
from candidate discovery, GF4 evaluation, GF5 resolution, clocks, randomness,
configuration, persistence, or providers.
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_HALF_EVEN

from app.match_strength.contracts import (
    DETERMINISTIC_MATCH_STRENGTH_V2,
    MatchBand,
    MatchStrengthEvidence,
    MatchStrengthResult,
    MatchStrengthStatus,
    MatchStrengthUnscoredReason,
)


SUPPORTING_EDGE_CLASSES = frozenset({"STRONG_SUPPORT", "REVIEW_SUPPORT"})


def deterministic_percentile(values: tuple[float, ...], fraction: float) -> float:
    """Return the exact linearly interpolated percentile defined by V2."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("percentile fraction must be between zero and one")
    ordered = tuple(sorted(float(value) for value in values))
    position = (len(ordered) - 1) * fraction
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return ordered[lower_index] + weight * (
        ordered[upper_index] - ordered[lower_index]
    )


def canonical_group_score(value: float) -> float:
    """Canonicalize a derived group score to the engine's two-decimal scale."""
    return float(
        Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    )


def match_band(value: float) -> MatchBand:
    """Band the canonical numeric value without consulting signed status."""
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError("Match Strength must be a finite value from 0 through 100")
    if value >= 90.0:
        return MatchBand.HIGH_MATCH
    if value >= 60.0:
        return MatchBand.MODERATE_MATCH
    return MatchBand.BORDERLINE_MATCH


def _unscored(
    *,
    status: MatchStrengthStatus,
    reason: MatchStrengthUnscoredReason,
    member_count: int,
    possible_pairs: int,
    supporting_pairs: int = 0,
) -> MatchStrengthResult:
    return MatchStrengthResult(
        status=status,
        match_strength=None,
        match_band=None,
        match_strength_version=DETERMINISTIC_MATCH_STRENGTH_V2,
        unscored_reason=reason,
        member_count=member_count,
        possible_pair_count=possible_pairs,
        supporting_pair_count=supporting_pairs,
        support_density=None,
        lower_quartile_score=None,
        weakest_member_anchor=None,
        pair_score_min=None,
        pair_score_median=None,
        pair_score_max=None,
        supporting_pair_scores=(),
    )


def project_match_strength(
    member_references: tuple[str, ...],
    evidence: tuple[MatchStrengthEvidence, ...],
    *,
    evidence_snapshot_compatible: bool = True,
) -> MatchStrengthResult:
    """Project one final group without changing or reconstructing pair evidence."""
    members = tuple(member_references)
    member_set = set(members)
    possible_pairs = len(members) * (len(members) - 1) // 2
    if len(members) < 2 or len(member_set) != len(members) or any(not item for item in members):
        return _unscored(
            status=MatchStrengthStatus.INVARIANT_VIOLATION,
            reason=MatchStrengthUnscoredReason.INVALID_GROUP_EVIDENCE,
            member_count=len(members),
            possible_pairs=possible_pairs,
        )
    if not evidence_snapshot_compatible:
        return _unscored(
            status=MatchStrengthStatus.UNSCORED,
            reason=MatchStrengthUnscoredReason.INCOMPATIBLE_EVIDENCE_SNAPSHOT,
            member_count=len(members),
            possible_pairs=possible_pairs,
        )

    by_pair = {}
    for item in evidence:
        pair = tuple(sorted((item.member_reference_1, item.member_reference_2)))
        if (
            item.member_reference_1 == item.member_reference_2
            or not set(pair) <= member_set
            or pair in by_pair
        ):
            return _unscored(
                status=MatchStrengthStatus.INVARIANT_VIOLATION,
                reason=MatchStrengthUnscoredReason.INVALID_GROUP_EVIDENCE,
                member_count=len(members),
                possible_pairs=possible_pairs,
            )
        by_pair[pair] = item

    if any(item.edge_class == "CANNOT_LINK" for item in by_pair.values()):
        return _unscored(
            status=MatchStrengthStatus.INVARIANT_VIOLATION,
            reason=MatchStrengthUnscoredReason.CANNOT_LINK_IN_FINAL_GROUP,
            member_count=len(members),
            possible_pairs=possible_pairs,
        )

    supporting = tuple(
        item for item in by_pair.values()
        if item.edge_class in SUPPORTING_EDGE_CLASSES
    )
    if any(not item.score_semantics_verified for item in supporting):
        return _unscored(
            status=MatchStrengthStatus.UNSCORED,
            reason=MatchStrengthUnscoredReason.UNPROVEN_SCORE_SEMANTICS,
            member_count=len(members),
            possible_pairs=possible_pairs,
            supporting_pairs=len(supporting),
        )
    if any(item.deterministic_score is None for item in supporting):
        return _unscored(
            status=MatchStrengthStatus.UNSCORED,
            reason=MatchStrengthUnscoredReason.MISSING_SUPPORTING_SCORE,
            member_count=len(members),
            possible_pairs=possible_pairs,
            supporting_pairs=len(supporting),
        )
    scores = tuple(float(item.deterministic_score) for item in supporting)
    if any(not math.isfinite(value) or not 0.0 <= value <= 100.0 for value in scores):
        return _unscored(
            status=MatchStrengthStatus.INVARIANT_VIOLATION,
            reason=MatchStrengthUnscoredReason.INVALID_GROUP_EVIDENCE,
            member_count=len(members),
            possible_pairs=possible_pairs,
            supporting_pairs=len(supporting),
        )

    member_best = {}
    for member in members:
        incident = tuple(
            float(item.deterministic_score)
            for item in supporting
            if member in {item.member_reference_1, item.member_reference_2}
        )
        if not incident:
            return _unscored(
                status=MatchStrengthStatus.INVARIANT_VIOLATION,
                reason=MatchStrengthUnscoredReason.MEMBER_WITHOUT_SUPPORT,
                member_count=len(members),
                possible_pairs=possible_pairs,
                supporting_pairs=len(supporting),
            )
        member_best[member] = max(incident)

    density = len(supporting) / possible_pairs
    lower_quartile = deterministic_percentile(scores, 0.25)
    weakest_anchor = min(member_best.values())
    median = deterministic_percentile(scores, 0.5)
    if len(members) == 2:
        if len(supporting) != 1:
            return _unscored(
                status=MatchStrengthStatus.INVARIANT_VIOLATION,
                reason=MatchStrengthUnscoredReason.INVALID_GROUP_EVIDENCE,
                member_count=len(members),
                possible_pairs=possible_pairs,
                supporting_pairs=len(supporting),
            )
        strength = scores[0]
    else:
        strength = canonical_group_score(min(lower_quartile, weakest_anchor) * density)
    return MatchStrengthResult(
        status=MatchStrengthStatus.SCORED,
        match_strength=strength,
        match_band=match_band(strength),
        match_strength_version=DETERMINISTIC_MATCH_STRENGTH_V2,
        unscored_reason=None,
        member_count=len(members),
        possible_pair_count=possible_pairs,
        supporting_pair_count=len(supporting),
        support_density=density,
        lower_quartile_score=lower_quartile,
        weakest_member_anchor=weakest_anchor,
        pair_score_min=min(scores),
        pair_score_median=median,
        pair_score_max=max(scores),
        supporting_pair_scores=tuple(sorted(scores)),
    )
