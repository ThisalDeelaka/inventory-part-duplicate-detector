"""Read-only GROUP_EVIDENCE_SCORE_V1 shadow report for a safe canonical scan."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, median

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.benchmarks.acceptance_provenance import request_provenance
from app.db.database import Base, SessionLocal
from app.identity_read.group_evidence_strength import (
    EvidenceBand,
    project_group_evidence_strength,
)
from app.services.canonical_record_service import (
    catalog_record_to_engine_input,
    load_scan_record_catalog,
)
from app.services.identity_read_service import IdentityReadService
from app.services.scan_runner import ScanRunner


def acceptance_configuration() -> Settings:
    """Pinned provider-free settings recorded by the Site-constraint acceptance."""
    return Settings(
        llm_provider="none",
        llm_demo_enabled=False,
        identity_orchestration_mode="group_first_primary",
        group_first_shadow_comparison_enabled=False,
        hybrid_retrieval_enabled=True,
        local_embedding_enabled=True,
        hybrid_retrieval_lexical_top_k=5,
        hybrid_retrieval_vector_top_k=5,
        hybrid_retrieval_final_top_k=10,
        hybrid_retrieval_max_pairs_per_scan=500,
        hybrid_retrieval_tier_a_max=250,
        hybrid_retrieval_tier_b_max=200,
        hybrid_retrieval_tier_c_max=50,
        hybrid_retrieval_family_max=25,
        identity_neighborhood_max_members=20,
    )


def summarize_snapshot(snapshot) -> dict:
    rows = []
    for group in snapshot.groups:
        strength = project_group_evidence_strength(group)
        if strength is None:
            continue
        rows.append({
            "group_reference": group.versioned_group_key.group_reference,
            "existing_evidence_tier": group.status.value,
            "member_count": group.member_count,
            **strength.as_dict(),
        })
    scores = [row["evidence_score"] for row in rows]
    by_band = Counter({band.value: 0 for band in EvidenceBand})
    by_band.update(row["evidence_band"] for row in rows)
    by_tier_band = Counter(
        (row["existing_evidence_tier"], row["evidence_band"]) for row in rows
    )

    def ordered(reverse=False):
        return sorted(
            rows,
            key=lambda row: (
                -row["evidence_score"] if reverse else row["evidence_score"],
                row["group_reference"],
            ),
        )[:5]

    def near(target):
        return sorted(
            rows,
            key=lambda row: (
                abs(row["evidence_score"] - target), row["group_reference"]
            ),
        )[:5]

    return {
        "scan_id": snapshot.scan_id,
        "canonical_record_count": snapshot.canonical_record_count,
        "group_count": snapshot.group_count,
        "scored_group_count": len(rows),
        "existing_tiers": {
            "Stronger Evidence": snapshot.likely_group_count,
            "Review Evidence": snapshot.review_group_count,
        },
        "score_min": min(scores),
        "score_max": max(scores),
        "score_mean": mean(scores),
        "score_median": median(scores),
        "band_distribution": dict(sorted(by_band.items())),
        "distribution_by_existing_tier": {
            f"{tier} | {band}": count
            for (tier, band), count in sorted(by_tier_band.items())
        },
        "highest_five": ordered(reverse=True),
        "lowest_five": ordered(),
        "nearest_75_five": near(75.0),
        "nearest_50_five": near(50.0),
        "semantic_counts": {
            "conflicts": snapshot.conflict_count,
            "deferred": snapshot.deferred_count,
            "unassigned": snapshot.unassigned_count,
            "member_rows": sum(group.member_count for group in snapshot.groups),
        },
        "provider_calls": 0,
    }


def replay_and_summarize(source_scan_id: int) -> dict:
    source_db = SessionLocal()
    try:
        source_records = load_scan_record_catalog(source_db, source_scan_id)
    finally:
        source_db.close()
    if not source_records:
        raise ValueError("source scan has no canonical records")
    records = pd.DataFrame(
        catalog_record_to_engine_input(record) for record in source_records
    )

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    replay_db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        scan, _ = ScanRunner(replay_db, acceptance_configuration()).run(
            records,
            "GROUP_EVIDENCE_SCORE_V1 shadow",
            ["CONTRACT", "UNIT_MEAS"],
            75,
            source_type="CANONICAL_DB_SNAPSHOT",
            scan_mode="SAME_SITE_DUPLICATE",
            orchestration_mode="group_first_primary",
        )
        snapshot = IdentityReadService(replay_db).load_identity_read_snapshot(scan.id)
        report = summarize_snapshot(snapshot)
        report["source"] = {
            "logical_label": f"canonical-db-snapshot-scan-{source_scan_id}",
            "protected_workbook_accessed": False,
        }
        report["request"] = request_provenance(
            scan_mode="SAME_SITE_DUPLICATE",
            selected_fields=["CONTRACT", "UNIT_MEAS"],
            threshold=75,
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
        return report
    finally:
        replay_db.close()
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-scan-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = replay_and_summarize(args.source_scan_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
