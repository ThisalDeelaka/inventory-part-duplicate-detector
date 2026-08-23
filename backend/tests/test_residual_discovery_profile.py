"""GF-11B residual-profiling correctness tests R1-R14."""

import inspect
import tempfile
from pathlib import Path

import pytest

from app.benchmarks import residual_discovery_profile as profile


@pytest.fixture(scope="module")
def profiled_pair():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        enabled = profile.run_residual_profile(
            records=64, seed=1101, db_path=root / "enabled.db"
        )
        disabled = profile.run_residual_profile(
            records=64, seed=1101, db_path=root / "disabled.db",
            python_profile_enabled=False,
        )
        yield enabled, disabled


def test_r1_timing_taxonomy_is_non_overlapping(profiled_pair):
    result = profiled_pair[0]
    values = result["timing_decomposition_seconds"]
    assert set(values) == set(profile.TAXONOMY) | {"OTHER_UNATTRIBUTED"}
    assert sum(values.values()) == pytest.approx(
        result["discovery_total_seconds"], abs=2e-5
    )


def test_r2_other_unattributed_is_exact_remainder(profiled_pair):
    result = profiled_pair[0]
    values = result["timing_decomposition_seconds"]
    named = sum(value for key, value in values.items() if key != "OTHER_UNATTRIBUTED")
    assert values["OTHER_UNATTRIBUTED"] == pytest.approx(
        max(0.0, result["discovery_total_seconds"] - named), abs=2e-5
    )


def test_r3_python_profiling_disabled_has_no_semantic_change(profiled_pair):
    enabled, disabled = profiled_pair
    assert enabled["proposal_semantic_fingerprint"] == disabled["proposal_semantic_fingerprint"]
    assert enabled["neighborhood_semantic_fingerprint"] == disabled["neighborhood_semantic_fingerprint"]
    assert enabled["proposal_row_count"] == disabled["proposal_row_count"]
    assert enabled["member_row_count"] == disabled["member_row_count"]


def test_r4_sql_counters_never_capture_parameters(profiled_pair):
    result = profiled_pair[0]
    assert result["raw_sql_parameters_captured"] is False
    assert set(result["sql_counts_total"]) <= {
        "SELECT", "INSERT", "UPDATE", "DELETE", "OTHER", "EXECUTEMANY"
    }


def test_r5_profile_output_is_path_and_machine_sanitized(profiled_pair):
    rows = (
        profiled_pair[0]["python_profile"]["by_cumulative"]
        + profiled_pair[0]["python_profile"]["by_self"]
    )
    assert rows
    assert all("/" not in row["module"] and "\\" not in row["module"] for row in rows)
    assert all(set(row) == {
        "module", "function", "call_count", "primitive_call_count",
        "self_seconds", "cumulative_seconds",
    } for row in rows)


def test_r6_proposal_counters_reconcile(profiled_pair):
    result = profiled_pair[0]
    assert result["object_counts"]["gf2_proposal_objects"] == result["proposal_row_count"]
    assert result["object_counts"]["gf2_proposal_rows"] == result["proposal_row_count"]


def test_r7_neighborhood_and_member_counters_reconcile(profiled_pair):
    result = profiled_pair[0]
    counts = result["object_counts"]
    assert counts["gf3_neighborhoods"] == counts["gf3_neighborhood_rows"] == result["neighborhood_row_count"]
    assert counts["gf3_members"] == counts["gf3_member_rows"] == result["member_row_count"]


def test_r8_commit_counters_reconcile(profiled_pair):
    commits = profiled_pair[0]["commit_counts"]
    assert commits == {
        "DISCOVERY_FINAL_VALIDATION_OR_RECONSTRUCTION": 1,
        "GF2_TRANSACTION_COMMIT": 1,
        "GF3_TRANSACTION_COMMIT": 1,
    }


def test_r9_500_semantic_comparison_contract_uses_both_fingerprints():
    source = inspect.getsource(profile.run_residual_profile)
    assert "proposal_semantic_fingerprint" in source
    assert "neighborhood_semantic_fingerprint" in source


def test_r10_5k_semantic_comparison_contract_is_cardinality_independent():
    assert "records" in inspect.signature(profile.run_residual_profile).parameters
    assert profile._semantic_fingerprint(((1, "a"), (2, "b"))) == (
        profile._semantic_fingerprint(((2, "b"), (1, "a")))
    )


def test_r11_benchmark_truth_is_not_imported_into_profiling_path():
    source = inspect.getsource(profile)
    assert ".truth" not in source
    assert "BenchmarkTruth" not in source


def test_r12_provider_calls_are_zero(profiled_pair):
    assert profiled_pair[0]["provider_request_count"] == 0
    assert profiled_pair[0]["retrieval_counts"]["provider_request_count"] == 0


def test_r13_disposable_database_does_not_use_configured_default(profiled_pair):
    assert profiled_pair[0]["database_is_disposable"] is True
    source = inspect.getsource(profile.run_residual_profile)
    assert "database_url" not in source
    assert "inventory_detector.db" not in source


def test_r14_timeout_records_active_stage_and_cannot_complete():
    result = profile.timeout_result(
        {"status": "RUNNING", "active_sub_stage": "GF2_PROPOSAL_PERSISTENCE"},
        timeout_seconds=300.0,
        wall_seconds=300.01,
    )
    assert result["status"] == "TIMED_OUT"
    assert result["active_sub_stage"] == "GF2_PROPOSAL_PERSISTENCE"
    assert result["status"] != "COMPLETED"

    finalized = profile.timeout_result(
        {"status": "COMPLETED", "active_sub_stage": "COMPLETED"},
        timeout_seconds=300.0,
        wall_seconds=300.01,
    )
    assert finalized["status"] == "TIMED_OUT"
    assert finalized["active_sub_stage"] == "REPORT_FINALIZATION_AFTER_DISCOVERY"
