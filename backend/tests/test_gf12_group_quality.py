"""GF-12A1 focused acceptance tests V12-1 through V12-26."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.benchmarks import gf12_group_quality as quality
from app.benchmarks.gf12_group_quality import (
    EvaluationDataError,
    GroupQualityEvaluationInput,
    GroupQualityTruth,
    PredictedIdentityGroup,
    PredictedOutcome,
    TruthIdentityGroup,
    evaluate_group_quality,
    truth_from_benchmark,
)
from app.benchmarks.group_first_scale_generator import (
    CANONICAL_SCENARIO,
    GENERATOR_VERSION,
    TRUTH_VERSION_V1,
    TRUTH_VERSION_V2,
    generate_corrected_scale_corpus,
    generate_scale_corpus,
)
from app.benchmarks.group_first_scale import benchmark_configuration


def _truth(*groups, records=12, cannot_links=(), scenarios=None):
    return GroupQualityTruth(
        corpus_version=GENERATOR_VERSION,
        truth_version=TRUTH_VERSION_V2,
        record_count=records,
        groups=tuple(TruthIdentityGroup(name, tuple(members)) for name, members in groups),
        cannot_link_pairs=tuple(cannot_links),
        bridge_sets=(),
        scenario_by_source_row=tuple(scenarios or ("S2",) * records),
    )


def _input(*groups, records=12, conflicts=(), deferred=(), unassigned=(), scan_id=1):
    return GroupQualityEvaluationInput(
        corpus_id="fixture-v1",
        corpus_version=GENERATOR_VERSION,
        truth_version=TRUTH_VERSION_V2,
        record_count=records,
        seed=1101,
        scan_id=scan_id,
        product_result_fingerprint="product-fingerprint",
        groups=tuple(PredictedIdentityGroup(ref, item_scan, status, tuple(members))
                     for ref, item_scan, status, members in groups),
        conflicts=tuple(PredictedOutcome(ref, item_scan, tuple(members))
                        for ref, item_scan, members in conflicts),
        deferred=tuple(PredictedOutcome(ref, item_scan, tuple(members))
                       for ref, item_scan, members in deferred),
        unassigned_source_rows=tuple(unassigned),
    )


def _perfect():
    truth = _truth(("a", (0, 1)), ("b", (2, 3, 4)))
    prediction = _input(
        ("p-a", 1, quality.LIKELY, (0, 1)),
        ("p-b", 1, quality.REVIEW, (2, 3, 4)),
    )
    return evaluate_group_quality(prediction, truth)


def test_v12_1_evaluator_cannot_affect_production_decisions():
    truth = _truth(("a", (0, 1)))
    prediction = _input(("p", 1, quality.LIKELY, (0, 1)))
    before = repr(prediction)
    evaluate_group_quality(prediction, truth)
    assert repr(prediction) == before
    source = inspect.getsource(quality)
    assert "ScanRunner" not in source and "scan_runner" not in source


def test_v12_2_production_modules_do_not_import_benchmark_truth_or_evaluator():
    app_root = Path(__file__).parents[1] / "app"
    offenders = []
    for path in app_root.rglob("*.py"):
        if "benchmarks" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "gf12_group_quality" in text or "BenchmarkTruth" in text:
            offenders.append(path)
    assert offenders == []


def test_truth_group_uniqueness_edge_case():
    truth = _truth(("same", (0, 1)), ("same", (2, 3)))
    with pytest.raises(EvaluationDataError, match="TRUTH_GROUP_ID_DUPLICATE"):
        evaluate_group_quality(_input(), truth)


@pytest.mark.parametrize("truth,code", [
    (_truth(("a", (0, 12))), "TRUTH_RECORD_REFERENCE_INVALID"),
    (_truth(("a", (0, 1)), ("b", (1, 2))), "TRUTH_RECORD_MULTI_MEMBERSHIP"),
    (_truth(("a", (0,))), "TRUTH_GROUP_SINGLETON"),
    (_truth(("a", (0, 1)), cannot_links=((0, 1),)), "TRUTH_CANNOT_LINK_CONTRADICTS_IDENTITY"),
])
def test_truth_membership_edge_cases(truth, code):
    with pytest.raises(EvaluationDataError, match=code):
        evaluate_group_quality(_input(), truth)


def test_v12_3_truth_v2_integrity_is_validated_before_evaluation():
    corrected = generate_corrected_scale_corpus(500, seed=1101)
    converted = truth_from_benchmark(
        corrected.truth, 500, corpus_version=GENERATOR_VERSION,
        truth_version=TRUTH_VERSION_V2,
    )
    assert converted.truth_version == TRUTH_VERSION_V2
    historical_50k = generate_scale_corpus(
        50_000, seed=1101, truth_version=TRUTH_VERSION_V1
    )
    with pytest.raises(EvaluationDataError, match="CORRECTED_TRUTH_V2_REQUIRED"):
        truth_from_benchmark(
            historical_50k.truth, 50_000,
            corpus_version=GENERATOR_VERSION,
            truth_version=TRUTH_VERSION_V1,
        )


def test_v12_4_corpus_v1_production_records_are_preserved():
    historical = generate_scale_corpus(
        500, seed=1101, truth_version=TRUTH_VERSION_V1
    )
    corrected = generate_corrected_scale_corpus(500, seed=1101)
    assert historical.version == corrected.version == GENERATOR_VERSION
    assert historical.records.to_dict("records") == corrected.records.to_dict("records")


def test_v12_5_truth_version_is_recorded_in_result_and_fingerprint():
    result = _perfect()
    assert result.corpus_version == GENERATOR_VERSION
    assert result.truth_version == TRUTH_VERSION_V2
    assert TRUTH_VERSION_V2 in result.to_json()


def test_v12_6_exact_group_precision():
    result = evaluate_group_quality(
        _input(("exact", 1, quality.LIKELY, (0, 1)),
               ("spurious", 1, quality.REVIEW, (8, 9))),
        _truth(("a", (0, 1))),
    )
    assert result.primary_metrics.gq1_exact_group_precision.value == 0.5


def test_v12_7_exact_group_recall():
    result = evaluate_group_quality(
        _input(("exact", 1, quality.LIKELY, (0, 1))),
        _truth(("a", (0, 1)), ("b", (2, 3))),
    )
    assert result.primary_metrics.gq2_exact_group_recall.value == 0.5


def test_v12_8_exact_group_f1():
    result = evaluate_group_quality(
        _input(("exact", 1, quality.LIKELY, (0, 1)),
               ("spurious", 1, quality.REVIEW, (8, 9))),
        _truth(("a", (0, 1)), ("b", (2, 3))),
    )
    assert result.primary_metrics.gq3_exact_group_f1 == 0.5


def test_v12_9_member_weighted_coverage_uses_largest_clean_identity_set():
    result = evaluate_group_quality(
        _input(("partial", 1, quality.REVIEW, (0, 1)),
               ("exact", 1, quality.LIKELY, (3, 4))),
        _truth(("large", (0, 1, 2)), ("small", (3, 4))),
    )
    metric = result.primary_metrics.gq4_member_weighted_group_coverage
    assert (metric.numerator, metric.denominator, metric.value) == (4, 5, 0.8)


def test_v12_10_split_detection():
    result = evaluate_group_quality(
        _input(("left", 1, quality.REVIEW, (0, 1)),
               ("right", 1, quality.REVIEW, (2, 3))),
        _truth(("whole", (0, 1, 2, 3))),
    )
    assert result.primary_metrics.gq5_split_errors == 1


def test_v12_11_merge_detection():
    result = evaluate_group_quality(
        _input(("merged", 1, quality.REVIEW, (0, 1, 2, 3))),
        _truth(("a", (0, 1)), ("b", (2, 3))),
    )
    assert result.primary_metrics.gq6_merge_errors == 1


def test_v12_12_missed_group_detection():
    result = evaluate_group_quality(_input(), _truth(("a", (0, 1))))
    assert result.primary_metrics.gq7_missed_truth_groups == 1


def test_v12_13_spurious_group_detection():
    result = evaluate_group_quality(
        _input(("spurious", 1, quality.LIKELY, (8, 9))),
        _truth(("a", (0, 1))),
    )
    assert result.primary_metrics.gq8_spurious_predicted_groups == 1


def test_v12_14_pair_diagnostics_are_derived_from_groups():
    result = evaluate_group_quality(
        _input(("partial", 1, quality.REVIEW, (0, 1))),
        _truth(("a", (0, 1, 2))),
    )
    assert result.pair_diagnostics.precision.value == 1.0
    assert result.pair_diagnostics.recall.value == pytest.approx(1 / 3)
    assert result.pair_diagnostics.label.startswith("DIAGNOSTIC ONLY")


def test_v12_15_cannot_link_violation_detection():
    result = evaluate_group_quality(
        _input(("unsafe", 1, quality.REVIEW, (6, 7))),
        _truth(("a", (0, 1)), cannot_links=((6, 7),)),
    )
    assert result.safety_metrics.cannot_link_accepted_violations == 1
    assert not result.safety_metrics.passed


def test_v12_16_duplicate_membership_detection():
    result = evaluate_group_quality(
        _input(("a", 1, quality.LIKELY, (0, 1)),
               ("b", 1, quality.REVIEW, (1, 2))),
        _truth(("truth", (0, 1, 2))),
    )
    assert result.safety_metrics.duplicate_accepted_membership == 1
    assert result.safety_metrics.overlapping_accepted_review_membership == 1


def test_v12_17_singleton_detection():
    result = evaluate_group_quality(
        _input(("single", 1, quality.REVIEW, (0,))),
        _truth(("truth", (0, 1))),
    )
    assert result.safety_metrics.singleton_accepted_groups == 1


def test_v12_18_status_aware_breakdown_keeps_outcomes_distinct():
    truth = _truth(
        ("likely", (0, 1)), ("review", (2, 3)),
        ("conflict", (4, 5)), ("deferred", (6, 7)), ("missed", (8, 9)),
    )
    prediction = _input(
        ("likely", 1, quality.LIKELY, (0, 1)),
        ("review", 1, quality.REVIEW, (2, 3)),
        conflicts=(("conflict", 1, (4, 5)),),
        deferred=(("deferred", 1, (6, 7)),),
        unassigned=(8, 9),
    )
    status = evaluate_group_quality(prediction, truth).status_breakdown
    assert dataclass_values(status)[:5] == (1, 1, 1, 1, 1)


def dataclass_values(value):
    return tuple(getattr(value, field.name) for field in value.__dataclass_fields__.values())


def test_v12_19_group_size_stratification_and_na_semantics():
    truth = _truth(
        ("s2", (0, 1)), ("s3", (2, 3, 4)),
        records=20, scenarios=("S2",) * 20,
    )
    result = evaluate_group_quality(
        _input(("s2", 1, quality.LIKELY, (0, 1)), records=20), truth
    )
    buckets = {item.bucket: item for item in result.group_size_breakdown}
    assert buckets["size 2"].exact_recall == 1.0
    assert buckets["size 3"].exact_recall == 0.0
    assert buckets["size >10"].exact_recall is None
    assert buckets["size 2"].split_count == 0
    assert buckets["size 2"].merge_involvement_count == 0


def test_v12_20_scenario_stratification_uses_only_authoritative_labels():
    scenarios = ("S2", "S2", "S5", "S5")
    truth = _truth(("a", (0, 1)), ("b", (2, 3)), records=4, scenarios=scenarios)
    result = evaluate_group_quality(
        _input(("a", 1, quality.LIKELY, (0, 1)), records=4), truth
    )
    assert {item.scenario_label for item in result.scenario_breakdown} == {"S2", "S5"}
    assert all(item.protected_cannot_link_case_count == 0 for item in result.scenario_breakdown)
    assert all(item.bridge_case_count == 0 for item in result.scenario_breakdown)


def test_v12_21_serialization_is_deterministic():
    first = _perfect()
    second = _perfect()
    assert first.to_json() == second.to_json()


def test_v12_22_evaluation_fingerprint_is_deterministic_and_timestamp_free():
    first = _perfect()
    second = _perfect()
    assert first.evaluation_fingerprint == second.evaluation_fingerprint
    assert "timestamp" not in first.to_json().casefold()


def test_empty_and_zero_denominator_semantics_are_explicit():
    result = evaluate_group_quality(_input(records=0), _truth(records=0, scenarios=()))
    assert result.primary_metrics.gq1_exact_group_precision.value is None
    assert result.primary_metrics.gq2_exact_group_recall.value is None
    assert result.primary_metrics.gq3_exact_group_f1 is None
    assert result.pair_diagnostics.precision.value is None
    assert result.pair_diagnostics.recall.value is None


def test_v12_23_truth_v1_v2_isolation_has_no_fallback():
    historical_truth = replace_truth_version(_truth(("a", (0, 1))), TRUTH_VERSION_V1)
    historical_input = replace_input_truth_version(
        _input(("a", 1, quality.LIKELY, (0, 1))), TRUTH_VERSION_V1
    )
    with pytest.raises(EvaluationDataError, match="CORRECTED_TRUTH_V2_REQUIRED"):
        evaluate_group_quality(historical_input, historical_truth)


def replace_truth_version(value, truth_version):
    from dataclasses import replace
    return replace(value, truth_version=truth_version)


def replace_input_truth_version(value, truth_version):
    from dataclasses import replace
    return replace(value, truth_version=truth_version)


def test_v12_24_provider_calls_are_zero_by_contract():
    config = benchmark_configuration()
    assert config.llm_provider == config.group_llm_provider == "none"
    assert "provider" not in inspect.signature(evaluate_group_quality).parameters


def test_v12_25_evaluator_adds_no_schema_migration_or_dependency_hook():
    source = inspect.getsource(quality).casefold()
    assert "app.db" not in source
    assert "migration" not in source
    assert "alembic" not in source
    assert "pip install" not in source
    assert "subprocess" not in source


def test_v12_26_no_production_semantic_dependency_or_reimplementation():
    source = inspect.getsource(quality)
    assert "resolve_identity_groups" not in source
    assert "IdentityEdgeEvaluator" not in source
    assert "ScanRunner" not in source
    assert CANONICAL_SCENARIO not in source
