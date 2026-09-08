"""Pure, offline GF-12 group-first quality evaluation.

Benchmark truth enters only through this module after an authority-selected
product snapshot exists. Production orchestration and decision modules must
never import this evaluator.
"""

from __future__ import annotations

import dataclasses
import itertools
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.benchmarks.contracts import canonical_json, stable_fingerprint
from app.benchmarks.group_first_scale_generator import (
    BenchmarkTruth,
    TRUTH_VERSION_V2,
    validate_benchmark_truth,
)


EVALUATION_VERSION = "gf12-group-quality-v1"
LIKELY = "LIKELY_DUPLICATE_GROUP"
REVIEW = "POSSIBLE_DUPLICATE_GROUP_REVIEW"
ACCEPTED_STATUSES = frozenset({LIKELY, REVIEW})
SIZE_BUCKETS = ("size 2", "size 3", "size 4-5", "size 6-10", "size >10")


class EvaluationDataError(ValueError):
    """Fail-closed error for invalid offline truth or evaluation input."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TruthIdentityGroup:
    truth_group_id: str
    source_row_indices: tuple[int, ...]


@dataclass(frozen=True)
class GroupQualityTruth:
    corpus_version: str
    truth_version: str
    record_count: int
    groups: tuple[TruthIdentityGroup, ...]
    cannot_link_pairs: tuple[tuple[int, int], ...]
    bridge_sets: tuple[tuple[int, ...], ...]
    scenario_by_source_row: tuple[str, ...]


@dataclass(frozen=True)
class PredictedIdentityGroup:
    group_reference: str
    scan_id: int
    status: str
    source_row_indices: tuple[int, ...]


@dataclass(frozen=True)
class PredictedOutcome:
    outcome_reference: str
    scan_id: int
    source_row_indices: tuple[int, ...]


@dataclass(frozen=True)
class GroupQualityEvaluationInput:
    corpus_id: str
    corpus_version: str
    truth_version: str
    record_count: int
    seed: int
    scan_id: int
    product_result_fingerprint: str
    groups: tuple[PredictedIdentityGroup, ...]
    conflicts: tuple[PredictedOutcome, ...]
    deferred: tuple[PredictedOutcome, ...]
    unassigned_source_rows: tuple[int, ...]
    source_fingerprint_before: str | None = None
    source_fingerprint_after: str | None = None


@dataclass(frozen=True)
class RatioMetric:
    numerator: int
    denominator: int
    value: float | None


@dataclass(frozen=True)
class PrimaryGroupMetrics:
    gq1_exact_group_precision: RatioMetric
    gq2_exact_group_recall: RatioMetric
    gq3_exact_group_f1: float | None
    gq4_member_weighted_group_coverage: RatioMetric
    gq5_split_errors: int
    gq6_merge_errors: int
    gq7_missed_truth_groups: int
    gq8_spurious_predicted_groups: int


@dataclass(frozen=True)
class PairDiagnosticMetrics:
    label: str
    precision: RatioMetric
    recall: RatioMetric
    f1: float | None


@dataclass(frozen=True)
class EvaluationSafetyMetrics:
    cannot_link_accepted_violations: int
    duplicate_accepted_membership: int
    singleton_accepted_groups: int
    overlapping_accepted_review_membership: int
    cross_scan_contamination: int
    source_record_mutation: int | None

    @property
    def passed(self) -> bool:
        values = (
            self.cannot_link_accepted_violations,
            self.duplicate_accepted_membership,
            self.singleton_accepted_groups,
            self.overlapping_accepted_review_membership,
            self.cross_scan_contamination,
        )
        return all(value == 0 for value in values) and self.source_record_mutation in (0, None)


@dataclass(frozen=True)
class StatusBreakdown:
    truth_groups_recovered_as_likely: int
    truth_groups_recovered_as_review: int
    truth_groups_represented_only_by_conflict: int
    truth_groups_represented_only_by_deferred: int
    truth_groups_completely_missed: int
    likely_predicted_group_count: int
    review_predicted_group_count: int
    conflict_outcome_count: int
    deferred_outcome_count: int
    unassigned_record_count: int


@dataclass(frozen=True)
class GroupSizeBreakdown:
    bucket: str
    truth_group_count: int
    exact_recovered_count: int
    exact_recall: float | None
    split_count: int
    merge_involvement_count: int


@dataclass(frozen=True)
class ScenarioBreakdown:
    scenario_label: str
    record_count: int
    truth_group_count: int
    exact_recovered_count: int
    conflict_or_deferred_truth_group_count: int
    completely_missed_truth_group_count: int
    protected_cannot_link_case_count: int
    bridge_case_count: int


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in sorted(value.items())}
    return value


@dataclass(frozen=True)
class GroupQualityEvaluationResult:
    evaluation_version: str
    corpus_id: str
    corpus_version: str
    truth_version: str
    record_count: int
    seed: int
    scan_id: int
    product_result_fingerprint: str
    predicted_group_count: int
    truth_group_count: int
    primary_metrics: PrimaryGroupMetrics
    pair_diagnostics: PairDiagnosticMetrics
    safety_metrics: EvaluationSafetyMetrics
    status_breakdown: StatusBreakdown
    group_size_breakdown: tuple[GroupSizeBreakdown, ...]
    scenario_breakdown: tuple[ScenarioBreakdown, ...]
    evaluation_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    def to_json(self, *, pretty: bool = True) -> str:
        return canonical_json(self, pretty=pretty)


def truth_from_benchmark(
    truth: BenchmarkTruth, record_count: int, *, corpus_version: str,
    truth_version: str,
) -> GroupQualityTruth:
    if truth_version != TRUTH_VERSION_V2:
        raise EvaluationDataError("CORRECTED_TRUTH_V2_REQUIRED")
    try:
        validate_benchmark_truth(truth, record_count=record_count)
    except ValueError as exc:
        raise EvaluationDataError(getattr(exc, "code", "TRUTH_INTEGRITY_INVALID")) from exc
    cannot_links = set()
    for members in truth.protected_conflict_sets:
        cannot_links.update(tuple(sorted(pair)) for pair in itertools.combinations(members, 2))
    return GroupQualityTruth(
        corpus_version=corpus_version,
        truth_version=truth_version,
        record_count=record_count,
        groups=tuple(
            TruthIdentityGroup(identity, tuple(members))
            for identity, members in truth.duplicate_sets
        ),
        cannot_link_pairs=tuple(sorted(cannot_links)),
        bridge_sets=tuple(tuple(members) for members in truth.bridge_sets),
        scenario_by_source_row=tuple(truth.scenario_by_source_row),
    )


def input_from_identity_read_snapshot(
    snapshot, *, corpus_id: str, seed: int,
    corpus_version: str, truth_version: str,
    source_row_by_record_reference: dict[str, int] | None = None,
    source_fingerprint_before: str | None = None,
    source_fingerprint_after: str | None = None,
) -> GroupQualityEvaluationInput:
    """Adapt only the authoritative downstream read snapshot; never recompute groups."""

    def member_rows(items):
        rows = []
        for item in items:
            value = item.source_row_index
            if value is None:
                raise EvaluationDataError("PRODUCT_MEMBER_SOURCE_ROW_MISSING")
            rows.append(value)
        return tuple(sorted(rows))

    groups = tuple(PredictedIdentityGroup(
        group_reference=item.versioned_group_key.group_reference,
        scan_id=item.versioned_group_key.scan_id,
        status=item.status.value,
        source_row_indices=member_rows(item.members),
    ) for item in snapshot.groups)
    record_by_reference = dict(source_row_by_record_reference or {})
    record_by_reference.update({
        member.stable_record_reference: member.source_row_index
        for group in snapshot.groups for member in group.members
    })
    for item in snapshot.unassigned_records:
        record_by_reference[item.stable_record_reference] = item.source_row_index
    for outcome in (*snapshot.conflicts, *snapshot.deferred_work_units):
        references = getattr(outcome, "involved_record_references", None) or outcome.record_references
        for reference in references:
            if reference not in record_by_reference:
                raise EvaluationDataError("PRODUCT_OUTCOME_SOURCE_ROW_MISSING")

    def outcome(item, kind):
        references = getattr(item, "involved_record_references", None) or item.record_references
        return PredictedOutcome(
            outcome_reference=getattr(item, "conflict_reference", None)
                or item.deferred_reference,
            scan_id=item.scan_id,
            source_row_indices=tuple(sorted(record_by_reference[ref] for ref in references)),
        )

    return GroupQualityEvaluationInput(
        corpus_id=corpus_id,
        corpus_version=corpus_version,
        truth_version=truth_version,
        record_count=snapshot.canonical_record_count,
        seed=seed,
        scan_id=snapshot.scan_id,
        product_result_fingerprint=snapshot.snapshot_fingerprint,
        groups=groups,
        conflicts=tuple(outcome(item, "CONFLICT") for item in snapshot.conflicts),
        deferred=tuple(outcome(item, "DEFERRED") for item in snapshot.deferred_work_units),
        unassigned_source_rows=tuple(sorted(
            item.source_row_index for item in snapshot.unassigned_records
            if item.source_row_index is not None
        )),
        source_fingerprint_before=source_fingerprint_before,
        source_fingerprint_after=source_fingerprint_after,
    )


def validate_truth(truth: GroupQualityTruth) -> None:
    if truth.record_count < 0:
        raise EvaluationDataError("TRUTH_RECORD_COUNT_INVALID")
    if len(truth.scenario_by_source_row) != truth.record_count:
        raise EvaluationDataError("TRUTH_SCENARIO_MEMBERSHIP_INVALID")
    group_ids = [group.truth_group_id for group in truth.groups]
    if len(group_ids) != len(set(group_ids)):
        raise EvaluationDataError("TRUTH_GROUP_ID_DUPLICATE")
    membership = set()
    group_sets = []
    for group in truth.groups:
        members = tuple(group.source_row_indices)
        if len(members) < 2:
            raise EvaluationDataError("TRUTH_GROUP_SINGLETON")
        if len(members) != len(set(members)):
            raise EvaluationDataError("TRUTH_GROUP_MEMBER_DUPLICATE")
        if any(index < 0 or index >= truth.record_count for index in members):
            raise EvaluationDataError("TRUTH_RECORD_REFERENCE_INVALID")
        if membership.intersection(members):
            raise EvaluationDataError("TRUTH_RECORD_MULTI_MEMBERSHIP")
        membership.update(members)
        group_sets.append(set(members))
    for pair in truth.cannot_link_pairs:
        if len(pair) != 2 or pair[0] == pair[1]:
            raise EvaluationDataError("TRUTH_CANNOT_LINK_INVALID")
        if any(index < 0 or index >= truth.record_count for index in pair):
            raise EvaluationDataError("TRUTH_RECORD_REFERENCE_INVALID")
        if any(set(pair) <= group for group in group_sets):
            raise EvaluationDataError("TRUTH_CANNOT_LINK_CONTRADICTS_IDENTITY")
    for bridge in truth.bridge_sets:
        if any(index < 0 or index >= truth.record_count for index in bridge):
            raise EvaluationDataError("TRUTH_RECORD_REFERENCE_INVALID")


def _ratio(numerator: int, denominator: int) -> RatioMetric:
    return RatioMetric(numerator, denominator, None if denominator == 0 else round(numerator / denominator, 12))


def _f1(precision: RatioMetric, recall: RatioMetric) -> float | None:
    if precision.value is None or recall.value is None:
        return None
    total = precision.value + recall.value
    return 0.0 if total == 0 else round(2 * precision.value * recall.value / total, 12)


def _pairs(groups: tuple[set[int], ...]) -> set[tuple[int, int]]:
    return {
        tuple(sorted(pair))
        for group in groups
        for pair in itertools.combinations(sorted(group), 2)
    }


def _size_bucket(size: int) -> str:
    if size == 2:
        return "size 2"
    if size == 3:
        return "size 3"
    if size <= 5:
        return "size 4-5"
    if size <= 10:
        return "size 6-10"
    return "size >10"


def evaluate_group_quality(
    evaluation_input: GroupQualityEvaluationInput,
    truth: GroupQualityTruth,
) -> GroupQualityEvaluationResult:
    validate_truth(truth)
    if truth.truth_version != TRUTH_VERSION_V2:
        raise EvaluationDataError("CORRECTED_TRUTH_V2_REQUIRED")
    if evaluation_input.record_count != truth.record_count:
        raise EvaluationDataError("PRODUCT_TRUTH_RECORD_COUNT_MISMATCH")
    if evaluation_input.corpus_version != truth.corpus_version:
        raise EvaluationDataError("PRODUCT_TRUTH_CORPUS_VERSION_MISMATCH")
    if evaluation_input.truth_version != truth.truth_version:
        raise EvaluationDataError("PRODUCT_TRUTH_VERSION_MISMATCH")
    accepted_items = tuple(
        group for group in evaluation_input.groups if group.status in ACCEPTED_STATUSES
    )
    accepted = tuple(set(group.source_row_indices) for group in accepted_items)
    truth_sets = tuple(set(group.source_row_indices) for group in truth.groups)
    if any(index < 0 or index >= truth.record_count for group in accepted for index in group):
        raise EvaluationDataError("PRODUCT_RECORD_REFERENCE_INVALID")

    exact_predicted = sum(group in truth_sets for group in accepted)
    exact_truth = sum(group in accepted for group in truth_sets)
    precision = _ratio(exact_predicted, len(accepted))
    recall = _ratio(exact_truth, len(truth_sets))

    truth_by_record = {
        member: truth_index
        for truth_index, group in enumerate(truth_sets)
        for member in group
    }
    covered_members = 0
    split_errors = 0
    missed_truth = 0
    for truth_set in truth_sets:
        clean_overlaps = [
            len(truth_set & predicted)
            for predicted in accepted
            if predicted <= truth_set
        ]
        covered_members += max(clean_overlaps, default=0)
        intersecting = [predicted for predicted in accepted if truth_set & predicted]
        split_errors += len(intersecting) > 1
        missed_truth += not any(len(truth_set & predicted) >= 2 for predicted in accepted)
    merge_errors = sum(
        len({truth_by_record[member] for member in predicted if member in truth_by_record}) > 1
        for predicted in accepted
    )
    spurious = sum(
        not any(
            len(predicted & truth_set) >= 2
            and not any(
                member in truth_by_record and truth_by_record[member] != truth_index
                for member in predicted
            )
            and predicted <= truth_set
            for truth_index, truth_set in enumerate(truth_sets)
        )
        for predicted in accepted
    )
    primary = PrimaryGroupMetrics(
        precision,
        recall,
        _f1(precision, recall),
        _ratio(covered_members, sum(len(group) for group in truth_sets)),
        split_errors,
        merge_errors,
        missed_truth,
        spurious,
    )

    predicted_pairs = _pairs(accepted)
    truth_pairs = _pairs(truth_sets)
    pair_precision = _ratio(len(predicted_pairs & truth_pairs), len(predicted_pairs))
    pair_recall = _ratio(len(predicted_pairs & truth_pairs), len(truth_pairs))
    pair_diagnostics = PairDiagnosticMetrics(
        "DIAGNOSTIC ONLY — NOT PRIMARY PRODUCT QUALITY",
        pair_precision,
        pair_recall,
        _f1(pair_precision, pair_recall),
    )

    membership = Counter(member for group in accepted for member in group)
    cannot_links = set(truth.cannot_link_pairs)
    cross_scan = sum(group.scan_id != evaluation_input.scan_id for group in accepted_items)
    cross_scan += sum(item.scan_id != evaluation_input.scan_id for item in (*evaluation_input.conflicts, *evaluation_input.deferred))
    mutation = None
    if evaluation_input.source_fingerprint_before is not None and evaluation_input.source_fingerprint_after is not None:
        mutation = int(evaluation_input.source_fingerprint_before != evaluation_input.source_fingerprint_after)
    safety = EvaluationSafetyMetrics(
        cannot_link_accepted_violations=sum(pair in predicted_pairs for pair in cannot_links),
        duplicate_accepted_membership=sum(count - 1 for count in membership.values() if count > 1),
        singleton_accepted_groups=sum(len(group) < 2 for group in accepted),
        overlapping_accepted_review_membership=sum(count > 1 for count in membership.values()),
        cross_scan_contamination=cross_scan,
        source_record_mutation=mutation,
    )

    conflict_sets = tuple(set(item.source_row_indices) for item in evaluation_input.conflicts)
    deferred_sets = tuple(set(item.source_row_indices) for item in evaluation_input.deferred)
    likely_sets = tuple(set(item.source_row_indices) for item in accepted_items if item.status == LIKELY)
    review_sets = tuple(set(item.source_row_indices) for item in accepted_items if item.status == REVIEW)
    exact_likely = sum(group in likely_sets for group in truth_sets)
    exact_review = sum(group in review_sets for group in truth_sets)
    conflict_only = sum(
        group not in accepted and any(len(group & item) >= 2 for item in conflict_sets)
        for group in truth_sets
    )
    deferred_only = sum(
        group not in accepted
        and not any(len(group & item) >= 2 for item in conflict_sets)
        and any(len(group & item) >= 2 for item in deferred_sets)
        for group in truth_sets
    )
    completely_missed = sum(
        group not in accepted
        and not any(len(group & item) >= 2 for item in (*conflict_sets, *deferred_sets))
        for group in truth_sets
    )
    status = StatusBreakdown(
        exact_likely, exact_review, conflict_only, deferred_only, completely_missed,
        len(likely_sets), len(review_sets), len(conflict_sets), len(deferred_sets),
        len(evaluation_input.unassigned_source_rows),
    )

    size_breakdown = []
    for bucket in SIZE_BUCKETS:
        bucket_groups = [group for group in truth_sets if _size_bucket(len(group)) == bucket]
        recovered = sum(group in accepted for group in bucket_groups)
        bucket_splits = sum(
            sum(bool(group & predicted) for predicted in accepted) > 1
            for group in bucket_groups
        )
        bucket_merge_involvement = sum(
            any(
                bool(group & predicted)
                and len({truth_by_record[member] for member in predicted if member in truth_by_record}) > 1
                for predicted in accepted
            )
            for group in bucket_groups
        )
        size_breakdown.append(GroupSizeBreakdown(
            bucket, len(bucket_groups), recovered,
            None if not bucket_groups else round(recovered / len(bucket_groups), 12),
            bucket_splits, bucket_merge_involvement,
        ))

    scenario_breakdown = []
    labels = tuple(sorted(set(truth.scenario_by_source_row)))
    for label in labels:
        label_records = {
            index for index, value in enumerate(truth.scenario_by_source_row) if value == label
        }
        label_truth = [group for group in truth_sets if group <= label_records]
        exact = sum(group in accepted for group in label_truth)
        conflict_or_deferred = sum(
            group not in accepted
            and any(len(group & item) >= 2 for item in (*conflict_sets, *deferred_sets))
            for group in label_truth
        )
        scenario_breakdown.append(ScenarioBreakdown(
            label, len(label_records), len(label_truth), exact,
            conflict_or_deferred,
            len(label_truth) - exact - conflict_or_deferred,
            sum(set(pair) <= label_records for pair in truth.cannot_link_pairs),
            sum(set(bridge) <= label_records for bridge in truth.bridge_sets),
        ))

    payload = {
        "evaluation_version": EVALUATION_VERSION,
        "corpus_id": evaluation_input.corpus_id,
        "corpus_version": evaluation_input.corpus_version,
        "truth_version": evaluation_input.truth_version,
        "record_count": evaluation_input.record_count,
        "seed": evaluation_input.seed,
        "scan_id": evaluation_input.scan_id,
        "product_result_fingerprint": evaluation_input.product_result_fingerprint,
        "predicted_group_count": len(accepted),
        "truth_group_count": len(truth_sets),
        "primary_metrics": primary,
        "pair_diagnostics": pair_diagnostics,
        "safety_metrics": safety,
        "status_breakdown": status,
        "group_size_breakdown": tuple(size_breakdown),
        "scenario_breakdown": tuple(scenario_breakdown),
    }
    return GroupQualityEvaluationResult(
        **payload,
        evaluation_fingerprint=stable_fingerprint(payload),
    )
