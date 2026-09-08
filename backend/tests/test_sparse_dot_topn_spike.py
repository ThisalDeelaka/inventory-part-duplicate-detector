import inspect
import os
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from sklearn.preprocessing import normalize

from app.benchmarks import sparse_dot_topn_spike as spike
from app.services.hybrid_retrieval import (
    _deterministic_lexical_directed_neighbors,
    _directed_neighbors_to_pairs,
)


@pytest.fixture(scope="module")
def package_target():
    value = os.environ.get(spike.PACKAGE_TARGET_ENV)
    if not value:
        pytest.skip("optional sparse-dot spike target is not configured")
    return Path(value).resolve()


def _matrix(rows):
    return normalize(csr_matrix(np.asarray(rows, dtype=np.float64)))


def _compare(matrix, refs, top_k, package_target, *, threads=1):
    result = spike.retrieve_sparse_dot_topn_exact(
        matrix, refs, top_k, n_threads=threads, package_target=package_target
    )
    expected = _deterministic_lexical_directed_neighbors(matrix, top_k, refs)
    assert result.directed_neighbors == expected
    return result, expected


def test_sd1_dependency_is_loaded_only_from_disposable_target(package_target):
    metadata = spike.dependency_metadata(package_target)
    repository = Path(__file__).resolve().parents[2]
    package_path = Path(metadata["package_path"]).resolve()
    assert repository not in package_path.parents
    assert package_target in package_path.parents


def test_sd2_package_version_and_platform_are_captured(package_target):
    metadata = spike.dependency_metadata(package_target)
    assert metadata["version"] == "1.2.0"
    assert metadata["python"] and metadata["numpy"] and metadata["scipy"]
    assert metadata["license"] == "Apache-2.0"


def test_sd3_s1_s14_unique_scores_preserve_exact_full_precision(package_target):
    matrix = _matrix(((1, 0, 0), (.9, .1, 0), (.7, .3, 0), (0, 0, 1)))
    result, expected = _compare(matrix, ("anchor", "r1", "r2", "other"), 2, package_target)
    for source, rows in result.directed_neighbors.items():
        assert rows == expected[source]


def test_sd4_s5_self_is_excluded_before_final_top_k(package_target):
    matrix = _matrix(((1, 0), (1, 0), (.8, .2), (0, 1)))
    result, _ = _compare(matrix, ("anchor", "same", "near", "other"), 2, package_target)
    assert all(source != target for source, rows in result.directed_neighbors.items() for target, _ in rows)
    assert len(result.directed_neighbors[0]) == 2


def test_sd5_s2_s3_exact_boundary_ties_use_canonical_refs(package_target):
    matrix = _matrix(((1, 0), (.8, .6), (.8, .6), (.7, .7)))
    refs = ("anchor", "z-ref", "a-ref", "below")
    result, _ = _compare(matrix, refs, 1, package_target)
    assert refs[result.directed_neighbors[0][0][0]] == "a-ref"


def test_sd6_s4_s6_large_tie_set_keeps_distinct_records(package_target):
    count = 256
    matrix = _matrix(tuple((1, 0) for _ in range(count)))
    refs = tuple(f"r-{count-index:04d}" for index in range(count))
    result, _ = _compare(matrix, refs, 5, package_target)
    assert result.metrics.anchors_with_boundary_ties == count
    assert result.metrics.maximum_boundary_tie_size == count - 1
    assert all(len(rows) == 5 for rows in result.directed_neighbors.values())


@pytest.mark.parametrize("rows,top_k,lengths", [
    (((1, 0, 0), (0, 1, 0), (0, 0, 1)), 2, (0, 0, 0)),
    (((1, 0, 0), (1, 1, 0), (0, 0, 1)), 3, (1, 1, 0)),
    (((1, 0), (1, .1), (1, .2), (1, .3)), 3, (3, 3, 3, 3)),
])
def test_sd7_s7_s8_s16_zero_and_fewer_than_k_semantics(
    rows, top_k, lengths, package_target,
):
    matrix = _matrix(rows)
    refs = tuple(f"r-{index}" for index in range(len(rows)))
    result, _ = _compare(matrix, refs, top_k, package_target)
    assert tuple(len(result.directed_neighbors[index]) for index in range(len(rows))) == lengths
    assert all(score > 0 for values in result.directed_neighbors.values() for _target, score in values)


def test_sd8_s9_s10_s11_s12_reverse_and_shuffles_are_exact(package_target):
    matrix = _matrix((
        (1, 1, 1, 0, 0), (1, 1, 1, 0, 0), (1, 1, .9, .1, 0),
        (0, 0, 0, 1, 1), (0, 0, 0, 0, 0), (1, .5, 0, .5, 0),
    ))
    refs = np.asarray(("z", "a", "m", "other", "missing", "bridge"), dtype=object)
    expected, _ = _compare(matrix, refs, 3, package_target)
    signature = tuple(sorted(
        (refs[source], refs[target], score)
        for source, rows in expected.directed_neighbors.items() for target, score in rows
    ))
    orders = [np.arange(len(refs))[::-1]] + [
        np.random.default_rng(seed).permutation(len(refs)) for seed in (7, 19, 1101)
    ]
    for order in orders:
        current = spike.retrieve_sparse_dot_topn_exact(
            matrix[order], refs[order], 3, package_target=package_target
        )
        current_signature = tuple(sorted(
            (refs[order][source], refs[order][target], score)
            for source, rows in current.directed_neighbors.items() for target, score in rows
        ))
        assert current_signature == signature


@pytest.mark.parametrize("threads", [1, 4])
def test_sd9_s13_repeated_runs_are_deterministic(threads, package_target):
    matrix = _matrix(tuple((1, index % 3, index % 5) for index in range(32)))
    refs = tuple(f"r-{index:03d}" for index in range(32))
    first = spike.retrieve_sparse_dot_topn_exact(
        matrix, refs, 5, n_threads=threads, package_target=package_target
    )
    second = spike.retrieve_sparse_dot_topn_exact(
        matrix, refs, 5, n_threads=threads, package_target=package_target
    )
    assert first.directed_neighbors == second.directed_neighbors


def test_sd10_native_ties_mismatch_but_canonical_recovery_is_exact(package_target):
    matrix = _matrix(tuple((1, 0) for _ in range(64)))
    refs = tuple(f"r-{64-index:03d}" for index in range(64))
    result = spike.retrieve_sparse_dot_topn_exact(matrix, refs, 5, package_target=package_target)
    expected = _deterministic_lexical_directed_neighbors(matrix, 5, refs)
    native_mismatches, native_unequal = spike._mismatch_counts(
        expected, result.native_directed_neighbors
    )
    corrected_mismatches, corrected_unequal = spike._mismatch_counts(
        expected, result.directed_neighbors
    )
    assert native_mismatches > 0 and native_unequal == 0
    assert corrected_mismatches == corrected_unequal == 0


def test_sd11_s15_reciprocity_and_provider_count_are_unchanged(package_target):
    matrix = _matrix(((1, 0), (1, 0), (.8, .2), (0, 1)))
    refs = ("a", "b", "c", "d")
    result, expected = _compare(matrix, refs, 2, package_target)
    assert _directed_neighbors_to_pairs(result.directed_neighbors, refs) == (
        _directed_neighbors_to_pairs(expected, refs)
    )
    assert result.metrics.provider_request_count == 0


def test_sd12_truth_is_not_supplied_to_dependency_retrieval():
    source = inspect.getsource(spike.retrieve_sparse_dot_topn_exact)
    assert "truth" not in source
    assert "corpus" not in source


def test_sd13_isolated_retrieval_does_not_open_database(monkeypatch, package_target):
    import sqlalchemy

    monkeypatch.setattr(
        sqlalchemy, "create_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("database opened")),
    )
    result = spike.retrieve_sparse_dot_topn_exact(
        _matrix(((1, 0), (1, 0))), ("a", "b"), 1,
        package_target=package_target,
    )
    assert result.directed_neighbors


def test_sd14_timeout_cannot_report_completed():
    result = spike.timeout_result(records=100000, timeout_seconds=120, wall_seconds=120.1)
    assert result["status"] == "TIMED_OUT"
    assert result["safe_failure_category"] == "SPARSE_DOT_TOPN_SPIKE_TIMEOUT"
