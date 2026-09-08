"""Pure structural adapters from G2-v1/v2 snapshots to neutral read snapshots."""

from __future__ import annotations

from dataclasses import replace

from app.identity_read.contracts import (
    G2V1ReadSourceSnapshot,
    IdentityReadConflict,
    IdentityReadDeferredWork,
    IdentityReadGroup,
    IdentityReadGroupMember,
    IdentityReadGroupStatus,
    IdentityReadProjectionContract,
    IdentityReadSnapshot,
    IdentityReadSourceRecord,
    IdentityReadSummary,
    IdentityReadUnassignedRecord,
    IdentityReadValidationCoverage,
    IdentityReadValidationMode,
    VersionedIdentityGroupKey,
)
from app.identity_read.fingerprints import identity_read_fingerprint
from app.identity_read.semantics import (
    conflict_semantic_payload,
    deferred_semantic_payload,
    group_semantic_payload,
)
from app.identity_read.validation import validate_identity_read_snapshot


def _value(value):
    return value.value if hasattr(value, "value") else value


def _records(scan_id, records):
    by_id = {}
    by_reference = {}
    for record in records:
        if record.scan_id != scan_id:
            raise ValueError("identity read source record crosses scans")
        reference = getattr(record, "stable_record_reference", None) or getattr(
            record, "record_ref_key", None
        )
        if not reference:
            raise ValueError("identity read source record lacks stable reference")
        if record.record_id in by_id or reference in by_reference:
            raise ValueError("identity read source records contain duplicate identity")
        by_id[record.record_id] = record
        by_reference[reference] = record
    return by_id, by_reference


def _member(record, reference, order):
    return IdentityReadGroupMember(
        record_id=record.record_id,
        stable_record_reference=reference,
        source_row_index=record.source_row_index,
        member_order=order,
        part_no=record.part_no,
        description=record.description,
        normalized_part_no=getattr(record, "normalized_part_no", ""),
        normalized_description=getattr(record, "normalized_description", ""),
        contract=getattr(record, "contract", None),
        uom=getattr(record, "uom", None),
        type_code=getattr(record, "type_code", None),
        prime_commodity=getattr(record, "prime_commodity", None),
        second_commodity=getattr(record, "second_commodity", None),
        accounting_group=getattr(record, "accounting_group", None),
        part_product_code=getattr(record, "part_product_code", None),
        part_product_family=getattr(record, "part_product_family", None),
        product_category_id=getattr(record, "product_category_id", None),
        hsn_sac_code=getattr(record, "hsn_sac_code", None),
        hazard_code=getattr(record, "hazard_code", None),
    )


def _finish(
    *, scan_id, projection_contract, source_projection_run_id,
    source_orchestration_run_id, source_resolution_run_id, groups, conflicts,
    deferred, unassigned, canonical_record_count, source_snapshot_fingerprint,
):
    groups = tuple(sorted(groups, key=lambda item: item.versioned_group_key.group_reference))
    conflicts = tuple(sorted(conflicts, key=lambda item: item.conflict_reference))
    deferred = tuple(sorted(deferred, key=lambda item: item.deferred_reference))
    unassigned = tuple(sorted(unassigned, key=lambda item: item.stable_record_reference))
    summary = IdentityReadSummary(
        canonical_record_count=canonical_record_count,
        group_count=len(groups),
        likely_group_count=sum(
            item.status == IdentityReadGroupStatus.LIKELY_DUPLICATE_GROUP for item in groups
        ),
        review_group_count=sum(
            item.status == IdentityReadGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
            for item in groups
        ),
        conflict_count=len(conflicts),
        deferred_count=len(deferred),
        unassigned_count=len(unassigned),
    )
    semantic = {
        "scan_id": scan_id,
        "projection_contract": projection_contract,
        "groups": tuple(group_semantic_payload(item) for item in groups),
        "conflicts": tuple(conflict_semantic_payload(item) for item in conflicts),
        "deferred": tuple(deferred_semantic_payload(item) for item in deferred),
        "unassigned": tuple(
            (item.stable_record_reference, item.source_row_index) for item in unassigned
        ),
        "summary": summary,
        "source_snapshot_fingerprint": source_snapshot_fingerprint,
    }
    snapshot = IdentityReadSnapshot(
        scan_id=scan_id,
        projection_contract=projection_contract,
        source_projection_run_id=source_projection_run_id,
        source_orchestration_run_id=source_orchestration_run_id,
        source_resolution_run_id=source_resolution_run_id,
        groups=groups,
        conflicts=conflicts,
        deferred_work_units=deferred,
        unassigned_records=unassigned,
        canonical_record_count=summary.canonical_record_count,
        group_count=summary.group_count,
        likely_group_count=summary.likely_group_count,
        review_group_count=summary.review_group_count,
        conflict_count=summary.conflict_count,
        deferred_count=summary.deferred_count,
        unassigned_count=summary.unassigned_count,
        summary=summary,
        source_snapshot_fingerprint=source_snapshot_fingerprint,
        snapshot_fingerprint=identity_read_fingerprint("identity-read-snapshot", semantic),
    )
    validate_identity_read_snapshot(snapshot)
    return snapshot


def adapt_g2_v1_to_identity_read_snapshot(
    source: G2V1ReadSourceSnapshot,
    canonical_records: tuple[IdentityReadSourceRecord, ...],
    *,
    source_orchestration_run_id: int | None = None,
) -> IdentityReadSnapshot:
    """Preserve historical v1 membership with explicit legacy pair completeness."""
    if source.status != "COMPLETED":
        raise ValueError("G2-v1 source projection is not completed")
    by_id, by_reference = _records(source.scan_id, canonical_records)
    if source.canonical_record_count != len(canonical_records):
        raise ValueError("G2-v1 canonical record count drift")
    groups = []
    grouped = set()
    for item in source.groups:
        if item.scan_id != source.scan_id:
            raise ValueError("G2-v1 group crosses scans")
        status = IdentityReadGroupStatus(_value(item.status))
        members = []
        orders = set()
        for source_member in item.members:
            if source_member.member_order in orders:
                raise ValueError("G2-v1 group has duplicate member order")
            orders.add(source_member.member_order)
            record = by_id.get(source_member.record_id)
            if record is None or by_reference.get(source_member.stable_record_reference) is not record:
                raise ValueError("G2-v1 member differs from canonical record identity")
            if record.record_id in grouped:
                raise ValueError("G2-v1 accepted membership overlaps")
            grouped.add(record.record_id)
            members.append(_member(record, source_member.stable_record_reference, source_member.member_order))
        members = tuple(sorted(members, key=lambda member: member.member_order))
        possible = len(members) * (len(members) - 1) // 2
        coverage = IdentityReadValidationCoverage(
            validation_mode=IdentityReadValidationMode.LEGACY_COMPLETE_PAIRWISE,
            member_count=len(members),
            possible_internal_pair_count=possible,
            evaluated_internal_pair_count=possible,
            required_validation_evidence_count=possible,
            strong_support_count=0,
            review_support_count=0,
            non_groupable_count=0,
            cannot_link_count=0,
            missing_nonrequired_pair_count=0,
            targeted_evidence_count=0,
            proposal_evidence_count=0,
        )
        group = IdentityReadGroup(
            versioned_group_key=VersionedIdentityGroupKey(
                source.scan_id, IdentityReadProjectionContract.G2_V1, item.group_reference
            ),
            status=status,
            member_count=len(members),
            members=members,
            validation_mode=IdentityReadValidationMode.LEGACY_COMPLETE_PAIRWISE,
            validation_coverage=coverage,
            group_evidence_summary=None,
            bridge_risk_summary=None,
            genericity_risk_summary=None,
            missing_evidence_summary=None,
            internal_evidence=(),
            source_group_fingerprint=item.source_group_fingerprint,
            read_group_fingerprint="",
        )
        groups.append(replace(group, read_group_fingerprint=identity_read_fingerprint(
            "identity-read-group", group_semantic_payload(group)
        )))
    unassigned = tuple(
        IdentityReadUnassignedRecord(
            record.record_id,
            getattr(record, "stable_record_reference", None) or getattr(record, "record_ref_key"),
            record.source_row_index,
        )
        for record in canonical_records if record.record_id not in grouped
    )
    return _finish(
        scan_id=source.scan_id,
        projection_contract=IdentityReadProjectionContract.G2_V1,
        source_projection_run_id=source.source_projection_run_id,
        source_orchestration_run_id=source_orchestration_run_id,
        source_resolution_run_id=None,
        groups=groups,
        conflicts=(), deferred=(), unassigned=unassigned,
        canonical_record_count=source.canonical_record_count,
        source_snapshot_fingerprint=source.source_snapshot_fingerprint,
    )


def adapt_g2_v2_to_identity_read_snapshot(
    source,
    canonical_records: tuple[IdentityReadSourceRecord, ...],
    *,
    source_projection_run_id: int,
    source_orchestration_run_id: int,
) -> IdentityReadSnapshot:
    """Preserve the full typed G2-v2 result without progressive down-conversion."""
    by_id, by_reference = _records(source.scan_id, canonical_records)
    if source.canonical_record_count != len(canonical_records):
        raise ValueError("G2-v2 canonical record count drift")
    groups = []
    grouped = set()
    for item in source.groups:
        if item.scan_id != source.scan_id:
            raise ValueError("G2-v2 group crosses scans")
        members = []
        orders = set()
        for source_member in item.members:
            if source_member.member_order in orders:
                raise ValueError("G2-v2 group has duplicate member order")
            orders.add(source_member.member_order)
            record = by_id.get(source_member.record_id)
            if record is None or by_reference.get(source_member.stable_record_reference) is not record:
                raise ValueError("G2-v2 member differs from canonical record identity")
            if record.record_id in grouped:
                raise ValueError("G2-v2 accepted membership overlaps")
            grouped.add(record.record_id)
            members.append(_member(record, source_member.stable_record_reference, source_member.member_order))
        members = tuple(sorted(members, key=lambda member: member.member_order))
        coverage_source = item.validation_coverage
        mode = IdentityReadValidationMode(_value(item.validation_mode))
        coverage = IdentityReadValidationCoverage(
            validation_mode=IdentityReadValidationMode(_value(coverage_source.validation_mode)),
            member_count=coverage_source.member_count,
            possible_internal_pair_count=coverage_source.possible_internal_pair_count,
            evaluated_internal_pair_count=coverage_source.evaluated_internal_pair_count,
            required_validation_evidence_count=coverage_source.required_validation_evidence_count,
            strong_support_count=coverage_source.strong_support_count,
            review_support_count=coverage_source.review_support_count,
            non_groupable_count=coverage_source.non_groupable_count,
            cannot_link_count=coverage_source.cannot_link_count,
            missing_nonrequired_pair_count=coverage_source.missing_nonrequired_pair_count,
            targeted_evidence_count=coverage_source.targeted_evidence_count,
            proposal_evidence_count=coverage_source.proposal_evidence_count,
        )
        internal_evidence = tuple(sorted(
            item.internal_evidence,
            key=lambda evidence: (
                evidence.stable_record_reference_1,
                evidence.stable_record_reference_2,
                evidence.evidence_fingerprint,
            ),
        ))
        group = IdentityReadGroup(
            versioned_group_key=VersionedIdentityGroupKey(
                source.scan_id, IdentityReadProjectionContract.G2_V2, item.group_reference
            ),
            status=IdentityReadGroupStatus(_value(item.status)),
            member_count=item.member_count,
            members=members,
            validation_mode=mode,
            validation_coverage=coverage,
            group_evidence_summary=item.group_evidence_summary,
            bridge_risk_summary=item.bridge_risk_summary,
            genericity_risk_summary=item.genericity_risk_summary,
            missing_evidence_summary=item.missing_evidence_summary,
            internal_evidence=internal_evidence,
            source_group_fingerprint=item.group_fingerprint,
            read_group_fingerprint="",
        )
        groups.append(replace(group, read_group_fingerprint=identity_read_fingerprint(
            "identity-read-group", group_semantic_payload(group)
        )))
    conflicts = []
    for item in source.conflicts:
        if item.scan_id != source.scan_id:
            raise ValueError("G2-v2 conflict crosses scans")
        if any(record_id not in by_id for record_id in item.involved_record_ids):
            raise ValueError("G2-v2 conflict references an unknown record")
        if any(reference not in by_reference for reference in item.involved_record_references):
            raise ValueError("G2-v2 conflict references an unknown stable identity")
        conflict = IdentityReadConflict(
            scan_id=item.scan_id,
            conflict_reference=item.conflict_reference,
            conflict_type=_value(item.conflict_type),
            involved_record_ids=tuple(sorted(item.involved_record_ids)),
            involved_record_references=tuple(sorted(item.involved_record_references)),
            protected_evidence_references=tuple(sorted(item.protected_evidence_references)),
            source_neighborhood_references=tuple(sorted(item.source_neighborhood_references)),
            summary=item.summary,
            source_conflict_fingerprint=item.conflict_fingerprint,
            read_conflict_fingerprint="",
        )
        conflicts.append(replace(conflict, read_conflict_fingerprint=identity_read_fingerprint(
            "identity-read-conflict", conflict_semantic_payload(conflict)
        )))
    deferred = []
    for item in source.deferred_work_units:
        if item.scan_id != source.scan_id:
            raise ValueError("G2-v2 deferred work crosses scans")
        if any(record_id not in by_id for record_id in item.record_ids):
            raise ValueError("G2-v2 deferred work references an unknown record")
        if any(reference not in by_reference for reference in item.record_references):
            raise ValueError("G2-v2 deferred work references an unknown stable identity")
        work = IdentityReadDeferredWork(
            scan_id=item.scan_id,
            deferred_reference=item.deferred_reference,
            reason=_value(item.reason),
            record_ids=tuple(sorted(item.record_ids)),
            record_references=tuple(sorted(item.record_references)),
            unfinished_evidence_summary=item.unfinished_evidence_summary,
            source_neighborhood_references=tuple(sorted(item.source_neighborhood_references)),
            source_deferred_fingerprint=item.deferred_fingerprint,
            read_deferred_fingerprint="",
        )
        deferred.append(replace(work, read_deferred_fingerprint=identity_read_fingerprint(
            "identity-read-deferred", deferred_semantic_payload(work)
        )))
    unassigned = []
    for record_id, reference in zip(
        source.unassigned_record_ids, source.unassigned_record_references, strict=True
    ):
        record = by_id.get(record_id)
        if record is None or by_reference.get(reference) is not record:
            raise ValueError("G2-v2 unassigned identity differs from canonical record")
        unassigned.append(IdentityReadUnassignedRecord(
            record_id, reference, record.source_row_index
        ))
    expected_counts = (
        len(source.groups),
        sum(_value(item.status) == "LIKELY_DUPLICATE_GROUP" for item in source.groups),
        sum(_value(item.status) == "POSSIBLE_DUPLICATE_GROUP_REVIEW" for item in source.groups),
        len(source.conflicts), len(source.deferred_work_units), len(unassigned),
    )
    declared_counts = (
        source.accepted_group_count, source.likely_group_count, source.review_group_count,
        source.conflict_count, source.deferred_count, source.unassigned_record_count,
    )
    if declared_counts != expected_counts:
        raise ValueError("G2-v2 manifest count drift")
    return _finish(
        scan_id=source.scan_id,
        projection_contract=IdentityReadProjectionContract.G2_V2,
        source_projection_run_id=source_projection_run_id,
        source_orchestration_run_id=source_orchestration_run_id,
        source_resolution_run_id=source.source_resolution_run_id,
        groups=groups, conflicts=conflicts, deferred=deferred, unassigned=unassigned,
        canonical_record_count=source.canonical_record_count,
        source_snapshot_fingerprint=source.manifest_fingerprint,
    )
