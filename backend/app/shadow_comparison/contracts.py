"""Immutable, database-independent GF-7A shadow-comparison contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.g2_v2.contracts import G2V2SnapshotManifest
from app.resolution.contracts import IdentityGroupHypothesisStatus


SHADOW_COMPARISON_ALGORITHM_VERSION = "g2-shadow-comparison-v1"


class ComparisonSourceVersion(str, Enum):
    V1 = "V1"
    V2 = "V2"


class ShadowComparisonCaseType(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    STATUS_CHANGE = "STATUS_CHANGE"
    V1_GROUP_SPLIT_IN_V2 = "V1_GROUP_SPLIT_IN_V2"
    V2_GROUP_MERGE_OF_V1 = "V2_GROUP_MERGE_OF_V1"
    PARTIAL_REASSIGNMENT = "PARTIAL_REASSIGNMENT"
    V1_ONLY_GROUP = "V1_ONLY_GROUP"
    V2_ONLY_GROUP = "V2_ONLY_GROUP"
    COMPLEX_OVERLAP = "COMPLEX_OVERLAP"


class ShadowSafetyDeltaType(str, Enum):
    V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT = "V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT"
    V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK = "V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK"
    V2_ACCEPTED_PAIR_ABSENT_FROM_V1 = "V2_ACCEPTED_PAIR_ABSENT_FROM_V1"
    V2_GROUP_USES_TARGETED_EVIDENCE_NOT_AVAILABLE_TO_V1 = "V2_GROUP_USES_TARGETED_EVIDENCE_NOT_AVAILABLE_TO_V1"
    V2_DEFERRED_WHERE_V1_ACCEPTED = "V2_DEFERRED_WHERE_V1_ACCEPTED"
    V2_CONFLICT_WHERE_V1_ACCEPTED = "V2_CONFLICT_WHERE_V1_ACCEPTED"
    V1_ACCEPTED_WHERE_V2_UNASSIGNED = "V1_ACCEPTED_WHERE_V2_UNASSIGNED"


class AdjudicationPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NONE = "NONE"


@dataclass(frozen=True)
class ShadowComparisonConfiguration:
    configuration_version: str = "g2-shadow-comparison-config-v1"
    empty_positive_pair_jaccard: float = 1.0


@dataclass(frozen=True)
class ComparisonIdentitySet:
    source_version: ComparisonSourceVersion
    group_reference: str
    status: IdentityGroupHypothesisStatus
    member_record_ids: tuple[int, ...]
    stable_member_references: tuple[str, ...]
    member_count: int
    source_fingerprint: str


@dataclass(frozen=True)
class V1ComparisonSnapshot:
    scan_id: int
    status: str
    snapshot_contract_version: int
    canonical_record_count: int
    groups: tuple[ComparisonIdentitySet, ...]
    source_fingerprint: str
    unassigned_record_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShadowComparisonInput:
    scan_id: int
    canonical_records: tuple[object, ...]
    v1_snapshot: V1ComparisonSnapshot
    v2_snapshot: G2V2SnapshotManifest
    v1_projection_run_id: int
    v2_projection_run_id: int
    v2_source_resolution_run_id: int
    v2_projection_status: str
    comparison_algorithm_version: str = SHADOW_COMPARISON_ALGORITHM_VERSION
    comparison_configuration: ShadowComparisonConfiguration = ShadowComparisonConfiguration()


@dataclass(frozen=True)
class GroupOverlapMetrics:
    v1_group_reference: str
    v2_group_reference: str
    intersection_count: int
    union_count: int
    member_jaccard: float
    v1_containment_ratio: float
    v2_containment_ratio: float


@dataclass(frozen=True)
class StatusTransition:
    v1_group_reference: str
    v2_group_reference: str
    v1_status: IdentityGroupHypothesisStatus
    v2_status: IdentityGroupHypothesisStatus


@dataclass(frozen=True)
class ShadowSafetyDelta:
    delta_type: ShadowSafetyDeltaType
    involved_record_references: tuple[str, ...]
    protected_evidence_references: tuple[str, ...]
    explanation: str
    delta_fingerprint: str


@dataclass(frozen=True)
class ShadowComparisonCase:
    case_reference: str
    case_type: ShadowComparisonCaseType
    v1_group_references: tuple[str, ...]
    v2_group_references: tuple[str, ...]
    involved_record_references: tuple[str, ...]
    v1_member_references: tuple[str, ...]
    v2_member_references: tuple[str, ...]
    overlap_metrics: tuple[GroupOverlapMetrics, ...]
    status_transitions: tuple[StatusTransition, ...]
    related_v2_conflict_references: tuple[str, ...]
    related_v2_deferred_references: tuple[str, ...]
    related_v2_unassigned_record_references: tuple[str, ...]
    safety_deltas: tuple[ShadowSafetyDelta, ...]
    adjudication_priority: AdjudicationPriority
    adjudication_reasons: tuple[str, ...]
    case_fingerprint: str


@dataclass(frozen=True)
class ShadowComparisonSummary:
    scan_id: int
    v1_projection_run_id: int
    v2_projection_run_id: int
    v2_source_resolution_run_id: int
    v1_group_count: int
    v2_group_count: int
    v1_likely_group_count: int
    v2_likely_group_count: int
    v1_review_group_count: int
    v2_review_group_count: int
    exact_match_count: int
    exact_member_status_change_count: int
    split_count: int
    merge_count: int
    reassignment_count: int
    v1_only_count: int
    v2_only_count: int
    complex_overlap_count: int
    v1_positive_pair_count: int
    v2_positive_pair_count: int
    positive_pair_intersection_count: int
    v1_only_positive_pair_count: int
    v2_only_positive_pair_count: int
    positive_pair_jaccard: float
    v1_membership_retained_in_v2_ratio: float
    v2_membership_also_present_in_v1_ratio: float
    records_total: int
    records_grouped_v1: int
    records_grouped_v2: int
    records_grouped_both: int
    records_grouped_v1_only: int
    records_grouped_v2_only: int
    records_unassigned_both: int
    v2_conflict_count: int
    v2_deferred_count: int
    critical_case_count: int
    high_case_count: int
    medium_case_count: int
    low_case_count: int
    none_case_count: int
    targeted_evidence_case_count: int
    overlap_graph_edge_count: int
    comparison_fingerprint: str


@dataclass(frozen=True)
class ShadowComparisonResult:
    summary: ShadowComparisonSummary
    cases: tuple[ShadowComparisonCase, ...]
    safety_deltas: tuple[ShadowSafetyDelta, ...]
    comparison_algorithm_version: str
    configuration_fingerprint: str
    comparison_fingerprint: str
