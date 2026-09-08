"""GF-11A isolated group-first scale benchmark runner and measurements."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.benchmarks.contracts import (
    SCALE_BENCHMARK_CONTRACT_VERSION,
    ScaleBenchmarkResult,
    ScaleBenchmarkRun,
    ScaleBenchmarkScenario,
    ScaleBenchmarkStatus,
    ScaleDatabaseMetrics,
    ScaleQualityMetrics,
    ScaleResourceMetrics,
    ScaleSafetyMetrics,
    ScaleStageMetrics,
    result_fingerprint_payload,
    stable_fingerprint,
)
from app.benchmarks.group_first_scale_generator import (
    BenchmarkTruth,
    generate_scale_corpus,
)
from app.db.database import Base
from app.db.models import (
    DuplicateCandidate,
    G2V2ConflictMemberRow,
    G2V2ConflictSnapshotRow,
    G2V2DeferredMemberRow,
    G2V2DeferredSnapshotRow,
    G2V2GroupMemberRow,
    G2V2GroupSnapshotRow,
    G2V2InternalEvidenceRow,
    G2V2ProjectionRun,
    G2V2UnassignedRecordRow,
    IdentityDiscoveryRun,
    IdentityEvidenceEdgeSnapshot,
    IdentityEvidenceRun,
    IdentityGroupProjectionRun,
    IdentityNeighborProposal,
    IdentityNeighborhoodMember,
    IdentityNeighborhoodSnapshot,
    IdentityResolutionConflictMember,
    IdentityResolutionConflictSnapshot,
    IdentityResolutionDeferredMember,
    IdentityResolutionDeferredSnapshot,
    IdentityResolutionGroupMember,
    IdentityResolutionGroupSnapshot,
    IdentityResolutionRun,
    IdentityResolutionTargetedEvidence,
    IdentityResolutionUnassignedRecord,
    RuleExclusionAudit,
    ScanOrchestrationRun,
    ScanOrchestrationStageResultRow,
    ScanRecordSnapshot,
    ShadowComparisonRun,
)
from app.services.scan_runner import ScanRunner


POLICY_VERSION = "group-first-orchestration-policy-v2"


def benchmark_configuration(*, hybrid_enabled: bool = True):
    """Explicit provider-free settings; this function reads no environment."""
    return SimpleNamespace(
        identity_orchestration_mode="group_first_primary",
        group_first_shadow_comparison_enabled=False,
        hybrid_retrieval_enabled=hybrid_enabled,
        hybrid_retrieval_lexical_top_k=5,
        hybrid_retrieval_vector_top_k=5,
        hybrid_retrieval_final_top_k=10,
        hybrid_retrieval_min_score=55.0,
        hybrid_retrieval_max_pairs_per_scan=500,
        hybrid_retrieval_tier_a_max=250,
        hybrid_retrieval_tier_b_max=200,
        hybrid_retrieval_tier_c_max=50,
        hybrid_retrieval_family_max=25,
        local_embedding_enabled=hybrid_enabled,
        local_embedding_model="sklearn-hashing-domain-v1",
        identity_neighborhood_max_members=20,
        llm_provider="none",
        group_llm_provider="none",
    )


_ROW_MODELS = (
    ("gf1_scan_records", ScanRecordSnapshot),
    ("gf2_discovery_runs", IdentityDiscoveryRun),
    ("gf2_neighbor_proposals", IdentityNeighborProposal),
    ("gf3_neighborhoods", IdentityNeighborhoodSnapshot),
    ("gf3_neighborhood_members", IdentityNeighborhoodMember),
    ("gf4_evidence_runs", IdentityEvidenceRun),
    ("gf4_evidence_edges", IdentityEvidenceEdgeSnapshot),
    ("gf5_resolution_runs", IdentityResolutionRun),
    ("gf5_groups", IdentityResolutionGroupSnapshot),
    ("gf5_group_members", IdentityResolutionGroupMember),
    ("gf5_conflicts", IdentityResolutionConflictSnapshot),
    ("gf5_conflict_members", IdentityResolutionConflictMember),
    ("gf5_deferred", IdentityResolutionDeferredSnapshot),
    ("gf5_deferred_members", IdentityResolutionDeferredMember),
    ("gf5_targeted_evidence", IdentityResolutionTargetedEvidence),
    ("gf5_unassigned", IdentityResolutionUnassignedRecord),
    ("gf6_projection_runs", G2V2ProjectionRun),
    ("gf6_groups", G2V2GroupSnapshotRow),
    ("gf6_group_members", G2V2GroupMemberRow),
    ("gf6_internal_evidence", G2V2InternalEvidenceRow),
    ("gf6_conflicts", G2V2ConflictSnapshotRow),
    ("gf6_conflict_members", G2V2ConflictMemberRow),
    ("gf6_deferred", G2V2DeferredSnapshotRow),
    ("gf6_deferred_members", G2V2DeferredMemberRow),
    ("gf6_unassigned", G2V2UnassignedRecordRow),
    ("orchestration_runs", ScanOrchestrationRun),
    ("orchestration_stages", ScanOrchestrationStageResultRow),
)


def safe_environment_metadata() -> tuple[tuple[str, str | int | None], ...]:
    return tuple(sorted({
        "logical_cpu_count": os.cpu_count(),
        "platform": platform.system(),
        "process_architecture": platform.machine(),
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
    }.items()))


def _peak_rss():
    try:
        import resource
    except ImportError:
        return None, "UNAVAILABLE"
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    multiplier = 1 if sys.platform == "darwin" else 1024
    return int(value * multiplier), "AVAILABLE"


def _stage_duration(row):
    if row.started_at is None or row.completed_at is None:
        return None
    return round(max(0.0, (row.completed_at - row.started_at).total_seconds()), 6)


def _max_work_unit_size(db, scan_id: int) -> int:
    neighborhoods = db.query(IdentityNeighborhoodMember).filter_by(scan_id=scan_id).all()
    members_by_neighborhood = defaultdict(list)
    for row in neighborhoods:
        members_by_neighborhood[row.neighborhood_id].append(row.record_id)
    parent = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    for members in members_by_neighborhood.values():
        if members:
            for member in members[1:]:
                union(members[0], member)
    counts = Counter(find(item) for item in parent)
    return max(counts.values(), default=0)


def _quality_metrics(db, scan_id: int, truth: BenchmarkTruth) -> ScaleQualityMetrics:
    group_rows = db.query(G2V2GroupSnapshotRow).filter_by(scan_id=scan_id).all()
    group_ids = [row.id for row in group_rows]
    members = db.query(G2V2GroupMemberRow).filter(
        G2V2GroupMemberRow.group_snapshot_id.in_(group_ids)
    ).all() if group_ids else []
    source_rows = {row.id: row.source_row_index for row in db.query(ScanRecordSnapshot).filter_by(scan_id=scan_id)}
    accepted = defaultdict(set)
    for row in members:
        accepted[row.group_snapshot_id].add(source_rows[row.record_id])
    accepted_sets = tuple(accepted.values())
    truth_sets = tuple(set(items) for _identity, items in truth.duplicate_sets if len(items) >= 2)
    covered = sum(any(items <= group for group in accepted_sets) for items in truth_sets)
    missed = sum(not any(len(items & group) >= 2 for group in accepted_sets) for items in truth_sets)
    split = sum(sum(bool(items & group) for group in accepted_sets) > 1 for items in truth_sets)
    truth_by_record = {}
    for index, items in enumerate(truth_sets):
        for item in items:
            truth_by_record[item] = index
    over_merged = sum(
        len({truth_by_record.get(item, f"unique:{item}") for item in group}) > 1
        for group in accepted_sets
    )
    deferred_members = db.query(G2V2DeferredMemberRow).filter(
        G2V2DeferredMemberRow.projection_run_id.in_(
            db.query(G2V2ProjectionRun.id).filter_by(scan_id=scan_id)
        )
    ).all()
    deferred_sources = {source_rows[row.record_id] for row in deferred_members}
    deferred_truth = sum(bool(items & deferred_sources) for items in truth_sets)
    return ScaleQualityMetrics(
        true_duplicate_set_count=len(truth_sets),
        covered_true_set_count=covered,
        missed_true_set_count=missed,
        over_merged_group_count=over_merged,
        split_true_set_count=split,
        conflict_detection_count=db.query(G2V2ConflictSnapshotRow).filter_by(scan_id=scan_id).count(),
        deferred_true_duplicate_set_count=deferred_truth,
    )


def _safety_metrics(db, scan_id: int) -> ScaleSafetyMetrics:
    runs = [row.id for row in db.query(G2V2ProjectionRun).filter_by(scan_id=scan_id)]
    groups = db.query(G2V2GroupSnapshotRow).filter_by(scan_id=scan_id).all()
    group_ids = [row.id for row in groups]
    members = db.query(G2V2GroupMemberRow).filter(
        G2V2GroupMemberRow.group_snapshot_id.in_(group_ids)
    ).all() if group_ids else []
    membership = Counter(row.record_id for row in members)
    cannot_links = db.query(G2V2InternalEvidenceRow).filter(
        G2V2InternalEvidenceRow.group_snapshot_id.in_(group_ids),
        G2V2InternalEvidenceRow.edge_class == "CANNOT_LINK",
    ).count() if group_ids else 0
    provider_calls = sum(
        value or 0 for value in (
            db.query(IdentityDiscoveryRun.provider_request_count).filter_by(scan_id=scan_id).scalar(),
            db.query(IdentityResolutionRun.provider_request_count).filter_by(scan_id=scan_id).scalar(),
        )
    )
    scan_models = (
        IdentityNeighborProposal, IdentityNeighborhoodSnapshot,
        IdentityNeighborhoodMember, IdentityEvidenceRun,
        IdentityEvidenceEdgeSnapshot, IdentityResolutionRun,
        IdentityResolutionGroupSnapshot, IdentityResolutionGroupMember,
        IdentityResolutionConflictSnapshot, IdentityResolutionDeferredSnapshot,
        G2V2ProjectionRun, G2V2GroupSnapshotRow, G2V2ConflictSnapshotRow,
        ScanOrchestrationRun,
    )
    contamination = sum(db.query(model).filter(model.scan_id != scan_id).count() for model in scan_models)
    return ScaleSafetyMetrics(
        accepted_cannot_link_violations=cannot_links,
        duplicate_accepted_memberships=sum(count - 1 for count in membership.values() if count > 1),
        single_member_accepted_groups=sum(row.member_count < 2 for row in groups),
        cross_scan_contamination=contamination,
        provider_calls=provider_calls,
        legacy_pair_rows=db.query(DuplicateCandidate).filter_by(scan_id=scan_id).count()
            + db.query(RuleExclusionAudit).filter_by(scan_id=scan_id).count(),
        g1_projection_rows=0,
        g2_v1_rows=db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan_id).count(),
        shadow_rows=db.query(ShadowComparisonRun).filter_by(scan_id=scan_id).count(),
    )


def _collect_result(
    db, *, db_path: Path, corpus, elapsed: float, query_count: int | None,
    forced_status: ScaleBenchmarkStatus | None = None,
) -> ScaleBenchmarkResult:
    orchestration = db.query(ScanOrchestrationRun).order_by(ScanOrchestrationRun.id.desc()).first()
    scan_id = orchestration.scan_id if orchestration else 0
    stages = db.query(ScanOrchestrationStageResultRow).filter_by(
        orchestration_run_id=orchestration.id
    ).order_by(ScanOrchestrationStageResultRow.execution_order).all() if orchestration else []
    discovery = db.query(IdentityDiscoveryRun).filter_by(scan_id=scan_id).one_or_none() if scan_id else None
    evidence = db.query(IdentityEvidenceRun).filter_by(scan_id=scan_id).order_by(IdentityEvidenceRun.id.desc()).first() if scan_id else None
    resolution = db.query(IdentityResolutionRun).filter_by(scan_id=scan_id).order_by(IdentityResolutionRun.id.desc()).first() if scan_id else None
    projection = db.query(G2V2ProjectionRun).filter_by(scan_id=scan_id).order_by(G2V2ProjectionRun.id.desc()).first() if scan_id else None
    count_map = {
        "CANONICAL_CATALOG": (corpus.records.shape[0], db.query(ScanRecordSnapshot).filter_by(scan_id=scan_id).count() if scan_id else 0, 0, 0),
        "DISCOVERY": (corpus.records.shape[0], discovery.proposal_count if discovery else 0, discovery.truncated_neighborhood_count if discovery else 0, discovery.deferred_family_count if discovery else None),
        "SIGNED_EVIDENCE": (discovery.proposal_count if discovery else 0, evidence.edge_count_persisted if evidence else 0, 0, 0),
        "GROUP_RESOLUTION": (discovery.neighborhood_count if discovery else 0, resolution.work_unit_count if resolution else 0, discovery.truncated_neighborhood_count if discovery else 0, resolution.deferred_work_unit_count if resolution else 0),
        "G2_V2_PROJECTION": (resolution.accepted_group_count if resolution else 0, projection.accepted_group_count if projection else 0, 0, projection.deferred_count if projection else 0),
    }
    stage_metrics = tuple(
        ScaleStageMetrics(
            stage=row.stage_id, status=row.status, wall_time_seconds=_stage_duration(row),
            input_count=count_map.get(row.stage_id, (None, None, None, None))[0],
            output_count=count_map.get(row.stage_id, (None, None, None, None))[1],
            truncated_count=count_map.get(row.stage_id, (None, None, None, None))[2],
            deferred_count=count_map.get(row.stage_id, (None, None, None, None))[3],
        ) for row in stages
    )
    row_counts = tuple((name, db.query(model).count()) for name, model in _ROW_MODELS)
    database = ScaleDatabaseMetrics(
        row_counts=row_counts,
        sqlite_size_bytes=db_path.stat().st_size if db_path.exists() else None,
        query_count=query_count,
    )
    if scan_id:
        safety = _safety_metrics(db, scan_id)
        quality = _quality_metrics(db, scan_id, corpus.truth)
    else:
        safety = ScaleSafetyMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)
        quality = ScaleQualityMetrics(len(corpus.truth.duplicate_sets), 0, len(corpus.truth.duplicate_sets), 0, 0, 0, 0)
    status = forced_status or (
        ScaleBenchmarkStatus.COMPLETED
        if orchestration and orchestration.status == "COMPLETED"
        else ScaleBenchmarkStatus.FAILED
    )
    if status == ScaleBenchmarkStatus.COMPLETED and not safety.passed:
        status = ScaleBenchmarkStatus.SAFETY_FAILURE
    last_stage = next(
        (
            row.stage_id for row in reversed(stages)
            if row.status not in {"NOT_APPLICABLE", "SKIPPED"}
        ),
        None,
    )
    if forced_status in {
        ScaleBenchmarkStatus.TIMED_OUT, ScaleBenchmarkStatus.RESOURCE_EXHAUSTED
    }:
        if projection is not None and projection.status == "RUNNING":
            last_stage = "G2_V2_PROJECTION"
        elif resolution is not None and resolution.status == "RUNNING":
            last_stage = "GROUP_RESOLUTION"
        elif evidence is not None and evidence.status == "RUNNING":
            last_stage = "SIGNED_EVIDENCE"
        elif discovery is not None and discovery.status == "RUNNING":
            last_stage = "DISCOVERY"
    run = ScaleBenchmarkRun(
        orchestration_mode=orchestration.mode if orchestration else "group_first_primary",
        policy_version=orchestration.policy_version if orchestration else POLICY_VERSION,
        status=status,
        last_stage=last_stage,
        safe_failure_category=(
            (resolution.safe_failure_category if resolution else None)
            or (orchestration.safe_failure_category if orchestration else None)
        ),
    )
    proposal_count = discovery.proposal_count if discovery else 0
    evidence_count = evidence.edge_count_persisted if evidence else 0
    record_count = corpus.records.shape[0]
    targeted = resolution.targeted_evidence_request_count if resolution else 0
    deferred = resolution.deferred_work_unit_count if resolution else 0
    complexity = tuple(sorted({
        "deferred_rate": round(deferred / max(1, resolution.work_unit_count), 6) if resolution else 0.0,
        "evidence_edges_per_record": round(evidence_count / record_count, 6),
        "max_neighborhood_size": discovery.max_included_member_count if discovery else 0,
        "max_resolution_work_unit_size": _max_work_unit_size(db, scan_id) if scan_id else 0,
        "proposal_count_per_record": round(proposal_count / record_count, 6),
        "targeted_checks_per_record": round(targeted / record_count, 6),
        "truncation_rate": round((discovery.truncated_neighborhood_count if discovery else 0) / max(1, discovery.neighborhood_count if discovery else 0), 6),
    }.items()))
    observations = []
    if complexity[4][1] and complexity[4][1] > 5:
        observations.append("HIGH_PROPOSAL_FANOUT")
    if discovery and discovery.truncated_neighborhood_count:
        observations.append("NEIGHBORHOOD_CAP_ACTIVE")
    if resolution and resolution.deferred_work_unit_count:
        observations.append("RESOLVER_DEFERRED_WORK")
    if forced_status == ScaleBenchmarkStatus.TIMED_OUT:
        observations.append("BOUNDED_TIMEOUT_REACHED")
    peak_rss, peak_status = _peak_rss()
    scenario = ScaleBenchmarkScenario(
        name=corpus.scenario_name, version=corpus.version,
        record_count=record_count, seed=corpus.seed,
        generator_fingerprint=corpus.generator_fingerprint,
    )
    resource = ScaleResourceMetrics(round(elapsed, 6), peak_rss, peak_status)
    fingerprint = stable_fingerprint(result_fingerprint_payload(
        scenario=scenario, run=run, stage_metrics=stage_metrics,
        database_metrics=database, safety_metrics=safety,
        quality_metrics=quality, complexity_metrics=complexity,
    ))
    return ScaleBenchmarkResult(
        contract_version=SCALE_BENCHMARK_CONTRACT_VERSION,
        scenario=scenario, environment=safe_environment_metadata(), run=run,
        stage_metrics=stage_metrics, database_metrics=database,
        safety_metrics=safety, quality_metrics=quality,
        resource_metrics=resource, complexity_metrics=complexity,
        bottleneck_observations=tuple(observations), result_fingerprint=fingerprint,
    )


def run_scale_benchmark(
    *, records: int, seed: int, scenario: str, db_path: str | Path,
    hybrid_enabled: bool = True,
) -> ScaleBenchmarkResult:
    path = Path(db_path).resolve()
    if path.exists():
        raise ValueError("benchmark database path must not already exist")
    path.parent.mkdir(parents=True, exist_ok=True)
    corpus = generate_scale_corpus(records, seed=seed, scenario=scenario)
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    queries = {"count": 0}

    @event.listens_for(engine, "before_cursor_execute")
    def _count_query(_connection, _cursor, _statement, _parameters, _context, _many):
        queries["count"] += 1

    session = sessionmaker(bind=engine)()
    started = time.perf_counter()
    forced_status = None
    try:
        ScanRunner(session, benchmark_configuration(hybrid_enabled=hybrid_enabled)).run(
            corpus.records, f"GF-11A {scenario} {records}", [], 60,
            sensitive_mode=False, scan_mode="DISCOVERY",
        )
    except MemoryError:
        session.rollback()
        forced_status = ScaleBenchmarkStatus.RESOURCE_EXHAUSTED
    except Exception:
        session.rollback()
        forced_status = ScaleBenchmarkStatus.FAILED
    runtime_query_count = queries["count"]
    result = _collect_result(
        session, db_path=path, corpus=corpus,
        elapsed=time.perf_counter() - started,
        query_count=runtime_query_count, forced_status=forced_status,
    )
    session.close()
    engine.dispose()
    return result


def inspect_interrupted_benchmark(
    *, records: int, seed: int, scenario: str, db_path: str | Path,
    elapsed: float, status: ScaleBenchmarkStatus,
) -> ScaleBenchmarkResult:
    path = Path(db_path).resolve()
    corpus = generate_scale_corpus(records, seed=seed, scenario=scenario)
    if not path.exists():
        scenario_contract = ScaleBenchmarkScenario(
            corpus.scenario_name, corpus.version, records, seed,
            corpus.generator_fingerprint,
        )
        run = ScaleBenchmarkRun(
            "group_first_primary", POLICY_VERSION, status, None, None
        )
        database = ScaleDatabaseMetrics((), None, None)
        safety = ScaleSafetyMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)
        quality = ScaleQualityMetrics(len(corpus.truth.duplicate_sets), 0, len(corpus.truth.duplicate_sets), 0, 0, 0, 0)
        resource = ScaleResourceMetrics(round(elapsed, 6), None, "UNAVAILABLE")
        fingerprint = stable_fingerprint(result_fingerprint_payload(
            scenario=scenario_contract, run=run, stage_metrics=(),
            database_metrics=database, safety_metrics=safety,
            quality_metrics=quality, complexity_metrics=(),
        ))
        return ScaleBenchmarkResult(
            SCALE_BENCHMARK_CONTRACT_VERSION, scenario_contract,
            safe_environment_metadata(), run, (), database, safety, quality,
            resource, (), ("BOUNDED_TIMEOUT_REACHED",), fingerprint,
        )
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False})
    session = sessionmaker(bind=engine)()
    result = _collect_result(
        session, db_path=path, corpus=corpus, elapsed=elapsed,
        query_count=None, forced_status=status,
    )
    session.close()
    engine.dispose()
    return result


def main(argv=None) -> int:
    from app.benchmarks.group_first_scale_cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
