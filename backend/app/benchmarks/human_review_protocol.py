"""Typed, offline-only contracts for blinded GF-12 human group review.

Production services must never import this module. Human labels are downstream
validation evidence and cannot alter discovery, evidence, resolution, or G2.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.benchmarks.contracts import canonical_json


HUMAN_REVIEW_PROTOCOL_VERSION = "gf12-human-group-review-v1"
REVIEW_PACK_VERSION = "gf12-blinded-review-pack-v1"
REVIEW_LABEL_SCHEMA_VERSION = "gf12-human-group-label-v1"

_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class HumanReviewValidationError(ValueError):
    """Fail-closed validation error with a stable safe code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class DatasetClassification(str, Enum):
    AUTHORIZED_HUMAN_VALIDATION_DATASET = "AUTHORIZED_HUMAN_VALIDATION_DATASET"
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    UNSPECIFIED_NOT_AUTHORIZED = "UNSPECIFIED/NOT_AUTHORIZED"


class ReviewStratum(str, Enum):
    LIKELY_DUPLICATE_GROUP = "LIKELY_DUPLICATE_GROUP"
    POSSIBLE_DUPLICATE_GROUP_REVIEW = "POSSIBLE_DUPLICATE_GROUP_REVIEW"
    CONFLICT = "CONFLICT"
    DEFERRED = "DEFERRED"
    UNASSIGNED_CANDIDATE_NEIGHBORHOOD = "UNASSIGNED/CANDIDATE-NEIGHBORHOOD"


class ReviewerConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNSPECIFIED = "UNSPECIFIED"


class ReviewCompletionState(str, Enum):
    DRAFT = "DRAFT"
    COMPLETE = "COMPLETE"


class ReviewerRole(str, Enum):
    REVIEWER = "REVIEWER"
    ADJUDICATOR = "ADJUDICATOR"


class HumanReviewReasonCode(str, Enum):
    SAME_PART_NUMBER = "SAME_PART_NUMBER"
    EQUIVALENT_DESCRIPTION = "EQUIVALENT_DESCRIPTION"
    COMPATIBLE_TECHNICAL_IDENTITY = "COMPATIBLE_TECHNICAL_IDENTITY"
    TECHNICAL_IDENTITY_CONFLICT = "TECHNICAL_IDENTITY_CONFLICT"
    GENERIC_DESCRIPTION = "GENERIC_DESCRIPTION"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    SITE_CONTEXT_ONLY = "SITE_CONTEXT_ONLY"
    UOM_CONTEXT_ONLY = "UOM_CONTEXT_ONLY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class ValidationDatasetDescriptor:
    dataset_id: str
    dataset_version: str
    dataset_fingerprint: str
    classification: DatasetClassification


@dataclass(frozen=True)
class BlindedReviewRecord:
    """Minimum allowlisted record view presented to a reviewer."""

    stable_record_reference: str
    source_row_reference: str | int
    part_no: str | None
    description: str | None
    product_category: str | None = None
    hsn_sac: str | None = None
    site_or_contract: str | None = None
    uom: str | None = None


BLINDED_FIELD_CLASSIFICATION = (
    ("stable_record_reference", "REQUIRED_FOR_IDENTITY_REVIEW"),
    ("source_row_reference", "REQUIRED_FOR_IDENTITY_REVIEW"),
    ("part_no", "REQUIRED_FOR_IDENTITY_REVIEW"),
    ("description", "REQUIRED_FOR_IDENTITY_REVIEW"),
    ("product_category", "REQUIRED_FOR_IDENTITY_REVIEW"),
    ("hsn_sac", "REQUIRED_FOR_IDENTITY_REVIEW"),
    ("site_or_contract", "OPTIONAL_CONTEXT"),
    ("uom", "OPTIONAL_CONTEXT"),
    ("system_status", "NOT_REQUIRED"),
    ("system_score", "NOT_REQUIRED"),
    ("retrieval_channel", "NOT_REQUIRED"),
    ("fusion_score", "NOT_REQUIRED"),
    ("system_decision", "NOT_REQUIRED"),
    ("benchmark_truth", "NOT_REQUIRED"),
    ("sampling_stratum", "NOT_REQUIRED"),
)


@dataclass(frozen=True)
class HumanReviewLabel:
    label_schema_version: str
    review_protocol_version: str
    review_pack_version: str
    review_unit_id: str
    dataset_id: str
    dataset_version: str
    reviewer_code: str
    reviewer_role: ReviewerRole
    record_refs_presented: tuple[str, ...]
    same_item_groups: tuple[tuple[str, ...], ...]
    unmatched_record_refs: tuple[str, ...]
    insufficient_evidence_refs: tuple[str, ...]
    insufficient_evidence_groups: tuple[tuple[str, ...], ...]
    confidence: ReviewerConfidence = ReviewerConfidence.UNSPECIFIED
    reason_codes: tuple[HumanReviewReasonCode, ...] = ()
    completion_state: ReviewCompletionState = ReviewCompletionState.COMPLETE

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


def validate_dataset_descriptor(descriptor: ValidationDatasetDescriptor) -> None:
    if not _CODE_PATTERN.fullmatch(descriptor.dataset_id):
        raise HumanReviewValidationError("DATASET_ID_INVALID")
    if not _CODE_PATTERN.fullmatch(descriptor.dataset_version):
        raise HumanReviewValidationError("DATASET_VERSION_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", descriptor.dataset_fingerprint):
        raise HumanReviewValidationError("DATASET_FINGERPRINT_INVALID")


def validate_blinded_record(record: BlindedReviewRecord) -> None:
    if not record.stable_record_reference or len(record.stable_record_reference) > 256:
        raise HumanReviewValidationError("RECORD_REFERENCE_INVALID")
    if record.source_row_reference is None or str(record.source_row_reference) == "":
        raise HumanReviewValidationError("SOURCE_ROW_REFERENCE_INVALID")
    for value in (
        record.part_no,
        record.description,
        record.product_category,
        record.hsn_sac,
        record.site_or_contract,
        record.uom,
    ):
        if value is not None and len(value) > 1000:
            raise HumanReviewValidationError("BLINDED_RECORD_FIELD_TOO_LONG")


def _validate_canonical_group(group: tuple[str, ...], *, minimum: int) -> None:
    if len(group) < minimum:
        raise HumanReviewValidationError("HUMAN_DUPLICATE_GROUP_TOO_SMALL")
    if len(group) != len(set(group)):
        raise HumanReviewValidationError("HUMAN_GROUP_RECORD_DUPLICATE")
    if group != tuple(sorted(group)):
        raise HumanReviewValidationError("HUMAN_GROUP_NOT_CANONICAL")


def validate_human_review_label(label: HumanReviewLabel) -> None:
    """Validate structure without repairing, sorting, or filling omissions."""

    if label.label_schema_version != REVIEW_LABEL_SCHEMA_VERSION:
        raise HumanReviewValidationError("LABEL_SCHEMA_VERSION_INVALID")
    if label.review_protocol_version != HUMAN_REVIEW_PROTOCOL_VERSION:
        raise HumanReviewValidationError("REVIEW_PROTOCOL_VERSION_INVALID")
    if label.review_pack_version != REVIEW_PACK_VERSION:
        raise HumanReviewValidationError("REVIEW_PACK_VERSION_INVALID")
    if not label.review_unit_id or len(label.review_unit_id) > 128:
        raise HumanReviewValidationError("REVIEW_UNIT_ID_INVALID")
    if not _CODE_PATTERN.fullmatch(label.dataset_id):
        raise HumanReviewValidationError("DATASET_ID_INVALID")
    if not _CODE_PATTERN.fullmatch(label.dataset_version):
        raise HumanReviewValidationError("DATASET_VERSION_INVALID")
    if not _CODE_PATTERN.fullmatch(label.reviewer_code):
        raise HumanReviewValidationError("REVIEWER_CODE_INVALID")

    presented = label.record_refs_presented
    if len(presented) < 2 or len(presented) != len(set(presented)):
        raise HumanReviewValidationError("PRESENTED_RECORD_SET_INVALID")
    if presented != tuple(sorted(presented)):
        raise HumanReviewValidationError("PRESENTED_RECORD_SET_NOT_CANONICAL")

    for group in label.same_item_groups:
        _validate_canonical_group(group, minimum=2)
    for group in label.insufficient_evidence_groups:
        _validate_canonical_group(group, minimum=2)
    if label.same_item_groups != tuple(sorted(label.same_item_groups)):
        raise HumanReviewValidationError("HUMAN_PARTITION_NOT_CANONICAL")
    if label.insufficient_evidence_groups != tuple(
        sorted(label.insufficient_evidence_groups)
    ):
        raise HumanReviewValidationError("INSUFFICIENT_GROUPS_NOT_CANONICAL")

    if label.unmatched_record_refs != tuple(sorted(label.unmatched_record_refs)):
        raise HumanReviewValidationError("UNMATCHED_RECORDS_NOT_CANONICAL")
    if label.insufficient_evidence_refs != tuple(
        sorted(label.insufficient_evidence_refs)
    ):
        raise HumanReviewValidationError("INSUFFICIENT_RECORDS_NOT_CANONICAL")
    if label.reason_codes != tuple(sorted(set(label.reason_codes), key=lambda item: item.value)):
        raise HumanReviewValidationError("REASON_CODES_NOT_CANONICAL")

    assigned = [
        reference
        for group in (*label.same_item_groups, *label.insufficient_evidence_groups)
        for reference in group
    ]
    assigned.extend(label.unmatched_record_refs)
    assigned.extend(label.insufficient_evidence_refs)
    if any(reference not in set(presented) for reference in assigned):
        raise HumanReviewValidationError("UNKNOWN_PRESENTED_RECORD")
    if len(assigned) != len(set(assigned)):
        raise HumanReviewValidationError("RECORD_REPEATED_ACROSS_HUMAN_PARTITION")
    if label.completion_state == ReviewCompletionState.COMPLETE and set(assigned) != set(presented):
        raise HumanReviewValidationError("HUMAN_PARTITION_RECORD_OMITTED")
    if label.completion_state == ReviewCompletionState.DRAFT and not set(assigned) <= set(presented):
        raise HumanReviewValidationError("DRAFT_PARTITION_INVALID")


def decidable_partition(label: HumanReviewLabel) -> tuple[tuple[str, ...], ...]:
    """Return duplicate blocks plus explicit unmatched singleton blocks."""

    validate_human_review_label(label)
    if label.completion_state != ReviewCompletionState.COMPLETE:
        raise HumanReviewValidationError("COMPLETE_REVIEW_REQUIRED")
    return tuple(sorted(
        (*label.same_item_groups, *((reference,) for reference in label.unmatched_record_refs))
    ))
