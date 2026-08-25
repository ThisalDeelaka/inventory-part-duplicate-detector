import inspect
import json
import time
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.config import Settings
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    _deterministic_lexical_directed_neighbors,
    _directed_neighbors_to_pairs,
)
from app.services.lexical_retrieval import (
    BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS,
    EXACT_INDEXED_V4,
    LEXICAL_RETRIEVAL_STRATEGY,
    PRIMARY_BOUNDED_CONFIGURATION,
    SECOND_PASS_BOUNDED_CONFIGURATION,
    BoundedLexicalConfiguration,
    LexicalRetrievalError,
    lexical_retrieval_contract_fingerprint,
    lexical_strategy_contract_fingerprint,
    lexical_strategy_contract_payload,
    retrieve_bounded_lexical_neighbors,
    retrieve_exact_indexed_lexical_neighbors,
    retrieve_production_lexical_neighbors,
    select_lexical_strategy,
)
from app.benchmarks import exact_indexed_lexical as query_benchmark


def _matrix(texts):
    return TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1
    ).fit_transform(texts)


def _compare(texts, refs, top_k=2):
    matrix = _matrix(texts)
    reference = _deterministic_lexical_directed_neighbors(matrix, top_k, refs)
    indexed = retrieve_exact_indexed_lexical_neighbors(matrix, refs, top_k)
    assert indexed.directed_neighbors == reference
    assert _directed_neighbors_to_pairs(indexed.directed_neighbors, refs) == (
        _directed_neighbors_to_pairs(reference, refs)
    )
    return indexed


def test_lx1_simple_fixture_matches_v4_reference_exactly():
    _compare(("alpha pump 100", "alpha pump 101", "unrelated cable"), ("a", "b", "c"))


def test_lx2_lx10_no_overlap_and_zero_pairs_match_reference():
    result = _compare(("aaa", "zzz"), ("a", "z"), top_k=5)
    assert result.directed_neighbors == {0: (), 1: ()}
    assert result.metrics.exact_score_evaluations == 0
    assert result.metrics.zero_overlap_comparisons_avoided == 2


def test_lx3_fewer_than_top_k_positive_neighbors_match():
    result = _compare(("alpha pump", "alpha motor", "zzz"), ("a", "b", "c"), top_k=5)
    assert len(result.directed_neighbors[0]) == 1


def test_lx4_lx5_lx6_high_overlap_scores_and_membership_are_exact():
    texts = tuple(f"common turbine bearing model {index % 4}" for index in range(20))
    result = _compare(texts, tuple(f"r-{index:02d}" for index in range(20)), top_k=5)
    assert result.metrics.exact_score_evaluations > 0
    assert result.metrics.max_anchor_candidate_union == 19


def test_lx7_exact_tie_uses_canonical_reference():
    result = _compare(("same value", "same value", "same value"), ("b", "z", "a"), top_k=1)
    assert result.directed_neighbors[0][0][0] == 2


def test_lx8_self_exclusion_and_lx9_rounding_reconstruction_match():
    result = _compare(("same value", "same value", "same values"), ("a", "b", "c"), top_k=1)
    assert all(source != target for source, rows in result.directed_neighbors.items() for target, _ in rows)
    assert _directed_neighbors_to_pairs(result.directed_neighbors, ("a", "b", "c"))[0][2] == 100.0


def test_lx11_reciprocity_matches_reference():
    result = _compare(("same value", "same value", "other value"), ("a", "b", "c"), top_k=1)
    assert _directed_neighbors_to_pairs(result.directed_neighbors, ("a", "b", "c"))[0][3] is True


def test_lx13_lx14_reverse_and_shuffles_are_invariant():
    texts = np.asarray(("alpha pump", "alpha motor", "alpha valve", "other cable"), dtype=object)
    refs = np.asarray(("r-z", "r-a", "r-m", "r-o"), dtype=object)
    expected = {
        (refs[source], refs[target], score)
        for source, rows in retrieve_exact_indexed_lexical_neighbors(_matrix(texts), refs, 2).directed_neighbors.items()
        for target, score in rows
    }
    orders = [np.arange(4)[::-1]] + [np.random.default_rng(seed).permutation(4) for seed in (7, 19, 1101)]
    for order in orders:
        current_refs = refs[order]
        actual = {
            (current_refs[source], current_refs[target], score)
            for source, rows in retrieve_exact_indexed_lexical_neighbors(_matrix(texts[order]), current_refs, 2).directed_neighbors.items()
            for target, score in rows
        }
        assert actual == expected


def test_lx15_duplicate_valued_records_remain_distinct():
    result = _compare(("same", "same", "same"), ("row-1", "row-2", "row-3"), top_k=2)
    assert all(len(rows) == 2 for rows in result.directed_neighbors.values())


def test_lx16_common_features_are_not_dropped_and_postings_are_measured():
    result = _compare(tuple("common shared term" for _ in range(12)), tuple(f"r-{i}" for i in range(12)), top_k=2)
    assert result.metrics.max_posting_size == 12
    assert result.metrics.posting_entry_count > 0


def test_lx17_zero_overlap_candidates_are_never_exact_scored():
    result = _compare(("aaa", "bbb", "ccc", "ddd"), ("a", "b", "c", "d"), top_k=2)
    assert result.metrics.exact_score_evaluations == 0
    assert result.metrics.theoretical_brute_directed_comparisons == 12


def test_lx12_production_uses_indexed_lexical_provenance_and_not_reference(monkeypatch):
    from app.services import hybrid_retrieval
    monkeypatch.setattr(
        hybrid_retrieval,
        "_deterministic_lexical_nearest_pairs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("reference called")),
    )
    data = pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "alpha pump", "CONTRACT": "S1", "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: "r-a"},
        {"PART_NO": "B", "DESCRIPTION": "alpha motor", "CONTRACT": "S1", "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: "r-b"},
    ])
    result = HybridCandidateRetriever(Settings(
        llm_provider="none", llm_demo_enabled=False, local_embedding_enabled=False,
        hybrid_retrieval_tier_c_max=10,
    )).retrieve(data, "DISCOVERY")
    assert result.lexical_retrieval.strategy == LEXICAL_RETRIEVAL_STRATEGY
    assert any("LEXICAL" in item.evidence.retrieval_sources for item in result.candidates)


@pytest.mark.parametrize("refs", [("", "b"), ("a", "a")])
def test_index_configuration_failures_are_typed_and_fail_closed(refs):
    with pytest.raises(LexicalRetrievalError) as error:
        retrieve_exact_indexed_lexical_neighbors(_matrix(("aaa", "bbb")), refs, 1)
    assert error.value.safe_category == "LEXICAL_INDEX_CONFIGURATION_INVALID"


@pytest.fixture(scope="module")
def instrumented_query_probe():
    return query_benchmark.run_query_probe(64, instrumentation_enabled=True)


@pytest.fixture(scope="module")
def uninstrumented_query_probe():
    return query_benchmark.run_query_probe(64, instrumentation_enabled=False)


def test_q1_hybrid_equivalence_returns_structured_fingerprints():
    result = query_benchmark.run_hybrid_equivalence(64)
    assert isinstance(result, dict)
    assert result["semantic_equal"] is True
    assert result["reference_fingerprint"]
    assert result["indexed_fingerprint"]


def test_q2_hybrid_mismatch_is_visible_and_cli_fails(monkeypatch, capsys):
    mismatch = {
        "semantic_equal": False,
        "reference_fingerprint": "reference",
        "indexed_fingerprint": "indexed",
    }
    monkeypatch.setattr(
        query_benchmark, "run_hybrid_equivalence", lambda *_args, **_kwargs: mismatch
    )
    assert query_benchmark.main(["--records", "64", "--hybrid"]) == 1
    assert '"semantic_equal": false' in capsys.readouterr().out


def test_q3_progress_checkpoints_are_monotonic():
    matrix = _matrix(tuple(f"common value {index}" for index in range(128)))
    collector = query_benchmark._QueryProgressCollector(
        records=128, matrix=matrix, checkpoint_path=None, checkpoint_interval=64
    )
    collector.query_started = time.perf_counter()
    payloads = []
    for start, evaluations in ((0, 100), (64, 200)):
        collector.batch_details[start] = {
            "union_sizes": [evaluations // 64] * 64,
            "top_k_seconds": 0.001,
        }
        collector.complete_batch(start, evaluations, 0.01)
        payloads.append(collector.payload())
    assert [item["anchors_completed"] for item in payloads] == [64, 128]
    assert [item["exact_score_evaluations"] for item in payloads] == [100, 300]


def test_q4_q5_timeout_preserves_checkpoint_and_never_reports_completed():
    result = query_benchmark.query_probe_timeout_result(
        {
            "active_lexical_sub_stage": "INDEXED_QUERY_SCORING",
            "anchors_completed": 256,
            "exact_score_evaluations": 12345,
        },
        records=100000, timeout_seconds=300.0, wall_seconds=300.1,
    )
    assert result["status"] == "TIMED_OUT"
    assert result["last_completed_checkpoint"]["anchors_completed"] == 256
    assert result["last_completed_checkpoint"]["exact_score_evaluations"] == 12345
    assert result["last_completed_checkpoint"]["active_lexical_sub_stage"] != "COMPLETED"


def test_q6_exact_score_counter_reconciles(instrumented_query_probe):
    assert instrumented_query_probe["progress"]["exact_score_evaluations"] == (
        instrumented_query_probe["production_metrics"]["exact_score_evaluations"]
    )


def test_q7_candidate_density_formula_is_exact(instrumented_query_probe):
    progress = instrumented_query_probe["progress"]
    expected = progress["exact_score_evaluations"] / (64 * 63)
    assert progress["candidate_density"] == pytest.approx(expected, abs=1e-9)


def test_q8_instrumentation_preserves_semantic_fingerprint(
    instrumented_query_probe, uninstrumented_query_probe,
):
    assert instrumented_query_probe["lexical_fingerprint"] == (
        uninstrumented_query_probe["lexical_fingerprint"]
    )


def test_q9_progress_payload_contains_no_raw_source_data(instrumented_query_probe):
    rendered = json.dumps(instrumented_query_probe["progress"], sort_keys=True)
    for prohibited in ("DESCRIPTION", "PART_NO", "CONTRACT", "UNIT_MEAS", "source_row"):
        assert prohibited not in rendered


def test_q10_benchmark_truth_is_absent_from_production_query_call():
    source = inspect.getsource(query_benchmark.run_query_probe)
    assert "corpus.truth" not in source
    assert "_coverage" not in source
    assert "del corpus" in source


def test_q11_query_probe_is_provider_free(instrumented_query_probe):
    assert instrumented_query_probe["provider_request_count"] == 0


def test_q12_isolated_query_probe_does_not_open_a_database(monkeypatch):
    import sqlalchemy

    monkeypatch.setattr(
        sqlalchemy, "create_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("database opened")),
    )
    result = query_benchmark.run_query_probe(64, instrumentation_enabled=False)
    assert result["status"] == "COMPLETED"


@pytest.mark.parametrize("count, expected", [
    (24_999, EXACT_INDEXED_V4),
    (25_000, BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS),
    (25_001, BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS),
    (100_000, BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS),
])
def test_i1_i2_i3_100k_threshold_selection(count, expected):
    assert select_lexical_strategy(count) == expected


@pytest.mark.parametrize("count, expected", [
    (24_999, "exact"), (25_000, "bounded"), (25_001, "bounded")
])
def test_i4_production_selection_uses_actual_matrix_row_count(
    monkeypatch, count, expected,
):
    from app.services import lexical_retrieval

    class Matrix:
        shape = (count, 1)

    monkeypatch.setattr(
        lexical_retrieval, "retrieve_bounded_lexical_neighbors",
        lambda matrix, refs, top_k: "bounded",
    )
    monkeypatch.setattr(
        lexical_retrieval, "retrieve_exact_indexed_lexical_neighbors",
        lambda *_args: "exact",
    )
    assert retrieve_production_lexical_neighbors(Matrix(), (), 5) == expected


def test_i5_i6_frozen_bounded_parameters():
    assert PRIMARY_BOUNDED_CONFIGURATION == BoundedLexicalConfiguration(
        "P1_RAREST", 32, 4096, 80, 64
    )
    assert SECOND_PASS_BOUNDED_CONFIGURATION == BoundedLexicalConfiguration(
        "P1_RAREST", 32, 16384, 80, 64
    )


def test_i7_i10_i11_fixed_second_pass_uses_exact_scores_only(monkeypatch):
    from app.services import lexical_retrieval

    monkeypatch.setattr(
        lexical_retrieval, "PRIMARY_BOUNDED_CONFIGURATION",
        BoundedLexicalConfiguration("P1_RAREST", 1, 4, 5, 2),
    )
    monkeypatch.setattr(
        lexical_retrieval, "SECOND_PASS_BOUNDED_CONFIGURATION",
        BoundedLexicalConfiguration("P1_RAREST", 1, 10, 5, 2),
    )
    matrix = csr_matrix([[1.0]] * 6)
    refs = tuple(f"ref-{index}" for index in range(6))
    bounded = retrieve_bounded_lexical_neighbors(matrix, refs, 2)
    exact = retrieve_exact_indexed_lexical_neighbors(matrix, refs, 2)
    assert bounded.directed_neighbors == exact.directed_neighbors
    assert bounded.metrics.primary_insufficient_anchors == 6
    assert bounded.metrics.second_pass_anchors == 6
    assert bounded.metrics.second_pass_recovered_anchors == 6
    assert bounded.metrics.remaining_insufficient_anchors == 0


def test_i8_i9_no_third_pass_and_post_second_pass_fails_closed(monkeypatch):
    from app.services import lexical_retrieval

    insufficient = BoundedLexicalConfiguration("P1_RAREST", 1, 4, 5, 2)
    monkeypatch.setattr(lexical_retrieval, "PRIMARY_BOUNDED_CONFIGURATION", insufficient)
    monkeypatch.setattr(lexical_retrieval, "SECOND_PASS_BOUNDED_CONFIGURATION", insufficient)
    with pytest.raises(LexicalRetrievalError) as error:
        retrieve_bounded_lexical_neighbors(
            csr_matrix([[1.0]] * 6), tuple(f"r-{i}" for i in range(6)), 2
        )
    assert error.value.safe_category == "LEXICAL_CANDIDATE_POOL_INSUFFICIENT"
    source = inspect.getsource(retrieve_bounded_lexical_neighbors)
    assert "third" not in source.casefold()
    assert "retrieve_exact_indexed_lexical_neighbors" not in source


def test_i12_i13_bounded_ties_and_reverse_are_canonical(monkeypatch):
    from app.services import lexical_retrieval

    configuration = BoundedLexicalConfiguration("P1_RAREST", 2, 20, 5, 2)
    monkeypatch.setattr(lexical_retrieval, "PRIMARY_BOUNDED_CONFIGURATION", configuration)
    monkeypatch.setattr(lexical_retrieval, "SECOND_PASS_BOUNDED_CONFIGURATION", configuration)
    matrix = csr_matrix([[1.0]] * 6)
    refs = np.asarray(("z", "a", "m", "b", "y", "c"), dtype=object)
    expected = {
        (refs[source], refs[target], score)
        for source, rows in retrieve_bounded_lexical_neighbors(matrix, refs, 2).directed_neighbors.items()
        for target, score in rows
    }
    order = np.arange(6)[::-1]
    actual = {
        (refs[order][source], refs[order][target], score)
        for source, rows in retrieve_bounded_lexical_neighbors(
            matrix[order], refs[order], 2
        ).directed_neighbors.items()
        for target, score in rows
    }
    assert actual == expected


def test_i14_strategy_fingerprint_changes_with_parameters():
    changed = replace(PRIMARY_BOUNDED_CONFIGURATION, visit_budget=4097)
    assert lexical_strategy_contract_fingerprint(5) != (
        lexical_strategy_contract_fingerprint(5, primary=changed)
    )


def test_i15_v4_contract_remains_frozen_and_embedded():
    assert lexical_retrieval_contract_fingerprint(5) == (
        "aa64c35e13cc2002301e5a4b4736789a14b25041d798e6f6658bef9412dd92e8"
    )
    assert lexical_strategy_contract_payload(5)["v4_contract_fingerprint"] == (
        lexical_retrieval_contract_fingerprint(5)
    )


def test_i20_production_strategy_has_no_provider_or_benchmark_dependency():
    from app.services import lexical_retrieval

    source = inspect.getsource(lexical_retrieval)
    assert "app.benchmarks" not in source
    assert "provider" not in source.casefold()
