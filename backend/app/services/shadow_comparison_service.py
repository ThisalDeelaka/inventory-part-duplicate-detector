"""GF-7B controlled, non-visible persistence for pure GF-7A comparisons."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

from app.db.models import (
    G2V2ProjectionRun,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    IdentityResolutionRun,
    ShadowComparisonCaseDeltaRow,
    ShadowComparisonCaseGroupRow,
    ShadowComparisonCaseRecordRow,
    ShadowComparisonCaseRow,
    ShadowComparisonRun,
    ShadowComparisonSafetyDeltaRow,
)
from app.repositories.shadow_comparison_repository import ShadowComparisonRepository
from app.resolution.contracts import IdentityGroupHypothesisStatus
from app.services.canonical_record_service import load_scan_record_catalog
from app.services.g2_v2_projection_service import load_persisted_g2_v2_manifest
from app.shadow_comparison.comparison import compare_g2_v1_v2
from app.shadow_comparison.contracts import (
    SHADOW_COMPARISON_ALGORITHM_VERSION,
    AdjudicationPriority,
    ComparisonIdentitySet,
    ComparisonSourceVersion,
    GroupOverlapMetrics,
    ShadowComparisonCase,
    ShadowComparisonCaseType,
    ShadowComparisonConfiguration,
    ShadowComparisonInput,
    ShadowComparisonResult,
    ShadowComparisonSummary,
    ShadowSafetyDelta,
    ShadowSafetyDeltaType,
    StatusTransition,
    V1ComparisonSnapshot,
)
from app.shadow_comparison.fingerprints import shadow_fingerprint


_SUMMARY_FIELDS = tuple(
    name for name in ShadowComparisonSummary.__dataclass_fields__
    if name not in {
        "scan_id", "v1_projection_run_id", "v2_projection_run_id",
        "v2_source_resolution_run_id", "comparison_fingerprint",
    }
)
_PRIORITY_RANK = {
    AdjudicationPriority.NONE: 0,
    AdjudicationPriority.LOW: 1,
    AdjudicationPriority.MEDIUM: 2,
    AdjudicationPriority.HIGH: 3,
    AdjudicationPriority.CRITICAL: 4,
}


@dataclass(frozen=True)
class ShadowComparisonPersistenceSummary:
    comparison_run_id: int
    status: str
    idempotent: bool
    input_fingerprint: str
    comparison_fingerprint: str | None
    result: ShadowComparisonResult | None
    safe_failure_category: str | None = None


def _canonical(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _json(value) -> str:
    return json.dumps(_canonical(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _safe_failure(error: Exception) -> str:
    value = re.sub(r"[^A-Z0-9_]+", "_", type(error).__name__.upper())[:80]
    return value or "SHADOW_COMPARISON_FAILURE"


def _load_v1_snapshot(db, run: IdentityGroupProjectionRun, records) -> V1ComparisonSnapshot:
    groups = db.query(IdentityGroupSnapshot).filter_by(
        projection_run_id=run.id
    ).order_by(IdentityGroupSnapshot.hypothesis_key).all()
    group_ids = [group.id for group in groups]
    members = db.query(IdentityGroupMemberSnapshot).filter(
        IdentityGroupMemberSnapshot.group_snapshot_id.in_(group_ids)
    ).order_by(
        IdentityGroupMemberSnapshot.group_snapshot_id,
        IdentityGroupMemberSnapshot.member_index,
    ).all() if group_ids else []
    members_by_group = defaultdict(list)
    for member in members:
        members_by_group[member.group_snapshot_id].append(member)
    records_by_ref = {record.record_ref_key: record for record in records}
    contracts = []
    grouped = set()
    for group in groups:
        group_members = tuple(members_by_group[group.id])
        references = tuple(item.record_ref_key for item in group_members)
        if any(reference not in records_by_ref for reference in references):
            raise ValueError("G2-v1 comparison membership differs from GF-1")
        paired = tuple(sorted(
            (reference, records_by_ref[reference].record_id) for reference in references
        ))
        semantic = {
            "status": group.group_status,
            "members": tuple(reference for reference, _record_id in paired),
            "hypothesis_fingerprint": group.hypothesis_key,
            "projection_algorithm_version": group.projection_algorithm_version,
        }
        contracts.append(ComparisonIdentitySet(
            source_version=ComparisonSourceVersion.V1,
            group_reference="g2-v1-" + group.hypothesis_key,
            status=IdentityGroupHypothesisStatus(group.group_status),
            member_record_ids=tuple(record_id for _reference, record_id in paired),
            stable_member_references=tuple(reference for reference, _record_id in paired),
            member_count=len(paired),
            source_fingerprint=shadow_fingerprint("g2-v1-comparison-group", semantic),
        ))
        grouped.update(references)
    contracts = tuple(sorted(contracts, key=lambda item: item.group_reference))
    source_fingerprint = shadow_fingerprint("g2-v1-comparison-snapshot", {
        "algorithm_version": run.algorithm_version,
        "edge_classifier_version": run.edge_classifier_version,
        "evidence_fingerprint": run.evidence_fingerprint,
        "records_seen": run.records_seen,
        "groups": tuple((
            group.source_fingerprint, group.status.value,
            group.stable_member_references,
        ) for group in contracts),
    })
    return V1ComparisonSnapshot(
        scan_id=run.scan_id,
        status=run.status,
        snapshot_contract_version=1,
        canonical_record_count=len(records),
        groups=contracts,
        source_fingerprint=source_fingerprint,
        unassigned_record_references=tuple(sorted(
            record.record_ref_key for record in records
            if record.record_ref_key not in grouped
        )),
    )


def build_shadow_comparison_input(
    db, *, scan_id: int, v1_projection_run_id: int, v2_projection_run_id: int,
    configuration: ShadowComparisonConfiguration = ShadowComparisonConfiguration(),
) -> ShadowComparisonInput:
    v1_run = db.get(IdentityGroupProjectionRun, v1_projection_run_id)
    v2_run = db.get(G2V2ProjectionRun, v2_projection_run_id)
    if v1_run is None or v1_run.status != "COMPLETED":
        raise ValueError("GF-7B requires a completed G2-v1 projection run")
    if v2_run is None or v2_run.status != "COMPLETED":
        raise ValueError("GF-7B requires a completed G2-v2 projection run")
    if v1_run.scan_id != scan_id or v2_run.scan_id != scan_id:
        raise ValueError("GF-7B projection selection crosses scans")
    resolution = db.get(IdentityResolutionRun, v2_run.source_resolution_run_id)
    if resolution is None or resolution.status != "COMPLETED" or resolution.scan_id != scan_id:
        raise ValueError("GF-7B requires completed same-scan GF-5C provenance")
    records = load_scan_record_catalog(db, scan_id)
    v2_snapshot = load_persisted_g2_v2_manifest(db, v2_run.id)
    return ShadowComparisonInput(
        scan_id=scan_id,
        canonical_records=records,
        v1_snapshot=_load_v1_snapshot(db, v1_run, records),
        v2_snapshot=v2_snapshot,
        v1_projection_run_id=v1_run.id,
        v2_projection_run_id=v2_run.id,
        v2_source_resolution_run_id=resolution.id,
        v2_projection_status=v2_run.status,
        comparison_algorithm_version=SHADOW_COMPARISON_ALGORITHM_VERSION,
        comparison_configuration=configuration,
    )


def shadow_comparison_input_fingerprint(value: ShadowComparisonInput) -> str:
    """Fingerprint semantic immutable inputs, excluding timestamps and DB run IDs."""
    return shadow_fingerprint("shadow-comparison-input", {
        "algorithm": value.comparison_algorithm_version,
        "configuration": shadow_fingerprint(
            "shadow-comparison-configuration", value.comparison_configuration
        ),
        "canonical_records": tuple(sorted(
            (item.record_ref_key, item.source_record_fingerprint)
            for item in value.canonical_records
        )),
        "v1_source": value.v1_snapshot.source_fingerprint,
        "v1_groups": tuple(sorted((
            group.source_fingerprint, group.status.value,
            tuple(sorted(group.stable_member_references)),
        ) for group in value.v1_snapshot.groups)),
        "v2_manifest": value.v2_snapshot.manifest_fingerprint,
        "v2_conflicts": tuple(sorted(
            item.conflict_fingerprint for item in value.v2_snapshot.conflicts
        )),
        "v2_deferred": tuple(sorted(
            item.deferred_fingerprint for item in value.v2_snapshot.deferred_work_units
        )),
        "v2_unassigned": tuple(sorted(value.v2_snapshot.unassigned_record_references)),
    })


def _persist_result(repository, run, result, comparison_input):
    v2_conflicts = {
        item.conflict_reference: item for item in comparison_input.v2_snapshot.conflicts
    }
    v2_deferred = {
        item.deferred_reference: item
        for item in comparison_input.v2_snapshot.deferred_work_units
    }
    delta_rows = {}
    for delta in result.safety_deltas:
        related_cases = tuple(
            case for case in result.cases
            if delta.delta_fingerprint in {item.delta_fingerprint for item in case.safety_deltas}
        )
        priority = max(
            (case.adjudication_priority for case in related_cases),
            key=lambda item: _PRIORITY_RANK[item],
            default=AdjudicationPriority.NONE,
        )
        related_groups = sorted({
            reference for case in related_cases
            for reference in (*case.v1_group_references, *case.v2_group_references)
        })
        related_outcomes = sorted({
            reference for case in related_cases
            for reference in (
                *case.related_v2_conflict_references,
                *case.related_v2_deferred_references,
                *case.related_v2_unassigned_record_references,
            )
        })
        endpoints = delta.involved_record_references if len(delta.involved_record_references) == 2 else (None, None)
        row = ShadowComparisonSafetyDeltaRow(
            comparison_run_id=run.id,
            delta_type=delta.delta_type.value,
            left_record_reference=endpoints[0],
            right_record_reference=endpoints[1],
            involved_record_references_json=_json(delta.involved_record_references),
            related_group_references_json=_json(related_groups),
            related_outcome_references_json=_json(related_outcomes),
            protected_evidence_references_json=_json(delta.protected_evidence_references),
            evidence_fingerprints_json=_json(delta.protected_evidence_references),
            explanation=delta.explanation,
            adjudication_priority=priority.value,
            delta_fingerprint=delta.delta_fingerprint,
        )
        repository.add_all([row])
        delta_rows[delta.delta_fingerprint] = row

    groups_by_reference = {
        group.group_reference: group for group in comparison_input.v1_snapshot.groups
    }
    groups_by_reference.update({
        group.group_reference: group for group in comparison_input.v2_snapshot.groups
    })
    for case in result.cases:
        row = ShadowComparisonCaseRow(
            comparison_run_id=run.id,
            case_reference=case.case_reference,
            case_type=case.case_type.value,
            overlap_metrics_json=_json([asdict(item) for item in case.overlap_metrics]),
            status_transitions_json=_json([asdict(item) for item in case.status_transitions]),
            related_v2_conflict_references_json=_json(case.related_v2_conflict_references),
            related_v2_deferred_references_json=_json(case.related_v2_deferred_references),
            related_v2_outcome_context_json=_json([
                {
                    "reference": reference,
                    "kind": "CONFLICT",
                    "reason": v2_conflicts[reference].conflict_type.value,
                    "summary": v2_conflicts[reference].summary,
                    "fingerprint": v2_conflicts[reference].conflict_fingerprint,
                }
                for reference in case.related_v2_conflict_references
            ] + [
                {
                    "reference": reference,
                    "kind": "DEFERRED",
                    "reason": v2_deferred[reference].reason.value,
                    "summary": v2_deferred[reference].unfinished_evidence_summary,
                    "fingerprint": v2_deferred[reference].deferred_fingerprint,
                }
                for reference in case.related_v2_deferred_references
            ]),
            adjudication_priority=case.adjudication_priority.value,
            adjudication_reasons_json=_json(case.adjudication_reasons),
            case_fingerprint=case.case_fingerprint,
        )
        repository.add_all([row])
        relations = []
        for source, references in (
            (ComparisonSourceVersion.V1, case.v1_group_references),
            (ComparisonSourceVersion.V2, case.v2_group_references),
        ):
            for reference in references:
                source_group = groups_by_reference[reference]
                member_refs = (
                    source_group.stable_member_references
                    if source == ComparisonSourceVersion.V1
                    else tuple(member.stable_record_reference for member in source_group.members)
                )
                relations.append(ShadowComparisonCaseGroupRow(
                    comparison_run_id=run.id,
                    case_id=row.id,
                    source_version=source.value,
                    group_reference=reference,
                    source_status=source_group.status.value,
                    source_fingerprint=(
                        source_group.source_fingerprint
                        if source == ComparisonSourceVersion.V1
                        else source_group.group_fingerprint
                    ),
                    member_references_json=_json(tuple(sorted(member_refs))),
                ))
        repository.add_all(relations)
        involved = set(case.involved_record_references)
        repository.add_all([ShadowComparisonCaseRecordRow(
            comparison_run_id=run.id,
            case_id=row.id,
            record_reference=reference,
            involved=True,
            in_v1_membership=reference in set(case.v1_member_references),
            in_v2_membership=reference in set(case.v2_member_references),
            v2_unassigned_context=reference in set(case.related_v2_unassigned_record_references),
        ) for reference in sorted(involved)])
        repository.add_all([ShadowComparisonCaseDeltaRow(
            comparison_run_id=run.id,
            case_id=row.id,
            safety_delta_id=delta_rows[delta.delta_fingerprint].id,
        ) for delta in case.safety_deltas])


def load_persisted_shadow_comparison(db, comparison_run_id: int) -> ShadowComparisonResult:
    run = db.get(ShadowComparisonRun, comparison_run_id)
    if run is None or run.status != "COMPLETED":
        raise ValueError("completed shadow comparison run not found")
    cases, groups, records, deltas, links = ShadowComparisonRepository(db).result_rows(run.id)
    groups_by_case, records_by_case, links_by_case = defaultdict(list), defaultdict(list), defaultdict(list)
    for item in groups: groups_by_case[item.case_id].append(item)
    for item in records: records_by_case[item.case_id].append(item)
    deltas_by_id = {}
    for item in deltas:
        protected_references = tuple(json.loads(item.protected_evidence_references_json))
        evidence_fingerprints = tuple(json.loads(item.evidence_fingerprints_json))
        if not set(protected_references) <= set(evidence_fingerprints):
            raise ValueError("shadow safety-delta evidence provenance is incomplete")
        if (item.left_record_reference is None) != (item.right_record_reference is None):
            raise ValueError("shadow safety-delta endpoints are incomplete")
        AdjudicationPriority(item.adjudication_priority)
        deltas_by_id[item.id] = ShadowSafetyDelta(
            delta_type=ShadowSafetyDeltaType(item.delta_type),
            involved_record_references=tuple(json.loads(item.involved_record_references_json)),
            protected_evidence_references=protected_references,
            explanation=item.explanation,
            delta_fingerprint=item.delta_fingerprint,
        )
    for item in links: links_by_case[item.case_id].append(item.safety_delta_id)
    case_contracts = []
    for row in cases:
        case_groups = groups_by_case[row.id]
        case_records = records_by_case[row.id]
        group_members = {}
        group_statuses = {}
        for item in case_groups:
            ComparisonSourceVersion(item.source_version)
            IdentityGroupHypothesisStatus(item.source_status)
            if len(item.source_fingerprint) != 64:
                raise ValueError("shadow case group lacks a source fingerprint")
            member_references = tuple(json.loads(item.member_references_json))
            if (
                len(member_references) < 2
                or member_references != tuple(sorted(set(member_references)))
            ):
                raise ValueError("shadow case group membership is not canonical")
            group_members[(item.source_version, item.group_reference)] = set(member_references)
            group_statuses[(item.source_version, item.group_reference)] = item.source_status
        v1_record_members = {
            item.record_reference for item in case_records if item.in_v1_membership
        }
        v2_record_members = {
            item.record_reference for item in case_records if item.in_v2_membership
        }
        v1_group_members = set().union(*(
            members for (source, _reference), members in group_members.items()
            if source == "V1"
        )) if any(source == "V1" for source, _reference in group_members) else set()
        v2_group_members = set().union(*(
            members for (source, _reference), members in group_members.items()
            if source == "V2"
        )) if any(source == "V2" for source, _reference in group_members) else set()
        if v1_record_members != v1_group_members or v2_record_members != v2_group_members:
            raise ValueError("shadow case group and record memberships differ")
        overlap = []
        for item in json.loads(row.overlap_metrics_json):
            overlap.append(GroupOverlapMetrics(**item))
        transitions = []
        for item in json.loads(row.status_transitions_json):
            if (
                group_statuses.get(("V1", item["v1_group_reference"])) != item["v1_status"]
                or group_statuses.get(("V2", item["v2_group_reference"])) != item["v2_status"]
            ):
                raise ValueError("shadow status transition differs from source groups")
            item["v1_status"] = IdentityGroupHypothesisStatus(item["v1_status"])
            item["v2_status"] = IdentityGroupHypothesisStatus(item["v2_status"])
            transitions.append(StatusTransition(**item))
        case_contracts.append(ShadowComparisonCase(
            case_reference=row.case_reference,
            case_type=ShadowComparisonCaseType(row.case_type),
            v1_group_references=tuple(sorted(
                item.group_reference for item in case_groups if item.source_version == "V1"
            )),
            v2_group_references=tuple(sorted(
                item.group_reference for item in case_groups if item.source_version == "V2"
            )),
            involved_record_references=tuple(
                item.record_reference for item in case_records if item.involved
            ),
            v1_member_references=tuple(
                item.record_reference for item in case_records if item.in_v1_membership
            ),
            v2_member_references=tuple(
                item.record_reference for item in case_records if item.in_v2_membership
            ),
            overlap_metrics=tuple(overlap),
            status_transitions=tuple(transitions),
            related_v2_conflict_references=tuple(json.loads(row.related_v2_conflict_references_json)),
            related_v2_deferred_references=tuple(json.loads(row.related_v2_deferred_references_json)),
            related_v2_unassigned_record_references=tuple(
                item.record_reference for item in case_records if item.v2_unassigned_context
            ),
            safety_deltas=tuple(sorted(
                (deltas_by_id[item] for item in links_by_case[row.id]),
                key=lambda item: (item.delta_type.value, item.delta_fingerprint),
            )),
            adjudication_priority=AdjudicationPriority(row.adjudication_priority),
            adjudication_reasons=tuple(json.loads(row.adjudication_reasons_json)),
            case_fingerprint=row.case_fingerprint,
        ))
    case_contracts = tuple(sorted(
        case_contracts, key=lambda item: (item.case_type.value, item.case_fingerprint)
    ))
    summary_values = {name: getattr(run, name) for name in _SUMMARY_FIELDS}
    summary = ShadowComparisonSummary(
        scan_id=run.scan_id,
        v1_projection_run_id=run.v1_projection_run_id,
        v2_projection_run_id=run.v2_projection_run_id,
        v2_source_resolution_run_id=run.v2_source_resolution_run_id,
        **summary_values,
        comparison_fingerprint=run.comparison_fingerprint,
    )
    delta_contracts = tuple(sorted(
        deltas_by_id.values(), key=lambda item: (item.delta_type.value, item.delta_fingerprint)
    ))
    return ShadowComparisonResult(
        summary=summary,
        cases=case_contracts,
        safety_deltas=delta_contracts,
        comparison_algorithm_version=run.comparison_algorithm_version,
        configuration_fingerprint=run.configuration_fingerprint,
        comparison_fingerprint=run.comparison_fingerprint,
    )


def build_and_persist_shadow_comparison(
    db, *, scan_id: int, v1_projection_run_id: int, v2_projection_run_id: int,
    configuration: ShadowComparisonConfiguration = ShadowComparisonConfiguration(),
) -> ShadowComparisonPersistenceSummary:
    comparison_input = build_shadow_comparison_input(
        db,
        scan_id=scan_id,
        v1_projection_run_id=v1_projection_run_id,
        v2_projection_run_id=v2_projection_run_id,
        configuration=configuration,
    )
    configuration_fingerprint = shadow_fingerprint(
        "shadow-comparison-configuration", configuration
    )
    input_fingerprint = shadow_comparison_input_fingerprint(comparison_input)
    identity = dict(
        scan_id=scan_id,
        v1_projection_run_id=v1_projection_run_id,
        v2_projection_run_id=v2_projection_run_id,
        comparison_algorithm_version=comparison_input.comparison_algorithm_version,
        configuration_fingerprint=configuration_fingerprint,
        input_fingerprint=input_fingerprint,
    )
    repository = ShadowComparisonRepository(db)
    existing = repository.run_for_identity(**identity)
    if existing is not None:
        result = load_persisted_shadow_comparison(db, existing.id) if existing.status == "COMPLETED" else None
        if result is not None:
            pure = compare_g2_v1_v2(comparison_input)
            if result != pure or result.comparison_fingerprint != existing.comparison_fingerprint:
                raise ValueError("completed shadow comparison differs from pure GF-7A output")
        return ShadowComparisonPersistenceSummary(
            existing.id, existing.status, True, input_fingerprint,
            existing.comparison_fingerprint, result, existing.safe_failure_category,
        )
    run = repository.add_run(
        **identity,
        v2_source_resolution_run_id=comparison_input.v2_source_resolution_run_id,
        status="RUNNING",
    )
    db.commit()
    run_id = run.id
    try:
        pure = compare_g2_v1_v2(comparison_input)
        run = db.get(ShadowComparisonRun, run_id)
        _persist_result(repository, run, pure, comparison_input)
        for name in _SUMMARY_FIELDS:
            setattr(run, name, getattr(pure.summary, name))
        run.critical_safety_delta_count = sum(
            delta.delta_type in {
                ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT,
                ShadowSafetyDeltaType.V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK,
            }
            for delta in pure.safety_deltas
        )
        run.comparison_fingerprint = pure.comparison_fingerprint
        run.status = "COMPLETED"
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        loaded = load_persisted_shadow_comparison(db, run_id)
        if loaded != pure:
            raise ValueError("persisted shadow comparison differs from pure GF-7A output")
        db.commit()
        return ShadowComparisonPersistenceSummary(
            run_id, "COMPLETED", False, input_fingerprint,
            pure.comparison_fingerprint, loaded,
        )
    except Exception as error:
        db.rollback()
        run = db.get(ShadowComparisonRun, run_id)
        if run is not None and run.status == "RUNNING":
            run.status = "FAILED"
            run.completed_at = datetime.now(timezone.utc)
            run.safe_failure_category = _safe_failure(error)
            db.commit()
        return ShadowComparisonPersistenceSummary(
            run_id, "FAILED", False, input_fingerprint, None, None,
            _safe_failure(error),
        )
