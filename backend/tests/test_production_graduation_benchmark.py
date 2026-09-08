"""GF-11D focused benchmark-contract acceptance tests D1-D14."""

from __future__ import annotations

import inspect
import json

import pytest

from app.benchmarks import production_graduation as graduation
from app.benchmarks.group_first_scale import benchmark_configuration
from app.benchmarks.residual_discovery_profile import _Collector, _decomposition
from app.services.lexical_retrieval import (
    BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS,
    EXACT_INDEXED_V4,
)


def test_d1_canonical_100k_corpus_and_configuration_are_pinned():
    assert graduation.CANONICAL_RECORDS == 100_000
    assert graduation.CANONICAL_SEED == 1101
    assert graduation.GRADUATION_TIMEOUT_SECONDS == 300.0


def test_d2_disposable_database_is_enforced(tmp_path):
    existing = tmp_path / "existing.sqlite"
    existing.touch()
    with pytest.raises(ValueError, match="must not already exist"):
        graduation.run_graduation_benchmark(
            records=1, seed=1101, db_path=existing
        )


def test_d3_provider_none_is_enforced():
    config = benchmark_configuration()
    assert config.llm_provider == config.group_llm_provider == "none"


def test_d4_strategy_selector_chooses_bounded_path_at_100k():
    assert graduation.strategy_sanity(20_000)["strategy"] == EXACT_INDEXED_V4
    assert graduation.strategy_sanity(50_000)["strategy"] == (
        BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS
    )
    assert graduation.strategy_sanity(100_000)["strategy"] == (
        BOUNDED_RARITY_AWARE_V1_WITH_FIXED_SECOND_PASS
    )


def test_d5_progress_checkpoints_are_monotonic(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    collector = _Collector(checkpoint, python_profile_enabled=False)
    collector.start_pipeline()
    first = json.loads(checkpoint.read_text(encoding="utf-8"))
    collector.checkpoint()
    second = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert second["pipeline_elapsed_seconds"] >= first["pipeline_elapsed_seconds"]
    assert "retrieval_partial" in second


def test_d6_timeout_cannot_report_completed():
    result = graduation.timeout_result(
        {"status": "COMPLETED", "active_sub_stage": "COMPLETED"},
        {}, bound=300.0, wall=300.1,
    )
    assert result["status"] == "TIMED_OUT"
    assert result["active_sub_stage"] == "TIMEOUT_AFTER_LAST_CHECKPOINT"


def test_d7_not_reached_is_used_instead_of_fabricated_zero():
    reachability = graduation.stage_reachability({
        "active_sub_stage": "CHAR_VECTOR",
        "bucket_seconds_partial": {"STANDARD_BLOCKING": 1.0},
        "completed_stages": {"CANONICAL_CATALOG": "SUCCEEDED"},
    })
    assert reachability["GF4_EVIDENCE_ACQUISITION"] == "NOT_REACHED"
    assert reachability["CHAR_VECTOR"] == "REACHED"


def test_d8_stage_timing_reconciliation():
    collector = _Collector(python_profile_enabled=False)
    collector.discovery_seconds = 10.0
    collector.elapsed["STANDARD_BLOCKING"] = 3.0
    values, _attributed, total = _decomposition(collector)
    assert sum(values.values()) == pytest.approx(total, abs=1e-6)


def test_d9_cache_sql_parameter_bound_is_preserved():
    assert graduation.MAX_SELECT_PARAMETERS == 902


def test_d10_benchmark_truth_is_absent_from_production_path():
    source = inspect.getsource(graduation)
    assert ".truth" not in source
    assert "BenchmarkTruth" not in source


def test_d11_deprecated_write_contract_is_explicitly_zero():
    source = inspect.getsource(benchmark_configuration)
    assert "group_first_primary" in source
    assert "group_first_shadow_comparison_enabled=False" in source


def test_d12_safety_counters_are_reported_from_persisted_scale_result():
    source = inspect.getsource(graduation.run_graduation_benchmark)
    assert "scale.to_dict()" in source
    assert "persisted_counts" in source


def test_d13_no_configured_or_default_database_access():
    source = inspect.getsource(graduation.run_graduation_benchmark)
    assert "database_url" not in source
    assert "inventory_detector.db" not in source
    assert '"configured_database_accessed": False' in source


def test_d14_no_schema_migration_or_dependency_hook():
    source = inspect.getsource(graduation)
    assert "alembic" not in source.casefold()
    assert "subprocess" not in source.casefold()
    assert "pip install" not in source.casefold()
