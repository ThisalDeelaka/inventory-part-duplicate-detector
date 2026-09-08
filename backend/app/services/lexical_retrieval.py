"""Exact indexed retrieval for the frozen v4 lexical TF-IDF contract."""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum

import numpy as np
import scipy
import sklearn
from sklearn.preprocessing import normalize

LEXICAL_RETRIEVAL_IMPLEMENTATION_VERSION = "exact-indexed-lexical-v1"
LEXICAL_RETRIEVAL_STRATEGY = "EXACT_INDEXED_LEXICAL"
LEXICAL_QUERY_BATCH_SIZE = 64
LEXICAL_QUERY_WORKERS = 4
EXACT_INDEXED_V4 = "EXACT_INDEXED_V4"
BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS = (
    "BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS"
)
LEXICAL_STRATEGY_VERSION = "production-lexical-strategy-v1"
LEXICAL_STRATEGY_THRESHOLD = 25_000
BOUNDED_PROXY_DEFINITION = (
    "visited-authoritative-tfidf-partial-dot-support"
)
BOUNDED_EXACT_RERANK_VERSION = "v4-full-cosine-score-desc-record-ref-asc"


@dataclass(frozen=True)
class BoundedLexicalConfiguration:
    ranking_policy: str
    feature_limit: int
    visit_budget: int
    candidate_pool: int
    batch_size: int


PRIMARY_BOUNDED_CONFIGURATION = BoundedLexicalConfiguration(
    ranking_policy="P1_RAREST",
    feature_limit=32,
    visit_budget=4096,
    candidate_pool=80,
    batch_size=64,
)
SECOND_PASS_BOUNDED_CONFIGURATION = BoundedLexicalConfiguration(
    ranking_policy="P1_RAREST",
    feature_limit=32,
    visit_budget=16384,
    candidate_pool=80,
    batch_size=64,
)


class LexicalRetrievalFailureCategory(str, Enum):
    INDEX_CONFIGURATION_INVALID = "LEXICAL_INDEX_CONFIGURATION_INVALID"
    INDEX_BUILD_FAILED = "LEXICAL_INDEX_BUILD_FAILED"
    INDEX_QUERY_FAILED = "LEXICAL_INDEX_QUERY_FAILED"
    CANDIDATE_POOL_INSUFFICIENT = "LEXICAL_CANDIDATE_POOL_INSUFFICIENT"


class LexicalRetrievalError(RuntimeError):
    def __init__(self, category: LexicalRetrievalFailureCategory, message: str) -> None:
        super().__init__(message)
        self.safe_category = category.value


@dataclass(frozen=True)
class LexicalRetrievalWorkMetrics:
    strategy: str
    contract_fingerprint: str
    feature_count: int
    posting_entry_count: int
    posting_size_p50: int
    posting_size_p95: int
    posting_size_p99: int
    max_posting_size: int
    candidate_union_enumerations: int
    unique_directed_candidates: int
    exact_score_evaluations: int
    theoretical_brute_directed_comparisons: int
    zero_overlap_comparisons_avoided: int
    max_anchor_candidate_union: int
    index_build_time_ms: float
    query_scoring_time_ms: float
    primary_insufficient_anchors: int = 0
    second_pass_anchors: int = 0
    second_pass_recovered_anchors: int = 0
    remaining_insufficient_anchors: int = 0
    second_pass_posting_visits: int = 0
    second_pass_exact_reranks: int = 0
    second_pass_time_ms: float = 0.0


@dataclass(frozen=True)
class IndexedLexicalResult:
    directed_neighbors: dict[int, tuple[tuple[int, float], ...]]
    metrics: LexicalRetrievalWorkMetrics


def lexical_retrieval_contract_payload(final_top_k: int) -> dict:
    if final_top_k < 1:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_CONFIGURATION_INVALID,
            "lexical final top-k must be positive",
        )
    return {
        "strategy": LEXICAL_RETRIEVAL_STRATEGY,
        "implementation_version": LEXICAL_RETRIEVAL_IMPLEMENTATION_VERSION,
        "representation": "tfidf-char-wb-3-5-v1",
        "backend": "scipy-csr-csc-sparse-dot",
        "scipy_version": scipy.__version__,
        "scikit_learn_version": sklearn.__version__,
        "candidate_rule": "shared-nonzero-tfidf-feature",
        "similarity": "exact-full-precision-cosine",
        "self_exclusion": "before-top-k",
        "ordering": "score-desc-record-ref-key-asc",
        "output_score": "two-decimal-after-selection",
        "final_top_k": final_top_k,
        "query_batch_size": LEXICAL_QUERY_BATCH_SIZE,
        "query_workers": LEXICAL_QUERY_WORKERS,
    }


def lexical_retrieval_contract_fingerprint(final_top_k: int) -> str:
    encoded = json.dumps(
        lexical_retrieval_contract_payload(final_top_k),
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_lexical_strategy(eligible_record_count: int) -> str:
    if eligible_record_count < 0:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_CONFIGURATION_INVALID,
            "lexical eligible-record count must not be negative",
        )
    return (
        EXACT_INDEXED_V4
        if eligible_record_count < LEXICAL_STRATEGY_THRESHOLD
        else BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS
    )


def lexical_strategy_contract_payload(
    final_top_k: int,
    *,
    threshold: int = LEXICAL_STRATEGY_THRESHOLD,
    primary: BoundedLexicalConfiguration = PRIMARY_BOUNDED_CONFIGURATION,
    second_pass: BoundedLexicalConfiguration = SECOND_PASS_BOUNDED_CONFIGURATION,
) -> dict:
    if final_top_k < 1 or threshold < 1:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_CONFIGURATION_INVALID,
            "lexical strategy top-k and threshold must be positive",
        )
    return {
        "strategy_version": LEXICAL_STRATEGY_VERSION,
        "eligible_record_threshold": threshold,
        "small_strategy": EXACT_INDEXED_V4,
        "large_strategy": BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS,
        "v4_contract_fingerprint": lexical_retrieval_contract_fingerprint(final_top_k),
        "primary": {
            "formulation": "R2_VISIT_BUDGET",
            "ranking_policy": primary.ranking_policy,
            "feature_limit": primary.feature_limit,
            "visit_budget": primary.visit_budget,
            "candidate_pool": primary.candidate_pool,
            "batch_size": primary.batch_size,
        },
        "second_pass": {
            "applies_to": "PRIMARY_INSUFFICIENT_ANCHORS_ONLY",
            "formulation": "R2_VISIT_BUDGET",
            "ranking_policy": second_pass.ranking_policy,
            "feature_limit": second_pass.feature_limit,
            "visit_budget": second_pass.visit_budget,
            "candidate_pool": second_pass.candidate_pool,
            "batch_size": second_pass.batch_size,
        },
        "proxy_definition": BOUNDED_PROXY_DEFINITION,
        "exact_rerank_version": BOUNDED_EXACT_RERANK_VERSION,
        "final_top_k": final_top_k,
        "canonical_ordering": "record-ref-key-ascending-before-candidate-generation",
        "canonical_tie_rule": "full-score-desc-record-ref-key-asc",
        "post_second_pass_failure_policy": (
            LexicalRetrievalFailureCategory.CANDIDATE_POOL_INSUFFICIENT.value
        ),
    }


def lexical_strategy_contract_fingerprint(final_top_k: int, **kwargs) -> str:
    encoded = json.dumps(
        lexical_strategy_contract_payload(final_top_k, **kwargs),
        ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _percentile(values: np.ndarray, percentile: int) -> int:
    return int(np.percentile(values, percentile, method="higher")) if len(values) else 0


def _canonical_top_k_positions(scores, targets, ref_values, top_k):
    if len(scores) <= top_k:
        return np.lexsort((ref_values[targets], -scores))
    provisional = np.argpartition(-scores, top_k - 1)[:top_k]
    boundary = scores[provisional].min()
    above = np.flatnonzero(scores > boundary)
    tied = np.flatnonzero(scores == boundary)
    needed = top_k - len(above)
    if len(tied) > needed:
        tied = tied[np.argsort(ref_values[targets[tied]], kind="stable")[:needed]]
    selected = np.concatenate((above, tied))
    return selected[np.lexsort((ref_values[targets[selected]], -scores[selected]))]


def retrieve_exact_indexed_lexical_neighbors(
    matrix, canonical_record_refs, final_top_k: int,
) -> IndexedLexicalResult:
    """Enumerate shared-feature candidates and rank by exact v4 cosine."""
    count = matrix.shape[0]
    refs = tuple(str(value or "").strip() for value in canonical_record_refs)
    if len(refs) != count or any(not value for value in refs):
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_CONFIGURATION_INVALID,
            "lexical retrieval requires one canonical record reference per row",
        )
    if len(set(refs)) != count:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_CONFIGURATION_INVALID,
            "lexical retrieval canonical record references must be unique",
        )
    contract_fingerprint = lexical_retrieval_contract_fingerprint(final_top_k)
    build_started = time.perf_counter()
    try:
        csr = matrix.tocsr(copy=False)
        csc = csr.tocsc(copy=False)
        cosine_matrix = normalize(csr, copy=True)
        posting_sizes = np.diff(csc.indptr)
    except Exception as exc:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_BUILD_FAILED,
            "exact lexical index construction failed",
        ) from exc
    build_ms = (time.perf_counter() - build_started) * 1000

    directed = {}
    evaluations = 0
    max_union = 0
    query_started = time.perf_counter()
    try:
        transpose = cosine_matrix.T
        ref_values = np.asarray(refs, dtype=object)
        def query_batch(start):
            similarities = (
                cosine_matrix[start:start + LEXICAL_QUERY_BATCH_SIZE] @ transpose
            ).tocsr()
            similarities.eliminate_zeros()
            rows = []
            batch_evaluations = 0
            batch_max_union = 0
            for offset in range(similarities.shape[0]):
                source = start + offset
                left, right = similarities.indptr[offset:offset + 2]
                targets = similarities.indices[left:right]
                scores = similarities.data[left:right]
                keep = (targets != source) & (scores > 0)
                targets, scores = targets[keep], scores[keep]
                batch_evaluations += len(targets)
                batch_max_union = max(batch_max_union, len(targets))
                order = _canonical_top_k_positions(
                    scores, targets, ref_values, final_top_k
                )
                rows.append((source, tuple(
                    (int(targets[position]), float(scores[position]))
                    for position in order
                )))
            return rows, batch_evaluations, batch_max_union

        starts = range(0, count, LEXICAL_QUERY_BATCH_SIZE)
        with ThreadPoolExecutor(max_workers=LEXICAL_QUERY_WORKERS) as executor:
            for rows, batch_evaluations, batch_max_union in executor.map(
                query_batch, starts
            ):
                directed.update(rows)
                evaluations += batch_evaluations
                max_union = max(max_union, batch_max_union)
    except Exception as exc:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_QUERY_FAILED,
            "exact lexical index query failed",
        ) from exc
    query_ms = (time.perf_counter() - query_started) * 1000
    brute = count * max(0, count - 1)
    metrics = LexicalRetrievalWorkMetrics(
        strategy=LEXICAL_RETRIEVAL_STRATEGY,
        contract_fingerprint=contract_fingerprint,
        feature_count=int(csr.shape[1]),
        posting_entry_count=int(csr.nnz),
        posting_size_p50=_percentile(posting_sizes, 50),
        posting_size_p95=_percentile(posting_sizes, 95),
        posting_size_p99=_percentile(posting_sizes, 99),
        max_posting_size=int(posting_sizes.max()) if len(posting_sizes) else 0,
        candidate_union_enumerations=int(evaluations),
        unique_directed_candidates=int(evaluations),
        exact_score_evaluations=int(evaluations),
        theoretical_brute_directed_comparisons=int(brute),
        zero_overlap_comparisons_avoided=int(brute - evaluations),
        max_anchor_candidate_union=int(max_union),
        index_build_time_ms=round(build_ms, 3),
        query_scoring_time_ms=round(query_ms, 3),
    )
    return IndexedLexicalResult(directed_neighbors=directed, metrics=metrics)


def _validate_and_stabilize(matrix, canonical_record_refs):
    count = matrix.shape[0]
    refs = tuple(str(value or "").strip() for value in canonical_record_refs)
    if len(refs) != count or any(not value for value in refs) or len(set(refs)) != count:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_CONFIGURATION_INVALID,
            "lexical retrieval requires one unique canonical record reference per row",
        )
    order = np.asarray(
        sorted(range(count), key=lambda index: refs[index]), dtype=np.int64
    )
    stable = normalize(matrix.tocsr(copy=True)[order], copy=False)
    return stable, tuple(refs[index] for index in order), order


def _rank_rarest_features(features, weights, posting_sizes):
    sizes = posting_sizes[features]
    order = np.lexsort((features, -weights, sizes))
    return features[order], weights[order], sizes[order]


def _bounded_candidate_pools(
    matrix, sources, csc, posting_sizes, configuration,
):
    pools = []
    posting_visits = unique_candidates = 0
    for source in sources:
        left, right = matrix.indptr[source:source + 2]
        features, weights, sizes = _rank_rarest_features(
            matrix.indices[left:right], matrix.data[left:right], posting_sizes
        )
        remaining = configuration.visit_budget
        target_parts, value_parts = [], []
        for feature, weight, size in zip(
            features[:configuration.feature_limit],
            weights[:configuration.feature_limit],
            sizes[:configuration.feature_limit],
        ):
            if size > remaining:
                continue
            pleft, pright = csc.indptr[feature:feature + 2]
            target_parts.append(csc.indices[pleft:pright])
            value_parts.append(weight * csc.data[pleft:pright])
            posting_visits += int(size)
            remaining -= int(size)
        if not target_parts:
            pools.append(np.empty(0, dtype=np.int64))
            continue
        targets = np.concatenate(target_parts)
        contributions = np.concatenate(value_parts)
        unique, inverse = np.unique(targets, return_inverse=True)
        support = np.zeros(len(unique), dtype=np.float64)
        np.add.at(support, inverse, contributions)
        keep = (unique != source) & (support > 0)
        unique, support = unique[keep], support[keep]
        unique_candidates += len(unique)
        selected = np.lexsort((unique, -support))[:configuration.candidate_pool]
        pools.append(unique[selected])
    return pools, posting_visits, unique_candidates


def _exact_rerank_pools(matrix, refs, sources, pools, final_top_k):
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
        selected = _canonical_top_k_positions(
            positive_scores, positive_pool, ref_values, final_top_k
        )
        directed[source] = tuple(
            (int(positive_pool[position]), float(positive_scores[position]))
            for position in selected
        )
    return directed


def retrieve_bounded_lexical_neighbors(
    matrix, canonical_record_refs, final_top_k: int,
) -> IndexedLexicalResult:
    """Run the frozen bounded primary and one fixed fail-closed second pass."""
    started = time.perf_counter()
    try:
        stable, stable_refs, original_positions = _validate_and_stabilize(
            matrix, canonical_record_refs
        )
        csc = stable.tocsc(copy=False)
        posting_sizes = np.diff(csc.indptr).astype(np.int64, copy=False)
    except LexicalRetrievalError:
        raise
    except Exception as exc:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_BUILD_FAILED,
            "bounded lexical index construction failed",
        ) from exc
    build_ms = (time.perf_counter() - started) * 1000
    query_started = time.perf_counter()
    primary_directed = {}
    primary_visits = primary_unique = primary_reranks = 0
    all_sources = tuple(range(stable.shape[0]))
    try:
        for offset in range(0, len(all_sources), PRIMARY_BOUNDED_CONFIGURATION.batch_size):
            sources = all_sources[offset:offset + PRIMARY_BOUNDED_CONFIGURATION.batch_size]
            pools, visits, unique = _bounded_candidate_pools(
                stable, sources, csc, posting_sizes,
                PRIMARY_BOUNDED_CONFIGURATION,
            )
            primary_visits += visits
            primary_unique += unique
            primary_reranks += sum(len(pool) for pool in pools)
            primary_directed.update(_exact_rerank_pools(
                stable, stable_refs, sources, pools, final_top_k
            ))
        insufficient = tuple(
            source for source in all_sources
            if len(primary_directed[source]) < final_top_k
        )
        second_started = time.perf_counter()
        second_directed = {}
        second_visits = second_unique = second_reranks = 0
        for offset in range(
            0, len(insufficient), SECOND_PASS_BOUNDED_CONFIGURATION.batch_size
        ):
            sources = insufficient[
                offset:offset + SECOND_PASS_BOUNDED_CONFIGURATION.batch_size
            ]
            pools, visits, unique = _bounded_candidate_pools(
                stable, sources, csc, posting_sizes,
                SECOND_PASS_BOUNDED_CONFIGURATION,
            )
            second_visits += visits
            second_unique += unique
            second_reranks += sum(len(pool) for pool in pools)
            second_directed.update(_exact_rerank_pools(
                stable, stable_refs, sources, pools, final_top_k
            ))
        second_ms = (time.perf_counter() - second_started) * 1000
    except LexicalRetrievalError:
        raise
    except Exception as exc:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.INDEX_QUERY_FAILED,
            "bounded lexical index query failed",
        ) from exc
    directed_stable = dict(primary_directed)
    directed_stable.update(second_directed)
    remaining = tuple(
        source for source in insufficient
        if len(directed_stable[source]) < final_top_k
    )
    if remaining:
        raise LexicalRetrievalError(
            LexicalRetrievalFailureCategory.CANDIDATE_POOL_INSUFFICIENT,
            "bounded lexical candidate pool remains insufficient after fixed second pass",
        )
    directed = {
        int(original_positions[source]): tuple(
            (int(original_positions[target]), score) for target, score in rows
        )
        for source, rows in directed_stable.items()
    }
    query_ms = (time.perf_counter() - query_started) * 1000
    exact_reranks = primary_reranks + second_reranks
    brute = stable.shape[0] * max(0, stable.shape[0] - 1)
    metrics = LexicalRetrievalWorkMetrics(
        strategy=BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS,
        contract_fingerprint=lexical_strategy_contract_fingerprint(final_top_k),
        feature_count=int(stable.shape[1]),
        posting_entry_count=int(stable.nnz),
        posting_size_p50=_percentile(posting_sizes, 50),
        posting_size_p95=_percentile(posting_sizes, 95),
        posting_size_p99=_percentile(posting_sizes, 99),
        max_posting_size=int(posting_sizes.max()) if len(posting_sizes) else 0,
        candidate_union_enumerations=int(primary_visits + second_visits),
        unique_directed_candidates=int(primary_unique + second_unique),
        exact_score_evaluations=int(exact_reranks),
        theoretical_brute_directed_comparisons=int(brute),
        zero_overlap_comparisons_avoided=int(max(0, brute - exact_reranks)),
        max_anchor_candidate_union=max(
            PRIMARY_BOUNDED_CONFIGURATION.candidate_pool,
            SECOND_PASS_BOUNDED_CONFIGURATION.candidate_pool,
        ),
        index_build_time_ms=round(build_ms, 3),
        query_scoring_time_ms=round(query_ms, 3),
        primary_insufficient_anchors=len(insufficient),
        second_pass_anchors=len(insufficient),
        second_pass_recovered_anchors=len(insufficient),
        remaining_insufficient_anchors=0,
        second_pass_posting_visits=int(second_visits),
        second_pass_exact_reranks=int(second_reranks),
        second_pass_time_ms=round(second_ms, 3),
    )
    return IndexedLexicalResult(directed, metrics)


def retrieve_production_lexical_neighbors(
    matrix, canonical_record_refs, final_top_k: int,
) -> IndexedLexicalResult:
    """Select only from the frozen deterministic eligible-record count."""
    strategy = select_lexical_strategy(matrix.shape[0])
    if strategy == EXACT_INDEXED_V4:
        return retrieve_exact_indexed_lexical_neighbors(
            matrix, canonical_record_refs, final_top_k
        )
    return retrieve_bounded_lexical_neighbors(
        matrix, canonical_record_refs, final_top_k
    )
