"""Database join for persisted deterministic explanation sources."""

from app.db.models import IdentityEvidenceEdgeSnapshot, IdentityResolutionRun
from app.resolution.pair_explanation import (
    DeterministicPairExplanationV1,
    project_targeted_pair_explanation,
)
from app.services.identity_resolution_service import load_persisted_resolution_result


def load_pair_explanation_sources(
    db, snapshot,
) -> dict[str, DeterministicPairExplanationV1 | object]:
    """Load persisted rich sources without evaluator or network execution."""
    if snapshot.source_resolution_run_id is None:
        return {}
    run = db.get(IdentityResolutionRun, snapshot.source_resolution_run_id)
    if run is None:
        return {}
    needed = {
        item.evidence_fingerprint
        for group in snapshot.groups
        for item in group.internal_evidence
    }
    proposal = db.query(IdentityEvidenceEdgeSnapshot).filter(
        IdentityEvidenceEdgeSnapshot.evidence_run_id == run.evidence_run_id,
        IdentityEvidenceEdgeSnapshot.evidence_fingerprint.in_(needed),
    ).all()
    targeted = load_persisted_resolution_result(
        db, run.id
    ).targeted_evidence_results
    output = {item.evidence_fingerprint: item for item in proposal}
    for result in targeted:
        output.setdefault(
            result.evidence_fingerprint, project_targeted_pair_explanation(result)
        )
    return output
