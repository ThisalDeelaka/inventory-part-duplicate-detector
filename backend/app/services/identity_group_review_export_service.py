"""Current human-review overlay CSV for immutable accepted group snapshots."""

import hashlib

from sqlalchemy import case, func
from sqlalchemy.orm import aliased

from app.db.models import (
    HumanIdentityConstraint,
    IdentityGroupMemberSnapshot,
    IdentityGroupReviewEvent,
    IdentityGroupReviewPartition,
    IdentityGroupReviewPartitionMember,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.services.identity_group_export_service import _csv, _json_array, _utc_timestamp
from app.services.identity_group_query_service import (
    IdentityGroupQueryService,
    InvalidSnapshotSelectionError,
    SnapshotNotFoundError,
)


REVIEWED_IDENTITY_EXPORT_FIELDS = [
    "projection_run_id", "projection_algorithm_version", "projection_created_at",
    "group_snapshot_id", "group_hypothesis_key", "system_group_status",
    "system_group_size", "original_group_member_index", "record_ref_key",
    "site_or_contract", "part_no", "description", "uom", "product_category",
    "hsn_sac", "review_resolution_status", "review_event_id",
    "review_decision_type", "reviewer", "reviewed_at", "review_comment",
    "supersedes_review_event_id", "reviewed_identity_set_key",
    "reviewed_identity_set_index", "reviewed_identity_set_size",
    "member_review_outcome", "must_link_count", "cannot_link_count",
    "distinct_uoms", "different_basis_pair_count",
    "missing_or_wildcard_pair_count", "malformed_or_unknown_pair_count",
    "possible_mapping_error_count",
]

_RESOLUTION = {
    "CONFIRM_ALL_AS_ONE": "FULLY_RESOLVED",
    "SPLIT_PARTITIONS": "FULLY_RESOLVED",
    "KEEP_ALL_SEPARATE": "FULLY_RESOLVED",
    "CONFIRM_SELECTED": "PARTIALLY_RESOLVED",
    "UNSURE": "UNSURE",
}


def _reviewed_set_key(run, group, review, partition_index, member_refs):
    payload = "|".join([
        f"scan:{run.scan_id}", f"projection:{run.id}", f"group:{group.id}",
        f"hypothesis:{group.hypothesis_key}", f"review:{review.id}",
        f"partition:{partition_index}", "members:" + ",".join(sorted(member_refs)),
    ])
    return "reviewed-set-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def reviewed_identity_decisions_to_csv(
    db, scan_id: int, projection_run_id: int | None = None
) -> str:
    """Overlay only current exact-snapshot reviews without recomputation or writes."""
    run = IdentityGroupQueryService(db).resolve_run(scan_id, projection_run_id)
    if run is None:
        raise SnapshotNotFoundError("No completed identity projection snapshot exists for scan")
    status_order = case(
        (IdentityGroupSnapshot.group_status == "LIKELY_DUPLICATE_GROUP", 0), else_=1
    )
    member_rows = db.query(
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
        status_order, IdentityGroupSnapshot.group_size.desc(),
        IdentityGroupSnapshot.hypothesis_key, IdentityGroupMemberSnapshot.member_index,
    ).all()
    group_ids = tuple(dict.fromkeys(group.id for group, _, _ in member_rows))
    successor = aliased(IdentityGroupReviewEvent)
    reviews = db.query(IdentityGroupReviewEvent).outerjoin(
        successor,
        successor.supersedes_review_event_id == IdentityGroupReviewEvent.id,
    ).filter(
        IdentityGroupReviewEvent.scan_id == scan_id,
        IdentityGroupReviewEvent.projection_run_id == run.id,
        IdentityGroupReviewEvent.group_snapshot_id.in_(group_ids) if group_ids else False,
        successor.id.is_(None),
    ).order_by(IdentityGroupReviewEvent.group_snapshot_id, IdentityGroupReviewEvent.id).all()
    reviews_by_group = {}
    for review in reviews:
        if review.group_snapshot_id in reviews_by_group:
            raise InvalidSnapshotSelectionError(
                "Multiple current reviews exist for an identity group snapshot"
            )
        reviews_by_group[review.group_snapshot_id] = review
    review_ids = [review.id for review in reviews]
    partition_rows = db.query(
        IdentityGroupReviewPartition, IdentityGroupReviewPartitionMember
    ).join(
        IdentityGroupReviewPartitionMember,
        IdentityGroupReviewPartitionMember.partition_id == IdentityGroupReviewPartition.id,
    ).filter(
        IdentityGroupReviewPartition.review_event_id.in_(review_ids)
        if review_ids else False
    ).order_by(
        IdentityGroupReviewPartition.review_event_id,
        IdentityGroupReviewPartition.partition_index,
        IdentityGroupReviewPartitionMember.member_index,
    ).all()
    partitions = {}
    for partition, member in partition_rows:
        partitions.setdefault(partition.review_event_id, {}).setdefault(
            partition.partition_index, []
        ).append(member.record_ref_key)
    count_rows = db.query(
        HumanIdentityConstraint.source_review_event_id,
        HumanIdentityConstraint.constraint_type,
        func.count(HumanIdentityConstraint.id),
    ).filter(
        HumanIdentityConstraint.source_review_event_id.in_(review_ids)
        if review_ids else False
    ).group_by(
        HumanIdentityConstraint.source_review_event_id,
        HumanIdentityConstraint.constraint_type,
    ).all()
    counts = {(event_id, kind): count for event_id, kind, count in count_rows}

    rows_by_group = {}
    for group, member, record in member_rows:
        rows_by_group.setdefault(group.id, (group, []) )[1].append((member, record))
    export_rows = []
    for group, members in rows_by_group.values():
        review = reviews_by_group.get(group.id)
        if review is not None and review.group_hypothesis_key != group.hypothesis_key:
            review = None
        resolution = _RESOLUTION.get(review.decision_type) if review else "NOT_REVIEWED"
        event_partitions = partitions.get(review.id, {}) if review else {}
        partition_by_ref = {
            ref: index for index, refs in event_partitions.items() for ref in refs
        }
        if review and review.decision_type in {
            "CONFIRM_ALL_AS_ONE", "SPLIT_PARTITIONS", "KEEP_ALL_SEPARATE"
        }:
            members = sorted(
                members,
                key=lambda item: (
                    partition_by_ref.get(item[0].record_ref_key, 10**9),
                    item[0].member_index,
                ),
            )
        elif review and review.decision_type == "CONFIRM_SELECTED":
            members = sorted(
                members,
                key=lambda item: (
                    0 if item[0].record_ref_key in partition_by_ref else 1,
                    item[0].member_index,
                ),
            )
        for member, record in members:
            partition_index = partition_by_ref.get(member.record_ref_key)
            has_set = review is not None and partition_index is not None
            set_refs = event_partitions.get(partition_index, []) if has_set else []
            if review is None:
                outcome = "NOT_REVIEWED"
            elif has_set:
                outcome = "CONFIRMED_IN_IDENTITY_SET"
            else:
                outcome = "UNRESOLVED_MEMBER"
            export_rows.append({
                "projection_run_id": run.id,
                "projection_algorithm_version": run.algorithm_version,
                "projection_created_at": _utc_timestamp(run.created_at),
                "group_snapshot_id": group.id,
                "group_hypothesis_key": group.hypothesis_key,
                "system_group_status": group.group_status,
                "system_group_size": group.group_size,
                "original_group_member_index": member.member_index,
                "record_ref_key": member.record_ref_key,
                "site_or_contract": record.contract,
                "part_no": record.part_no,
                "description": record.description,
                "uom": record.uom,
                "product_category": record.product_category_id,
                "hsn_sac": record.hsn_sac_code,
                "review_resolution_status": resolution,
                "review_event_id": review.id if review else None,
                "review_decision_type": review.decision_type if review else None,
                "reviewer": review.reviewer if review else None,
                "reviewed_at": _utc_timestamp(review.created_at) if review else None,
                "review_comment": review.comment if review else None,
                "supersedes_review_event_id": (
                    review.supersedes_review_event_id if review else None
                ),
                "reviewed_identity_set_key": (
                    _reviewed_set_key(
                        run, group, review, partition_index, set_refs
                    ) if has_set else None
                ),
                "reviewed_identity_set_index": partition_index + 1 if has_set else None,
                "reviewed_identity_set_size": len(set_refs) if has_set else None,
                "member_review_outcome": outcome,
                "must_link_count": counts.get((review.id, "MUST_LINK"), 0) if review else 0,
                "cannot_link_count": counts.get((review.id, "CANNOT_LINK"), 0) if review else 0,
                "distinct_uoms": _json_array(group.distinct_uoms_json),
                "different_basis_pair_count": group.different_basis_pair_count,
                "missing_or_wildcard_pair_count": group.missing_or_wildcard_pair_count,
                "malformed_or_unknown_pair_count": group.malformed_or_unknown_pair_count,
                "possible_mapping_error_count": group.possible_mapping_error_count,
            })
    return _csv(REVIEWED_IDENTITY_EXPORT_FIELDS, export_rows)
