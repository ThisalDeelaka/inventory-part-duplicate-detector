"""GF-5C durable resolver lifecycle and non-visible scan integration."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from app.db.models import (
    DuplicateScan,
    IdentityDiscoveryRun,
    IdentityEvidenceRun,
    IdentityResolutionRun,
    IdentityResolutionConflictMember,
    IdentityResolutionConflictSnapshot,
    IdentityResolutionConstraintInput,
    IdentityResolutionDeferredMember,
    IdentityResolutionDeferredSnapshot,
    IdentityResolutionGroupMember,
    IdentityResolutionGroupSnapshot,
    IdentityResolutionTargetedEvidence,
    IdentityResolutionUnassignedRecord,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.engine.identity_evidence_evaluator import DeterministicIdentityContext
from app.repositories.resolution_repository import ResolutionRepository
from app.resolution.contracts import (
    DEFAULT_RESOLVER_ALGORITHM_VERSION,
    BridgeRiskSummary,
    DeferredIdentityReason,
    DeferredIdentityWorkUnit,
    GenericityRiskSummary,
    GroupEvidenceSummary,
    IdentityConflict,
    IdentityConflictType,
    IdentityGroupHypothesis,
    IdentityGroupHypothesisStatus,
    IdentityResolutionInput,
    IdentityResolutionEvidenceEdge,
    IdentityResolutionMetrics,
    IdentityResolutionNeighborhood,
    IdentityResolutionResult,
    IdentityValidationMode,
    MissingEvidenceSummary,
    ResolverConfiguration,
    TargetedEvidenceReason,
    TargetedEvidenceRequest,
    TargetedEvidenceResult,
)
from app.resolution.fingerprints import fingerprint_payload
from app.resolution.resolver import (
    CanonicalEvaluatorTargetedEvidenceProvider,
    resolve_identity_groups,
)
from app.resolution.validation import (
    adapt_effective_human_constraints,
    validate_resolution_result,
)
from app.services.canonical_record_service import load_scan_record_catalog
from app.services.identity_evidence_service import load_identity_evidence
from app.services.identity_group_review_service import IdentityGroupReviewService
from app.services.identity_neighborhood_service import load_identity_neighborhoods


DEFAULT_RESOLVER_CONFIGURATION = ResolverConfiguration(
    max_resolution_members=20,
    max_targeted_checks_per_work_unit=40,
    complete_pairwise_member_limit=8,
    configuration_version="constrained-identity-resolver-config-v1",
)


@dataclass(frozen=True)
class PersistedIdentityResolution:
    resolution_run_id: int
    status: str
    idempotent: bool
    result: IdentityResolutionResult | None
    safe_failure_category: str | None = None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _safe_failure(error: Exception) -> str:
    value = re.sub(r"[^A-Z0-9_]+", "_", type(error).__name__.upper())[:80]
    return value or "IDENTITY_RESOLUTION_FAILURE"


def _resolution_input(
    db, scan_id: int, discovery_run_id: int, evidence_run_id: int,
    configuration: ResolverConfiguration,
) -> IdentityResolutionInput:
    scan = db.get(DuplicateScan, scan_id)
    discovery = db.get(IdentityDiscoveryRun, discovery_run_id)
    evidence = db.get(IdentityEvidenceRun, evidence_run_id)
    if scan is None or discovery is None or evidence is None:
        raise ValueError("GF-5C prerequisite run does not exist")
    if discovery.scan_id != scan_id or evidence.scan_id != scan_id:
        raise ValueError("GF-5C prerequisite run crosses scans")
    if discovery.status != "COMPLETED" or evidence.status != "COMPLETED":
        raise ValueError("GF-5C requires completed discovery and evidence runs")
    if evidence.discovery_run_id != discovery_run_id:
        raise ValueError("GF-5C evidence does not belong to the discovery run")

    records = load_scan_record_catalog(db, scan_id)
    neighborhoods = load_identity_neighborhoods(db, discovery_run_id)
    members = defaultdict(list)
    for member in neighborhoods.members:
        members[member.neighborhood_id].append(member.record_id)
    resolution_neighborhoods = tuple(sorted((
        IdentityResolutionNeighborhood(
            neighborhood_reference=item.neighborhood_fingerprint,
            scan_id=scan_id,
            discovery_run_id=discovery_run_id,
            member_record_ids=tuple(sorted(members[item.neighborhood_id])),
            truncated=item.is_truncated,
            degraded=item.degraded,
        )
        for item in neighborhoods.neighborhoods
    ), key=lambda item: item.neighborhood_reference))
    evidence_result = load_identity_evidence(db, evidence_run_id)
    edges = tuple(sorted((
        IdentityResolutionEvidenceEdge(
            scan_id=scan_id,
            evidence_run_id=evidence_run_id,
            record_id_1=item.record_id_1,
            record_id_2=item.record_id_2,
            edge_class=item.edge_class,
            reason_codes=tuple(sorted(item.classification_reason_codes)),
            evidence_fingerprint=item.evidence_fingerprint,
            generic_only=bool(json.loads(item.generic_evidence_json).get("generic_guard_reason")),
        ) for item in evidence_result.edges
    ), key=lambda item: (item.record_id_1, item.record_id_2)))
    effective = IdentityGroupReviewService(db).effective_constraints(scan_id)
    constraints = adapt_effective_human_constraints(
        scan_id=scan_id, canonical_records=records, effective_constraints=effective
    )
    return IdentityResolutionInput(
        scan_id=scan_id,
        discovery_run_id=discovery_run_id,
        evidence_run_id=evidence_run_id,
        canonical_records=records,
        identity_neighborhoods=resolution_neighborhoods,
        machine_evidence_edges=edges,
        human_constraints=constraints,
        resolver_algorithm_version=DEFAULT_RESOLVER_ALGORITHM_VERSION,
        resolver_configuration=configuration,
    )


def resolution_input_fingerprint(value: IdentityResolutionInput) -> str:
    refs = {record.record_id: record.record_ref_key for record in value.canonical_records}
    return fingerprint_payload("identity-resolution-input", {
        "records": tuple((r.record_ref_key, r.source_record_fingerprint) for r in value.canonical_records),
        "neighborhoods": tuple({
            "reference": n.neighborhood_reference,
            "members": tuple(refs[item] for item in n.member_record_ids),
            "truncated": n.truncated,
            "degraded": n.degraded,
        } for n in value.identity_neighborhoods),
        "evidence": tuple({
            "pair": (refs[e.record_id_1], refs[e.record_id_2]),
            "class": e.edge_class,
            "fingerprint": e.evidence_fingerprint,
            "generic_only": e.generic_only,
        } for e in value.machine_evidence_edges),
        "constraints": tuple({
            "pair": (refs[c.record_id_1], refs[c.record_id_2]),
            "type": c.constraint_type,
            "authority": c.source_authority,
            "reference": c.source_reference,
        } for c in value.human_constraints),
        "resolver_algorithm_version": value.resolver_algorithm_version,
        "configuration": value.resolver_configuration,
    })


def _persist_result(repository, run, value, result):
    for group in result.accepted_groups:
        row = IdentityResolutionGroupSnapshot(
            resolution_run_id=run.id, scan_id=run.scan_id,
            hypothesis_id=group.hypothesis_id, status=group.status.value,
            validation_mode=group.validation_mode.value,
            member_count=len(group.member_record_ids),
            evidence_summary_json=_json(asdict(group.evidence_summary)),
            bridge_risk_summary_json=_json(asdict(group.bridge_risk_summary)),
            genericity_risk_summary_json=_json(asdict(group.genericity_risk_summary)),
            missing_evidence_summary_json=_json(asdict(group.missing_evidence_summary)),
            source_neighborhood_references_json=_json(group.source_neighborhood_references),
            hypothesis_fingerprint=group.hypothesis_fingerprint,
        )
        repository.add_all([row])
        repository.add_all([
            IdentityResolutionGroupMember(
                resolution_run_id=run.id, group_snapshot_id=row.id, scan_id=run.scan_id,
                record_id=record_id, record_ref_key=record_ref, member_index=index,
            ) for index, (record_id, record_ref) in enumerate(zip(
                group.member_record_ids, group.member_record_references
            ))
        ])
    for conflict in result.conflicts:
        row = IdentityResolutionConflictSnapshot(
            resolution_run_id=run.id, scan_id=run.scan_id,
            conflict_id=conflict.conflict_id, conflict_type=conflict.conflict_type.value,
            protected_evidence_references_json=_json(conflict.protected_evidence_references),
            source_neighborhood_references_json=_json(conflict.source_neighborhood_references),
            summary=conflict.summary, fingerprint=conflict.fingerprint,
        )
        repository.add_all([row])
        repository.add_all([
            IdentityResolutionConflictMember(
                resolution_run_id=run.id, conflict_snapshot_id=row.id,
                record_id=record_id, record_ref_key=record_ref, member_index=index,
            ) for index, (record_id, record_ref) in enumerate(zip(
                conflict.involved_record_ids, conflict.involved_record_references
            ))
        ])
    for deferred in result.deferred_work_units:
        row = IdentityResolutionDeferredSnapshot(
            resolution_run_id=run.id, scan_id=run.scan_id,
            deferred_id=deferred.deferred_id, reason=deferred.reason.value,
            unfinished_evidence_summary=deferred.unfinished_evidence_summary,
            source_neighborhood_references_json=_json(deferred.source_neighborhood_references),
            fingerprint=deferred.fingerprint,
        )
        repository.add_all([row])
        repository.add_all([
            IdentityResolutionDeferredMember(
                resolution_run_id=run.id, deferred_snapshot_id=row.id,
                record_id=record_id, record_ref_key=record_ref, member_index=index,
            ) for index, (record_id, record_ref) in enumerate(zip(
                deferred.record_ids, deferred.record_references
            ))
        ])
    results = {item.request.request_fingerprint: item for item in result.targeted_evidence_results}
    repository.add_all([
        IdentityResolutionTargetedEvidence(
            resolution_run_id=run.id, scan_id=run.scan_id,
            record_id_1=request.record_id_1, record_id_2=request.record_id_2,
            record_ref_key_1=request.record_reference_1,
            record_ref_key_2=request.record_reference_2, reason=request.reason.value,
            requesting_work_unit_reference=request.requesting_work_unit_reference,
            request_fingerprint=request.request_fingerprint,
            evaluation_completed=request.request_fingerprint in results,
            edge_class=(results[request.request_fingerprint].edge_class.value if request.request_fingerprint in results else None),
            reason_codes_json=(_json(results[request.request_fingerprint].reason_codes) if request.request_fingerprint in results else None),
            evidence_summary=(results[request.request_fingerprint].evidence_summary if request.request_fingerprint in results else None),
            evaluator_version=(results[request.request_fingerprint].evaluator_version if request.request_fingerprint in results else None),
            evidence_fingerprint=(results[request.request_fingerprint].evidence_fingerprint if request.request_fingerprint in results else None),
            generic_only=(results[request.request_fingerprint].generic_only if request.request_fingerprint in results else None),
        ) for request in result.targeted_evidence_requests
    ])
    repository.add_all([
        IdentityResolutionUnassignedRecord(
            resolution_run_id=run.id, scan_id=run.scan_id,
            record_id=record_id, record_ref_key=record_ref, unassigned_index=index,
        ) for index, (record_id, record_ref) in enumerate(zip(
            result.unassigned_record_ids, result.unassigned_record_references
        ))
    ])
    refs = {record.record_id: record.record_ref_key for record in value.canonical_records}
    repository.add_all([
        IdentityResolutionConstraintInput(
            resolution_run_id=run.id, scan_id=run.scan_id,
            record_id_1=item.record_id_1, record_id_2=item.record_id_2,
            record_ref_key_1=refs[item.record_id_1], record_ref_key_2=refs[item.record_id_2],
            constraint_type=item.constraint_type.value,
            source_authority=item.source_authority, source_reference=item.source_reference,
        ) for item in value.human_constraints
    ])


def _tuple_pairs(values):
    return tuple(tuple(item) for item in values)


def load_persisted_resolution_result(db, resolution_run_id: int) -> IdentityResolutionResult:
    repository = ResolutionRepository(db)
    run = db.get(IdentityResolutionRun, resolution_run_id)
    if run is None or run.status != "COMPLETED":
        raise ValueError("completed identity resolution run not found")
    groups, group_members, conflicts, conflict_members, deferred, deferred_members, targeted, unassigned = repository.result_rows(run.id)
    group_members_by_id, conflict_members_by_id, deferred_members_by_id = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in group_members: group_members_by_id[row.group_snapshot_id].append(row)
    for row in conflict_members: conflict_members_by_id[row.conflict_snapshot_id].append(row)
    for row in deferred_members: deferred_members_by_id[row.deferred_snapshot_id].append(row)
    group_contracts = []
    for row in groups:
        members = group_members_by_id[row.id]
        bridge = json.loads(row.bridge_risk_summary_json)
        bridge.update(
            articulation_record_ids=tuple(bridge["articulation_record_ids"]),
            single_edge_branch_record_ids=tuple(bridge["single_edge_branch_record_ids"]),
            neutral_cross_branch_pairs=_tuple_pairs(bridge["neutral_cross_branch_pairs"]),
            missing_cross_branch_pairs=_tuple_pairs(bridge["missing_cross_branch_pairs"]),
            generic_hub_record_ids=tuple(bridge["generic_hub_record_ids"]),
            competing_partition_evidence=tuple(bridge["competing_partition_evidence"]),
        )
        genericity = json.loads(row.genericity_risk_summary_json)
        genericity["hub_dependency_record_ids"] = tuple(genericity["hub_dependency_record_ids"])
        missing = json.loads(row.missing_evidence_summary_json)
        missing["missing_pairs"] = _tuple_pairs(missing["missing_pairs"])
        missing["incomplete_reason_codes"] = tuple(missing["incomplete_reason_codes"])
        evidence = json.loads(row.evidence_summary_json)
        evidence["validation_mode"] = IdentityValidationMode(evidence["validation_mode"])
        group_contracts.append(IdentityGroupHypothesis(
            hypothesis_id=row.hypothesis_id, scan_id=row.scan_id,
            member_record_ids=tuple(item.record_id for item in members),
            member_record_references=tuple(item.record_ref_key for item in members),
            status=IdentityGroupHypothesisStatus(row.status),
            validation_mode=IdentityValidationMode(row.validation_mode),
            evidence_summary=GroupEvidenceSummary(**evidence),
            bridge_risk_summary=BridgeRiskSummary(**bridge),
            genericity_risk_summary=GenericityRiskSummary(**genericity),
            missing_evidence_summary=MissingEvidenceSummary(**missing),
            source_neighborhood_references=tuple(json.loads(row.source_neighborhood_references_json)),
            hypothesis_fingerprint=row.hypothesis_fingerprint,
        ))
    conflict_contracts = tuple(IdentityConflict(
        conflict_id=row.conflict_id, scan_id=row.scan_id,
        involved_record_ids=tuple(item.record_id for item in conflict_members_by_id[row.id]),
        involved_record_references=tuple(item.record_ref_key for item in conflict_members_by_id[row.id]),
        conflict_type=IdentityConflictType(row.conflict_type),
        protected_evidence_references=tuple(json.loads(row.protected_evidence_references_json)),
        source_neighborhood_references=tuple(json.loads(row.source_neighborhood_references_json)),
        summary=row.summary, fingerprint=row.fingerprint,
    ) for row in conflicts)
    deferred_contracts = tuple(DeferredIdentityWorkUnit(
        deferred_id=row.deferred_id, scan_id=row.scan_id,
        record_ids=tuple(item.record_id for item in deferred_members_by_id[row.id]),
        record_references=tuple(item.record_ref_key for item in deferred_members_by_id[row.id]),
        reason=DeferredIdentityReason(row.reason),
        unfinished_evidence_summary=row.unfinished_evidence_summary,
        source_neighborhood_references=tuple(json.loads(row.source_neighborhood_references_json)),
        fingerprint=row.fingerprint,
    ) for row in deferred)
    requests, results = [], []
    for row in targeted:
        request = TargetedEvidenceRequest(
            scan_id=row.scan_id, record_id_1=row.record_id_1, record_id_2=row.record_id_2,
            reason=TargetedEvidenceReason(row.reason),
            requesting_work_unit_reference=row.requesting_work_unit_reference,
            request_fingerprint=row.request_fingerprint,
            record_reference_1=row.record_ref_key_1, record_reference_2=row.record_ref_key_2,
        )
        requests.append(request)
        if row.evaluation_completed:
            results.append(TargetedEvidenceResult(
                request=request, edge_class=IdentityEdgeClass(row.edge_class),
                reason_codes=tuple(json.loads(row.reason_codes_json)),
                evidence_summary=row.evidence_summary, evaluator_version=row.evaluator_version,
                evidence_fingerprint=row.evidence_fingerprint, generic_only=bool(row.generic_only),
            ))
    metrics = IdentityResolutionMetrics(**{
        name: getattr(run, name) for name in IdentityResolutionMetrics.__dataclass_fields__
    })
    return IdentityResolutionResult(
        scan_id=run.scan_id, accepted_groups=tuple(group_contracts),
        conflicts=conflict_contracts, deferred_work_units=deferred_contracts,
        unassigned_record_ids=tuple(row.record_id for row in unassigned),
        unassigned_record_references=tuple(row.record_ref_key for row in unassigned),
        targeted_evidence_requests=tuple(requests),
        targeted_evidence_results=tuple(sorted(
            results, key=lambda item: item.request.request_fingerprint
        )),
        metrics=metrics, resolver_algorithm_version=run.resolver_algorithm_version,
        resolution_fingerprint=run.resolution_fingerprint,
    )


def resolve_and_persist_identity_groups(
    db, *, scan_id: int, discovery_run_id: int, evidence_run_id: int,
    configuration: ResolverConfiguration = DEFAULT_RESOLVER_CONFIGURATION,
) -> PersistedIdentityResolution:
    """Run GF-5 exactly once for stable inputs; persist failure without escaping."""
    value = _resolution_input(db, scan_id, discovery_run_id, evidence_run_id, configuration)
    input_fingerprint = resolution_input_fingerprint(value)
    configuration_fingerprint = fingerprint_payload("resolver-configuration", configuration)
    constraint_fingerprint = fingerprint_payload("effective-human-constraints", value.human_constraints)
    identity = dict(
        scan_id=scan_id, discovery_run_id=discovery_run_id, evidence_run_id=evidence_run_id,
        resolver_algorithm_version=value.resolver_algorithm_version,
        configuration_fingerprint=configuration_fingerprint,
        input_fingerprint=input_fingerprint,
    )
    repository = ResolutionRepository(db)
    existing = repository.run_for_input(**identity)
    if existing is not None:
        result = load_persisted_resolution_result(db, existing.id) if existing.status == "COMPLETED" else None
        return PersistedIdentityResolution(
            existing.id, existing.status, True, result, existing.safe_failure_category
        )
    run = repository.add_run(
        **identity, configuration_version=configuration.configuration_version,
        configuration_json=_json(asdict(configuration)), status="RUNNING",
        source_record_count=len(value.canonical_records),
        effective_constraint_count=len(value.human_constraints),
        effective_constraint_fingerprint=constraint_fingerprint,
        provider_request_count=0,
    )
    db.commit()
    run_id = run.id
    try:
        scan = db.get(DuplicateScan, scan_id)
        provider = CanonicalEvaluatorTargetedEvidenceProvider(
            value.canonical_records,
            DeterministicIdentityContext(
                scan_mode=scan.scan_mode,
                selected_fields=tuple(json.loads(scan.selected_fields)),
            ),
        )
        result = resolve_identity_groups(value, provider)
        run = db.get(type(run), run_id)
        _persist_result(repository, run, value, result)
        metrics = result.metrics
        for name in IdentityResolutionMetrics.__dataclass_fields__:
            setattr(run, name, getattr(metrics, name))
        run.resolution_fingerprint = result.resolution_fingerprint
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        reloaded = load_persisted_resolution_result(db, run_id)
        validate_resolution_result(reloaded, value)
        if reloaded != result:
            raise ValueError("persisted resolution differs from the pure resolver output")
        db.commit()
        return PersistedIdentityResolution(run_id, "COMPLETED", False, reloaded)
    except Exception as error:
        db.rollback()
        run = db.get(type(run), run_id)
        if run is not None and run.status == "RUNNING":
            run.status = "FAILED"
            run.completed_at = datetime.now(timezone.utc)
            run.safe_failure_category = _safe_failure(error)
            db.commit()
        return PersistedIdentityResolution(
            run_id, "FAILED", False, None, _safe_failure(error)
        )
