"""Immutable, persistence-neutral GF-9A identity-read contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


IDENTITY_READ_CONTRACT_VERSION = "identity-read-contract-v1"


class IdentityReadProjectionContract(str, Enum):
    G2_V1 = "G2_V1"
    G2_V2 = "G2_V2"


class IdentityReadGroupStatus(str, Enum):
    LIKELY_DUPLICATE_GROUP = "LIKELY_DUPLICATE_GROUP"
    POSSIBLE_DUPLICATE_GROUP_REVIEW = "POSSIBLE_DUPLICATE_GROUP_REVIEW"


class IdentityReadValidationMode(str, Enum):
    LEGACY_COMPLETE_PAIRWISE = "LEGACY_COMPLETE_PAIRWISE"
    COMPLETE_PAIRWISE = "COMPLETE_PAIRWISE"
    PROGRESSIVE_TARGETED = "PROGRESSIVE_TARGETED"


class IdentityReadAuthorityStatus(str, Enum):
    READY = "READY"
    READ_NOT_READY = "READ_NOT_READY"
    READ_AUTHORITY_INCONSISTENT = "READ_AUTHORITY_INCONSISTENT"


@dataclass(frozen=True)
class VersionedIdentityGroupKey:
    scan_id: int
    projection_contract: IdentityReadProjectionContract
    group_reference: str


@dataclass(frozen=True)
class IdentityReadSourceRecord:
    record_id: int
    scan_id: int
    stable_record_reference: str
    source_row_index: int | None
    part_no: str
    description: str
    normalized_part_no: str = ""
    normalized_description: str = ""
    contract: str | None = None
    uom: str | None = None
    type_code: str | None = None
    prime_commodity: str | None = None
    second_commodity: str | None = None
    accounting_group: str | None = None
    part_product_code: str | None = None
    part_product_family: str | None = None
    product_category_id: str | None = None
    hsn_sac_code: str | None = None
    hazard_code: str | None = None


@dataclass(frozen=True)
class G2V1ReadSourceMember:
    record_id: int
    stable_record_reference: str
    member_order: int


@dataclass(frozen=True)
class G2V1ReadSourceGroup:
    group_reference: str
    scan_id: int
    status: str
    members: tuple[G2V1ReadSourceMember, ...]
    source_group_fingerprint: str


@dataclass(frozen=True)
class G2V1ReadSourceSnapshot:
    scan_id: int
    source_projection_run_id: int
    status: str
    canonical_record_count: int
    groups: tuple[G2V1ReadSourceGroup, ...]
    source_snapshot_fingerprint: str


@dataclass(frozen=True)
class IdentityReadProjectionAvailability:
    projection_contract: IdentityReadProjectionContract
    scan_id: int
    source_projection_run_id: int | None
    status: str | None
    snapshot_valid: bool
    provenance_compatible: bool = True


@dataclass(frozen=True)
class IdentityReadAuthorityContext:
    scan_id: int
    orchestration_run_id: int | None
    persisted_orchestration_mode: str | None
    orchestration_status: str | None
    v1_projection: IdentityReadProjectionAvailability | None
    v2_projection: IdentityReadProjectionAvailability | None


@dataclass(frozen=True)
class IdentityReadAuthorityDecision:
    scan_id: int
    authority_status: IdentityReadAuthorityStatus
    projection_contract: IdentityReadProjectionContract | None
    source_projection_run_id: int | None
    source_orchestration_run_id: int | None
    reason_code: str


@dataclass(frozen=True)
class IdentityReadValidationCoverage:
    validation_mode: IdentityReadValidationMode
    member_count: int
    possible_internal_pair_count: int
    evaluated_internal_pair_count: int
    required_validation_evidence_count: int
    strong_support_count: int
    review_support_count: int
    non_groupable_count: int
    cannot_link_count: int
    missing_nonrequired_pair_count: int
    targeted_evidence_count: int
    proposal_evidence_count: int


@dataclass(frozen=True)
class IdentityReadGroupMember:
    record_id: int
    stable_record_reference: str
    source_row_index: int | None
    member_order: int
    part_no: str
    description: str
    normalized_part_no: str
    normalized_description: str
    contract: str | None
    uom: str | None
    type_code: str | None
    prime_commodity: str | None
    second_commodity: str | None
    accounting_group: str | None
    part_product_code: str | None
    part_product_family: str | None
    product_category_id: str | None
    hsn_sac_code: str | None
    hazard_code: str | None


@dataclass(frozen=True)
class IdentityReadGroup:
    versioned_group_key: VersionedIdentityGroupKey
    status: IdentityReadGroupStatus
    member_count: int
    members: tuple[IdentityReadGroupMember, ...]
    validation_mode: IdentityReadValidationMode
    validation_coverage: IdentityReadValidationCoverage | None
    group_evidence_summary: Any | None
    bridge_risk_summary: Any | None
    genericity_risk_summary: Any | None
    missing_evidence_summary: Any | None
    internal_evidence: tuple[Any, ...]
    source_group_fingerprint: str
    read_group_fingerprint: str


@dataclass(frozen=True)
class IdentityReadConflict:
    scan_id: int
    conflict_reference: str
    conflict_type: str
    involved_record_ids: tuple[int, ...]
    involved_record_references: tuple[str, ...]
    protected_evidence_references: tuple[str, ...]
    source_neighborhood_references: tuple[str, ...]
    summary: str
    source_conflict_fingerprint: str
    read_conflict_fingerprint: str


@dataclass(frozen=True)
class IdentityReadDeferredWork:
    scan_id: int
    deferred_reference: str
    reason: str
    record_ids: tuple[int, ...]
    record_references: tuple[str, ...]
    unfinished_evidence_summary: str
    source_neighborhood_references: tuple[str, ...]
    source_deferred_fingerprint: str
    read_deferred_fingerprint: str


@dataclass(frozen=True)
class IdentityReadUnassignedRecord:
    record_id: int
    stable_record_reference: str
    source_row_index: int | None


@dataclass(frozen=True)
class IdentityReadSummary:
    canonical_record_count: int
    group_count: int
    likely_group_count: int
    review_group_count: int
    conflict_count: int
    deferred_count: int
    unassigned_count: int


@dataclass(frozen=True)
class IdentityReadSnapshot:
    scan_id: int
    projection_contract: IdentityReadProjectionContract
    source_projection_run_id: int
    source_orchestration_run_id: int | None
    source_resolution_run_id: int | None
    groups: tuple[IdentityReadGroup, ...]
    conflicts: tuple[IdentityReadConflict, ...]
    deferred_work_units: tuple[IdentityReadDeferredWork, ...]
    unassigned_records: tuple[IdentityReadUnassignedRecord, ...]
    canonical_record_count: int
    group_count: int
    likely_group_count: int
    review_group_count: int
    conflict_count: int
    deferred_count: int
    unassigned_count: int
    summary: IdentityReadSummary
    source_snapshot_fingerprint: str
    snapshot_fingerprint: str
