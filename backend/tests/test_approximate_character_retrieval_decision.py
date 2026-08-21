import inspect

import numpy as np
import pytest
from sklearn.preprocessing import normalize

from app.benchmarks import approximate_character_retrieval as decision
from app.benchmarks.character_retrieval_contract import _coverage, _pairs
from app.services.hybrid_retrieval import _deterministic_directed_neighbors


def _matrix(rows):
    values = np.zeros((len(rows), 384), dtype=np.float32)
    values[:, :len(rows[0])] = np.asarray(rows, dtype=np.float32)
    return normalize(values)


def _semantic_signature(result, refs):
    return tuple(sorted(
        (
            refs[source], refs[target], round(score * 100, 2), rank,
        )
        for source, neighbors in result.directed_neighbors.items()
        for rank, (target, score) in enumerate(neighbors, 1)
    ))


@pytest.fixture(scope="module")
def canonical_500():
    corpus, matrix, refs = decision.corpus_vectors(500)
    exact = _deterministic_directed_neighbors(matrix, 5, refs)
    result = decision.run_lsh_exact_rerank(
        matrix, refs, decision.LshConfiguration(candidate_pool_k=320)
    )
    return corpus, matrix, refs, exact, result


def test_a1_exact_deterministic_reference_fixture_is_stable():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1)))
    refs = ("anchor", "z-ref", "a-ref", "other")
    assert _deterministic_directed_neighbors(
        matrix, 2, refs
    ) == _deterministic_directed_neighbors(matrix, 2, refs)


def test_a2_lsh_repeated_runs_are_deterministic():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1)))
    refs = ("anchor", "z-ref", "a-ref", "other")
    configuration = decision.LshConfiguration(
        table_count=4, bits_per_table=6, candidate_pool_k=3, final_top_k=2
    )
    first = decision.run_lsh_exact_rerank(matrix, refs, configuration)
    second = decision.run_lsh_exact_rerank(matrix, refs, configuration)
    assert first.status == second.status == decision.ExperimentStatus.COMPLETED
    assert first.result_fingerprint == second.result_fingerprint
    assert first.directed_neighbors == second.directed_neighbors


def test_a3_lsh_shuffled_input_is_semantically_deterministic():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1), (0.6, 0.8)))
    refs = np.asarray(("anchor", "z-ref", "a-ref", "other", "near"), dtype=object)
    configuration = decision.LshConfiguration(
        table_count=4, bits_per_table=6, candidate_pool_k=4, final_top_k=2
    )
    expected = decision.run_lsh_exact_rerank(matrix, refs, configuration)
    for order in (
        np.arange(len(refs))[::-1],
        np.random.default_rng(7).permutation(len(refs)),
        np.random.default_rng(19).permutation(len(refs)),
        np.random.default_rng(1101).permutation(len(refs)),
    ):
        actual = decision.run_lsh_exact_rerank(matrix[order], refs[order], configuration)
        assert _semantic_signature(actual, refs[order]) == _semantic_signature(expected, refs)
        assert actual.result_fingerprint == expected.result_fingerprint


def test_a4_exact_rerank_uses_canonical_order_for_equal_cosine():
    matrix = _matrix(((1, 0), (1, 0), (1, 0), (0, 1)))
    refs = ("anchor", "z-ref", "a-ref", "other")
    result = decision.run_lsh_exact_rerank(
        matrix, refs,
        decision.LshConfiguration(
            table_count=4, bits_per_table=6, candidate_pool_k=3, final_top_k=1
        ),
    )
    assert result.directed_neighbors[0][0] == (2, 1.0)


def test_a5_candidate_pool_cannot_be_below_final_top_k():
    with pytest.raises(ValueError, match="cannot be below"):
        decision.LshConfiguration(candidate_pool_k=4, final_top_k=5).validate()


def test_a6_exact_rerank_uses_current_384_bin_cosine():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.6, 0.8)))
    result = decision.run_lsh_exact_rerank(
        matrix, ("anchor", "b", "c"),
        decision.LshConfiguration(
            table_count=4, bits_per_table=6, candidate_pool_k=2, final_top_k=2
        ),
    )
    assert matrix.shape[1] == 384
    assert [score for _target, score in result.directed_neighbors[0]] == pytest.approx(
        sorted((float(matrix[1] @ matrix[0]), float(matrix[2] @ matrix[0])), reverse=True)
    )


def test_a7_lsh_native_order_or_score_is_never_exposed():
    source = inspect.getsource(decision.query_lsh_exact_rerank)
    assert "exact_scores" in source
    assert "-exact_scores" in source
    assert "approximate_matches" in source
    assert "directed_stable[anchor]" in source


def test_a8_protected_conflict_coverage_does_not_regress(canonical_500):
    corpus, _matrix, _refs, exact, result = canonical_500
    exact_coverage = _coverage(_pairs(exact), corpus.truth)
    approximate = _coverage(_pairs(result.directed_neighbors), corpus.truth)
    assert approximate["protected_conflicts"] == exact_coverage["protected_conflicts"]


def test_a9_cross_site_coverage_does_not_regress(canonical_500):
    corpus, _matrix, _refs, exact, result = canonical_500
    exact_coverage = _coverage(_pairs(exact), corpus.truth)
    approximate = _coverage(_pairs(result.directed_neighbors), corpus.truth)
    assert approximate["cross_site_S5"] == exact_coverage["cross_site_S5"]


def test_a10_bridge_coverage_does_not_regress(canonical_500):
    corpus, _matrix, _refs, exact, result = canonical_500
    exact_coverage = _coverage(_pairs(exact), corpus.truth)
    approximate = _coverage(_pairs(result.directed_neighbors), corpus.truth)
    assert approximate["bridge_S7"] == exact_coverage["bridge_S7"]


def test_a11_benchmark_truth_is_not_a_retrieval_input():
    assert "truth" not in inspect.signature(decision.run_lsh_exact_rerank).parameters
    core_source = inspect.getsource(decision.run_lsh_exact_rerank)
    core_source += inspect.getsource(decision.query_lsh_exact_rerank)
    assert "truth" not in core_source


def test_a12_provider_calls_are_zero(canonical_500):
    assert canonical_500[-1].provider_request_count == 0


def test_a13_prototype_uses_no_database_or_default_database():
    source = inspect.getsource(decision)
    assert "app.db" not in source
    assert "sqlite" not in source.casefold()
    assert "inventory_detector.db" not in source


def test_a14_interrupted_prototype_cannot_report_completed():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.6, 0.8), (0, 1)))
    result = decision.run_lsh_exact_rerank(
        matrix, ("a", "b", "c", "d"),
        decision.LshConfiguration(
            table_count=4, bits_per_table=6, candidate_pool_k=3, final_top_k=2
        ),
        interrupt_after_anchors=2,
    )
    assert result.status == decision.ExperimentStatus.INTERRUPTED
    assert result.directed_neighbors == {}
    assert result.result_fingerprint is None


def test_a15_algorithm_fingerprint_contains_every_required_parameter():
    payload = decision._configuration_payload(decision.LshConfiguration())
    assert {
        "algorithm_contract_version", "ann_backend_name", "ann_backend_version",
        "vector_representation_version", "seed", "build_parameters",
        "search_parameters", "exact_rerank_version", "top_k",
    } <= payload.keys()
    assert payload["search_parameters"]["candidate_pool_k"] == 80


def test_a16_unavailable_or_unsupported_ann_backend_fails_explicitly():
    inventory = decision.ann_backend_inventory()
    for backend in ("hnswlib", "faiss"):
        if not inventory[backend]["available"]:
            with pytest.raises(decision.UnavailableAnnBackendError, match="unavailable"):
                decision.require_ann_backend(backend)
    with pytest.raises(decision.UnavailableAnnBackendError, match="unsupported"):
        decision.require_ann_backend("incidental-fallback")
