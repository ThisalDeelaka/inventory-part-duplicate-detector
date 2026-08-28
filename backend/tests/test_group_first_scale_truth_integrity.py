"""GF-12A1-PRE focused truth-integrity tests TG1 through TG18."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.benchmarks.contracts import stable_fingerprint
from app.benchmarks.group_first_scale import benchmark_configuration
from app.benchmarks.group_first_scale_generator import (
    BenchmarkTruth,
    BenchmarkTruthIntegrityError,
    TRUTH_V2_ADDITIONAL_CORRECTION_CLASSIFICATION,
    TRUTH_V2_BOUNDARY_RULE,
    TRUTH_V2_CORRECTION_CLASSIFICATION,
    TRUTH_VERSION_V1,
    TRUTH_VERSION_V2,
    generate_corrected_scale_corpus,
    generate_scale_corpus,
    validate_benchmark_truth,
)


CANONICAL_SCALES = (500, 5_000, 20_000, 50_000, 100_000)


def _assert_integrity(records):
    corpus = generate_corrected_scale_corpus(records, seed=1101)
    validate_benchmark_truth(corpus.truth, record_count=records)
    assert all(len(members) >= 2 for _identity, members in corpus.truth.duplicate_sets)
    return corpus


def test_tg1_reproduce_old_50k_singleton_defect():
    old = generate_scale_corpus(
        50_000, seed=1101, truth_version=TRUTH_VERSION_V1
    )
    assert [item for item in old.truth.duplicate_sets if len(item[1]) == 1] == [
        ("cross-site-3755308", (31_249,))
    ]
    with pytest.raises(BenchmarkTruthIntegrityError, match="TRUTH_GROUP_SINGLETON"):
        validate_benchmark_truth(old.truth, record_count=50_000)


def test_tg2_root_cause_classification_and_boundary_rule_are_recorded():
    assert TRUTH_V2_CORRECTION_CLASSIFICATION == (
        "A. PARTIAL_GROUP_AFTER_CORPUS_BOUNDARY"
    )
    assert "retain requested production records" in TRUTH_V2_BOUNDARY_RULE
    assert "complete generated scenario" in TRUTH_V2_BOUNDARY_RULE
    assert TRUTH_V2_ADDITIONAL_CORRECTION_CLASSIFICATION == (
        "E. TRUTH_ASSEMBLY_DEFECT"
    )


def test_tg3_corrected_500_truth_integrity():
    _assert_integrity(500)


def test_tg4_corrected_5k_truth_integrity():
    _assert_integrity(5_000)


def test_tg5_corrected_20k_truth_integrity():
    _assert_integrity(20_000)


def test_tg6_corrected_50k_truth_integrity():
    _assert_integrity(50_000)


def test_tg7_corrected_100k_truth_integrity():
    _assert_integrity(100_000)


def test_tg8_cross_site_3755308_is_absent_when_incomplete_in_v2():
    corrected = generate_corrected_scale_corpus(50_000, seed=1101)
    identities = {identity for identity, _members in corrected.truth.duplicate_sets}
    assert "cross-site-3755308" not in identities
    assert corrected.truth.scenario_by_source_row[31_249] == "S5"
    assert len(corrected.records) == 50_000


@pytest.mark.parametrize("members,code", [
    ((), "TRUTH_GROUP_EMPTY"),
    ((0,), "TRUTH_GROUP_SINGLETON"),
])
def test_tg9_no_empty_or_singleton_positive_groups(members, code):
    truth = BenchmarkTruth((("bad", members),), (), (), ("S2", "S2"))
    with pytest.raises(BenchmarkTruthIntegrityError, match=code):
        validate_benchmark_truth(truth, record_count=2)


def test_tg10_no_unknown_truth_members():
    truth = BenchmarkTruth((("bad", (0, 2)),), (), (), ("S2", "S2"))
    with pytest.raises(BenchmarkTruthIntegrityError, match="TRUTH_RECORD_REFERENCE_INVALID"):
        validate_benchmark_truth(truth, record_count=2)


def test_tg11_no_duplicate_positive_membership():
    truth = BenchmarkTruth(
        (("a", (0, 1)), ("b", (1, 2))), (), (), ("S2", "S2", "S2")
    )
    with pytest.raises(BenchmarkTruthIntegrityError, match="TRUTH_RECORD_MULTI_MEMBERSHIP"):
        validate_benchmark_truth(truth, record_count=3)
    duplicate_member = BenchmarkTruth(
        (("a", (0, 0)),), (), (), ("S2", "S2")
    )
    with pytest.raises(BenchmarkTruthIntegrityError, match="TRUTH_GROUP_MEMBER_DUPLICATE"):
        validate_benchmark_truth(duplicate_member, record_count=2)
    duplicate_id = BenchmarkTruth(
        (("a", (0, 1)), ("a", (2, 3))), (), (), ("S2",) * 4
    )
    with pytest.raises(BenchmarkTruthIntegrityError, match="TRUTH_GROUP_ID_DUPLICATE"):
        validate_benchmark_truth(duplicate_id, record_count=4)


def test_tg12_no_positive_cannot_link_contradiction():
    truth = BenchmarkTruth(
        (("a", (0, 1)),), ((0, 1),), (), ("S2", "S2")
    )
    with pytest.raises(
        BenchmarkTruthIntegrityError,
        match="TRUTH_CANNOT_LINK_CONTRADICTS_IDENTITY",
    ):
        validate_benchmark_truth(truth, record_count=2)


def test_tg13_deterministic_group_ordering():
    first = generate_corrected_scale_corpus(50_000, seed=1101)
    second = generate_corrected_scale_corpus(50_000, seed=1101)
    assert first.truth.duplicate_sets == second.truth.duplicate_sets


def test_tg14_deterministic_truth_fingerprint():
    first = generate_corrected_scale_corpus(50_000, seed=1101)
    second = generate_corrected_scale_corpus(50_000, seed=1101)
    assert first.truth_fingerprint == second.truth_fingerprint


def test_tg15_v1_is_default_and_historical_fingerprint_is_unchanged():
    default = generate_scale_corpus(50_000, seed=1101)
    explicit = generate_scale_corpus(
        50_000, seed=1101, truth_version=TRUTH_VERSION_V1
    )
    assert default.truth_version == explicit.truth_version == TRUTH_VERSION_V1
    assert default.generator_fingerprint == explicit.generator_fingerprint == (
        "42be1d818085d2562a6c20edf65355c34beb4d3e81e88f869c78920cdcdf1263"
    )


@pytest.mark.parametrize("records", CANONICAL_SCALES)
def test_tg16_production_record_fingerprint_is_preserved(records):
    old = generate_scale_corpus(records, seed=1101, truth_version=TRUTH_VERSION_V1)
    corrected = generate_scale_corpus(
        records, seed=1101, truth_version=TRUTH_VERSION_V2
    )
    assert old.records.to_dict("records") == corrected.records.to_dict("records")
    assert stable_fingerprint(old.records.to_dict("records")) == stable_fingerprint(
        corrected.records.to_dict("records")
    )


def test_tg17_provider_zero_and_truth_stays_benchmark_only():
    config = benchmark_configuration()
    assert config.llm_provider == config.group_llm_provider == "none"
    app_root = Path(__file__).parents[1] / "app"
    offenders = []
    for path in app_root.rglob("*.py"):
        if "benchmarks" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "group_first_scale_generator" in text or "BenchmarkTruth" in text:
            offenders.append(path)
    assert offenders == []


def test_tg18_no_schema_migration_or_dependency_change():
    from app.benchmarks import group_first_scale_generator as generator

    source = inspect.getsource(generator).casefold()
    assert "app.db" not in source
    assert "alembic" not in source
    assert "migration" not in source
    assert "pip install" not in source
    assert "subprocess" not in source
