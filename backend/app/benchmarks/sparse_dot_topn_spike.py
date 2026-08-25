"""Benchmark-only GF-11C-D1 sparse_dot_topn exact top-N spike."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import sys
import time
import types
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import scipy
import sklearn
from sklearn.preprocessing import normalize

from app.benchmarks.contracts import stable_fingerprint
from app.benchmarks.exact_indexed_lexical import _inputs
from app.services.hybrid_retrieval import _directed_neighbors_to_pairs
from app.services.lexical_retrieval import (
    IndexedLexicalResult,
    LexicalRetrievalWorkMetrics,
    _canonical_top_k_positions,
    lexical_retrieval_contract_fingerprint,
    retrieve_exact_indexed_lexical_neighbors,
)


SPIKE_VERSION = "gf11c-d1-sparse-dot-topn-1"
PACKAGE_TARGET_ENV = "GF11C_D1_PACKAGE_TARGET"


@dataclass(frozen=True)
class SparseDotTopNMetrics:
    package_version: str
    package_path: str
    algorithm_version: str
    n_threads: int
    native_top_n: int
    topn_seconds: float
    boundary_recovery_seconds: float
    canonical_rerank_seconds: float
    total_seconds: float
    output_nnz: int
    anchors_with_boundary_ties: int
    maximum_boundary_tie_size: int
    supplemental_exact_evaluations: int
    native_result_bytes: int
    configuration_fingerprint: str
    provider_request_count: int = 0


@dataclass(frozen=True)
class SparseDotTopNResult:
    native_directed_neighbors: dict[int, tuple[tuple[int, float], ...]]
    directed_neighbors: dict[int, tuple[tuple[int, float], ...]]
    metrics: SparseDotTopNMetrics


def _load_dependency(package_target: str | Path | None = None):
    target = Path(package_target or os.environ.get(PACKAGE_TARGET_ENV, "")).resolve()
    if not str(package_target or os.environ.get(PACKAGE_TARGET_ENV, "")).strip():
        raise RuntimeError(f"{PACKAGE_TARGET_ENV} must identify the disposable package target")
    repository = Path(__file__).resolve().parents[3]
    if target == repository or repository in target.parents:
        raise RuntimeError("dependency target must be outside the repository")
    if not target.is_dir():
        raise RuntimeError("disposable dependency target does not exist")
    target_text = str(target)
    if target_text not in sys.path:
        sys.path.insert(0, target_text)
    try:
        importlib.import_module("psutil")
    except ModuleNotFoundError:
        shim = types.ModuleType("psutil")
        shim.cpu_count = lambda logical=True: os.cpu_count() or 1
        sys.modules["psutil"] = shim
    package = importlib.import_module("sparse_dot_topn")
    package_path = Path(package.__file__).resolve()
    if target != package_path and target not in package_path.parents:
        raise RuntimeError("sparse_dot_topn was not loaded from the disposable target")
    return package, importlib.metadata.version("sparse-dot-topn"), package_path


def dependency_metadata(package_target: str | Path | None = None) -> dict:
    package, version, package_path = _load_dependency(package_target)
    return {
        "package": "sparse-dot-topn",
        "version": version,
        "package_path": str(package_path),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "scikit_learn": sklearn.__version__,
        "openmp_available": bool(package._has_openmp_support),
        "license": "Apache-2.0",
        "provider_request_count": 0,
    }


def _stable_inputs(matrix, refs):
    refs = tuple(str(value or "").strip() for value in refs)
    if len(refs) != matrix.shape[0] or any(not value for value in refs):
        raise ValueError("one nonblank canonical reference is required per row")
    if len(set(refs)) != len(refs):
        raise ValueError("canonical references must be unique")
    order = np.asarray(sorted(range(len(refs)), key=lambda item: refs[item]), dtype=np.int64)
    return (
        normalize(matrix.tocsr(copy=True)[order], copy=False),
        np.asarray([refs[item] for item in order], dtype=object),
        order,
    )


def _select(scores, targets, refs, top_k):
    order = _canonical_top_k_positions(scores, targets, refs, top_k)
    return tuple((int(targets[item]), float(scores[item])) for item in order)


def retrieve_sparse_dot_topn_exact(
    matrix, refs, top_k: int, *, n_threads: int = 1,
    package_target: str | Path | None = None, progress_callback=None,
) -> SparseDotTopNResult:
    if top_k < 1 or n_threads < 1:
        raise ValueError("top_k and n_threads must be positive")
    package, package_version, package_path = _load_dependency(package_target)
    started = time.perf_counter()
    stable, stable_refs, original_positions = _stable_inputs(matrix, refs)
    count = stable.shape[0]
    native_top_n = min(count, top_k + 2)

    topn_started = time.perf_counter()
    product = package.sp_matmul_topn(
        stable, stable.T, top_n=native_top_n, threshold=0.0,
        sort=True, n_threads=n_threads,
    ).tocsr()
    topn_seconds = time.perf_counter() - topn_started
    if progress_callback:
        progress_callback({
            "stage": "NATIVE_TOPN_COMPLETED", "topn_seconds": round(topn_seconds, 6),
            "native_result_nnz": int(product.nnz),
        })

    native_stable = {}
    corrected_stable = {}
    ambiguous = []
    canonical_seconds = 0.0
    for source in range(count):
        left, right = product.indptr[source:source + 2]
        targets = product.indices[left:right]
        scores = product.data[left:right]
        keep = (targets != source) & (scores > 0)
        targets, scores = targets[keep], scores[keep]
        rerank_started = time.perf_counter()
        native_stable[source] = _select(scores, targets, stable_refs, top_k)
        canonical_seconds += time.perf_counter() - rerank_started
        ranked_scores = np.sort(scores)[::-1]
        if len(ranked_scores) > top_k and ranked_scores[top_k - 1] == ranked_scores[top_k]:
            ambiguous.append(source)
        else:
            corrected_stable[source] = native_stable[source]
    if progress_callback:
        progress_callback({
            "stage": "BOUNDARY_DETECTION_COMPLETED",
            "anchors_with_boundary_ties": len(ambiguous),
        })

    recovery_started = time.perf_counter()
    supplemental_rerank_seconds = 0.0
    maximum_tie = 0
    supplemental_evaluations = 0
    transpose = stable.T
    for batch_start in range(0, len(ambiguous), 64):
        sources = ambiguous[batch_start:batch_start + 64]
        similarities = (stable[sources] @ transpose).tocsr()
        similarities.eliminate_zeros()
        for offset, source in enumerate(sources):
            left, right = similarities.indptr[offset:offset + 2]
            targets, scores = similarities.indices[left:right], similarities.data[left:right]
            keep = (targets != source) & (scores > 0)
            targets, scores = targets[keep], scores[keep]
            supplemental_evaluations += len(targets)
            rerank_started = time.perf_counter()
            corrected_stable[source] = _select(scores, targets, stable_refs, top_k)
            rerank_elapsed = time.perf_counter() - rerank_started
            canonical_seconds += rerank_elapsed
            supplemental_rerank_seconds += rerank_elapsed
            if len(scores) >= top_k:
                boundary = corrected_stable[source][-1][1]
                maximum_tie = max(maximum_tie, int(np.count_nonzero(scores == boundary)))
        if progress_callback and (
            batch_start == 0 or batch_start + 64 >= len(ambiguous)
            or (batch_start + 64) % 4096 == 0
        ):
            progress_callback({
                "stage": "BOUNDARY_RECOVERY_RUNNING",
                "anchors_completed": min(batch_start + 64, len(ambiguous)),
                "anchors_total": len(ambiguous),
                "supplemental_exact_evaluations": supplemental_evaluations,
                "boundary_recovery_seconds": round(time.perf_counter() - recovery_started, 6),
            })
    recovery_seconds = time.perf_counter() - recovery_started
    boundary_query_seconds = max(0.0, recovery_seconds - supplemental_rerank_seconds)

    def restore(directed):
        return {
            int(original_positions[source]): tuple(
                (int(original_positions[target]), score) for target, score in neighbors
            )
            for source, neighbors in directed.items()
        }

    payload = {
        "algorithm_version": SPIKE_VERSION,
        "package": "sparse-dot-topn",
        "package_version": package_version,
        "representation": "tfidf-char-wb-3-5-l2-float64",
        "native_top_n": native_top_n,
        "threshold": "strict-positive-0.0",
        "self_exclusion": "native-k-plus-two-then-remove-before-final-top-k",
        "boundary_detection": "kth-equals-k-plus-one-exact-score",
        "boundary_recovery": "exact-sparse-64-anchor-batches-for-ambiguous-anchors",
        "ordering": "score-desc-record-ref-key-asc",
        "top_k": top_k,
        "n_threads": n_threads,
    }
    native_bytes = product.data.nbytes + product.indices.nbytes + product.indptr.nbytes
    return SparseDotTopNResult(
        native_directed_neighbors=restore(native_stable),
        directed_neighbors=restore(corrected_stable),
        metrics=SparseDotTopNMetrics(
            package_version=package_version,
            package_path=str(package_path),
            algorithm_version=SPIKE_VERSION,
            n_threads=n_threads,
            native_top_n=native_top_n,
            topn_seconds=round(topn_seconds, 6),
            boundary_recovery_seconds=round(boundary_query_seconds, 6),
            canonical_rerank_seconds=round(canonical_seconds, 6),
            total_seconds=round(time.perf_counter() - started, 6),
            output_nnz=sum(len(row) for row in corrected_stable.values()),
            anchors_with_boundary_ties=len(ambiguous),
            maximum_boundary_tie_size=maximum_tie,
            supplemental_exact_evaluations=supplemental_evaluations,
            native_result_bytes=int(native_bytes),
            configuration_fingerprint=stable_fingerprint(payload),
        ),
    )


def _mismatch_counts(expected, actual):
    membership = 0
    unequal = 0
    for source, expected_rows in expected.items():
        actual_rows = actual[source]
        for position in range(max(len(expected_rows), len(actual_rows))):
            expected_item = expected_rows[position] if position < len(expected_rows) else None
            actual_item = actual_rows[position] if position < len(actual_rows) else None
            if expected_item != actual_item:
                membership += 1
                if expected_item is None or actual_item is None or expected_item[1] != actual_item[1]:
                    unequal += 1
    return membership, unequal


def evaluate(records: int, *, seed: int = 1101, n_threads: int = 1,
             package_target: str | Path | None = None, include_reference: bool = True,
             progress_callback=None):
    wall_started = time.perf_counter()
    input_started = time.perf_counter()
    _corpus, matrix, refs = _inputs(records, seed)
    input_seconds = time.perf_counter() - input_started
    reference = None
    reference_seconds = None
    if include_reference:
        reference_started = time.perf_counter()
        reference = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
        reference_seconds = time.perf_counter() - reference_started
    candidate = retrieve_sparse_dot_topn_exact(
        matrix, refs, 5, n_threads=n_threads, package_target=package_target,
        progress_callback=progress_callback,
    )
    result = {
        "status": "COMPLETED",
        "records": records,
        "matrix_shape": list(matrix.shape),
        "matrix_nnz": int(matrix.nnz),
        "tfidf_input_seconds": round(input_seconds, 6),
        "reference_seconds": round(reference_seconds, 6) if reference_seconds is not None else None,
        "metrics": asdict(candidate.metrics),
        "native_fingerprint": stable_fingerprint(
            _directed_neighbors_to_pairs(candidate.native_directed_neighbors, refs)
        ),
        "canonical_fingerprint": stable_fingerprint(
            _directed_neighbors_to_pairs(candidate.directed_neighbors, refs)
        ),
        "provider_request_count": 0,
    }
    if reference is not None:
        native_mismatches, native_unequal = _mismatch_counts(
            reference.directed_neighbors, candidate.native_directed_neighbors
        )
        corrected_mismatches, corrected_unequal = _mismatch_counts(
            reference.directed_neighbors, candidate.directed_neighbors
        )
        result.update({
            "reference_fingerprint": stable_fingerprint(
                _directed_neighbors_to_pairs(reference.directed_neighbors, refs)
            ),
            "native_mismatches": native_mismatches,
            "native_unequal_score_mismatches": native_unequal,
            "canonical_corrected_mismatches": corrected_mismatches,
            "canonical_unequal_score_mismatches": corrected_unequal,
            "exact_equal": reference.directed_neighbors == candidate.directed_neighbors,
        })
    result["wall_seconds"] = round(time.perf_counter() - wall_started, 6)
    return result


def determinism(records: int, *, n_threads: int, seed: int = 1101,
                package_target: str | Path | None = None):
    _corpus, matrix, refs = _inputs(records, seed)
    expected = retrieve_sparse_dot_topn_exact(
        matrix, refs, 5, n_threads=n_threads, package_target=package_target
    )
    expected_rows = tuple(sorted(
        (refs[source], refs[target], score)
        for source, neighbors in expected.directed_neighbors.items()
        for target, score in neighbors
    ))
    results = {}
    orders = {
        "repeat": np.arange(records),
        "reverse": np.arange(records)[::-1],
        **{f"shuffle_{value}": np.random.default_rng(value).permutation(records)
           for value in (7, 19, 1101)},
    }
    refs_array = np.asarray(refs, dtype=object)
    for name, order in orders.items():
        current_refs = refs_array[order]
        current = retrieve_sparse_dot_topn_exact(
            matrix[order], current_refs, 5, n_threads=n_threads,
            package_target=package_target,
        )
        rows = tuple(sorted(
            (current_refs[source], current_refs[target], score)
            for source, neighbors in current.directed_neighbors.items()
            for target, score in neighbors
        ))
        results[name] = rows == expected_rows
    return results


def _production_adapter(matrix, refs, top_k, *, n_threads, package_target):
    result = retrieve_sparse_dot_topn_exact(
        matrix, refs, top_k, n_threads=n_threads, package_target=package_target
    )
    count = matrix.shape[0]
    metrics = result.metrics
    return IndexedLexicalResult(
        result.directed_neighbors,
        LexicalRetrievalWorkMetrics(
            strategy="EXACT_INDEXED_LEXICAL",
            contract_fingerprint=lexical_retrieval_contract_fingerprint(top_k),
            feature_count=matrix.shape[1], posting_entry_count=matrix.nnz,
            posting_size_p50=0, posting_size_p95=0, posting_size_p99=0,
            max_posting_size=0,
            candidate_union_enumerations=metrics.supplemental_exact_evaluations,
            unique_directed_candidates=metrics.output_nnz,
            exact_score_evaluations=metrics.supplemental_exact_evaluations,
            theoretical_brute_directed_comparisons=count * max(0, count - 1),
            zero_overlap_comparisons_avoided=max(
                0, count * max(0, count - 1) - metrics.supplemental_exact_evaluations
            ),
            max_anchor_candidate_union=metrics.maximum_boundary_tie_size,
            index_build_time_ms=0,
            query_scoring_time_ms=metrics.total_seconds * 1000,
        ),
    )


def run_hybrid_comparison(records=500, *, seed=1101, n_threads=1,
                          package_target=None):
    from app.benchmarks.group_first_scale import benchmark_configuration
    from app.benchmarks.group_first_scale_generator import generate_scale_corpus
    from app.services import hybrid_retrieval
    from app.services.canonical_record_service import canonical_record_ref_key
    from app.services.hybrid_retrieval import (
        CANONICAL_RECORD_REF_FIELD, HybridCandidateRetriever, MemoryEmbeddingVectorCache,
    )

    corpus = generate_scale_corpus(records, seed=seed)
    data = corpus.records.copy()
    refs = tuple(canonical_record_ref_key(1, index) for index in range(records))
    data[CANONICAL_RECORD_REF_FIELD] = refs
    original = hybrid_retrieval.retrieve_production_lexical_neighbors

    def execute(function):
        hybrid_retrieval.retrieve_production_lexical_neighbors = function
        return HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")

    def adapter(matrix, canonical_refs, top_k):
        return _production_adapter(
            matrix, canonical_refs, top_k, n_threads=n_threads,
            package_target=package_target,
        )

    try:
        exact, dependency = execute(original), execute(adapter)
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

    return {
        "exact_count": len(exact.candidates),
        "dependency_count": len(dependency.candidates),
        "exact_fingerprint": stable_fingerprint(signature(exact)),
        "dependency_fingerprint": stable_fingerprint(signature(dependency)),
        "exact_equal": signature(exact) == signature(dependency),
        "provider_request_count": (
            exact.metrics.provider_request_count + dependency.metrics.provider_request_count
        ),
    }


def run_discovery_comparison(records=500, *, seed=1101, n_threads=1,
                             package_target=None):
    from app.benchmarks.residual_discovery_profile import run_residual_profile
    from app.services import hybrid_retrieval

    original = hybrid_retrieval.retrieve_production_lexical_neighbors

    def adapter(matrix, canonical_refs, top_k):
        return _production_adapter(
            matrix, canonical_refs, top_k, n_threads=n_threads,
            package_target=package_target,
        )

    results = {}
    try:
        with tempfile.TemporaryDirectory(prefix="gf11c-d1-discovery-") as directory:
            for name, function in (("REFERENCE", original), ("DEPENDENCY", adapter)):
                hybrid_retrieval.retrieve_production_lexical_neighbors = function
                value = run_residual_profile(
                    records=records, seed=seed,
                    db_path=Path(directory) / f"{name.casefold()}.sqlite",
                    python_profile_enabled=False,
                )
                results[name] = {
                    "status": value["status"],
                    "proposal_count": value["proposal_row_count"],
                    "neighborhood_count": value["neighborhood_row_count"],
                    "proposal_fingerprint": value["proposal_semantic_fingerprint"],
                    "neighborhood_fingerprint": value["neighborhood_semantic_fingerprint"],
                    "provider_request_count": value["provider_request_count"],
                }
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
    results["exact_equal"] = (
        results["REFERENCE"]["proposal_fingerprint"]
        == results["DEPENDENCY"]["proposal_fingerprint"]
        and results["REFERENCE"]["neighborhood_fingerprint"]
        == results["DEPENDENCY"]["neighborhood_fingerprint"]
    )
    return results


def timeout_result(*, records: int, timeout_seconds: float, wall_seconds: float):
    return {
        "status": "TIMED_OUT",
        "safe_failure_category": "SPARSE_DOT_TOPN_SPIKE_TIMEOUT",
        "records": records,
        "timeout_seconds": timeout_seconds,
        "wall_seconds": wall_seconds,
        "provider_request_count": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--determinism", action="store_true")
    parser.add_argument("--metadata", action="store_true")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args(argv)
    result = (
        dependency_metadata() if args.metadata else
        determinism(args.records, n_threads=args.threads) if args.determinism else
        evaluate(
            args.records, n_threads=args.threads, include_reference=not args.isolated,
            progress_callback=(
                lambda value: print(json.dumps(value, sort_keys=True), flush=True)
                if args.progress else None
            ),
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
