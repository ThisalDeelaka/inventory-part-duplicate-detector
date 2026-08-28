"""HR1-HR24: offline, blinded, group-first human-review validation."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from app.benchmarks.human_review_evaluation import (
    HUMAN_REVIEW_EVALUATION_VERSION,
    REVIEWER_AGREEMENT_LABEL,
    evaluate_human_pilot_outcomes,
    evaluate_reviewer_agreement,
    validate_labels_for_pack,
)
from app.benchmarks.human_review_pilot import (
    PILOT_SAMPLING_SEED,
    BlindedReviewPack,
    PilotCandidateUnit,
    PilotEvidenceClassification,
    ReviewStratum,
    build_blinded_review_pack,
    build_synthetic_smoke_review_pack,
)
from app.benchmarks.human_review_protocol import (
    BlindedReviewRecord,
    DatasetClassification,
    HUMAN_REVIEW_PROTOCOL_VERSION,
    HumanReviewLabel,
    HumanReviewReasonCode,
    HumanReviewValidationError,
    REVIEW_LABEL_SCHEMA_VERSION,
    REVIEW_PACK_VERSION,
    ReviewCompletionState,
    ReviewerConfidence,
    ReviewerRole,
    ValidationDatasetDescriptor,
    validate_human_review_label,
)


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _descriptor(classification=DatasetClassification.SYNTHETIC_ONLY):
    return ValidationDatasetDescriptor(
        dataset_id="gf12-test-fixture",
        dataset_version="v1",
        dataset_fingerprint="a" * 64,
        classification=classification,
    )


def _record(reference: str, index: int) -> BlindedReviewRecord:
    return BlindedReviewRecord(
        stable_record_reference=reference,
        source_row_reference=index,
        part_no=f"PN-{index}",
        description=f"Synthetic test item {index}",
        product_category="TEST",
        hsn_sac="0000",
        site_or_contract="SITE-X",
        uom="EA",
    )


def _unit(stratum: ReviewStratum, index: int, size: int = 3) -> PilotCandidateUnit:
    refs = tuple(
        f"{stratum.name.lower()}-{index:03d}-{offset:02d}"
        for offset in range(size)
    )
    records = tuple(_record(reference, index * 10 + offset) for offset, reference in enumerate(refs))
    system_grouping = (refs,) if stratum in {
        ReviewStratum.LIKELY_DUPLICATE_GROUP,
        ReviewStratum.POSSIBLE_DUPLICATE_GROUP_REVIEW,
    } else ()
    return PilotCandidateUnit(
        source_unit_reference=f"source-{stratum.value}-{index}",
        stratum=stratum,
        records=records,
        system_status=stratum.value,
        system_grouping=system_grouping,
        internal_evidence=(("safe_reference", f"evidence-{index}"),),
    )


def _candidate_units():
    units = []
    for stratum in ReviewStratum:
        units.extend(_unit(stratum, index) for index in range(3))
    return tuple(units)


def _build():
    return build_synthetic_smoke_review_pack(
        _descriptor(),
        production_result_fingerprint="product-fixture-v1",
        candidate_units=_candidate_units(),
    )


def _label(
    pack: BlindedReviewPack,
    unit_index: int,
    *,
    reviewer="reviewer-a",
    role=ReviewerRole.REVIEWER,
    groups=None,
    unmatched=None,
    insufficient=(),
    insufficient_groups=(),
    state=ReviewCompletionState.COMPLETE,
):
    unit = pack.review_units[unit_index]
    refs = tuple(record.stable_record_reference for record in unit.records)
    if groups is None:
        groups = (refs,)
    used = {reference for group in groups for reference in group}
    used.update(insufficient)
    used.update(reference for group in insufficient_groups for reference in group)
    if unmatched is None:
        unmatched = tuple(reference for reference in refs if reference not in used)
    return HumanReviewLabel(
        label_schema_version=REVIEW_LABEL_SCHEMA_VERSION,
        review_protocol_version=HUMAN_REVIEW_PROTOCOL_VERSION,
        review_pack_version=REVIEW_PACK_VERSION,
        review_unit_id=unit.review_unit_id,
        dataset_id=pack.dataset_id,
        dataset_version=pack.dataset_version,
        reviewer_code=reviewer,
        reviewer_role=role,
        record_refs_presented=refs,
        same_item_groups=tuple(sorted(tuple(sorted(group)) for group in groups)),
        unmatched_record_refs=tuple(sorted(unmatched)),
        insufficient_evidence_refs=tuple(sorted(insufficient)),
        insufficient_evidence_groups=tuple(
            sorted(tuple(sorted(group)) for group in insufficient_groups)
        ),
        confidence=ReviewerConfidence.HIGH,
        reason_codes=(HumanReviewReasonCode.EQUIVALENT_DESCRIPTION,),
        completion_state=state,
    )


def _expect_code(code, function, *args, **kwargs):
    with pytest.raises(HumanReviewValidationError) as exc_info:
        function(*args, **kwargs)
    assert exc_info.value.code == code


def test_hr1_human_review_modules_are_offline_only_and_reverse_import_safe():
    human_modules = tuple((APP_ROOT / "benchmarks").glob("human_review_*.py"))
    assert len(human_modules) == 3
    for path in human_modules:
        source = path.read_text(encoding="utf-8")
        assert "sqlalchemy" not in source.lower()
        assert "app.db" not in source
        assert "app.services.scan_runner" not in source
    for path in APP_ROOT.rglob("*.py"):
        if path in human_modules:
            continue
        assert "app.benchmarks.human_review" not in path.read_text(encoding="utf-8")


def test_hr2_authorized_dataset_gate_rejects_synthetic_and_unspecified():
    for classification in (
        DatasetClassification.SYNTHETIC_ONLY,
        DatasetClassification.UNSPECIFIED_NOT_AUTHORIZED,
    ):
        _expect_code(
            "HUMAN_REVIEW_DATASET_REQUIRED",
            build_blinded_review_pack,
            _descriptor(classification),
            production_result_fingerprint="product",
            candidate_units=_candidate_units(),
        )


def test_hr2_authorized_dataset_can_cross_gate_without_raw_data_persistence():
    result = build_blinded_review_pack(
        _descriptor(DatasetClassification.AUTHORIZED_HUMAN_VALIDATION_DATASET),
        production_result_fingerprint="product",
        candidate_units=_candidate_units(),
    )
    assert result.blinded_pack.evidence_classification == PilotEvidenceClassification.PILOT_EVIDENCE_ELIGIBLE


def test_hr3_seed_is_fixed_and_sampling_is_input_order_independent():
    first = _build()
    second = build_synthetic_smoke_review_pack(
        _descriptor(),
        production_result_fingerprint="product-fixture-v1",
        candidate_units=tuple(reversed(_candidate_units())),
    )
    assert first == second
    assert first.blinded_pack.sampling_seed == PILOT_SAMPLING_SEED
    _expect_code(
        "PILOT_SAMPLING_SEED_INVALID",
        build_synthetic_smoke_review_pack,
        _descriptor(),
        production_result_fingerprint="product-fixture-v1",
        candidate_units=_candidate_units(),
        seed=1202,
    )


def test_hr4_blinded_pack_excludes_status_scores_truth_and_strata():
    raw = _build().blinded_pack.to_json().lower()
    for forbidden in (
        "system_status", "system_score", "retrieval_channel", "rrf",
        "fusion_score", "gf4", "gf5", "benchmark_truth", "expected_label",
        "sampling_stratum", "internal_evidence",
    ):
        assert forbidden not in raw


def test_hr5_private_manifest_retains_post_review_metadata():
    manifest = _build().private_manifest
    unit = manifest.review_units[0]
    assert unit.system_status
    assert unit.sampling_stratum in ReviewStratum
    assert unit.internal_evidence
    assert unit.source_record_refs


def test_hr6_stable_unit_ids_do_not_depend_on_input_order():
    first = _build().blinded_pack
    second = build_synthetic_smoke_review_pack(
        _descriptor(),
        production_result_fingerprint="product-fixture-v1",
        candidate_units=tuple(reversed(_candidate_units())),
    ).blinded_pack
    assert [unit.review_unit_id for unit in first.review_units] == [
        unit.review_unit_id for unit in second.review_units
    ]


def test_hr7_group_first_partition_supports_multiple_groups_and_singletons():
    pack = _build().blinded_pack
    refs = tuple(record.stable_record_reference for record in pack.review_units[0].records)
    label = _label(pack, 0, groups=((refs[0], refs[1]),), unmatched=(refs[2],))
    validate_human_review_label(label)
    assert label.same_item_groups == ((refs[0], refs[1]),)


def test_hr8_duplicate_human_group_requires_two_members():
    label = _label(_build().blinded_pack, 0)
    invalid = dataclasses.replace(label, same_item_groups=((label.record_refs_presented[0],),))
    _expect_code("HUMAN_DUPLICATE_GROUP_TOO_SMALL", validate_human_review_label, invalid)


def test_hr9_record_in_two_human_groups_is_rejected():
    pack = _build().blinded_pack
    refs = tuple(record.stable_record_reference for record in pack.review_units[0].records)
    invalid = _label(
        pack, 0, groups=((refs[0], refs[1]), (refs[1], refs[2])), unmatched=(),
    )
    _expect_code(
        "RECORD_REPEATED_ACROSS_HUMAN_PARTITION", validate_human_review_label, invalid
    )


def test_hr10_unknown_review_unit_is_rejected():
    pack = _build().blinded_pack
    invalid = dataclasses.replace(_label(pack, 0), review_unit_id="unknown-unit")
    _expect_code("UNKNOWN_REVIEW_UNIT", validate_labels_for_pack, pack, (invalid,))


def test_hr11_unknown_record_and_pack_record_mismatch_are_rejected():
    pack = _build().blinded_pack
    label = _label(pack, 0)
    invalid = dataclasses.replace(
        label,
        same_item_groups=(tuple(sorted((*label.same_item_groups[0][:-1], "unknown-ref"))),),
    )
    _expect_code("UNKNOWN_PRESENTED_RECORD", validate_human_review_label, invalid)


def test_hr12_insufficient_evidence_is_explicit_and_excluded_from_evaluation():
    result = _build()
    pack = result.blinded_pack
    unit_index = next(
        index for index, unit in enumerate(result.private_manifest.review_units)
        if unit.sampling_stratum == ReviewStratum.CONFLICT
    )
    refs = tuple(record.stable_record_reference for record in pack.review_units[unit_index].records)
    label = _label(pack, unit_index, groups=(), unmatched=refs[1:], insufficient=(refs[0],))
    evaluation = evaluate_human_pilot_outcomes(pack, result.private_manifest, (label,))
    conflict = next(item for item in evaluation.stratum_metrics if item.stratum == ReviewStratum.CONFLICT)
    assert conflict.insufficient_evidence_unit_count == 1
    assert conflict.evaluable_unit_count == 0


def test_hr13_reviewer_independence_and_adjudication_seam():
    pack = _build().blinded_pack
    a = _label(pack, 0, reviewer="reviewer-a")
    same = _label(pack, 0, reviewer="reviewer-a")
    _expect_code("INDEPENDENT_REVIEWERS_REQUIRED", evaluate_reviewer_agreement, a, same)
    adjudicated = _label(pack, 0, reviewer="adjudicator-1", role=ReviewerRole.ADJUDICATOR)
    evaluation = evaluate_human_pilot_outcomes(
        pack, _build().private_manifest, (a, _label(pack, 0, reviewer="reviewer-b"), adjudicated)
    )
    assert evaluation.completed_label_count == 1


def test_hr14_exact_partition_agreement():
    pack = _build().blinded_pack
    diagnostics = evaluate_reviewer_agreement(
        _label(pack, 0, reviewer="reviewer-a"),
        _label(pack, 0, reviewer="reviewer-b"),
    )
    assert diagnostics.exact_partition_agreement is True


def test_hr15_pairwise_reviewer_agreement_diagnostics_are_typed():
    pack = _build().blinded_pack
    refs = tuple(record.stable_record_reference for record in pack.review_units[0].records)
    a = _label(pack, 0, reviewer="a", groups=(refs,), unmatched=())
    b = _label(pack, 0, reviewer="b", groups=((refs[0], refs[1]),), unmatched=(refs[2],))
    diagnostics = evaluate_reviewer_agreement(a, b)
    assert diagnostics.label == REVIEWER_AGREEMENT_LABEL
    assert diagnostics.pairwise_precision_b_against_a.value == 1.0
    assert diagnostics.pairwise_recall_b_against_a.value == pytest.approx(1 / 3)
    assert diagnostics.pairwise_co_membership_agreement.value == pytest.approx(1 / 3)


def test_hr16_accepted_and_review_human_metrics():
    result = _build()
    labels = []
    for index, unit in enumerate(result.private_manifest.review_units):
        if unit.sampling_stratum in {
            ReviewStratum.LIKELY_DUPLICATE_GROUP,
            ReviewStratum.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        }:
            labels.append(_label(result.blinded_pack, index, reviewer=f"r-{index}"))
    evaluation = evaluate_human_pilot_outcomes(
        result.blinded_pack, result.private_manifest, tuple(labels)
    )
    likely = next(item for item in evaluation.stratum_metrics if item.stratum == ReviewStratum.LIKELY_DUPLICATE_GROUP)
    assert likely.exact_human_group_match_rate.value == 1.0
    assert likely.human_confirmed_same_item_membership_rate.value == 1.0
    assert likely.human_observed_merge_errors == 0
    assert likely.human_observed_split_errors == 0


@pytest.mark.parametrize("stratum", [ReviewStratum.CONFLICT, ReviewStratum.DEFERRED])
def test_hr17_conflict_and_deferred_latent_positive_metrics(stratum):
    result = _build()
    index = next(
        position for position, unit in enumerate(result.private_manifest.review_units)
        if unit.sampling_stratum == stratum
    )
    evaluation = evaluate_human_pilot_outcomes(
        result.blinded_pack,
        result.private_manifest,
        (_label(result.blinded_pack, index, reviewer="reviewer-x"),),
    )
    metric = next(item for item in evaluation.stratum_metrics if item.stratum == stratum)
    assert metric.latent_duplicate_set_yield.value == 1.0
    assert metric.latent_duplicate_group_count == 1
    assert metric.latent_duplicate_record_count == 3


def test_hr18_unassigned_candidate_neighborhood_latent_positive_metrics():
    result = _build()
    index = next(
        position for position, unit in enumerate(result.private_manifest.review_units)
        if unit.sampling_stratum == ReviewStratum.UNASSIGNED_CANDIDATE_NEIGHBORHOOD
    )
    evaluation = evaluate_human_pilot_outcomes(
        result.blinded_pack,
        result.private_manifest,
        (_label(result.blinded_pack, index, reviewer="reviewer-u"),),
    )
    metric = next(
        item for item in evaluation.stratum_metrics
        if item.stratum == ReviewStratum.UNASSIGNED_CANDIDATE_NEIGHBORHOOD
    )
    assert metric.latent_duplicate_set_yield.value == 1.0


def test_hr19_result_has_no_population_recall_or_extrapolation_field():
    fields = {field.name for field in dataclasses.fields(
        type(evaluate_human_pilot_outcomes(
            _build().blinded_pack, _build().private_manifest, (),
        ))
    )}
    assert "population_recall" not in fields
    assert "estimated_population_recall" not in fields


def test_hr20_pack_and_evaluation_fingerprints_are_deterministic():
    first = _build()
    second = _build()
    assert first.blinded_pack.to_json() == second.blinded_pack.to_json()
    assert first.private_manifest.to_json() == second.private_manifest.to_json()
    label = _label(first.blinded_pack, 0)
    evaluation_a = evaluate_human_pilot_outcomes(first.blinded_pack, first.private_manifest, (label,))
    evaluation_b = evaluate_human_pilot_outcomes(second.blinded_pack, second.private_manifest, (label,))
    assert evaluation_a.evaluation_version == HUMAN_REVIEW_EVALUATION_VERSION
    assert evaluation_a == evaluation_b


def test_hr21_benchmark_truth_and_hidden_labels_never_enter_pack():
    raw = _build().blinded_pack.to_json().lower()
    assert "truth" not in raw
    assert "expected_label" not in raw
    assert "sampling_stratum" not in raw


def test_hr22_human_review_tooling_has_no_provider_or_network_imports():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (APP_ROOT / "benchmarks").glob("human_review_*.py")
    ).lower()
    for forbidden in (
        "import requests", "from requests", "import httpx", "from httpx",
        "import groq", "from groq", "import anthropic", "from anthropic",
        "api_key", "authorization_header",
    ):
        assert forbidden not in combined


def test_hr23_no_schema_migration_or_dependency_coupling():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (APP_ROOT / "benchmarks").glob("human_review_*.py")
    ).lower()
    for forbidden in ("sqlalchemy", "alembic", "app.db", "migration", "pydantic"):
        assert forbidden not in combined


def test_hr24_no_production_semantic_dependency_and_fixture_is_not_evidence():
    result = _build()
    assert result.blinded_pack.evidence_classification == PilotEvidenceClassification.SYNTHETIC_TEST_FIXTURE_ONLY
    assert result.private_manifest.evidence_classification == PilotEvidenceClassification.SYNTHETIC_TEST_FIXTURE_ONLY
    assert not any(
        "app.benchmarks.human_review" in path.read_text(encoding="utf-8")
        for path in APP_ROOT.rglob("*.py")
        if "benchmarks" not in path.parts
    )


def test_large_review_units_are_excluded_without_truncation_and_shortages_remain():
    large = _unit(ReviewStratum.CONFLICT, 999, size=13)
    result = build_synthetic_smoke_review_pack(
        _descriptor(),
        production_result_fingerprint="product",
        candidate_units=(large,),
    )
    assert result.blinded_pack.review_units == ()
    assert result.private_manifest.exclusions[0].reason_code == "LARGE_REVIEW_UNIT_EXCLUDED"
    assert result.private_manifest.exclusions[0].record_count == 13
    conflict = next(
        item for item in result.private_manifest.sampling_counts
        if item.stratum == ReviewStratum.CONFLICT
    )
    assert conflict.selected_count == 0
    assert conflict.shortage_count == 10


def test_label_file_is_deterministic_and_contains_no_free_text_field():
    label = _label(_build().blinded_pack, 0)
    assert label.to_json() == label.to_json()
    assert "free_text" not in label.to_dict()
    assert "notes" not in label.to_dict()
