from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.engine.identity_edge import IdentityEdgeClass


class EvidenceRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class IdentityEvidenceRun:
    evidence_run_id: int
    scan_id: int
    discovery_run_id: int
    algorithm_version: str
    configuration_fingerprint: str
    status: EvidenceRunStatus
    started_at: datetime
    completed_at: datetime | None
    proposal_count_expected: int
    edge_count_persisted: int
    strong_support_count: int
    review_support_count: int
    cannot_link_count: int
    non_groupable_count: int
    safe_failure_category: str | None


@dataclass(frozen=True)
class IdentityEvidenceEdge:
    edge_id: int
    evidence_run_id: int
    scan_id: int
    discovery_run_id: int
    record_id_1: int
    record_id_2: int
    source_proposal_id: int
    edge_class: IdentityEdgeClass
    classification_reason_codes: tuple[str, ...]
    evaluation_algorithm_version: str
    evidence_fingerprint: str
    deterministic_score: float
    component_scores_json: str
    rule_decision: str
    rejection_reason: str
    protected_conflicts_json: str
    generic_evidence_json: str
    technical_evidence_json: str
    uom_context_json: str
    evaluation_context_json: str
    created_at: datetime
