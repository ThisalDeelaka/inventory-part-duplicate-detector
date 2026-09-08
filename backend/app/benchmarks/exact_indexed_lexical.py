"""GF-11C exact indexed lexical equivalence and work measurements."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor as _RealThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from app.benchmarks.character_retrieval_contract import _coverage
from app.benchmarks.contracts import stable_fingerprint
from app.benchmarks.group_first_scale import benchmark_configuration
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
from app.services.lexical_retrieval import (
    IndexedLexicalResult,
    retrieve_exact_indexed_lexical_neighbors,
)


def _inputs(records, seed):
    corpus = generate_scale_corpus(records, seed=seed)
    texts = [semantic_retrieval_text(row) for row in corpus.records.to_dict("records")]
    matrix = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1
    ).fit_transform(texts)
    refs = np.asarray(
        [canonical_record_ref_key(1, index) for index in range(records)], dtype=object
    )
    return corpus, matrix, refs


def _semantic_directed(directed, refs):
    return tuple(sorted(
        (refs[source], refs[target], score)
        for source, neighbors in directed.items()
        for target, score in neighbors
    ))


def _pair_positions(directed):
    return {
        tuple(sorted((source, target)))
        for source, neighbors in directed.items()
        for target, _score in neighbors
    }


def run_indexed_equivalence(records, *, seed=1101, permutations=True):
    corpus, matrix, refs = _inputs(records, seed)
    started = time.perf_counter()
    reference = _deterministic_lexical_directed_neighbors(matrix, 5, refs)
    reference_ms = (time.perf_counter() - started) * 1000
    indexed = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
    reference_signature = _semantic_directed(reference, refs)
    indexed_signature = _semantic_directed(indexed.directed_neighbors, refs)
    reference_pairs = _directed_neighbors_to_pairs(reference, refs)
    indexed_pairs = _directed_neighbors_to_pairs(indexed.directed_neighbors, refs)
    differences = {"original": len(set(reference_signature) ^ set(indexed_signature))}
    if permutations:
        orders = {
            "reversed": np.arange(records)[::-1],
            **{f"shuffle_{value}": np.random.default_rng(value).permutation(records) for value in (7, 19, 1101)},
        }
        for name, order in orders.items():
            candidate_refs = refs[order]
            candidate = retrieve_exact_indexed_lexical_neighbors(
                matrix[order], candidate_refs, 5
            ).directed_neighbors
            differences[name] = len(
                set(indexed_signature) ^ set(_semantic_directed(candidate, candidate_refs))
            )
    reference_position_pairs = _pair_positions(reference)
    indexed_position_pairs = _pair_positions(indexed.directed_neighbors)
    return {
        "records": records,
        "reference_time_ms": round(reference_ms, 3),
        "indexed_metrics": asdict(indexed.metrics),
        "directed_semantic_difference": differences["original"],
        "pair_semantic_equal": reference_pairs == indexed_pairs,
        "reference_lexical_fingerprint": stable_fingerprint(reference_pairs),
        "indexed_lexical_fingerprint": stable_fingerprint(indexed_pairs),
        "permutation_differences": differences,
        "reference_coverage": _coverage(reference_position_pairs, corpus.truth),
        "indexed_coverage": _coverage(indexed_position_pairs, corpus.truth),
    }


def run_indexed_only(records, *, seed=1101):
    corpus, matrix, refs = _inputs(records, seed)
    del corpus
    indexed = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
    pairs = _directed_neighbors_to_pairs(indexed.directed_neighbors, refs)
    return {
        "records": records,
        "indexed_metrics": asdict(indexed.metrics),
        "indexed_lexical_fingerprint": stable_fingerprint(pairs),
    }


def run_hybrid_equivalence(records, *, seed=1101):
    from app.services import hybrid_retrieval
    corpus = generate_scale_corpus(records, seed=seed)
    data = corpus.records.copy()
    refs = tuple(canonical_record_ref_key(1, index) for index in range(records))
    data[CANONICAL_RECORD_REF_FIELD] = refs
    original = hybrid_retrieval.retrieve_production_lexical_neighbors

    def reference_adapter(matrix, canonical_refs, top_k):
        measured = original(matrix, canonical_refs, top_k)
        return IndexedLexicalResult(
            directed_neighbors=_deterministic_lexical_directed_neighbors(
                matrix, top_k, canonical_refs
            ),
            metrics=measured.metrics,
        )

    def run(reference):
        hybrid_retrieval.retrieve_production_lexical_neighbors = (
            reference_adapter if reference else original
        )
        return HybridCandidateRetriever(
            benchmark_configuration(), cache=MemoryEmbeddingVectorCache()
        ).retrieve(data, "DISCOVERY")

    try:
        reference_result, indexed_result = run(True), run(False)
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original

    def signature(result):
        return tuple(
            (tuple(sorted((refs[item.left_record_id], refs[item.right_record_id]))),
             item.retrieval_priority, item.retrieval_rank, item.retrieval_tier.value,
             item.evidence.retrieval_sources, item.evidence.channel_ranks,
             item.evidence.channel_scores, item.evidence.reciprocal_sources)
            for item in result.candidates
        )

    reference_signature = signature(reference_result)
    indexed_signature = signature(indexed_result)
    reference_pairs = {
        tuple(sorted((item.left_record_id, item.right_record_id)))
        for item in reference_result.candidates
    }
    indexed_pairs = {
        tuple(sorted((item.left_record_id, item.right_record_id)))
        for item in indexed_result.candidates
    }
    return {
        "records": records,
        "reference_count": len(reference_result.candidates),
        "indexed_count": len(indexed_result.candidates),
        "semantic_equal": reference_signature == indexed_signature,
        "reference_fingerprint": stable_fingerprint(reference_signature),
        "indexed_fingerprint": stable_fingerprint(indexed_signature),
        "reference_coverage": _coverage(reference_pairs, corpus.truth),
        "indexed_coverage": _coverage(indexed_pairs, corpus.truth),
        "provider_calls": reference_result.metrics.provider_request_count + indexed_result.metrics.provider_request_count,
    }


class _QueryProgressCollector:
    """Benchmark-only observation around production deterministic query batches."""

    def __init__(self, *, records, matrix, checkpoint_path, checkpoint_interval):
        csr = matrix.tocsr(copy=False)
        csc = csr.tocsc(copy=False)
        posting_sizes = np.diff(csc.indptr).astype(np.int64, copy=False)
        binary = csr.copy()
        binary.data = np.ones(binary.nnz, dtype=np.int64)
        self.posting_visits_by_anchor = np.asarray(
            binary @ posting_sizes, dtype=np.int64
        ).reshape(-1)
        self.raw_candidate_visits_by_anchor = np.asarray(
            binary @ np.maximum(posting_sizes - 1, 0), dtype=np.int64
        ).reshape(-1)
        self.records = records
        self.checkpoint_path = Path(checkpoint_path) if checkpoint_path else None
        self.checkpoint_interval = checkpoint_interval
        self.call_started = time.perf_counter()
        self.query_started = None
        self.anchors_completed = 0
        self.posting_visits = 0
        self.candidate_union_raw_count = 0
        self.exact_score_evaluations = 0
        self.union_sizes = []
        self.worker_batch_seconds = 0.0
        self.top_k_seconds = 0.0
        self.batch_details = {}
        self.thread_local = threading.local()
        self.lock = threading.Lock()

    def begin_query(self):
        if self.query_started is None:
            self.query_started = time.perf_counter()
            self._write_checkpoint()

    def record_top_k(self, candidate_count, elapsed):
        batch_start = getattr(self.thread_local, "batch_start", None)
        if batch_start is None:
            return
        with self.lock:
            detail = self.batch_details.setdefault(
                batch_start, {"union_sizes": [], "top_k_seconds": 0.0}
            )
            detail["union_sizes"].append(int(candidate_count))
            detail["top_k_seconds"] += elapsed

    def complete_batch(self, start, evaluations, batch_wall_seconds):
        end = min(start + 64, self.records)
        detail = self.batch_details.pop(start)
        self.anchors_completed += end - start
        self.posting_visits += int(self.posting_visits_by_anchor[start:end].sum())
        self.candidate_union_raw_count += int(
            self.raw_candidate_visits_by_anchor[start:end].sum()
        )
        self.exact_score_evaluations += int(evaluations)
        self.union_sizes.extend(detail["union_sizes"])
        self.worker_batch_seconds += batch_wall_seconds
        self.top_k_seconds += detail["top_k_seconds"]
        if (
            self.anchors_completed == self.records
            or self.anchors_completed % self.checkpoint_interval == 0
        ):
            self._write_checkpoint()

    def payload(self):
        query_elapsed = (
            time.perf_counter() - self.query_started if self.query_started else 0.0
        )
        denominator = self.anchors_completed * max(0, self.records - 1)
        values = np.asarray(self.union_sizes, dtype=np.int64)

        def percentile(value):
            return int(np.percentile(values, value, method="higher")) if len(values) else 0

        return {
            "active_lexical_sub_stage": (
                "COMPLETED" if self.anchors_completed == self.records else "INDEXED_QUERY_SCORING"
            ),
            "anchors_total": self.records,
            "anchors_completed": self.anchors_completed,
            "batch_size": 64,
            "checkpoint_interval_anchors": self.checkpoint_interval,
            "elapsed_query_seconds": round(query_elapsed, 6),
            "index_build_seconds": round(
                (self.query_started or time.perf_counter()) - self.call_started, 6
            ),
            "posting_visits": self.posting_visits,
            "candidate_union_raw_count": self.candidate_union_raw_count,
            "candidate_union_unique_count": self.exact_score_evaluations,
            "exact_score_evaluations": self.exact_score_evaluations,
            "candidate_union_p50": percentile(50),
            "candidate_union_p95": percentile(95),
            "candidate_union_p99": percentile(99),
            "max_anchor_candidate_union": int(values.max()) if len(values) else 0,
            "candidate_density": (
                round(self.exact_score_evaluations / denominator, 9) if denominator else 0.0
            ),
            "exact_scores_per_second": (
                round(self.exact_score_evaluations / query_elapsed, 3) if query_elapsed else 0.0
            ),
            "anchors_per_second": (
                round(self.anchors_completed / query_elapsed, 6) if query_elapsed else 0.0
            ),
            "worker_batch_seconds_sum": round(self.worker_batch_seconds, 6),
            "sparse_enumeration_and_scoring_worker_seconds": round(
                max(0.0, self.worker_batch_seconds - self.top_k_seconds), 6
            ),
            "top_k_worker_seconds": round(self.top_k_seconds, 6),
        }

    def _write_checkpoint(self):
        if self.checkpoint_path is None:
            return
        payload = self.payload()
        temporary = self.checkpoint_path.with_suffix(self.checkpoint_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        temporary.replace(self.checkpoint_path)


def run_query_probe(
    records, *, seed=1101, instrumentation_enabled=True, checkpoint_path=None,
    checkpoint_interval=256,
):
    """Run the exact production lexical function with benchmark-only observation."""
    from app.services import lexical_retrieval

    corpus, matrix, refs = _inputs(records, seed)
    del corpus
    collector = None
    original_executor = lexical_retrieval.ThreadPoolExecutor
    original_top_k = lexical_retrieval._canonical_top_k_positions
    started = time.perf_counter()
    if instrumentation_enabled:
        collector = _QueryProgressCollector(
            records=records, matrix=matrix, checkpoint_path=checkpoint_path,
            checkpoint_interval=checkpoint_interval,
        )

        class InstrumentedExecutor:
            def __init__(self, *, max_workers):
                self.executor = _RealThreadPoolExecutor(max_workers=max_workers)

            def __enter__(self):
                self.executor.__enter__()
                collector.begin_query()
                return self

            def __exit__(self, *arguments):
                return self.executor.__exit__(*arguments)

            def map(self, function, starts):
                def measured(start):
                    collector.thread_local.batch_start = start
                    batch_started = time.perf_counter()
                    value = function(start)
                    return start, value, time.perf_counter() - batch_started

                for start, value, elapsed in self.executor.map(measured, starts):
                    rows, evaluations, _maximum = value
                    collector.complete_batch(start, evaluations, elapsed)
                    yield rows, evaluations, _maximum

        def measured_top_k(scores, targets, ref_values, top_k):
            selection_started = time.perf_counter()
            selected = original_top_k(scores, targets, ref_values, top_k)
            collector.record_top_k(
                len(scores), time.perf_counter() - selection_started
            )
            return selected

        lexical_retrieval.ThreadPoolExecutor = InstrumentedExecutor
        lexical_retrieval._canonical_top_k_positions = measured_top_k
    try:
        result = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 5)
    finally:
        lexical_retrieval.ThreadPoolExecutor = original_executor
        lexical_retrieval._canonical_top_k_positions = original_top_k
    pairs = _directed_neighbors_to_pairs(result.directed_neighbors, refs)
    return {
        "status": "COMPLETED",
        "records": records,
        "instrumentation_enabled": instrumentation_enabled,
        "total_wall_seconds": round(time.perf_counter() - started, 6),
        "lexical_fingerprint": stable_fingerprint(pairs),
        "provider_request_count": 0,
        "production_metrics": asdict(result.metrics),
        "progress": collector.payload() if collector else None,
    }


def query_probe_timeout_result(checkpoint, *, records, timeout_seconds, wall_seconds):
    progress = dict(checkpoint or {})
    if progress.get("active_lexical_sub_stage") == "COMPLETED":
        progress["active_lexical_sub_stage"] = "TIMEOUT_AFTER_LAST_CHECKPOINT"
    return {
        "status": "TIMED_OUT",
        "records": records,
        "timeout_seconds": timeout_seconds,
        "bounded_wall_seconds": round(wall_seconds, 6),
        "provider_request_count": 0,
        "last_completed_checkpoint": progress,
    }


def _query_probe_worker(queue, values):
    try:
        queue.put(run_query_probe(**values))
    except BaseException as exc:
        queue.put({
            "status": "FAILED",
            "safe_failure_category": type(exc).__name__,
            "provider_request_count": 0,
        })


def run_bounded_query_probe(*, records, seed=1101, timeout_seconds=300.0):
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="gf11c-query-probe-") as directory:
        checkpoint = Path(directory) / "checkpoint.json"
        values = {
            "records": records,
            "seed": seed,
            "instrumentation_enabled": True,
            "checkpoint_path": checkpoint,
            "checkpoint_interval": 256,
        }
        queue = context.Queue(maxsize=1)
        process = context.Process(target=_query_probe_worker, args=(queue, values))
        started = time.perf_counter()
        process.start()
        process.join(timeout_seconds)
        wall_seconds = time.perf_counter() - started
        if process.is_alive():
            process.terminate()
            process.join()
            saved = (
                json.loads(checkpoint.read_text(encoding="utf-8"))
                if checkpoint.exists() else {}
            )
            return query_probe_timeout_result(
                saved, records=records, timeout_seconds=timeout_seconds,
                wall_seconds=wall_seconds,
            )
        if not queue.empty():
            return queue.get()
        return {
            "status": "FAILED",
            "safe_failure_category": "QUERY_PROBE_PROCESS_EXITED_WITHOUT_RESULT",
            "provider_request_count": 0,
        }


def run_component_sample(records, *, seed=1101, sample_anchors=16):
    """Separate structural posting, scoring, and top-k costs on fixed anchors."""
    from app.services.lexical_retrieval import _canonical_top_k_positions

    corpus, matrix, refs = _inputs(records, seed)
    del corpus
    build_started = time.perf_counter()
    csr = normalize(matrix.tocsr(copy=True), copy=False)
    csc = csr.tocsc(copy=False)
    index_build_seconds = time.perf_counter() - build_started
    anchors = np.linspace(
        0, records - 1, num=min(sample_anchors, records), dtype=np.int64
    )
    enumeration_seconds = 0.0
    scoring_seconds = 0.0
    top_k_seconds = 0.0
    posting_visits = 0
    candidate_union_raw_count = 0
    exact_score_evaluations = 0
    union_sizes = []
    for source in anchors:
        features = csr.indices[csr.indptr[source]:csr.indptr[source + 1]]
        posting_arrays = tuple(
            csc.indices[csc.indptr[feature]:csc.indptr[feature + 1]]
            for feature in features
        )
        enum_started = time.perf_counter()
        raw = np.concatenate(posting_arrays) if posting_arrays else np.empty(0, dtype=np.int32)
        posting_visits += len(raw)
        raw = raw[raw != source]
        candidate_union_raw_count += len(raw)
        targets = np.unique(raw)
        enumeration_seconds += time.perf_counter() - enum_started

        score_started = time.perf_counter()
        scores = np.asarray(
            (csr[targets] @ csr[int(source)].T).toarray(), dtype=np.float64
        ).reshape(-1)
        scoring_seconds += time.perf_counter() - score_started
        exact_score_evaluations += len(targets)
        union_sizes.append(len(targets))

        top_k_started = time.perf_counter()
        _canonical_top_k_positions(scores, targets, refs, 5)
        top_k_seconds += time.perf_counter() - top_k_started
    timed_total = enumeration_seconds + scoring_seconds + top_k_seconds
    return {
        "records": records,
        "sample_anchors": len(anchors),
        "anchor_selection": "evenly-spaced-canonical-position",
        "index_build_seconds": round(index_build_seconds, 6),
        "posting_enumeration_and_union_seconds": round(enumeration_seconds, 6),
        "exact_sparse_scoring_seconds": round(scoring_seconds, 6),
        "top_k_selection_seconds": round(top_k_seconds, 6),
        "timed_component_total_seconds": round(timed_total, 6),
        "posting_visits": posting_visits,
        "candidate_union_raw_count": candidate_union_raw_count,
        "exact_score_evaluations": exact_score_evaluations,
        "candidate_union_p50": int(np.percentile(union_sizes, 50, method="higher")),
        "candidate_union_p95": int(np.percentile(union_sizes, 95, method="higher")),
        "candidate_union_p99": int(np.percentile(union_sizes, 99, method="higher")),
        "max_anchor_candidate_union": max(union_sizes),
        "provider_request_count": 0,
    }


def run_discovery_equivalence(records, *, seed=1101):
    from pathlib import Path
    from app.benchmarks.residual_discovery_profile import run_residual_profile
    from app.services import hybrid_retrieval
    original = hybrid_retrieval.retrieve_production_lexical_neighbors

    def reference_adapter(matrix, canonical_refs, top_k):
        measured = original(matrix, canonical_refs, top_k)
        return IndexedLexicalResult(
            directed_neighbors=_deterministic_lexical_directed_neighbors(
                matrix, top_k, canonical_refs
            ),
            metrics=measured.metrics,
        )

    results = {}
    try:
        with tempfile.TemporaryDirectory(prefix="gf11c-discovery-equivalence-") as directory:
            for name, reference in (("REFERENCE", True), ("INDEXED", False)):
                hybrid_retrieval.retrieve_production_lexical_neighbors = (
                    reference_adapter if reference else original
                )
                results[name] = run_residual_profile(
                    records=records, seed=seed,
                    db_path=Path(directory) / f"{name.casefold()}.db",
                    python_profile_enabled=False,
                )
    finally:
        hybrid_retrieval.retrieve_production_lexical_neighbors = original
    return {
        name: {
            "status": value["status"],
            "discovery_total_seconds": value["discovery_total_seconds"],
            "proposal_count": value["proposal_row_count"],
            "neighborhood_count": value["neighborhood_row_count"],
            "proposal_fingerprint": value["proposal_semantic_fingerprint"],
            "neighborhood_fingerprint": value["neighborhood_semantic_fingerprint"],
            "provider_request_count": value["provider_request_count"],
        }
        for name, value in results.items()
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=1101)
    parser.add_argument("--hybrid", action="store_true")
    parser.add_argument("--indexed-only", action="store_true")
    parser.add_argument("--discovery", action="store_true")
    parser.add_argument("--query-probe", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--instrumentation-disabled", action="store_true")
    parser.add_argument("--component-sample", action="store_true")
    parser.add_argument("--sample-anchors", type=int, default=16)
    parser.add_argument("--no-permutations", action="store_true")
    args = parser.parse_args(argv)
    result = (
        run_component_sample(
            args.records, seed=args.seed, sample_anchors=args.sample_anchors
        ) if args.component_sample else
        run_bounded_query_probe(
            records=args.records, seed=args.seed, timeout_seconds=args.timeout_seconds
        ) if args.query_probe and not args.instrumentation_disabled else
        run_query_probe(
            args.records, seed=args.seed, instrumentation_enabled=False
        ) if args.query_probe else
        run_discovery_equivalence(args.records, seed=args.seed)
        if args.discovery else run_indexed_only(args.records, seed=args.seed)
        if args.indexed_only else run_hybrid_equivalence(args.records, seed=args.seed)
        if args.hybrid else run_indexed_equivalence(
            args.records, seed=args.seed, permutations=not args.no_permutations
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    passed = result.get("status") in {"COMPLETED", "TIMED_OUT"} or result.get(
        "semantic_equal", result.get("directed_semantic_difference", 0) == 0
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
