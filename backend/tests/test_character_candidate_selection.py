"""GF-11D-CHAR1 exact selector acceptance tests H1-H18/E1-E10."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from app.orchestration.pair_path_deprecation import pair_path_write_policy
from app.services import character_retrieval
from app.services.character_retrieval import _select_candidate_pool_exact
from app.benchmarks.approximate_character_retrieval import corpus_vectors
from app.benchmarks.character_retrieval_profile import _semantic_fingerprints


POOL = 320
GATHER = 1280


def _legacy(candidates, priorities):
    candidates = np.asarray(candidates, dtype=np.int64)
    priorities = np.asarray(priorities)
    refs = np.asarray([f"ref-{item:08d}" for item in candidates], dtype=object)
    order = np.lexsort((refs, -priorities.astype(np.int32)))
    return candidates[order[:GATHER]][:POOL]


def _new(candidates, priorities):
    return _select_candidate_pool_exact(
        np.asarray(candidates, dtype=np.int64), np.asarray(priorities),
        gather_limit=GATHER, candidate_pool_k=POOL,
    )


def _assert_equal(candidates, priorities):
    assert np.array_equal(_new(candidates, priorities), _legacy(candidates, priorities))


def test_h1_exact_current_pool_ranking_key_is_frozen():
    source = inspect.getsource(_select_candidate_pool_exact)
    assert "priorities" in source
    assert "[::-1]" in source
    assert "np.sort(candidate_array[positions])" in source


def test_h2_e1_fewer_than_320():
    candidates = np.arange(73)
    _assert_equal(candidates[::-1], candidates[::-1] % 7)


def test_h3_e2_exactly_320():
    candidates = np.arange(320)
    _assert_equal(candidates[::-1], candidates[::-1] % 97)


def test_h4_e3_more_than_320_unique_candidate_priorities():
    candidates = np.arange(2000)
    _assert_equal(candidates[::-1], candidates[::-1] % 97)


def test_h5_e4_e5_huge_best_and_boundary_ties():
    candidates = np.arange(3000)[::-1]
    priorities = np.concatenate((np.full(200, 96), np.full(1500, 95), np.zeros(1300)))
    _assert_equal(candidates, priorities)


def test_h6_e6_all_priorities_equal():
    candidates = np.arange(5000)[::-1]
    _assert_equal(candidates, np.full(len(candidates), 42))


def test_e7_duplicate_encounters_are_deduplicated_before_selection():
    encounters = [9, 1, 9, 5, 1, 3, 5]
    candidates = np.asarray(list(set(encounters)), dtype=np.int64)
    _assert_equal(candidates, np.asarray([20 + item for item in candidates]))


def test_h7_e8_e9_reverse_and_fixed_shuffles_are_equal():
    candidates = np.arange(4096)
    priorities = candidates % 97
    for order in (
        candidates[::-1],
        *(np.random.default_rng(seed).permutation(candidates) for seed in (7, 19, 1101)),
    ):
        _assert_equal(order, priorities[order])


def test_e10_canonical_reference_key_extremes():
    candidates = np.asarray([9999, 0, 5000, 1, 9998])
    _assert_equal(candidates, np.full(5, 96))


def test_h8_randomized_differential_zero_mismatches():
    rng = np.random.default_rng(1101)
    for case in range(500):
        count = int(rng.integers(0, 5001))
        candidates = rng.permutation(count).astype(np.int64)
        if case % 3 == 0:
            priorities = rng.integers(0, 4, count, dtype=np.int16)
        elif case % 3 == 1:
            priorities = rng.integers(0, 97, count, dtype=np.int16)
        else:
            priorities = np.full(count, int(rng.integers(0, 97)), dtype=np.int16)
        _assert_equal(candidates, priorities)


def test_h9_pool_size_is_bounded():
    result = _new(np.arange(5000), np.arange(5000) % 97)
    assert len(result) == POOL


def test_h10_selected_sequence_is_canonical_and_deterministic():
    candidates = np.arange(1000)[::-1]
    priorities = candidates % 5
    first = _new(candidates, priorities)
    second = _new(candidates[::-1], priorities[::-1])
    assert np.array_equal(first, second)


def test_h11_exact_rerank_receives_identical_sequence(monkeypatch):
    rng = np.random.default_rng(19)
    candidates = rng.permutation(2000).astype(np.int64)
    priorities = rng.integers(0, 97, 2000, dtype=np.int16)
    assert np.array_equal(_new(candidates, priorities), _legacy(candidates, priorities))


@pytest.mark.parametrize("records", (500, 5_000))
def test_h12_h13_old_new_production_directed_pair_and_scores_match(
    monkeypatch, records,
):
    _corpus, matrix, refs = corpus_vectors(records, seed=1101)
    optimized = character_retrieval._select_candidate_pool_exact

    def legacy(candidate_array, approximate_matches, *, gather_limit, candidate_pool_k):
        order = np.lexsort((
            candidate_array,
            -approximate_matches.astype(np.int32),
        ))
        return candidate_array[order[:gather_limit]][:candidate_pool_k]

    monkeypatch.setattr(character_retrieval, "_select_candidate_pool_exact", legacy)
    old = character_retrieval.retrieve_lsh_directed_neighbors(matrix, refs, 5)
    monkeypatch.setattr(character_retrieval, "_select_candidate_pool_exact", optimized)
    new = character_retrieval.retrieve_lsh_directed_neighbors(matrix, refs, 5)
    assert old.directed_neighbors == new.directed_neighbors
    assert _semantic_fingerprints(old.directed_neighbors, refs) == (
        _semantic_fingerprints(new.directed_neighbors, refs)
    )


def test_h14_no_approximate_or_third_party_selection():
    source = inspect.getsource(_select_candidate_pool_exact).casefold()
    assert "heap" not in source
    assert "partition" not in source
    assert "random" not in source


def test_h15_provider_surface_is_zero():
    assert "provider" not in inspect.getsource(character_retrieval).casefold()


def test_h16_no_configured_or_default_database_access():
    source = inspect.getsource(character_retrieval).casefold()
    assert "database_url" not in source
    assert "inventory_detector.db" not in source


def test_h17_deprecated_writes_remain_disabled():
    policy = pair_path_write_policy("group_first_primary", shadow_comparison_enabled=True)
    assert not policy.write_legacy_pairs
    assert not policy.write_g1_projection
    assert not policy.write_g2_v1_projection
    assert not policy.run_shadow_comparison


def test_h18_no_schema_migration_or_dependency_change():
    source = inspect.getsource(character_retrieval).casefold()
    assert "alembic" not in source
    assert "pip install" not in source
