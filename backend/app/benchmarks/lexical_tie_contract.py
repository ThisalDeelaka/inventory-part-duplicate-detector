"""GF-11C-PRE deterministic lexical-reference measurements."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors

from app.benchmarks.contracts import stable_fingerprint
from app.benchmarks.group_first_scale import benchmark_configuration, run_scale_benchmark
from app.benchmarks.group_first_scale_generator import generate_scale_corpus
from app.services.canonical_record_service import canonical_record_ref_key
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    MemoryEmbeddingVectorCache,
    _deterministic_lexical_directed_neighbors,
    _directed_neighbors_to_pairs,
    semantic_retrieval_text,
)


def _historical_directed(matrix, top_k):
    count = matrix.shape[0]
    index = NearestNeighbors(
        n_neighbors=min(count, top_k + 1), metric="cosine", algorithm="brute"
    ).fit(matrix)
    output = {}
    for start in range(0, count, 256):
        distances, indices = index.kneighbors(matrix[start:start + 256])
        for offset, (row_distances, row_indices) in enumerate(zip(distances, indices)):
            source = start + offset
            output[source] = tuple(
                (int(target), float(1.0 - distance))
                for distance, target in zip(row_distances, row_indices)
                if int(target) != source and 1.0 - float(distance) > 0
            )
    return output


def _semantic_signature(directed, refs):
    return tuple(sorted(
        (refs[source], refs[target], round(float(score), 12))
        for source, neighbors in directed.items()
        for target, score in neighbors
    ))


def _pairs(directed):
    return {
        tuple(sorted((source, target)))
        for source, neighbors in directed.items()
        for target, _score in neighbors
    }


def _coverage(pairs, truth):
    def covered(members):
        return any(
            tuple(sorted((left, right))) in pairs
            for index, left in enumerate(members)
            for right in members[index + 1:]
        )
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


def run_lexical_tie_experiment(records, *, seed=1101, permutations=True):
    corpus = generate_scale_corpus(records, seed=seed)
    texts = [semantic_retrieval_text(row) for row in corpus.records.to_dict("records")]
    matrix = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1
    ).fit_transform(texts)
    refs = np.asarray(
        [canonical_record_ref_key(1, index) for index in range(records)], dtype=object
    )
    started = time.perf_counter()
    historical = _historical_directed(matrix, 5)
    historical_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    canonical = _deterministic_lexical_directed_neighbors(matrix, 5, refs)
    canonical_ms = (time.perf_counter() - started) * 1000

    substitutions = unequal = boundary_anchors = tied_candidates = 0
    for source in range(records):
        old, new = dict(historical[source]), dict(canonical[source])
        removed, added = set(old) - set(new), set(new) - set(old)
        substitutions += len(removed) + len(added)
        if new and len(new) == min(5, records - 1):
            boundary = min(new.values())
            tied = sum(
                abs(float(cosine) - boundary) <= 1e-12
                for target, cosine in enumerate((matrix[source] @ matrix.T).toarray()[0])
                if target != source and cosine > 0
            )
            if tied > 1:
                boundary_anchors += 1
                tied_candidates += tied
        if removed or added:
            boundary = min(new.values())
            changed = [old[target] for target in removed] + [new[target] for target in added]
            unequal += int(any(abs(score - boundary) > 1e-12 for score in changed))

    signature = _semantic_signature(canonical, refs)
    differences = {"original": 0}
    if permutations:
        orders = {
            "reversed": np.arange(records)[::-1],
            **{f"shuffle_{value}": np.random.default_rng(value).permutation(records) for value in (7, 19, 1101)},
        }
        for name, order in orders.items():
            candidate_refs = refs[order]
            candidate = _semantic_signature(
                _deterministic_lexical_directed_neighbors(matrix[order], 5, candidate_refs),
                candidate_refs,
            )
            differences[name] = len(set(signature) ^ set(candidate))

    old_pairs, new_pairs = _pairs(historical), _pairs(canonical)
    generic = {index for index, code in enumerate(corpus.truth.scenario_by_source_row) if code == "S3"}
    old_rows = _directed_neighbors_to_pairs(historical, refs)
    new_rows = _directed_neighbors_to_pairs(canonical, refs)
    return {
        "records": records,
        "historical_ms": round(historical_ms, 3),
        "canonical_ms": round(canonical_ms, 3),
        "anchors_with_kth_boundary_ties": boundary_anchors,
        "tied_candidates_at_boundaries": tied_candidates,
        "directed_tie_substitutions": substitutions,
        "unequal_score_substitution_anchors": unequal,
        "lexical_pair_symmetric_difference": len(old_pairs ^ new_pairs),
        "historical_lexical_fingerprint": stable_fingerprint(old_rows),
        "canonical_lexical_fingerprint": stable_fingerprint(new_rows),
        "permutation_pair_differences": differences,
        "historical_coverage": _coverage(old_pairs, corpus.truth),
        "canonical_coverage": _coverage(new_pairs, corpus.truth),
        "historical_generic_hub_pairs": sum(left in generic and right in generic for left, right in old_pairs),
        "canonical_generic_hub_pairs": sum(left in generic and right in generic for left, right in new_pairs),
    }


def run_hybrid_comparison(records, *, seed=1101):
    from app.services import hybrid_retrieval
    corpus = generate_scale_corpus(records, seed=seed)
    data = corpus.records.copy()
    refs = tuple(canonical_record_ref_key(1, index) for index in range(records))
    data[CANONICAL_RECORD_REF_FIELD] = refs
    original = hybrid_retrieval._deterministic_lexical_nearest_pairs
    def run(historical):
        hybrid_retrieval._deterministic_lexical_nearest_pairs = (
            (lambda matrix, top_k, _refs: hybrid_retrieval._nearest_pairs(matrix, top_k))
            if historical else original
        )
        return HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")
    try:
        historical, canonical = run(True), run(False)
    finally:
        hybrid_retrieval._deterministic_lexical_nearest_pairs = original
    def signature(result):
        return tuple(
            (tuple(sorted((refs[item.left_record_id], refs[item.right_record_id]))), item.retrieval_priority,
             item.retrieval_rank, item.retrieval_tier.value, item.evidence.retrieval_sources,
             item.evidence.channel_ranks, item.evidence.channel_scores, item.evidence.reciprocal_sources)
            for item in result.candidates
        )
    old_pairs = {tuple(sorted((item.left_record_id, item.right_record_id))) for item in historical.candidates}
    new_pairs = {tuple(sorted((item.left_record_id, item.right_record_id))) for item in canonical.candidates}
    generic = {index for index, code in enumerate(corpus.truth.scenario_by_source_row) if code == "S3"}
    return {
        "historical_candidate_count": len(historical.candidates),
        "canonical_candidate_count": len(canonical.candidates),
        "candidate_pair_symmetric_difference": len(old_pairs ^ new_pairs),
        "pair_overlap": len(old_pairs & new_pairs),
        "historical_fingerprint": stable_fingerprint(signature(historical)),
        "canonical_fingerprint": stable_fingerprint(signature(canonical)),
        "historical_coverage": _coverage(old_pairs, corpus.truth),
        "canonical_coverage": _coverage(new_pairs, corpus.truth),
        "historical_generic_hub_pairs": sum(left in generic and right in generic for left, right in old_pairs),
        "canonical_generic_hub_pairs": sum(left in generic and right in generic for left, right in new_pairs),
        "provider_calls": historical.metrics.provider_request_count + canonical.metrics.provider_request_count,
    }


def run_downstream_comparison(records=64, *, seed=1101):
    from app.services import hybrid_retrieval
    original = hybrid_retrieval._deterministic_lexical_nearest_pairs
    results = {}
    try:
        with tempfile.TemporaryDirectory(prefix="gf11c-pre-") as directory:
            for name, historical in (("HISTORICAL", True), ("CANONICAL", False)):
                hybrid_retrieval._deterministic_lexical_nearest_pairs = (
                    (lambda matrix, top_k, _refs: hybrid_retrieval._nearest_pairs(matrix, top_k))
                    if historical else original
                )
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
        hybrid_retrieval._deterministic_lexical_nearest_pairs = original
    return results


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=1101)
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--downstream", action="store_true")
    parser.add_argument("--no-permutations", action="store_true")
    args = parser.parse_args(argv)
    if args.downstream:
        result = run_downstream_comparison(args.records, seed=args.seed)
    elif args.hybrid:
        result = run_hybrid_comparison(args.records, seed=args.seed)
    else:
        result = run_lexical_tie_experiment(
            args.records, seed=args.seed, permutations=not args.no_permutations
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
