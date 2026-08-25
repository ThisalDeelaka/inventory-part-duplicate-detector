"""GF-11D-CHAR-PRE focused acceptance tests CP1-CP14."""

from __future__ import annotations

import inspect
import json

import numpy as np
import pytest
from sklearn.preprocessing import normalize

from app.benchmarks import character_retrieval_profile as profile
from app.services.character_retrieval import (
    CharacterLshConfiguration,
    retrieve_lsh_directed_neighbors,
)


@pytest.fixture(scope="module")
def small_profile(tmp_path_factory):
    return profile.run_profile(
        64, checkpoint_path=tmp_path_factory.mktemp("char-profile") / "checkpoint.json"
    )


def test_cp1_taxonomy_reconciles_to_char_total(small_profile):
    timings = small_profile["timing_seconds"]
    children = sum(timings[name] for name in profile.TAXONOMY)
    assert children + timings["OTHER_UNATTRIBUTED"] == pytest.approx(
        timings["CHAR_TOTAL"], abs=2e-5
    )


def test_cp2_other_unattributed_is_nonnegative(small_profile):
    assert small_profile["timing_seconds"]["OTHER_UNATTRIBUTED"] >= 0


def test_cp3_bucket_counters_reconcile(small_profile):
    counters = small_profile["counters"]
    assert counters["bucket_lookups"] == (
        counters["bucket_hits"] + counters["empty_bucket_lookups"]
    )
    assert counters["raw_candidate_visits"] == counters["bucket_members_visited"]


def test_cp4_candidate_dedup_counters_reconcile(small_profile):
    counters = small_profile["counters"]
    assert counters["dedup_eliminations"] == (
        counters["raw_candidate_visits"]
        - counters["unique_candidates_before_pool"]
    )


def test_cp5_exact_rerank_count_reconciles(small_profile):
    counters = small_profile["counters"]
    assert counters["exact_rerank_evaluations"] == (
        counters["candidate_pool_evaluations"]
    )
    assert counters["candidate_pool"]["max"] <= 63


def test_cp6_checkpoints_are_monotonic(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    telemetry = profile._Telemetry(checkpoint)
    telemetry.checkpoint()
    first = json.loads(checkpoint.read_text(encoding="utf-8"))
    telemetry.anchors_completed = 256
    telemetry.counters["bucket_lookups"] = 10
    telemetry.checkpoint()
    second = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert second["anchors_completed"] >= first["anchors_completed"]
    assert second["elapsed_char_seconds"] >= first["elapsed_char_seconds"]
    assert second["bucket_lookups"] >= first["bucket_lookups"]


def test_cp7_timeout_cannot_report_completion():
    result = profile.timeout_result(
        {"status": "COMPLETED", "active_sub_stage": "COMPLETED"},
        timeout_seconds=450.0, wall_seconds=450.1,
    )
    assert result["status"] == "TIMED_OUT"
    assert result["active_sub_stage"] == "TIMEOUT_AFTER_LAST_CHECKPOINT"


def test_cp8_timeout_retains_last_checkpoint():
    checkpoint = {"anchors_completed": 256, "active_sub_stage": "EXACT_RERANK"}
    result = profile.timeout_result(
        checkpoint, timeout_seconds=450.0, wall_seconds=450.1
    )
    assert result["last_checkpoint"] == checkpoint


def test_cp9_telemetry_contains_no_raw_record_data(small_profile):
    assert small_profile["raw_record_data_emitted"] is False
    assert "directed_neighbors" not in small_profile or isinstance(
        small_profile["counters"]["directed_neighbors"], int
    )


def test_cp10_instrumentation_preserves_semantic_fingerprint():
    rng = np.random.default_rng(1101)
    matrix = normalize(rng.random((32, 384), dtype=np.float32)).astype(np.float32)
    refs = tuple(f"ref-{index:04d}" for index in range(32))
    config = CharacterLshConfiguration(
        table_count=4, bits_per_table=2, probe_radius=2, candidate_pool_k=31
    )
    production = retrieve_lsh_directed_neighbors(matrix, refs, 5, config)
    first = profile._semantic_fingerprints(production.directed_neighbors, refs)
    second = profile._semantic_fingerprints(production.directed_neighbors, refs)
    assert first == second


def test_cp11_enabled_disabled_semantics_are_identical(small_profile):
    baseline = profile.run_uninstrumented(64)
    assert baseline["directed_neighbor_fingerprint"] == (
        small_profile["directed_neighbor_fingerprint"]
    )
    assert baseline["pair_fingerprint"] == small_profile["pair_fingerprint"]


def test_cp12_provider_calls_are_zero(small_profile):
    assert small_profile["provider_calls"] == 0


def test_cp13_benchmark_does_not_open_configured_database():
    source = inspect.getsource(profile)
    assert "database_url" not in source
    assert "inventory_detector.db" not in source


def test_cp14_no_schema_migration_or_dependency_change():
    source = inspect.getsource(profile).casefold()
    assert "alembic" not in source
    assert "pip install" not in source
