"""Provider-free acceptance for targeted pair-explanation evidence persistence."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.benchmarks.acceptance_provenance import request_provenance
from app.benchmarks.match_strength_v2_shadow import (
    approved_csv,
    provider_disabled_configuration,
)
from app.benchmarks.scan_determinism_audit import ScanAudit
from app.db.database import Base
from app.db.models import (
    G2V2ProjectionRun,
    HumanIdentityConstraint,
    IdentityEvidenceEdgeSnapshot,
    IdentityResolutionRun,
)
from app.g2_v2.contracts import G2V2EvidenceOrigin
from app.match_strength.service import MatchStrengthProjectionService
from app.resolution.pair_explanation import (
    PairExplanationAvailability,
    project_proposal_pair_explanation,
    project_targeted_pair_explanation,
)
from app.services.identity_read_service import IdentityReadService
from app.services.identity_resolution_service import load_persisted_resolution_result
from app.services.scan_runner import ScanRunner


MODES = {
    "site_selected": {
        "selected_fields": ["CONTRACT", "UNIT_MEAS"],
        "request_fingerprint": (
            "fab4c9e6de6bad086bd14b4582d16b9ad64ecb2330b7663f2cf7cab5fff3faff"
        ),
        "artifact": "site_selected.acceptance_provenance.json",
    },
    "site_unselected": {
        "selected_fields": ["UNIT_MEAS"],
        "request_fingerprint": (
            "6742e55aeecdd734e7e37875abbcf79f8c8ec8a1531d4c06bca6f3ebed49a85a"
        ),
        "artifact": "site_unselected.acceptance_provenance.json",
    },
}


def _provider_calls(session, scan_id: int) -> int:
    resolution = session.query(IdentityResolutionRun).filter_by(scan_id=scan_id).one()
    return int(resolution.provider_request_count or 0)


def _stages(database: Path, scan_id: int):
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        return {
            item.stage.split("_", 1)[0]: {
                "name": item.stage,
                "count": item.count,
                "sha256": item.fingerprint,
            }
            for item in ScanAudit(connection, scan_id).stages()
        }
    finally:
        connection.close()


def _run_mode(repository_root: Path, records, mode: str, settings: dict) -> dict:
    with tempfile.TemporaryDirectory(
        prefix=f"targeted-pair-explanation-{mode}-"
    ) as directory:
        database = Path(directory) / "acceptance.sqlite3"
        engine = create_engine(
            f"sqlite:///{database.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            scan, _ = ScanRunner(
                session, provider_disabled_configuration()
            ).run(
                records,
                f"Targeted explanation acceptance: {mode}",
                settings["selected_fields"],
                75.0,
                source_type="CANONICAL_DB_SNAPSHOT",
                sensitive_mode=True,
                scan_mode="SAME_SITE_DUPLICATE",
            )
            snapshot = IdentityReadService(session).load_identity_read_snapshot(scan.id)
            resolution = session.query(IdentityResolutionRun).filter_by(
                scan_id=scan.id
            ).one()
            projection = session.query(G2V2ProjectionRun).filter_by(
                scan_id=scan.id
            ).one()
            persisted = load_persisted_resolution_result(session, resolution.id)
            targeted = {
                item.evidence_fingerprint: item
                for item in persisted.targeted_evidence_results
            }
            proposal_references = {
                item.evidence_fingerprint
                for group in snapshot.groups
                for item in group.internal_evidence
                if item.evidence_origin == G2V2EvidenceOrigin.PROPOSAL_EVIDENCE
            }
            proposal_rows = session.query(IdentityEvidenceEdgeSnapshot).filter(
                IdentityEvidenceEdgeSnapshot.evidence_fingerprint.in_(
                    proposal_references
                )
            ).all()
            proposals = {item.evidence_fingerprint: item for item in proposal_rows}

            coverage = Counter()
            by_origin = Counter()
            group_complete = {}
            relationship_count = 0
            for group in snapshot.groups:
                complete = True
                for item in group.internal_evidence:
                    relationship_count += 1
                    if item.evidence_origin == G2V2EvidenceOrigin.PROPOSAL_EVIDENCE:
                        source = proposals.get(item.evidence_fingerprint)
                        if source is None:
                            availability = "UNKNOWN"
                        else:
                            explanation = project_proposal_pair_explanation(
                                source,
                                record_reference_1=item.stable_record_reference_1,
                                record_reference_2=item.stable_record_reference_2,
                            )
                            availability = explanation.availability.value
                        by_origin[f"PROPOSAL_{availability}"] += 1
                    else:
                        source = targeted.get(item.evidence_fingerprint)
                        if source is None:
                            availability = "UNKNOWN"
                        else:
                            explanation = project_targeted_pair_explanation(source)
                            availability = explanation.availability.value
                        by_origin[f"TARGETED_{availability}"] += 1
                    coverage[availability] += 1
                    complete = complete and (
                        availability == PairExplanationAvailability.COMPLETE.value
                    )
                group_complete[group.versioned_group_key] = complete

            strengths = MatchStrengthProjectionService(session).project_groups(
                snapshot.groups
            )
            bands = Counter(
                result.match_band.value if result.match_band else "UNSCORED"
                for result in strengths.values()
            )
            crossovers = [
                group
                for group in snapshot.groups
                if group.status.value == "POSSIBLE_DUPLICATE_GROUP_REVIEW"
                and strengths[group.versioned_group_key].match_band is not None
                and strengths[group.versioned_group_key].match_band.value == "HIGH_MATCH"
            ]
            exact_crossover = sum(
                bool([
                    item
                    for item in group.internal_evidence
                    if item.edge_class.value == "REVIEW_SUPPORT"
                    and item.reason_codes
                ])
                for group in crossovers
            )
            current_stages = _stages(database, scan.id)
            baseline = json.loads((
                repository_root
                / "artifacts"
                / "request_scoped_site_constraint"
                / settings["artifact"]
            ).read_text(encoding="utf-8"))
            stage_matches = {
                key: current_stages[key] == baseline["semantic_fingerprints"][key]
                for key in current_stages
            }
            cross_site_groups = sum(
                len({member.contract for member in group.members}) > 1
                for group in snapshot.groups
            )
            request = request_provenance(
                scan_mode="SAME_SITE_DUPLICATE",
                selected_fields=settings["selected_fields"],
                threshold=75.0,
                candidate_mode="group_first_primary",
                sensitive_mode=True,
                source_type="CANONICAL_DB_SNAPSHOT",
                feature_flags={
                    "hybrid_retrieval_enabled": True,
                    "local_embedding_enabled": True,
                },
                semantic_options={
                    "identity_discovery_mode": "DISCOVERY",
                    "visible_projection_contract": "G2_V2",
                },
            )
            result = {
                "request_fingerprint": request["sha256"],
                "request_fingerprint_matches": (
                    request["sha256"] == settings["request_fingerprint"]
                ),
                "detector_counts": {
                    "records": resolution.source_record_count,
                    "groups": resolution.accepted_group_count,
                    "stronger": resolution.likely_group_count,
                    "review": resolution.review_group_count,
                    "conflicts": resolution.conflict_count,
                    "deferred": resolution.deferred_work_unit_count,
                    "grouped_records": (
                        projection.canonical_record_count
                        - projection.unassigned_record_count
                    ),
                    "unassigned": resolution.unassigned_record_count,
                    "cross_site_groups": cross_site_groups,
                    "provider_calls": _provider_calls(session, scan.id),
                    "human_constraints": session.query(
                        HumanIdentityConstraint
                    ).count(),
                },
                "match_strength": {
                    "scored": len(strengths) - bands["UNSCORED"],
                    "unscored": bands["UNSCORED"],
                    "high": bands["HIGH_MATCH"],
                    "moderate": bands["MODERATE_MATCH"],
                    "borderline": bands["BORDERLINE_MATCH"],
                },
                "explanation_coverage": {
                    "relationships": relationship_count,
                    "full": coverage["COMPLETE"],
                    "partial": coverage["PARTIAL_LEGACY"],
                    "generic_only": 0,
                    "requires_rerun": 0,
                    "unknown": coverage["UNKNOWN"],
                    "by_origin": dict(sorted(by_origin.items())),
                    "two_member_groups_full": sum(
                        group.member_count == 2
                        and group_complete[group.versioned_group_key]
                        for group in snapshot.groups
                    ),
                    "two_member_groups_total": sum(
                        group.member_count == 2 for group in snapshot.groups
                    ),
                    "multi_member_groups_full": sum(
                        group.member_count >= 3
                        and group_complete[group.versioned_group_key]
                        for group in snapshot.groups
                    ),
                    "multi_member_groups_total": sum(
                        group.member_count >= 3 for group in snapshot.groups
                    ),
                },
                "crossover_reason_coverage": {
                    "groups": len(crossovers),
                    "exact": exact_crossover,
                    "partial": len(crossovers) - exact_crossover,
                    "generic_only": 0,
                },
                "semantic_stage_matches": stage_matches,
                "semantic_fingerprints": current_stages,
            }
        finally:
            session.close()
            engine.dispose()
    return result


def run_acceptance(repository_root: Path) -> dict:
    records = approved_csv(repository_root)
    result = {"contract": "targeted-pair-explanation-acceptance-v1"}
    for mode, settings in MODES.items():
        result[mode] = _run_mode(repository_root, records, mode, settings)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_acceptance(args.repository_root.resolve())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
