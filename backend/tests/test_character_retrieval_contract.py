import numpy as np
import pandas as pd
from sklearn.preprocessing import normalize

from app.benchmarks.character_retrieval_contract import (
    run_character_contract_experiment,
    run_downstream_experiment,
    run_hybrid_tie_comparison,
    run_production_tie_experiment,
)
from app.core.config import Settings
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD, HybridCandidateRetriever,
    _deterministic_directed_neighbors, _deterministic_nearest_pairs,
)


def _matrix(rows):
    return normalize(np.asarray(rows, dtype=np.float32))


def _semantic_signature(matrix, refs, top_k=2):
    rows = _deterministic_nearest_pairs(matrix, top_k, refs)
    return tuple(
        (*sorted((refs[left], refs[right])), score, reciprocal)
        for left, right, score, reciprocal in rows
    )


def _configuration(**values):
    defaults = dict(
        llm_provider="none", llm_demo_enabled=False,
        hybrid_retrieval_enabled=True, hybrid_retrieval_min_score=40,
        hybrid_retrieval_lexical_top_k=2, hybrid_retrieval_vector_top_k=2,
        hybrid_retrieval_final_top_k=4, hybrid_retrieval_max_pairs_per_scan=20,
    )
    defaults.update(values)
    return Settings(**defaults)


def test_current_character_ties_are_input_order_dependent_but_repeatable():
    result = run_character_contract_experiment(64, seed=1101)
    assert result["repeated_equal"] is True
    assert result["block_size_equal"] is True
    assert result["anchors_with_kth_boundary_tie"] > 0
    assert result["input_order_pair_symmetric_difference"] > 0


def test_deterministic_tie_changes_only_exact_boundary_scores():
    result = run_character_contract_experiment(64, seed=1101)
    assert result["anchors_changed_by_deterministic_tie"] > 0
    assert result["anchors_with_unequal_score_membership_change"] == 0
    assert result["anchors_with_unequal_rounded_score_membership_change"] == 0
    assert result["deterministic_coverage"] == result["current_coverage"]


def test_sparse_character_experiment_is_exact_indexed_and_preserves_fixture_coverage():
    result = run_character_contract_experiment(64, seed=1101)
    metrics = result["sparse_metrics"]
    assert result["sparse_coverage"] == result["current_coverage"]
    assert metrics["zero_overlap_comparisons_avoided"] > 0
    assert metrics["exact_similarity_evaluation_count"] < 64 * 63
    assert metrics["posting_entry_count"] > 0
    assert metrics["max_posting_size"] > 0


def test_manageable_normal_pipeline_has_no_tie_or_sparse_safety_regression():
    results = run_downstream_experiment(64, seed=1101)
    current = results["HISTORICAL"]
    for name in ("DETERMINISTIC_TIE", "SPARSE_CHARACTER"):
        candidate = results[name]
        assert candidate["status"] == current["status"] == "COMPLETED"
        assert candidate["row_counts"] == current["row_counts"]
        assert candidate["safety"] == current["safety"]
        assert candidate["quality"] == current["quality"]
        assert candidate["complexity"] == current["complexity"]
    assert current["safety"]["provider_calls"] == 0


def test_t1_clear_unequal_scores_preserve_ordering():
    matrix = _matrix(((1, 0), (0.9, 0.1), (0.7, 0.3), (0, 1)))
    directed = _deterministic_directed_neighbors(matrix, 2, ("r0", "r3", "r2", "r1"))
    assert [target for target, _score in directed[0]] == [1, 2]
    assert directed[0][0][1] > directed[0][1][1]


def test_t2_exact_boundary_tie_uses_canonical_reference():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6)))
    directed = _deterministic_directed_neighbors(matrix, 1, ("anchor", "z-ref", "a-ref"))
    assert directed[0][0][0] == 2


def test_t3_tie_below_boundary_does_not_change_top_k():
    matrix = _matrix(((1, 0), (0.95, 0.05), (0.8, 0.2), (0.5, 0.5), (0.5, 0.5)))
    directed = _deterministic_directed_neighbors(
        matrix, 2, ("anchor", "r1", "r2", "a-below", "z-below")
    )
    assert [target for target, _score in directed[0]] == [1, 2]


def test_t4_self_exclusion_precedes_deterministic_ordering():
    matrix = _matrix(((1, 0), (1, 0), (1, 0)))
    directed = _deterministic_directed_neighbors(matrix, 1, ("a-self", "c-ref", "b-ref"))
    assert directed[0] == ((2, 1.0),)


def test_t5_duplicate_valued_records_remain_distinct():
    rows = _deterministic_nearest_pairs(
        _matrix(((1, 0), (1, 0))), 1, ("distinct-a", "distinct-b")
    )
    assert rows == [(0, 1, 100.0, True)]


def test_t6_reversed_input_preserves_semantic_neighbors():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1)))
    refs = np.asarray(("anchor", "z-ref", "a-ref", "other"), dtype=object)
    reverse = np.arange(len(refs))[::-1]
    assert _semantic_signature(matrix, refs) == _semantic_signature(
        matrix[reverse], refs[reverse]
    )


def test_t7_multiple_fixed_shuffles_preserve_semantic_neighbors():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1), (0.6, 0.8)))
    refs = np.asarray(tuple(f"ref-{index}" for index in range(5)), dtype=object)
    expected = _semantic_signature(matrix, refs)
    for seed in (3, 7, 19, 1101):
        order = np.random.default_rng(seed).permutation(len(refs))
        assert _semantic_signature(matrix[order], refs[order]) == expected


def test_t8_repeated_runs_have_identical_pairs_scores_reciprocity_and_order():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1)))
    refs = ("anchor", "z-ref", "a-ref", "other")
    assert _semantic_signature(matrix, refs) == _semantic_signature(matrix, refs)


def test_t9_historical_differences_are_exact_boundary_ties_only():
    result = run_production_tie_experiment(64, seed=1101)
    assert result["tie_substitutions"] > 0
    assert result["unequal_score_substitution_anchors"] == 0


def test_t10_reciprocal_reconstruction_is_deterministic():
    matrix = _matrix(((1, 0), (1, 0), (1, 0)))
    refs = np.asarray(("a", "b", "c"), dtype=object)
    expected = _semantic_signature(matrix, refs, top_k=1)
    assert ("a", "b", 100.0, True) in expected
    order = np.asarray((2, 0, 1))
    assert _semantic_signature(matrix[order], refs[order], top_k=1) == expected


def test_t11_final_proposal_cap_is_unchanged():
    data = pd.DataFrame([
        {
            "PART_NO": f"P-{index}", "DESCRIPTION": f"bearing motor {index}",
            "CONTRACT": "S1", "UNIT_MEAS": "EA",
            CANONICAL_RECORD_REF_FIELD: f"ref-{index:03d}",
        }
        for index in range(12)
    ])
    result = HybridCandidateRetriever(_configuration(
        hybrid_retrieval_max_pairs_per_scan=3,
        hybrid_retrieval_final_top_k=2,
    )).retrieve(data, "SAME_SITE_DUPLICATE")
    assert len(result.candidates) <= 3


def test_t12_non_character_channels_are_unchanged():
    data = pd.DataFrame([
        {
            "PART_NO": part, "DESCRIPTION": description, "CONTRACT": "S1",
            "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: f"ref-{index}",
        }
        for index, (part, description) in enumerate((
            ("A-6205", "Motor Bearing 6205"),
            ("B-6205", "Motor Bearing 6205"),
        ))
    ])
    result = HybridCandidateRetriever(_configuration(local_embedding_enabled=False)).retrieve(
        data, "SAME_SITE_DUPLICATE"
    )
    sources = set(result.candidates[0].evidence.retrieval_sources)
    assert {"EXACT_DESCRIPTION", "LEXICAL", "TECHNICAL_IDENTITY"} <= sources
    assert "CHAR_VECTOR" not in sources


def test_t13_64_record_gf1_through_gf6_is_safety_equivalent():
    results = run_downstream_experiment(64, seed=1101)
    historical = results["HISTORICAL"]
    deterministic = results["DETERMINISTIC_TIE"]
    assert deterministic["status"] == historical["status"] == "COMPLETED"
    assert deterministic["row_counts"] == historical["row_counts"]
    assert deterministic["safety"] == historical["safety"]
    assert deterministic["quality"] == historical["quality"]
    assert deterministic["complexity"] == historical["complexity"]


def test_t14_canonical_500_coverage_non_regresses_without_unequal_substitution():
    result = run_production_tie_experiment(500, seed=1101)
    fusion = run_hybrid_tie_comparison(500, seed=1101)
    assert result["unequal_score_substitution_anchors"] == 0
    assert result["deterministic_coverage"] == result["historical_coverage"]
    assert result["all_permutations_equal"] is True
    assert fusion["deterministic_coverage"] == fusion["historical_coverage"]
    assert fusion["deterministic_candidate_count"] == fusion["historical_candidate_count"]
    assert fusion["historical_provider_calls"] == fusion["deterministic_provider_calls"] == 0
