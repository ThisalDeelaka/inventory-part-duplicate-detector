"""Read-only evidence-strength projection over final identity groups.

This module is intentionally downstream of GF4/GF5.  Nothing in the
deterministic engine imports it, and its output is not part of group identity,
membership, review authority, or request provenance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

from app.identity_read.contracts import (
    IdentityReadGroup,
    IdentityReadProjectionContract,
)


GROUP_EVIDENCE_SCORE_VERSION = "GROUP_EVIDENCE_SCORE_V1"
CREATED_DATE_POLICY = "CREATED_DATE_NOT_IDENTITY_EVIDENCE_V1"


class EvidenceBand(str, Enum):
    HIGH = "HIGH EVIDENCE"
    MODERATE = "MODERATE EVIDENCE"
    LIMITED = "LIMITED EVIDENCE"


class GroupEvidenceScoreInvariantViolation(ValueError):
    """The final group cannot safely receive a normal evidence score."""

    code = "SCORE_INVARIANT_VIOLATION"


@dataclass(frozen=True)
class GroupEvidenceStrength:
    evidence_score: float
    evidence_band: EvidenceBand
    evidence_score_version: str
    possible_relationship_count: int
    strong_relationship_count: int
    review_relationship_count: int
    non_groupable_relationship_count: int
    support_density: float
    strong_support_share: float

    def as_dict(self) -> dict:
        value = asdict(self)
        value["evidence_band"] = self.evidence_band.value
        return value


def evidence_band(score: float) -> EvidenceBand:
    """Assign a band from the unrounded score."""
    if score >= 75.0:
        return EvidenceBand.HIGH
    if score >= 50.0:
        return EvidenceBand.MODERATE
    return EvidenceBand.LIMITED


def score_relationship_counts(
    *,
    member_count: int,
    strong_relationships: int,
    review_relationships: int,
    non_groupable_relationships: int,
    cannot_link_relationships: int = 0,
) -> GroupEvidenceStrength:
    """Apply V1 exactly once to authoritative final-group relationship classes."""
    possible = member_count * (member_count - 1) // 2
    counts = (
        strong_relationships,
        review_relationships,
        non_groupable_relationships,
        cannot_link_relationships,
    )
    if member_count < 2 or possible <= 0 or any(value < 0 for value in counts):
        raise GroupEvidenceScoreInvariantViolation(
            "SCORE_INVARIANT_VIOLATION: invalid group relationship counts"
        )
    if cannot_link_relationships:
        raise GroupEvidenceScoreInvariantViolation(
            "SCORE_INVARIANT_VIOLATION: final group contains CANNOT_LINK"
        )
    if sum(counts) != possible:
        raise GroupEvidenceScoreInvariantViolation(
            "SCORE_INVARIANT_VIOLATION: relationship coverage is incomplete"
        )

    score = 100.0 * (
        strong_relationships + 0.5 * review_relationships
    ) / possible
    supported = strong_relationships + review_relationships
    return GroupEvidenceStrength(
        evidence_score=score,
        evidence_band=evidence_band(score),
        evidence_score_version=GROUP_EVIDENCE_SCORE_VERSION,
        possible_relationship_count=possible,
        strong_relationship_count=strong_relationships,
        review_relationship_count=review_relationships,
        non_groupable_relationship_count=non_groupable_relationships,
        support_density=supported / possible,
        strong_support_share=(strong_relationships / supported if supported else 0.0),
    )


def project_group_evidence_strength(
    group: IdentityReadGroup,
) -> GroupEvidenceStrength | None:
    """Project a score without mutating or fingerprinting the authoritative group.

    G2-v1 read snapshots do not retain authoritative relationship classes, so
    they remain explicitly unscored rather than receiving a fabricated zero.
    """
    if (
        group.versioned_group_key.projection_contract
        == IdentityReadProjectionContract.G2_V1
    ):
        return None
    coverage = group.validation_coverage
    if coverage is None:
        raise GroupEvidenceScoreInvariantViolation(
            "SCORE_INVARIANT_VIOLATION: validation coverage is unavailable"
        )
    if coverage.member_count != group.member_count:
        raise GroupEvidenceScoreInvariantViolation(
            "SCORE_INVARIANT_VIOLATION: member count differs from coverage"
        )
    expected_possible = group.member_count * (group.member_count - 1) // 2
    if coverage.possible_internal_pair_count != expected_possible:
        raise GroupEvidenceScoreInvariantViolation(
            "SCORE_INVARIANT_VIOLATION: possible relationship count drift"
        )
    classified = (
        coverage.strong_support_count
        + coverage.review_support_count
        + coverage.non_groupable_count
        + coverage.cannot_link_count
    )
    if classified != expected_possible:
        # Some historical/progressive snapshots intentionally omit
        # non-required pairs. V1 never invents a relationship class for them.
        return None
    return score_relationship_counts(
        member_count=group.member_count,
        strong_relationships=coverage.strong_support_count,
        review_relationships=coverage.review_support_count,
        non_groupable_relationships=coverage.non_groupable_count,
        cannot_link_relationships=coverage.cannot_link_count,
    )


def evidence_strength_distribution(groups) -> dict[str, int]:
    distribution = {band.value: 0 for band in EvidenceBand}
    for group in groups:
        projection = project_group_evidence_strength(group)
        if projection is not None:
            distribution[projection.evidence_band.value] += 1
    return distribution
