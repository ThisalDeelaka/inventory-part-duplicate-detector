"""Benchmark-only GF-11C-ARCH2 bounded rarity-aware lexical experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass

import numpy as np
from sklearn.preprocessing import normalize

from app.benchmarks.character_retrieval_contract import _coverage
from app.benchmarks.contracts import stable_fingerprint
from app.benchmarks.exact_indexed_lexical import _inputs
from app.benchmarks.group_first_scale import benchmark_configuration
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    MemoryEmbeddingVectorCache,
    _directed_neighbors_to_pairs,
)
from app.services.lexical_retrieval import (
    IndexedLexicalResult,
    LexicalRetrievalWorkMetrics,
    _canonical_top_k_positions,
    lexical_retrieval_contract_fingerprint,
    retrieve_exact_indexed_lexical_neighbors,
)


ALGORITHM_VERSION = "bounded-rarity-aware-postings-v1"
RANKING_POLICIES = {"P1_RAREST", "P2_WEIGHT", "P3_INFORMATION"}
PARTIAL_SUPPORT = "sum-anchor-weight-times-candidate-weight-over-visited-features"
EXACT_RERANK_VERSION = "v4-full-cosine-score-desc-record-ref-asc"


@dataclass(frozen=True)
class RarityConfiguration:
    formulation: str
    ranking_policy: str
    candidate_pool: int
    feature_limit: int
    df_cap: int | None = None
    visit_budget: int | None = None
    batch_size: int = 64

    def validate(self, top_k: int) -> None:
        if self.formulation not in {"R1", "R2"}:
            raise ValueError("formulation must be R1 or R2")
        if self.ranking_policy not in RANKING_POLICIES:
            raise ValueError("unsupported feature ranking policy")
        if self.candidate_pool < top_k:
            raise ValueError("candidate pool must be at least lexical top_k")
        if self.feature_limit < 1 or self.batch_size < 1:
            raise ValueError("feature and batch bounds must be positive")
        if self.formulation == "R1":
            if not self.df_cap or self.visit_budget is not None:
                raise ValueError("R1 requires only a positive df_cap")
        elif not self.visit_budget or self.df_cap is not None:
            raise ValueError("R2 requires only a positive visit_budget")


@dataclass(frozen=True)
class RarityMetrics:
    algorithm_version: str
    configuration_fingerprint: str
    features_inspected: int
    postings_traversed: int
    raw_posting_visits: int
    unique_candidate_accumulations: int
    exact_rerank_evaluations: int
    minimum_candidate_pool: int
    candidate_pool_p50: int
    candidate_pool_p95: int
    candidate_pool_p99: int
    maximum_candidate_pool: int
    anchors_with_insufficient_candidates: int
    candidate_generation_seconds: float
    exact_rerank_seconds: float
    total_seconds: float
    estimated_array_bytes: int
    provider_request_count: int = 0


@dataclass(frozen=True)
class RarityResult:
    directed_neighbors: dict[int, tuple[tuple[int, float], ...]]
    candidate_generation_fingerprint: str
    metrics: RarityMetrics


def configuration_payload(configuration: RarityConfiguration, top_k: int) -> dict:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "v4_lexical_contract_fingerprint": lexical_retrieval_contract_fingerprint(top_k),
        "formulation": configuration.formulation,
        "ranking_policy": configuration.ranking_policy,
        "feature_limit": configuration.feature_limit,
        "df_cap": configuration.df_cap,
        "visit_budget": configuration.visit_budget,
        "candidate_pool": configuration.candidate_pool,
        "partial_support": PARTIAL_SUPPORT,
        "exact_rerank_version": EXACT_RERANK_VERSION,
        "lexical_top_k": top_k,
        "canonical_tie_policy": "full-score-desc-record-ref-key-asc",
        "input_canonicalization": "record-ref-key-asc",
        "batch_size": configuration.batch_size,
    }


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _stable_inputs(matrix, refs):
    refs = tuple(str(value or "").strip() for value in refs)
    if any(not value for value in refs) or len(set(refs)) != len(refs):
        raise ValueError("one unique canonical reference is required per row")
    order = np.asarray(sorted(range(len(refs)), key=lambda index: refs[index]), dtype=np.int64)
    return normalize(matrix.tocsr(copy=True)[order], copy=False), tuple(refs[i] for i in order), order


def _rank_features(features, weights, posting_sizes, policy):
    sizes = posting_sizes[features]
    if policy == "P1_RAREST":
        order = np.lexsort((features, -weights, sizes))
    elif policy == "P2_WEIGHT":
        order = np.lexsort((features, sizes, -weights))
    else:
        information = weights / np.maximum(1, sizes)
        order = np.lexsort((features, sizes, -weights, -information))
    return features[order], weights[order], sizes[order]


def _percentile(values, percentile):
    return int(np.percentile(values, percentile, method="higher")) if values else 0


def _exact_rerank_batch(matrix, refs, sources, pools, top_k):
    lengths = [len(pool) for pool in pools]
    targets = (
        np.concatenate([pool for pool in pools if len(pool)])
        if any(lengths) else np.empty(0, dtype=np.int64)
    )
    source_rows = np.repeat(np.asarray(sources, dtype=np.int64), lengths)
    scores = (
        np.asarray(matrix[source_rows].multiply(matrix[targets]).sum(axis=1)).reshape(-1)
        if len(targets) else np.empty(0, dtype=np.float64)
    )
    ref_values = np.asarray(refs, dtype=object)
    directed, offset = {}, 0
    for source, pool, length in zip(sources, pools, lengths):
        current = scores[offset:offset + length]
        offset += length
        positive = current > 0
        positive_pool, positive_scores = pool[positive], current[positive]
        selected = _canonical_top_k_positions(positive_scores, positive_pool, ref_values, top_k)
        directed[source] = tuple(
            (int(positive_pool[position]), float(positive_scores[position]))
            for position in selected
        )
    return directed


def retrieve_bounded_rarity_candidates(matrix, refs, top_k, configuration):
    """Generate a strictly bounded pool, then compute authoritative exact cosine."""
    configuration.validate(top_k)
    started = time.perf_counter()
    stable, stable_refs, original_positions = _stable_inputs(matrix, refs)
    csc = stable.tocsc(copy=False)
    posting_sizes = np.diff(csc.indptr).astype(np.int64, copy=False)
    candidate_seconds = rerank_seconds = 0.0
    features_inspected = postings_traversed = raw_visits = unique_accumulations = 0
    pool_sizes, directed_stable = [], {}
    digest = hashlib.sha256()
    support = np.zeros(stable.shape[0], dtype=np.float64)
    ref_values = np.asarray(stable_refs, dtype=object)

    for batch_start in range(0, stable.shape[0], configuration.batch_size):
        batch_end = min(batch_start + configuration.batch_size, stable.shape[0])
        pools = []
        candidate_started = time.perf_counter()
        for source in range(batch_start, batch_end):
            left, right = stable.indptr[source:source + 2]
            ranked_features, ranked_weights, ranked_sizes = _rank_features(
                stable.indices[left:right], stable.data[left:right], posting_sizes,
                configuration.ranking_policy,
            )
            posting_targets, posting_contributions = [], []
            remaining = configuration.visit_budget
            selected = 0
            inspected = 0
            for feature, anchor_weight, posting_size in zip(
                ranked_features, ranked_weights, ranked_sizes
            ):
                if configuration.formulation == "R2" and inspected >= configuration.feature_limit:
                    break
                inspected += 1
                if configuration.formulation == "R1":
                    if posting_size > configuration.df_cap:
                        continue
                else:
                    if posting_size > remaining:
                        continue
                    remaining -= int(posting_size)
                pleft, pright = csc.indptr[feature:feature + 2]
                targets = csc.indices[pleft:pright]
                contributions = anchor_weight * csc.data[pleft:pright]
                posting_targets.append(targets)
                posting_contributions.append(contributions)
                postings_traversed += 1
                raw_visits += len(targets)
                selected += 1
                if configuration.formulation == "R1" and selected >= configuration.feature_limit:
                    break
            features_inspected += inspected
            if posting_targets:
                all_targets = np.concatenate(posting_targets)
                all_values = np.concatenate(posting_contributions)
                candidates = np.unique(all_targets)
                candidates = candidates[candidates != source]
                support[candidates] = 0.0
                np.add.at(support, all_targets, all_values)
                proxy = support[candidates]
                positive = proxy > 0
                candidates, proxy = candidates[positive], proxy[positive]
                unique_accumulations += len(candidates)
                order = np.lexsort((candidates, -proxy))[:configuration.candidate_pool]
                pool = candidates[order]
                support[candidates] = 0.0
            else:
                pool = np.empty(0, dtype=np.int64)
            pools.append(pool)
            pool_sizes.append(len(pool))
            digest.update(np.asarray((source, len(pool)), dtype="<i8").tobytes())
            digest.update(np.asarray(pool, dtype="<i8").tobytes())
        candidate_seconds += time.perf_counter() - candidate_started
        rerank_started = time.perf_counter()
        directed_stable.update(_exact_rerank_batch(
            stable, stable_refs, tuple(range(batch_start, batch_end)), pools, top_k
        ))
        rerank_seconds += time.perf_counter() - rerank_started

    directed = {
        int(original_positions[source]): tuple(
            (int(original_positions[target]), score) for target, score in neighbors
        )
        for source, neighbors in directed_stable.items()
    }
    total = time.perf_counter() - started
    fingerprint = _fingerprint(configuration_payload(configuration, top_k))
    return RarityResult(
        directed,
        digest.hexdigest(),
        RarityMetrics(
            ALGORITHM_VERSION, fingerprint, features_inspected, postings_traversed,
            raw_visits, unique_accumulations, sum(pool_sizes), min(pool_sizes, default=0),
            _percentile(pool_sizes, 50), _percentile(pool_sizes, 95),
            _percentile(pool_sizes, 99), max(pool_sizes, default=0),
            sum(size < top_k for size in pool_sizes), round(candidate_seconds, 6),
            round(rerank_seconds, 6), round(total, 6),
            int(stable.data.nbytes + stable.indices.nbytes + stable.indptr.nbytes
                + csc.data.nbytes + csc.indices.nbytes + csc.indptr.nbytes
                + support.nbytes),
        ),
    )


def evaluate_configuration(records, configuration, *, seed=1101, _prepared=None):
    corpus, matrix, refs, exact = _prepared or (*_inputs(records, seed), None)
    if exact is None:
        exact = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
    candidate = retrieve_bounded_rarity_candidates(matrix, refs, 5, configuration)
    exact_directed = {
        (source, target) for source, rows in exact.directed_neighbors.items()
        for target, _score in rows
    }
    candidate_directed = {
        (source, target) for source, rows in candidate.directed_neighbors.items()
        for target, _score in rows
    }
    exact_pairs = {tuple(sorted(pair)) for pair in exact_directed}
    candidate_pairs = {tuple(sorted(pair)) for pair in candidate_directed}
    recalls, complete = [], 0
    for source in range(records):
        expected = {target for target, _score in exact.directed_neighbors[source]}
        actual = {target for target, _score in candidate.directed_neighbors[source]}
        recall = len(expected & actual) / max(1, len(expected))
        recalls.append(recall)
        complete += int(expected <= actual)
    generic = {
        index for index, code in enumerate(corpus.truth.scenario_by_source_row) if code == "S3"
    }
    return {
        "records": records,
        "configuration": asdict(configuration),
        "metrics": asdict(candidate.metrics),
        "candidate_generation_fingerprint": candidate.candidate_generation_fingerprint,
        "lexical_fingerprint": stable_fingerprint(
            _directed_neighbors_to_pairs(candidate.directed_neighbors, refs)
        ),
        "directed_neighbor_recall": round(
            len(exact_directed & candidate_directed) / max(1, len(exact_directed)), 9
        ),
        "lexical_pair_recall": round(len(exact_pairs & candidate_pairs) / max(1, len(exact_pairs)), 9),
        "lexical_pair_jaccard": round(
            len(exact_pairs & candidate_pairs) / max(1, len(exact_pairs | candidate_pairs)), 9
        ),
        "anchors_with_all_exact_neighbors": complete,
        "worst_anchor_recall": round(min(recalls), 9),
        "coverage": _coverage(candidate_pairs, corpus.truth),
        "generic_hub_pairs": sum(left in generic and right in generic for left, right in candidate_pairs),
        "provider_request_count": 0,
    }


def run_isolated(records, configuration, *, seed=1101):
    started = time.perf_counter()
    corpus, matrix, refs = _inputs(records, seed)
    input_seconds = time.perf_counter() - started
    del corpus
    result = retrieve_bounded_rarity_candidates(matrix, refs, 5, configuration)
    return {
        "status": "COMPLETED", "records": records,
        "configuration": asdict(configuration), "matrix_shape": matrix.shape,
        "matrix_nnz": matrix.nnz, "tfidf_seconds": round(input_seconds, 6),
        "metrics": asdict(result.metrics),
        "lexical_fingerprint": stable_fingerprint(
            _directed_neighbors_to_pairs(result.directed_neighbors, refs)
        ),
        "wall_seconds": round(time.perf_counter() - started, 6),
        "provider_request_count": 0,
    }


def run_determinism(records, configuration, *, seed=1101):
    _corpus, matrix, refs = _inputs(records, seed)
    baseline = retrieve_bounded_rarity_candidates(matrix, refs, 5, configuration)
    signature = tuple(sorted(
        (refs[source], refs[target], score) for source, rows in baseline.directed_neighbors.items()
        for target, score in rows
    ))
    results = {}
    orders = {"repeat": np.arange(records), "reverse": np.arange(records)[::-1]}
    orders.update({
        f"shuffle_{seed_value}": np.random.default_rng(seed_value).permutation(records)
        for seed_value in (7, 19, 1101)
    })
    for name, order in orders.items():
        current = retrieve_bounded_rarity_candidates(matrix[order], refs[order], 5, configuration)
        current_signature = tuple(sorted(
            (refs[order][source], refs[order][target], score)
            for source, rows in current.directed_neighbors.items() for target, score in rows
        ))
        results[name] = {
            "candidate_fingerprint_equal": current.candidate_generation_fingerprint
            == baseline.candidate_generation_fingerprint,
            "semantic_equal": current_signature == signature,
        }
    return results


def _lexical_adapter(records, configuration):
    def adapter(matrix, refs, top_k):
        result = retrieve_bounded_rarity_candidates(matrix, refs, top_k, configuration)
        metrics = result.metrics
        return IndexedLexicalResult(result.directed_neighbors, LexicalRetrievalWorkMetrics(
            strategy=ALGORITHM_VERSION, contract_fingerprint=metrics.configuration_fingerprint,
            feature_count=matrix.shape[1], posting_entry_count=matrix.nnz,
            posting_size_p50=0, posting_size_p95=0, posting_size_p99=0,
            max_posting_size=0, candidate_union_enumerations=metrics.raw_posting_visits,
            unique_directed_candidates=metrics.unique_candidate_accumulations,
            exact_score_evaluations=metrics.exact_rerank_evaluations,
            theoretical_brute_directed_comparisons=records * (records - 1),
            zero_overlap_comparisons_avoided=max(0, records * (records - 1) - metrics.exact_rerank_evaluations),
            max_anchor_candidate_union=metrics.maximum_candidate_pool,
            index_build_time_ms=0.0,
            query_scoring_time_ms=(metrics.candidate_generation_seconds + metrics.exact_rerank_seconds) * 1000,
        ))
    return adapter


def _hybrid_signature(result, refs):
    return tuple(
        (tuple(sorted((refs[item.left_record_id], refs[item.right_record_id]))),
         item.retrieval_priority, item.retrieval_rank, item.retrieval_tier.value,
         item.evidence.retrieval_sources, item.evidence.channel_ranks,
         item.evidence.channel_scores, item.evidence.reciprocal_sources)
        for item in result.candidates
    )


def run_hybrid_comparison(records, configuration, *, seed=1101):
    from app.services import hybrid_retrieval
    corpus, _matrix, _refs = _inputs(records, seed)
    data = corpus.records.copy()
    refs = tuple(__import__(
        "app.services.canonical_record_service", fromlist=["canonical_record_ref_key"]
    ).canonical_record_ref_key(1, index) for index in range(records))
    data[CANONICAL_RECORD_REF_FIELD] = refs
    original = hybrid_retrieval.retrieve_production_lexical_neighbors
    try:
        exact = HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")
        hybrid_retrieval.retrieve_production_lexical_neighbors = _lexical_adapter(records, configuration)
        approximate = HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
    exact_signature, approximate_signature = _hybrid_signature(exact, refs), _hybrid_signature(approximate, refs)
    exact_pairs = {item[0] for item in exact_signature}
    approximate_pairs = {item[0] for item in approximate_signature}
    return {
        "records": records, "exact_count": len(exact_pairs),
        "approximate_count": len(approximate_pairs),
        "exact_fingerprint": stable_fingerprint(exact_signature),
        "approximate_fingerprint": stable_fingerprint(approximate_signature),
        "proposal_jaccard": round(len(exact_pairs & approximate_pairs) / max(1, len(exact_pairs | approximate_pairs)), 9),
        "exact_coverage": _coverage({tuple(sorted((item.left_record_id, item.right_record_id))) for item in exact.candidates}, corpus.truth),
        "approximate_coverage": _coverage({tuple(sorted((item.left_record_id, item.right_record_id))) for item in approximate.candidates}, corpus.truth),
        "provider_request_count": exact.metrics.provider_request_count + approximate.metrics.provider_request_count,
    }


def run_lexical_ablation(records, *, seed=1101):
    from app.services import hybrid_retrieval
    corpus, _matrix, _refs = _inputs(records, seed)
    data = corpus.records.copy()
    refs = tuple(__import__(
        "app.services.canonical_record_service", fromlist=["canonical_record_ref_key"]
    ).canonical_record_ref_key(1, index) for index in range(records))
    data[CANONICAL_RECORD_REF_FIELD] = refs
    original = hybrid_retrieval.retrieve_production_lexical_neighbors
    empty_metrics = LexicalRetrievalWorkMetrics(
        "LEXICAL_REMOVED_ABLATION", lexical_retrieval_contract_fingerprint(5),
        0, 0, 0, 0, 0, 0, 0, 0, 0, records * (records - 1),
        records * (records - 1), 0, 0.0, 0.0,
    )
    try:
        exact = HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")
        hybrid_retrieval.retrieve_production_lexical_neighbors = (
            lambda _matrix, _refs, _top_k: IndexedLexicalResult(
                {index: () for index in range(records)}, empty_metrics
            )
        )
        removed = HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
    exact_pairs = {tuple(sorted((item.left_record_id, item.right_record_id))) for item in exact.candidates}
    removed_pairs = {tuple(sorted((item.left_record_id, item.right_record_id))) for item in removed.candidates}
    exact_coverage, removed_coverage = _coverage(exact_pairs, corpus.truth), _coverage(removed_pairs, corpus.truth)
    def covered(pairs, members):
        return any(
            tuple(sorted((left, right))) in pairs
            for offset, left in enumerate(members) for right in members[offset + 1:]
        )
    unique_by_code = {"S5": 0, "S7": 0}
    truth_unique = 0
    for _identity, members in corpus.truth.duplicate_sets:
        unique = covered(exact_pairs, members) and not covered(removed_pairs, members)
        truth_unique += int(unique)
        codes = {corpus.truth.scenario_by_source_row[item] for item in members}
        if unique and len(codes) == 1 and next(iter(codes)) in unique_by_code:
            unique_by_code[next(iter(codes))] += 1
    generic = {index for index, code in enumerate(corpus.truth.scenario_by_source_row) if code == "S3"}
    return {
        "records": records, "exact_count": len(exact_pairs), "without_lexical_count": len(removed_pairs),
        "proposal_jaccard": round(len(exact_pairs & removed_pairs) / max(1, len(exact_pairs | removed_pairs)), 9),
        "exact_final_unique_to_lexical": len(exact_pairs - removed_pairs),
        "truth_uniquely_recovered": truth_unique,
        "bridge_uniquely_recovered": unique_by_code["S7"],
        "cross_site_uniquely_recovered": unique_by_code["S5"],
        "generic_hub_change": sum(a in generic and b in generic for a, b in exact_pairs)
        - sum(a in generic and b in generic for a, b in removed_pairs),
        "exact_coverage": exact_coverage, "without_lexical_coverage": removed_coverage,
        "provider_request_count": exact.metrics.provider_request_count + removed.metrics.provider_request_count,
    }


def timeout_result(*, records, configuration, timeout_seconds, wall_seconds):
    return {
        "status": "TIMED_OUT", "safe_failure_category": "RARITY_AWARE_BENCHMARK_TIMEOUT",
        "records": records, "configuration": asdict(configuration),
        "timeout_seconds": timeout_seconds, "wall_seconds": wall_seconds,
        "provider_request_count": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--formulation", choices=("R1", "R2"), default="R2")
    parser.add_argument("--policy", choices=tuple(sorted(RANKING_POLICIES)), default="P1_RAREST")
    parser.add_argument("--features", type=int, default=16)
    parser.add_argument("--df-cap", type=int, default=512)
    parser.add_argument("--visit-budget", type=int, default=4096)
    parser.add_argument("--pool", type=int, default=160)
    parser.add_argument("--determinism", action="store_true")
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--ablation", action="store_true")
    parser.add_argument("--isolated", action="store_true")
    args = parser.parse_args(argv)
    configuration = RarityConfiguration(
        args.formulation, args.policy, args.pool, args.features,
        df_cap=args.df_cap if args.formulation == "R1" else None,
        visit_budget=args.visit_budget if args.formulation == "R2" else None,
    )
    result = (
        run_determinism(args.records, configuration) if args.determinism else
        run_hybrid_comparison(args.records, configuration) if args.hybrid else
        run_lexical_ablation(args.records) if args.ablation else
        run_isolated(args.records, configuration) if args.isolated else
        evaluate_configuration(args.records, configuration)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
