"""GF-11B-PRE experiments for the character-retrieval contract.

This module is benchmark-only.  It does not participate in scan execution and
keeps benchmark truth outside every retrieval input.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize

from app.benchmarks.group_first_scale_generator import generate_scale_corpus
from app.services.hybrid_retrieval import SklearnHashingEmbedder, semantic_retrieval_text


def _token_character_ngrams(text):
    features = []
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        bounded = f"^{token}$"
        for size in (3, 4, 5):
            features.extend(
                bounded[index:index + size]
                for index in range(max(0, len(bounded) - size + 1))
            )
    return features


def _current_directed(matrix, refs, *, top_k=5, batch_size=256):
    index = NearestNeighbors(
        n_neighbors=min(len(refs), top_k + 1), metric="cosine", algorithm="brute"
    ).fit(matrix)
    output = {}
    for start in range(0, len(refs), batch_size):
        distances, indices = index.kneighbors(matrix[start:start + batch_size])
        for offset, (row_distances, row_indices) in enumerate(zip(distances, indices)):
            source = start + offset
            output[int(refs[source])] = tuple(
                (int(refs[int(target)]), float(1.0 - distance))
                for distance, target in zip(row_distances, row_indices)
                if source != int(target)
            )
    return output


def _stable_dense_directed(matrix, refs, *, top_k=5, batch_size=128):
    output = {}
    boundary_ties = 0
    boundary_tied_candidates = 0
    index = NearestNeighbors(
        n_neighbors=len(refs), metric="cosine", algorithm="brute"
    ).fit(matrix)
    for start in range(0, len(refs), batch_size):
        distances, indices = index.kneighbors(
            matrix[start:start + batch_size], n_neighbors=len(refs)
        )
        for offset, (row_distances, row_indices) in enumerate(zip(distances, indices)):
            source = start + offset
            scores = 1.0 - row_distances
            row_refs = refs[row_indices]
            keep = row_indices != source
            scores, row_refs = scores[keep], row_refs[keep]
            order = np.lexsort((row_refs, -scores))[:top_k]
            output[int(refs[source])] = tuple(
                (int(row_refs[target]), float(scores[target])) for target in order
            )
            if len(refs) > top_k:
                boundary = scores[order[-1]]
                tied = int(np.count_nonzero(scores == boundary))
                if tied > 1:
                    boundary_ties += 1
                    boundary_tied_candidates += tied
    return output, boundary_ties, boundary_tied_candidates


def _sparse_directed(matrix, refs, *, top_k=5, batch_size=64):
    started = time.perf_counter()
    csr = matrix.tocsr()
    postings = csr.tocsc()
    lengths = np.diff(postings.indptr)
    build_ms = (time.perf_counter() - started) * 1000
    output = {}
    evaluations = 0
    max_accumulator = 0
    query_started = time.perf_counter()
    for start in range(0, len(refs), batch_size):
        similarities = (csr[start:start + batch_size] @ csr.T).tocsr()
        similarities.eliminate_zeros()
        for offset in range(similarities.shape[0]):
            source = start + offset
            left, right = similarities.indptr[offset:offset + 2]
            targets = similarities.indices[left:right]
            scores = similarities.data[left:right]
            keep = (targets != source) & (scores > 0)
            targets, scores = targets[keep], scores[keep]
            evaluations += len(targets)
            max_accumulator = max(max_accumulator, len(targets))
            order = np.lexsort((refs[targets], -scores))[:top_k]
            output[int(refs[source])] = tuple(
                (int(refs[int(targets[position])]), float(scores[position]))
                for position in order
            )
    metrics = {
        "index_build_time_ms": round(build_ms, 3),
        "query_time_ms": round((time.perf_counter() - query_started) * 1000, 3),
        "index_feature_count": int(csr.shape[1]),
        "posting_entry_count": int(csr.nnz),
        "max_posting_size": int(lengths.max()) if len(lengths) else 0,
        "p95_posting_size": int(np.percentile(lengths, 95, method="higher")) if len(lengths) else 0,
        "candidate_enumeration_count": int(sum(int(n) * (int(n) - 1) for n in lengths)),
        "exact_similarity_evaluation_count": int(evaluations),
        "zero_overlap_comparisons_avoided": int(len(refs) * (len(refs) - 1) - evaluations),
        "max_anchor_candidate_accumulator": int(max_accumulator),
    }
    return output, metrics


def _pairs(directed):
    result = set()
    for source, neighbors in directed.items():
        for target, _score in neighbors:
            result.add(tuple(sorted((source, target))))
    return result


def _production_pair_rows(directed):
    pairs = {}
    for source, neighbors in directed.items():
        for target, score in neighbors:
            pair = tuple(sorted((source, target)))
            value = pairs.setdefault(pair, {"score": 0.0, "directions": set()})
            value["score"] = max(value["score"], round(max(0.0, score) * 100, 2))
            value["directions"].add((source, target))
    rows = [
        (
            left, right, value["score"], len(value["directions"]) == 2
        )
        for (left, right), value in pairs.items()
        if value["score"] > 0
    ]
    return sorted(rows, key=lambda item: (-item[2], item[0], item[1]))


def run_downstream_experiment(records=64, *, seed=1101):
    """Compare manageable normal GF1-GF6 runs without changing production code."""
    from pathlib import Path
    from app.benchmarks.group_first_scale import run_scale_benchmark
    from app.services import hybrid_retrieval

    corpus = generate_scale_corpus(records, seed=seed)
    texts = [semantic_retrieval_text(row) for row in corpus.records.to_dict("records")]
    refs = np.arange(records, dtype=np.int64)
    dense = normalize(SklearnHashingEmbedder().encode(texts))
    stable, _anchors, _ties = _stable_dense_directed(dense, refs)
    sparse_matrix = TfidfVectorizer(
        analyzer=_token_character_ngrams, min_df=1, lowercase=False
    ).fit_transform(texts)
    sparse_result, _metrics = _sparse_directed(sparse_matrix, refs)
    alternatives = {
        "CURRENT": None,
        "DETERMINISTIC_TIE": _production_pair_rows(stable),
        "SPARSE_CHARACTER": _production_pair_rows(sparse_result),
    }
    original = hybrid_retrieval._nearest_pairs
    results = {}
    try:
        with tempfile.TemporaryDirectory(prefix="gf11b-pre-") as directory:
            for name, replacement in alternatives.items():
                calls = {"value": 0}
                if replacement is not None:
                    def selected(matrix, top_k, *, _replacement=replacement):
                        calls["value"] += 1
                        if calls["value"] % 2 == 1:
                            return original(matrix, top_k)
                        return _replacement
                    hybrid_retrieval._nearest_pairs = selected
                else:
                    hybrid_retrieval._nearest_pairs = original
                result = run_scale_benchmark(
                    records=records, seed=seed, scenario="canonical-mixed",
                    db_path=Path(directory) / f"{name.casefold()}.sqlite",
                    hybrid_enabled=True,
                )
                results[name] = {
                    "status": result.run.status.value,
                    "safe_failure_category": result.run.safe_failure_category,
                    "row_counts": dict(result.database_metrics.row_counts),
                    "safety": result.safety_metrics.__dict__,
                    "quality": result.quality_metrics.__dict__,
                    "complexity": dict(result.complexity_metrics),
                }
    finally:
        hybrid_retrieval._nearest_pairs = original
    return results


def _coverage(pairs, truth):
    def covered(members):
        return any(tuple(sorted((left, right))) in pairs for i, left in enumerate(members) for right in members[i + 1:])

    by_code = defaultdict(lambda: [0, 0])
    for _identity, members in truth.duplicate_sets:
        codes = {truth.scenario_by_source_row[item] for item in members}
        code = next(iter(codes)) if len(codes) == 1 else "MIXED"
        by_code[code][1] += 1
        by_code[code][0] += int(covered(members))
    return {
        "true_sets": [sum(value[0] for value in by_code.values()), sum(value[1] for value in by_code.values())],
        "cross_site_S5": by_code["S5"],
        "bridge_S7": by_code["S7"],
        "protected_conflicts": [
            sum(covered(members) for members in truth.protected_conflict_sets),
            len(truth.protected_conflict_sets),
        ],
    }


def run_character_contract_experiment(records, *, seed=1101):
    corpus = generate_scale_corpus(records, seed=seed)
    texts = [semantic_retrieval_text(row) for row in corpus.records.to_dict("records")]
    refs = np.arange(records, dtype=np.int64)
    dense = normalize(SklearnHashingEmbedder().encode(texts))

    started = time.perf_counter()
    current = _current_directed(dense, refs)
    current_ms = (time.perf_counter() - started) * 1000
    repeated = _current_directed(dense, refs)
    block_64 = _current_directed(dense, refs, batch_size=64)

    rng = np.random.default_rng(seed)
    permutation = rng.permutation(records)
    shuffled = _current_directed(dense[permutation], refs[permutation])

    stable_started = time.perf_counter()
    stable, anchors_with_tie, tied_candidates = _stable_dense_directed(dense, refs)
    stable_ms = (time.perf_counter() - stable_started) * 1000

    current_pairs, shuffled_pairs, stable_pairs = map(_pairs, (current, shuffled, stable))
    current_vs_shuffle = current_pairs ^ shuffled_pairs
    current_vs_stable = current_pairs ^ stable_pairs

    unequal_score_changes = 0
    unequal_rounded_score_changes = 0
    changed_anchors = 0
    for anchor in refs:
        old = {target: score for target, score in current[int(anchor)]}
        new = {target: score for target, score in stable[int(anchor)]}
        removed, added = set(old) - set(new), set(new) - set(old)
        if removed or added:
            changed_anchors += 1
            boundary = min(new.values())
            changed_scores = [old[target] for target in removed] + [new[target] for target in added]
            if any(
                not np.isclose(score, boundary, rtol=1e-6, atol=1e-7)
                for score in changed_scores
            ):
                unequal_score_changes += 1
            if any(round(score * 100, 2) != round(boundary * 100, 2) for score in changed_scores):
                unequal_rounded_score_changes += 1

    sparse_started = time.perf_counter()
    sparse_matrix = TfidfVectorizer(
        analyzer=_token_character_ngrams, min_df=1, lowercase=False
    ).fit_transform(texts)
    sparse_feature_ms = (time.perf_counter() - sparse_started) * 1000
    sparse_result, sparse_metrics = _sparse_directed(sparse_matrix, refs)
    sparse_pairs = _pairs(sparse_result)

    generic_refs = {i for i, code in enumerate(corpus.truth.scenario_by_source_row) if code == "S3"}
    def generic_pairs(pairs):
        return sum(left in generic_refs and right in generic_refs for left, right in pairs)

    union = current_pairs | sparse_pairs
    return {
        "records": records,
        "current_dense_ms": round(current_ms, 3),
        "deterministic_dense_ms": round(stable_ms, 3),
        "repeated_equal": current == repeated,
        "block_size_equal": current == block_64,
        "input_order_pair_symmetric_difference": len(current_vs_shuffle),
        "anchors_with_kth_boundary_tie": anchors_with_tie,
        "tied_candidates_at_boundaries": tied_candidates,
        "anchors_changed_by_deterministic_tie": changed_anchors,
        "current_vs_deterministic_pair_symmetric_difference": len(current_vs_stable),
        "anchors_with_unequal_score_membership_change": unequal_score_changes,
        "anchors_with_unequal_rounded_score_membership_change": unequal_rounded_score_changes,
        "current_pair_count": len(current_pairs),
        "deterministic_pair_count": len(stable_pairs),
        "sparse_pair_count": len(sparse_pairs),
        "sparse_pair_jaccard_vs_current": round(len(current_pairs & sparse_pairs) / max(1, len(union)), 6),
        "current_coverage": _coverage(current_pairs, corpus.truth),
        "deterministic_coverage": _coverage(stable_pairs, corpus.truth),
        "sparse_coverage": _coverage(sparse_pairs, corpus.truth),
        "current_generic_hub_pairs": generic_pairs(current_pairs),
        "sparse_generic_hub_pairs": generic_pairs(sparse_pairs),
        "sparse_feature_time_ms": round(sparse_feature_ms, 3),
        "sparse_metrics": sparse_metrics,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, choices=(64, 500, 5000), required=True)
    parser.add_argument("--seed", type=int, default=1101)
    parser.add_argument("--downstream", action="store_true")
    args = parser.parse_args(argv)
    result = (
        run_downstream_experiment(args.records, seed=args.seed)
        if args.downstream else run_character_contract_experiment(args.records, seed=args.seed)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
