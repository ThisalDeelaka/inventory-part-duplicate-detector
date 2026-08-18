"""GF-6B immutable, non-current G2-v2 persistence and reconstruction."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from app.db.models import (
    G2V2ConflictMemberRow,
    G2V2ConflictSnapshotRow,
    G2V2DeferredMemberRow,
    G2V2DeferredSnapshotRow,
    G2V2GroupMemberRow,
    G2V2GroupSnapshotRow,
    G2V2InternalEvidenceRow,
    G2V2ProjectionRun,
    G2V2UnassignedRecordRow,
    IdentityResolutionRun,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.g2_v2.adapter import build_g2_v2_manifest
from app.g2_v2.contracts import (
    G2V2AdapterConfiguration,
    G2V2ConflictSnapshot,
    G2V2DeferredSnapshot,
    G2V2EvidenceOrigin,
    G2V2GroupMember,
    G2V2GroupSnapshot,
    G2V2InternalEvidence,
    G2V2SnapshotManifest,
    G2V2SourceProvenance,
    G2V2ValidationCoverage,
)
from app.g2_v2.validation import validate_g2_v2_manifest
from app.repositories.g2_v2_projection_repository import G2V2ProjectionRepository
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
from app.services.canonical_record_service import load_scan_record_catalog
from app.services.identity_evidence_service import load_identity_evidence
from app.services.identity_resolution_service import load_persisted_resolution_result


@dataclass(frozen=True)
class G2V2ProjectionSummary:
    projection_run_id: int
    status: str
    idempotent: bool
    manifest_fingerprint: str
    manifest: G2V2SnapshotManifest | None
    safe_failure_category: str | None = None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _safe_failure(error: Exception) -> str:
    value = re.sub(r"[^A-Z0-9_]+", "_", type(error).__name__.upper())[:80]
    return value or "G2_V2_PROJECTION_FAILURE"


def _bridge(value):
    value = dict(value)
    for name in (
        "articulation_record_ids", "single_edge_branch_record_ids",
        "generic_hub_record_ids", "competing_partition_evidence",
    ):
        value[name] = tuple(value[name])
    for name in ("neutral_cross_branch_pairs", "missing_cross_branch_pairs"):
        value[name] = tuple(tuple(item) for item in value[name])
    return BridgeRiskSummary(**value)


def _genericity(value):
    value = dict(value)
    value["hub_dependency_record_ids"] = tuple(value["hub_dependency_record_ids"])
    return GenericityRiskSummary(**value)


def _missing(value):
    value = dict(value)
    value["missing_pairs"] = tuple(tuple(item) for item in value["missing_pairs"])
    value["incomplete_reason_codes"] = tuple(value["incomplete_reason_codes"])
    return MissingEvidenceSummary(**value)


def _group_evidence(value):
    value = dict(value)
    value["validation_mode"] = IdentityValidationMode(value["validation_mode"])
    return GroupEvidenceSummary(**value)


def _persist_manifest(repository, run, manifest):
    for group in manifest.groups:
        row = G2V2GroupSnapshotRow(
            projection_run_id=run.id, scan_id=run.scan_id,
            group_reference=group.group_reference, status=group.status.value,
            validation_mode=group.validation_mode.value, member_count=group.member_count,
            group_evidence_summary_json=_json(asdict(group.group_evidence_summary)),
            bridge_risk_summary_json=_json(asdict(group.bridge_risk_summary)),
            genericity_risk_summary_json=_json(asdict(group.genericity_risk_summary)),
            missing_evidence_summary_json=_json(asdict(group.missing_evidence_summary)),
            validation_coverage_json=_json(asdict(group.validation_coverage)),
            source_hypothesis_fingerprint=group.source_hypothesis_fingerprint,
            source_neighborhood_references_json=_json(group.source_neighborhood_references),
            group_fingerprint=group.group_fingerprint,
        )
        repository.add_all([row])
        repository.add_all([G2V2GroupMemberRow(
            projection_run_id=run.id, group_snapshot_id=row.id, scan_id=run.scan_id,
            record_id=item.record_id,
            stable_record_reference=item.stable_record_reference,
            member_order=item.member_order,
        ) for item in group.members])
        repository.add_all([G2V2InternalEvidenceRow(
            projection_run_id=run.id, group_snapshot_id=row.id,
            record_id_1=item.record_id_1, record_id_2=item.record_id_2,
            stable_record_reference_1=item.stable_record_reference_1,
            stable_record_reference_2=item.stable_record_reference_2,
            edge_class=item.edge_class.value, evidence_origin=item.evidence_origin.value,
            source_evidence_reference=item.source_evidence_reference,
            supplemental_source_references_json=_json(item.supplemental_source_references),
            reason_codes_json=_json(item.reason_codes),
            evidence_summary=item.evidence_summary, evaluator_version=item.evaluator_version,
            evidence_fingerprint=item.evidence_fingerprint,
            required_for_validation=item.required_for_validation,
        ) for item in group.internal_evidence])
    for conflict in manifest.conflicts:
        row = G2V2ConflictSnapshotRow(
            projection_run_id=run.id, scan_id=run.scan_id,
            conflict_reference=conflict.conflict_reference,
            conflict_type=conflict.conflict_type.value, summary=conflict.summary,
            protected_evidence_references_json=_json(conflict.protected_evidence_references),
            source_neighborhood_references_json=_json(conflict.source_neighborhood_references),
            source_conflict_fingerprint=conflict.source_conflict_fingerprint,
            conflict_fingerprint=conflict.conflict_fingerprint,
        )
        repository.add_all([row])
        repository.add_all([G2V2ConflictMemberRow(
            projection_run_id=run.id, conflict_snapshot_id=row.id,
            record_id=record_id, stable_record_reference=record_ref,
            member_order=index,
        ) for index, (record_id, record_ref) in enumerate(zip(
            conflict.involved_record_ids, conflict.involved_record_references
        ))])
    for deferred in manifest.deferred_work_units:
        row = G2V2DeferredSnapshotRow(
            projection_run_id=run.id, scan_id=run.scan_id,
            deferred_reference=deferred.deferred_reference, reason=deferred.reason.value,
            unfinished_evidence_summary=deferred.unfinished_evidence_summary,
            source_neighborhood_references_json=_json(deferred.source_neighborhood_references),
            source_deferred_fingerprint=deferred.source_deferred_fingerprint,
            deferred_fingerprint=deferred.deferred_fingerprint,
        )
        repository.add_all([row])
        repository.add_all([G2V2DeferredMemberRow(
            projection_run_id=run.id, deferred_snapshot_id=row.id,
            record_id=record_id, stable_record_reference=record_ref,
            member_order=index,
        ) for index, (record_id, record_ref) in enumerate(zip(
            deferred.record_ids, deferred.record_references
        ))])
    repository.add_all([G2V2UnassignedRecordRow(
        projection_run_id=run.id, record_id=record_id,
        stable_record_reference=record_ref, member_order=index,
    ) for index, (record_id, record_ref) in enumerate(zip(
        manifest.unassigned_record_ids, manifest.unassigned_record_references
    ))])


def load_persisted_g2_v2_manifest(db, projection_run_id: int) -> G2V2SnapshotManifest:
    """Reconstruct one terminal completed manifest with eight bounded SELECTs."""
    run = db.get(G2V2ProjectionRun, projection_run_id)
    if run is None or run.status != "COMPLETED":
        raise ValueError("completed G2-v2 projection run not found")
    rows = G2V2ProjectionRepository(db).result_rows(run.id)
    groups, members, evidence, conflicts, conflict_members, deferred, deferred_members, unassigned = rows
    members_by_group, evidence_by_group = defaultdict(list), defaultdict(list)
    conflict_members_by_id, deferred_members_by_id = defaultdict(list), defaultdict(list)
    for item in members: members_by_group[item.group_snapshot_id].append(item)
    for item in evidence: evidence_by_group[item.group_snapshot_id].append(item)
    for item in conflict_members: conflict_members_by_id[item.conflict_snapshot_id].append(item)
    for item in deferred_members: deferred_members_by_id[item.deferred_snapshot_id].append(item)
    group_contracts = []
    for row in groups:
        coverage = json.loads(row.validation_coverage_json)
        coverage["validation_mode"] = IdentityValidationMode(coverage["validation_mode"])
        group_contracts.append(G2V2GroupSnapshot(
            group_reference=row.group_reference, scan_id=row.scan_id,
            status=IdentityGroupHypothesisStatus(row.status),
            validation_mode=IdentityValidationMode(row.validation_mode),
            member_count=row.member_count,
            members=tuple(G2V2GroupMember(
                group_reference=row.group_reference, record_id=item.record_id,
                stable_record_reference=item.stable_record_reference,
                member_order=item.member_order,
            ) for item in members_by_group[row.id]),
            internal_evidence=tuple(G2V2InternalEvidence(
                group_reference=row.group_reference,
                record_id_1=item.record_id_1, record_id_2=item.record_id_2,
                stable_record_reference_1=item.stable_record_reference_1,
                stable_record_reference_2=item.stable_record_reference_2,
                edge_class=IdentityEdgeClass(item.edge_class),
                evidence_origin=G2V2EvidenceOrigin(item.evidence_origin),
                source_evidence_reference=item.source_evidence_reference,
                supplemental_source_references=tuple(json.loads(item.supplemental_source_references_json)),
                reason_codes=tuple(json.loads(item.reason_codes_json)),
                evidence_summary=item.evidence_summary, evaluator_version=item.evaluator_version,
                evidence_fingerprint=item.evidence_fingerprint,
                required_for_validation=item.required_for_validation,
            ) for item in evidence_by_group[row.id]),
            validation_coverage=G2V2ValidationCoverage(**coverage),
            group_evidence_summary=_group_evidence(json.loads(row.group_evidence_summary_json)),
            bridge_risk_summary=_bridge(json.loads(row.bridge_risk_summary_json)),
            genericity_risk_summary=_genericity(json.loads(row.genericity_risk_summary_json)),
            missing_evidence_summary=_missing(json.loads(row.missing_evidence_summary_json)),
            source_hypothesis_fingerprint=row.source_hypothesis_fingerprint,
            source_neighborhood_references=tuple(json.loads(row.source_neighborhood_references_json)),
            group_fingerprint=row.group_fingerprint,
        ))
    conflict_contracts = tuple(G2V2ConflictSnapshot(
        conflict_reference=row.conflict_reference, scan_id=row.scan_id,
        conflict_type=IdentityConflictType(row.conflict_type),
        involved_record_ids=tuple(item.record_id for item in conflict_members_by_id[row.id]),
        involved_record_references=tuple(item.stable_record_reference for item in conflict_members_by_id[row.id]),
        protected_evidence_references=tuple(json.loads(row.protected_evidence_references_json)),
        source_neighborhood_references=tuple(json.loads(row.source_neighborhood_references_json)),
        summary=row.summary, source_conflict_fingerprint=row.source_conflict_fingerprint,
        conflict_fingerprint=row.conflict_fingerprint,
    ) for row in conflicts)
    deferred_contracts = tuple(G2V2DeferredSnapshot(
        deferred_reference=row.deferred_reference, scan_id=row.scan_id,
        reason=DeferredIdentityReason(row.reason),
        record_ids=tuple(item.record_id for item in deferred_members_by_id[row.id]),
        record_references=tuple(item.stable_record_reference for item in deferred_members_by_id[row.id]),
        unfinished_evidence_summary=row.unfinished_evidence_summary,
        source_neighborhood_references=tuple(json.loads(row.source_neighborhood_references_json)),
        source_deferred_fingerprint=row.source_deferred_fingerprint,
        deferred_fingerprint=row.deferred_fingerprint,
    ) for row in deferred)
    return G2V2SnapshotManifest(
        scan_id=run.scan_id, source_resolution_run_id=run.source_resolution_run_id,
        source_discovery_run_id=run.source_discovery_run_id,
        source_evidence_run_id=run.source_evidence_run_id,
        snapshot_contract_version=run.snapshot_contract_version,
        adapter_algorithm_version=run.adapter_algorithm_version,
        adapter_configuration_fingerprint=run.adapter_configuration_fingerprint,
        source_resolution_fingerprint=run.source_manifest_fingerprint,
        groups=tuple(group_contracts), conflicts=conflict_contracts,
        deferred_work_units=deferred_contracts,
        unassigned_record_ids=tuple(item.record_id for item in unassigned),
        unassigned_record_references=tuple(item.stable_record_reference for item in unassigned),
        canonical_record_count=run.canonical_record_count,
        accepted_group_count=run.accepted_group_count,
        likely_group_count=run.likely_group_count,
        review_group_count=run.review_group_count,
        conflict_count=run.conflict_count, deferred_count=run.deferred_count,
        unassigned_record_count=run.unassigned_record_count,
        manifest_fingerprint=run.manifest_fingerprint,
    )


def build_and_persist_g2_v2_projection(
    db, *, scan_id: int, resolution_run_id: int,
    configuration: G2V2AdapterConfiguration = G2V2AdapterConfiguration(),
) -> G2V2ProjectionSummary:
    source_run = db.get(IdentityResolutionRun, resolution_run_id)
    if source_run is None or source_run.status != "COMPLETED":
        raise ValueError("GF-6B requires a completed GF-5C resolution run")
    if source_run.scan_id != scan_id:
        raise ValueError("GF-6B source resolution crosses scans")
    result = load_persisted_resolution_result(db, resolution_run_id)
    records = load_scan_record_catalog(db, scan_id)
    evidence = load_identity_evidence(db, source_run.evidence_run_id)
    if (
        evidence.run.status.value != "COMPLETED"
        or evidence.run.scan_id != scan_id
        or evidence.run.discovery_run_id != source_run.discovery_run_id
    ):
        raise ValueError("GF-6B evidence provenance is incompatible")
    provenance = G2V2SourceProvenance(
        scan_id=scan_id, source_resolution_run_id=source_run.id,
        source_discovery_run_id=source_run.discovery_run_id,
        source_evidence_run_id=source_run.evidence_run_id,
        source_resolution_status=source_run.status,
        source_resolution_fingerprint=source_run.resolution_fingerprint,
        source_resolver_algorithm_version=source_run.resolver_algorithm_version,
    )
    manifest = build_g2_v2_manifest(
        result, records, evidence.edges, result.targeted_evidence_results,
        provenance, configuration,
    )
    identity = dict(
        scan_id=scan_id, source_resolution_run_id=source_run.id,
        adapter_algorithm_version=manifest.adapter_algorithm_version,
        adapter_configuration_fingerprint=manifest.adapter_configuration_fingerprint,
        source_manifest_fingerprint=manifest.source_resolution_fingerprint,
        manifest_fingerprint=manifest.manifest_fingerprint,
    )
    repository = G2V2ProjectionRepository(db)
    existing = repository.run_for_identity(**identity)
    if existing is not None:
        loaded = load_persisted_g2_v2_manifest(db, existing.id) if existing.status == "COMPLETED" else None
        if loaded is not None and loaded != manifest:
            raise ValueError("completed G2-v2 projection differs from its pure manifest")
        return G2V2ProjectionSummary(
            existing.id, existing.status, True, existing.manifest_fingerprint,
            loaded, existing.safe_failure_category,
        )
    run = repository.add_run(
        **identity, source_discovery_run_id=source_run.discovery_run_id,
        source_evidence_run_id=source_run.evidence_run_id,
        snapshot_contract_version=manifest.snapshot_contract_version,
        status="RUNNING",
    )
    db.commit()
    run_id = run.id
    try:
        run = db.get(G2V2ProjectionRun, run_id)
        _persist_manifest(repository, run, manifest)
        for name in (
            "canonical_record_count", "accepted_group_count", "likely_group_count",
            "review_group_count", "conflict_count", "deferred_count",
            "unassigned_record_count",
        ):
            setattr(run, name, getattr(manifest, name))
        db.flush()
        # Reconstruct before completion by temporarily using the same bounded loader logic.
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        loaded = load_persisted_g2_v2_manifest(db, run_id)
        validate_g2_v2_manifest(
            loaded, result, records, evidence.edges,
            result.targeted_evidence_results, provenance,
        )
        if loaded != manifest:
            raise ValueError("persisted G2-v2 manifest differs from pure GF-6A output")
        db.commit()
        return G2V2ProjectionSummary(
            run_id, "COMPLETED", False, manifest.manifest_fingerprint, loaded
        )
    except Exception as error:
        db.rollback()
        run = db.get(G2V2ProjectionRun, run_id)
        if run is not None and run.status == "RUNNING":
            run.status = "FAILED"
            run.completed_at = datetime.now(timezone.utc)
            run.safe_failure_category = _safe_failure(error)
            db.commit()
        return G2V2ProjectionSummary(
            run_id, "FAILED", False, manifest.manifest_fingerprint, None,
            _safe_failure(error),
        )
