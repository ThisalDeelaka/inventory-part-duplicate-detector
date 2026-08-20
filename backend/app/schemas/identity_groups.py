"""Typed, business-safe contracts for immutable G2 snapshot reads."""

from datetime import datetime
from enum import Enum

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.identity_group_reviews import GroupReviewStateResponse


class AcceptedIdentityGroupStatus(str, Enum):
    LIKELY_DUPLICATE_GROUP = "LIKELY_DUPLICATE_GROUP"
    POSSIBLE_DUPLICATE_GROUP_REVIEW = "POSSIBLE_DUPLICATE_GROUP_REVIEW"


class IdentityDiagnosticStatus(str, Enum):
    CONFLICTING_FAMILY = "CONFLICTING_FAMILY"
    DEFERRED_OVERSIZED_FAMILY = "DEFERRED_OVERSIZED_FAMILY"
    DEFERRED_AMBIGUOUS_RECORD_FAMILY = "DEFERRED_AMBIGUOUS_RECORD_FAMILY"


class ProjectionRunResponse(BaseModel):
    projection_run_id: int
    scan_id: int
    algorithm_version: str
    edge_classifier_version: str
    deterministic_engine_version: str
    evidence_fingerprint: str
    max_group_validation_members: int
    status: str
    created_at: datetime
    records_seen: int
    seed_edges: int
    provisional_components: int
    accepted_groups: int
    likely_groups: int
    review_groups: int
    conflicting_families: int
    oversized_families: int
    ambiguous_families: int
    internal_pairs_total: int
    internal_pairs_reused: int
    internal_pairs_rescored: int
    cannot_links_found: int
    max_component_size: int
    max_accepted_group_size: int


class IdentityGroupUomSummaryResponse(BaseModel):
    distinct_uoms: list[str]
    same_uom_pair_count: int
    convertible_uom_pair_count: int
    different_basis_pair_count: int
    missing_or_wildcard_pair_count: int
    malformed_or_unknown_pair_count: int
    possible_mapping_error_count: int


class IdentityGroupListItem(BaseModel):
    group_snapshot_id: int
    hypothesis_key: str
    group_status: AcceptedIdentityGroupStatus
    group_size: int
    supporting_edge_count: int
    review_edge_count: int
    non_groupable_internal_count: int
    internal_pair_count: int
    internal_pairs_reused: int
    internal_pairs_rescored: int
    evidence_completeness: float
    reason_codes: list[str]
    uom_summary: IdentityGroupUomSummaryResponse
    projection_algorithm_version: str
    created_at: datetime
    review_state: GroupReviewStateResponse = Field(default_factory=GroupReviewStateResponse)


class IdentityGroupMemberResponse(BaseModel):
    member_index: int
    record_ref_key: str
    contract: str | None
    part_no: str
    description: str
    normalized_part_no: str
    normalized_description: str
    uom: str | None
    product_category_id: str | None
    hsn_sac_code: str | None


class IdentityGroupEdgeResponse(BaseModel):
    left_record_ref_key: str
    right_record_ref_key: str
    edge_class: str
    reason_codes: list[str]
    evidence_source: str
    candidate_id: int | None
    exclusion_id: int | None
    deterministic_score: float | None
    deterministic_status: str | None
    critical_mismatches: list[dict]


class IdentityGroupDetail(IdentityGroupListItem):
    projection: ProjectionRunResponse
    members: list[IdentityGroupMemberResponse]
    internal_edges: list[IdentityGroupEdgeResponse]


class PaginatedIdentityGroupsResponse(BaseModel):
    selected_projection: ProjectionRunResponse | None
    limit: int
    offset: int
    total: int
    items: list[IdentityGroupListItem]


class IdentityGroupSummaryResponse(BaseModel):
    snapshot_available: bool
    selected_projection: ProjectionRunResponse | None
    accepted_groups: int = 0
    likely_groups: int = 0
    review_groups: int = 0
    diagnostic_families: int = 0
    conflicting_families: int = 0
    oversized_families: int = 0
    ambiguous_families: int = 0
    group_size_distribution: dict[int, int] = Field(default_factory=dict)
    largest_accepted_group: int = 0
    largest_diagnostic_family: int = 0
    uom_summary: IdentityGroupUomSummaryResponse


class IdentityDiagnosticListItem(BaseModel):
    diagnostic_snapshot_id: int
    diagnostic_key: str
    diagnostic_status: IdentityDiagnosticStatus
    member_count: int
    seed_edge_count: int
    internal_pair_count: int
    internal_pairs_reused: int
    internal_pairs_rescored: int
    cannot_link_count: int
    reason_codes: list[str]
    projection_algorithm_version: str
    created_at: datetime


class IdentityDiagnosticDetail(IdentityDiagnosticListItem):
    projection: ProjectionRunResponse
    members: list[IdentityGroupMemberResponse]
    conflict_edges: list[IdentityGroupEdgeResponse]


class PaginatedIdentityDiagnosticsResponse(BaseModel):
    selected_projection: ProjectionRunResponse | None
    limit: int
    offset: int
    total: int
    items: list[IdentityDiagnosticListItem]


class IdentityReadProjectionMetadataResponse(BaseModel):
    projection_contract: str
    source_projection_run_id: int
    source_orchestration_run_id: int | None
    source_resolution_run_id: int | None


class IdentityReadValidationCoverageResponse(BaseModel):
    validation_mode: str
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


class IdentityReadGroupResponse(BaseModel):
    versioned_group_key: str
    group_reference: str
    projection_contract: str
    group_status: AcceptedIdentityGroupStatus
    group_size: int
    validation_mode: str
    validation_coverage: IdentityReadValidationCoverageResponse
    source_group_fingerprint: str
    read_group_fingerprint: str
    group_evidence_summary: dict[str, Any] | None = None
    bridge_risk_summary: dict[str, Any] | None = None
    genericity_risk_summary: dict[str, Any] | None = None
    missing_evidence_summary: dict[str, Any] | None = None
    member_preview: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    review_state: GroupReviewStateResponse = Field(default_factory=GroupReviewStateResponse)


class IdentityReadGroupDetailResponse(IdentityReadGroupResponse):
    members: list[dict[str, Any]]
    internal_evidence: list[dict[str, Any]]


class PaginatedIdentityReadGroupsResponse(BaseModel):
    projection: IdentityReadProjectionMetadataResponse
    limit: int
    offset: int
    total: int
    items: list[IdentityReadGroupResponse]


class IdentityReadSummaryApiResponse(BaseModel):
    snapshot_available: bool
    read_ready: bool
    projection: IdentityReadProjectionMetadataResponse
    canonical_record_count: int
    group_count: int
    likely_group_count: int
    review_group_count: int
    conflict_count: int
    deferred_count: int
    unassigned_count: int
    snapshot_fingerprint: str


class IdentityReadOutcomesResponse(BaseModel):
    projection: IdentityReadProjectionMetadataResponse
    conflicts: list[dict[str, Any]]
    deferred_work_units: list[dict[str, Any]]
    unassigned_records: list[dict[str, Any]]


class VersionedGroupAdvisoryEligibilityResponse(BaseModel):
    versioned_group_key: str
    projection_contract: str
    source_projection_run_id: int
    source_group_fingerprint: str
    eligible: bool
    reason_code: str
    details: list[str]
    request_fingerprint: str | None = None
