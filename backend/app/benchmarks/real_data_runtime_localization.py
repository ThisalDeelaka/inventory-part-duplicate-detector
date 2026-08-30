"""GF-12C1-R3 benchmark-only real-data runtime localization.

This module wraps the unchanged production ``ScanRunner`` with aggregate timers,
counters, and disposable SQLite state.  It never serializes source rows or raw
descriptions and it reads configuration from an explicit provider-none object,
not from the environment.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import io
import json
import multiprocessing
import pstats
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from itertools import combinations
from math import comb
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import sessionmaker

from app.benchmarks.group_first_scale import benchmark_configuration
from app.benchmarks.production_graduation import _profile_payload
from app.benchmarks.residual_discovery_profile import (
    _Collector,
    _instrumented_production_path,
    _operation,
    _parameter_shape,
)
from app.db.database import Base
from app.db.models import (
    DuplicateCandidate,
    DuplicateScan,
    G2V2ProjectionRun,
    IdentityDiscoveryRun,
    IdentityEvidenceEdgeSnapshot,
    IdentityEvidenceRun,
    IdentityGroupProjectionRun,
    IdentityNeighborProposal,
    IdentityNeighborhoodMember,
    IdentityNeighborhoodSnapshot,
    IdentityResolutionRun,
    ScanOrchestrationRun,
    ScanOrchestrationStageResultRow,
    ScanRecordSnapshot,
    ShadowComparisonRun,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.resolution import resolver
from app.services import g2_v2_projection_service, hybrid_retrieval
from app.services import identity_resolution_service
from app.services.scan_runner import ScanRunner
from app.services.validation_service import apply_column_mapping, validate_dataframe


LOCALIZATION_CONTRACT_VERSION = "gf12c1-r3-runtime-localization-v1"
EXPECTED_REAL_SHA256 = (
    "8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b"
)
EXPECTED_REAL_RECORDS = 5_327
DEFAULT_TIMEOUT_SECONDS = 900.0


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int((len(ordered) - 1) * percentile)
    return ordered[index]


def _distribution(values) -> dict:
    rows = [int(value) for value in values]
    return {
        "count": len(rows),
        "min": min(rows) if rows else None,
        "median": _percentile(rows, 0.50),
        "p90": _percentile(rows, 0.90),
        "p95": _percentile(rows, 0.95),
        "p99": _percentile(rows, 0.99),
        "max": max(rows) if rows else None,
        "over_10": sum(value > 10 for value in rows),
        "over_25": sum(value > 25 for value in rows),
        "over_50": sum(value > 50 for value in rows),
        "over_100": sum(value > 100 for value in rows),
    }


def _duration(started, completed):
    if started is None or completed is None:
        return None
    return round(max(0.0, (completed - started).total_seconds()), 6)


def _work_shape_from_rows(neighborhood_members, proposals, evidence_edges=()) -> dict:
    parent: dict[int, int] = {}

    def find(value: int) -> int:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    members_by_neighborhood = defaultdict(list)
    for row in neighborhood_members:
        members_by_neighborhood[row.neighborhood_id].append(row.record_id)
    for members in members_by_neighborhood.values():
        if members:
            for member in members[1:]:
                union(members[0], member)
    record_counts = Counter(find(record_id) for record_id in parent)
    edge_counts = Counter()
    cannot_link_counts = Counter()
    for row in proposals:
        root = find(row.record_id_1)
        if root == find(row.record_id_2):
            edge_counts[root] += 1
    for row in evidence_edges:
        root = find(row.record_id_1)
        if (
            root == find(row.record_id_2)
            and row.edge_class == IdentityEdgeClass.CANNOT_LINK.value
        ):
            cannot_link_counts[root] += 1
    shapes = [{
        "records": count,
        "candidate_edges": edge_counts.get(root, 0),
        "cannot_links": cannot_link_counts.get(root, 0),
    } for root, count in record_counts.items()]
    return {
        "records_per_work_unit": _distribution(record_counts.values()),
        "candidate_edges_per_work_unit": _distribution(
            edge_counts.get(root, 0) for root in record_counts
        ),
        "cannot_links_per_work_unit": _distribution(
            cannot_link_counts.get(root, 0) for root in record_counts
        ),
        "largest_work_unit_shapes": sorted(
            shapes,
            key=lambda item: (
                -item["records"], -item["candidate_edges"], -item["cannot_links"]
            ),
        )[:12],
    }


def inspect_database(
    db_path: str | Path, *, expected_records: int = EXPECTED_REAL_RECORDS
) -> dict:
    """Return aggregate lifecycle/work-shape evidence from a diagnostic DB."""
    path = Path(db_path).resolve()
    if not path.exists() or path.stat().st_size == 0:
        return {"available": False}
    engine = create_engine(
        f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}
    )
    session = sessionmaker(bind=engine)()
    try:
        candidate_scan_ids = [scan_id for scan_id, _count in (
            session.query(ScanRecordSnapshot.scan_id, func.count(ScanRecordSnapshot.id))
            .group_by(ScanRecordSnapshot.scan_id)
            .having(func.count(ScanRecordSnapshot.id) == expected_records)
            .all()
        )]
        # Select the newest scan with the target catalog cardinality without
        # reading or emitting any business field.
        target_scan_id = None
        for scan_id in sorted(candidate_scan_ids, reverse=True):
            if session.query(ScanRecordSnapshot).filter_by(scan_id=scan_id).count() == expected_records:
                target_scan_id = scan_id
                break
        if target_scan_id is None:
            return {"available": False}

        scan = session.get(DuplicateScan, target_scan_id)
        orchestration = session.query(ScanOrchestrationRun).filter_by(
            scan_id=target_scan_id
        ).order_by(ScanOrchestrationRun.id.desc()).first()
        stages = []
        if orchestration is not None:
            rows = session.query(ScanOrchestrationStageResultRow).filter_by(
                orchestration_run_id=orchestration.id
            ).order_by(ScanOrchestrationStageResultRow.execution_order).all()
            stages = [{
                "stage": row.stage_id,
                "status": row.status,
                "seconds": _duration(row.started_at, row.completed_at),
                "safe_failure_category": row.safe_failure_category,
            } for row in rows]
        discovery = session.query(IdentityDiscoveryRun).filter_by(
            scan_id=target_scan_id
        ).order_by(IdentityDiscoveryRun.id.desc()).first()
        evidence = session.query(IdentityEvidenceRun).filter_by(
            scan_id=target_scan_id
        ).order_by(IdentityEvidenceRun.id.desc()).first()
        resolution = session.query(IdentityResolutionRun).filter_by(
            scan_id=target_scan_id
        ).order_by(IdentityResolutionRun.id.desc()).first()
        projection = session.query(G2V2ProjectionRun).filter_by(
            scan_id=target_scan_id
        ).order_by(G2V2ProjectionRun.id.desc()).first()
        neighborhoods = session.query(IdentityNeighborhoodSnapshot).filter_by(
            scan_id=target_scan_id
        ).all()
        members = session.query(IdentityNeighborhoodMember).filter_by(
            scan_id=target_scan_id
        ).all()
        proposals = session.query(IdentityNeighborProposal).filter_by(
            scan_id=target_scan_id
        ).all()
        evidence_edges = session.query(IdentityEvidenceEdgeSnapshot).filter_by(
            scan_id=target_scan_id
        ).all()
        work_shape = _work_shape_from_rows(members, proposals, evidence_edges)
        return {
            "available": True,
            "scan_status": scan.status if scan else None,
            "authoritative": bool(
                scan and scan.status == "COMPLETED" and orchestration
                and orchestration.visible_product_ready
            ),
            "orchestration_status": orchestration.status if orchestration else None,
            "visible_product_ready": (
                orchestration.visible_product_ready if orchestration else None
            ),
            "stages": stages,
            "discovery": {
                "status": discovery.status if discovery else None,
                "records": discovery.records_total if discovery else None,
                "proposals": discovery.proposal_count if discovery else None,
                "neighborhoods": discovery.neighborhood_count if discovery else None,
                "provider_calls": discovery.provider_request_count if discovery else 0,
            },
            "neighborhood_size_distribution": _distribution(
                row.member_count for row in neighborhoods
            ),
            "neighborhood_members": len(members),
            "work_shape": work_shape,
            "gf4": {
                "status": evidence.status if evidence else None,
                "edges": evidence.edge_count_persisted if evidence else None,
                "seconds": _duration(evidence.started_at, evidence.completed_at)
                if evidence else None,
                "provider_calls": getattr(evidence, "provider_request_count", 0)
                if evidence else 0,
            },
            "gf5": {
                "status": resolution.status if resolution else None,
                "work_units": resolution.work_unit_count if resolution else None,
                "targeted_requests": resolution.targeted_evidence_request_count
                if resolution else None,
                "targeted_results": resolution.targeted_evidence_result_count
                if resolution else None,
                "groups": resolution.accepted_group_count if resolution else None,
                "likely": resolution.likely_group_count if resolution else None,
                "review": resolution.review_group_count if resolution else None,
                "conflicts": resolution.conflict_count if resolution else None,
                "deferred": resolution.deferred_work_unit_count if resolution else None,
                "unassigned": resolution.unassigned_record_count if resolution else None,
                "seconds": _duration(resolution.started_at, resolution.completed_at)
                if resolution else None,
                "safe_failure_category": resolution.safe_failure_category
                if resolution else None,
                "provider_calls": resolution.provider_request_count if resolution else 0,
            },
            "gf6": {
                "status": projection.status if projection else None,
                "groups": projection.accepted_group_count if projection else None,
                "likely": projection.likely_group_count if projection else None,
                "review": projection.review_group_count if projection else None,
                "conflicts": projection.conflict_count if projection else None,
                "deferred": projection.deferred_count if projection else None,
                "unassigned": projection.unassigned_record_count if projection else None,
                "seconds": _duration(projection.started_at, projection.completed_at)
                if projection else None,
                "safe_failure_category": projection.safe_failure_category
                if projection else None,
            },
            "deprecated_writes": {
                "pairs": session.query(DuplicateCandidate).filter_by(scan_id=target_scan_id).count(),
                "g2_v1": session.query(IdentityGroupProjectionRun).filter_by(scan_id=target_scan_id).count(),
                "shadow": session.query(ShadowComparisonRun).filter_by(scan_id=target_scan_id).count(),
            },
        }
    finally:
        session.close()
        engine.dispose()


@contextmanager
def _additional_instrumentation(
    collector: _Collector,
    *,
    dense_candidate_repetitions: int = 1,
    profile_dense_reference: bool = False,
):
    originals = {}

    def patch(owner, name, replacement):
        originals[(owner, name)] = getattr(owner, name)
        setattr(owner, name, replacement)

    phase = {"name": None, "started": None}

    def in_retrieval() -> bool:
        return any(bucket == "RETRIEVAL_TOTAL" for bucket, _started in collector.stack)

    def transition(name: str):
        now = time.perf_counter()
        if phase["name"] is not None:
            collector.elapsed[phase["name"]] += now - phase["started"]
            collector.calls[phase["name"]] += 1
        phase.update(name=name, started=now)
        collector.active_sub_stage = name
        collector.checkpoint()

    def finish_retrieval_phase():
        if phase["name"] is not None:
            now = time.perf_counter()
            collector.elapsed[phase["name"]] += now - phase["started"]
            collector.calls[phase["name"]] += 1
            phase.update(name=None, started=None)
        collector.active_sub_stage = "POST_RETRIEVAL_PROPOSAL_MATERIALIZATION"
        collector.checkpoint()

    original_retrieve = hybrid_retrieval.HybridCandidateRetriever.retrieve
    def retrieve(instance, *args, **kwargs):
        result = original_retrieve(instance, *args, **kwargs)
        finish_retrieval_phase()
        return result
    patch(hybrid_retrieval.HybridCandidateRetriever, "retrieve", retrieve)

    original_specificity = hybrid_retrieval.description_specificity_statistics
    def specificity(*args, **kwargs):
        result = original_specificity(*args, **kwargs)
        if in_retrieval():
            transition("EXACT_DESCRIPTION_CHANNEL")
        return result
    patch(hybrid_retrieval, "description_specificity_statistics", specificity)

    original_part = hybrid_retrieval.part_number_family_keys
    part_started = False
    def part(*args, **kwargs):
        nonlocal part_started
        if in_retrieval() and not part_started:
            part_started = True
            transition("PART_FAMILY_CHANNEL")
        return original_part(*args, **kwargs)
    patch(hybrid_retrieval, "part_number_family_keys", part)

    original_tfidf = hybrid_retrieval.TfidfVectorizer.fit_transform
    def tfidf(instance, *args, **kwargs):
        if in_retrieval():
            transition("LEXICAL_CHANNEL")
        return original_tfidf(instance, *args, **kwargs)
    patch(hybrid_retrieval.TfidfVectorizer, "fit_transform", tfidf)

    original_cache_load = hybrid_retrieval.SqlAlchemyEmbeddingVectorCache.load
    def cache_load(instance, *args, **kwargs):
        if in_retrieval():
            transition("CHARACTER_PREPARATION")
        return original_cache_load(instance, *args, **kwargs)
    patch(hybrid_retrieval.SqlAlchemyEmbeddingVectorCache, "load", cache_load)

    original_technical = hybrid_retrieval._technical_keys
    technical_started = False
    def technical(*args, **kwargs):
        nonlocal technical_started
        if in_retrieval() and not technical_started:
            technical_started = True
            transition("TECHNICAL_CHANNEL")
        return original_technical(*args, **kwargs)
    patch(hybrid_retrieval, "_technical_keys", technical)

    original_conflicts = hybrid_retrieval._conflict_signals
    fusion_started = False
    def conflicts(*args, **kwargs):
        nonlocal fusion_started
        if in_retrieval() and not fusion_started:
            fusion_started = True
            transition("FUSION_MATERIALIZATION")
        return original_conflicts(*args, **kwargs)
    patch(hybrid_retrieval, "_conflict_signals", conflicts)

    original_work_units = resolver._work_units
    def work_units(value):
        with collector.measure("GF5_WORK_UNIT_BUILD", checkpoint=True):
            units = original_work_units(value)
        edge_counts = Counter()
        cannot_counts = Counter()
        owner = {}
        for index, unit in enumerate(units):
            for record_id in unit.member_ids:
                owner[record_id] = index
        for edge in value.machine_evidence_edges:
            index = owner.get(edge.record_id_1)
            if index is not None and owner.get(edge.record_id_2) == index:
                edge_counts[index] += 1
                if edge.edge_class == IdentityEdgeClass.CANNOT_LINK:
                    cannot_counts[index] += 1
        shapes = []
        for index, unit in enumerate(units):
            size = len(unit.member_ids)
            theoretical = sum(comb(size, width) for width in range(
                2, min(size, value.resolver_configuration.complete_pairwise_member_limit) + 1
            ))
            bounded_limit = (
                value.resolver_configuration.max_resolution_members ** 2
                * max(1, value.resolver_configuration.max_targeted_checks_per_work_unit + 1)
            )
            shapes.append({
                "records": size,
                "candidate_edges": edge_counts[index],
                "cannot_links": cannot_counts[index],
                "theoretical_candidate_subsets": theoretical,
                "candidate_generation_bound": bounded_limit,
                "deferred_over_member_cap": (
                    size > value.resolver_configuration.max_resolution_members
                ),
            })
        collector.counts.update({
            "gf5_work_units_planned": len(units),
            "gf5_records_per_work_unit": _distribution(
                len(unit.member_ids) for unit in units
            ),
            "gf5_candidate_edges_per_work_unit": _distribution(
                edge_counts[index] for index in range(len(units))
            ),
            "gf5_cannot_links_per_work_unit": _distribution(
                cannot_counts[index] for index in range(len(units))
            ),
            "gf5_targeted_budget_per_work_unit": (
                value.resolver_configuration.max_targeted_checks_per_work_unit
            ),
            "gf5_largest_work_unit_shapes": sorted(
                shapes,
                key=lambda item: (
                    -item["records"], -item["candidate_edges"],
                    -item["cannot_links"], -item["theoretical_candidate_subsets"],
                ),
            )[:12],
        })
        collector.checkpoint()
        return units
    patch(resolver, "_work_units", work_units)

    original_constraints = resolver._constraint_conflicts
    def constraints(value, unit):
        collector.counts["gf5_work_units_started"] = (
            collector.counts.get("gf5_work_units_started", 0) + 1
        )
        collector.counts["gf5_current_work_unit_size"] = len(unit.member_ids)
        collector.counts["gf5_slowest_observed_work_unit_size"] = max(
            collector.counts.get("gf5_slowest_observed_work_unit_size", 0),
            len(unit.member_ids),
        )
        collector.checkpoint()
        return original_constraints(value, unit)
    patch(resolver, "_constraint_conflicts", constraints)

    original_requests = resolver._targeted_requests
    def targeted_requests(value, unit, lookup):
        with collector.measure("GF5_TARGETED_PLANNING", checkpoint=True):
            rows = original_requests(value, unit, lookup)
        collector.counts["gf5_targeted_checks_planned"] = (
            collector.counts.get("gf5_targeted_checks_planned", 0) + len(rows)
        )
        collector.checkpoint()
        return rows
    patch(resolver, "_targeted_requests", targeted_requests)

    original_evaluate = resolver.CanonicalEvaluatorTargetedEvidenceProvider.evaluate
    def evaluate(instance, *args, **kwargs):
        collector.counts["gf5_targeted_checks_actual"] = (
            collector.counts.get("gf5_targeted_checks_actual", 0) + 1
        )
        with collector.measure("GF5_TARGETED_EVALUATION"):
            result = original_evaluate(instance, *args, **kwargs)
        if collector.counts["gf5_targeted_checks_actual"] % 10 == 0:
            collector.checkpoint()
        return result
    patch(resolver.CanonicalEvaluatorTargetedEvidenceProvider, "evaluate", evaluate)

    original_candidates = resolver._candidate_groups
    dense_reference_profiled = False
    def candidates(*args, **kwargs):
        nonlocal dense_reference_profiled
        unit = args[1]
        counters = args[4]
        if len(unit.member_ids) == 18 and not dense_reference_profiled:
            dense_reference_profiled = True
            if profile_dense_reference:
                reference_counters = resolver._ExecutionCounters()
                profiler = cProfile.Profile()
                reference_started = time.perf_counter()
                profiler.enable()
                reference_result = resolver._candidate_groups_reference(
                    args[0], unit, args[2], args[3], reference_counters
                )
                profiler.disable()
                stats = pstats.Stats(profiler)
                named = {}
                for (_path, _line, name), values in stats.stats.items():
                    if name in {
                        "_build_group", "fingerprint_payload",
                        "identity_group_hypothesis_fingerprint",
                        "validate_group_hypothesis", "_bridge_summary",
                    }:
                        named[name] = {
                            "calls": values[1],
                            "self_seconds": round(values[2], 6),
                            "cumulative_seconds": round(values[3], 6),
                        }
                collector.counts["gf5_dense_reference_profile"] = {
                    "elapsed_seconds": round(
                        time.perf_counter() - reference_started, 6
                    ),
                    "visited": reference_counters.candidate_partitions_explored,
                    "retained": len(reference_result[0]),
                    "exhausted": reference_result[1],
                    "functions": dict(sorted(named.items())),
                }
                collector.checkpoint()
            repeated = []
            for _ in range(max(1, dense_candidate_repetitions)):
                repeat_counters = resolver._ExecutionCounters()
                repeat_started = time.perf_counter()
                repeat_result = original_candidates(
                    args[0], unit, args[2], args[3], repeat_counters
                )
                repeated.append({
                    "seconds": round(time.perf_counter() - repeat_started, 9),
                    "visited": repeat_counters.candidate_partitions_explored,
                    "retained": len(repeat_result[0]),
                    "exhausted": repeat_result[1],
                    "fingerprints": tuple(
                        item.group.hypothesis_fingerprint for item in repeat_result[0]
                    ),
                })
            collector.counts["gf5_dense_corrected_runs"] = repeated
            collector.checkpoint()
        before = counters.candidate_partitions_explored
        started = time.perf_counter()
        collector.active_sub_stage = "GF5_CANDIDATE_GENERATION"
        collector.counts["gf5_current_candidate_generation_size"] = len(unit.member_ids)
        collector.checkpoint()
        try:
            return original_candidates(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - started
            collector.elapsed["GF5_CANDIDATE_GENERATION"] += elapsed
            collector.calls["GF5_CANDIDATE_GENERATION"] += 1
            explored = counters.candidate_partitions_explored - before
            collector.counts["gf5_candidate_subsets_explored"] = (
                collector.counts.get("gf5_candidate_subsets_explored", 0) + explored
            )
            if elapsed >= collector.counts.get("gf5_slowest_candidate_generation_seconds", 0):
                collector.counts["gf5_slowest_candidate_generation_seconds"] = round(elapsed, 6)
                collector.counts["gf5_slowest_candidate_generation_size"] = len(unit.member_ids)
                collector.counts["gf5_slowest_candidate_generation_edges"] = sum(
                    1 for left, right in combinations(unit.member_ids, 2)
                    if (left, right) in args[2]
                )
                collector.counts["gf5_slowest_candidate_subsets_explored"] = explored
            collector.active_sub_stage = "GF5_GROUP_RESOLUTION"
            collector.checkpoint()
    patch(resolver, "_candidate_groups", candidates)

    original_partition = resolver._select_partition
    def partition(*args, **kwargs):
        with collector.measure("GF5_PARTITION_SEARCH", checkpoint=True):
            result = original_partition(*args, **kwargs)
        collector.counts["gf5_work_units_completed"] = (
            collector.counts.get("gf5_work_units_completed", 0) + 1
        )
        collector.checkpoint()
        return result
    patch(resolver, "_select_partition", partition)

    original_input = identity_resolution_service._resolution_input
    def resolution_input(*args, **kwargs):
        with collector.measure("GF5_INPUT_RECONSTRUCTION", checkpoint=True):
            return original_input(*args, **kwargs)
    patch(identity_resolution_service, "_resolution_input", resolution_input)

    original_persist = identity_resolution_service._persist_result
    def persist_result(*args, **kwargs):
        with collector.measure("GF5_PERSISTENCE", checkpoint=True):
            return original_persist(*args, **kwargs)
    patch(identity_resolution_service, "_persist_result", persist_result)

    original_validate_service = identity_resolution_service.validate_resolution_result
    def validate_service(*args, **kwargs):
        with collector.measure("GF5_VALIDATION", checkpoint=True):
            return original_validate_service(*args, **kwargs)
    patch(identity_resolution_service, "validate_resolution_result", validate_service)

    original_manifest = g2_v2_projection_service.build_g2_v2_manifest
    def manifest(*args, **kwargs):
        with collector.measure("GF6_MANIFEST_BUILD", checkpoint=True):
            return original_manifest(*args, **kwargs)
    patch(g2_v2_projection_service, "build_g2_v2_manifest", manifest)

    original_gf6_persist = g2_v2_projection_service._persist_manifest
    def persist_manifest(*args, **kwargs):
        with collector.measure("GF6_PERSISTENCE", checkpoint=True):
            return original_gf6_persist(*args, **kwargs)
    patch(g2_v2_projection_service, "_persist_manifest", persist_manifest)

    original_gf6_load = g2_v2_projection_service.load_persisted_g2_v2_manifest
    def load_manifest(*args, **kwargs):
        with collector.measure("GF6_RECONSTRUCTION", checkpoint=True):
            return original_gf6_load(*args, **kwargs)
    patch(g2_v2_projection_service, "load_persisted_g2_v2_manifest", load_manifest)

    try:
        yield
    finally:
        if phase["name"] is not None:
            collector.elapsed[phase["name"]] += time.perf_counter() - phase["started"]
            collector.calls[phase["name"]] += 1
        for (owner, name), value in reversed(tuple(originals.items())):
            setattr(owner, name, value)


def _load_real_csv(path: Path) -> tuple[pd.DataFrame, str]:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != EXPECTED_REAL_SHA256:
        raise ValueError("real CSV SHA-256 does not match the authorized target")
    source = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=True)
    mapped, _metadata = apply_column_mapping(source, {})
    validation = validate_dataframe(mapped, [], sensitive_mode=False)
    if validation["missing_required_columns"]:
        raise ValueError("authorized real CSV no longer satisfies required columns")
    if len(mapped) != EXPECTED_REAL_RECORDS:
        raise ValueError("authorized real CSV record count changed")
    return mapped, digest


def run_localization(
    *, csv_path: str | Path, db_path: str | Path,
    checkpoint_path: str | Path | None = None,
    dense_candidate_repetitions: int = 1,
    profile_dense_reference: bool = False,
) -> dict:
    csv = Path(csv_path).resolve()
    database = Path(db_path).resolve()
    if database.exists():
        raise ValueError("localization database path must not already exist")
    database.parent.mkdir(parents=True, exist_ok=True)
    frame, csv_hash = _load_real_csv(csv)
    engine = create_engine(
        f"sqlite:///{database.as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    collector = _Collector(
        Path(checkpoint_path).resolve() if checkpoint_path else None,
        python_profile_enabled=False,
    )
    sql = defaultdict(Counter)

    @event.listens_for(engine, "before_cursor_execute")
    def count_sql(_connection, _cursor, statement, parameters, _context, executemany):
        operation = _operation(statement)
        _parameter_count, batch_size = _parameter_shape(parameters, executemany)
        sql[collector.active_bucket][operation] += 1
        collector.sql[collector.active_bucket][operation] += 1
        collector.sql_total[operation] += 1
        if executemany:
            sql[collector.active_bucket]["EXECUTEMANY"] += 1
            sql[collector.active_bucket]["EXECUTEMANY_ROWS"] += batch_size
        statement_count = sum(
            count for values in sql.values() for key, count in values.items()
            if key not in {"EXECUTEMANY", "EXECUTEMANY_ROWS"}
        )
        collector.counts["sql_statements"] = statement_count
        if statement_count and statement_count % 1000 == 0:
            collector.checkpoint()

    terminal = "FAILED"
    failure = None
    collector.start_pipeline()
    started = time.perf_counter()
    try:
        with ExitStack() as stack:
            stack.enter_context(_instrumented_production_path(
                collector, session, stop_after_discovery=False
            ))
            stack.enter_context(_additional_instrumentation(
                collector,
                dense_candidate_repetitions=dense_candidate_repetitions,
                profile_dense_reference=profile_dense_reference,
            ))
            ScanRunner(session, benchmark_configuration()).run(
                frame,
                "GF-12C1-R3 real runtime localization",
                [],
                60,
                sensitive_mode=False,
                scan_mode="SAME_SITE_DUPLICATE",
            )
        terminal = "COMPLETED"
    except BaseException as exc:
        session.rollback()
        failure = type(exc).__name__.upper()
        terminal = "FAILED"
    elapsed = time.perf_counter() - started
    collector.finish_pipeline(terminal)
    profile = _profile_payload(collector)
    profile["fine_stage_seconds"] = {
        name: round(collector.elapsed[name], 6) for name in (
            "EXACT_DESCRIPTION_CHANNEL", "PART_FAMILY_CHANNEL",
            "LEXICAL_CHANNEL", "CHARACTER_PREPARATION", "TECHNICAL_CHANNEL",
            "FUSION_MATERIALIZATION", "GF5_INPUT_RECONSTRUCTION",
            "GF5_WORK_UNIT_BUILD", "GF5_TARGETED_PLANNING",
            "GF5_TARGETED_EVALUATION", "GF5_CANDIDATE_GENERATION",
            "GF5_PARTITION_SEARCH", "GF5_PERSISTENCE", "GF5_VALIDATION",
            "GF6_MANIFEST_BUILD", "GF6_PERSISTENCE", "GF6_RECONSTRUCTION",
        )
    }
    profile["sql_counts_by_stage"] = {
        key: dict(sorted(value.items())) for key, value in sorted(sql.items())
    }
    result = {
        "contract_version": LOCALIZATION_CONTRACT_VERSION,
        "status": terminal,
        "failure_category": failure,
        "wall_seconds": round(elapsed, 6),
        "real_csv_sha256": csv_hash,
        "provider": "none",
        "provider_calls": sum((
            profile.get("retrieval_counts", {}).get("provider_request_count", 0),
            inspect_database(database).get("discovery", {}).get("provider_calls", 0),
            inspect_database(database).get("gf4", {}).get("provider_calls", 0),
            inspect_database(database).get("gf5", {}).get("provider_calls", 0),
        )),
        "profile": profile,
        "database": inspect_database(database),
        "raw_business_rows_emitted": False,
        "configured_database_accessed": False,
    }
    if checkpoint_path:
        Path(checkpoint_path).write_text(
            json.dumps(result, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    session.close()
    engine.dispose()
    return result


def _worker(arguments: dict, result_path: str):
    result = run_localization(**arguments)
    Path(result_path).write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def execute_bounded_localization(
    *, csv_path: str | Path, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    dense_candidate_repetitions: int = 1,
    profile_dense_reference: bool = False,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="gf12c1-r3-") as directory:
        root = Path(directory)
        database = root / "real-localization.sqlite"
        checkpoint = root / "checkpoint.json"
        result_path = root / "result.json"
        process = multiprocessing.get_context("spawn").Process(
            target=_worker,
            args=({
                "csv_path": str(Path(csv_path).resolve()),
                "db_path": str(database),
                "checkpoint_path": str(checkpoint),
                "dense_candidate_repetitions": dense_candidate_repetitions,
                "profile_dense_reference": profile_dense_reference,
            }, str(result_path)),
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
            return {
                "contract_version": LOCALIZATION_CONTRACT_VERSION,
                "status": "TIMED_OUT",
                "timeout_seconds": timeout_seconds,
                "wall_seconds": round(wall, 6),
                "last_checkpoint": partial,
                "database": inspect_database(database),
                "provider": "none",
                "raw_business_rows_emitted": False,
                "configured_database_accessed": False,
            }
        if process.exitcode != 0 or not result_path.exists():
            return {
                "contract_version": LOCALIZATION_CONTRACT_VERSION,
                "status": "FAILED",
                "failure_category": "LOCALIZATION_PROCESS_EXITED_WITHOUT_RESULT",
                "database": inspect_database(database),
            }
        return json.loads(result_path.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dense-candidate-repetitions", type=int, default=1)
    parser.add_argument("--profile-dense-reference", action="store_true")
    args = parser.parse_args(argv)
    result = execute_bounded_localization(
        csv_path=args.csv,
        timeout_seconds=args.timeout_seconds,
        dense_candidate_repetitions=args.dense_candidate_repetitions,
        profile_dense_reference=args.profile_dense_reference,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result.get("status") == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
