"""Deterministic CSV exports over immutable G2 identity snapshots only."""

import csv
import io
import json
from datetime import timezone

from sqlalchemy import case

from app.db.models import (
    IdentityFamilyDiagnosticMemberSnapshot,
    IdentityFamilyDiagnosticSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
    ScanOrchestrationRun,
)
from app.services.export_service import sanitize_csv_cell
from app.services.identity_group_query_service import (
    IdentityGroupQueryService,
    InvalidSnapshotSelectionError,
    SnapshotNotFoundError,
)


IDENTITY_GROUP_EXPORT_FIELDS = [
    "group_snapshot_id", "group_hypothesis_key", "duplicate_group_status",
    "duplicate_group_status_label", "duplicate_group_size", "group_member_index",
    "projection_run_id", "projection_algorithm_version", "projection_created_at",
    "record_ref_key", "site_or_contract", "part_no", "description", "uom",
    "product_category", "hsn_sac", "supporting_edge_count", "review_edge_count",
    "non_groupable_internal_count", "internal_pair_count", "internal_pairs_reused",
    "internal_pairs_rescored", "evidence_completeness", "group_reason_codes",
    "distinct_uoms", "same_uom_pair_count", "convertible_uom_pair_count",
    "different_basis_pair_count", "missing_or_wildcard_pair_count",
    "malformed_or_unknown_pair_count", "possible_mapping_error_count",
]

IDENTITY_DIAGNOSTIC_EXPORT_FIELDS = [
    "diagnostic_snapshot_id", "diagnostic_key", "diagnostic_status",
    "diagnostic_status_label", "diagnostic_member_count", "diagnostic_member_index",
    "reason_codes", "cannot_link_count", "projection_run_id",
    "projection_algorithm_version", "projection_created_at", "record_ref_key",
    "site_or_contract", "part_no", "description", "uom", "product_category", "hsn_sac",
]

_GROUP_LABELS = {
    "LIKELY_DUPLICATE_GROUP": "Likely duplicate group",
    "POSSIBLE_DUPLICATE_GROUP_REVIEW": "Possible duplicate group — review",
}

_DIAGNOSTIC_LABELS = {
    "CONFLICTING_FAMILY": "Conflicting candidate family",
    "DEFERRED_OVERSIZED_FAMILY": "Deferred oversized candidate family",
    "DEFERRED_AMBIGUOUS_RECORD_FAMILY": "Deferred ambiguous-record family",
}


def _json_array(value):
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        parsed = []
    return json.dumps(parsed if isinstance(parsed, list) else [], ensure_ascii=True, separators=(",", ":"))


def _utc_timestamp(value):
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _csv(fields, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: sanitize_csv_cell(row.get(field)) for field in fields})
    return output.getvalue()


def identity_groups_to_csv(db, scan_id: int, projection_run_id: int | None = None) -> str:
    """Export one adjacent row per accepted-group member in canonical snapshot order."""
    selection = db.query(
        IdentityGroupProjectionRun, ScanOrchestrationRun.mode
    ).outerjoin(
        ScanOrchestrationRun, ScanOrchestrationRun.scan_id == IdentityGroupProjectionRun.scan_id
    ).filter(
        IdentityGroupProjectionRun.scan_id == scan_id
    )
    if projection_run_id is not None:
        selected = selection.filter(IdentityGroupProjectionRun.id == projection_run_id).one_or_none()
        if selected is None:
            raise SnapshotNotFoundError("Identity projection snapshot not found for scan")
        run, orchestration_mode = selected
        if run.status != "COMPLETED":
            raise InvalidSnapshotSelectionError(
                "Selected projection run is not a completed data snapshot"
            )
    else:
        selected = selection.filter(
            IdentityGroupProjectionRun.status == "COMPLETED"
        ).order_by(
            IdentityGroupProjectionRun.created_at.desc(),
            IdentityGroupProjectionRun.id.desc(),
        ).first()
        run, orchestration_mode = selected if selected is not None else (None, None)
    if orchestration_mode == "group_first_primary":
        raise InvalidSnapshotSelectionError(
            "Authoritative group-first System Group Export is pending GF-9C"
        )
    if run is None:
        raise SnapshotNotFoundError("No completed identity projection snapshot exists for scan")
    status_order = case((IdentityGroupSnapshot.group_status == "LIKELY_DUPLICATE_GROUP", 0), else_=1)
    rows = db.query(
        IdentityGroupSnapshot, IdentityGroupMemberSnapshot, ScanRecordSnapshot
    ).join(
        IdentityGroupMemberSnapshot,
        IdentityGroupMemberSnapshot.group_snapshot_id == IdentityGroupSnapshot.id,
    ).join(
        ScanRecordSnapshot,
        ScanRecordSnapshot.id == IdentityGroupMemberSnapshot.record_snapshot_id,
    ).filter(
        IdentityGroupSnapshot.projection_run_id == run.id,
    ).order_by(
        status_order,
        IdentityGroupSnapshot.group_size.desc(),
        IdentityGroupSnapshot.hypothesis_key,
        IdentityGroupMemberSnapshot.member_index,
    ).all()
    export_rows = []
    for group, member, record in rows:
        export_rows.append({
            "group_snapshot_id": group.id,
            "group_hypothesis_key": group.hypothesis_key,
            "duplicate_group_status": group.group_status,
            "duplicate_group_status_label": _GROUP_LABELS.get(group.group_status, f"Unknown group status ({group.group_status})"),
            "duplicate_group_size": group.group_size,
            "group_member_index": member.member_index,
            "projection_run_id": run.id,
            "projection_algorithm_version": run.algorithm_version,
            "projection_created_at": _utc_timestamp(run.created_at),
            "record_ref_key": member.record_ref_key,
            "site_or_contract": record.contract,
            "part_no": record.part_no,
            "description": record.description,
            "uom": record.uom,
            "product_category": record.product_category_id,
            "hsn_sac": record.hsn_sac_code,
            "supporting_edge_count": group.supporting_edge_count,
            "review_edge_count": group.review_edge_count,
            "non_groupable_internal_count": group.non_groupable_internal_count,
            "internal_pair_count": group.internal_pair_count,
            "internal_pairs_reused": group.internal_pairs_reused,
            "internal_pairs_rescored": group.internal_pairs_rescored,
            "evidence_completeness": group.evidence_completeness,
            "group_reason_codes": _json_array(group.reason_codes_json),
            "distinct_uoms": _json_array(group.distinct_uoms_json),
            "same_uom_pair_count": group.same_uom_pair_count,
            "convertible_uom_pair_count": group.convertible_uom_pair_count,
            "different_basis_pair_count": group.different_basis_pair_count,
            "missing_or_wildcard_pair_count": group.missing_or_wildcard_pair_count,
            "malformed_or_unknown_pair_count": group.malformed_or_unknown_pair_count,
            "possible_mapping_error_count": group.possible_mapping_error_count,
        })
    return _csv(IDENTITY_GROUP_EXPORT_FIELDS, export_rows)


def identity_group_diagnostics_to_csv(
    db, scan_id: int, projection_run_id: int | None = None
) -> str:
    """Export diagnostic families separately, with complete adjacent membership."""
    run = IdentityGroupQueryService(db).resolve_run(scan_id, projection_run_id)
    if run is None:
        raise SnapshotNotFoundError("No completed identity projection snapshot exists for scan")
    rows = db.query(
        IdentityFamilyDiagnosticSnapshot,
        IdentityFamilyDiagnosticMemberSnapshot,
        ScanRecordSnapshot,
    ).join(
        IdentityFamilyDiagnosticMemberSnapshot,
        IdentityFamilyDiagnosticMemberSnapshot.diagnostic_snapshot_id
        == IdentityFamilyDiagnosticSnapshot.id,
    ).join(
        ScanRecordSnapshot,
        ScanRecordSnapshot.id == IdentityFamilyDiagnosticMemberSnapshot.record_snapshot_id,
    ).filter(
        IdentityFamilyDiagnosticSnapshot.projection_run_id == run.id,
    ).order_by(
        IdentityFamilyDiagnosticSnapshot.diagnostic_status,
        IdentityFamilyDiagnosticSnapshot.member_count.desc(),
        IdentityFamilyDiagnosticSnapshot.diagnostic_key,
        IdentityFamilyDiagnosticMemberSnapshot.member_index,
    ).all()
    export_rows = []
    for diagnostic, member, record in rows:
        export_rows.append({
            "diagnostic_snapshot_id": diagnostic.id,
            "diagnostic_key": diagnostic.diagnostic_key,
            "diagnostic_status": diagnostic.diagnostic_status,
            "diagnostic_status_label": _DIAGNOSTIC_LABELS.get(
                diagnostic.diagnostic_status,
                f"Unknown diagnostic status ({diagnostic.diagnostic_status})",
            ),
            "diagnostic_member_count": diagnostic.member_count,
            "diagnostic_member_index": member.member_index,
            "reason_codes": _json_array(diagnostic.reason_codes_json),
            "cannot_link_count": diagnostic.cannot_link_count,
            "projection_run_id": run.id,
            "projection_algorithm_version": run.algorithm_version,
            "projection_created_at": _utc_timestamp(run.created_at),
            "record_ref_key": member.record_ref_key,
            "site_or_contract": record.contract,
            "part_no": record.part_no,
            "description": record.description,
            "uom": record.uom,
            "product_category": record.product_category_id,
            "hsn_sac": record.hsn_sac_code,
        })
    return _csv(IDENTITY_DIAGNOSTIC_EXPORT_FIELDS, export_rows)
