"""Immutable, database-independent GF-6A G2-v2 manifest contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.engine.identity_edge import IdentityEdgeClass
from app.resolution.contracts import (
    BridgeRiskSummary,
    DeferredIdentityReason,
    GenericityRiskSummary,
    GroupEvidenceSummary,
    IdentityConflictType,
    IdentityGroupHypothesisStatus,
    IdentityValidationMode,
    MissingEvidenceSummary,
)


G2_V2_SNAPSHOT_CONTRACT_VERSION = 2
G2_V2_ADAPTER_ALGORITHM_VERSION = "g2-v2-resolution-adapter-v1"


class G2V2EvidenceOrigin(str, Enum):
    PROPOSAL_EVIDENCE = "PROPOSAL_EVIDENCE"
    TARGETED_RESOLUTION_EVIDENCE = "TARGETED_RESOLUTION_EVIDENCE"


@dataclass(frozen=True)
class G2V2AdapterConfiguration:
    configuration_version: str = "g2-v2-adapter-config-v1"
    prefer_proposal_evidence: bool = True


@dataclass(frozen=True)
class G2V2SourceProvenance:
    scan_id: int
    source_resolution_run_id: int
    source_discovery_run_id: int
    source_evidence_run_id: int
    source_resolution_status: str
    source_resolution_fingerprint: str
    source_resolver_algorithm_version: str


@dataclass(frozen=True)
class G2V2GroupMember:
    group_reference: str
    record_id: int
    stable_record_reference: str
    member_order: int


@dataclass(frozen=True)
class G2V2InternalEvidence:
    group_reference: str
    record_id_1: int
    record_id_2: int
    stable_record_reference_1: str
    stable_record_reference_2: str
    edge_class: IdentityEdgeClass
    evidence_origin: G2V2EvidenceOrigin
    source_evidence_reference: str
    supplemental_source_references: tuple[str, ...]
    reason_codes: tuple[str, ...]
    evidence_summary: str
    evaluator_version: str
    evidence_fingerprint: str
    required_for_validation: bool


@dataclass(frozen=True)
class G2V2ValidationCoverage:
    validation_mode: IdentityValidationMode
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
class G2V2GroupSnapshot:
    group_reference: str
    scan_id: int
    status: IdentityGroupHypothesisStatus
    validation_mode: IdentityValidationMode
    member_count: int
    members: tuple[G2V2GroupMember, ...]
    internal_evidence: tuple[G2V2InternalEvidence, ...]
    validation_coverage: G2V2ValidationCoverage
    group_evidence_summary: GroupEvidenceSummary
    bridge_risk_summary: BridgeRiskSummary
    genericity_risk_summary: GenericityRiskSummary
    missing_evidence_summary: MissingEvidenceSummary
    source_hypothesis_fingerprint: str
    source_neighborhood_references: tuple[str, ...]
    group_fingerprint: str


@dataclass(frozen=True)
class G2V2ConflictSnapshot:
    conflict_reference: str
    scan_id: int
    conflict_type: IdentityConflictType
    involved_record_ids: tuple[int, ...]
    involved_record_references: tuple[str, ...]
    protected_evidence_references: tuple[str, ...]
    source_neighborhood_references: tuple[str, ...]
    summary: str
    source_conflict_fingerprint: str
    conflict_fingerprint: str


@dataclass(frozen=True)
class G2V2DeferredSnapshot:
    deferred_reference: str
    scan_id: int
    reason: DeferredIdentityReason
    record_ids: tuple[int, ...]
    record_references: tuple[str, ...]
    unfinished_evidence_summary: str
    source_neighborhood_references: tuple[str, ...]
    source_deferred_fingerprint: str
    deferred_fingerprint: str


@dataclass(frozen=True)
class G2V2SnapshotManifest:
    scan_id: int
    source_resolution_run_id: int
    source_discovery_run_id: int
    source_evidence_run_id: int
    snapshot_contract_version: int
    adapter_algorithm_version: str
    adapter_configuration_fingerprint: str
    source_resolution_fingerprint: str
    groups: tuple[G2V2GroupSnapshot, ...]
    conflicts: tuple[G2V2ConflictSnapshot, ...]
    deferred_work_units: tuple[G2V2DeferredSnapshot, ...]
    unassigned_record_ids: tuple[int, ...]
    unassigned_record_references: tuple[str, ...]
    canonical_record_count: int
    accepted_group_count: int
    likely_group_count: int
    review_group_count: int
    conflict_count: int
    deferred_count: int
    unassigned_record_count: int
    manifest_fingerprint: str
