"""Offline reviewer-agreement and blinded-pilot outcome diagnostics."""

from __future__ import annotations

import dataclasses
import itertools
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.benchmarks.contracts import canonical_json, stable_fingerprint
from app.benchmarks.human_review_pilot import (
    BlindedReviewPack,
    PilotEvidenceClassification,
    PrivateEvaluationManifest,
)
from app.benchmarks.human_review_protocol import (
    HUMAN_REVIEW_PROTOCOL_VERSION,
    HumanReviewLabel,
    HumanReviewValidationError,
    REVIEW_LABEL_SCHEMA_VERSION,
    REVIEW_PACK_VERSION,
    ReviewCompletionState,
    ReviewerRole,
    ReviewStratum,
    decidable_partition,
    validate_human_review_label,
)


HUMAN_REVIEW_EVALUATION_VERSION = "gf12-human-review-evaluation-v1"
REVIEWER_AGREEMENT_LABEL = "REVIEWER AGREEMENT DIAGNOSTICS"


@dataclass(frozen=True)
class ReviewRatio:
    numerator: int
    denominator: int
    value: float | None


@dataclass(frozen=True)
class ReviewerAgreementDiagnostics:
    label: str
    review_unit_id: str
    reviewer_a_code: str
    reviewer_b_code: str
    comparable_record_count: int
    exact_partition_agreement: bool
    pairwise_co_membership_agreement: ReviewRatio
    pairwise_precision_b_against_a: ReviewRatio
    pairwise_recall_b_against_a: ReviewRatio
    pairwise_f1_b_against_a: float | None


@dataclass(frozen=True)
class HumanOutcomeStratumMetrics:
    stratum: ReviewStratum
    review_unit_count: int
    evaluable_unit_count: int
    insufficient_evidence_unit_count: int
    insufficient_evidence_rate: ReviewRatio
    exact_human_group_match_rate: ReviewRatio | None
    human_confirmed_same_item_membership_rate: ReviewRatio | None
    human_observed_merge_errors: int | None
    human_observed_split_errors: int | None
    latent_duplicate_set_yield: ReviewRatio | None
    latent_duplicate_group_count: int | None
    latent_duplicate_record_count: int | None


@dataclass(frozen=True)
class HumanPilotEvaluationResult:
    evaluation_version: str
    review_protocol_version: str
    review_pack_version: str
    review_label_schema_version: str
    dataset_id: str
    dataset_version: str
    dataset_fingerprint: str
    evidence_classification: PilotEvidenceClassification
    blinded_pack_fingerprint: str
    private_manifest_fingerprint: str
    completed_label_count: int
    stratum_metrics: tuple[HumanOutcomeStratumMetrics, ...]
    evaluation_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    def to_json(self, *, pretty: bool = True) -> str:
        return canonical_json(self, pretty=pretty)


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in sorted(value.items())}
    return value


def _ratio(numerator: int, denominator: int) -> ReviewRatio:
    return ReviewRatio(
        numerator,
        denominator,
        None if denominator == 0 else round(numerator / denominator, 12),
    )


def _f1(precision: ReviewRatio, recall: ReviewRatio) -> float | None:
    if precision.value is None or recall.value is None:
        return None
    total = precision.value + recall.value
    return 0.0 if total == 0 else round(
        2 * precision.value * recall.value / total, 12
    )


def _pairs(groups: tuple[tuple[str, ...], ...]) -> set[tuple[str, str]]:
    return {
        tuple(pair)
        for group in groups
        if len(group) >= 2
        for pair in itertools.combinations(sorted(group), 2)
    }


def _insufficient_refs(label: HumanReviewLabel) -> set[str]:
    return set(label.insufficient_evidence_refs).union(
        reference
        for group in label.insufficient_evidence_groups
        for reference in group
    )


def _restricted_partition(
    label: HumanReviewLabel, allowed: set[str]
) -> tuple[tuple[str, ...], ...]:
    blocks = []
    for block in decidable_partition(label):
        reduced = tuple(reference for reference in block if reference in allowed)
        if reduced:
            blocks.append(reduced)
    return tuple(sorted(blocks))


def evaluate_reviewer_agreement(
    reviewer_a: HumanReviewLabel,
    reviewer_b: HumanReviewLabel,
) -> ReviewerAgreementDiagnostics:
    validate_human_review_label(reviewer_a)
    validate_human_review_label(reviewer_b)
    if reviewer_a.reviewer_role != ReviewerRole.REVIEWER or reviewer_b.reviewer_role != ReviewerRole.REVIEWER:
        raise HumanReviewValidationError("INDEPENDENT_REVIEWER_ROLE_REQUIRED")
    if reviewer_a.reviewer_code == reviewer_b.reviewer_code:
        raise HumanReviewValidationError("INDEPENDENT_REVIEWERS_REQUIRED")
    if reviewer_a.review_unit_id != reviewer_b.review_unit_id:
        raise HumanReviewValidationError("AGREEMENT_REVIEW_UNIT_MISMATCH")
    if reviewer_a.record_refs_presented != reviewer_b.record_refs_presented:
        raise HumanReviewValidationError("AGREEMENT_PRESENTED_RECORD_MISMATCH")
    if (
        reviewer_a.dataset_id,
        reviewer_a.dataset_version,
        reviewer_a.review_pack_version,
    ) != (
        reviewer_b.dataset_id,
        reviewer_b.dataset_version,
        reviewer_b.review_pack_version,
    ):
        raise HumanReviewValidationError("AGREEMENT_CONTEXT_MISMATCH")
    if reviewer_a.completion_state != ReviewCompletionState.COMPLETE or reviewer_b.completion_state != ReviewCompletionState.COMPLETE:
        raise HumanReviewValidationError("COMPLETE_REVIEW_REQUIRED")

    allowed = set(reviewer_a.record_refs_presented) - _insufficient_refs(
        reviewer_a
    ) - _insufficient_refs(reviewer_b)
    partition_a = _restricted_partition(reviewer_a, allowed)
    partition_b = _restricted_partition(reviewer_b, allowed)
    pairs_a = _pairs(partition_a)
    pairs_b = _pairs(partition_b)
    all_pairs = set(itertools.combinations(sorted(allowed), 2))
    matches = sum((pair in pairs_a) == (pair in pairs_b) for pair in all_pairs)
    true_positive = len(pairs_a & pairs_b)
    precision = _ratio(true_positive, len(pairs_b))
    recall = _ratio(true_positive, len(pairs_a))
    return ReviewerAgreementDiagnostics(
        label=REVIEWER_AGREEMENT_LABEL,
        review_unit_id=reviewer_a.review_unit_id,
        reviewer_a_code=reviewer_a.reviewer_code,
        reviewer_b_code=reviewer_b.reviewer_code,
        comparable_record_count=len(allowed),
        exact_partition_agreement=(
            partition_a == partition_b
            and _insufficient_refs(reviewer_a) == _insufficient_refs(reviewer_b)
        ),
        pairwise_co_membership_agreement=_ratio(matches, len(all_pairs)),
        pairwise_precision_b_against_a=precision,
        pairwise_recall_b_against_a=recall,
        pairwise_f1_b_against_a=_f1(precision, recall),
    )


def validate_labels_for_pack(
    pack: BlindedReviewPack,
    labels: tuple[HumanReviewLabel, ...],
) -> tuple[HumanReviewLabel, ...]:
    units = {
        unit.review_unit_id: tuple(
            record.stable_record_reference for record in unit.records
        )
        for unit in pack.review_units
    }
    seen = set()
    validated = []
    for label in labels:
        validate_human_review_label(label)
        if label.review_unit_id not in units:
            raise HumanReviewValidationError("UNKNOWN_REVIEW_UNIT")
        if label.record_refs_presented != units[label.review_unit_id]:
            raise HumanReviewValidationError("REVIEW_LABEL_RECORD_SET_MISMATCH")
        if label.dataset_id != pack.dataset_id or label.dataset_version != pack.dataset_version:
            raise HumanReviewValidationError("REVIEW_LABEL_DATASET_MISMATCH")
        key = (label.review_unit_id, label.reviewer_role, label.reviewer_code)
        if key in seen:
            raise HumanReviewValidationError("DUPLICATE_REVIEWER_LABEL")
        seen.add(key)
        validated.append(label)
    return tuple(validated)


def _effective_labels(
    pack: BlindedReviewPack,
    labels: tuple[HumanReviewLabel, ...],
) -> dict[str, HumanReviewLabel]:
    by_unit: dict[str, list[HumanReviewLabel]] = {}
    for label in validate_labels_for_pack(pack, labels):
        if label.completion_state == ReviewCompletionState.COMPLETE:
            by_unit.setdefault(label.review_unit_id, []).append(label)
    effective = {}
    for unit_id, items in by_unit.items():
        adjudicators = [item for item in items if item.reviewer_role == ReviewerRole.ADJUDICATOR]
        reviewers = [item for item in items if item.reviewer_role == ReviewerRole.REVIEWER]
        if len(adjudicators) > 1:
            raise HumanReviewValidationError("MULTIPLE_ADJUDICATOR_LABELS")
        if adjudicators:
            effective[unit_id] = adjudicators[0]
        elif len(reviewers) == 1:
            effective[unit_id] = reviewers[0]
        elif len(reviewers) > 1:
            raise HumanReviewValidationError("ADJUDICATION_REQUIRED")
    return effective


def _partition_blocks(label: HumanReviewLabel) -> tuple[set[str], ...]:
    return tuple(set(block) for block in decidable_partition(label))


def evaluate_human_pilot_outcomes(
    pack: BlindedReviewPack,
    manifest: PrivateEvaluationManifest,
    labels: tuple[HumanReviewLabel, ...],
) -> HumanPilotEvaluationResult:
    if manifest.blinded_pack_fingerprint != pack.pack_fingerprint:
        raise HumanReviewValidationError("PACK_MANIFEST_FINGERPRINT_MISMATCH")
    if (
        pack.dataset_id,
        pack.dataset_version,
        pack.dataset_fingerprint,
        pack.evidence_classification,
    ) != (
        manifest.dataset_id,
        manifest.dataset_version,
        manifest.dataset_fingerprint,
        manifest.evidence_classification,
    ):
        raise HumanReviewValidationError("PACK_MANIFEST_CONTEXT_MISMATCH")
    effective = _effective_labels(pack, labels)
    manifest_units = {unit.review_unit_id: unit for unit in manifest.review_units}

    metrics = []
    for stratum, _target in (
        (item.stratum, item.target_count) for item in manifest.sampling_counts
    ):
        units = [unit for unit in manifest.review_units if unit.sampling_stratum == stratum]
        available_labels = [effective[unit.review_unit_id] for unit in units if unit.review_unit_id in effective]
        insufficient = sum(bool(_insufficient_refs(label)) for label in available_labels)
        evaluable = [label for label in available_labels if not _insufficient_refs(label)]
        accepted = stratum in {
            ReviewStratum.LIKELY_DUPLICATE_GROUP,
            ReviewStratum.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        }

        if accepted:
            exact = 0
            confirmed_pairs = 0
            system_pairs = 0
            merges = 0
            splits = 0
            for label in evaluable:
                unit = manifest_units[label.review_unit_id]
                system_groups = tuple(tuple(group) for group in unit.system_grouping)
                human_groups = label.same_item_groups
                exact += tuple(sorted(system_groups)) == tuple(sorted(human_groups))
                predicted_pairs = _pairs(system_groups)
                human_pairs = _pairs(human_groups)
                confirmed_pairs += len(predicted_pairs & human_pairs)
                system_pairs += len(predicted_pairs)
                human_blocks = _partition_blocks(label)
                merges += sum(
                    len({index for index, block in enumerate(human_blocks) if block & set(group)}) > 1
                    for group in system_groups
                )
                splits += sum(
                    sum(bool(set(group) & set(human_group)) for group in system_groups) > 1
                    for human_group in human_groups
                )
            exact_rate = _ratio(exact, len(evaluable))
            membership_rate = _ratio(confirmed_pairs, system_pairs)
            latent_yield = None
            latent_groups = None
            latent_records = None
        else:
            latent_positive_units = sum(bool(label.same_item_groups) for label in evaluable)
            exact_rate = None
            membership_rate = None
            merges = None
            splits = None
            latent_yield = _ratio(latent_positive_units, len(evaluable))
            latent_groups = sum(len(label.same_item_groups) for label in evaluable)
            latent_records = sum(
                len(group) for label in evaluable for group in label.same_item_groups
            )

        metrics.append(HumanOutcomeStratumMetrics(
            stratum=stratum,
            review_unit_count=len(units),
            evaluable_unit_count=len(evaluable),
            insufficient_evidence_unit_count=insufficient,
            insufficient_evidence_rate=_ratio(insufficient, len(available_labels)),
            exact_human_group_match_rate=exact_rate,
            human_confirmed_same_item_membership_rate=membership_rate,
            human_observed_merge_errors=merges,
            human_observed_split_errors=splits,
            latent_duplicate_set_yield=latent_yield,
            latent_duplicate_group_count=latent_groups,
            latent_duplicate_record_count=latent_records,
        ))

    payload = {
        "evaluation_version": HUMAN_REVIEW_EVALUATION_VERSION,
        "review_protocol_version": HUMAN_REVIEW_PROTOCOL_VERSION,
        "review_pack_version": REVIEW_PACK_VERSION,
        "review_label_schema_version": REVIEW_LABEL_SCHEMA_VERSION,
        "dataset_id": pack.dataset_id,
        "dataset_version": pack.dataset_version,
        "dataset_fingerprint": pack.dataset_fingerprint,
        "evidence_classification": pack.evidence_classification,
        "blinded_pack_fingerprint": pack.pack_fingerprint,
        "private_manifest_fingerprint": manifest.manifest_fingerprint,
        "completed_label_count": len(effective),
        "stratum_metrics": tuple(metrics),
    }
    return HumanPilotEvaluationResult(
        **payload,
        evaluation_fingerprint=stable_fingerprint(payload),
    )
