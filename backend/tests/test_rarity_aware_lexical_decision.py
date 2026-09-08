import inspect

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from sklearn.preprocessing import normalize

from app.benchmarks import rarity_aware_lexical_decision as rarity


def _fixture():
    matrix = normalize(csr_matrix(np.asarray((
        (1.0, .8, 0, .1), (.9, .7, 0, .2), (.8, .6, .2, 0),
        (0, .1, .9, .8), (.1, 0, .8, .9), (.6, .5, .4, .3),
    ))))
    return matrix, np.asarray(("r-f", "r-a", "r-e", "r-b", "r-d", "r-c"), dtype=object)


def _r1(**overrides):
    values = dict(formulation="R1", ranking_policy="P1_RAREST", candidate_pool=5,
                  feature_limit=2, df_cap=4)
    values.update(overrides)
    return rarity.RarityConfiguration(**values)


def _r2(**overrides):
    values = dict(formulation="R2", ranking_policy="P1_RAREST", candidate_pool=5,
                  feature_limit=3, visit_budget=8)
    values.update(overrides)
    return rarity.RarityConfiguration(**values)


@pytest.mark.parametrize("configuration", [_r1(), _r2()])
def test_rar1_bounded_posting_work(configuration):
    matrix, refs = _fixture()
    result = rarity.retrieve_bounded_rarity_candidates(matrix, refs, 3, configuration)
    bound = (configuration.feature_limit * configuration.df_cap
             if configuration.formulation == "R1" else configuration.visit_budget)
    assert result.metrics.raw_posting_visits <= len(refs) * bound


def test_rar2_postings_are_never_partially_truncated():
    matrix = normalize(csr_matrix(np.ones((6, 1))))
    refs = tuple(f"r-{i}" for i in range(6))
    result = rarity.retrieve_bounded_rarity_candidates(matrix, refs, 1, _r2(visit_budget=5))
    assert result.metrics.raw_posting_visits == 0
    assert result.metrics.postings_traversed == 0


@pytest.mark.parametrize("policy", sorted(rarity.RANKING_POLICIES))
def test_rar3_feature_ranking_is_deterministic(policy):
    features = np.asarray((9, 2, 5))
    weights = np.asarray((.4, .4, .8))
    sizes = np.arange(10) + 1
    first = rarity._rank_features(features, weights, sizes, policy)
    second = rarity._rank_features(features, weights, sizes, policy)
    assert all(np.array_equal(a, b) for a, b in zip(first, second))


def test_rar4_candidate_proxy_is_deterministic():
    matrix, refs = _fixture()
    first = rarity.retrieve_bounded_rarity_candidates(matrix, refs, 3, _r1())
    second = rarity.retrieve_bounded_rarity_candidates(matrix, refs, 3, _r1())
    assert first.candidate_generation_fingerprint == second.candidate_generation_fingerprint


def test_rar5_final_score_is_exact_full_cosine():
    matrix, refs = _fixture()
    result = rarity.retrieve_bounded_rarity_candidates(matrix, refs, 3, _r1())
    for source, rows in result.directed_neighbors.items():
        for target, score in rows:
            assert score == pytest.approx(float(matrix[source].multiply(matrix[target]).sum()), abs=1e-12)


def test_rar6_canonical_tie_order_is_preserved():
    matrix = normalize(csr_matrix(np.asarray(((1, 0), (1, 0), (1, 0)), dtype=float)))
    refs = np.asarray(("anchor", "z-ref", "a-ref"), dtype=object)
    result = rarity.retrieve_bounded_rarity_candidates(
        matrix, refs, 1, _r1(candidate_pool=2, feature_limit=1, df_cap=3)
    )
    assert refs[result.directed_neighbors[0][0][0]] == "a-ref"


def test_rar7_candidate_pool_must_cover_top_k():
    with pytest.raises(ValueError, match="at least"):
        _r1(candidate_pool=2).validate(3)


def test_rar8_reverse_and_shuffle_determinism():
    result = rarity.run_determinism(64, _r2(candidate_pool=20, feature_limit=8, visit_budget=256))
    assert all(item["candidate_fingerprint_equal"] and item["semantic_equal"] for item in result.values())


def test_rar9_truth_is_absent_from_retrieval():
    source = inspect.getsource(rarity.retrieve_bounded_rarity_candidates)
    assert "truth" not in source and "corpus" not in source


def test_rar10_partial_support_never_becomes_final_score():
    source = inspect.getsource(rarity.retrieve_bounded_rarity_candidates)
    assert "_exact_rerank_batch" in source
    assert rarity.PARTIAL_SUPPORT != rarity.EXACT_RERANK_VERSION


def test_rar11_insufficient_pool_is_visible():
    matrix = normalize(csr_matrix(np.eye(4)))
    result = rarity.retrieve_bounded_rarity_candidates(
        matrix, tuple(f"r-{i}" for i in range(4)), 2, _r1(candidate_pool=2, feature_limit=1, df_cap=1)
    )
    assert result.metrics.anchors_with_insufficient_candidates == 4


def test_rar12_provider_calls_are_zero():
    matrix, refs = _fixture()
    result = rarity.retrieve_bounded_rarity_candidates(matrix, refs, 3, _r1())
    assert result.metrics.provider_request_count == 0


def test_rar13_isolated_benchmark_does_not_open_database(monkeypatch):
    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("database opened")
    ))
    result = rarity.run_isolated(64, _r2(candidate_pool=20, feature_limit=8, visit_budget=256))
    assert result["status"] == "COMPLETED"


def test_rar14_timeout_cannot_report_completed():
    result = rarity.timeout_result(
        records=100000, configuration=_r2(), timeout_seconds=120, wall_seconds=120.1
    )
    assert result["status"] == "TIMED_OUT"
    assert result["safe_failure_category"] == "RARITY_AWARE_BENCHMARK_TIMEOUT"
