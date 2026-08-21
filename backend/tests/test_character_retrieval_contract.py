from app.benchmarks.character_retrieval_contract import (
    run_character_contract_experiment,
    run_downstream_experiment,
)


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
    current = results["CURRENT"]
    for name in ("DETERMINISTIC_TIE", "SPARSE_CHARACTER"):
        candidate = results[name]
        assert candidate["status"] == current["status"] == "COMPLETED"
        assert candidate["row_counts"] == current["row_counts"]
        assert candidate["safety"] == current["safety"]
        assert candidate["quality"] == current["quality"]
        assert candidate["complexity"] == current["complexity"]
    assert current["safety"]["provider_calls"] == 0
