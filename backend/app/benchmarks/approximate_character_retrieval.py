"""GF-11B-ANN benchmark-only approximate character retrieval experiments.

Nothing in this module participates in production discovery.  Approximate
search nominates candidates only; the current 384-bin vectors, exact cosine,
and canonical record-reference tie ordering remain the final selector.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import time
from dataclasses import asdict, dataclass
from enum import Enum

import numpy as np
import sklearn
from sklearn.preprocessing import normalize

from app.benchmarks.contracts import stable_fingerprint
from app.benchmarks.group_first_scale_generator import generate_scale_corpus
from app.services.canonical_record_service import canonical_record_ref_key
from app.services.hybrid_retrieval import (
    SklearnHashingEmbedder,
    _deterministic_directed_neighbors,
    semantic_retrieval_text,
)


LSH_ALGORITHM_VERSION = "fixed-seed-cosine-lsh-exact-rerank-v1"
VECTOR_REPRESENTATION_VERSION = "sklearn-hashing-domain-v1-384-char-wb-3-5"
EXACT_RERANK_VERSION = "exact-cosine-canonical-tie-v1"
DEFAULT_SEED = 1101


class ExperimentStatus(str, Enum):
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


class UnavailableAnnBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class LshConfiguration:
    table_count: int = 8
    bits_per_table: int = 12
    probe_radius: int = 2
    candidate_pool_k: int = 80
    final_top_k: int = 5
    seed: int = DEFAULT_SEED
    bucket_probe_cap_multiplier: int = 2
    candidate_gather_multiplier: int = 4

    def validate(self) -> None:
        if self.final_top_k < 1:
            raise ValueError("final_top_k must be positive")
        if self.candidate_pool_k < self.final_top_k:
            raise ValueError("candidate_pool_k cannot be below final_top_k")
        if not 1 <= self.table_count <= 32:
            raise ValueError("table_count must be between 1 and 32")
        if not 2 <= self.bits_per_table <= 16:
            raise ValueError("bits_per_table must be between 2 and 16")
        if not 0 <= self.probe_radius <= 2:
            raise ValueError("probe_radius must be between 0 and 2")
        if self.bucket_probe_cap_multiplier < 1 or self.candidate_gather_multiplier < 1:
            raise ValueError("candidate bounds must be positive")


@dataclass(frozen=True)
class LshIndex:
    matrix: np.ndarray
    refs: tuple[str, ...]
    original_positions: np.ndarray
    hyperplanes: np.ndarray
    signatures: np.ndarray
    buckets: tuple[dict[int, tuple[int, ...]], ...]
    configuration: LshConfiguration
    build_time_ms: float
    array_bytes: int
    fingerprint: str


@dataclass(frozen=True)
class LshRunResult:
    status: ExperimentStatus
    directed_neighbors: dict[int, tuple[tuple[int, float], ...]]
    index_fingerprint: str
    result_fingerprint: str | None
    build_time_ms: float
    query_time_ms: float
    total_time_ms: float
    candidate_enumerations: int
    exact_rerank_evaluations: int
    max_candidates_gathered: int
    index_array_bytes: int
    vector_array_bytes: int
    provider_request_count: int
    safe_failure_category: str | None


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "UNAVAILABLE"


def ann_backend_inventory() -> dict[str, dict[str, str | bool]]:
    """Return local availability only; importing or installing is unnecessary."""
    candidates = {
        "hnswlib": ("hnswlib", "hnswlib"),
        "usearch": ("usearch", "usearch"),
        "faiss": ("faiss", "faiss-cpu"),
    }
    return {
        name: {
            "available": importlib.util.find_spec(module) is not None,
            "version": _package_version(distribution),
        }
        for name, (module, distribution) in candidates.items()
    }


def require_ann_backend(name: str) -> None:
    inventory = ann_backend_inventory()
    if name not in inventory:
        raise UnavailableAnnBackendError(f"unsupported ANN backend: {name}")
    if not inventory[name]["available"]:
        raise UnavailableAnnBackendError(f"ANN backend is unavailable: {name}")


def _configuration_payload(configuration: LshConfiguration) -> dict:
    return {
        "algorithm_contract_version": LSH_ALGORITHM_VERSION,
        "ann_backend_name": "numpy-random-hyperplane-lsh",
        "ann_backend_version": np.__version__,
        "vector_representation_version": VECTOR_REPRESENTATION_VERSION,
        "seed": configuration.seed,
        "build_parameters": {
            "table_count": configuration.table_count,
            "bits_per_table": configuration.bits_per_table,
            "probe_radius": configuration.probe_radius,
            "bucket_probe_cap_multiplier": configuration.bucket_probe_cap_multiplier,
            "candidate_gather_multiplier": configuration.candidate_gather_multiplier,
            "random_generator": "numpy-PCG64",
            "stable_insertion_order": "record_ref_key-ascending",
        },
        "search_parameters": {
            "candidate_pool_k": configuration.candidate_pool_k,
        },
        "exact_rerank_version": EXACT_RERANK_VERSION,
        "top_k": configuration.final_top_k,
        "numpy_version": np.__version__,
        "scikit_learn_version": sklearn.__version__,
    }


def _probe_masks(bits: int, radius: int) -> tuple[int, ...]:
    masks = [0]
    if radius >= 1:
        masks.extend(1 << bit for bit in range(bits))
    if radius >= 2:
        masks.extend(
            (1 << left) | (1 << right)
            for left in range(bits)
            for right in range(left + 1, bits)
        )
    return tuple(masks)


def build_lsh_index(
    matrix: np.ndarray, canonical_record_refs, configuration: LshConfiguration,
) -> LshIndex:
    configuration.validate()
    values = np.asarray(matrix, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] != 384:
        raise ValueError("LSH requires the current 384-bin character vectors")
    norms = np.linalg.norm(values, axis=1)
    if np.any((norms != 0) & ~np.isclose(norms, 1.0, rtol=1e-5, atol=1e-6)):
        raise ValueError("LSH requires the current L2-normalized character vectors")
    refs = tuple(str(value or "").strip() for value in canonical_record_refs)
    if len(refs) != len(values) or any(not value for value in refs):
        raise ValueError("LSH requires one nonblank canonical reference per vector")
    if len(set(refs)) != len(refs):
        raise ValueError("LSH canonical references must be unique")

    started = time.perf_counter()
    order = np.asarray(sorted(range(len(refs)), key=lambda index: refs[index]), dtype=np.int64)
    stable_matrix = np.ascontiguousarray(values[order], dtype=np.float32)
    stable_refs = tuple(refs[index] for index in order)
    rng = np.random.Generator(np.random.PCG64(configuration.seed))
    hyperplanes = rng.standard_normal(
        (configuration.table_count, configuration.bits_per_table, 384),
        dtype=np.float32,
    )
    hyperplanes = normalize(
        hyperplanes.reshape(-1, 384), norm="l2"
    ).astype(np.float32).reshape(hyperplanes.shape)
    signatures = np.empty((len(refs), configuration.table_count), dtype=np.uint16)
    weights = (1 << np.arange(configuration.bits_per_table, dtype=np.uint16))
    bucket_rows = []
    for table in range(configuration.table_count):
        signs = stable_matrix @ hyperplanes[table].T >= 0
        codes = (signs.astype(np.uint16) * weights).sum(axis=1, dtype=np.uint16)
        signatures[:, table] = codes
        table_buckets: dict[int, list[int]] = {}
        for position, code in enumerate(codes):
            table_buckets.setdefault(int(code), []).append(position)
        bucket_rows.append({key: tuple(value) for key, value in table_buckets.items()})
    payload = _configuration_payload(configuration)
    payload["record_refs"] = stable_refs
    payload["hyperplane_sha256"] = stable_fingerprint(hyperplanes.tolist())
    payload["signature_sha256"] = stable_fingerprint(signatures.tolist())
    array_bytes = int(hyperplanes.nbytes + signatures.nbytes + order.nbytes)
    return LshIndex(
        matrix=stable_matrix,
        refs=stable_refs,
        original_positions=order,
        hyperplanes=hyperplanes,
        signatures=signatures,
        buckets=tuple(bucket_rows),
        configuration=configuration,
        build_time_ms=round((time.perf_counter() - started) * 1000, 3),
        array_bytes=array_bytes,
        fingerprint=stable_fingerprint(payload),
    )


def _semantic_result_fingerprint(index: LshIndex, directed) -> str:
    rows = []
    for source, neighbors in directed.items():
        for target, score in neighbors:
            rows.append({
                "source": index.refs[source],
                "target": index.refs[target],
                "score": round(float(score) * 100, 2),
            })
    return stable_fingerprint(sorted(rows, key=lambda row: (
        row["source"], -row["score"], row["target"]
    )))


def query_lsh_exact_rerank(
    index: LshIndex, *, interrupt_after_anchors: int | None = None,
) -> LshRunResult:
    configuration = index.configuration
    count = len(index.refs)
    if count < 2:
        return LshRunResult(
            ExperimentStatus.COMPLETED, {}, index.fingerprint,
            stable_fingerprint(()), index.build_time_ms, 0.0,
            index.build_time_ms, 0, 0, 0, index.array_bytes,
            int(index.matrix.nbytes), 0, None,
        )
    required = min(configuration.final_top_k, count - 1)
    bucket_cap = max(
        16, configuration.candidate_pool_k * configuration.bucket_probe_cap_multiplier
    )
    gather_limit = min(
        count - 1,
        configuration.candidate_pool_k * configuration.candidate_gather_multiplier,
    )
    masks = _probe_masks(configuration.bits_per_table, configuration.probe_radius)
    popcount = np.fromiter(
        (value.bit_count() for value in range(1 << configuration.bits_per_table)),
        dtype=np.uint8,
    )
    directed_stable: dict[int, tuple[tuple[int, float], ...]] = {}
    candidate_enumerations = 0
    rerank_evaluations = 0
    max_candidates = 0
    query_started = time.perf_counter()

    source = 0
    while source < count:
        if interrupt_after_anchors is not None and source >= interrupt_after_anchors:
            query_ms = (time.perf_counter() - query_started) * 1000
            return LshRunResult(
                ExperimentStatus.INTERRUPTED, {}, index.fingerprint, None,
                index.build_time_ms, round(query_ms, 3),
                round(index.build_time_ms + query_ms, 3), candidate_enumerations,
                rerank_evaluations, max_candidates, index.array_bytes,
                int(index.matrix.nbytes), 0, "INTERRUPTED_BY_BOUND",
            )
        batch_end = min(count, source + 64)
        if interrupt_after_anchors is not None:
            batch_end = min(batch_end, interrupt_after_anchors)
        pools = []
        for anchor in range(source, batch_end):
            candidates: set[int] = set()
            for mask in masks:
                for table in range(configuration.table_count):
                    code = int(index.signatures[anchor, table]) ^ mask
                    bucket = index.buckets[table].get(code, ())
                    candidate_enumerations += min(len(bucket), bucket_cap)
                    candidates.update(bucket[:bucket_cap])
                    candidates.discard(anchor)
                if len(candidates) >= gather_limit:
                    break
            if len(candidates) < required:
                query_ms = (time.perf_counter() - query_started) * 1000
                return LshRunResult(
                    ExperimentStatus.FAILED, {}, index.fingerprint, None,
                    index.build_time_ms, round(query_ms, 3),
                    round(index.build_time_ms + query_ms, 3), candidate_enumerations,
                    rerank_evaluations, max_candidates, index.array_bytes,
                    int(index.matrix.nbytes), 0, "EMPTY_OR_UNDERSIZED_CANDIDATE_POOL",
                )

            candidate_array = np.fromiter(candidates, dtype=np.int64)
            xor = np.bitwise_xor(
                index.signatures[candidate_array], index.signatures[anchor]
            )
            approximate_matches = (
                configuration.table_count * configuration.bits_per_table
                - popcount[xor].sum(axis=1)
            )
            approximate_order = np.lexsort((
                np.asarray([index.refs[item] for item in candidate_array], dtype=object),
                -approximate_matches.astype(np.int32),
            ))
            gathered = candidate_array[approximate_order[:gather_limit]]
            max_candidates = max(max_candidates, len(gathered))
            pools.append(gathered[:configuration.candidate_pool_k])

        pool_lengths = [len(pool) for pool in pools]
        pool_width = max(pool_lengths)
        pool_matrix = np.empty((len(pools), pool_width), dtype=np.int64)
        for offset, pool in enumerate(pools):
            pool_matrix[offset, :len(pool)] = pool
            pool_matrix[offset, len(pool):] = pool[0]
        rerank_evaluations += sum(pool_lengths)
        # Both operands are the frozen L2-normalized vectors.  Their dot product
        # is therefore the exact current cosine, evaluated only on the pool.
        exact_batch = np.einsum(
            "bkd,bd->bk",
            index.matrix[pool_matrix],
            index.matrix[source:batch_end],
            optimize=True,
        )
        for offset, anchor in enumerate(range(source, batch_end)):
            pool = pool_matrix[offset, :pool_lengths[offset]]
            exact_scores = exact_batch[offset, :pool_lengths[offset]]
            exact_order = np.lexsort((
                np.asarray([index.refs[item] for item in pool], dtype=object),
                -exact_scores,
            ))[:required]
            directed_stable[anchor] = tuple(
                (int(pool[position]), float(exact_scores[position]))
                for position in exact_order
                if exact_scores[position] > 0
            )
        source = batch_end

    query_ms = (time.perf_counter() - query_started) * 1000
    semantic_fingerprint = _semantic_result_fingerprint(index, directed_stable)
    remapped = {
        int(index.original_positions[source]): tuple(
            (int(index.original_positions[target]), score) for target, score in neighbors
        )
        for source, neighbors in directed_stable.items()
    }
    return LshRunResult(
        ExperimentStatus.COMPLETED, remapped, index.fingerprint,
        semantic_fingerprint, index.build_time_ms, round(query_ms, 3),
        round(index.build_time_ms + query_ms, 3), candidate_enumerations,
        rerank_evaluations, max_candidates, index.array_bytes,
        int(index.matrix.nbytes), 0, None,
    )


def run_lsh_exact_rerank(
    matrix: np.ndarray, canonical_record_refs, configuration: LshConfiguration,
    *, interrupt_after_anchors: int | None = None,
) -> LshRunResult:
    index = build_lsh_index(matrix, canonical_record_refs, configuration)
    return query_lsh_exact_rerank(
        index, interrupt_after_anchors=interrupt_after_anchors
    )


def _directed_ref_sets(directed, refs) -> dict[str, set[str]]:
    return {
        refs[source]: {refs[target] for target, _score in neighbors}
        for source, neighbors in directed.items()
    }


def _pair_set(directed, refs) -> set[tuple[str, str]]:
    return {
        tuple(sorted((refs[source], refs[target])))
        for source, neighbors in directed.items()
        for target, _score in neighbors
    }


def quality_metrics(exact, approximate, refs) -> dict[str, float | int]:
    exact_by_ref = _directed_ref_sets(exact, refs)
    approximate_by_ref = _directed_ref_sets(approximate, refs)
    recalls = []
    missing = []
    fully_recovered = 0
    for anchor, expected in exact_by_ref.items():
        actual = approximate_by_ref.get(anchor, set())
        recovered = len(expected & actual)
        recalls.append(recovered / max(1, len(expected)))
        missing.append(len(expected - actual))
        fully_recovered += int(expected <= actual)
    exact_pairs = _pair_set(exact, refs)
    approximate_pairs = _pair_set(approximate, refs)
    intersection = exact_pairs & approximate_pairs
    union = exact_pairs | approximate_pairs
    return {
        "directed_neighbor_recall": round(sum(recalls) / max(1, len(recalls)), 6),
        "char_pair_set_recall": round(len(intersection) / max(1, len(exact_pairs)), 6),
        "char_pair_set_precision": round(
            len(intersection) / max(1, len(approximate_pairs)), 6
        ),
        "char_pair_set_jaccard": round(len(intersection) / max(1, len(union)), 6),
        "exact_top_k_anchors_fully_recovered": fully_recovered,
        "anchor_count": len(exact_by_ref),
        "mean_missing_exact_neighbors": round(sum(missing) / max(1, len(missing)), 6),
        "worst_anchor_recall": round(min(recalls, default=1.0), 6),
        "exact_pair_count": len(exact_pairs),
        "approximate_pair_count": len(approximate_pairs),
    }


def corpus_vectors(records: int, *, seed: int = DEFAULT_SEED):
    corpus = generate_scale_corpus(records, seed=seed)
    rows = corpus.records.to_dict("records")
    texts = [semantic_retrieval_text(row) for row in rows]
    matrix = normalize(SklearnHashingEmbedder().encode(texts))
    refs = tuple(canonical_record_ref_key(1, index) for index in range(records))
    return corpus, matrix, refs


def run_quality_sweep(
    records: int, *, seed: int = DEFAULT_SEED,
    pool_multipliers=(1, 2, 4, 8, 16), table_counts=(4, 8, 12),
) -> dict:
    corpus, matrix, refs = corpus_vectors(records, seed=seed)
    exact_started = time.perf_counter()
    exact = _deterministic_directed_neighbors(matrix, 5, refs)
    exact_ms = (time.perf_counter() - exact_started) * 1000
    rows = []
    for tables in table_counts:
        for multiplier in pool_multipliers:
            configuration = LshConfiguration(
                table_count=tables, candidate_pool_k=5 * multiplier, seed=seed
            )
            result = run_lsh_exact_rerank(matrix, refs, configuration)
            row = {
                "configuration": asdict(configuration),
                "status": result.status.value,
                "build_time_ms": result.build_time_ms,
                "query_time_ms": result.query_time_ms,
                "total_time_ms": result.total_time_ms,
                "candidate_enumerations": result.candidate_enumerations,
                "exact_rerank_evaluations": result.exact_rerank_evaluations,
                "max_candidates_gathered": result.max_candidates_gathered,
                "index_array_bytes": result.index_array_bytes,
                "vector_array_bytes": result.vector_array_bytes,
                "result_fingerprint": result.result_fingerprint,
            }
            if result.status == ExperimentStatus.COMPLETED:
                row["quality"] = quality_metrics(
                    exact, result.directed_neighbors, refs
                )
            rows.append(row)
    return {
        "records": records,
        "seed": seed,
        "exact_time_ms": round(exact_ms, 3),
        "exact_result_fingerprint": stable_fingerprint(
            sorted((refs[source], refs[target], round(score * 100, 2))
                   for source, values in exact.items() for target, score in values)
        ),
        "corpus_fingerprint": corpus.generator_fingerprint,
        "backend_inventory": ann_backend_inventory(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        "sweep": rows,
    }


def run_scale_observation(
    records: int, configuration: LshConfiguration, *, seed: int = DEFAULT_SEED,
) -> dict:
    corpus, matrix, refs = corpus_vectors(records, seed=seed)
    result = run_lsh_exact_rerank(matrix, refs, configuration)
    return {
        "records": records,
        "seed": seed,
        "corpus_fingerprint": corpus.generator_fingerprint,
        "configuration": asdict(configuration),
        "status": result.status.value,
        "safe_failure_category": result.safe_failure_category,
        "build_time_ms": result.build_time_ms,
        "query_time_ms": result.query_time_ms,
        "total_time_ms": result.total_time_ms,
        "candidate_enumerations": result.candidate_enumerations,
        "exact_rerank_evaluations": result.exact_rerank_evaluations,
        "max_candidates_gathered": result.max_candidates_gathered,
        "index_array_bytes": result.index_array_bytes,
        "vector_array_bytes": result.vector_array_bytes,
        "result_fingerprint": result.result_fingerprint,
        "provider_request_count": result.provider_request_count,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--pool-k", type=int, default=80)
    parser.add_argument("--tables", type=int, default=8)
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args(argv)
    if args.sweep:
        result = run_quality_sweep(args.records, seed=args.seed)
    else:
        result = run_scale_observation(
            args.records,
            LshConfiguration(
                table_count=args.tables, candidate_pool_k=args.pool_k, seed=args.seed
            ),
            seed=args.seed,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
