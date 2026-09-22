"""Provider-free real-data shadow validation for Match Strength V2."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import statistics
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.benchmarks.acceptance_provenance import request_provenance
from app.benchmarks.scan_determinism_audit import ScanAudit
from app.db.database import Base
from app.db.models import (
    G2V2ProjectionRun,
    HybridRetrievalRun,
    IdentityDiscoveryRun,
    IdentityResolutionRun,
)
from app.match_strength.contracts import MatchStrengthStatus
from app.match_strength.projection import deterministic_percentile
from app.match_strength.service import MatchStrengthProjectionService
from app.services.identity_read_service import IdentityReadService
from app.services.scan_runner import ScanRunner
from app.services.validation_service import apply_column_mapping


SAFE_CSV_OBJECT = "f6889ef3b05cee89369af232a8344aff12f969a7:data/List_20260709_093045.csv"
SAFE_CSV_SHA256 = "8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b"
EXPECTED_REQUEST_FINGERPRINT = "fab4c9e6de6bad086bd14b4582d16b9ad64ecb2330b7663f2cf7cab5fff3faff"


def provider_disabled_configuration():
    return SimpleNamespace(
        identity_orchestration_mode="group_first_primary",
        group_first_shadow_comparison_enabled=False,
        hybrid_retrieval_enabled=True,
        hybrid_retrieval_lexical_top_k=5,
        hybrid_retrieval_vector_top_k=5,
        hybrid_retrieval_final_top_k=10,
        hybrid_retrieval_min_score=55.0,
        hybrid_retrieval_max_pairs_per_scan=500,
        hybrid_retrieval_tier_a_max=250,
        hybrid_retrieval_tier_b_max=200,
        hybrid_retrieval_tier_c_max=50,
        hybrid_retrieval_family_max=25,
        local_embedding_enabled=True,
        local_embedding_model="sklearn-hashing-domain-v1",
        identity_neighborhood_max_members=20,
        llm_demo_enabled=False,
        llm_provider="none",
        group_llm_provider="none",
        groq_api_key="",
        anthropic_api_key="",
    )


def approved_csv(repository_root: Path) -> pd.DataFrame:
    result = subprocess.run(
        ("git", "-C", str(repository_root), "cat-file", "blob", SAFE_CSV_OBJECT),
        check=True,
        capture_output=True,
    )
    if hashlib.sha256(result.stdout).hexdigest() != SAFE_CSV_SHA256:
        raise ValueError("approved CSV Git blob differs from its frozen SHA-256")
    source = pd.read_csv(io.BytesIO(result.stdout), low_memory=False)
    records, metadata = apply_column_mapping(source, {})
    if metadata["column_mapping_conflicts"]:
        raise ValueError("approved CSV has ambiguous column mappings")
    return records


def _distribution(values):
    values = tuple(float(value) for value in values)
    counts = Counter(values)
    modal_count = max(counts.values()) if counts else 0
    mode = min((value for value, count in counts.items() if count == modal_count), default=None)
    return {
        "count": len(values),
        "unique": len(counts),
        "minimum": min(values) if values else None,
        "p10": deterministic_percentile(values, 0.10) if values else None,
        "p25": deterministic_percentile(values, 0.25) if values else None,
        "median": deterministic_percentile(values, 0.50) if values else None,
        "p75": deterministic_percentile(values, 0.75) if values else None,
        "p90": deterministic_percentile(values, 0.90) if values else None,
        "maximum": max(values) if values else None,
        "mean": statistics.fmean(values) if values else None,
        "mode": mode,
        "mode_percentage": 100.0 * modal_count / len(values) if values else None,
    }


def _group_row(group, result):
    return {
        "group_id": group.versioned_group_key.group_reference,
        "size": group.member_count,
        "match_strength": result.match_strength,
        "band": result.match_band.value if result.match_band else None,
        "status": result.status.value,
        "unscored_reason": result.unscored_reason.value if result.unscored_reason else None,
        "existing_tier": group.status.value,
        "support_density": result.support_density,
        "p25": result.lower_quartile_score,
        "weakest_member_anchor": result.weakest_member_anchor,
        "base_strength": (
            min(result.lower_quartile_score, result.weakest_member_anchor)
            if result.lower_quartile_score is not None
            and result.weakest_member_anchor is not None else None
        ),
        "pair_score_min": result.pair_score_min,
        "pair_score_median": result.pair_score_median,
        "pair_score_max": result.pair_score_max,
        "supporting_pair_scores": list(result.supporting_pair_scores),
    }


def _boundary(rows, key, count=10):
    return sorted(rows, key=key)[:count]


def _provider_calls(session, scan_id):
    discovery = session.query(IdentityDiscoveryRun).filter_by(scan_id=scan_id).one()
    resolution = session.query(IdentityResolutionRun).filter_by(scan_id=scan_id).one()
    hybrid = session.query(HybridRetrievalRun).filter_by(scan_id=scan_id).one_or_none()
    return sum((
        int(discovery.provider_request_count or 0),
        int(resolution.provider_request_count or 0),
        int(hybrid.provider_request_count or 0) if hybrid else 0,
    ))


def run_shadow(repository_root: Path) -> dict:
    records = approved_csv(repository_root)
    with tempfile.TemporaryDirectory(prefix="match-strength-v2-shadow-") as directory:
        db_path = Path(directory) / "shadow.sqlite3"
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            scan, _ = ScanRunner(session, provider_disabled_configuration()).run(
                records,
                "Match Strength V2 shadow validation",
                ["CONTRACT", "UNIT_MEAS"],
                75.0,
                source_type="CANONICAL_DB_SNAPSHOT",
                sensitive_mode=True,
                scan_mode="SAME_SITE_DUPLICATE",
            )
            snapshot = IdentityReadService(session).load_identity_read_snapshot(scan.id)
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            try:
                before = ScanAudit(connection, scan.id).stages()
            finally:
                connection.close()
            projections = MatchStrengthProjectionService(session).project_groups(snapshot.groups)
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row
            try:
                after = ScanAudit(connection, scan.id).stages()
            finally:
                connection.close()
            if before != after:
                raise ValueError("Match Strength projection changed S0-S10 semantics")

            rows = [
                _group_row(group, projections[group.versioned_group_key])
                for group in snapshot.groups
            ]
            scored = [row for row in rows if row["status"] == MatchStrengthStatus.SCORED.value]
            unscored = [row for row in rows if row["status"] != MatchStrengthStatus.SCORED.value]
            multi = [row for row in rows if row["size"] >= 3]
            bands = Counter(row["band"] for row in scored)
            tier_band = defaultdict(Counter)
            for row in rows:
                tier_band[row["existing_tier"]][row["band"] or "UNSCORED"] += 1
            values = [row["match_strength"] for row in scored]
            two = [row for row in rows if row["size"] == 2]
            two_values = [row["match_strength"] for row in two if row["match_strength"] is not None]
            resolution = session.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
            projection = session.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one()
            result = {
                "request_fingerprint": EXPECTED_REQUEST_FINGERPRINT,
                "detector_counts": {
                    "records": resolution.source_record_count,
                    "groups": resolution.accepted_group_count,
                    "stronger": resolution.likely_group_count,
                    "review": resolution.review_group_count,
                    "conflicts": resolution.conflict_count,
                    "deferred": resolution.deferred_work_unit_count,
                    "grouped_records": projection.canonical_record_count
                    - projection.unassigned_record_count,
                    "unassigned": resolution.unassigned_record_count,
                    "cross_site_groups": sum(
                        len({item.contract for item in group.members}) > 1
                        for group in snapshot.groups
                    ),
                    "provider_calls": _provider_calls(session, scan.id),
                },
                "coverage": {
                    "scored_groups": len(scored),
                    "unscored_groups": len(unscored),
                    "two_member_scored": sum(row["match_strength"] is not None for row in two),
                    "two_member_unscored": sum(row["match_strength"] is None for row in two),
                    "three_member_scored": sum(row["size"] == 3 and row["match_strength"] is not None for row in rows),
                    "three_member_unscored": sum(row["size"] == 3 and row["match_strength"] is None for row in rows),
                    "four_plus_scored": sum(row["size"] >= 4 and row["match_strength"] is not None for row in rows),
                    "four_plus_unscored": sum(row["size"] >= 4 and row["match_strength"] is None for row in rows),
                },
                "distribution": _distribution(values),
                "band_counts": {
                    "HIGH_MATCH": bands["HIGH_MATCH"],
                    "MODERATE_MATCH": bands["MODERATE_MATCH"],
                    "BORDERLINE_MATCH": bands["BORDERLINE_MATCH"],
                    "UNSCORED": len(unscored),
                },
                "tier_band_cross_tab": {
                    tier: {
                        band: counts[band]
                        for band in ("HIGH_MATCH", "MODERATE_MATCH", "BORDERLINE_MATCH", "UNSCORED")
                    }
                    for tier, counts in sorted(tier_band.items())
                },
                "two_member_distribution": _distribution(two_values),
                "multi_member_groups": multi,
                "boundary_inspections": {
                    "highest_10": _boundary(scored, lambda row: (-row["match_strength"], row["group_id"])),
                    "lowest_10": _boundary(scored, lambda row: (row["match_strength"], row["group_id"])),
                    "nearest_90": _boundary(scored, lambda row: (abs(row["match_strength"] - 90.0), row["group_id"])),
                    "nearest_60": _boundary(scored, lambda row: (abs(row["match_strength"] - 60.0), row["group_id"])),
                    "high_review": [row for row in rows if row["band"] == "HIGH_MATCH" and row["existing_tier"] == "POSSIBLE_DUPLICATE_GROUP_REVIEW"],
                    "borderline": [row for row in rows if row["band"] == "BORDERLINE_MATCH"],
                    "unscored": unscored,
                },
                "semantic_fingerprints": {
                    item.stage.split("_", 1)[0]: {
                        "name": item.stage, "count": item.count,
                        "sha256": item.fingerprint,
                    }
                    for item in after
                },
                "semantic_fingerprints_unchanged_by_projection": True,
            }
        finally:
            session.close()
            engine.dispose()

    request = request_provenance(
        scan_mode="SAME_SITE_DUPLICATE",
        selected_fields=["CONTRACT", "UNIT_MEAS"], threshold=75.0,
        candidate_mode="group_first_primary", sensitive_mode=True,
        source_type="CANONICAL_DB_SNAPSHOT",
        feature_flags={
            "hybrid_retrieval_enabled": True, "local_embedding_enabled": True,
        },
        semantic_options={
            "identity_discovery_mode": "DISCOVERY",
            "visible_projection_contract": "G2_V2",
        },
    )
    if request["sha256"] != EXPECTED_REQUEST_FINGERPRINT:
        raise ValueError("shadow request differs from the frozen acceptance")
    baseline = json.loads((
        repository_root / "artifacts" / "request_scoped_site_constraint"
        / "site_selected.acceptance_provenance.json"
    ).read_text(encoding="utf-8"))
    if result["semantic_fingerprints"] != baseline["semantic_fingerprints"]:
        raise ValueError("shadow S0-S10 differs from the frozen acceptance")
    result["semantic_fingerprints_match_baseline"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_shadow(args.repository_root.resolve())
    rendered = json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
