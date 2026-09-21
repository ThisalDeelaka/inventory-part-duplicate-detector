from app.match_strength import (
    DETERMINISTIC_MATCH_STRENGTH_V2,
    MatchBand,
    MatchStrengthEvidence,
    MatchStrengthStatus,
    MatchStrengthUnscoredReason,
    project_match_strength,
)
from app.match_strength.projection import deterministic_percentile, match_band


def edge(left, right, score, edge_class="REVIEW_SUPPORT", verified=True):
    return MatchStrengthEvidence(left, right, edge_class, score, verified)


def test_two_member_group_uses_direct_score_without_category_mapping():
    result = project_match_strength(("a", "b"), (edge("a", "b", 78.25),))
    assert result.status == MatchStrengthStatus.SCORED
    assert result.match_strength == 78.25
    assert result.match_band == MatchBand.MODERATE_MATCH
    assert result.match_strength_version == DETERMINISTIC_MATCH_STRENGTH_V2


def test_triangle_uses_exact_p25_and_weakest_member_formula():
    evidence = (
        edge("a", "b", 65.0),
        edge("a", "c", 94.41, "STRONG_SUPPORT"),
        edge("b", "c", 94.47, "STRONG_SUPPORT"),
    )
    result = project_match_strength(("a", "b", "c"), evidence)
    assert deterministic_percentile((65.0, 94.41, 94.47), 0.25) == 79.705
    assert result.lower_quartile_score == 79.705
    assert result.weakest_member_anchor == 94.41
    assert result.support_density == 1.0
    assert result.match_strength == 79.7


def test_weakest_member_anchor_can_control_larger_group():
    evidence = (
        edge("a", "b", 99.0, "STRONG_SUPPORT"),
        edge("a", "c", 98.0, "STRONG_SUPPORT"),
        edge("b", "c", 97.0, "STRONG_SUPPORT"),
        edge("a", "d", 70.0),
        edge("b", "d", None, "NON_GROUPABLE", False),
        edge("c", "d", None, "NON_GROUPABLE", False),
    )
    result = project_match_strength(("a", "b", "c", "d"), evidence)
    assert result.lower_quartile_score == 90.25
    assert result.weakest_member_anchor == 70.0
    assert result.support_density == 4 / 6
    assert result.match_strength == 46.67


def test_incomplete_pairwise_density_penalizes_without_changing_pair_scores():
    evidence = (
        edge("a", "b", 90.0, "STRONG_SUPPORT"),
        edge("a", "c", 90.0, "STRONG_SUPPORT"),
        edge("b", "c", None, "NON_GROUPABLE", False),
    )
    result = project_match_strength(("a", "b", "c"), evidence)
    assert result.support_density == 2 / 3
    assert result.match_strength == 60.0
    assert result.match_band == MatchBand.MODERATE_MATCH


def test_missing_supporting_score_is_unscored_not_zero():
    result = project_match_strength(("a", "b"), (edge("a", "b", None),))
    assert result.status == MatchStrengthStatus.UNSCORED
    assert result.unscored_reason == MatchStrengthUnscoredReason.MISSING_SUPPORTING_SCORE
    assert result.match_strength is None


def test_unproven_score_semantics_is_unscored():
    result = project_match_strength(("a", "b"), (edge("a", "b", 80.0, verified=False),))
    assert result.status == MatchStrengthStatus.UNSCORED
    assert result.unscored_reason == MatchStrengthUnscoredReason.UNPROVEN_SCORE_SEMANTICS


def test_cannot_link_and_member_without_support_are_invariant_violations():
    cannot = project_match_strength(
        ("a", "b"), (edge("a", "b", 45.0, "CANNOT_LINK"),)
    )
    assert cannot.status == MatchStrengthStatus.INVARIANT_VIOLATION
    assert cannot.unscored_reason == MatchStrengthUnscoredReason.CANNOT_LINK_IN_FINAL_GROUP
    detached = project_match_strength(
        ("a", "b", "c"), (edge("a", "b", 80.0),)
    )
    assert detached.status == MatchStrengthStatus.INVARIANT_VIOLATION
    assert detached.unscored_reason == MatchStrengthUnscoredReason.MEMBER_WITHOUT_SUPPORT


def test_band_boundaries_and_high_review_crossover_do_not_silently_cap():
    expected = (
        (100.0, MatchBand.HIGH_MATCH), (90.0, MatchBand.HIGH_MATCH),
        (89.99, MatchBand.MODERATE_MATCH), (60.0, MatchBand.MODERATE_MATCH),
        (59.99, MatchBand.BORDERLINE_MATCH), (0.0, MatchBand.BORDERLINE_MATCH),
    )
    assert tuple((value, match_band(value)) for value, _band in expected) == expected
    review = project_match_strength(("a", "b"), (edge("a", "b", 99.23),))
    assert review.match_strength == 99.23
    assert review.match_band == MatchBand.HIGH_MATCH
