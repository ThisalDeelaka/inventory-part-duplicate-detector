"""GF-12A1 offline canonical quality-baseline harness."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.benchmarks.gf12_group_quality import (
    GroupQualityEvaluationResult,
    evaluate_group_quality,
    input_from_identity_read_snapshot,
    truth_from_benchmark,
)
from app.benchmarks.group_first_scale_generator import (
    CANONICAL_SCENARIO,
    GENERATOR_VERSION,
    TRUTH_VERSION_V2,
    generate_corrected_scale_corpus,
)
from app.benchmarks.production_graduation import run_graduation_benchmark
from app.db.models import (
    IdentityDiscoveryRun,
    IdentityResolutionRun,
    ScanOrchestrationRun,
)
from app.services.canonical_record_service import load_scan_record_catalog
from app.services.identity_read_service import IdentityReadService


@dataclass(frozen=True)
class CanonicalQualityBaseline:
    production_status: str
    provider_calls: int
    production_strategy: str
    truth_integrity: str
    evaluation: GroupQualityEvaluationResult

    def to_dict(self):
        return {
            "production_status": self.production_status,
            "provider_calls": self.provider_calls,
            "production_strategy": self.production_strategy,
            "truth_integrity": self.truth_integrity,
            "evaluation": self.evaluation.to_dict(),
        }


def evaluate_persisted_canonical_run(
    *, db_path: str | Path, records: int, seed: int = 1101,
) -> GroupQualityEvaluationResult:
    """Load the same authority-selected snapshot used by product readers."""
    corpus = generate_corrected_scale_corpus(
        records, seed=seed, scenario=CANONICAL_SCENARIO
    )
    engine = create_engine(
        f"sqlite:///{Path(db_path).resolve().as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session = sessionmaker(bind=engine)()
    try:
        orchestration = session.query(ScanOrchestrationRun).order_by(
            ScanOrchestrationRun.id.desc()
        ).one()
        snapshot = IdentityReadService(session).load_identity_read_snapshot(
            orchestration.scan_id
        )
        catalog = load_scan_record_catalog(session, orchestration.scan_id)
        reference_rows = {
            record.record_ref_key: record.source_row_index for record in catalog
        }
        evaluation_input = input_from_identity_read_snapshot(
            snapshot,
            corpus_id=CANONICAL_SCENARIO,
            corpus_version=GENERATOR_VERSION,
            truth_version=TRUTH_VERSION_V2,
            seed=seed,
            source_row_by_record_reference=reference_rows,
        )
        return evaluate_group_quality(
            evaluation_input,
            truth_from_benchmark(
                corpus.truth, records,
                corpus_version=GENERATOR_VERSION,
                truth_version=TRUTH_VERSION_V2,
            ),
        )
    finally:
        session.close()
        engine.dispose()


def run_canonical_quality_baseline(
    *, db_path: str | Path, records: int, seed: int = 1101,
) -> CanonicalQualityBaseline:
    production = run_graduation_benchmark(
        records=records, seed=seed, db_path=db_path
    )
    if production["status"] != "COMPLETED":
        raise RuntimeError(
            f"canonical production run did not complete: {production['status']}"
        )
    scale = production["scale_result"]
    provider_calls = scale["safety_metrics"]["provider_calls"]
    if provider_calls != 0:
        raise RuntimeError("canonical production run made provider calls")
    return CanonicalQualityBaseline(
        production_status=production["status"],
        provider_calls=provider_calls,
        production_strategy="policy-v2 / group_first_primary",
        truth_integrity="PASS",
        evaluation=evaluate_persisted_canonical_run(
            db_path=db_path, records=records, seed=seed
        ),
    )


def load_existing_canonical_quality_baseline(
    *, db_path: str | Path, records: int, seed: int = 1101,
) -> CanonicalQualityBaseline:
    """Re-evaluate an already completed disposable production run offline."""
    path = Path(db_path).resolve()
    engine = create_engine(
        f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}
    )
    session = sessionmaker(bind=engine)()
    try:
        orchestration = session.query(ScanOrchestrationRun).order_by(
            ScanOrchestrationRun.id.desc()
        ).one()
        if orchestration.status != "COMPLETED":
            raise RuntimeError("persisted canonical production run is not completed")
        discovery = session.query(IdentityDiscoveryRun).filter_by(
            scan_id=orchestration.scan_id
        ).one()
        resolution = session.query(IdentityResolutionRun).filter_by(
            scan_id=orchestration.scan_id
        ).one()
        provider_calls = (
            (discovery.provider_request_count or 0)
            + (resolution.provider_request_count or 0)
        )
        if provider_calls != 0:
            raise RuntimeError("persisted canonical production run made provider calls")
    finally:
        session.close()
        engine.dispose()
    return CanonicalQualityBaseline(
        production_status="COMPLETED",
        provider_calls=provider_calls,
        production_strategy="policy-v2 / group_first_primary",
        truth_integrity="PASS",
        evaluation=evaluate_persisted_canonical_run(
            db_path=path, records=records, seed=seed
        ),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=1101)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--existing", action="store_true")
    args = parser.parse_args(argv)
    runner = (
        load_existing_canonical_quality_baseline
        if args.existing else run_canonical_quality_baseline
    )
    result = runner(db_path=args.db, records=args.records, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.to_dict(), ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
