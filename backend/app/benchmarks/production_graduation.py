"""GF-11D benchmark-only full production graduation measurement.

The harness runs the real policy-v2 ScanRunner against an isolated SQLite
database. It adds telemetry only; it does not replace or alter production
retrieval, evidence, resolution, or projection behavior.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.benchmarks.group_first_scale import (
    _collect_result,
    benchmark_configuration,
    inspect_interrupted_benchmark,
)
from app.benchmarks.contracts import ScaleBenchmarkStatus
from app.benchmarks.group_first_scale_generator import (
    CANONICAL_SCENARIO,
    generate_scale_corpus,
)
from app.benchmarks.residual_discovery_profile import (
    PROFILE_CONTRACT_VERSION,
    _Collector,
    _decomposition,
    _instrumented_production_path,
    _operation,
    _parameter_shape,
)
from app.db.database import Base
from app.db.models import (
    G2V2ProjectionRun,
    IdentityDiscoveryRun,
    IdentityEvidenceRun,
    IdentityNeighborhoodMember,
    IdentityNeighborhoodSnapshot,
    IdentityResolutionRun,
    ScanOrchestrationRun,
)
from app.services.identity_discovery_service import (
    DISCOVERY_ALGORITHM_VERSION,
    DISCOVERY_CONFIGURATION_VERSION,
)
from app.services.lexical_retrieval import (
    LEXICAL_STRATEGY_VERSION,
    lexical_strategy_contract_fingerprint,
    select_lexical_strategy,
)
from app.services.scan_runner import ScanRunner


GRADUATION_CONTRACT_VERSION = "gf11d-production-graduation-v1"
CANONICAL_RECORDS = 100_000
CANONICAL_SEED = 1101
GRADUATION_TIMEOUT_SECONDS = 300.0
MAX_SELECT_PARAMETERS = 902
REPORT_STAGES = (
    "CANONICAL_CATALOG",
    "FEATURE_PRECOMPUTATION",
    "STANDARD_BLOCKING",
    "LEXICAL_VECTORIZATION",
    "LEXICAL_NEAREST_NEIGHBORS",
    "CHAR_VECTOR",
    "RETRIEVAL_CACHE_LOAD",
    "RETRIEVAL_CACHE_SAVE",
    "RETRIEVAL_TOTAL",
    "GF2_PROPOSAL_PERSISTENCE",
    "GF3_NEIGHBORHOOD_PERSISTENCE",
    "GF4_EVIDENCE_ACQUISITION",
    "GF5_GROUP_RESOLUTION",
    "GF6_G2_V2_PROJECTION",
)


def strategy_sanity(record_count: int, final_top_k: int = 5) -> dict:
    """Return immutable strategy identity without generating benchmark truth."""
    return {
        "record_count": record_count,
        "strategy": select_lexical_strategy(record_count),
        "strategy_version": LEXICAL_STRATEGY_VERSION,
        "discovery_algorithm_version": DISCOVERY_ALGORITHM_VERSION,
        "discovery_configuration_version": DISCOVERY_CONFIGURATION_VERSION,
        "contract_fingerprint": lexical_strategy_contract_fingerprint(final_top_k),
        "provider_calls": 0,
    }


def stage_reachability(checkpoint: dict) -> dict:
    """Use NOT_REACHED for unavailable stage evidence; never fabricate zero."""
    elapsed = checkpoint.get("bucket_seconds_partial", {})
    active = checkpoint.get("active_sub_stage")
    completed = checkpoint.get("completed_stages", {})
    reached = {}
    for stage in REPORT_STAGES:
        if stage in completed or elapsed.get(stage, 0) > 0:
            reached[stage] = "COMPLETED"
        elif active == stage:
            reached[stage] = "REACHED"
        else:
            reached[stage] = "NOT_REACHED"
    return reached


def _profile_payload(collector: _Collector) -> dict:
    decomposition, attributed, discovery_total = _decomposition(collector)
    return {
        "contract_version": PROFILE_CONTRACT_VERSION,
        "active_sub_stage": collector.active_sub_stage,
        "pipeline_seconds": round(collector.pipeline_seconds or 0.0, 6),
        "discovery_seconds": round(discovery_total, 6),
        "timing_decomposition_seconds": decomposition,
        "attributed_percent": round(100 * attributed / discovery_total, 4)
        if discovery_total else 0.0,
        "retrieval_breakdown_seconds": {
            "cache_load": round(collector.elapsed["RETRIEVAL_CACHE_LOAD"], 6),
            "cache_save": round(collector.elapsed["RETRIEVAL_CACHE_SAVE"], 6),
            "lexical_vectorization": round(collector.elapsed["LEXICAL_VECTORIZATION"], 6),
            "lexical_nearest_neighbors": round(collector.elapsed["LEXICAL_NEAREST_NEIGHBORS"], 6),
            "character": collector.retrieval.get("character_seconds", 0.0),
            "other_channels_fusion_and_materialization": round(max(
                0.0,
                collector.elapsed["RETRIEVAL_TOTAL"]
                - collector.elapsed["RETRIEVAL_CACHE_LOAD"]
                - collector.elapsed["RETRIEVAL_CACHE_SAVE"]
                - collector.elapsed["LEXICAL_VECTORIZATION"]
                - collector.elapsed["LEXICAL_NEAREST_NEIGHBORS"]
                - collector.retrieval.get("character_seconds", 0.0),
            ), 6),
        },
        "downstream_seconds": {
            "GF4_EVIDENCE_ACQUISITION": round(collector.elapsed["GF4_EVIDENCE_ACQUISITION"], 6),
            "GF5_GROUP_RESOLUTION": round(collector.elapsed["GF5_GROUP_RESOLUTION"], 6),
            "GF6_G2_V2_PROJECTION": round(collector.elapsed["GF6_G2_V2_PROJECTION"], 6),
        },
        "retrieval_counts": dict(collector.retrieval),
        "object_counts": dict(collector.counts),
        "commit_counts": dict(sorted(collector.commit_count.items())),
        "completed_stages": dict(sorted(collector.completed_stages.items())),
    }


def run_graduation_benchmark(
    *, records: int, seed: int, db_path: str | Path,
    checkpoint_path: str | Path | None = None,
) -> dict:
    path = Path(db_path).resolve()
    if path.exists():
        raise ValueError("graduation database path must not already exist")
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = Path(checkpoint_path).resolve() if checkpoint_path else None
    corpus = generate_scale_corpus(records, seed=seed, scenario=CANONICAL_SCENARIO)
    engine = create_engine(
        f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    size_before = path.stat().st_size if path.exists() else 0
    session = sessionmaker(bind=engine)()
    collector = _Collector(checkpoint, python_profile_enabled=False)
    sql = defaultdict(Counter)
    select_parameter_max = 0

    @event.listens_for(engine, "before_cursor_execute")
    def count_sql(_connection, _cursor, statement, parameters, _context, executemany):
        nonlocal select_parameter_max
        operation = _operation(statement)
        parameter_count, batch_size = _parameter_shape(parameters, executemany)
        sql[collector.active_sub_stage][operation] += 1
        collector.sql[collector.active_sub_stage][operation] += 1
        collector.sql_total[operation] += 1
        if executemany:
            sql[collector.active_sub_stage]["EXECUTEMANY"] += 1
            sql[collector.active_sub_stage]["EXECUTEMANY_ROWS"] += batch_size
            collector.sql[collector.active_sub_stage]["EXECUTEMANY"] += 1
            collector.sql_total["EXECUTEMANY"] += 1
        if operation == "SELECT":
            select_parameter_max = max(select_parameter_max, parameter_count)
            collector.counts["select_parameter_max"] = select_parameter_max
        collector.counts["sql_statements"] = sum(
            count for values in sql.values() for key, count in values.items()
            if key not in {"EXECUTEMANY", "EXECUTEMANY_ROWS"}
        )
        if collector.counts["sql_statements"] % 1000 == 0:
            collector.checkpoint()

    collector.start_pipeline()
    forced_error = None
    started = time.perf_counter()
    try:
        with _instrumented_production_path(
            collector, session, stop_after_discovery=False
        ):
            ScanRunner(session, benchmark_configuration()).run(
                corpus.records,
                f"GF-11D production graduation {records}",
                [],
                60,
                sensitive_mode=False,
                scan_mode="DISCOVERY",
            )
    except MemoryError:
        session.rollback()
        forced_error = "MEMORYERROR"
    except Exception as exc:
        session.rollback()
        forced_error = type(exc).__name__.upper()

    elapsed = time.perf_counter() - started
    scale = _collect_result(
        session, db_path=path, corpus=corpus, elapsed=elapsed,
        query_count=sum(
            count for values in sql.values() for key, count in values.items()
            if key not in {"EXECUTEMANY", "EXECUTEMANY_ROWS"}
        ),
    )
    terminal = scale.run.status.value
    if forced_error is not None and terminal == "COMPLETED":
        terminal = "FAILED"
    collector.finish_pipeline(terminal)

    discovery = session.query(IdentityDiscoveryRun).order_by(
        IdentityDiscoveryRun.id.desc()
    ).first()
    evidence = session.query(IdentityEvidenceRun).order_by(
        IdentityEvidenceRun.id.desc()
    ).first()
    resolution = session.query(IdentityResolutionRun).order_by(
        IdentityResolutionRun.id.desc()
    ).first()
    projection = session.query(G2V2ProjectionRun).order_by(
        G2V2ProjectionRun.id.desc()
    ).first()
    orchestration = session.query(ScanOrchestrationRun).order_by(
        ScanOrchestrationRun.id.desc()
    ).first()
    profile = _profile_payload(collector)
    profile["sql_counts_by_stage"] = {
        key: dict(sorted(value.items())) for key, value in sorted(sql.items())
    }
    profile["select_parameter_max"] = select_parameter_max
    profile["database_size_before_bytes"] = size_before
    profile["database_size_after_bytes"] = path.stat().st_size
    profile["safe_failure_category"] = forced_error or (
        resolution.safe_failure_category if resolution else None
    )
    profile["persisted_counts"] = {
        "proposals": discovery.proposal_count if discovery else None,
        "neighborhoods": discovery.neighborhood_count if discovery else None,
        "neighborhood_members": session.query(IdentityNeighborhoodMember).count()
        if discovery else None,
        "evidence_edges": evidence.edge_count_persisted if evidence else None,
        "resolution_work_units": resolution.work_unit_count if resolution else None,
        "groups": resolution.accepted_group_count if resolution else None,
        "conflicts": resolution.conflict_count if resolution else None,
        "deferred": resolution.deferred_work_unit_count if resolution else None,
        "unassigned": resolution.unassigned_record_count if resolution else None,
        "g2_v2_groups": projection.accepted_group_count if projection else None,
    }
    profile["orchestration_status"] = orchestration.status if orchestration else None
    result = {
        "contract_version": GRADUATION_CONTRACT_VERSION,
        "canonical_configuration": {
            "scenario": CANONICAL_SCENARIO,
            "records": records,
            "seed": seed,
            "provider": "none",
            "mode": "group_first_primary",
            "policy": "group-first-orchestration-policy-v2",
            "database_is_disposable": True,
        },
        "status": terminal,
        "forced_error": forced_error,
        "scale_result": scale.to_dict(),
        "profile": profile,
        "benchmark_truth_absent_from_production_path": True,
        "configured_database_accessed": False,
    }
    if checkpoint:
        checkpoint.write_text(
            json.dumps(result, ensure_ascii=True, sort_keys=True), encoding="utf-8"
        )
    session.close()
    engine.dispose()
    return result


def _worker(arguments: dict, result_path: str):
    result = run_graduation_benchmark(**arguments)
    Path(result_path).write_text(
        json.dumps(result, ensure_ascii=True, sort_keys=True), encoding="utf-8"
    )


def timeout_result(partial: dict, interrupted: dict, *, bound: float, wall: float) -> dict:
    active = partial.get("active_sub_stage") or "UNKNOWN_ACTIVE_SUB_STAGE"
    if active in {"COMPLETED", "FAILED"}:
        active = "TIMEOUT_AFTER_LAST_CHECKPOINT"
    return {
        "contract_version": GRADUATION_CONTRACT_VERSION,
        "status": "TIMED_OUT",
        "timeout_seconds": bound,
        "bounded_wall_seconds": round(wall, 6),
        "active_sub_stage": active,
        "last_checkpoint": partial,
        "stage_reachability": stage_reachability(partial),
        "scale_result": interrupted,
    }


def execute_bounded_graduation(
    *, records: int = CANONICAL_RECORDS, seed: int = CANONICAL_SEED,
    timeout_seconds: float = GRADUATION_TIMEOUT_SECONDS,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="gf11d-graduation-") as directory:
        root = Path(directory)
        db_path = root / "graduation.sqlite"
        checkpoint = root / "checkpoint.json"
        result_path = root / "result.json"
        arguments = {
            "records": records,
            "seed": seed,
            "db_path": db_path,
            "checkpoint_path": checkpoint,
        }
        process = multiprocessing.get_context("spawn").Process(
            target=_worker, args=(arguments, str(result_path))
        )
        started = time.perf_counter()
        process.start()
        process.join(timeout_seconds)
        wall = time.perf_counter() - started
        if process.is_alive():
            process.terminate()
            process.join(30)
            partial = json.loads(checkpoint.read_text(encoding="utf-8")) \
                if checkpoint.exists() else {}
            interrupted = inspect_interrupted_benchmark(
                records=records, seed=seed, scenario=CANONICAL_SCENARIO,
                db_path=db_path, elapsed=wall,
                status=ScaleBenchmarkStatus.TIMED_OUT,
            ).to_dict()
            return timeout_result(
                partial, interrupted, bound=timeout_seconds, wall=wall
            )
        if process.exitcode != 0 or not result_path.exists():
            return {
                "contract_version": GRADUATION_CONTRACT_VERSION,
                "status": "FAILED",
                "safe_failure_category": "BENCHMARK_PROCESS_EXITED_WITHOUT_RESULT",
            }
        return json.loads(result_path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=CANONICAL_RECORDS)
    parser.add_argument("--seed", type=int, default=CANONICAL_SEED)
    parser.add_argument("--timeout-seconds", type=float, default=GRADUATION_TIMEOUT_SECONDS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = execute_bounded_graduation(
        records=args.records, seed=args.seed, timeout_seconds=args.timeout_seconds
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0 if result.get("status") == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
