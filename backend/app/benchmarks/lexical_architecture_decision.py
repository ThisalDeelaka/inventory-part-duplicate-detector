"""Benchmark-only GF-11C lexical retrieval architecture experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.preprocessing import normalize

from app.benchmarks.character_retrieval_contract import _coverage
from app.benchmarks.contracts import stable_fingerprint
from app.benchmarks.exact_indexed_lexical import _inputs
from app.benchmarks.group_first_scale import benchmark_configuration, run_scale_benchmark
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


ARCHITECTURE_B_VERSION = "high-information-tfidf-candidates-v1"
ARCHITECTURE_C_VERSION = "sparse-simhash-exact-rerank-v1"
SIMHASH_SEED = 1101


@dataclass(frozen=True)
class HighInformationConfiguration:
    feature_count: int
    candidate_pool: int

    def validate(self, top_k: int) -> None:
        if self.feature_count < 1 or self.candidate_pool < top_k:
            raise ValueError("high-information configuration is invalid")


@dataclass(frozen=True)
class SparseSimHashConfiguration:
    table_count: int
    bits_per_table: int
    probe_radius: int
    candidate_pool: int
    gather_multiplier: int = 4
    bucket_cap_multiplier: int = 2
    seed: int = SIMHASH_SEED

    def validate(self, top_k: int) -> None:
        if (
            self.table_count < 1
            or self.bits_per_table < 2
            or self.bits_per_table > 16
            or self.probe_radius not in {0, 1, 2}
            or self.candidate_pool < top_k
            or self.gather_multiplier < 1
            or self.bucket_cap_multiplier < 1
        ):
            raise ValueError("sparse SimHash configuration is invalid")


@dataclass(frozen=True)
class ExperimentalMetrics:
    architecture: str
    configuration_fingerprint: str
    index_build_seconds: float
    candidate_generation_seconds: float
    exact_rerank_seconds: float
    total_seconds: float
    raw_candidate_visits: int
    candidate_pool_evaluations: int
    exact_rerank_evaluations: int
    minimum_candidate_pool: int
    candidate_pool_p50: int
    candidate_pool_p95: int
    candidate_pool_p99: int
    maximum_candidate_pool: int
    estimated_array_bytes: int
    provider_request_count: int = 0


@dataclass(frozen=True)
class ExperimentalResult:
    directed_neighbors: dict[int, tuple[tuple[int, float], ...]]
    candidate_generation_fingerprint: str
    metrics: ExperimentalMetrics


def _configuration_fingerprint(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _stable_inputs(matrix, refs):
    refs = tuple(str(value or "").strip() for value in refs)
    if any(not value for value in refs) or len(set(refs)) != len(refs):
        raise ValueError("one unique canonical reference is required per row")
    order = np.asarray(sorted(range(len(refs)), key=lambda item: refs[item]), dtype=np.int64)
    stable = normalize(matrix.tocsr(copy=True)[order], copy=False)
    return stable, tuple(refs[item] for item in order), order


def _pool_percentile(pool_sizes, percentile):
    return int(np.percentile(pool_sizes, percentile, method="higher")) if pool_sizes else 0


def _fingerprint_pool(digest, anchor, pool):
    digest.update(np.asarray((anchor, len(pool)), dtype="<i8").tobytes())
    digest.update(np.asarray(pool, dtype="<i8").tobytes())


def _exact_rerank_batch(matrix, refs, starts, pools, top_k):
    lengths = [len(pool) for pool in pools]
    flat_targets = (
        np.concatenate([pool for pool in pools if len(pool)])
        if any(lengths) else np.empty(0, dtype=np.int64)
    )
    flat_sources = np.repeat(np.asarray(starts, dtype=np.int64), lengths)
    scores = (
        np.asarray(
            matrix[flat_sources].multiply(matrix[flat_targets]).sum(axis=1)
        ).reshape(-1)
        if len(flat_targets) else np.empty(0, dtype=np.float64)
    )
    directed = {}
    offset = 0
    for source, pool, length in zip(starts, pools, lengths):
        current_scores = scores[offset:offset + length]
        offset += length
        order = _canonical_top_k_positions(
            current_scores, pool, np.asarray(refs, dtype=object), top_k
        )
        directed[source] = tuple(
            (int(pool[position]), float(current_scores[position])) for position in order
        )
    return directed


def retrieve_high_information_candidates(matrix, refs, top_k, configuration):
    configuration.validate(top_k)
    started = time.perf_counter()
    stable, stable_refs, original_positions = _stable_inputs(matrix, refs)
    selected_indices = []
    selected_values = []
    selected_indptr = [0]
    for source in range(stable.shape[0]):
        left, right = stable.indptr[source:source + 2]
        features = stable.indices[left:right]
        weights = stable.data[left:right]
        order = np.lexsort((features, -weights))[:configuration.feature_count]
        ordered = np.sort(order)
        selected_indices.extend(features[ordered])
        selected_values.extend(weights[ordered])
        selected_indptr.append(len(selected_indices))
    selected = csr_matrix(
        (
            np.asarray(selected_values, dtype=stable.dtype),
            np.asarray(selected_indices, dtype=np.int32),
            np.asarray(selected_indptr, dtype=np.int64),
        ),
        shape=stable.shape,
    )
    build_seconds = time.perf_counter() - started
    candidate_seconds = 0.0
    rerank_seconds = 0.0
    directed_stable = {}
    raw_candidates = 0
    pool_sizes = []
    digest = hashlib.sha256()
    ref_values = np.asarray(stable_refs, dtype=object)
    for start in range(0, stable.shape[0], 64):
        candidate_started = time.perf_counter()
        end = min(start + 64, stable.shape[0])
        similarities = (selected[start:end] @ stable.T).tocsr()
        similarities.eliminate_zeros()
        pools = []
        for offset, source in enumerate(range(start, end)):
            left, right = similarities.indptr[offset:offset + 2]
            targets = similarities.indices[left:right]
            scores = similarities.data[left:right]
            keep = (targets != source) & (scores > 0)
            targets, scores = targets[keep], scores[keep]
            raw_candidates += len(targets)
            order = _canonical_top_k_positions(
                scores, targets, ref_values, configuration.candidate_pool
            )
            pool = targets[order]
            pools.append(pool)
            pool_sizes.append(len(pool))
            _fingerprint_pool(digest, source, pool)
        candidate_seconds += time.perf_counter() - candidate_started
        rerank_started = time.perf_counter()
        directed_stable.update(
            _exact_rerank_batch(stable, stable_refs, tuple(range(start, end)), pools, top_k)
        )
        rerank_seconds += time.perf_counter() - rerank_started
    directed = {
        int(original_positions[source]): tuple(
            (int(original_positions[target]), score) for target, score in neighbors
        )
        for source, neighbors in directed_stable.items()
    }
    payload = {
        "version": ARCHITECTURE_B_VERSION,
        "feature_count": configuration.feature_count,
        "candidate_pool": configuration.candidate_pool,
        "feature_order": "tfidf-desc-feature-index-asc",
        "candidate_order": "selected-feature-partial-dot-desc-record-ref-asc",
        "exact_rerank": "v4-full-cosine-score-desc-record-ref-asc",
        "top_k": top_k,
    }
    total_seconds = time.perf_counter() - started
    return ExperimentalResult(
        directed,
        digest.hexdigest(),
        ExperimentalMetrics(
            ARCHITECTURE_B_VERSION, _configuration_fingerprint(payload),
            round(build_seconds, 6), round(candidate_seconds, 6),
            round(rerank_seconds, 6), round(total_seconds, 6), raw_candidates,
            sum(pool_sizes), sum(pool_sizes), min(pool_sizes),
            _pool_percentile(pool_sizes, 50), _pool_percentile(pool_sizes, 95),
            _pool_percentile(pool_sizes, 99), max(pool_sizes),
            int(selected.data.nbytes + selected.indices.nbytes + selected.indptr.nbytes
                + 64 * max(pool_sizes, default=0) * np.dtype(np.int64).itemsize),
        ),
    )


def _probe_masks(bits, radius):
    masks = [0]
    if radius >= 1:
        masks.extend(1 << bit for bit in range(bits))
    if radius >= 2:
        masks.extend(
            (1 << left) | (1 << right)
            for left in range(bits) for right in range(left + 1, bits)
        )
    return tuple(masks)


def retrieve_sparse_simhash_candidates(matrix, refs, top_k, configuration):
    configuration.validate(top_k)
    started = time.perf_counter()
    stable, stable_refs, original_positions = _stable_inputs(matrix, refs)
    rng = np.random.Generator(np.random.PCG64(configuration.seed))
    signatures = np.empty(
        (stable.shape[0], configuration.table_count), dtype=np.uint16
    )
    weights = 1 << np.arange(configuration.bits_per_table, dtype=np.uint16)
    buckets = []
    projection_bytes = 0
    for table in range(configuration.table_count):
        signs = rng.integers(
            0, 2, size=(stable.shape[1], configuration.bits_per_table),
            dtype=np.int8,
        )
        signs = signs * 2 - 1
        projections = np.asarray(stable @ signs, dtype=np.float32)
        projection_bytes = max(projection_bytes, signs.nbytes + projections.nbytes)
        codes = ((projections >= 0).astype(np.uint16) * weights).sum(
            axis=1, dtype=np.uint16
        )
        signatures[:, table] = codes
        table_buckets = {}
        for position, code in enumerate(codes):
            table_buckets.setdefault(int(code), []).append(position)
        buckets.append({code: tuple(values) for code, values in table_buckets.items()})
    build_seconds = time.perf_counter() - started
    masks = _probe_masks(configuration.bits_per_table, configuration.probe_radius)
    popcount = np.fromiter(
        (value.bit_count() for value in range(1 << configuration.bits_per_table)),
        dtype=np.uint8,
    )
    gather_limit = min(
        stable.shape[0] - 1,
        configuration.candidate_pool * configuration.gather_multiplier,
    )
    bucket_cap = max(
        16, configuration.candidate_pool * configuration.bucket_cap_multiplier
    )
    candidate_seconds = 0.0
    rerank_seconds = 0.0
    directed_stable = {}
    raw_visits = 0
    pool_sizes = []
    digest = hashlib.sha256()
    for start in range(0, stable.shape[0], 64):
        candidate_started = time.perf_counter()
        end = min(start + 64, stable.shape[0])
        pools = []
        for source in range(start, end):
            candidates = set()
            for mask in masks:
                for table in range(configuration.table_count):
                    bucket = buckets[table].get(int(signatures[source, table]) ^ mask, ())
                    raw_visits += min(len(bucket), bucket_cap)
                    candidates.update(bucket[:bucket_cap])
                    candidates.discard(source)
                if len(candidates) >= gather_limit:
                    break
            values = np.fromiter(candidates, dtype=np.int64)
            xor = np.bitwise_xor(signatures[values], signatures[source])
            matches = (
                configuration.table_count * configuration.bits_per_table
                - popcount[xor].sum(axis=1)
            )
            order = np.lexsort((values, -matches.astype(np.int32)))
            pool = values[order[:configuration.candidate_pool]]
            pools.append(pool)
            pool_sizes.append(len(pool))
            _fingerprint_pool(digest, source, pool)
        candidate_seconds += time.perf_counter() - candidate_started
        rerank_started = time.perf_counter()
        directed_stable.update(
            _exact_rerank_batch(stable, stable_refs, tuple(range(start, end)), pools, top_k)
        )
        rerank_seconds += time.perf_counter() - rerank_started
    directed = {
        int(original_positions[source]): tuple(
            (int(original_positions[target]), score) for target, score in neighbors
        )
        for source, neighbors in directed_stable.items()
    }
    payload = {
        "version": ARCHITECTURE_C_VERSION,
        **asdict(configuration),
        "hyperplane": "pcg64-fixed-seed-dense-sign-over-sparse-input",
        "canonical_insertion_order": "record-ref-asc",
        "candidate_order": "signature-bit-matches-desc-record-ref-asc",
        "exact_rerank": "v4-full-cosine-score-desc-record-ref-asc",
        "top_k": top_k,
    }
    total_seconds = time.perf_counter() - started
    return ExperimentalResult(
        directed,
        digest.hexdigest(),
        ExperimentalMetrics(
            ARCHITECTURE_C_VERSION, _configuration_fingerprint(payload),
            round(build_seconds, 6), round(candidate_seconds, 6),
            round(rerank_seconds, 6), round(total_seconds, 6), raw_visits,
            sum(pool_sizes), sum(pool_sizes), min(pool_sizes),
            _pool_percentile(pool_sizes, 50), _pool_percentile(pool_sizes, 95),
            _pool_percentile(pool_sizes, 99), max(pool_sizes),
            int(stable.data.nbytes + stable.indices.nbytes + stable.indptr.nbytes
                + signatures.nbytes + projection_bytes
                + 64 * max(pool_sizes, default=0) * np.dtype(np.int64).itemsize),
        ),
    )


def _semantic_directed(directed, refs):
    return tuple(sorted(
        (refs[source], refs[target], score)
        for source, neighbors in directed.items() for target, score in neighbors
    ))


def evaluate_configuration(records, architecture, configuration, *, seed=1101):
    corpus, matrix, refs = _inputs(records, seed)
    exact = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
    approximate = (
        retrieve_high_information_candidates(matrix, refs, 5, configuration)
        if architecture == "B" else
        retrieve_sparse_simhash_candidates(matrix, refs, 5, configuration)
    )
    exact_directed = {
        (refs[source], refs[target])
        for source, values in exact.directed_neighbors.items() for target, _score in values
    }
    approximate_directed = {
        (refs[source], refs[target])
        for source, values in approximate.directed_neighbors.items() for target, _score in values
    }
    recalls = []
    fully_recovered = 0
    for source in range(records):
        expected = {target for target, _score in exact.directed_neighbors[source]}
        actual = {target for target, _score in approximate.directed_neighbors[source]}
        recall = len(expected & actual) / max(1, len(expected))
        recalls.append(recall)
        fully_recovered += int(expected <= actual)
    exact_pairs = {
        tuple(sorted((source, target)))
        for source, values in exact.directed_neighbors.items() for target, _score in values
    }
    approximate_pairs = {
        tuple(sorted((source, target)))
        for source, values in approximate.directed_neighbors.items() for target, _score in values
    }
    generic_refs = {
        index for index, code in enumerate(corpus.truth.scenario_by_source_row)
        if code == "S3"
    }
    return {
        "records": records,
        "architecture": architecture,
        "configuration": asdict(configuration),
        "metrics": asdict(approximate.metrics),
        "candidate_generation_fingerprint": approximate.candidate_generation_fingerprint,
        "lexical_fingerprint": stable_fingerprint(
            _directed_neighbors_to_pairs(approximate.directed_neighbors, refs)
        ),
        "directed_neighbor_recall": round(
            len(exact_directed & approximate_directed) / max(1, len(exact_directed)), 9
        ),
        "lexical_pair_recall": round(
            len(exact_pairs & approximate_pairs) / max(1, len(exact_pairs)), 9
        ),
        "lexical_pair_jaccard": round(
            len(exact_pairs & approximate_pairs) / max(1, len(exact_pairs | approximate_pairs)), 9
        ),
        "anchors_with_all_exact_neighbors": fully_recovered,
        "worst_anchor_recall": round(min(recalls), 9),
        "coverage": _coverage(approximate_pairs, corpus.truth),
        "generic_hub_pairs": sum(
            left in generic_refs and right in generic_refs
            for left, right in approximate_pairs
        ),
        "provider_request_count": 0,
    }


def run_isolated_viability(records, architecture, configuration, *, seed=1101):
    """Run only the proposed retrieval path; never construct the exact reference."""
    started = time.perf_counter()
    corpus, matrix, refs = _inputs(records, seed)
    input_seconds = time.perf_counter() - started
    result = (
        retrieve_high_information_candidates(matrix, refs, 5, configuration)
        if architecture == "B" else
        retrieve_sparse_simhash_candidates(matrix, refs, 5, configuration)
    )
    pairs = {
        tuple(sorted((source, target)))
        for source, values in result.directed_neighbors.items() for target, _score in values
    }
    generic_refs = {
        index for index, code in enumerate(corpus.truth.scenario_by_source_row)
        if code == "S3"
    }
    return {
        "status": "COMPLETED",
        "records": records,
        "architecture": architecture,
        "configuration": asdict(configuration),
        "input_build_seconds": round(input_seconds, 6),
        "metrics": asdict(result.metrics),
        "wall_seconds": round(time.perf_counter() - started, 6),
        "candidate_generation_fingerprint": result.candidate_generation_fingerprint,
        "lexical_fingerprint": stable_fingerprint(
            _directed_neighbors_to_pairs(result.directed_neighbors, refs)
        ),
        "coverage": _coverage(pairs, corpus.truth),
        "generic_hub_pairs": sum(
            left in generic_refs and right in generic_refs for left, right in pairs
        ),
        "provider_request_count": 0,
    }


def architecture_timeout_result(*, records, architecture, configuration, timeout_seconds,
                                wall_seconds):
    """Create an explicit timeout result that cannot masquerade as completion."""
    return {
        "status": "TIMED_OUT",
        "safe_failure_category": "ARCHITECTURE_BENCHMARK_TIMEOUT",
        "records": records,
        "architecture": architecture,
        "configuration": asdict(configuration),
        "timeout_seconds": timeout_seconds,
        "wall_seconds": wall_seconds,
        "provider_request_count": 0,
    }


def run_determinism_check(records, architecture, configuration, *, seed=1101):
    _corpus, matrix, refs = _inputs(records, seed)
    retrieve = (
        retrieve_high_information_candidates if architecture == "B"
        else retrieve_sparse_simhash_candidates
    )
    expected = retrieve(matrix, refs, 5, configuration)
    expected_semantic = _semantic_directed(expected.directed_neighbors, refs)
    results = {}
    orders = {
        "repeat": np.arange(records),
        "reverse": np.arange(records)[::-1],
        **{
            f"shuffle_{value}": np.random.default_rng(value).permutation(records)
            for value in (7, 19, 1101)
        },
    }
    for name, order in orders.items():
        current_refs = refs[order]
        current = retrieve(matrix[order], current_refs, 5, configuration)
        results[name] = {
            "candidate_fingerprint_equal": (
                current.candidate_generation_fingerprint
                == expected.candidate_generation_fingerprint
            ),
            "semantic_equal": (
                _semantic_directed(current.directed_neighbors, current_refs)
                == expected_semantic
            ),
        }
    return results


def run_hybrid_comparison(records, architecture, configuration, *, seed=1101):
    from app.services import hybrid_retrieval

    corpus = __import__(
        "app.benchmarks.group_first_scale_generator", fromlist=["generate_scale_corpus"]
    ).generate_scale_corpus(records, seed=seed)
    data = corpus.records.copy()
    refs = tuple(__import__(
        "app.services.canonical_record_service", fromlist=["canonical_record_ref_key"]
    ).canonical_record_ref_key(1, index) for index in range(records))
    data[CANONICAL_RECORD_REF_FIELD] = refs
    original = hybrid_retrieval.retrieve_production_lexical_neighbors

    def adapter(matrix, canonical_refs, top_k):
        experimental = (
            retrieve_high_information_candidates(matrix, canonical_refs, top_k, configuration)
            if architecture == "B" else
            retrieve_sparse_simhash_candidates(matrix, canonical_refs, top_k, configuration)
        )
        metrics = experimental.metrics
        return IndexedLexicalResult(
            experimental.directed_neighbors,
            LexicalRetrievalWorkMetrics(
                strategy=metrics.architecture,
                contract_fingerprint=metrics.configuration_fingerprint,
                feature_count=matrix.shape[1], posting_entry_count=matrix.nnz,
                posting_size_p50=0, posting_size_p95=0, posting_size_p99=0,
                max_posting_size=0,
                candidate_union_enumerations=metrics.raw_candidate_visits,
                unique_directed_candidates=metrics.candidate_pool_evaluations,
                exact_score_evaluations=metrics.exact_rerank_evaluations,
                theoretical_brute_directed_comparisons=records * (records - 1),
                zero_overlap_comparisons_avoided=(
                    records * (records - 1) - metrics.exact_rerank_evaluations
                ),
                max_anchor_candidate_union=metrics.maximum_candidate_pool,
                index_build_time_ms=metrics.index_build_seconds * 1000,
                query_scoring_time_ms=(
                    metrics.candidate_generation_seconds + metrics.exact_rerank_seconds
                ) * 1000,
            ),
        )

    def execute(function):
        hybrid_retrieval.retrieve_production_lexical_neighbors = function
        return HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")

    try:
        exact, approximate = execute(original), execute(adapter)
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original

    def signature(result):
        return tuple(
            (
                tuple(sorted((refs[item.left_record_id], refs[item.right_record_id]))),
                item.retrieval_priority, item.retrieval_rank, item.retrieval_tier.value,
                item.evidence.retrieval_sources, item.evidence.channel_ranks,
                item.evidence.channel_scores, item.evidence.reciprocal_sources,
            )
            for item in result.candidates
        )

    exact_signature, approximate_signature = signature(exact), signature(approximate)
    exact_pairs = {
        tuple(sorted((item.left_record_id, item.right_record_id))) for item in exact.candidates
    }
    approximate_pairs = {
        tuple(sorted((item.left_record_id, item.right_record_id)))
        for item in approximate.candidates
    }
    generic_refs = {
        index for index, code in enumerate(corpus.truth.scenario_by_source_row)
        if code == "S3"
    }
    return {
        "records": records,
        "exact_count": len(exact.candidates),
        "approximate_count": len(approximate.candidates),
        "exact_fingerprint": stable_fingerprint(exact_signature),
        "approximate_fingerprint": stable_fingerprint(approximate_signature),
        "proposal_jaccard": round(
            len(exact_pairs & approximate_pairs) / max(1, len(exact_pairs | approximate_pairs)), 9
        ),
        "exact_coverage": _coverage(exact_pairs, corpus.truth),
        "approximate_coverage": _coverage(approximate_pairs, corpus.truth),
        "exact_generic_hub_pairs": sum(
            left in generic_refs and right in generic_refs for left, right in exact_pairs
        ),
        "approximate_generic_hub_pairs": sum(
            left in generic_refs and right in generic_refs for left, right in approximate_pairs
        ),
        "provider_request_count": (
            exact.metrics.provider_request_count + approximate.metrics.provider_request_count
        ),
    }


def run_safety_probe(architecture, configuration, *, records=64, seed=1101):
    from app.services import hybrid_retrieval

    original = hybrid_retrieval.retrieve_production_lexical_neighbors

    def adapter(matrix, refs, top_k):
        result = (
            retrieve_high_information_candidates(matrix, refs, top_k, configuration)
            if architecture == "B" else
            retrieve_sparse_simhash_candidates(matrix, refs, top_k, configuration)
        )
        metrics = result.metrics
        return IndexedLexicalResult(
            result.directed_neighbors,
            LexicalRetrievalWorkMetrics(
                metrics.architecture, metrics.configuration_fingerprint,
                matrix.shape[1], matrix.nnz, 0, 0, 0, 0,
                metrics.raw_candidate_visits, metrics.candidate_pool_evaluations,
                metrics.exact_rerank_evaluations, records * (records - 1),
                records * (records - 1) - metrics.exact_rerank_evaluations,
                metrics.maximum_candidate_pool, metrics.index_build_seconds * 1000,
                (metrics.candidate_generation_seconds + metrics.exact_rerank_seconds) * 1000,
            ),
        )

    try:
        hybrid_retrieval.retrieve_production_lexical_neighbors = adapter
        with tempfile.TemporaryDirectory(prefix="gf11c-arch-safety-") as directory:
            result = run_scale_benchmark(
                records=records, seed=seed, scenario="canonical-mixed",
                db_path=Path(directory) / "probe.sqlite",
            )
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
    return {
        "status": result.run.status.value,
        "safe_failure_category": result.run.safe_failure_category,
        "safety": asdict(result.safety_metrics),
        "row_counts": dict(result.database_metrics.row_counts),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--architecture", choices=("B", "C"), required=True)
    parser.add_argument("--feature-count", type=int, default=8)
    parser.add_argument("--candidate-pool", type=int, default=320)
    parser.add_argument("--tables", type=int, default=8)
    parser.add_argument("--bits", type=int, default=12)
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--determinism", action="store_true")
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args(argv)
    configuration = (
        HighInformationConfiguration(args.feature_count, args.candidate_pool)
        if args.architecture == "B" else
        SparseSimHashConfiguration(
            args.tables, args.bits, args.radius, args.candidate_pool
        )
    )
    if args.sweep:
        configurations = (
            [
                HighInformationConfiguration(feature_count, candidate_pool)
                for feature_count in (4, 8, 16, 32)
                for candidate_pool in (40, 80, 160, 320, 640)
            ]
            if args.architecture == "B" else
            [
                SparseSimHashConfiguration(8, 12, radius, candidate_pool)
                for radius, candidate_pool in (
                    (1, 160), (1, 320), (1, 640),
                    (2, 160), (2, 320), (2, 640),
                )
            ] + [
                SparseSimHashConfiguration(12, 12, 1, 320),
                SparseSimHashConfiguration(8, 14, 2, 320),
            ]
        )
        result = [
            evaluate_configuration(args.records, args.architecture, item)
            for item in configurations
        ]
    else:
        result = (
        run_hybrid_comparison(args.records, args.architecture, configuration)
        if args.hybrid else
        run_determinism_check(args.records, args.architecture, configuration)
        if args.determinism else
        run_isolated_viability(args.records, args.architecture, configuration)
        if args.isolated else
        evaluate_configuration(args.records, args.architecture, configuration)
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
