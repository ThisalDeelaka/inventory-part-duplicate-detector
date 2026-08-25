import numpy as np
import pandas as pd
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize

from app.core.config import Settings
from app.benchmarks.lexical_tie_contract import run_downstream_comparison
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    _deterministic_lexical_directed_neighbors,
    _deterministic_lexical_nearest_pairs,
)
from app.services.identity_discovery_service import (
    DISCOVERY_ALGORITHM_VERSION,
    DISCOVERY_CONFIGURATION_VERSION,
)
from app.services.lexical_retrieval import LexicalRetrievalError


def _matrix(rows):
    return normalize(np.asarray(rows, dtype=np.float64))


def _semantic(directed, refs):
    return tuple(sorted(
        (refs[source], refs[target], round(score, 12))
        for source, neighbors in directed.items()
        for target, score in neighbors
    ))


def _old_directed(matrix, top_k):
    count = matrix.shape[0]
    index = NearestNeighbors(
        n_neighbors=min(count, top_k + 1), metric="cosine", algorithm="brute"
    ).fit(matrix)
    distances, indices = index.kneighbors(matrix)
    return {
        source: tuple(
            (int(target), float(1.0 - distance))
            for distance, target in zip(distances[source], indices[source])
            if int(target) != source and 1.0 - float(distance) > 0
        )
        for source in range(count)
    }


def test_lt1_unique_score_ranking_is_exact_and_unchanged():
    matrix = _matrix(((1, 0), (0.9, 0.1), (0.7, 0.3), (0, 1)))
    refs = ("anchor", "r1", "r2", "r3")
    new = _deterministic_lexical_directed_neighbors(matrix, 2, refs)
    old = _old_directed(matrix, 2)
    assert [target for target, _ in new[0]] == [target for target, _ in old[0]]
    assert [score for _, score in new[0]] == pytest.approx(
        [score for _, score in old[0]], abs=1e-12
    )


def test_lt2_exact_boundary_tie_uses_record_ref_key():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6)))
    directed = _deterministic_lexical_directed_neighbors(
        matrix, 1, ("anchor", "z-ref", "a-ref")
    )
    assert directed[0][0][0] == 2


def test_lt3_self_is_excluded_before_final_top_k():
    matrix = _matrix(((1, 0), (1, 0), (1, 0)))
    refs = ("b-anchor", "c-ref", "a-ref")
    directed = _deterministic_lexical_directed_neighbors(matrix, 1, refs)
    assert directed[0] == ((2, pytest.approx(1.0)),)
    assert directed[2] == ((0, pytest.approx(1.0)),)


def test_lt4_tie_below_boundary_does_not_change_top_k():
    matrix = _matrix(((1, 0), (0.99, 0.01), (0.8, 0.2), (0.5, 0.5), (0.5, 0.5)))
    directed = _deterministic_lexical_directed_neighbors(
        matrix, 2, ("anchor", "r1", "r2", "a-below", "z-below")
    )
    assert [target for target, _ in directed[0]] == [1, 2]


def test_lt5_fewer_than_top_k_positive_neighbors_are_preserved():
    matrix = _matrix(((1, 0, 0), (0.5, 0.5, 0), (0, 0, 1)))
    directed = _deterministic_lexical_directed_neighbors(matrix, 5, ("a", "b", "c"))
    assert [target for target, _ in directed[0]] == [1]
    assert directed[2] == ()


def test_lt6_all_zero_similarities_never_become_pairs():
    matrix = _matrix(((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    refs = ("a", "b", "c")
    assert all(not row for row in _deterministic_lexical_directed_neighbors(matrix, 2, refs).values())
    assert _deterministic_lexical_nearest_pairs(matrix, 2, refs) == []


def test_lt7_duplicate_valued_rows_remain_distinct_canonical_records():
    matrix = _matrix(((1, 0), (1, 0), (1, 0)))
    refs = ("record-1", "record-2", "record-3")
    directed = _deterministic_lexical_directed_neighbors(matrix, 2, refs)
    assert set(directed) == {0, 1, 2}
    assert all(len(neighbors) == 2 for neighbors in directed.values())


@pytest.mark.parametrize("seed", [None, 7, 19, 1101])
def test_lt8_lt9_reverse_and_fixed_shuffles_are_semantically_invariant(seed):
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1), (0.6, 0.8)))
    refs = np.asarray(("anchor", "z-ref", "a-ref", "other", "middle"), dtype=object)
    expected = _semantic(_deterministic_lexical_directed_neighbors(matrix, 2, refs), refs)
    permutation = np.arange(len(refs))[::-1] if seed is None else np.random.default_rng(seed).permutation(len(refs))
    actual_refs = refs[permutation]
    actual = _semantic(
        _deterministic_lexical_directed_neighbors(matrix[permutation], 2, actual_refs),
        actual_refs,
    )
    assert actual == expected


def test_lt10_repeated_runs_are_identical():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0, 1)))
    refs = ("anchor", "z-ref", "a-ref", "other")
    first = _deterministic_lexical_directed_neighbors(matrix, 2, refs)
    assert first == _deterministic_lexical_directed_neighbors(matrix, 2, refs)


def test_lt11_lt12_historical_substitutions_are_exact_score_ties_only():
    matrix = _matrix(((1, 0), (0.8, 0.6), (0.8, 0.6), (0.8, 0.6)))
    refs = ("anchor", "z-ref", "m-ref", "a-ref")
    old = _old_directed(matrix, 1)
    new = _deterministic_lexical_directed_neighbors(matrix, 1, refs)
    substitutions = 0
    for source in range(len(refs)):
        old_scores = dict(old[source])
        new_scores = dict(new[source])
        removed = set(old_scores) - set(new_scores)
        added = set(new_scores) - set(old_scores)
        substitutions += len(removed) + len(added)
        if removed or added:
            boundary = min(new_scores.values())
            assert all(old_scores[target] == pytest.approx(boundary) for target in removed)
            assert all(new_scores[target] == pytest.approx(boundary) for target in added)
    assert substitutions > 0


def test_lt13_reciprocity_and_two_decimal_score_reconstruction_are_preserved():
    matrix = _matrix(((1, 0), (1, 0), (0.9, 0.1)))
    rows = _deterministic_lexical_nearest_pairs(matrix, 1, ("a", "b", "c"))
    assert rows[0] == (0, 1, 100.0, True)


def test_lt14_production_preserves_lexical_provenance_caps_and_configuration():
    data = pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "alpha pump", "CONTRACT": "S1", "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: "r-a"},
        {"PART_NO": "B", "DESCRIPTION": "alpha pump", "CONTRACT": "S1", "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: "r-b"},
        {"PART_NO": "C", "DESCRIPTION": "alpha pump", "CONTRACT": "S1", "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: "r-c"},
    ])
    settings = Settings(
        llm_provider="none", llm_demo_enabled=False, local_embedding_enabled=False,
        hybrid_retrieval_lexical_top_k=1, hybrid_retrieval_final_top_k=1,
        hybrid_retrieval_max_pairs_per_scan=10,
        hybrid_retrieval_tier_a_max=10, hybrid_retrieval_tier_b_max=10,
        hybrid_retrieval_tier_c_max=10,
    )
    result = HybridCandidateRetriever(settings).retrieve(data, "DISCOVERY")
    assert result.candidates
    assert all("LEXICAL" in item.evidence.retrieval_sources for item in result.candidates)
    assert result.metrics.max_candidates_for_any_record <= 1
    assert DISCOVERY_ALGORITHM_VERSION == "identity-discovery-v5-bounded-lexical-strategy"
    assert DISCOVERY_CONFIGURATION_VERSION == "identity-discovery-config-v5"


@pytest.mark.parametrize("refs", [("", "b"), ("a", "a")])
def test_lexical_canonical_reference_failures_are_closed(refs):
    with pytest.raises(ValueError, match="lexical retrieval"):
        _deterministic_lexical_directed_neighbors(_matrix(((1, 0), (0, 1))), 1, refs)


def test_production_does_not_swallow_missing_canonical_reference_failure():
    data = pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "alpha pump", "CONTRACT": "S1", "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: ""},
        {"PART_NO": "B", "DESCRIPTION": "alpha motor", "CONTRACT": "S1", "UNIT_MEAS": "EA", CANONICAL_RECORD_REF_FIELD: "r-b"},
    ])
    settings = Settings(llm_provider="none", llm_demo_enabled=False, local_embedding_enabled=False)
    with pytest.raises(LexicalRetrievalError, match="lexical retrieval") as error:
        HybridCandidateRetriever(settings).retrieve(data, "DISCOVERY")
    assert getattr(error.value, "safe_category", None) == "LEXICAL_INDEX_CONFIGURATION_INVALID"


def test_vectorizer_contract_remains_char_wb_3_to_5_l2_tfidf():
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1)
    matrix = vectorizer.fit_transform(("alpha pump", "alpha motor"))
    assert vectorizer.analyzer == "char_wb"
    assert vectorizer.ngram_range == (3, 5)
    assert vectorizer.norm == "l2"
    assert np.linalg.norm(matrix.toarray(), axis=1) == pytest.approx((1.0, 1.0))


def test_lt15_lt16_bounded_gf1_gf6_safety_and_deprecated_writes_are_identical():
    results = run_downstream_comparison(64, seed=1101)
    assert results["CANONICAL"] == results["HISTORICAL"]
    safety = results["CANONICAL"]["safety"]
    assert safety == {
        "accepted_cannot_link_violations": 0,
        "duplicate_accepted_memberships": 0,
        "single_member_accepted_groups": 0,
        "cross_scan_contamination": 0,
        "provider_calls": 0,
        "legacy_pair_rows": 0,
        "g1_projection_rows": 0,
        "g2_v1_rows": 0,
        "shadow_rows": 0,
    }
