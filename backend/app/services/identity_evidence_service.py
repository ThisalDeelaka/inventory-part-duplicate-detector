"""GF-4 proposal-complete independent deterministic evidence acquisition."""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.models import (
    IdentityDiscoveryRun,
    IdentityEvidenceEdgeSnapshot,
    IdentityEvidenceRun as IdentityEvidenceRunRow,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.engine.identity_evidence_evaluator import (
    IDENTITY_EVIDENCE_EVALUATOR_VERSION,
    DeterministicIdentityContext,
    canonical_json,
    deterministic_context_payload,
    evaluate_canonical_identity_relationship,
    sha256_payload,
)
from app.evidence.contracts import (
    EvidenceRunStatus,
    IdentityEvidenceEdge,
    IdentityEvidenceRun,
)
from app.repositories.discovery_repository import DiscoveryRepository
from app.repositories.evidence_repository import EvidenceRepository
from app.services.canonical_record_service import load_scan_record_catalog


IDENTITY_EVIDENCE_ACQUISITION_VERSION = "independent-identity-evidence-v1"


@dataclass(frozen=True)
class EvidenceAcquisitionResult:
    run: IdentityEvidenceRun
    edges: tuple[IdentityEvidenceEdge, ...]
    idempotent: bool


def _run_contract(row: IdentityEvidenceRunRow) -> IdentityEvidenceRun:
    return IdentityEvidenceRun(
        evidence_run_id=row.id,
        scan_id=row.scan_id,
        discovery_run_id=row.discovery_run_id,
        algorithm_version=row.algorithm_version,
        configuration_fingerprint=row.configuration_fingerprint,
        status=EvidenceRunStatus(row.status),
        started_at=row.started_at,
        completed_at=row.completed_at,
        proposal_count_expected=row.proposal_count_expected,
        edge_count_persisted=row.edge_count_persisted,
        strong_support_count=row.strong_support_count,
        review_support_count=row.review_support_count,
        cannot_link_count=row.cannot_link_count,
        non_groupable_count=row.non_groupable_count,
        safe_failure_category=row.safe_failure_category,
    )


def _configuration(discovery, proposals, context: DeterministicIdentityContext):
    payload = {
        "acquisition_version": IDENTITY_EVIDENCE_ACQUISITION_VERSION,
        "evaluator_version": IDENTITY_EVIDENCE_EVALUATOR_VERSION,
        "discovery_fingerprint": discovery.discovery_fingerprint,
        "proposal_keys": sorted(proposal.proposal_key for proposal in proposals),
        "deterministic_context": deterministic_context_payload(context),
    }
    return sha256_payload(payload), canonical_json(payload)


def start_identity_evidence_run(
    db, *, scan_id: int, discovery_run_id: int, context: DeterministicIdentityContext
) -> IdentityEvidenceRun:
    discovery = db.get(IdentityDiscoveryRun, discovery_run_id)
    if discovery is None or discovery.scan_id != scan_id:
        raise ValueError("evidence discovery run does not belong to the scan")
    if discovery.status != "COMPLETED":
        raise ValueError("GF-4 requires a completed GF-2/GF-3 discovery run")
    discovery_configuration = json.loads(discovery.configuration_json)
    if (
        context.scan_mode != discovery_configuration.get("scan_mode")
        or sorted(set(context.selected_fields))
        != sorted(set(discovery_configuration.get("selected_fields") or []))
    ):
        raise ValueError("identity evidence context is incompatible with discovery")
    proposals = DiscoveryRepository(db).proposals_for_run(discovery_run_id)
    fingerprint, configuration_json = _configuration(discovery, proposals, context)
    repository = EvidenceRepository(db)
    existing = repository.run_for_configuration(
        discovery_run_id, IDENTITY_EVIDENCE_ACQUISITION_VERSION, fingerprint
    )
    if existing is not None:
        return _run_contract(existing)
    row = repository.add_run(
        scan_id=scan_id,
        discovery_run_id=discovery_run_id,
        algorithm_version=IDENTITY_EVIDENCE_ACQUISITION_VERSION,
        configuration_fingerprint=fingerprint,
        configuration_json=configuration_json,
        status=EvidenceRunStatus.RUNNING.value,
        proposal_count_expected=len(proposals),
        edge_count_persisted=0,
        strong_support_count=0,
        review_support_count=0,
        cannot_link_count=0,
        non_groupable_count=0,
    )
    return _run_contract(row)


def _edge_contract(row) -> IdentityEvidenceEdge:
    return IdentityEvidenceEdge(
        edge_id=row.id,
        evidence_run_id=row.evidence_run_id,
        scan_id=row.scan_id,
        discovery_run_id=row.discovery_run_id,
        record_id_1=row.record_id_1,
        record_id_2=row.record_id_2,
        source_proposal_id=row.source_proposal_id,
        edge_class=IdentityEdgeClass(row.edge_class),
        classification_reason_codes=tuple(
            json.loads(row.classification_reason_codes_json)
        ),
        evaluation_algorithm_version=row.evaluation_algorithm_version,
        evidence_fingerprint=row.evidence_fingerprint,
        deterministic_score=row.deterministic_score,
        component_scores_json=row.component_scores_json,
        rule_decision=row.rule_decision,
        rejection_reason=row.rejection_reason,
        protected_conflicts_json=row.protected_conflicts_json,
        generic_evidence_json=row.generic_evidence_json,
        technical_evidence_json=row.technical_evidence_json,
        uom_context_json=row.uom_context_json,
        evaluation_context_json=row.evaluation_context_json,
        created_at=row.created_at,
    )


def _load_and_validate(db, evidence_run_id: int):
    run = db.get(IdentityEvidenceRunRow, evidence_run_id)
    if run is None:
        raise ValueError("identity evidence run does not exist")
    discovery = db.get(IdentityDiscoveryRun, run.discovery_run_id)
    if discovery is None or discovery.scan_id != run.scan_id:
        raise ValueError("identity evidence run has incompatible discovery provenance")
    records = load_scan_record_catalog(db, run.scan_id)
    records_by_id = {record.record_id: record for record in records}
    proposals = DiscoveryRepository(db).proposals_for_run(run.discovery_run_id)
    configuration = json.loads(run.configuration_json)
    context_payload = configuration["deterministic_context"]
    context = DeterministicIdentityContext(
        scan_mode=context_payload["scan_mode"],
        selected_fields=tuple(context_payload["selected_fields"]),
    )
    current_fingerprint, _configuration_json = _configuration(
        discovery, proposals, context
    )
    if current_fingerprint != run.configuration_fingerprint:
        raise ValueError("identity evidence input configuration no longer matches its run")
    proposals_by_id = {proposal.id: proposal for proposal in proposals}
    rows = EvidenceRepository(db).edges_for_run(evidence_run_id)
    for row in rows:
        if row.scan_id != run.scan_id or row.discovery_run_id != run.discovery_run_id:
            raise ValueError("identity evidence edge has incompatible run provenance")
        if row.record_id_1 >= row.record_id_2:
            raise ValueError("identity evidence edge endpoints are not canonical")
        if row.record_id_1 not in records_by_id or row.record_id_2 not in records_by_id:
            raise ValueError("identity evidence edge endpoint is outside its GF-1 catalog")
        proposal = proposals_by_id.get(row.source_proposal_id)
        if (
            proposal is None
            or proposal.discovery_run_id != run.discovery_run_id
            or proposal.scan_id != run.scan_id
            or (proposal.record_id_1, proposal.record_id_2)
            != (row.record_id_1, row.record_id_2)
        ):
            raise ValueError("identity evidence edge does not match its source proposal")
    if run.status == EvidenceRunStatus.COMPLETED.value:
        counts = Counter(row.edge_class for row in rows)
        if (
            len(rows) != run.proposal_count_expected
            or len(rows) != run.edge_count_persisted
            or run.strong_support_count != counts[IdentityEdgeClass.STRONG_SUPPORT.value]
            or run.review_support_count != counts[IdentityEdgeClass.REVIEW_SUPPORT.value]
            or run.cannot_link_count != counts[IdentityEdgeClass.CANNOT_LINK.value]
            or run.non_groupable_count != counts[IdentityEdgeClass.NON_GROUPABLE.value]
        ):
            raise ValueError("completed identity evidence run is incomplete or inconsistent")
    return run, proposals, tuple(_edge_contract(row) for row in rows)


def acquire_identity_evidence(db, *, evidence_run_id: int) -> EvidenceAcquisitionResult:
    run, proposals, existing_edges = _load_and_validate(db, evidence_run_id)
    if run.status == EvidenceRunStatus.COMPLETED.value:
        return EvidenceAcquisitionResult(_run_contract(run), existing_edges, True)
    if run.status != EvidenceRunStatus.RUNNING.value:
        raise ValueError("only a running identity evidence run can acquire edges")
    if existing_edges:
        raise ValueError("running identity evidence run already has partial edge rows")
    if len(proposals) != run.proposal_count_expected:
        raise ValueError("proposal set changed after identity evidence run creation")

    configuration = json.loads(run.configuration_json)
    context_payload = configuration["deterministic_context"]
    context = DeterministicIdentityContext(
        scan_mode=context_payload["scan_mode"],
        selected_fields=tuple(context_payload["selected_fields"]),
    )
    records = load_scan_record_catalog(db, run.scan_id)
    records_by_id = {record.record_id: record for record in records}
    ordered_proposals = sorted(
        proposals,
        key=lambda item: (
            records_by_id[item.record_id_1].record_ref_key,
            records_by_id[item.record_id_2].record_ref_key,
        ),
    )
    pair_keys = {(item.record_id_1, item.record_id_2) for item in ordered_proposals}
    if len(pair_keys) != len(ordered_proposals):
        raise ValueError("discovery run contains duplicate proposal pairs")

    rows = []
    counts = Counter()
    for proposal in ordered_proposals:
        left = records_by_id.get(proposal.record_id_1)
        right = records_by_id.get(proposal.record_id_2)
        if left is None or right is None or proposal.scan_id != run.scan_id:
            raise ValueError("proposal endpoint is outside the evidence run GF-1 catalog")
        evaluated = evaluate_canonical_identity_relationship(left, right, context)
        if (evaluated.record_id_1, evaluated.record_id_2) != (
            proposal.record_id_1, proposal.record_id_2
        ):
            raise ValueError("proposal endpoints are not in canonical database order")
        counts[evaluated.edge_class.value] += 1
        rows.append(IdentityEvidenceEdgeSnapshot(
            evidence_run_id=run.id,
            scan_id=run.scan_id,
            discovery_run_id=run.discovery_run_id,
            record_id_1=evaluated.record_id_1,
            record_id_2=evaluated.record_id_2,
            source_proposal_id=proposal.id,
            edge_class=evaluated.edge_class.value,
            classification_reason_codes_json=canonical_json(
                list(evaluated.classification_reason_codes)
            ),
            evaluation_algorithm_version=evaluated.evaluation_algorithm_version,
            evidence_fingerprint=evaluated.evidence_fingerprint,
            deterministic_score=evaluated.deterministic_score,
            component_scores_json=evaluated.component_scores_json,
            rule_decision=evaluated.rule_decision,
            rejection_reason=evaluated.rejection_reason,
            protected_conflicts_json=evaluated.protected_conflicts_json,
            generic_evidence_json=evaluated.generic_evidence_json,
            technical_evidence_json=evaluated.technical_evidence_json,
            uom_context_json=evaluated.uom_context_json,
            evaluation_context_json=evaluated.evaluation_context_json,
        ))
    EvidenceRepository(db).add_edges(rows)
    persisted = EvidenceRepository(db).edges_for_run(run.id)
    if len(persisted) != len(proposals):
        raise ValueError("identity evidence persistence did not cover every proposal")
    run.edge_count_persisted = len(persisted)
    run.strong_support_count = counts[IdentityEdgeClass.STRONG_SUPPORT.value]
    run.review_support_count = counts[IdentityEdgeClass.REVIEW_SUPPORT.value]
    run.cannot_link_count = counts[IdentityEdgeClass.CANNOT_LINK.value]
    run.non_groupable_count = counts[IdentityEdgeClass.NON_GROUPABLE.value]
    run.status = EvidenceRunStatus.COMPLETED.value
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
    loaded_run, _proposals, edges = _load_and_validate(db, evidence_run_id)
    return EvidenceAcquisitionResult(_run_contract(loaded_run), edges, False)


def mark_identity_evidence_failed(db, evidence_run_id: int, error: Exception) -> None:
    row = db.get(IdentityEvidenceRunRow, evidence_run_id)
    if row is None or row.status != EvidenceRunStatus.RUNNING.value:
        return
    category = re.sub(r"[^A-Z0-9_]+", "_", type(error).__name__.upper())[:80]
    row.status = EvidenceRunStatus.FAILED.value
    row.safe_failure_category = category or "IDENTITY_EVIDENCE_FAILURE"
    row.completed_at = datetime.now(timezone.utc)
    row.edge_count_persisted = 0
    row.strong_support_count = 0
    row.review_support_count = 0
    row.cannot_link_count = 0
    row.non_groupable_count = 0
    db.flush()


def load_identity_evidence(db, evidence_run_id: int) -> EvidenceAcquisitionResult:
    run, _proposals, edges = _load_and_validate(db, evidence_run_id)
    return EvidenceAcquisitionResult(_run_contract(run), edges, True)


def load_evidence_runs_for_discovery(
    db, discovery_run_id: int
) -> tuple[IdentityEvidenceRun, ...]:
    return tuple(
        _run_contract(row)
        for row in EvidenceRepository(db).runs_for_discovery(discovery_run_id)
    )
