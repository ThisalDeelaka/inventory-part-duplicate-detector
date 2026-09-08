import inspect

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from sklearn.preprocessing import normalize

from app.benchmarks import lexical_architecture_decision as decision
from app.services.hybrid_retrieval import _deterministic_lexical_directed_neighbors
from app.services.lexical_retrieval import retrieve_exact_indexed_lexical_neighbors


def _fixture():
    matrix = normalize(csr_matrix(np.asarray((
        (1.0, 0.8, 0.0, 0.1),
        (0.9, 0.7, 0.0, 0.2),
        (0.8, 0.6, 0.2, 0.0),
        (0.0, 0.1, 0.9, 0.8),
        (0.1, 0.0, 0.8, 0.9),
        (0.6, 0.5, 0.4, 0.3),
    ))))
    return matrix, np.asarray(("r-f", "r-a", "r-e", "r-b", "r-d", "r-c"), dtype=object)


def _semantic(result, refs):
    return tuple(sorted(
        (refs[source], refs[target], score)
        for source, neighbors in result.directed_neighbors.items()
        for target, score in neighbors
    ))


@pytest.fixture(scope="module")
def b500():
    return decision.evaluate_configuration(
        500, "B", decision.HighInformationConfiguration(16, 160)
    )


def test_a1_v4_exact_reference_remains_unchanged():
    matrix, refs = _fixture()
    assert retrieve_exact_indexed_lexical_neighbors(matrix, refs, 3).directed_neighbors == (
        _deterministic_lexical_directed_neighbors(matrix, 3, refs)
    )


def test_a2_truth_is_not_supplied_to_candidate_retrieval():
    for function in (
        decision.retrieve_high_information_candidates,
        decision.retrieve_sparse_simhash_candidates,
    ):
        source = inspect.getsource(function)
        assert "truth" not in source
        assert tuple(inspect.signature(function).parameters) == (
            "matrix", "refs", "top_k", "configuration"
        )


@pytest.mark.parametrize("architecture,configuration", [
    ("B", decision.HighInformationConfiguration(3, 5)),
    ("C", decision.SparseSimHashConfiguration(4, 4, 1, 5)),
])
def test_a3_candidate_generation_is_repeatable(architecture, configuration):
    matrix, refs = _fixture()
    retrieve = (
        decision.retrieve_high_information_candidates if architecture == "B"
        else decision.retrieve_sparse_simhash_candidates
    )
    first, second = retrieve(matrix, refs, 3, configuration), retrieve(matrix, refs, 3, configuration)
    assert first.candidate_generation_fingerprint == second.candidate_generation_fingerprint
    assert first.directed_neighbors == second.directed_neighbors


@pytest.mark.parametrize("architecture,configuration", [
    ("B", decision.HighInformationConfiguration(3, 5)),
    ("C", decision.SparseSimHashConfiguration(4, 4, 1, 5)),
])
def test_a4_reverse_and_fixed_shuffles_preserve_semantics(architecture, configuration):
    matrix, refs = _fixture()
    retrieve = (
        decision.retrieve_high_information_candidates if architecture == "B"
        else decision.retrieve_sparse_simhash_candidates
    )
    expected = retrieve(matrix, refs, 3, configuration)
    expected_semantic = _semantic(expected, refs)
    for order in [np.arange(len(refs))[::-1]] + [
        np.random.default_rng(seed).permutation(len(refs)) for seed in (7, 19, 1101)
    ]:
        current = retrieve(matrix[order], refs[order], 3, configuration)
        assert current.candidate_generation_fingerprint == expected.candidate_generation_fingerprint
        assert _semantic(current, refs[order]) == expected_semantic


def test_a5_admitted_candidates_receive_exact_full_cosine_scores():
    matrix, refs = _fixture()
    result = decision.retrieve_high_information_candidates(
        matrix, refs, 3, decision.HighInformationConfiguration(1, 5)
    )
    for source, neighbors in result.directed_neighbors.items():
        for target, score in neighbors:
            assert score == pytest.approx(float(matrix[source].multiply(matrix[target]).sum()), abs=1e-12)


def test_a6_exact_rerank_uses_canonical_tie_order():
    matrix = normalize(csr_matrix(np.asarray(((1, 0), (1, 0), (1, 0)), dtype=float)))
    refs = np.asarray(("anchor", "z-ref", "a-ref"), dtype=object)
    result = decision.retrieve_high_information_candidates(
        matrix, refs, 1, decision.HighInformationConfiguration(1, 2)
    )
    assert refs[result.directed_neighbors[0][0][0]] == "a-ref"


@pytest.mark.parametrize("configuration", [
    decision.HighInformationConfiguration(2, 2),
    decision.SparseSimHashConfiguration(2, 4, 1, 2),
])
def test_a7_candidate_pool_must_cover_top_k(configuration):
    with pytest.raises(ValueError):
        configuration.validate(3)


def test_a8_simhash_score_never_becomes_final_lexical_score():
    matrix, refs = _fixture()
    result = decision.retrieve_sparse_simhash_candidates(
        matrix, refs, 3, decision.SparseSimHashConfiguration(4, 4, 1, 5)
    )
    for source, neighbors in result.directed_neighbors.items():
        for target, score in neighbors:
            assert score == pytest.approx(float(matrix[source].multiply(matrix[target]).sum()), abs=1e-12)


def test_a9_protected_conflict_coverage_is_measured_without_candidate_loss(b500):
    assert b500["coverage"]["protected_conflicts"] == [31, 31]


def test_a10_truth_bridge_and_cross_site_coverage_is_measured(b500):
    assert b500["coverage"]["true_sets"] == [60, 60]
    assert b500["coverage"]["bridge_S7"] == [21, 21]
    assert b500["coverage"]["cross_site_S5"] == [20, 20]


def test_a11_experiment_is_provider_free(b500):
    assert b500["provider_request_count"] == 0
    assert b500["metrics"]["provider_request_count"] == 0


def test_a12_isolated_benchmark_does_not_open_database(monkeypatch):
    import sqlalchemy

    monkeypatch.setattr(
        sqlalchemy, "create_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("database opened")),
    )
    result = decision.run_isolated_viability(
        64, "B", decision.HighInformationConfiguration(8, 40)
    )
    assert result["status"] == "COMPLETED"


def test_a13_timeout_result_cannot_report_completed():
    result = decision.architecture_timeout_result(
        records=100000,
        architecture="B",
        configuration=decision.HighInformationConfiguration(16, 160),
        timeout_seconds=120.0,
        wall_seconds=120.1,
    )
    assert result["status"] == "TIMED_OUT"
    assert result["safe_failure_category"] == "ARCHITECTURE_BENCHMARK_TIMEOUT"


@pytest.mark.parametrize("left,right", [
    (decision.HighInformationConfiguration(16, 160), decision.HighInformationConfiguration(8, 160)),
    (decision.HighInformationConfiguration(16, 160), decision.HighInformationConfiguration(16, 320)),
    (
        decision.SparseSimHashConfiguration(8, 12, 2, 160, seed=1101),
        decision.SparseSimHashConfiguration(8, 12, 2, 160, seed=19),
    ),
])
def test_a14_all_candidate_parameters_affect_fingerprint(left, right):
    matrix, refs = _fixture()
    retrieve = (
        decision.retrieve_high_information_candidates
        if isinstance(left, decision.HighInformationConfiguration)
        else decision.retrieve_sparse_simhash_candidates
    )
    assert retrieve(matrix, refs, 3, left).metrics.configuration_fingerprint != (
        retrieve(matrix, refs, 3, right).metrics.configuration_fingerprint
    )
