"""Deterministic production strategies for the frozen character-vector channel.

LSH is candidate generation only. Final neighbors always use exact cosine over
the existing L2-normalized 384-bin vectors and canonical GF-1 tie ordering.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum

import numpy as np
import sklearn
from sklearn.preprocessing import normalize


CHARACTER_RETRIEVAL_CONTRACT_VERSION = "character-retrieval-strategy-v1"
LSH_CONTRACT_VERSION = "fixed-seed-cosine-lsh-exact-rerank-v1"
VECTOR_REPRESENTATION_VERSION = "sklearn-hashing-domain-v1-384-char-wb-3-5"
EXACT_RERANK_VERSION = "exact-cosine-canonical-tie-v1"
ACTIVATION_THRESHOLD = 2_000


class CharacterRetrievalStrategy(str, Enum):
    EXACT = "EXACT"
    FIXED_SEED_LSH_EXACT_RERANK = "FIXED_SEED_LSH_EXACT_RERANK"


class CharacterRetrievalFailureCategory(str, Enum):
    LSH_INDEX_BUILD_FAILED = "LSH_INDEX_BUILD_FAILED"
    LSH_QUERY_FAILED = "LSH_QUERY_FAILED"
    LSH_CANDIDATE_POOL_INSUFFICIENT = "LSH_CANDIDATE_POOL_INSUFFICIENT"
    LSH_CONFIGURATION_INVALID = "LSH_CONFIGURATION_INVALID"
    LSH_DETERMINISM_VALIDATION_FAILED = "LSH_DETERMINISM_VALIDATION_FAILED"


class CharacterRetrievalError(RuntimeError):
    def __init__(self, category: CharacterRetrievalFailureCategory, message: str) -> None:
        super().__init__(message)
        self.safe_category = category.value


@dataclass(frozen=True)
class CharacterLshConfiguration:
    table_count: int = 8
    bits_per_table: int = 12
    seed: int = 1101
    probe_radius: int = 2
    candidate_pool_k: int = 320
    bucket_probe_cap_multiplier: int = 2
    candidate_gather_multiplier: int = 4

    def validate(self, final_top_k: int) -> None:
        invalid = None
        if final_top_k < 1 or self.candidate_pool_k < final_top_k:
            invalid = "candidate pool must be at least final top-k"
        elif not 1 <= self.table_count <= 32:
            invalid = "table count is outside the supported range"
        elif not 2 <= self.bits_per_table <= 16:
            invalid = "bits per table are outside the supported range"
        elif not 0 <= self.probe_radius <= 2:
            invalid = "probe radius is outside the supported range"
        elif self.seed < 0:
            invalid = "seed must be nonnegative"
        elif self.bucket_probe_cap_multiplier < 1 or self.candidate_gather_multiplier < 1:
            invalid = "candidate bounds must be positive"
        if invalid:
            raise CharacterRetrievalError(
                CharacterRetrievalFailureCategory.LSH_CONFIGURATION_INVALID,
                f"invalid character LSH configuration: {invalid}",
            )


PRODUCTION_LSH_CONFIGURATION = CharacterLshConfiguration()


def _select_candidate_pool_exact(
    candidate_array: np.ndarray,
    approximate_matches: np.ndarray,
    *,
    gather_limit: int,
    candidate_pool_k: int,
) -> np.ndarray:
    """Return the exact legacy pool order without sorting ineligible priorities.

    Candidate ids are positions in the record-ref-key-sorted LSH index, so
    ascending integer id is exactly the frozen canonical reference tie rule.
    Bit agreement is an integer in the finite [0, tables * bits] domain.
    """
    limit = min(len(candidate_array), gather_limit, candidate_pool_k)
    if limit <= 0:
        return np.empty(0, dtype=np.int64)
    priorities = np.asarray(approximate_matches)
    counts = np.bincount(priorities.astype(np.int64, copy=False))
    selected = []
    remaining = limit
    for priority in np.flatnonzero(counts)[::-1]:
        positions = np.flatnonzero(priorities == priority)
        canonical = np.sort(candidate_array[positions])
        take = min(remaining, len(canonical))
        selected.append(canonical[:take])
        remaining -= take
        if remaining == 0:
            break
    return np.concatenate(selected).astype(np.int64, copy=False)


@dataclass(frozen=True)
class CharacterRetrievalWorkMetrics:
    strategy: CharacterRetrievalStrategy
    contract_fingerprint: str
    index_build_time_ms: float = 0.0
    bucket_enumeration_count: int = 0
    candidate_pool_evaluations: int = 0
    exact_rerank_evaluations: int = 0
    max_candidate_pool: int = 0
    retrieval_time_ms: float = 0.0


@dataclass(frozen=True)
class CharacterLshResult:
    directed_neighbors: dict[int, tuple[tuple[int, float], ...]]
    metrics: CharacterRetrievalWorkMetrics


@dataclass(frozen=True)
class _CharacterLshIndex:
    matrix: np.ndarray
    refs: tuple[str, ...]
    original_positions: np.ndarray
    hyperplanes: np.ndarray
    signatures: np.ndarray
    buckets: tuple[dict[int, tuple[int, ...]], ...]
    build_time_ms: float


def select_character_retrieval_strategy(record_count: int) -> CharacterRetrievalStrategy:
    if record_count < 0:
        raise ValueError("record count cannot be negative")
    if record_count < ACTIVATION_THRESHOLD:
        return CharacterRetrievalStrategy.EXACT
    return CharacterRetrievalStrategy.FIXED_SEED_LSH_EXACT_RERANK


def _stable_fingerprint(payload) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def character_retrieval_contract_payload(
    record_count: int,
    final_top_k: int,
    configuration: CharacterLshConfiguration = PRODUCTION_LSH_CONFIGURATION,
) -> dict:
    config = configuration
    config.validate(final_top_k)
    return {
        "strategy_contract_version": CHARACTER_RETRIEVAL_CONTRACT_VERSION,
        "selected_strategy": select_character_retrieval_strategy(record_count).value,
        "activation_threshold": ACTIVATION_THRESHOLD,
        "lsh_contract_version": LSH_CONTRACT_VERSION,
        "backend": "numpy-random-hyperplane-lsh",
        "numpy_version": np.__version__,
        "scikit_learn_version": sklearn.__version__,
        "vector_representation_version": VECTOR_REPRESENTATION_VERSION,
        "random_generator": "numpy-PCG64",
        "seed": config.seed,
        "table_count": config.table_count,
        "bits_per_table": config.bits_per_table,
        "probe_radius": config.probe_radius,
        "candidate_pool_k": config.candidate_pool_k,
        "bucket_probe_cap_multiplier": config.bucket_probe_cap_multiplier,
        "candidate_gather_multiplier": config.candidate_gather_multiplier,
        "stable_insertion_order": "record_ref_key-ascending",
        "candidate_retention_order": "bit-agreement-descending-record-ref-ascending",
        "exact_rerank_version": EXACT_RERANK_VERSION,
        "final_top_k": final_top_k,
    }


def character_retrieval_contract_fingerprint(
    record_count: int,
    final_top_k: int,
    configuration: CharacterLshConfiguration = PRODUCTION_LSH_CONFIGURATION,
) -> str:
    return _stable_fingerprint(
        character_retrieval_contract_payload(
            record_count, final_top_k, configuration
        )
    )


def generate_lsh_hyperplanes(
    vector_dimension: int = 384,
    configuration: CharacterLshConfiguration = PRODUCTION_LSH_CONFIGURATION,
) -> np.ndarray:
    configuration.validate(1)
    if vector_dimension != 384:
        raise CharacterRetrievalError(
            CharacterRetrievalFailureCategory.LSH_CONFIGURATION_INVALID,
            "LSH requires the frozen 384-bin vector dimension",
        )
    rng = np.random.Generator(np.random.PCG64(configuration.seed))
    values = rng.standard_normal(
        (configuration.table_count, configuration.bits_per_table, vector_dimension),
        dtype=np.float32,
    )
    return normalize(values.reshape(-1, vector_dimension), norm="l2").astype(
        np.float32
    ).reshape(values.shape)


def _validated_values(matrix, canonical_record_refs) -> tuple[np.ndarray, tuple[str, ...]]:
    values = np.asarray(matrix, dtype=np.float32)
    refs = tuple(str(value or "").strip() for value in canonical_record_refs)
    if values.ndim != 2 or values.shape[1] != 384:
        raise CharacterRetrievalError(
            CharacterRetrievalFailureCategory.LSH_CONFIGURATION_INVALID,
            "LSH requires the frozen 384-bin character vectors",
        )
    if (
        len(refs) != len(values)
        or any(not value for value in refs)
        or len(set(refs)) != len(refs)
    ):
        raise CharacterRetrievalError(
            CharacterRetrievalFailureCategory.LSH_CONFIGURATION_INVALID,
            "LSH requires one unique nonblank canonical reference per vector",
        )
    norms = np.linalg.norm(values, axis=1)
    if np.any((norms != 0) & ~np.isclose(norms, 1.0, rtol=1e-5, atol=1e-6)):
        raise CharacterRetrievalError(
            CharacterRetrievalFailureCategory.LSH_CONFIGURATION_INVALID,
            "LSH requires L2-normalized character vectors",
        )
    return values, refs


def _build_lsh_index(
    matrix, canonical_record_refs, configuration: CharacterLshConfiguration
) -> _CharacterLshIndex:
    try:
        values, refs = _validated_values(matrix, canonical_record_refs)
        started = time.perf_counter()
        order = np.asarray(
            sorted(range(len(refs)), key=lambda item: refs[item]), dtype=np.int64
        )
        stable_matrix = np.ascontiguousarray(values[order], dtype=np.float32)
        stable_refs = tuple(refs[item] for item in order)
        hyperplanes = generate_lsh_hyperplanes(384, configuration)
        signatures = np.empty(
            (len(refs), configuration.table_count), dtype=np.uint16
        )
        weights = 1 << np.arange(configuration.bits_per_table, dtype=np.uint16)
        bucket_rows = []
        for table in range(configuration.table_count):
            codes = (
                (stable_matrix @ hyperplanes[table].T >= 0).astype(np.uint16)
                * weights
            ).sum(axis=1, dtype=np.uint16)
            signatures[:, table] = codes
            table_buckets: dict[int, list[int]] = {}
            for position, code in enumerate(codes):
                table_buckets.setdefault(int(code), []).append(position)
            bucket_rows.append(
                {code: tuple(items) for code, items in table_buckets.items()}
            )
        return _CharacterLshIndex(
            matrix=stable_matrix,
            refs=stable_refs,
            original_positions=order,
            hyperplanes=hyperplanes,
            signatures=signatures,
            buckets=tuple(bucket_rows),
            build_time_ms=round((time.perf_counter() - started) * 1000, 3),
        )
    except CharacterRetrievalError:
        raise
    except Exception as exc:
        raise CharacterRetrievalError(
            CharacterRetrievalFailureCategory.LSH_INDEX_BUILD_FAILED,
            "deterministic character LSH index construction failed",
        ) from exc


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


def retrieve_lsh_directed_neighbors(
    matrix,
    canonical_record_refs,
    final_top_k: int,
    configuration: CharacterLshConfiguration = PRODUCTION_LSH_CONFIGURATION,
) -> CharacterLshResult:
    configuration.validate(final_top_k)
    index = _build_lsh_index(matrix, canonical_record_refs, configuration)
    count = len(index.refs)
    contract_fingerprint = character_retrieval_contract_fingerprint(
        count, final_top_k, configuration
    )
    if count < 2:
        return CharacterLshResult(
            {},
            CharacterRetrievalWorkMetrics(
                CharacterRetrievalStrategy.FIXED_SEED_LSH_EXACT_RERANK,
                contract_fingerprint,
                index_build_time_ms=index.build_time_ms,
            ),
        )
    required = min(final_top_k, count - 1)
    bucket_cap = max(
        16,
        configuration.candidate_pool_k
        * configuration.bucket_probe_cap_multiplier,
    )
    gather_limit = min(
        count - 1,
        configuration.candidate_pool_k
        * configuration.candidate_gather_multiplier,
    )
    masks = _probe_masks(
        configuration.bits_per_table, configuration.probe_radius
    )
    popcount = np.fromiter(
        (
            value.bit_count()
            for value in range(1 << configuration.bits_per_table)
        ),
        dtype=np.uint8,
    )
    directed_stable = {}
    bucket_enumerations = 0
    pool_evaluations = 0
    rerank_evaluations = 0
    max_pool = 0
    query_started = time.perf_counter()
    try:
        source = 0
        while source < count:
            batch_end = min(count, source + 64)
            pools = []
            for anchor in range(source, batch_end):
                candidates: set[int] = set()
                for mask in masks:
                    for table in range(configuration.table_count):
                        code = int(index.signatures[anchor, table]) ^ mask
                        bucket = index.buckets[table].get(code, ())
                        bucket_enumerations += min(len(bucket), bucket_cap)
                        candidates.update(bucket[:bucket_cap])
                        candidates.discard(anchor)
                    if len(candidates) >= gather_limit:
                        break
                if len(candidates) < required:
                    raise CharacterRetrievalError(
                        CharacterRetrievalFailureCategory.LSH_CANDIDATE_POOL_INSUFFICIENT,
                        "LSH candidate pool cannot satisfy final character top-k",
                    )
                candidate_array = np.fromiter(candidates, dtype=np.int64)
                xor = np.bitwise_xor(
                    index.signatures[candidate_array], index.signatures[anchor]
                )
                approximate_matches = (
                    configuration.table_count * configuration.bits_per_table
                    - popcount[xor].sum(axis=1)
                )
                retained = _select_candidate_pool_exact(
                    candidate_array,
                    approximate_matches,
                    gather_limit=gather_limit,
                    candidate_pool_k=configuration.candidate_pool_k,
                )
                pool_evaluations += len(retained)
                max_pool = max(max_pool, len(retained))
                pools.append(retained)

            lengths = [len(pool) for pool in pools]
            width = max(lengths)
            pool_matrix = np.empty((len(pools), width), dtype=np.int64)
            for offset, pool in enumerate(pools):
                pool_matrix[offset, : len(pool)] = pool
                pool_matrix[offset, len(pool) :] = pool[0]
            rerank_evaluations += sum(lengths)
            exact_batch = np.einsum(
                "bkd,bd->bk",
                index.matrix[pool_matrix],
                index.matrix[source:batch_end],
                optimize=True,
            )
            for offset, anchor in enumerate(range(source, batch_end)):
                pool = pool_matrix[offset, : lengths[offset]]
                scores = exact_batch[offset, : lengths[offset]]
                exact_order = np.lexsort(
                    (
                        np.asarray(
                            [index.refs[item] for item in pool], dtype=object
                        ),
                        -scores,
                    )
                )[:required]
                if (
                    len(exact_order) < required
                    or np.any(scores[exact_order] <= 0)
                ):
                    raise CharacterRetrievalError(
                        CharacterRetrievalFailureCategory.LSH_CANDIDATE_POOL_INSUFFICIENT,
                        "LSH candidate pool has too few positive-cosine candidates",
                    )
                directed_stable[anchor] = tuple(
                    (int(pool[position]), float(scores[position]))
                    for position in exact_order
                )
            source = batch_end
    except CharacterRetrievalError:
        raise
    except Exception as exc:
        raise CharacterRetrievalError(
            CharacterRetrievalFailureCategory.LSH_QUERY_FAILED,
            "deterministic character LSH query failed",
        ) from exc

    query_ms = round((time.perf_counter() - query_started) * 1000, 3)
    remapped = {
        int(index.original_positions[anchor]): tuple(
            (int(index.original_positions[target]), score)
            for target, score in neighbors
        )
        for anchor, neighbors in directed_stable.items()
    }
    return CharacterLshResult(
        remapped,
        CharacterRetrievalWorkMetrics(
            strategy=CharacterRetrievalStrategy.FIXED_SEED_LSH_EXACT_RERANK,
            contract_fingerprint=contract_fingerprint,
            index_build_time_ms=index.build_time_ms,
            bucket_enumeration_count=bucket_enumerations,
            candidate_pool_evaluations=pool_evaluations,
            exact_rerank_evaluations=rerank_evaluations,
            max_candidate_pool=max_pool,
            retrieval_time_ms=round(index.build_time_ms + query_ms, 3),
        ),
    )
