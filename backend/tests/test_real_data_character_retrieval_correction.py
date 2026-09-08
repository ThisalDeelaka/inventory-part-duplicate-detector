"""CHAR-R1..CHAR-R24 structural coverage for the real-data correction."""

from __future__ import annotations

import inspect

import numpy as np
from sklearn.preprocessing import normalize

from app.core.config import Settings
from app.services import character_retrieval
from app.services.character_retrieval import (
    CharacterLshConfiguration,
    _CharacterLshIndex,
    retrieve_lsh_directed_neighbors,
)
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
)


def _refs(count):
    return tuple(f"synthetic-ref-{index:04d}" for index in range(count))


def _config(count):
    return CharacterLshConfiguration(
        table_count=4,
        bits_per_table=2,
        probe_radius=2,
        candidate_pool_k=max(1, count - 1),
    )


def _matrix(rows):
    values = np.zeros((len(rows), 384), dtype=np.float32)
    values[:, : len(rows[0])] = np.asarray(rows, dtype=np.float32)
    return normalize(values).astype(np.float32)


def _semantic(result, refs):
    return tuple(
        (refs[source], tuple((refs[target], round(score, 7)) for target, score in neighbors))
        for source, neighbors in sorted(result.directed_neighbors.items())
    )


def test_char_r4_r6_r7_r13_zero_and_orthogonal_vectors_return_no_fabricated_neighbors():
    matrix = np.zeros((4, 384), dtype=np.float32)
    matrix[1:, :3] = np.eye(3, dtype=np.float32)
    result = retrieve_lsh_directed_neighbors(matrix, _refs(4), 3, _config(4))
    assert result.directed_neighbors == {index: () for index in range(4)}
    assert result.metrics.zero_neighbor_anchors == 4
    assert all(source != target for source, rows in result.directed_neighbors.items() for target, _ in rows)


def test_char_r5_r9_r14_fewer_than_k_sparse_positives_are_exactly_ranked():
    matrix = _matrix(((1, 0, 0), (0.8, 0.6, 0), (0.6, 0.8, 0), (0, 0, 1)))
    refs = _refs(4)
    result = retrieve_lsh_directed_neighbors(matrix, refs, 3, _config(4))
    assert tuple(target for target, _ in result.directed_neighbors[0]) == (1, 2)
    assert tuple(round(score, 7) for _, score in result.directed_neighbors[0]) == (0.8, 0.6)
    assert result.metrics.short_neighbor_anchors == 3
    assert result.metrics.zero_neighbor_anchors == 1


def test_char_r3_r11_lsh_miss_is_not_filled_with_an_unprobed_neighbor(monkeypatch):
    matrix = _matrix(((1, 0), (1, 0), (0, 1)))
    refs = _refs(3)
    configuration = CharacterLshConfiguration(
        table_count=1, bits_per_table=2, probe_radius=0, candidate_pool_k=1
    )
    crafted = _CharacterLshIndex(
        matrix=matrix,
        refs=refs,
        original_positions=np.arange(3, dtype=np.int64),
        hyperplanes=np.zeros((1, 2, 384), dtype=np.float32),
        signatures=np.asarray(((0,), (1,), (0,)), dtype=np.uint16),
        buckets=({0: (0, 2), 1: (1,)},),
        build_time_ms=0.0,
    )
    monkeypatch.setattr(character_retrieval, "_build_lsh_index", lambda *_args: crafted)
    result = retrieve_lsh_directed_neighbors(matrix, refs, 1, configuration)
    assert float(matrix[0] @ matrix[1]) == 1.0
    assert result.directed_neighbors[0] == ()
    assert result.metrics.zero_neighbor_anchors >= 1


def test_char_r8_r9_r10_r16_equal_vectors_are_deterministic_and_tied_by_ref():
    matrix = _matrix(((1, 0), (1, 0), (1, 0), (0.8, 0.6), (0, 1)))
    refs = ("z", "a", "m", "n", "q")
    runs = [retrieve_lsh_directed_neighbors(matrix, refs, 3, _config(5)) for _ in range(3)]
    assert _semantic(runs[0], refs) == _semantic(runs[1], refs) == _semantic(runs[2], refs)
    assert tuple(refs[target] for target, _ in runs[0].directed_neighbors[0]) == ("a", "m", "n")
    assert runs[0].metrics.full_neighbor_anchors == 4
    assert runs[0].metrics.short_neighbor_anchors == 1


def test_char_r12_large_n_path_contains_no_unconditional_exact_fallback():
    source = inspect.getsource(character_retrieval.retrieve_lsh_directed_neighbors)
    assert "NearestNeighbors" not in source
    assert "matrix @ index.matrix" not in source
    assert "candidate_pool_k" in source


def test_char_r17_r18_r19_r20_small_mode_smoke_preserves_scan_modes_and_zero_provider():
    import pandas as pd

    frame = pd.DataFrame([
        {
            "PART_NO": f"P-{index}",
            "DESCRIPTION": f"synthetic motor bearing {index % 2}",
            "CONTRACT": "S1" if index < 3 else "S2",
            "UNIT_MEAS": "EA",
            CANONICAL_RECORD_REF_FIELD: f"ref-{index}",
        }
        for index in range(6)
    ])
    configuration = Settings(
        llm_demo_enabled=False,
        llm_provider="none",
        group_llm_provider="none",
        hybrid_retrieval_vector_top_k=3,
    )
    retriever = HybridCandidateRetriever(configuration)
    same = retriever.retrieve(frame, "SAME_SITE_DUPLICATE")
    cross = retriever.retrieve(frame, "CROSS_SITE_STANDARDIZATION")
    assert same.character_retrieval is not None
    assert cross.character_retrieval is not None
    assert same.metrics.provider_request_count == cross.metrics.provider_request_count == 0


def test_char_r21_r22_r23_r24_source_scope_has_no_data_schema_provider_or_secret_surface():
    source = inspect.getsource(character_retrieval).casefold()
    for forbidden in (".env", "groq", "anthropic", "provider", "alembic", "migration"):
        assert forbidden not in source
    assert "score_candidate" not in source
    assert "group_resolution" not in source
