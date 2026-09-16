import pytest

from app.identity_read.group_evidence_strength import (
    CREATED_DATE_POLICY,
    GROUP_EVIDENCE_SCORE_VERSION,
    EvidenceBand,
    GroupEvidenceScoreInvariantViolation,
    evidence_band,
    score_relationship_counts,
)


@pytest.mark.parametrize(
    ("members", "strong", "review", "neutral", "expected"),
    (
        (2, 1, 0, 0, 100.0),
        (2, 0, 1, 0, 50.0),
        (3, 3, 0, 0, 100.0),
        (3, 0, 3, 0, 50.0),
        (4, 3, 3, 0, 75.0),
        (4, 0, 4, 2, 100.0 / 3.0),
    ),
)
def test_v1_formula(members, strong, review, neutral, expected):
    result = score_relationship_counts(
        member_count=members,
        strong_relationships=strong,
        review_relationships=review,
        non_groupable_relationships=neutral,
    )
    assert result.evidence_score == pytest.approx(expected)
    assert result.evidence_score_version == GROUP_EVIDENCE_SCORE_VERSION
    assert result.possible_relationship_count == members * (members - 1) // 2


def test_support_diagnostics():
    result = score_relationship_counts(
        member_count=4,
        strong_relationships=3,
        review_relationships=1,
        non_groupable_relationships=2,
    )
    assert result.support_density == pytest.approx(4 / 6)
    assert result.strong_support_share == pytest.approx(3 / 4)


def test_cannot_link_fails_closed():
    with pytest.raises(
        GroupEvidenceScoreInvariantViolation, match="SCORE_INVARIANT_VIOLATION"
    ):
        score_relationship_counts(
            member_count=2,
            strong_relationships=0,
            review_relationships=0,
            non_groupable_relationships=0,
            cannot_link_relationships=1,
        )


def test_incomplete_relationship_coverage_fails_closed():
    with pytest.raises(
        GroupEvidenceScoreInvariantViolation, match="SCORE_INVARIANT_VIOLATION"
    ):
        score_relationship_counts(
            member_count=3,
            strong_relationships=1,
            review_relationships=1,
            non_groupable_relationships=0,
        )


@pytest.mark.parametrize(
    ("score", "expected"),
    (
        (100.0, EvidenceBand.HIGH),
        (75.0, EvidenceBand.HIGH),
        (74.999999, EvidenceBand.MODERATE),
        (50.0, EvidenceBand.MODERATE),
        (49.999999, EvidenceBand.LIMITED),
        (0.0, EvidenceBand.LIMITED),
    ),
)
def test_band_boundaries_use_unrounded_score(score, expected):
    assert evidence_band(score) == expected


def test_created_date_is_explicitly_outside_v1():
    assert CREATED_DATE_POLICY == "CREATED_DATE_NOT_IDENTITY_EVIDENCE_V1"
    base = score_relationship_counts(
        member_count=2,
        strong_relationships=1,
        review_relationships=0,
        non_groupable_relationships=0,
    )
    # The immutable result has no temporal input or field to alter.
    assert "date" not in " ".join(base.as_dict()).lower()
