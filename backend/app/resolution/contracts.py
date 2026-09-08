"""Immutable GF-5A contracts for future constrained identity resolution.

These types define a provider-free boundary.  They do not resolve a work unit,
persist a result, or publish a G2 snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.engine.identity_edge import IdentityEdgeClass
from app.services.canonical_record_service import CanonicalScanRecord


RESOLVER_CONTRACT_VERSION = "identity-resolution-contract-v1"
DEFAULT_RESOLVER_ALGORITHM_VERSION = "constrained-identity-resolver-v1"


class IdentityResolutionConstraintType(str, Enum):
    MUST_LINK = "MUST_LINK"
    CANNOT_LINK = "CANNOT_LINK"


class TargetedEvidenceReason(str, Enum):
    BRIDGE_CROSS_CHECK = "BRIDGE_CROSS_CHECK"
    PARTITION_CROSS_CHECK = "PARTITION_CROSS_CHECK"
    LIKELY_GROUP_COMPLETENESS_CHECK = "LIKELY_GROUP_COMPLETENESS_CHECK"
    OWNERSHIP_AMBIGUITY_CHECK = "OWNERSHIP_AMBIGUITY_CHECK"


class IdentityGroupHypothesisStatus(str, Enum):
    LIKELY_DUPLICATE_GROUP = "LIKELY_DUPLICATE_GROUP"
    POSSIBLE_DUPLICATE_GROUP_REVIEW = "POSSIBLE_DUPLICATE_GROUP_REVIEW"


class IdentityValidationMode(str, Enum):
    COMPLETE_PAIRWISE = "COMPLETE_PAIRWISE"
    PROGRESSIVE_TARGETED = "PROGRESSIVE_TARGETED"


class IdentityConflictType(str, Enum):
    PROTECTED_CANNOT_LINK = "PROTECTED_CANNOT_LINK"
    HUMAN_MACHINE_AUTHORITY_CONFLICT = "HUMAN_MACHINE_AUTHORITY_CONFLICT"
    INCOMPATIBLE_MUST_LINK_CONSTRAINTS = "INCOMPATIBLE_MUST_LINK_CONSTRAINTS"
    OVERLAPPING_ACCEPTED_MEMBERSHIP_CONFLICT = (
        "OVERLAPPING_ACCEPTED_MEMBERSHIP_CONFLICT"
    )


class DeferredIdentityReason(str, Enum):
    RESOLUTION_MEMBER_CAP_REACHED = "RESOLUTION_MEMBER_CAP_REACHED"
    TARGETED_EVIDENCE_BUDGET_EXHAUSTED = "TARGETED_EVIDENCE_BUDGET_EXHAUSTED"
    UNRESOLVED_BRIDGE_AMBIGUITY = "UNRESOLVED_BRIDGE_AMBIGUITY"
    UNRESOLVED_OWNERSHIP_AMBIGUITY = "UNRESOLVED_OWNERSHIP_AMBIGUITY"
    INSUFFICIENT_PARTITION_STABILITY = "INSUFFICIENT_PARTITION_STABILITY"
    DISCOVERY_TRUNCATION_REQUIRES_LATER_ANALYSIS = (
        "DISCOVERY_TRUNCATION_REQUIRES_LATER_ANALYSIS"
    )


@dataclass(frozen=True)
class ResolverConfiguration:
    max_resolution_members: int
    max_targeted_checks_per_work_unit: int
    complete_pairwise_member_limit: int
    configuration_version: str


@dataclass(frozen=True)
class IdentityResolutionNeighborhood:
    neighborhood_reference: str
    scan_id: int
    discovery_run_id: int
    member_record_ids: tuple[int, ...]
    truncated: bool
    degraded: bool


@dataclass(frozen=True)
class IdentityResolutionEvidenceEdge:
    scan_id: int
    evidence_run_id: int
    record_id_1: int
    record_id_2: int
    edge_class: IdentityEdgeClass
    reason_codes: tuple[str, ...]
    evidence_fingerprint: str
    generic_only: bool = False


@dataclass(frozen=True)
class IdentityResolutionConstraint:
    scan_id: int
    record_id_1: int
    record_id_2: int
    constraint_type: IdentityResolutionConstraintType
    source_authority: str
    source_reference: str


@dataclass(frozen=True)
class TargetedEvidenceRequest:
    scan_id: int
    record_id_1: int
    record_id_2: int
    reason: TargetedEvidenceReason
    requesting_work_unit_reference: str
    request_fingerprint: str
    record_reference_1: str
    record_reference_2: str


@dataclass(frozen=True)
class TargetedEvidenceResult:
    request: TargetedEvidenceRequest
    edge_class: IdentityEdgeClass
    reason_codes: tuple[str, ...]
    evidence_summary: str
    evaluator_version: str
    evidence_fingerprint: str
    generic_only: bool = False


@dataclass(frozen=True)
class BridgeRiskSummary:
    articulation_record_ids: tuple[int, ...] = ()
    single_edge_branch_record_ids: tuple[int, ...] = ()
    neutral_cross_branch_pairs: tuple[tuple[int, int], ...] = ()
    missing_cross_branch_pairs: tuple[tuple[int, int], ...] = ()
    generic_hub_record_ids: tuple[int, ...] = ()
    competing_partition_evidence: tuple[str, ...] = ()
    unresolved: bool = False


@dataclass(frozen=True)
class GenericityRiskSummary:
    generic_description_burden: bool = False
    review_only_support: bool = False
    hub_dependency_record_ids: tuple[int, ...] = ()
    insufficient_independent_identity_evidence: bool = False


@dataclass(frozen=True)
class MissingEvidenceSummary:
    missing_pairs: tuple[tuple[int, int], ...] = ()
    incomplete_reason_codes: tuple[str, ...] = ()
    discovery_truncation_affects_membership: bool = False
    unresolved_ownership_ambiguity: bool = False


@dataclass(frozen=True)
class GroupEvidenceSummary:
    member_count: int
    validation_mode: IdentityValidationMode
    evaluated_pair_count: int
    possible_pair_count: int
    strong_support_count: int
    review_support_count: int
    non_groupable_count: int
    cannot_link_count: int
    support_density: float | None
    strong_support_density: float | None
    generic_evidence_edge_count: int
    generic_member_count: int | None
    protected_conflict_count: int
    technical_consensus_summary: str | None
    missing_evidence_count: int
    bridge_risk_flag_count: int
    required_conflict_checks_total: int
    required_conflict_checks_completed: int
    discovery_truncated: bool
    discovery_degraded: bool
    source_neighborhood_count: int


@dataclass(frozen=True)
class IdentityGroupHypothesis:
    hypothesis_id: str
    scan_id: int
    member_record_ids: tuple[int, ...]
    member_record_references: tuple[str, ...]
    status: IdentityGroupHypothesisStatus
    validation_mode: IdentityValidationMode
    evidence_summary: GroupEvidenceSummary
    bridge_risk_summary: BridgeRiskSummary
    genericity_risk_summary: GenericityRiskSummary
    missing_evidence_summary: MissingEvidenceSummary
    source_neighborhood_references: tuple[str, ...]
    hypothesis_fingerprint: str


@dataclass(frozen=True)
class IdentityConflict:
    conflict_id: str
    scan_id: int
    involved_record_ids: tuple[int, ...]
    involved_record_references: tuple[str, ...]
    conflict_type: IdentityConflictType
    protected_evidence_references: tuple[str, ...]
    source_neighborhood_references: tuple[str, ...]
    summary: str
    fingerprint: str


@dataclass(frozen=True)
class DeferredIdentityWorkUnit:
    deferred_id: str
    scan_id: int
    record_ids: tuple[int, ...]
    record_references: tuple[str, ...]
    reason: DeferredIdentityReason
    unfinished_evidence_summary: str
    source_neighborhood_references: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class IdentityResolutionMetrics:
    source_record_count: int
    accepted_group_count: int
    likely_group_count: int
    review_group_count: int
    conflict_count: int
    deferred_work_unit_count: int
    unassigned_record_count: int
    targeted_evidence_request_count: int
    targeted_evidence_result_count: int
    work_unit_count: int = 0
    candidate_partitions_explored: int = 0
    targeted_evidence_cache_hit_count: int = 0


@dataclass(frozen=True)
class IdentityResolutionInput:
    scan_id: int
    discovery_run_id: int
    evidence_run_id: int
    canonical_records: tuple[CanonicalScanRecord, ...]
    identity_neighborhoods: tuple[IdentityResolutionNeighborhood, ...]
    machine_evidence_edges: tuple[IdentityResolutionEvidenceEdge, ...]
    human_constraints: tuple[IdentityResolutionConstraint, ...]
    resolver_algorithm_version: str
    resolver_configuration: ResolverConfiguration


@dataclass(frozen=True)
class IdentityResolutionResult:
    scan_id: int
    accepted_groups: tuple[IdentityGroupHypothesis, ...]
    conflicts: tuple[IdentityConflict, ...]
    deferred_work_units: tuple[DeferredIdentityWorkUnit, ...]
    unassigned_record_ids: tuple[int, ...]
    unassigned_record_references: tuple[str, ...]
    targeted_evidence_requests: tuple[TargetedEvidenceRequest, ...]
    targeted_evidence_results: tuple[TargetedEvidenceResult, ...]
    metrics: IdentityResolutionMetrics
    resolver_algorithm_version: str
    resolution_fingerprint: str
