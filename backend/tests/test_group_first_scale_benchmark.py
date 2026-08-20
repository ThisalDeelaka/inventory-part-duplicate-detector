"""GF-11A focused acceptance tests B1-B16."""

from __future__ import annotations

from dataclasses import replace

from app.benchmarks.contracts import ScaleBenchmarkStatus, ScaleSafetyMetrics
from app.benchmarks.group_first_scale import (
    inspect_interrupted_benchmark,
    run_scale_benchmark,
    safe_environment_metadata,
)
from app.benchmarks.group_first_scale_generator import (
    SCENARIO_CODES,
    generate_scale_corpus,
)


def test_b1_same_seed_and_version_are_deterministic():
    first = generate_scale_corpus(500, seed=1101)
    second = generate_scale_corpus(500, seed=1101)
    assert first.version == second.version
    assert first.generator_fingerprint == second.generator_fingerprint
    assert first.records.to_dict("records") == second.records.to_dict("records")
    assert first.truth == second.truth


def test_b2_different_seed_changes_corpus():
    assert generate_scale_corpus(500, seed=1).generator_fingerprint != (
        generate_scale_corpus(500, seed=2).generator_fingerprint
    )


def test_b3_duplicate_valued_rows_remain_distinct():
    corpus = generate_scale_corpus(20, seed=4, scenario="S2")
    first_set = corpus.truth.duplicate_sets[0][1]
    assert corpus.records.iloc[first_set[0]].to_dict() == corpus.records.iloc[first_set[1]].to_dict()
    assert first_set[0] != first_set[1]


def test_b4_generic_hub_labels_stay_outside_product_input():
    corpus = generate_scale_corpus(20, seed=4, scenario="S3")
    assert "benchmark" not in " ".join(corpus.records.columns).casefold()
    assert set(corpus.truth.scenario_by_source_row) == {"S3"}


def test_b5_technical_conflict_truth_is_benchmark_only():
    corpus = generate_scale_corpus(20, seed=4, scenario="S4")
    assert corpus.truth.protected_conflict_sets
    assert not any("truth" in column.casefold() for column in corpus.records.columns)


def test_b6_bridge_scenario_is_generated_correctly():
    corpus = generate_scale_corpus(21, seed=4, scenario="S7")
    assert corpus.truth.bridge_sets
    assert all(len(items) == 3 for items in corpus.truth.bridge_sets)
    assert all(len(items) == 2 for _identity, items in corpus.truth.duplicate_sets)


def test_b7_100k_generation_is_bounded_without_pair_matrix():
    corpus = generate_scale_corpus(100_000, seed=1101)
    assert len(corpus.records) == 100_000
    assert len(corpus.truth.scenario_by_source_row) == 100_000
    assert not hasattr(corpus.truth, "negative_pairs")
    assert sum(len(items) for _identity, items in corpus.truth.duplicate_sets) <= 100_000


def _small_result(tmp_path, name="small.sqlite"):
    return run_scale_benchmark(
        records=64, seed=1101, scenario="canonical-mixed",
        db_path=tmp_path / name, hybrid_enabled=False,
    )


def test_b8_result_json_schema_is_stable(tmp_path):
    body = _small_result(tmp_path).to_dict()
    assert tuple(body) == (
        "contract_version", "scenario", "environment", "run", "stage_metrics",
        "database_metrics", "safety_metrics", "quality_metrics",
        "resource_metrics", "complexity_metrics", "bottleneck_observations",
        "result_fingerprint",
    )


def test_b9_stage_counters_reconcile_with_persisted_rows(tmp_path):
    result = _small_result(tmp_path)
    rows = dict(result.database_metrics.row_counts)
    stages = {item.stage: item for item in result.stage_metrics}
    assert stages["CANONICAL_CATALOG"].output_count == rows["gf1_scan_records"] == 64
    assert stages["DISCOVERY"].output_count == rows["gf2_neighbor_proposals"]
    assert stages["SIGNED_EVIDENCE"].output_count == rows["gf4_evidence_edges"]
    assert rows["gf6_projection_runs"] == 1


def test_b10_safety_contract_detects_an_injected_violation():
    safe = ScaleSafetyMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)
    assert safe.passed
    assert not replace(safe, accepted_cannot_link_violations=1).passed


def test_b11_policy_v2_creates_no_pair_g1_v1_or_shadow(tmp_path):
    safety = _small_result(tmp_path).safety_metrics
    assert safety.legacy_pair_rows == 0
    assert safety.g1_projection_rows == 0
    assert safety.g2_v1_rows == 0
    assert safety.shadow_rows == 0


def test_b12_provider_calls_are_zero(tmp_path):
    assert _small_result(tmp_path).safety_metrics.provider_calls == 0


def test_b13_database_is_isolated_from_other_paths(tmp_path):
    unrelated = tmp_path / "configured-default.sqlite"
    result = _small_result(tmp_path, "disposable.sqlite")
    assert result.run.status == ScaleBenchmarkStatus.COMPLETED
    assert not unrelated.exists()
    assert (tmp_path / "disposable.sqlite").exists()


def test_b14_interrupted_result_cannot_report_completed(tmp_path):
    result = inspect_interrupted_benchmark(
        records=32, seed=1101, scenario="canonical-mixed",
        db_path=tmp_path / "not-created.sqlite", elapsed=0.01,
        status=ScaleBenchmarkStatus.TIMED_OUT,
    )
    assert result.run.status == ScaleBenchmarkStatus.TIMED_OUT
    assert result.run.status != ScaleBenchmarkStatus.COMPLETED


def test_b15_semantic_result_fingerprint_is_deterministic(tmp_path):
    first = _small_result(tmp_path, "first.sqlite")
    second = _small_result(tmp_path, "second.sqlite")
    assert first.result_fingerprint == second.result_fingerprint


def test_b16_environment_metadata_contains_no_identity_or_paths():
    metadata = dict(safe_environment_metadata())
    assert set(metadata) == {
        "logical_cpu_count", "platform", "process_architecture",
        "python_version", "sqlite_version",
    }
    text = repr(metadata).casefold()
    assert "hostname" not in text and "username" not in text
    assert ":\\" not in text and "/home/" not in text


def test_all_s1_to_s8_scenarios_are_available():
    assert SCENARIO_CODES == ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")
