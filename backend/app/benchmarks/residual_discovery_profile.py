"""GF-11B benchmark-only residual discovery attribution.

The profiler wraps the real production discovery path and stops immediately
after the DISCOVERY stage is durably completed. It changes no production
algorithm, persistence representation, batch size, or database contract.
"""

from __future__ import annotations

import cProfile
import hashlib
import json
import multiprocessing
import pstats
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.benchmarks.group_first_scale import benchmark_configuration
from app.benchmarks.group_first_scale_generator import generate_scale_corpus
from app.db.database import Base
from app.db.models import (
    IdentityDiscoveryRun,
    IdentityNeighborProposal,
    IdentityNeighborhoodMember,
    IdentityNeighborhoodSnapshot,
)
from app.orchestration.contracts import ScanStage
from app.engine import candidate_evaluation_features
from app.repositories.discovery_repository import DiscoveryRepository
from app.services import hybrid_retrieval, identity_discovery_service
from app.services import identity_neighborhood_service, scan_runner
from app.services.hybrid_retrieval import SqlAlchemyEmbeddingVectorCache
from app.services.scan_runner import ScanRunner


PROFILE_CONTRACT_VERSION = "gf11b-residual-discovery-profile-v1"
TAXONOMY = (
    "DISCOVERY_FINGERPRINTING",
    "FEATURE_PRECOMPUTATION",
    "STANDARD_BLOCKING",
    "RETRIEVAL_TOTAL",
    "POST_RETRIEVAL_PROPOSAL_MATERIALIZATION",
    "GF2_PROPOSAL_MATERIALIZATION",
    "GF2_PROPOSAL_PERSISTENCE",
    "GF2_TRANSACTION_COMMIT",
    "GF3_NEIGHBORHOOD_CONSTRUCTION",
    "GF3_NEIGHBORHOOD_PERSISTENCE",
    "GF3_TRANSACTION_COMMIT",
    "DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION",
)


class _StopAfterDiscovery(RuntimeError):
    pass


class _Collector:
    def __init__(
        self, checkpoint_path: Path | None = None, *, python_profile_enabled=True
    ):
        self.checkpoint_path = checkpoint_path
        self.discovery_started = None
        self.discovery_seconds = None
        self.retrieval_finished_at = None
        self.post_retrieval_seconds = None
        self.active_sub_stage = "NOT_STARTED"
        self.elapsed = defaultdict(float)
        self.calls = Counter()
        self.sql = defaultdict(Counter)
        self.sql_total = Counter()
        self.sql_event_count = 0
        self.commit_count = Counter()
        self.counts = {}
        self.retrieval = {}
        self.stack = []
        self.profiler = cProfile.Profile()
        self.python_profile_enabled = python_profile_enabled

    @property
    def active_bucket(self):
        return self.stack[-1][0] if self.stack else "OTHER_UNATTRIBUTED"

    def start_discovery(self):
        self.discovery_started = time.perf_counter()
        self.active_sub_stage = "DISCOVERY_FINGERPRINTING"
        if self.python_profile_enabled:
            self.profiler.enable()
        self.checkpoint()

    def finish_discovery(self):
        if self.discovery_started is not None and self.discovery_seconds is None:
            finished = time.perf_counter()
            self.discovery_seconds = finished - self.discovery_started
            if self.retrieval_finished_at is not None:
                self.post_retrieval_seconds = finished - self.retrieval_finished_at
            if self.python_profile_enabled:
                self.profiler.disable()
            self.active_sub_stage = "COMPLETED"
            self.checkpoint()

    @contextmanager
    def measure(self, bucket, *, checkpoint=False):
        previous = self.active_sub_stage
        if checkpoint:
            self.active_sub_stage = bucket
            self.checkpoint()
        started = time.perf_counter()
        self.stack.append((bucket, started))
        try:
            yield
        finally:
            self.stack.pop()
            self.elapsed[bucket] += time.perf_counter() - started
            self.calls[bucket] += 1
            if checkpoint:
                self.active_sub_stage = previous
                self.checkpoint()

    def checkpoint(self):
        if self.checkpoint_path is None:
            return
        payload = {
            "contract_version": PROFILE_CONTRACT_VERSION,
            "status": "COMPLETED" if self.discovery_seconds is not None else "RUNNING",
            "active_sub_stage": self.active_sub_stage,
            "discovery_elapsed_seconds": round(
                self.discovery_seconds
                if self.discovery_seconds is not None
                else (
                    time.perf_counter() - self.discovery_started
                    if self.discovery_started is not None else 0.0
                ),
                6,
            ),
            "bucket_seconds_partial": {
                key: round(value, 6) for key, value in sorted(self.elapsed.items())
            },
            "sql_counts_partial": {
                key: dict(sorted(value.items())) for key, value in sorted(self.sql.items())
            },
            "counts_partial": self.counts,
        }
        self.checkpoint_path.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )


def _operation(statement: str) -> str:
    value = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else "OTHER"
    return value if value in {"SELECT", "INSERT", "UPDATE", "DELETE"} else "OTHER"


def _semantic_fingerprint(values) -> str:
    return hashlib.sha256(json.dumps(
        sorted(values), ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _profile_rows(profiler: cProfile.Profile, limit=20):
    stats = pstats.Stats(profiler)
    rows = []
    for (filename, _line, function), values in stats.stats.items():
        primitive, calls, self_seconds, cumulative_seconds, _callers = values
        module = Path(filename).name if not filename.startswith("~") else "python-runtime"
        rows.append({
            "module": module,
            "function": function,
            "call_count": int(calls),
            "primitive_call_count": int(primitive),
            "self_seconds": round(self_seconds, 6),
            "cumulative_seconds": round(cumulative_seconds, 6),
        })
    by_cumulative = sorted(
        rows, key=lambda item: (-item["cumulative_seconds"], -item["self_seconds"], item["module"], item["function"])
    )[:limit]
    by_self = sorted(
        rows, key=lambda item: (-item["self_seconds"], -item["cumulative_seconds"], item["module"], item["function"])
    )[:limit]
    return {"by_cumulative": by_cumulative, "by_self": by_self}


@contextmanager
def _instrumented_production_path(collector: _Collector, session):
    originals = {}

    def patch(owner, name, replacement):
        originals[(owner, name)] = getattr(owner, name)
        setattr(owner, name, replacement)

    original_start = scan_runner.start_discovery_run
    def start_discovery(*args, **kwargs):
        collector.start_discovery()
        with collector.measure("DISCOVERY_FINGERPRINTING", checkpoint=True):
            return original_start(*args, **kwargs)
    patch(scan_runner, "start_discovery_run", start_discovery)

    original_generate = scan_runner.generate_candidate_pairs
    def generate(*args, **kwargs):
        with collector.measure("STANDARD_BLOCKING", checkpoint=True):
            result = original_generate(*args, **kwargs)
        collector.counts["standard_pair_objects"] = len(result)
        return result
    patch(scan_runner, "generate_candidate_pairs", generate)

    original_score = scan_runner.score_candidate
    state = {
        "retrieval_completed": False,
        "gf3_completed": False,
        "gf3_durable_commit_done": False,
    }
    def score(*args, **kwargs):
        collector.counts["scoring_calls"] = collector.counts.get("scoring_calls", 0) + 1
        if kwargs.get("features_a") is not None and kwargs.get("features_b") is not None:
            collector.counts["feature_reuse_hits"] = (
                collector.counts.get("feature_reuse_hits", 0) + 2
            )
        bucket = (
            "POST_RETRIEVAL_PROPOSAL_MATERIALIZATION"
            if state["retrieval_completed"] else "STANDARD_BLOCKING"
        )
        with collector.measure(bucket):
            return original_score(*args, **kwargs)
    patch(scan_runner, "score_candidate", score)

    original_build_features = scan_runner.build_candidate_evaluation_features
    def build_features(*args, **kwargs):
        collector.counts["feature_bundles_built"] = (
            collector.counts.get("feature_bundles_built", 0) + 1
        )
        with collector.measure("FEATURE_PRECOMPUTATION"):
            result = original_build_features(*args, **kwargs)
        if collector.counts["feature_bundles_built"] % 5000 == 0:
            collector.active_sub_stage = "FEATURE_PRECOMPUTATION"
            collector.checkpoint()
        return result
    patch(scan_runner, "build_candidate_evaluation_features", build_features)

    original_variant_extraction = candidate_evaluation_features.extract_variant_attributes
    def variant_extraction(*args, **kwargs):
        collector.counts["variant_extraction_calls"] = (
            collector.counts.get("variant_extraction_calls", 0) + 1
        )
        return original_variant_extraction(*args, **kwargs)
    patch(candidate_evaluation_features, "extract_variant_attributes", variant_extraction)

    original_retrieve = hybrid_retrieval.HybridCandidateRetriever.retrieve
    def retrieve(instance, *args, **kwargs):
        with collector.measure("RETRIEVAL_TOTAL", checkpoint=True):
            result = original_retrieve(instance, *args, **kwargs)
        state["retrieval_completed"] = True
        collector.retrieval_finished_at = time.perf_counter()
        metrics = result.metrics
        character = result.character_retrieval
        collector.retrieval = {
            "records_indexed": metrics.records_indexed,
            "final_candidates": len(result.candidates),
            "exact_description_candidates": metrics.exact_description_candidates,
            "part_family_candidates": metrics.part_family_candidates,
            "lexical_candidates": metrics.lexical_candidates_generated,
            "char_vector_candidates": metrics.vector_candidates_generated,
            "technical_identity_candidates": metrics.technical_identity_candidates,
            "retrieval_reported_seconds": round(metrics.retrieval_runtime_ms / 1000, 6),
            "character_seconds": round(character.retrieval_time_ms / 1000, 6) if character else 0.0,
            "character_strategy": character.strategy.value if character else "DISABLED",
            "provider_request_count": metrics.provider_request_count,
            "feature_bundles_built": metrics.feature_bundles_built,
            "feature_reuse_hits": metrics.feature_reuse_hits,
            "eligibility_calls": metrics.eligibility_calls,
            "allowed_pair_calls": metrics.allowed_pair_calls,
        }
        collector.counts["feature_reuse_hits"] = (
            collector.counts.get("feature_reuse_hits", 0)
            + metrics.feature_reuse_hits
        )
        collector.counts["fused_final_proposals"] = len(result.candidates)
        collector.checkpoint()
        return result
    patch(hybrid_retrieval.HybridCandidateRetriever, "retrieve", retrieve)

    original_lsh_retrieval = hybrid_retrieval.retrieve_lsh_directed_neighbors
    def lsh_retrieval(*args, **kwargs):
        with collector.measure("CHAR_VECTOR", checkpoint=True):
            return original_lsh_retrieval(*args, **kwargs)
    patch(hybrid_retrieval, "retrieve_lsh_directed_neighbors", lsh_retrieval)

    original_exact_character = hybrid_retrieval._deterministic_directed_neighbors
    def exact_character(*args, **kwargs):
        with collector.measure("CHAR_VECTOR", checkpoint=True):
            return original_exact_character(*args, **kwargs)
    patch(hybrid_retrieval, "_deterministic_directed_neighbors", exact_character)

    original_cache_load = SqlAlchemyEmbeddingVectorCache.load
    def cache_load(instance, *args, **kwargs):
        with collector.measure("RETRIEVAL_CACHE_LOAD", checkpoint=True):
            return original_cache_load(instance, *args, **kwargs)
    patch(SqlAlchemyEmbeddingVectorCache, "load", cache_load)

    original_cache_save = SqlAlchemyEmbeddingVectorCache.save
    def cache_save(instance, *args, **kwargs):
        vectors = args[0] if args else kwargs.get("vectors", {})
        collector.counts["embedding_cache_rows_requested"] = len(vectors)
        with collector.measure("RETRIEVAL_CACHE_SAVE", checkpoint=True):
            return original_cache_save(instance, *args, **kwargs)
    patch(SqlAlchemyEmbeddingVectorCache, "save", cache_save)

    original_nearest = hybrid_retrieval._nearest_pairs
    def nearest(*args, **kwargs):
        with collector.measure("LEXICAL_NEAREST_NEIGHBORS", checkpoint=True):
            return original_nearest(*args, **kwargs)
    patch(hybrid_retrieval, "_nearest_pairs", nearest)

    original_tfidf = hybrid_retrieval.TfidfVectorizer.fit_transform
    def tfidf(instance, *args, **kwargs):
        if not any(bucket == "RETRIEVAL_TOTAL" for bucket, _started in collector.stack):
            return original_tfidf(instance, *args, **kwargs)
        with collector.measure("LEXICAL_VECTORIZATION"):
            return original_tfidf(instance, *args, **kwargs)
    patch(hybrid_retrieval.TfidfVectorizer, "fit_transform", tfidf)

    original_persist = scan_runner.persist_discovery_proposals
    def persist(*args, **kwargs):
        if collector.retrieval_finished_at is not None:
            total_materialization = time.perf_counter() - collector.retrieval_finished_at
            already_measured = collector.elapsed[
                "POST_RETRIEVAL_PROPOSAL_MATERIALIZATION"
            ]
            collector.elapsed["POST_RETRIEVAL_PROPOSAL_MATERIALIZATION"] += max(
                0.0, total_materialization - already_measured
            )
        with collector.measure("GF2_PROPOSAL_TOTAL", checkpoint=True):
            result = original_persist(*args, **kwargs)
        collector.counts["gf2_proposal_rows"] = result.proposal_count
        return result
    patch(scan_runner, "persist_discovery_proposals", persist)

    original_add_proposals = DiscoveryRepository.add_proposals
    def add_proposals(instance, rows):
        collector.counts["gf2_proposal_objects"] = len(rows)
        with collector.measure("GF2_PROPOSAL_PERSISTENCE", checkpoint=True):
            return original_add_proposals(instance, rows)
    patch(DiscoveryRepository, "add_proposals", add_proposals)

    original_plan = identity_neighborhood_service._plan_neighborhoods
    def plan(*args, **kwargs):
        with collector.measure("GF3_NEIGHBORHOOD_PLANNING", checkpoint=True):
            result = original_plan(*args, **kwargs)
        collector.counts["gf3_planned_neighborhoods"] = len(result[0])
        collector.counts["gf3_planned_members"] = sum(
            len(item.selected) + 1 for item in result[0]
        )
        return result
    patch(identity_neighborhood_service, "_plan_neighborhoods", plan)

    original_add_neighborhoods = DiscoveryRepository.add_neighborhoods
    def add_neighborhoods(instance, rows):
        collector.counts["gf3_neighborhood_rows"] = len(rows)
        with collector.measure("GF3_NEIGHBORHOOD_PERSISTENCE", checkpoint=True):
            return original_add_neighborhoods(instance, rows)
    patch(DiscoveryRepository, "add_neighborhoods", add_neighborhoods)

    original_add_members = DiscoveryRepository.add_neighborhood_members
    def add_members(instance, rows):
        collector.counts["gf3_member_rows"] = len(rows)
        with collector.measure("GF3_NEIGHBORHOOD_PERSISTENCE", checkpoint=True):
            return original_add_members(instance, rows)
    patch(DiscoveryRepository, "add_neighborhood_members", add_members)

    original_load_contracts = identity_neighborhood_service._load_contracts
    def load_contracts(*args, **kwargs):
        with collector.measure(
            "DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION", checkpoint=True
        ):
            return original_load_contracts(*args, **kwargs)
    patch(identity_neighborhood_service, "_load_contracts", load_contracts)

    original_build = scan_runner.build_and_persist_identity_neighborhoods
    def build(*args, **kwargs):
        with collector.measure("GF3_NEIGHBORHOOD_TOTAL", checkpoint=True):
            result = original_build(*args, **kwargs)
        state["gf3_completed"] = True
        collector.counts.update({
            "gf3_neighborhoods": result.neighborhood_count,
            "gf3_members": result.member_count,
            "gf3_max_neighborhood_members": result.max_included_member_count,
        })
        return result
    patch(scan_runner, "build_and_persist_identity_neighborhoods", build)

    original_record_stage = scan_runner.record_scan_stage_result
    def record_stage(*args, **kwargs):
        stage = kwargs.get("stage")
        bucket = (
            "DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION"
            if stage == ScanStage.DISCOVERY else collector.active_bucket
        )
        with collector.measure(bucket):
            result = original_record_stage(*args, **kwargs)
        if stage == ScanStage.DISCOVERY:
            collector.finish_discovery()
        return result
    patch(scan_runner, "record_scan_stage_result", record_stage)

    original_evidence_start = scan_runner.start_identity_evidence_run
    def stop_after_discovery(*_args, **_kwargs):
        raise _StopAfterDiscovery("benchmark stopped after completed discovery")
    patch(scan_runner, "start_identity_evidence_run", stop_after_discovery)

    original_commit = session.commit
    def commit():
        if collector.discovery_started is None or collector.discovery_seconds is not None:
            return original_commit()
        if state["gf3_completed"]:
            bucket = (
                "GF3_TRANSACTION_COMMIT"
                if not state["gf3_durable_commit_done"]
                else "DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION"
            )
        else:
            bucket = "GF2_TRANSACTION_COMMIT"
        collector.commit_count[bucket] += 1
        with collector.measure(bucket, checkpoint=True):
            result = original_commit()
        if bucket == "GF3_TRANSACTION_COMMIT":
            state["gf3_durable_commit_done"] = True
        return result
    session.commit = commit

    try:
        yield state
    finally:
        session.commit = original_commit
        for (owner, name), value in reversed(tuple(originals.items())):
            setattr(owner, name, value)


def _decomposition(collector: _Collector):
    elapsed = collector.elapsed
    gf2_total = elapsed["GF2_PROPOSAL_TOTAL"]
    gf2_persistence = elapsed["GF2_PROPOSAL_PERSISTENCE"]
    gf3_total = elapsed["GF3_NEIGHBORHOOD_TOTAL"]
    gf3_persistence = elapsed["GF3_NEIGHBORHOOD_PERSISTENCE"]
    final_validation = elapsed["DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION"]
    values = {
        "DISCOVERY_FINGERPRINTING": elapsed["DISCOVERY_FINGERPRINTING"],
        "FEATURE_PRECOMPUTATION": elapsed["FEATURE_PRECOMPUTATION"],
        "STANDARD_BLOCKING": elapsed["STANDARD_BLOCKING"],
        "RETRIEVAL_TOTAL": elapsed["RETRIEVAL_TOTAL"],
        "POST_RETRIEVAL_PROPOSAL_MATERIALIZATION": elapsed[
            "POST_RETRIEVAL_PROPOSAL_MATERIALIZATION"
        ],
        "GF2_PROPOSAL_MATERIALIZATION": max(0.0, gf2_total - gf2_persistence),
        "GF2_PROPOSAL_PERSISTENCE": gf2_persistence,
        "GF2_TRANSACTION_COMMIT": elapsed["GF2_TRANSACTION_COMMIT"],
        "GF3_NEIGHBORHOOD_CONSTRUCTION": max(
            0.0, gf3_total - gf3_persistence - final_validation
        ),
        "GF3_NEIGHBORHOOD_PERSISTENCE": gf3_persistence,
        "GF3_TRANSACTION_COMMIT": elapsed["GF3_TRANSACTION_COMMIT"],
        "DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION": final_validation,
    }
    total = collector.discovery_seconds or 0.0
    attributed = sum(values.values())
    values["OTHER_UNATTRIBUTED"] = max(0.0, total - attributed)
    rounded = {key: round(values.get(key, 0.0), 6) for key in (*TAXONOMY, "OTHER_UNATTRIBUTED")}
    return rounded, attributed, total


def run_residual_profile(
    *, records: int, seed: int, db_path: str | Path,
    checkpoint_path: str | Path | None = None,
    python_profile_enabled: bool = True,
) -> dict:
    path = Path(db_path).resolve()
    if path.exists():
        raise ValueError("profiling database path must not already exist")
    path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = Path(checkpoint_path).resolve() if checkpoint_path else None
    corpus = generate_scale_corpus(records, seed=seed)
    engine = create_engine(
        f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    collector = _Collector(
        checkpoint, python_profile_enabled=python_profile_enabled
    )

    @event.listens_for(engine, "before_cursor_execute")
    def count_sql(_connection, _cursor, statement, _parameters, _context, executemany):
        if collector.discovery_started is None or collector.discovery_seconds is not None:
            return
        operation = _operation(statement)
        bucket = collector.active_bucket
        collector.sql[bucket][operation] += 1
        collector.sql_total[operation] += 1
        collector.sql_event_count += 1
        if executemany:
            collector.sql[bucket]["EXECUTEMANY"] += 1
            collector.sql_total["EXECUTEMANY"] += 1
        if collector.sql_event_count % 1000 == 0:
            collector.checkpoint()

    forced_error = None
    try:
        with _instrumented_production_path(collector, session):
            try:
                ScanRunner(session, benchmark_configuration()).run(
                    corpus.records,
                    f"GF-11B residual profile {records}",
                    [],
                    60,
                    sensitive_mode=False,
                    scan_mode="DISCOVERY",
                )
            except _StopAfterDiscovery:
                pass
            except Exception as exc:  # safe type only; never serialize raw text
                forced_error = type(exc).__name__
    finally:
        if collector.python_profile_enabled:
            collector.profiler.disable()

    run = session.query(IdentityDiscoveryRun).one_or_none()
    proposal_rows = session.query(IdentityNeighborProposal).order_by(
        IdentityNeighborProposal.proposal_order
    ).all()
    neighborhood_rows = session.query(IdentityNeighborhoodSnapshot).order_by(
        IdentityNeighborhoodSnapshot.anchor_record_id
    ).all()
    member_count = session.query(IdentityNeighborhoodMember).count()
    decomposition, attributed, total = _decomposition(collector)
    post_retrieval = collector.post_retrieval_seconds or 0.0
    attributed_post = sum(
        value for key, value in decomposition.items()
        if key in {
            "POST_RETRIEVAL_PROPOSAL_MATERIALIZATION",
            "GF2_PROPOSAL_MATERIALIZATION",
            "GF2_PROPOSAL_PERSISTENCE",
            "GF3_NEIGHBORHOOD_CONSTRUCTION",
            "GF3_NEIGHBORHOOD_PERSISTENCE",
            "GF3_TRANSACTION_COMMIT",
            "DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION",
        }
    )
    result = {
        "contract_version": PROFILE_CONTRACT_VERSION,
        "status": "COMPLETED" if collector.discovery_seconds is not None else "FAILED",
        "safe_failure_category": forced_error,
        "records": records,
        "seed": seed,
        "active_sub_stage": collector.active_sub_stage,
        "discovery_total_seconds": round(total, 6),
        "timing_decomposition_seconds": decomposition,
        "attributed_percent": round(100 * attributed / total, 4) if total else 0.0,
        "post_retrieval_attributed_percent": (
            round(100 * attributed_post / post_retrieval, 4)
            if post_retrieval else 100.0
        ),
        "post_retrieval_total_seconds": round(post_retrieval, 6),
        "post_retrieval_other_unattributed_seconds": round(
            max(0.0, post_retrieval - attributed_post), 6
        ),
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
        "retrieval_counts": collector.retrieval,
        "object_counts": collector.counts,
        "sql_counts_by_bucket": {
            key: dict(sorted(value.items())) for key, value in sorted(collector.sql.items())
        },
        "sql_counts_total": dict(sorted(collector.sql_total.items())),
        "commit_counts": dict(sorted(collector.commit_count.items())),
        "proposal_row_count": len(proposal_rows),
        "neighborhood_row_count": len(neighborhood_rows),
        "member_row_count": member_count,
        "proposal_semantic_fingerprint": _semantic_fingerprint(
            (row.proposal_order, row.proposal_key) for row in proposal_rows
        ),
        "neighborhood_semantic_fingerprint": _semantic_fingerprint(
            (row.anchor_record_id, row.neighborhood_fingerprint) for row in neighborhood_rows
        ),
        "discovery_run_status": run.status if run else None,
        "provider_request_count": run.provider_request_count if run else 0,
        "python_profile": (
            _profile_rows(collector.profiler)
            if python_profile_enabled else {"by_cumulative": [], "by_self": []}
        ),
        "python_profile_enabled": python_profile_enabled,
        "database_is_disposable": True,
        "raw_sql_parameters_captured": False,
    }
    if checkpoint:
        checkpoint.write_text(
            json.dumps(result, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
    session.close()
    engine.dispose()
    return result


def _child_profile(queue, values):
    try:
        queue.put(run_residual_profile(**values))
    except BaseException as exc:
        queue.put({
            "contract_version": PROFILE_CONTRACT_VERSION,
            "status": "FAILED",
            "safe_failure_category": type(exc).__name__,
        })


def timeout_result(partial: dict, *, timeout_seconds: float, wall_seconds: float) -> dict:
    result = dict(partial)
    result.update({
        "contract_version": PROFILE_CONTRACT_VERSION,
        "status": "TIMED_OUT",
        "timeout_seconds": timeout_seconds,
        "bounded_wall_seconds": round(wall_seconds, 6),
    })
    if result.get("active_sub_stage") == "COMPLETED":
        result["active_sub_stage"] = "REPORT_FINALIZATION_AFTER_DISCOVERY"
    elif result.get("active_sub_stage") in {None, "NOT_STARTED"}:
        result["active_sub_stage"] = "UNKNOWN_ACTIVE_SUB_STAGE"
    return result


def run_bounded_residual_profile(
    *, records: int, seed: int = 1101, timeout_seconds: float = 300.0,
    python_profile_enabled: bool = True,
) -> dict:
    with tempfile.TemporaryDirectory(prefix="gf11b-residual-") as directory:
        root = Path(directory)
        checkpoint = root / "checkpoint.json"
        values = {
            "records": records,
            "seed": seed,
            "db_path": root / "profile.db",
            "checkpoint_path": checkpoint,
            "python_profile_enabled": python_profile_enabled,
        }
        context = multiprocessing.get_context("spawn")
        queue = context.Queue(maxsize=1)
        process = context.Process(target=_child_profile, args=(queue, values))
        started = time.perf_counter()
        process.start()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join()
            partial = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
            return timeout_result(
                partial,
                timeout_seconds=timeout_seconds,
                wall_seconds=time.perf_counter() - started,
            )
        if not queue.empty():
            return queue.get()
        return {
            "contract_version": PROFILE_CONTRACT_VERSION,
            "status": "FAILED",
            "safe_failure_category": "PROFILE_PROCESS_EXITED_WITHOUT_RESULT",
        }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=1101)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--no-python-profile", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = run_bounded_residual_profile(
        records=args.records,
        seed=args.seed,
        timeout_seconds=args.timeout_seconds,
        python_profile_enabled=not args.no_python_profile,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result.get("status") == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
