"""Provider-free GF-11B production character retrieval quality measurements."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from app.benchmarks.approximate_character_retrieval import corpus_vectors
from app.benchmarks.character_retrieval_contract import _coverage, _pairs
from app.benchmarks.group_first_scale import benchmark_configuration
from app.services import hybrid_retrieval
from app.services.character_retrieval import (
    CharacterRetrievalStrategy,
    retrieve_lsh_directed_neighbors,
    select_character_retrieval_strategy,
)
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    MemoryEmbeddingVectorCache,
    _deterministic_directed_neighbors,
)


def _candidate_pairs(result):
    return {
        tuple(sorted((item.left_record_id, item.right_record_id)))
        for item in result.candidates
    }


def _hybrid_result(records, refs, *, force_exact: bool):
    frame = records.copy()
    frame[CANONICAL_RECORD_REF_FIELD] = refs
    original = hybrid_retrieval.select_character_retrieval_strategy
    if force_exact:
        hybrid_retrieval.select_character_retrieval_strategy = (
            lambda _count: CharacterRetrievalStrategy.EXACT
        )
    try:
        return HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(frame, "DISCOVERY")
    finally:
        hybrid_retrieval.select_character_retrieval_strategy = original


def run_production_quality(records: int, *, seed: int = 1101) -> dict:
    corpus, matrix, refs = corpus_vectors(records, seed=seed)
    exact_started = time.perf_counter()
    exact = _deterministic_directed_neighbors(matrix, 5, refs)
    exact_seconds = time.perf_counter() - exact_started
    strategy = select_character_retrieval_strategy(records)
    if strategy == CharacterRetrievalStrategy.EXACT:
        production = exact
        work = None
    else:
        lsh = retrieve_lsh_directed_neighbors(matrix, refs, 5)
        production = lsh.directed_neighbors
        work = asdict(lsh.metrics)
        work["strategy"] = lsh.metrics.strategy.value

    exact_pairs = _pairs(exact)
    production_pairs = _pairs(production)
    exact_hybrid = _hybrid_result(corpus.records, refs, force_exact=True)
    production_hybrid = _hybrid_result(corpus.records, refs, force_exact=False)
    exact_final = _candidate_pairs(exact_hybrid)
    production_final = _candidate_pairs(production_hybrid)
    return {
        "records": records,
        "seed": seed,
        "strategy": strategy.value,
        "exact_char_seconds": round(exact_seconds, 6),
        "production_character_work": work,
        "exact_character_pair_count": len(exact_pairs),
        "production_character_pair_count": len(production_pairs),
        "exact_character_coverage": _coverage(exact_pairs, corpus.truth),
        "production_character_coverage": _coverage(production_pairs, corpus.truth),
        "final_hybrid_exact_count": len(exact_final),
        "final_hybrid_production_count": len(production_final),
        "final_hybrid_overlap": len(exact_final & production_final),
        "final_hybrid_exact_coverage": _coverage(exact_final, corpus.truth),
        "final_hybrid_production_coverage": _coverage(production_final, corpus.truth),
        "provider_request_count": (
            exact_hybrid.metrics.provider_request_count
            + production_hybrid.metrics.provider_request_count
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=1101)
    arguments = parser.parse_args(argv)
    print(json.dumps(
        run_production_quality(arguments.records, seed=arguments.seed),
        indent=2, sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
