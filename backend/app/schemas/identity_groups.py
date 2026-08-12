"""Typed, business-safe contracts for immutable G2 snapshot reads."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


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
