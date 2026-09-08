"""Pure invariants and semantic-fingerprint validation for GF-9A snapshots."""

from __future__ import annotations

from app.identity_read.contracts import (
    IdentityReadGroupStatus,
    IdentityReadProjectionContract,
    IdentityReadSummary,
    IdentityReadValidationMode,
)
from app.identity_read.fingerprints import identity_read_fingerprint
from app.identity_read.semantics import (
    conflict_semantic_payload,
    deferred_semantic_payload,
    group_semantic_payload,
)


class IdentityReadValidationError(ValueError):
    pass


def validate_identity_read_snapshot(snapshot) -> None:
    if not isinstance(snapshot.projection_contract, IdentityReadProjectionContract):
        raise IdentityReadValidationError("invalid read projection contract")
    if snapshot.scan_id <= 0 or snapshot.source_projection_run_id <= 0:
        raise IdentityReadValidationError("invalid read snapshot source identity")
    if snapshot.projection_contract == IdentityReadProjectionContract.G2_V1:
        if snapshot.source_resolution_run_id is not None:
            raise IdentityReadValidationError("G2-v1 cannot claim resolution provenance")
        if snapshot.conflicts or snapshot.deferred_work_units:
            raise IdentityReadValidationError("G2-v1 cannot invent G2-v2 outcomes")
    elif snapshot.source_orchestration_run_id is None or snapshot.source_resolution_run_id is None:
        raise IdentityReadValidationError("G2-v2 requires orchestration and resolution provenance")
    keys = set()
    accepted_records = set()
    accepted_references = set()
    for group in snapshot.groups:
        key = group.versioned_group_key
        if key in keys:
            raise IdentityReadValidationError("duplicate versioned identity group key")
        keys.add(key)
        if key.scan_id != snapshot.scan_id or key.projection_contract != snapshot.projection_contract:
            raise IdentityReadValidationError("identity read group crosses snapshot authority")
        if not isinstance(group.status, IdentityReadGroupStatus):
            raise IdentityReadValidationError("invalid identity read group status")
        if group.member_count != len(group.members) or group.member_count < 2:
            raise IdentityReadValidationError("identity read group member count drift")
        orders = [member.member_order for member in group.members]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            raise IdentityReadValidationError("invalid identity read member order")
        for member in group.members:
            if member.record_id in accepted_records or member.stable_record_reference in accepted_references:
                raise IdentityReadValidationError("duplicate accepted membership")
            accepted_records.add(member.record_id)
            accepted_references.add(member.stable_record_reference)
        coverage = group.validation_coverage
        if coverage is None or coverage.validation_mode != group.validation_mode:
            raise IdentityReadValidationError("identity read validation coverage drift")
        possible = group.member_count * (group.member_count - 1) // 2
        if coverage.member_count != group.member_count or coverage.possible_internal_pair_count != possible:
            raise IdentityReadValidationError("identity read possible-pair count drift")
        if not 0 <= coverage.evaluated_internal_pair_count <= possible:
            raise IdentityReadValidationError("identity read evaluated-pair count drift")
        if coverage.evaluated_internal_pair_count + coverage.missing_nonrequired_pair_count != possible:
            raise IdentityReadValidationError("identity read missing-pair count drift")
        if snapshot.projection_contract == IdentityReadProjectionContract.G2_V1:
            if group.validation_mode != IdentityReadValidationMode.LEGACY_COMPLETE_PAIRWISE:
                raise IdentityReadValidationError("G2-v1 cannot claim v2 validation semantics")
            if group.internal_evidence or any((
                group.group_evidence_summary, group.bridge_risk_summary,
                group.genericity_risk_summary, group.missing_evidence_summary,
            )):
                raise IdentityReadValidationError("G2-v1 cannot invent G2-v2 provenance")
        else:
            if group.validation_mode == IdentityReadValidationMode.LEGACY_COMPLETE_PAIRWISE:
                raise IdentityReadValidationError("G2-v2 cannot use legacy validation semantics")
            if group.validation_mode == IdentityReadValidationMode.PROGRESSIVE_TARGETED:
                if coverage.missing_nonrequired_pair_count <= 0:
                    raise IdentityReadValidationError("G2-v2 progressive validation was lost")
            if len(group.internal_evidence) != coverage.evaluated_internal_pair_count:
                raise IdentityReadValidationError("G2-v2 evidence coverage drift")
            if any(summary is None for summary in (
                group.group_evidence_summary, group.bridge_risk_summary,
                group.genericity_risk_summary, group.missing_evidence_summary,
            )):
                raise IdentityReadValidationError("G2-v2 summary provenance was lost")
        expected_group_fingerprint = identity_read_fingerprint(
            "identity-read-group", group_semantic_payload(group)
        )
        if group.read_group_fingerprint != expected_group_fingerprint:
            raise IdentityReadValidationError("identity read group fingerprint mismatch")

    for conflict in snapshot.conflicts:
        if conflict.scan_id != snapshot.scan_id:
            raise IdentityReadValidationError("identity read conflict crosses scans")
        payload = conflict_semantic_payload(conflict)
        if conflict.read_conflict_fingerprint != identity_read_fingerprint(
            "identity-read-conflict", payload
        ):
            raise IdentityReadValidationError("identity read conflict fingerprint mismatch")
    for work in snapshot.deferred_work_units:
        if work.scan_id != snapshot.scan_id:
            raise IdentityReadValidationError("identity read deferred work crosses scans")
        payload = deferred_semantic_payload(work)
        if work.read_deferred_fingerprint != identity_read_fingerprint(
            "identity-read-deferred", payload
        ):
            raise IdentityReadValidationError("identity read deferred fingerprint mismatch")
    unassigned_ids = {item.record_id for item in snapshot.unassigned_records}
    unassigned_refs = {item.stable_record_reference for item in snapshot.unassigned_records}
    if len(unassigned_ids) != len(snapshot.unassigned_records) or len(unassigned_refs) != len(snapshot.unassigned_records):
        raise IdentityReadValidationError("duplicate unassigned identity")
    if accepted_records & unassigned_ids or accepted_references & unassigned_refs:
        raise IdentityReadValidationError("accepted and unassigned identity overlap")
    summary = IdentityReadSummary(
        canonical_record_count=snapshot.canonical_record_count,
        group_count=len(snapshot.groups),
        likely_group_count=sum(
            group.status == IdentityReadGroupStatus.LIKELY_DUPLICATE_GROUP
            for group in snapshot.groups
        ),
        review_group_count=sum(
            group.status == IdentityReadGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
            for group in snapshot.groups
        ),
        conflict_count=len(snapshot.conflicts),
        deferred_count=len(snapshot.deferred_work_units),
        unassigned_count=len(snapshot.unassigned_records),
    )
    if snapshot.summary != summary or any((
        snapshot.group_count != summary.group_count,
        snapshot.likely_group_count != summary.likely_group_count,
        snapshot.review_group_count != summary.review_group_count,
        snapshot.conflict_count != summary.conflict_count,
        snapshot.deferred_count != summary.deferred_count,
        snapshot.unassigned_count != summary.unassigned_count,
    )):
        raise IdentityReadValidationError("identity read summary count drift")
    if len(accepted_records) + len(unassigned_ids) > snapshot.canonical_record_count:
        raise IdentityReadValidationError("identity read canonical record count drift")
    semantic = {
        "scan_id": snapshot.scan_id,
        "projection_contract": snapshot.projection_contract,
        "groups": tuple(group_semantic_payload(item) for item in snapshot.groups),
        "conflicts": tuple(conflict_semantic_payload(item) for item in snapshot.conflicts),
        "deferred": tuple(deferred_semantic_payload(item) for item in snapshot.deferred_work_units),
        "unassigned": tuple(
            (item.stable_record_reference, item.source_row_index)
            for item in snapshot.unassigned_records
        ),
        "summary": snapshot.summary,
        "source_snapshot_fingerprint": snapshot.source_snapshot_fingerprint,
    }
    if snapshot.snapshot_fingerprint != identity_read_fingerprint(
        "identity-read-snapshot", semantic
    ):
        raise IdentityReadValidationError("identity read snapshot fingerprint mismatch")
