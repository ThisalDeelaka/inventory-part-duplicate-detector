import inspect
import json

import pytest
from scipy.sparse import csr_matrix

from app.benchmarks import lexical_crossover_decision as cross


def test_c1_uses_canonical_corpus_only():
    source = inspect.getsource(cross.run_isolated_strategy)
    assert "_inputs" in source and "truth" not in source


def test_c2_threshold_is_deterministic():
    rows = [
        cross.CrossoverObservation(25000, strategy, value)
        for strategy, values in ((cross.EXACT, (10, 12)), (cross.BOUNDED, (7, 8)))
        for value in values
    ]
    assert cross.select_activation_threshold(rows) == 25000
    assert cross.select_activation_threshold(list(reversed(rows))) == 25000


def test_c3_threshold_has_no_machine_load_input():
    assert tuple(inspect.signature(cross.select_activation_threshold).parameters) == (
        "observations", "advantage"
    )


def test_c4_insufficient_classification_is_deterministic():
    kwargs = dict(selected_features=0, candidate_count=0, skipped_for_budget=4,
                  feature_limit_exhausted=True, duplicate_collapse=True)
    assert cross.classify_insufficient_reason(**kwargs) == "NO_ELIGIBLE_BOUNDED_POSTING"


def test_c5_diagnostics_have_no_raw_record_data():
    result = cross.characterize_insufficient_anchors(64)
    rendered = json.dumps(result)
    assert all(value not in rendered for value in ("DESCRIPTION", "PART_NO", "record_ref"))


def test_c6_insufficient_counts_reconcile():
    result = cross.characterize_insufficient_anchors(64)
    distribution = result["candidate_count_distribution"]
    assert result["insufficient_anchor_count"] == sum(distribution.values())


def test_c7_exact_reference_subset_is_truthful():
    result = cross.characterize_insufficient_anchors(64, exact_reference=True)
    assert result["exact_reference_available"] is True
    assert result["insufficient_anchor_lexical_recall"] is None or 0 <= result["insufficient_anchor_lexical_recall"] <= 1


def test_c8_degraded_state_is_visible():
    result = cross.degraded_anchor_result({"insufficient_anchor_count": 3})
    assert result == {"status": "COMPLETED_DEGRADED", "reason": cross.INSUFFICIENT,
                      "affected_anchors": 3}


def test_c9_typed_failure_is_explicit():
    assert cross.typed_failure_result({"insufficient_anchor_count": 3})[
        "safe_failure_category"
    ] == cross.INSUFFICIENT


def test_c10_second_pass_is_hard_bounded():
    assert cross.second_pass_bound(anchors=10, visit_budget=8192) == {
        "maximum_posting_visits": 81920, "maximum_exact_reranks": 800
    }


def test_c11_no_unbounded_exact_fallback():
    source = inspect.getsource(cross.characterize_insufficient_anchors)
    assert "fallback" not in source and "n_jobs" not in source


def test_c12_provider_calls_are_zero():
    assert cross.characterize_insufficient_anchors(64)["provider_request_count"] == 0


def test_c13_isolated_diagnostics_do_not_open_database(monkeypatch):
    import sqlalchemy
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda *_a, **_k: (_ for _ in ()).throw(
        AssertionError("database opened")
    ))
    assert cross.characterize_insufficient_anchors(64)["records"] == 64


def test_c14_timeout_cannot_complete():
    result = cross.timeout_result(records=100000, strategy=cross.EXACT,
                                  timeout_seconds=120, wall_seconds=120.1,
                                  stage="INDEXED_QUERY_SCORING")
    assert result["status"] == "TIMED_OUT"
    assert result["active_stage"] == "INDEXED_QUERY_SCORING"


def test_op_fixed_second_pass_processes_only_insufficient_anchors(monkeypatch):
    primary = cross.RarityConfiguration(
        "R2", "P1_RAREST", 5, 1, visit_budget=4, batch_size=2
    )
    second = cross.RarityConfiguration(
        "R2", "P1_RAREST", 5, 1, visit_budget=10, batch_size=2
    )
    monkeypatch.setattr(cross, "PRIMARY", primary)
    monkeypatch.setattr(cross, "SECOND_PASS", second)
    matrix = csr_matrix([[1.0]] * 6)
    refs = tuple(f"ref-{index}" for index in range(6))

    result, diagnostics = cross.retrieve_selected_bounded_lexical(
        matrix, refs, 2
    )

    assert diagnostics["primary_insufficient"] == 6
    assert diagnostics["second_pass_recovered"] == 6
    assert diagnostics["remaining_insufficient"] == 0
    assert diagnostics["second_pass_posting_visits"] == 36
    assert diagnostics["second_pass_exact_reranks"] == 30
    assert all(len(rows) == 2 for rows in result.directed_neighbors.values())
    assert result.metrics.strategy == (
        "BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS"
    )


def test_op_selected_policy_has_no_machine_load_input():
    assert tuple(inspect.signature(
        cross.retrieve_selected_bounded_lexical
    ).parameters) == ("matrix", "refs", "top_k")


def test_op_cache_operation_uses_disposable_chunked_database():
    result = cross.run_cache_load_operation(901)
    assert result["status"] == "COMPLETED"
    assert result["database_is_disposable"] is True
    assert result["sql_statement_count"] == result["number_of_batches"] == 2
    assert result["parameters_per_statement_max"] == 902
    assert result["last_statement_parameter_count"] == 3
    assert result["commit_count"] == result["provider_request_count"] == 0
    assert result["raw_sql_parameters_captured"] is False
