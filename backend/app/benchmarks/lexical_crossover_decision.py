"""Benchmark-only GF-11C crossover and degradation policy evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np

from app.benchmarks.exact_indexed_lexical import _inputs
from app.benchmarks.rarity_aware_lexical_decision import (
    RarityConfiguration,
    _exact_rerank_batch,
    _rank_features,
    _stable_inputs,
    retrieve_bounded_rarity_candidates,
)
from app.services.lexical_retrieval import (
    IndexedLexicalResult,
    LexicalRetrievalWorkMetrics,
    retrieve_exact_indexed_lexical_neighbors,
)


STRATEGY_VERSION = "lexical-retrieval-strategy-decision-v1"
EXACT = "EXACT_INDEXED_V4"
BOUNDED = "BOUNDED_RARITY_AWARE_V1"
PRIMARY = RarityConfiguration(
    "R2", "P1_RAREST", 80, 32, visit_budget=4096, batch_size=64
)
SECOND_PASS = RarityConfiguration(
    "R2", "P1_RAREST", 80, 32, visit_budget=16384, batch_size=64
)
INSUFFICIENT = "LEXICAL_CANDIDATE_POOL_INSUFFICIENT"
REASON_PRECEDENCE = (
    "NO_ELIGIBLE_BOUNDED_POSTING",
    "LEGITIMATELY_FEWER_POSITIVE_NEIGHBORS",
    "VISIT_BUDGET_EXHAUSTED",
    "FEATURE_LIMIT_EXHAUSTED",
    "DUPLICATE_CANDIDATE_COLLAPSE",
    "TOO_FEW_UNIQUE_CANDIDATES",
    "OTHER",
)


@dataclass(frozen=True)
class CrossoverObservation:
    records: int
    strategy: str
    lexical_seconds: float
    status: str = "COMPLETED"


def select_activation_threshold(observations, *, advantage=0.20):
    """Choose the smallest scale with two runs and a stable >=20% advantage."""
    grouped = {}
    for item in observations:
        grouped.setdefault((item.records, item.strategy), []).append(item)
    for records in sorted({item.records for item in observations}):
        exact = grouped.get((records, EXACT), ())
        bounded = grouped.get((records, BOUNDED), ())
        if len(exact) < 2 or len(bounded) < 2:
            continue
        if any(item.status != "COMPLETED" for item in (*exact, *bounded)):
            continue
        exact_median = statistics.median(item.lexical_seconds for item in exact)
        bounded_median = statistics.median(item.lexical_seconds for item in bounded)
        if bounded_median <= exact_median * (1 - advantage):
            return records
    return None


def _description_bucket(value):
    length = len(str(value or "").strip())
    if length == 0:
        return "EMPTY"
    if length <= 16:
        return "1_16"
    if length <= 48:
        return "17_48"
    if length <= 96:
        return "49_96"
    return "97_PLUS"


def _feature_bucket(count):
    if count == 0:
        return "0"
    if count <= 8:
        return "1_8"
    if count <= 16:
        return "9_16"
    if count <= 32:
        return "17_32"
    return "33_PLUS"


def classify_insufficient_reason(*, selected_features, candidate_count,
                                 skipped_for_budget, feature_limit_exhausted,
                                 duplicate_collapse, exact_positive_count=None):
    facts = {
        "NO_ELIGIBLE_BOUNDED_POSTING": selected_features == 0,
        "LEGITIMATELY_FEWER_POSITIVE_NEIGHBORS": (
            exact_positive_count is not None and exact_positive_count < 5
        ),
        "VISIT_BUDGET_EXHAUSTED": skipped_for_budget > 0,
        "FEATURE_LIMIT_EXHAUSTED": feature_limit_exhausted,
        "DUPLICATE_CANDIDATE_COLLAPSE": duplicate_collapse,
        "TOO_FEW_UNIQUE_CANDIDATES": candidate_count < 5,
        "OTHER": True,
    }
    return next(reason for reason in REASON_PRECEDENCE if facts[reason])


def characterize_insufficient_anchors(records, *, seed=1101, exact_reference=False):
    """Return aggregate-only diagnostics; no record values or identities escape."""
    corpus, matrix, refs = _inputs(records, seed)
    stable, _stable_refs, original_positions = _stable_inputs(matrix, refs)
    csc = stable.tocsc(copy=False)
    posting_sizes = np.diff(csc.indptr).astype(np.int64, copy=False)
    exact_counts = None
    if exact_reference:
        exact = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
        inverse_positions = np.empty(len(original_positions), dtype=np.int64)
        inverse_positions[original_positions] = np.arange(len(original_positions))
        exact_counts = {
            int(inverse_positions[source]): len(rows)
            for source, rows in exact.directed_neighbors.items()
        }
    counts = Counter()
    reasons = Counter()
    descriptions = Counter()
    feature_counts = Counter()
    selected_values, skipped_values = [], []
    exhausted_features = exhausted_budget = 0
    insufficient_recall_numerator = insufficient_recall_denominator = 0
    exact_positive_distribution = Counter()
    for source in range(stable.shape[0]):
        left, right = stable.indptr[source:source + 2]
        features = stable.indices[left:right]
        ranked_features, _weights, ranked_sizes = _rank_features(
            features, stable.data[left:right], posting_sizes, "P1_RAREST"
        )
        remaining, selected, skipped = 4096, 0, 0
        postings = []
        for feature, size in zip(ranked_features[:32], ranked_sizes[:32]):
            if size > remaining:
                skipped += 1
                continue
            pleft, pright = csc.indptr[feature:feature + 2]
            postings.append(csc.indices[pleft:pright])
            remaining -= int(size)
            selected += 1
        candidates = np.unique(np.concatenate(postings)) if postings else np.empty(0, dtype=np.int64)
        count = int(np.count_nonzero(candidates != source))
        if count >= 5:
            continue
        counts["zero" if count == 0 else "one_to_four"] += 1
        selected_values.append(selected)
        skipped_values.append(skipped)
        exhausted_features += int(len(features) > 32)
        exhausted_budget += int(skipped > 0)
        original = int(original_positions[source])
        descriptions[_description_bucket(corpus.records.iloc[original].get("DESCRIPTION"))] += 1
        feature_counts[_feature_bucket(len(features))] += 1
        exact_count = exact_counts.get(source) if exact_counts is not None else None
        reason = classify_insufficient_reason(
            selected_features=selected, candidate_count=count,
            skipped_for_budget=skipped, feature_limit_exhausted=len(features) > 32,
            duplicate_collapse=sum(len(item) for item in postings) > count + 1,
            exact_positive_count=exact_count,
        )
        reasons[reason] += 1
        if exact_count is not None:
            exact_positive_distribution[str(exact_count)] += 1
            insufficient_recall_numerator += min(count, exact_count)
            insufficient_recall_denominator += exact_count
    insufficient = sum(counts.values())
    return {
        "records": records,
        "insufficient_anchor_count": insufficient,
        "insufficient_anchor_rate": insufficient / max(1, records),
        "candidate_count_distribution": {
            "zero": counts["zero"], "one_to_four": counts["one_to_four"],
            "five_to_79": 0,
        },
        "description_length_buckets": dict(sorted(descriptions.items())),
        "tfidf_feature_count_buckets": dict(sorted(feature_counts.items())),
        "selected_eligible_features": {
            "minimum": min(selected_values, default=0),
            "median": statistics.median(selected_values) if selected_values else 0,
            "maximum": max(selected_values, default=0),
        },
        "postings_skipped_for_budget": sum(skipped_values),
        "anchors_exhausting_feature_limit": exhausted_features,
        "anchors_exhausting_visit_budget": exhausted_budget,
        "reason_distribution": dict(sorted(reasons.items())),
        "exact_reference_available": exact_reference,
        "exact_positive_neighbor_count_distribution": dict(
            sorted(exact_positive_distribution.items())
        ),
        "insufficient_anchor_lexical_recall": (
            insufficient_recall_numerator / insufficient_recall_denominator
            if insufficient_recall_denominator else None
        ),
        "provider_request_count": 0,
    }


def run_isolated_strategy(records, strategy, *, seed=1101):
    started = time.perf_counter()
    _corpus, matrix, refs = _inputs(records, seed)
    tfidf = time.perf_counter() - started
    lexical_started = time.perf_counter()
    if strategy == EXACT:
        result = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
        metrics = asdict(result.metrics)
    elif strategy == BOUNDED:
        result = retrieve_bounded_rarity_candidates(matrix, refs, 5, PRIMARY)
        metrics = asdict(result.metrics)
    else:
        raise ValueError("unsupported lexical strategy")
    return {
        "status": "COMPLETED", "records": records, "strategy": strategy,
        "tfidf_seconds": round(tfidf, 6),
        "lexical_seconds": round(time.perf_counter() - lexical_started, 6),
        "wall_seconds": round(time.perf_counter() - started, 6),
        "metrics": metrics, "provider_request_count": 0,
    }


def retrieve_selected_bounded_lexical(matrix, refs, top_k):
    """Apply the frozen primary and fixed second pass only to insufficient anchors."""
    primary = retrieve_bounded_rarity_candidates(matrix, refs, top_k, PRIMARY)
    insufficient_original = sorted(
        source for source, rows in primary.directed_neighbors.items()
        if len(rows) < top_k
    )
    stable, stable_refs, original_positions = _stable_inputs(matrix, refs)
    inverse_positions = np.empty(len(original_positions), dtype=np.int64)
    inverse_positions[original_positions] = np.arange(len(original_positions))
    insufficient_stable = sorted(
        int(inverse_positions[source]) for source in insufficient_original
    )
    csc = stable.tocsc(copy=False)
    posting_sizes = np.diff(csc.indptr).astype(np.int64, copy=False)
    pools = []
    raw_visits = unique_candidates = 0
    candidate_started = time.perf_counter()
    for source in insufficient_stable:
        left, right = stable.indptr[source:source + 2]
        features, weights, sizes = _rank_features(
            stable.indices[left:right], stable.data[left:right],
            posting_sizes, SECOND_PASS.ranking_policy,
        )
        remaining, target_parts, value_parts = SECOND_PASS.visit_budget, [], []
        for feature, weight, size in zip(
            features[:SECOND_PASS.feature_limit],
            weights[:SECOND_PASS.feature_limit],
            sizes[:SECOND_PASS.feature_limit],
        ):
            if size > remaining:
                continue
            pleft, pright = csc.indptr[feature:feature + 2]
            target_parts.append(csc.indices[pleft:pright])
            value_parts.append(weight * csc.data[pleft:pright])
            raw_visits += int(size)
            remaining -= int(size)
        if target_parts:
            targets = np.concatenate(target_parts)
            values = np.concatenate(value_parts)
            unique, inverse = np.unique(targets, return_inverse=True)
            support = np.zeros(len(unique), dtype=np.float64)
            np.add.at(support, inverse, values)
            keep = unique != source
            unique, support = unique[keep], support[keep]
            positive = support > 0
            unique, support = unique[positive], support[positive]
            unique_candidates += len(unique)
            order = np.lexsort((unique, -support))[:SECOND_PASS.candidate_pool]
            pool = unique[order]
        else:
            pool = np.empty(0, dtype=np.int64)
        pools.append(pool)
    candidate_seconds = time.perf_counter() - candidate_started
    rerank_started = time.perf_counter()
    second_directed = {}
    for offset in range(0, len(insufficient_stable), SECOND_PASS.batch_size):
        sources = insufficient_stable[offset:offset + SECOND_PASS.batch_size]
        second_directed.update(_exact_rerank_batch(
            stable, stable_refs, sources,
            pools[offset:offset + SECOND_PASS.batch_size], top_k,
        ))
    rerank_seconds = time.perf_counter() - rerank_started
    directed = dict(primary.directed_neighbors)
    for source, rows in second_directed.items():
        directed[int(original_positions[source])] = tuple(
            (int(original_positions[target]), score) for target, score in rows
        )
    remaining = sum(len(directed[source]) < top_k for source in insufficient_original)
    exact_reranks = sum(len(pool) for pool in pools)
    total_pairs = len(refs) * max(0, len(refs) - 1)
    policy_fingerprint = hashlib.sha256(json.dumps({
        "primary": PRIMARY.__dict__, "second_pass": SECOND_PASS.__dict__,
        "top_k": top_k,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    metrics = primary.metrics
    result = IndexedLexicalResult(directed, LexicalRetrievalWorkMetrics(
        strategy="BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS",
        contract_fingerprint=policy_fingerprint,
        feature_count=matrix.shape[1], posting_entry_count=matrix.nnz,
        posting_size_p50=0, posting_size_p95=0, posting_size_p99=0,
        max_posting_size=0,
        candidate_union_enumerations=metrics.raw_posting_visits + raw_visits,
        unique_directed_candidates=(
            metrics.unique_candidate_accumulations + unique_candidates
        ),
        exact_score_evaluations=metrics.exact_rerank_evaluations + exact_reranks,
        theoretical_brute_directed_comparisons=total_pairs,
        zero_overlap_comparisons_avoided=max(
            0, total_pairs - metrics.exact_rerank_evaluations - exact_reranks
        ),
        max_anchor_candidate_union=max(
            metrics.maximum_candidate_pool, max((len(pool) for pool in pools), default=0)
        ),
        index_build_time_ms=0.0,
        query_scoring_time_ms=(
            metrics.total_seconds + candidate_seconds + rerank_seconds
        ) * 1000,
    ))
    diagnostics = {
        "primary_insufficient": len(insufficient_original),
        "second_pass_recovered": len(insufficient_original) - remaining,
        "remaining_insufficient": remaining,
        "second_pass_posting_visits": raw_visits,
        "second_pass_exact_reranks": exact_reranks,
        "second_pass_candidate_seconds": round(candidate_seconds, 6),
        "second_pass_rerank_seconds": round(rerank_seconds, 6),
        "second_pass_total_seconds": round(candidate_seconds + rerank_seconds, 6),
    }
    return result, diagnostics


def _selected_lexical_adapter(diagnostics):
    def adapter(matrix, refs, top_k):
        result, values = retrieve_selected_bounded_lexical(matrix, refs, top_k)
        diagnostics.update(values)
        return result
    return adapter


def run_full_discovery(records, strategy, *, seed=1101):
    """Run the normal production discovery boundary on a disposable database."""
    from pathlib import Path
    from app.benchmarks.residual_discovery_profile import run_residual_profile
    from app.services import hybrid_retrieval

    original = hybrid_retrieval.retrieve_production_lexical_neighbors
    second_pass = {}
    try:
        if strategy == EXACT:
            hybrid_retrieval.retrieve_production_lexical_neighbors = (
                retrieve_exact_indexed_lexical_neighbors
            )
        elif strategy != BOUNDED:
            raise ValueError("unsupported lexical strategy")
        with tempfile.TemporaryDirectory(prefix="gf11c-cross-discovery-") as directory:
            result = run_residual_profile(
                records=records, seed=seed,
                db_path=Path(directory) / "discovery.sqlite",
                python_profile_enabled=False,
            )
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
    result["strategy"] = strategy
    retrieval = result.get("retrieval_counts", {})
    result["second_pass"] = {
        "primary_insufficient": retrieval.get("lexical_primary_insufficient_anchors", 0),
        "second_pass_recovered": retrieval.get("lexical_second_pass_recovered_anchors", 0),
        "remaining_insufficient": retrieval.get("lexical_remaining_insufficient_anchors", 0),
        "second_pass_posting_visits": retrieval.get("lexical_second_pass_posting_visits", 0),
        "second_pass_exact_reranks": retrieval.get("lexical_second_pass_exact_reranks", 0),
        "second_pass_total_seconds": retrieval.get("lexical_second_pass_seconds", 0.0),
    }
    return result


def run_selected_product_comparison(records, *, seed=1101):
    """Compare aggregate product coverage without exposing corpus record data."""
    from app.benchmarks.character_retrieval_contract import _coverage
    from app.benchmarks.contracts import stable_fingerprint
    from app.benchmarks.group_first_scale import benchmark_configuration
    from app.services import hybrid_retrieval
    from app.services.canonical_record_service import canonical_record_ref_key
    from app.services.hybrid_retrieval import (
        CANONICAL_RECORD_REF_FIELD,
        HybridCandidateRetriever,
        MemoryEmbeddingVectorCache,
    )

    corpus, _matrix, _refs = _inputs(records, seed)
    data = corpus.records.copy()
    data[CANONICAL_RECORD_REF_FIELD] = tuple(
        canonical_record_ref_key(1, index) for index in range(records)
    )
    original = hybrid_retrieval.retrieve_production_lexical_neighbors
    second_pass = {}
    try:
        hybrid_retrieval.retrieve_production_lexical_neighbors = (
            retrieve_exact_indexed_lexical_neighbors
        )
        exact = HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
        selected = HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
    exact_pairs = {
        tuple(sorted((item.left_record_id, item.right_record_id)))
        for item in exact.candidates
    }
    selected_pairs = {
        tuple(sorted((item.left_record_id, item.right_record_id)))
        for item in selected.candidates
    }
    generic = {
        index for index, code in enumerate(corpus.truth.scenario_by_source_row)
        if code == "S3"
    }
    def generic_hubs(pairs):
        return sum(left in generic and right in generic for left, right in pairs)
    return {
        "records": records,
        "exact_final_hybrid_count": len(exact_pairs),
        "selected_final_hybrid_count": len(selected_pairs),
        "exact_pair_fingerprint": stable_fingerprint(sorted(exact_pairs)),
        "selected_pair_fingerprint": stable_fingerprint(sorted(selected_pairs)),
        "final_hybrid_jaccard": round(
            len(exact_pairs & selected_pairs) /
            max(1, len(exact_pairs | selected_pairs)), 9
        ),
        "exact_coverage": _coverage(exact_pairs, corpus.truth),
        "selected_coverage": _coverage(selected_pairs, corpus.truth),
        "exact_generic_hub_pairs": generic_hubs(exact_pairs),
        "selected_generic_hub_pairs": generic_hubs(selected_pairs),
        "second_pass": {
            "primary_insufficient": selected.lexical_retrieval.primary_insufficient_anchors,
            "second_pass_recovered": selected.lexical_retrieval.second_pass_recovered_anchors,
            "remaining_insufficient": selected.lexical_retrieval.remaining_insufficient_anchors,
            "second_pass_posting_visits": selected.lexical_retrieval.second_pass_posting_visits,
            "second_pass_exact_reranks": selected.lexical_retrieval.second_pass_exact_reranks,
            "second_pass_total_seconds": round(selected.lexical_retrieval.second_pass_time_ms / 1000, 6),
        },
        "provider_request_count": (
            exact.metrics.provider_request_count + selected.metrics.provider_request_count
        ),
    }


def run_cache_load_operation(records):
    """Measure the corrected cache lookup on an empty disposable SQLite database."""
    from pathlib import Path
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from app.db.models import LocalEmbeddingCache
    from app.services.hybrid_retrieval import SqlAlchemyEmbeddingVectorCache

    with tempfile.TemporaryDirectory(prefix="gf11c-op50-cache-") as directory:
        path = Path(directory) / "cache.sqlite"
        engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        LocalEmbeddingCache.__table__.create(engine)
        session = sessionmaker(bind=engine)()
        parameter_counts = []
        statement_count = 0

        @event.listens_for(engine, "before_cursor_execute")
        def observe(_connection, _cursor, statement, parameters, _context, _executemany):
            nonlocal statement_count
            if (
                statement.lstrip().upper().startswith("SELECT")
                and "local_embedding_cache" in statement.lower()
            ):
                statement_count += 1
                parameter_counts.append(len(parameters))

        fingerprints = [
            hashlib.sha256(f"op50-{index}".encode("ascii")).hexdigest()
            for index in range(records)
        ]
        started = time.perf_counter()
        loaded = SqlAlchemyEmbeddingVectorCache(session).load(
            fingerprints, "op50-benchmark-model"
        )
        wall_seconds = time.perf_counter() - started
        transaction_active = session.in_transaction()
        session.close()
        engine.dispose()
    return {
        "status": "COMPLETED",
        "input_item_count": records,
        "operation": "SELECT",
        "sql_statement_count": statement_count,
        "parameters_per_statement_min": min(parameter_counts, default=0),
        "parameters_per_statement_max": max(parameter_counts, default=0),
        "last_statement_parameter_count": parameter_counts[-1] if parameter_counts else 0,
        "rows_per_batch_max": 900,
        "number_of_batches": statement_count,
        "rows_returned": len(loaded),
        "commit_count": 0,
        "transaction_was_active_before_close": transaction_active,
        "wall_seconds": round(wall_seconds, 6),
        "database_is_disposable": True,
        "provider_request_count": 0,
        "raw_sql_parameters_captured": False,
    }


def run_production_lexical_operation(records, *, seed=1101):
    """Exercise only the selected production lexical boundary; no database."""
    from app.services.lexical_retrieval import retrieve_production_lexical_neighbors

    started = time.perf_counter()
    _corpus, matrix, refs = _inputs(records, seed)
    input_seconds = time.perf_counter() - started
    lexical_started = time.perf_counter()
    result = retrieve_production_lexical_neighbors(matrix, refs, 5)
    return {
        "status": "COMPLETED",
        "records": records,
        "strategy": result.metrics.strategy,
        "tfidf_seconds": round(input_seconds, 6),
        "lexical_seconds": round(time.perf_counter() - lexical_started, 6),
        "metrics": asdict(result.metrics),
        "provider_request_count": 0,
        "database_opened": False,
    }


def degraded_anchor_result(diagnostics):
    return {"status": "COMPLETED_DEGRADED", "reason": INSUFFICIENT,
            "affected_anchors": diagnostics["insufficient_anchor_count"]}


def typed_failure_result(diagnostics):
    return {"status": "FAILED", "safe_failure_category": INSUFFICIENT,
            "affected_anchors": diagnostics["insufficient_anchor_count"]}


def second_pass_bound(*, anchors, visit_budget, candidate_pool=80):
    return {"maximum_posting_visits": anchors * visit_budget,
            "maximum_exact_reranks": anchors * candidate_pool}


def run_second_pass(records, *, visit_budget, feature_limit=32, seed=1101):
    """Measure one fixed second pass for primary-insufficient anchors only."""
    _corpus, matrix, refs = _inputs(records, seed)
    stable, stable_refs, _positions = _stable_inputs(matrix, refs)
    csc = stable.tocsc(copy=False)
    posting_sizes = np.diff(csc.indptr).astype(np.int64, copy=False)
    insufficient = []
    for source in range(records):
        left, right = stable.indptr[source:source + 2]
        features, _weights, sizes = _rank_features(
            stable.indices[left:right], stable.data[left:right], posting_sizes, "P1_RAREST"
        )
        remaining, postings = 4096, []
        for feature, size in zip(features[:32], sizes[:32]):
            if size > remaining:
                continue
            pleft, pright = csc.indptr[feature:feature + 2]
            postings.append(csc.indices[pleft:pright])
            remaining -= int(size)
        candidates = np.unique(np.concatenate(postings)) if postings else np.empty(0, dtype=np.int64)
        if np.count_nonzero(candidates != source) < 5:
            insufficient.append(source)
    started = time.perf_counter()
    raw_visits, pool_sizes, pools = 0, [], []
    for source in insufficient:
        left, right = stable.indptr[source:source + 2]
        features, weights, sizes = _rank_features(
            stable.indices[left:right], stable.data[left:right], posting_sizes, "P1_RAREST"
        )
        remaining, targets_parts, value_parts = visit_budget, [], []
        for feature, weight, size in zip(features[:feature_limit], weights[:feature_limit], sizes[:feature_limit]):
            if size > remaining:
                continue
            pleft, pright = csc.indptr[feature:feature + 2]
            targets_parts.append(csc.indices[pleft:pright])
            value_parts.append(weight * csc.data[pleft:pright])
            raw_visits += int(size)
            remaining -= int(size)
        if targets_parts:
            targets = np.concatenate(targets_parts)
            values = np.concatenate(value_parts)
            unique, inverse = np.unique(targets, return_inverse=True)
            support = np.zeros(len(unique), dtype=np.float64)
            np.add.at(support, inverse, values)
            keep = unique != source
            unique, support = unique[keep], support[keep]
            order = np.lexsort((unique, -support))[:80]
            pool = unique[order]
        else:
            pool = np.empty(0, dtype=np.int64)
        pools.append(pool)
        pool_sizes.append(len(pool))
    candidate_seconds = time.perf_counter() - started
    rerank_started = time.perf_counter()
    for offset in range(0, len(insufficient), 64):
        sources = insufficient[offset:offset + 64]
        _exact_rerank_batch(stable, stable_refs, sources, pools[offset:offset + 64], 5)
    rerank_seconds = time.perf_counter() - rerank_started
    return {
        "records": records, "anchors_entering_second_pass": len(insufficient),
        "anchors_still_insufficient": sum(size < 5 for size in pool_sizes),
        "visit_budget": visit_budget, "feature_limit": feature_limit,
        "extra_posting_visits": raw_visits, "extra_exact_reranks": sum(pool_sizes),
        "candidate_seconds": round(candidate_seconds, 6),
        "rerank_seconds": round(rerank_seconds, 6),
        "extra_seconds": round(candidate_seconds + rerank_seconds, 6),
        "provider_request_count": 0,
    }


def timeout_result(*, records, strategy, timeout_seconds, wall_seconds, stage):
    return {"status": "TIMED_OUT", "records": records, "strategy": strategy,
            "active_stage": stage, "timeout_seconds": timeout_seconds,
            "wall_seconds": wall_seconds, "provider_request_count": 0}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--strategy", choices=(EXACT, BOUNDED), default=BOUNDED)
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--exact-reference", action="store_true")
    parser.add_argument("--second-pass-budget", type=int)
    parser.add_argument("--second-pass-features", type=int, default=32)
    parser.add_argument("--full-discovery", action="store_true")
    parser.add_argument("--product-comparison", action="store_true")
    parser.add_argument("--cache-operation", action="store_true")
    parser.add_argument("--production-lexical", action="store_true")
    args = parser.parse_args(argv)
    result = (run_production_lexical_operation(
        args.records
    ) if args.production_lexical else run_cache_load_operation(
        args.records
    ) if args.cache_operation else run_selected_product_comparison(
        args.records
    ) if args.product_comparison else run_full_discovery(
        args.records, args.strategy
    ) if args.full_discovery else run_second_pass(
        args.records, visit_budget=args.second_pass_budget,
        feature_limit=args.second_pass_features,
    ) if args.second_pass_budget else characterize_insufficient_anchors(
        args.records, exact_reference=args.exact_reference
    ) if args.diagnostics else run_isolated_strategy(args.records, args.strategy))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
