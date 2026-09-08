"""Authority-selected, member-shaped GF-9C identity exports."""

from __future__ import annotations

import csv
import io
import json
from collections import defaultdict

from sqlalchemy.orm import aliased

from app.db.models import (
    VersionedIdentityGroupReviewEvent,
    VersionedIdentityGroupReviewPartition,
    VersionedIdentityGroupReviewPartitionMember,
)
from app.identity_read.contracts import IdentityReadProjectionContract
from app.identity_read.fingerprints import canonical_value
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.services.export_service import sanitize_csv_cell
from app.services.identity_group_review_export_service import (
    reviewed_identity_decisions_to_csv,
)
from app.services.identity_read_service import IdentityReadService
from app.services.canonical_record_service import load_scan_record_catalog


SYSTEM_GROUP_EXPORT_FIELDS = [
    "export_contract_version", "scan_id", "projection_contract",
    "source_projection_run_id", "source_orchestration_run_id",
    "source_resolution_run_id", "group_key", "group_reference", "group_status",
    "validation_mode", "member_count", "member_order", "record_id",
    "stable_record_reference", "source_row_reference", "part_no", "description",
    "site_or_contract", "uom", "product_category", "hsn_sac",
    "possible_relationship_count", "evaluated_relationship_count",
    "required_validation_evidence_count", "missing_nonrequired_relationship_count",
    "group_evidence_summary", "bridge_risk_summary", "genericity_risk_summary",
    "missing_evidence_summary",
]

IDENTITY_CONFLICT_EXPORT_FIELDS = [
    "export_contract_version", "scan_id", "projection_contract",
    "source_projection_run_id", "source_resolution_run_id", "conflict_reference",
    "conflict_type", "member_count", "member_order", "record_id",
    "stable_record_reference", "source_row_reference", "part_no", "description",
    "site_or_contract", "uom", "summary", "protected_evidence_references",
    "source_neighborhood_references", "source_conflict_fingerprint",
]

DEFERRED_IDENTITY_WORK_EXPORT_FIELDS = [
    "export_contract_version", "scan_id", "projection_contract",
    "source_projection_run_id", "source_resolution_run_id", "deferred_reference",
    "deferred_reason", "member_count", "member_order", "record_id",
    "stable_record_reference", "source_row_reference", "part_no", "description",
    "site_or_contract", "uom", "unfinished_evidence_summary",
    "source_neighborhood_references", "source_deferred_fingerprint",
]

REVIEWED_IDENTITY_EXPORT_FIELDS_V2 = [
    "export_contract_version", "scan_id", "projection_contract",
    "source_projection_run_id", "source_orchestration_run_id",
    "source_resolution_run_id", "group_key", "group_reference", "group_status",
    "review_event_id", "reviewed_identity_set_key", "reviewed_identity_set_index",
    "reviewed_identity_set_size", "member_order", "record_id",
    "stable_record_reference", "source_row_reference", "part_no", "description",
    "site_or_contract", "uom", "product_category", "hsn_sac",
    "review_decision_type", "reviewer", "reviewed_at", "review_comment",
    "operational_authority",
]

_CONTRACT_VERSION = "identity-read-export-v1"


def _json(value) -> str:
    return json.dumps(
        canonical_value(value), ensure_ascii=True, sort_keys=True,
        separators=(",", ":"),
    )


def _csv(fields, rows) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: sanitize_csv_cell(row.get(field)) for field in fields})
    return output.getvalue()


def _projection(snapshot):
    return {
        "export_contract_version": _CONTRACT_VERSION,
        "scan_id": snapshot.scan_id,
        "projection_contract": snapshot.projection_contract.value,
        "source_projection_run_id": snapshot.source_projection_run_id,
        "source_orchestration_run_id": snapshot.source_orchestration_run_id,
        "source_resolution_run_id": snapshot.source_resolution_run_id,
    }


def _member(member):
    return {
        "record_id": member.record_id,
        "stable_record_reference": member.stable_record_reference,
        "source_row_reference": member.source_row_index,
        "part_no": member.part_no,
        "description": member.description,
        "site_or_contract": member.contract,
        "uom": member.uom,
        "product_category": member.product_category_id,
        "hsn_sac": member.hsn_sac_code,
        "part_type": member.type_code,
        "commodity_group_01": member.prime_commodity,
        "commodity_group_02": member.second_commodity,
        "safety_code": member.hazard_code,
        "accounting_group": member.accounting_group,
        "product_code": member.part_product_code,
        "product_family": member.part_product_family,
    }


def authority_selected_system_group_rows(db, scan_id: int):
    """Return the authoritative snapshot and shared member-shaped export rows."""
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan_id)
    base = _projection(snapshot)
    rows = []
    for group in snapshot.groups:
        coverage = group.validation_coverage
        group_key = serialize_versioned_identity_group_key(group.versioned_group_key)
        for member in group.members:
            rows.append({
                **base,
                "group_key": group_key,
                "group_reference": group.versioned_group_key.group_reference,
                "group_status": group.status.value,
                "validation_mode": group.validation_mode.value,
                "member_count": group.member_count,
                "member_order": member.member_order,
                **_member(member),
                "possible_relationship_count": coverage.possible_internal_pair_count,
                "evaluated_relationship_count": coverage.evaluated_internal_pair_count,
                "required_validation_evidence_count": coverage.required_validation_evidence_count,
                "missing_nonrequired_relationship_count": coverage.missing_nonrequired_pair_count,
                "group_evidence_summary": _json(group.group_evidence_summary),
                "bridge_risk_summary": _json(group.bridge_risk_summary),
                "genericity_risk_summary": _json(group.genericity_risk_summary),
                "missing_evidence_summary": _json(group.missing_evidence_summary),
            })
    return snapshot, tuple(rows)


def authority_selected_system_groups_to_csv(db, scan_id: int) -> str:
    """Export exactly one row per authoritative group member."""
    _, rows = authority_selected_system_group_rows(db, scan_id)
    return _csv(SYSTEM_GROUP_EXPORT_FIELDS, rows)


def _record_lookup(db, scan_id):
    return {
        row.record_ref_key: row for row in load_scan_record_catalog(db, scan_id)
    }


def authority_selected_conflicts_to_csv(db, scan_id: int) -> str:
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan_id)
    records = _record_lookup(db, scan_id)
    base = _projection(snapshot)
    rows = []
    for outcome in snapshot.conflicts:
        for index, reference in enumerate(outcome.involved_record_references):
            record = records.get(reference)
            rows.append({
                **base,
                "conflict_reference": outcome.conflict_reference,
                "conflict_type": outcome.conflict_type,
                "member_count": len(outcome.involved_record_references),
                "member_order": index,
                "record_id": outcome.involved_record_ids[index],
                "stable_record_reference": reference,
                "source_row_reference": getattr(record, "source_row_index", None),
                "part_no": getattr(record, "part_no", None),
                "description": getattr(record, "description", None),
                "site_or_contract": getattr(record, "contract", None),
                "uom": getattr(record, "uom", None),
                "summary": outcome.summary,
                "protected_evidence_references": _json(outcome.protected_evidence_references),
                "source_neighborhood_references": _json(outcome.source_neighborhood_references),
                "source_conflict_fingerprint": outcome.source_conflict_fingerprint,
            })
    return _csv(IDENTITY_CONFLICT_EXPORT_FIELDS, rows)


def authority_selected_deferred_to_csv(db, scan_id: int) -> str:
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan_id)
    records = _record_lookup(db, scan_id)
    base = _projection(snapshot)
    rows = []
    for outcome in snapshot.deferred_work_units:
        for index, reference in enumerate(outcome.record_references):
            record = records.get(reference)
            rows.append({
                **base,
                "deferred_reference": outcome.deferred_reference,
                "deferred_reason": outcome.reason,
                "member_count": len(outcome.record_references),
                "member_order": index,
                "record_id": outcome.record_ids[index],
                "stable_record_reference": reference,
                "source_row_reference": getattr(record, "source_row_index", None),
                "part_no": getattr(record, "part_no", None),
                "description": getattr(record, "description", None),
                "site_or_contract": getattr(record, "contract", None),
                "uom": getattr(record, "uom", None),
                "unfinished_evidence_summary": outcome.unfinished_evidence_summary,
                "source_neighborhood_references": _json(outcome.source_neighborhood_references),
                "source_deferred_fingerprint": outcome.source_deferred_fingerprint,
            })
    return _csv(DEFERRED_IDENTITY_WORK_EXPORT_FIELDS, rows)


def _reviewed_set_key(group_key: str, review_id: int, partition_index: int, refs) -> str:
    import hashlib
    payload = f"{group_key}|{review_id}|{partition_index}|{'|'.join(sorted(refs))}"
    return "reviewed-set-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _v1_confirmed_rows(db, snapshot):
    audit_csv = reviewed_identity_decisions_to_csv(
        db, snapshot.scan_id, snapshot.source_projection_run_id
    )
    for row in csv.DictReader(io.StringIO(audit_csv)):
        if row["member_review_outcome"] != "CONFIRMED_IN_IDENTITY_SET":
            continue
        if row["review_decision_type"] not in {
            "CONFIRM_ALL_AS_ONE", "CONFIRM_SELECTED", "SPLIT_PARTITIONS"
        }:
            continue
        group_reference = row["group_hypothesis_key"]
        group = next(
            item for item in snapshot.groups
            if item.versioned_group_key.group_reference == group_reference
        )
        group_key = serialize_versioned_identity_group_key(group.versioned_group_key)
        member = next(
            item for item in group.members
            if item.stable_record_reference == row["record_ref_key"]
        )
        yield {
            **_projection(snapshot),
            "group_key": group_key,
            "group_reference": group_reference,
            "group_status": group.status.value,
            "review_event_id": row["review_event_id"],
            "reviewed_identity_set_key": row["reviewed_identity_set_key"],
            "reviewed_identity_set_index": row["reviewed_identity_set_index"],
            "reviewed_identity_set_size": row["reviewed_identity_set_size"],
            "member_order": member.member_order,
            **_member(member),
            "review_decision_type": row["review_decision_type"],
            "reviewer": row["reviewer"],
            "reviewed_at": row["reviewed_at"],
            "review_comment": row["review_comment"],
            "operational_authority": "HUMAN_CONFIRMED",
        }


def _v2_confirmed_rows(db, snapshot):
    groups = {
        serialize_versioned_identity_group_key(group.versioned_group_key): group
        for group in snapshot.groups
    }
    successor = aliased(VersionedIdentityGroupReviewEvent)
    reviews = db.query(VersionedIdentityGroupReviewEvent).outerjoin(
        successor,
        successor.supersedes_review_event_id == VersionedIdentityGroupReviewEvent.id,
    ).filter(
        VersionedIdentityGroupReviewEvent.scan_id == snapshot.scan_id,
        VersionedIdentityGroupReviewEvent.projection_contract == "G2_V2",
        VersionedIdentityGroupReviewEvent.source_projection_run_id
        == snapshot.source_projection_run_id,
        VersionedIdentityGroupReviewEvent.versioned_group_key.in_(tuple(groups))
        if groups else False,
        successor.id.is_(None),
    ).order_by(VersionedIdentityGroupReviewEvent.versioned_group_key).all()
    affirmative = {
        row.id: row for row in reviews if row.decision_type in {
            "CONFIRM_ALL_AS_ONE", "CONFIRM_SELECTED", "SPLIT_PARTITIONS"
        }
    }
    partition_rows = db.query(
        VersionedIdentityGroupReviewPartition,
        VersionedIdentityGroupReviewPartitionMember,
    ).join(
        VersionedIdentityGroupReviewPartitionMember,
        VersionedIdentityGroupReviewPartitionMember.partition_id
        == VersionedIdentityGroupReviewPartition.id,
    ).filter(
        VersionedIdentityGroupReviewPartition.review_event_id.in_(tuple(affirmative))
        if affirmative else False
    ).order_by(
        VersionedIdentityGroupReviewPartition.review_event_id,
        VersionedIdentityGroupReviewPartition.partition_index,
        VersionedIdentityGroupReviewPartitionMember.member_index,
    ).all()
    partitions = defaultdict(lambda: defaultdict(list))
    for partition, member in partition_rows:
        partitions[partition.review_event_id][partition.partition_index].append(
            member.record_ref_key
        )
    for review in affirmative.values():
        group = groups[review.versioned_group_key]
        members = {item.stable_record_reference: item for item in group.members}
        for partition_index, refs in sorted(partitions[review.id].items()):
            set_key = _reviewed_set_key(
                review.versioned_group_key, review.id, partition_index, refs
            )
            for ref in refs:
                member = members[ref]
                yield {
                    **_projection(snapshot),
                    "group_key": review.versioned_group_key,
                    "group_reference": review.group_reference,
                    "group_status": group.status.value,
                    "review_event_id": review.id,
                    "reviewed_identity_set_key": set_key,
                    "reviewed_identity_set_index": partition_index + 1,
                    "reviewed_identity_set_size": len(refs),
                    "member_order": member.member_order,
                    **_member(member),
                    "review_decision_type": review.decision_type,
                    "reviewer": review.reviewer,
                    "reviewed_at": review.created_at,
                    "review_comment": review.comment,
                    "operational_authority": "HUMAN_CONFIRMED",
                }


def authority_selected_reviewed_identities_to_csv(db, scan_id: int) -> str:
    """Export confirmed sets from only the exact authority-selected review chain."""
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan_id)
    if snapshot.projection_contract == IdentityReadProjectionContract.G2_V1:
        rows = _v1_confirmed_rows(db, snapshot)
    else:
        rows = _v2_confirmed_rows(db, snapshot)
    return _csv(REVIEWED_IDENTITY_EXPORT_FIELDS_V2, rows)
