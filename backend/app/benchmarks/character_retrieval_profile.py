"""GF-11D-CHAR-PRE benchmark-only character retrieval attribution.

This module mirrors the frozen production LSH loop solely to expose
non-overlapping timers and sanitized counters. Production retrieval imports no
code from this module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.preprocessing import normalize

from app.benchmarks.group_first_scale_generator import generate_scale_corpus
from app.services.canonical_record_service import canonical_record_ref_key
from app.services.character_retrieval import (
    PRODUCTION_LSH_CONFIGURATION,
    CharacterRetrievalError,
    CharacterRetrievalFailureCategory,
    _probe_masks,
    _validated_values,
    character_retrieval_contract_fingerprint,
    generate_lsh_hyperplanes,
    retrieve_lsh_directed_neighbors,
)
from app.services.hybrid_retrieval import (
    SklearnHashingEmbedder,
    _directed_neighbors_to_pairs,
    semantic_retrieval_text,
)


PROFILE_CONTRACT_VERSION = "gf11d-char-pre-profile-v1"
CANONICAL_SEED = 1101
FINAL_TOP_K = 5
CHECKPOINT_ANCHOR_BATCH = 256
TAXONOMY = (
    "VECTOR_PREPARATION",
    "LSH_SETUP",
    "SIGNATURE_COMPUTATION",
    "INDEX_BUILD",
    "PROBE_CODE_GENERATION",
    "BUCKET_LOOKUP",
    "BUCKET_MEMBER_ENUMERATION",
    "CANDIDATE_DEDUP_OR_ACCUMULATION",
    "CANDIDATE_POOL_SELECTION",
    "EXACT_RERANK",
    "DIRECTED_TOPK_FINALIZATION",
    "RECIPROCAL_PAIR_RECONSTRUCTION",
)


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _percentiles(values) -> dict:
    array = np.asarray(values, dtype=np.int64)
    if not len(array):
        return {"p50": 0, "p95": 0, "p99": 0, "max": 0}
    return {
        "p50": int(np.percentile(array, 50, method="nearest")),
        "p95": int(np.percentile(array, 95, method="nearest")),
        "p99": int(np.percentile(array, 99, method="nearest")),
        "max": int(array.max()),
    }


def _semantic_fingerprints(directed, refs) -> tuple[str, str, int, int]:
    directed_rows = tuple(sorted(
        (refs[source], refs[target], float(score).hex())
        for source, neighbors in directed.items()
        for target, score in neighbors
    ))
    pairs = _directed_neighbors_to_pairs(directed, refs)
    pair_rows = tuple(
        (refs[left], refs[right], float(score).hex(), reciprocal)
        for left, right, score, reciprocal in pairs
    )
    return (
        _fingerprint(directed_rows), _fingerprint(pair_rows),
        len(directed_rows), sum(bool(row[3]) for row in pairs),
    )


class _Telemetry:
    def __init__(self, checkpoint_path: Path | None):
        self.checkpoint_path = checkpoint_path
        self.started = time.perf_counter()
        self.elapsed = defaultdict(float)
        self.active_sub_stage = "VECTOR_PREPARATION"
        self.anchors_completed = 0
        self.counters = defaultdict(int)

    def measure(self, stage, operation):
        self.active_sub_stage = stage
        started = time.perf_counter()
        result = operation()
        self.elapsed[stage] += time.perf_counter() - started
        return result

    def checkpoint(self, *, status="RUNNING"):
        if self.checkpoint_path is None:
            return
        payload = {
            "contract_version": PROFILE_CONTRACT_VERSION,
            "status": status,
            "active_sub_stage": self.active_sub_stage,
            "anchors_completed": self.anchors_completed,
            "elapsed_char_seconds": round(time.perf_counter() - self.started, 6),
            "bucket_lookups": self.counters["bucket_lookups"],
            "bucket_members_visited": self.counters["bucket_members_visited"],
            "unique_candidates": self.counters["unique_candidates_before_pool"],
            "exact_reranks": self.counters["exact_rerank_evaluations"],
            "timing_partial_seconds": {
                key: round(self.elapsed[key], 6) for key in TAXONOMY
            },
        }
        temporary = self.checkpoint_path.with_suffix(
            self.checkpoint_path.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.checkpoint_path)


def run_uninstrumented(records: int, *, seed: int = CANONICAL_SEED) -> dict:
    # Corpus generation is benchmark setup, not character-vector work.
    corpus = generate_scale_corpus(records, seed=seed)
    rows = corpus.records.to_dict("records")
    started = time.perf_counter()
    texts = [semantic_retrieval_text(row) for row in rows]
    matrix = normalize(SklearnHashingEmbedder().encode(texts)).astype(np.float32)
    refs = tuple(canonical_record_ref_key(1, index) for index in range(records))
    result = retrieve_lsh_directed_neighbors(matrix, refs, FINAL_TOP_K)
    directed_fp, pair_fp, directed_count, reciprocal_count = (
        _semantic_fingerprints(result.directed_neighbors, refs)
    )
    return {
        "contract_version": PROFILE_CONTRACT_VERSION,
        "status": "COMPLETED",
        "instrumentation_enabled": False,
        "records": records,
        "seed": seed,
        "char_total_seconds": round(time.perf_counter() - started, 6),
        "directed_neighbor_fingerprint": directed_fp,
        "pair_fingerprint": pair_fp,
        "directed_neighbors": directed_count,
        "reciprocal_pairs": reciprocal_count,
        "exact_rerank_evaluations": result.metrics.exact_rerank_evaluations,
        "provider_calls": 0,
        "configured_database_accessed": False,
    }


def run_profile(
    records: int, *, seed: int = CANONICAL_SEED,
    checkpoint_path: str | Path | None = None,
) -> dict:
    configuration = PRODUCTION_LSH_CONFIGURATION
    configuration.validate(FINAL_TOP_K)
    checkpoint = Path(checkpoint_path).resolve() if checkpoint_path else None
    corpus = generate_scale_corpus(records, seed=seed)
    telemetry = _Telemetry(checkpoint)
    telemetry.checkpoint()

    def vector_preparation():
        rows = corpus.records.to_dict("records")
        texts = [semantic_retrieval_text(row) for row in rows]
        matrix = normalize(SklearnHashingEmbedder().encode(texts)).astype(np.float32)
        refs = tuple(canonical_record_ref_key(1, index) for index in range(records))
        return matrix, refs

    matrix, refs = telemetry.measure("VECTOR_PREPARATION", vector_preparation)
    telemetry.checkpoint()

    setup_started = time.perf_counter()
    values, refs = _validated_values(matrix, refs)
    order = np.asarray(
        sorted(range(len(refs)), key=lambda item: refs[item]), dtype=np.int64
    )
    stable_matrix = np.ascontiguousarray(values[order], dtype=np.float32)
    stable_refs = tuple(refs[item] for item in order)
    hyperplanes = generate_lsh_hyperplanes(384, configuration)
    signatures = np.empty((records, configuration.table_count), dtype=np.uint16)
    weights = 1 << np.arange(configuration.bits_per_table, dtype=np.uint16)
    telemetry.elapsed["LSH_SETUP"] += time.perf_counter() - setup_started

    bucket_rows = []
    for table in range(configuration.table_count):
        telemetry.active_sub_stage = "SIGNATURE_COMPUTATION"
        started = time.perf_counter()
        codes = (
            (stable_matrix @ hyperplanes[table].T >= 0).astype(np.uint16)
            * weights
        ).sum(axis=1, dtype=np.uint16)
        signatures[:, table] = codes
        telemetry.elapsed["SIGNATURE_COMPUTATION"] += time.perf_counter() - started

        telemetry.active_sub_stage = "INDEX_BUILD"
        started = time.perf_counter()
        table_buckets: dict[int, list[int]] = {}
        for position, code in enumerate(codes):
            table_buckets.setdefault(int(code), []).append(position)
        bucket_rows.append({code: tuple(items) for code, items in table_buckets.items()})
        telemetry.elapsed["INDEX_BUILD"] += time.perf_counter() - started
        telemetry.checkpoint()

    setup_started = time.perf_counter()
    required = min(FINAL_TOP_K, records - 1)
    bucket_cap = max(
        16, configuration.candidate_pool_k
        * configuration.bucket_probe_cap_multiplier
    )
    gather_limit = min(
        records - 1,
        configuration.candidate_pool_k
        * configuration.candidate_gather_multiplier,
    )
    masks = _probe_masks(configuration.bits_per_table, configuration.probe_radius)
    popcount = np.fromiter(
        (value.bit_count() for value in range(1 << configuration.bits_per_table)),
        dtype=np.uint8,
    )
    telemetry.elapsed["LSH_SETUP"] += time.perf_counter() - setup_started

    directed_stable = {}
    bucket_members_per_anchor = []
    unique_per_anchor = []
    pool_sizes = []
    source = 0
    while source < records:
        batch_end = min(records, source + 64)
        pools = []
        for anchor in range(source, batch_end):
            candidates: set[int] = set()
            anchor_visits = 0
            hit_gather_cap = False
            for mask in masks:
                started = time.perf_counter()
                codes = tuple(
                    int(signatures[anchor, table]) ^ mask
                    for table in range(configuration.table_count)
                )
                telemetry.elapsed["PROBE_CODE_GENERATION"] += time.perf_counter() - started

                started = time.perf_counter()
                buckets = tuple(
                    bucket_rows[table].get(code, ())
                    for table, code in enumerate(codes)
                )
                telemetry.elapsed["BUCKET_LOOKUP"] += time.perf_counter() - started
                telemetry.counters["bucket_lookups"] += len(buckets)
                hits = sum(bool(bucket) for bucket in buckets)
                telemetry.counters["bucket_hits"] += hits
                telemetry.counters["empty_bucket_lookups"] += len(buckets) - hits

                started = time.perf_counter()
                bounded = tuple(bucket[:bucket_cap] for bucket in buckets)
                visits = sum(len(bucket) for bucket in bounded)
                telemetry.elapsed["BUCKET_MEMBER_ENUMERATION"] += (
                    time.perf_counter() - started
                )
                anchor_visits += visits
                telemetry.counters["bucket_members_visited"] += visits
                telemetry.counters["raw_candidate_visits"] += visits
                telemetry.counters["buckets_hitting_cap"] += sum(
                    len(bucket) >= bucket_cap for bucket in buckets
                )

                started = time.perf_counter()
                for bucket in bounded:
                    candidates.update(bucket)
                candidates.discard(anchor)
                telemetry.elapsed["CANDIDATE_DEDUP_OR_ACCUMULATION"] += (
                    time.perf_counter() - started
                )
                if len(candidates) >= gather_limit:
                    hit_gather_cap = True
                    break

            if len(candidates) < required:
                raise CharacterRetrievalError(
                    CharacterRetrievalFailureCategory.LSH_CANDIDATE_POOL_INSUFFICIENT,
                    "profiled LSH pool cannot satisfy final top-k",
                )
            unique_count = len(candidates)
            bucket_members_per_anchor.append(anchor_visits)
            unique_per_anchor.append(unique_count)
            telemetry.counters["unique_candidates_before_pool"] += unique_count
            telemetry.counters["dedup_eliminations"] += anchor_visits - unique_count
            telemetry.counters["anchors_hitting_gather_cap"] += int(hit_gather_cap)

            telemetry.active_sub_stage = "CANDIDATE_POOL_SELECTION"
            started = time.perf_counter()
            candidate_array = np.fromiter(candidates, dtype=np.int64)
            xor = np.bitwise_xor(signatures[candidate_array], signatures[anchor])
            approximate_matches = (
                configuration.table_count * configuration.bits_per_table
                - popcount[xor].sum(axis=1)
            )
            approximate_order = np.lexsort((
                np.asarray([stable_refs[item] for item in candidate_array], dtype=object),
                -approximate_matches.astype(np.int32),
            ))
            gathered = candidate_array[approximate_order[:gather_limit]]
            retained = gathered[:configuration.candidate_pool_k]
            telemetry.elapsed["CANDIDATE_POOL_SELECTION"] += time.perf_counter() - started
            pool_sizes.append(len(retained))
            telemetry.counters["candidate_pool_evaluations"] += len(retained)
            telemetry.counters["anchors_with_pool_below_top_k"] += int(
                len(retained) < required
            )
            pools.append(retained)

        lengths = [len(pool) for pool in pools]
        telemetry.active_sub_stage = "EXACT_RERANK"
        started = time.perf_counter()
        width = max(lengths)
        pool_matrix = np.empty((len(pools), width), dtype=np.int64)
        for offset, pool in enumerate(pools):
            pool_matrix[offset, :len(pool)] = pool
            pool_matrix[offset, len(pool):] = pool[0]
        exact_batch = np.einsum(
            "bkd,bd->bk", stable_matrix[pool_matrix],
            stable_matrix[source:batch_end], optimize=True,
        )
        telemetry.elapsed["EXACT_RERANK"] += time.perf_counter() - started
        telemetry.counters["exact_rerank_evaluations"] += sum(lengths)

        telemetry.active_sub_stage = "DIRECTED_TOPK_FINALIZATION"
        started = time.perf_counter()
        for offset, anchor in enumerate(range(source, batch_end)):
            pool = pool_matrix[offset, :lengths[offset]]
            scores = exact_batch[offset, :lengths[offset]]
            exact_order = np.lexsort((
                np.asarray([stable_refs[item] for item in pool], dtype=object),
                -scores,
            ))[:required]
            if len(exact_order) < required or np.any(scores[exact_order] <= 0):
                raise CharacterRetrievalError(
                    CharacterRetrievalFailureCategory.LSH_CANDIDATE_POOL_INSUFFICIENT,
                    "profiled LSH pool has too few positive candidates",
                )
            directed_stable[anchor] = tuple(
                (int(pool[position]), float(scores[position]))
                for position in exact_order
            )
        telemetry.elapsed["DIRECTED_TOPK_FINALIZATION"] += time.perf_counter() - started
        source = batch_end
        telemetry.anchors_completed = source
        if source % CHECKPOINT_ANCHOR_BATCH == 0 or source == records:
            telemetry.active_sub_stage = (
                "PROBE_CODE_GENERATION" if source < records else "RECIPROCAL_PAIR_RECONSTRUCTION"
            )
            telemetry.checkpoint()

    telemetry.active_sub_stage = "DIRECTED_TOPK_FINALIZATION"
    started = time.perf_counter()
    directed = {
        int(order[anchor]): tuple(
            (int(order[target]), score) for target, score in neighbors
        )
        for anchor, neighbors in directed_stable.items()
    }
    telemetry.elapsed["DIRECTED_TOPK_FINALIZATION"] += time.perf_counter() - started

    telemetry.active_sub_stage = "RECIPROCAL_PAIR_RECONSTRUCTION"
    started = time.perf_counter()
    directed_fp, pair_fp, directed_count, reciprocal_count = (
        _semantic_fingerprints(directed, refs)
    )
    telemetry.elapsed["RECIPROCAL_PAIR_RECONSTRUCTION"] += (
        time.perf_counter() - started
    )

    char_total = time.perf_counter() - telemetry.started
    child_total = sum(telemetry.elapsed[name] for name in TAXONOMY)
    other = max(0.0, char_total - child_total)
    timings = {
        "CHAR_TOTAL": round(char_total, 6),
        **{name: round(telemetry.elapsed[name], 6) for name in TAXONOMY},
        "OTHER_UNATTRIBUTED": round(other, 6),
    }
    counters = dict(telemetry.counters)
    counters.update({
        "records": records,
        "candidate_pool": _percentiles(pool_sizes),
        "bucket_members_visited_per_anchor": _percentiles(bucket_members_per_anchor),
        "unique_candidates_per_anchor": _percentiles(unique_per_anchor),
        "directed_neighbors": directed_count,
        "reciprocal_pairs": reciprocal_count,
    })
    result = {
        "contract_version": PROFILE_CONTRACT_VERSION,
        "status": "COMPLETED",
        "instrumentation_enabled": True,
        "records": records,
        "seed": seed,
        "configuration": {
            "table_count": configuration.table_count,
            "bits_per_table": configuration.bits_per_table,
            "seed": configuration.seed,
            "probe_radius": configuration.probe_radius,
            "bucket_cap": configuration.candidate_pool_k
            * configuration.bucket_probe_cap_multiplier,
            "gather_cap": configuration.candidate_pool_k
            * configuration.candidate_gather_multiplier,
            "candidate_pool": configuration.candidate_pool_k,
            "top_k": FINAL_TOP_K,
            "checkpoint_anchor_batch": CHECKPOINT_ANCHOR_BATCH,
        },
        "contract_fingerprint": character_retrieval_contract_fingerprint(
            records, FINAL_TOP_K, configuration
        ),
        "timing_seconds": timings,
        "counters": counters,
        "directed_neighbor_fingerprint": directed_fp,
        "pair_fingerprint": pair_fp,
        "provider_calls": 0,
        "configured_database_accessed": False,
        "raw_record_data_emitted": False,
    }
    telemetry.active_sub_stage = "COMPLETED"
    telemetry.checkpoint(status="COMPLETED")
    return result


def timeout_result(partial: dict, *, timeout_seconds: float, wall_seconds: float):
    active = partial.get("active_sub_stage") or "UNKNOWN_ACTIVE_SUB_STAGE"
    if active == "COMPLETED":
        active = "TIMEOUT_AFTER_LAST_CHECKPOINT"
    return {
        "contract_version": PROFILE_CONTRACT_VERSION,
        "status": "TIMED_OUT",
        "timeout_seconds": timeout_seconds,
        "bounded_wall_seconds": round(wall_seconds, 6),
        "active_sub_stage": active,
        "last_checkpoint": partial,
    }


def _worker(arguments, result_path):
    result = run_profile(**arguments)
    Path(result_path).write_text(
        json.dumps(result, sort_keys=True), encoding="utf-8"
    )


def run_bounded_profile(
    records: int, *, seed: int = CANONICAL_SEED, timeout_seconds: float = 450.0
):
    with tempfile.TemporaryDirectory(prefix="gf11d-char-pre-") as directory:
        root = Path(directory)
        checkpoint = root / "checkpoint.json"
        result_path = root / "result.json"
        arguments = {
            "records": records,
            "seed": seed,
            "checkpoint_path": checkpoint,
        }
        process = multiprocessing.get_context("spawn").Process(
            target=_worker, args=(arguments, str(result_path))
        )
        started = time.perf_counter()
        process.start()
        process.join(timeout_seconds)
        wall = time.perf_counter() - started
        if process.is_alive():
            process.terminate()
            process.join(30)
            partial = json.loads(checkpoint.read_text(encoding="utf-8")) \
                if checkpoint.exists() else {}
            return timeout_result(
                partial, timeout_seconds=timeout_seconds, wall_seconds=wall
            )
        if process.exitcode != 0 or not result_path.exists():
            return {
                "contract_version": PROFILE_CONTRACT_VERSION,
                "status": "FAILED",
                "safe_failure_category": "PROFILE_PROCESS_EXITED_WITHOUT_RESULT",
            }
        return json.loads(result_path.read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, required=True)
    parser.add_argument("--seed", type=int, default=CANONICAL_SEED)
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--uninstrumented", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.uninstrumented:
        result = run_uninstrumented(args.records, seed=args.seed)
    elif args.timeout_seconds is not None:
        result = run_bounded_profile(
            args.records, seed=args.seed, timeout_seconds=args.timeout_seconds
        )
    else:
        result = run_profile(args.records, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if result.get("status") == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
