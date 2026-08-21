"""GF-11B production fixed-seed LSH acceptance tests P1-P20."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.preprocessing import normalize

from app.core.config import Settings
from app.orchestration.pair_path_deprecation import pair_path_write_policy
from app.services import hybrid_retrieval
from app.services.character_retrieval import (
    ACTIVATION_THRESHOLD,
    PRODUCTION_LSH_CONFIGURATION,
    CharacterLshConfiguration,
    CharacterRetrievalError,
    CharacterRetrievalFailureCategory,
    CharacterRetrievalStrategy,
    character_retrieval_contract_fingerprint,
    generate_lsh_hyperplanes,
    retrieve_lsh_directed_neighbors,
    select_character_retrieval_strategy,
)
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    _directed_neighbors_to_pairs,
)


def _vectors(count=24, seed=1101):
    values = np.random.default_rng(seed).random((count, 384), dtype=np.float32)
    return normalize(values).astype(np.float32)


def _refs(count):
    return np.asarray([f"record-ref-{index:05d}" for index in range(count)], dtype=object)


def _test_configuration(count=24):
    return CharacterLshConfiguration(
        table_count=4, bits_per_table=2, probe_radius=2,
        candidate_pool_k=count - 1,
    )


def _semantic(result, refs):
    return tuple(sorted(
        (str(refs[source]), str(refs[target]), round(score, 7))
        for source, neighbors in result.directed_neighbors.items()
        for target, score in neighbors
    ))


def test_p1_1999_selects_exact():
    assert ACTIVATION_THRESHOLD == 2_000
    assert select_character_retrieval_strategy(1_999) == CharacterRetrievalStrategy.EXACT


def test_p2_2000_selects_lsh():
    assert select_character_retrieval_strategy(2_000) == (
        CharacterRetrievalStrategy.FIXED_SEED_LSH_EXACT_RERANK
    )


def test_p3_strategy_selection_is_input_order_independent():
    assert select_character_retrieval_strategy(2_000) == select_character_retrieval_strategy(
        len(tuple(reversed(range(2_000))))
    )


def test_p4_hyperplanes_are_deterministic_for_contract_and_seed():
    first = generate_lsh_hyperplanes()
    second = generate_lsh_hyperplanes()
    assert np.array_equal(first, second)


def test_p5_fingerprint_changes_for_an_approved_parameter_change():
    base = character_retrieval_contract_fingerprint(2_000, 5)
    changed = character_retrieval_contract_fingerprint(
        2_000, 5, replace(PRODUCTION_LSH_CONFIGURATION, seed=1102)
    )
    assert base != changed


def test_p6_candidate_pool_must_cover_final_top_k():
    with pytest.raises(CharacterRetrievalError) as caught:
        CharacterLshConfiguration(candidate_pool_k=4).validate(5)
    assert caught.value.safe_category == "LSH_CONFIGURATION_INVALID"


def test_p7_repeated_lsh_runs_are_semantically_identical():
    matrix, refs, config = _vectors(), _refs(24), _test_configuration()
    first = retrieve_lsh_directed_neighbors(matrix, refs, 3, config)
    second = retrieve_lsh_directed_neighbors(matrix, refs, 3, config)
    assert _semantic(first, refs) == _semantic(second, refs)


def test_p8_reversed_input_is_semantically_identical():
    matrix, refs, config = _vectors(), _refs(24), _test_configuration()
    expected = _semantic(retrieve_lsh_directed_neighbors(matrix, refs, 3, config), refs)
    order = np.arange(len(refs))[::-1]
    actual = retrieve_lsh_directed_neighbors(matrix[order], refs[order], 3, config)
    assert _semantic(actual, refs[order]) == expected


def test_p9_fixed_shuffles_are_semantically_identical():
    matrix, refs, config = _vectors(), _refs(24), _test_configuration()
    expected = _semantic(retrieve_lsh_directed_neighbors(matrix, refs, 3, config), refs)
    for seed in (7, 19, 1101):
        order = np.random.default_rng(seed).permutation(len(refs))
        actual = retrieve_lsh_directed_neighbors(matrix[order], refs[order], 3, config)
        assert _semantic(actual, refs[order]) == expected


def test_p10_exact_rerank_uses_current_cosine():
    matrix, refs, config = _vectors(12), _refs(12), _test_configuration(12)
    result = retrieve_lsh_directed_neighbors(matrix, refs, 3, config)
    for source, neighbors in result.directed_neighbors.items():
        for target, score in neighbors:
            assert score == pytest.approx(float(matrix[source] @ matrix[target]), abs=1e-6)


def test_p11_exact_tie_uses_record_ref_key():
    matrix = np.zeros((4, 384), dtype=np.float32)
    matrix[:, :2] = normalize(np.asarray(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1))))
    refs = np.asarray(("anchor", "z-ref", "a-ref", "other"), dtype=object)
    config = _test_configuration(4)
    result = retrieve_lsh_directed_neighbors(matrix, refs, 1, config)
    assert refs[result.directed_neighbors[0][0][0]] == "a-ref"


def test_p12_lsh_native_values_never_become_final_scores():
    matrix, refs, config = _vectors(12), _refs(12), _test_configuration(12)
    result = retrieve_lsh_directed_neighbors(matrix, refs, 3, config)
    scores = [score for neighbors in result.directed_neighbors.values() for _, score in neighbors]
    assert scores and all(0.0 < score <= 1.0 for score in scores)
    assert any(not float(score).is_integer() for score in scores)


def test_p13_reciprocity_reconstruction_remains_shared():
    directed = {0: ((1, 0.9),), 1: ((0, 0.8),), 2: ((0, 0.7),)}
    pairs = _directed_neighbors_to_pairs(directed, ("a", "b", "c"))
    assert pairs == [(0, 1, 90.0, True), (0, 2, 70.0, False)]


def _settings(**updates):
    values = dict(
        llm_provider="none", llm_demo_enabled=False,
        hybrid_retrieval_enabled=True, hybrid_retrieval_lexical_top_k=2,
        hybrid_retrieval_vector_top_k=2, hybrid_retrieval_final_top_k=2,
        hybrid_retrieval_max_pairs_per_scan=3,
    )
    values.update(updates)
    return Settings(**values)


def _frame(count=8):
    return pd.DataFrame([{
        "PART_NO": f"P-{index}", "DESCRIPTION": f"motor bearing {index}",
        "CONTRACT": "S1", "UNIT_MEAS": "EA",
        CANONICAL_RECORD_REF_FIELD: f"ref-{index:04d}",
    } for index in range(count)])


def test_p14_hybrid_final_cap_is_unchanged():
    result = HybridCandidateRetriever(_settings()).retrieve(_frame(), "SAME_SITE_DUPLICATE")
    assert len(result.candidates) <= 3


def test_p15_non_character_channels_remain_available_without_char_vector():
    data = _frame(2)
    data["DESCRIPTION"] = "motor bearing 6205"
    result = HybridCandidateRetriever(_settings(local_embedding_enabled=False)).retrieve(
        data, "SAME_SITE_DUPLICATE"
    )
    sources = set(result.candidates[0].evidence.retrieval_sources)
    assert "LEXICAL" in sources
    assert "CHAR_VECTOR" not in sources


def test_p16_large_strategy_failure_never_calls_exact_fallback(monkeypatch):
    failure = CharacterRetrievalError(
        CharacterRetrievalFailureCategory.LSH_QUERY_FAILED, "safe failure"
    )
    monkeypatch.setattr(
        hybrid_retrieval, "select_character_retrieval_strategy",
        lambda _count: CharacterRetrievalStrategy.FIXED_SEED_LSH_EXACT_RERANK,
    )
    monkeypatch.setattr(
        hybrid_retrieval, "retrieve_lsh_directed_neighbors",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(
        hybrid_retrieval, "_deterministic_directed_neighbors",
        lambda *_args, **_kwargs: pytest.fail("exact fallback was invoked"),
    )
    with pytest.raises(CharacterRetrievalError) as caught:
        HybridCandidateRetriever(_settings()).retrieve(_frame(6), "SAME_SITE_DUPLICATE")
    assert caught.value.safe_category == "LSH_QUERY_FAILED"


def test_p17_insufficient_viable_pool_fails_typed():
    matrix = np.eye(8, 384, dtype=np.float32)
    with pytest.raises(CharacterRetrievalError) as caught:
        retrieve_lsh_directed_neighbors(matrix, _refs(8), 3, _test_configuration(8))
    assert caught.value.safe_category == "LSH_CANDIDATE_POOL_INSUFFICIENT"


def test_p18_production_lsh_has_no_benchmark_truth_dependency():
    source = Path(__file__).parents[1].joinpath(
        "app", "services", "character_retrieval.py"
    ).read_text(encoding="utf-8").casefold()
    forbidden = (
        "truth_set_id", "scenario family", "protected-conflict benchmark",
        "cross-site truth", "bridge truth", "benchmark quality",
    )
    assert not any(value in source for value in forbidden)
    assert "app.benchmarks" not in source


def test_p19_policy_v2_disables_pair_g1_v1_and_shadow_writes():
    policy = pair_path_write_policy("group_first_primary", shadow_comparison_enabled=True)
    assert policy.policy_version == "group-first-orchestration-policy-v2"
    assert not policy.write_legacy_pairs
    assert not policy.write_g1_projection
    assert not policy.write_g2_v1_projection
    assert not policy.run_shadow_comparison


def test_p20_production_character_path_has_zero_provider_surface():
    source = Path(__file__).parents[1].joinpath(
        "app", "services", "character_retrieval.py"
    ).read_text(encoding="utf-8").casefold()
    assert "provider" not in source
    result = HybridCandidateRetriever(_settings()).retrieve(_frame(), "SAME_SITE_DUPLICATE")
    assert result.metrics.provider_request_count == 0
