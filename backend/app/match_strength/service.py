"""Read-only persisted-evidence resolver for Match Strength V2."""

from __future__ import annotations

from collections import Counter

from app.db.models import IdentityEvidenceEdgeSnapshot
from app.engine.identity_evidence_evaluator import IDENTITY_EVIDENCE_EVALUATOR_VERSION
from app.g2_v2.contracts import G2V2EvidenceOrigin
from app.identity_read.contracts import IdentityReadProjectionContract
from app.match_strength.contracts import (
    MatchBand,
    MatchStrengthEvidence,
    MatchStrengthResult,
    MatchStrengthStatus,
)
from app.match_strength.projection import project_match_strength
from app.resolution.contracts import TARGETED_EVIDENCE_CONTRACT_VERSION


class MatchStrengthProjectionService:
    """Projects from immutable rows and never invokes the deterministic evaluator."""

    def __init__(self, db):
        self.db = db

    def project_groups(self, groups) -> dict[object, MatchStrengthResult]:
        groups = tuple(groups)
        proposal_references = {
            item.evidence_fingerprint
            for group in groups
            for item in group.internal_evidence
            if item.evidence_origin == G2V2EvidenceOrigin.PROPOSAL_EVIDENCE
        }
        proposal_rows = (
            self.db.query(IdentityEvidenceEdgeSnapshot)
            .filter(IdentityEvidenceEdgeSnapshot.evidence_fingerprint.in_(proposal_references))
            .all()
            if proposal_references else []
        )
        proposal_by_fingerprint = {
            row.evidence_fingerprint: row for row in proposal_rows
        }
        return {
            group.versioned_group_key: self._project_group(
                group, proposal_by_fingerprint
            )
            for group in groups
        }

    def project_group(self, group) -> MatchStrengthResult:
        return self.project_groups((group,))[group.versioned_group_key]

    @staticmethod
    def _project_group(group, proposal_by_fingerprint) -> MatchStrengthResult:
        if (
            group.versioned_group_key.projection_contract
            != IdentityReadProjectionContract.G2_V2
        ):
            return project_match_strength(
                tuple(item.stable_record_reference for item in group.members),
                (),
                evidence_snapshot_compatible=False,
            )
        compatible = True
        evidence = []
        for item in group.internal_evidence:
            score = item.deterministic_score
            semantics_verified = False
            if item.evidence_origin == G2V2EvidenceOrigin.PROPOSAL_EVIDENCE:
                source = proposal_by_fingerprint.get(item.evidence_fingerprint)
                if source is not None:
                    score = source.deterministic_score
                    semantics_verified = bool(
                        source.scan_id == group.versioned_group_key.scan_id
                        and source.record_id_1 == item.record_id_1
                        and source.record_id_2 == item.record_id_2
                        and source.edge_class == item.edge_class.value
                        and source.evaluation_algorithm_version
                        == IDENTITY_EVIDENCE_EVALUATOR_VERSION
                    )
                else:
                    compatible = False
            elif item.evidence_origin == G2V2EvidenceOrigin.TARGETED_RESOLUTION_EVIDENCE:
                semantics_verified = bool(
                    item.source_evidence_contract_version
                    == TARGETED_EVIDENCE_CONTRACT_VERSION
                    and item.evaluator_version == IDENTITY_EVIDENCE_EVALUATOR_VERSION
                )
            else:
                compatible = False
            evidence.append(MatchStrengthEvidence(
                member_reference_1=item.stable_record_reference_1,
                member_reference_2=item.stable_record_reference_2,
                edge_class=item.edge_class.value,
                deterministic_score=score,
                score_semantics_verified=semantics_verified,
            ))
        return project_match_strength(
            tuple(item.stable_record_reference for item in group.members),
            tuple(evidence),
            evidence_snapshot_compatible=compatible,
        )


def match_strength_distribution(results) -> dict[str, int]:
    counts = Counter(
        result.match_band.value
        if result.status == MatchStrengthStatus.SCORED
        else "UNSCORED"
        for result in results
    )
    return {
        MatchBand.HIGH_MATCH.value: counts[MatchBand.HIGH_MATCH.value],
        MatchBand.MODERATE_MATCH.value: counts[MatchBand.MODERATE_MATCH.value],
        MatchBand.BORDERLINE_MATCH.value: counts[MatchBand.BORDERLINE_MATCH.value],
        "UNSCORED": counts["UNSCORED"],
    }


def match_strength_payload(result: MatchStrengthResult, *, group_status: str) -> dict:
    crossover = bool(
        result.match_band == MatchBand.HIGH_MATCH
        and group_status == "POSSIBLE_DUPLICATE_GROUP_REVIEW"
    )
    return {
        "match_strength": result.match_strength,
        "match_band": result.match_band.value if result.match_band else None,
        "match_strength_version": result.match_strength_version,
        "match_strength_status": result.status.value,
        "match_strength_unscored_reason": (
            result.unscored_reason.value if result.unscored_reason else None
        ),
        "support_density": result.support_density,
        "lower_quartile_score": result.lower_quartile_score,
        "weakest_member_anchor": result.weakest_member_anchor,
        "pair_score_min": result.pair_score_min,
        "pair_score_median": result.pair_score_median,
        "pair_score_max": result.pair_score_max,
        "safety_status_crossover": crossover,
        "safety_status_message": (
            "High numeric match, but deterministic safety rules require review."
            if crossover else None
        ),
    }
