"""Bounded, read-only queries over immutable G2 identity snapshot tables."""

import json

from sqlalchemy import case, func
from sqlalchemy.orm import aliased

from app.db.models import (
    DuplicateScan,
    IdentityFamilyDiagnosticMemberSnapshot,
    IdentityFamilyDiagnosticSnapshot,
    IdentityGroupEdgeSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupReviewEvent,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)


class SnapshotNotFoundError(LookupError):
    pass


class InvalidSnapshotSelectionError(ValueError):
    pass


def _json_list(value, *, limit=32):
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed[:limit] if isinstance(parsed, list) else []


def _run_json(run):
    return {
        "projection_run_id": run.id,
        "scan_id": run.scan_id,
        "algorithm_version": run.algorithm_version,
        "edge_classifier_version": run.edge_classifier_version,
        "deterministic_engine_version": run.engine_version,
        "evidence_fingerprint": run.evidence_fingerprint,
        "max_group_validation_members": run.max_group_validation_members,
        "status": run.status,
        "created_at": run.created_at,
        **{name: getattr(run, name) for name in (
            "records_seen", "seed_edges", "provisional_components", "accepted_groups",
            "likely_groups", "review_groups", "conflicting_families", "oversized_families",
            "ambiguous_families", "internal_pairs_total", "internal_pairs_reused",
            "internal_pairs_rescored", "cannot_links_found", "max_component_size",
            "max_accepted_group_size",
        )},
    }


def _uom_json(group=None, aggregate=None):
    if group is not None:
        return {
            "distinct_uoms": _json_list(group.distinct_uoms_json),
            **{name: getattr(group, name) for name in (
                "same_uom_pair_count", "convertible_uom_pair_count",
                "different_basis_pair_count", "missing_or_wildcard_pair_count",
                "malformed_or_unknown_pair_count", "possible_mapping_error_count",
            )},
        }
    aggregate = aggregate or {}
    return {"distinct_uoms": aggregate.get("distinct_uoms", []), **{
        name: int(aggregate.get(name, 0) or 0) for name in (
            "same_uom_pair_count", "convertible_uom_pair_count",
            "different_basis_pair_count", "missing_or_wildcard_pair_count",
            "malformed_or_unknown_pair_count", "possible_mapping_error_count",
        )
    }}


def _empty_review_state():
    return {
        "reviewed": False,
        "current_decision_type": None,
        "reviewer": None,
        "reviewed_at": None,
        "current_review_event_id": None,
    }


def _group_json(group, review_state=None):
    return {
        "group_snapshot_id": group.id,
        "hypothesis_key": group.hypothesis_key,
        "group_status": group.group_status,
        "group_size": group.group_size,
        "supporting_edge_count": group.supporting_edge_count,
        "review_edge_count": group.review_edge_count,
        "non_groupable_internal_count": group.non_groupable_internal_count,
        "internal_pair_count": group.internal_pair_count,
        "internal_pairs_reused": group.internal_pairs_reused,
        "internal_pairs_rescored": group.internal_pairs_rescored,
        "evidence_completeness": group.evidence_completeness,
        "reason_codes": _json_list(group.reason_codes_json),
        "uom_summary": _uom_json(group),
        "projection_algorithm_version": group.projection_algorithm_version,
        "created_at": group.created_at,
        "review_state": review_state or _empty_review_state(),
    }


def _diagnostic_json(row):
    return {
        "diagnostic_snapshot_id": row.id,
        "diagnostic_key": row.diagnostic_key,
        "diagnostic_status": row.diagnostic_status,
        "member_count": row.member_count,
        "seed_edge_count": row.seed_edge_count,
        "internal_pair_count": row.internal_pair_count,
        "internal_pairs_reused": row.internal_pairs_reused,
        "internal_pairs_rescored": row.internal_pairs_rescored,
        "cannot_link_count": row.cannot_link_count,
        "reason_codes": _json_list(row.reason_codes_json),
        "projection_algorithm_version": row.projection_algorithm_version,
        "created_at": row.created_at,
    }


def _member_json(member, record):
    return {
        "member_index": member.member_index,
        "record_ref_key": member.record_ref_key,
        "contract": record.contract,
        "part_no": record.part_no,
        "description": record.description,
        "normalized_part_no": record.normalized_part_no,
        "normalized_description": record.normalized_description,
        "uom": record.uom,
        "product_category_id": record.product_category_id,
        "hsn_sac_code": record.hsn_sac_code,
    }


def _edge_json(row, refs_by_id):
    return {
        "left_record_ref_key": refs_by_id[row.left_record_snapshot_id],
        "right_record_ref_key": refs_by_id[row.right_record_snapshot_id],
        "edge_class": row.edge_class,
        "reason_codes": _json_list(row.reason_codes_json),
        "evidence_source": row.evidence_source,
        "candidate_id": row.candidate_id,
        "exclusion_id": row.exclusion_id,
        "deterministic_score": row.deterministic_score,
        "deterministic_status": row.deterministic_status,
        "critical_mismatches": _json_list(row.critical_mismatches_json),
    }


class IdentityGroupQueryService:
    def __init__(self, db):
        self.db = db

    def scan_exists(self, scan_id):
        return self.db.query(DuplicateScan.id).filter_by(id=scan_id).first() is not None

    def _current_review_states(self, group_ids):
        if not group_ids:
            return {}
        successor = aliased(IdentityGroupReviewEvent)
        rows = self.db.query(IdentityGroupReviewEvent).outerjoin(
            successor,
            successor.supersedes_review_event_id == IdentityGroupReviewEvent.id,
        ).filter(
            IdentityGroupReviewEvent.group_snapshot_id.in_(group_ids),
            successor.id.is_(None),
        ).order_by(IdentityGroupReviewEvent.id).all()
        return {
            row.group_snapshot_id: {
                "reviewed": True,
                "current_decision_type": row.decision_type,
                "reviewer": row.reviewer,
                "reviewed_at": row.created_at,
                "current_review_event_id": row.id,
            }
            for row in rows
        }

    def list_runs(self, scan_id):
        return [
            _run_json(run) for run in self.db.query(IdentityGroupProjectionRun).filter_by(
                scan_id=scan_id
            ).order_by(
                IdentityGroupProjectionRun.created_at.desc(),
                IdentityGroupProjectionRun.id.desc(),
            ).all()
        ]

    def resolve_run(self, scan_id, projection_run_id=None):
        query = self.db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan_id)
        if projection_run_id is not None:
            run = query.filter_by(id=projection_run_id).one_or_none()
            if run is None:
                raise SnapshotNotFoundError("Identity projection snapshot not found for scan")
            if run.status != "COMPLETED":
                raise InvalidSnapshotSelectionError("Selected projection run is not a completed data snapshot")
            return run
        return query.filter_by(status="COMPLETED").order_by(
            IdentityGroupProjectionRun.created_at.desc(),
            IdentityGroupProjectionRun.id.desc(),
        ).first()

    def summary(self, scan_id, projection_run_id=None):
        run = self.resolve_run(scan_id, projection_run_id)
        empty_uom = _uom_json()
        if run is None:
            return {"snapshot_available": False, "selected_projection": None, "uom_summary": empty_uom}
        size_rows = self.db.query(
            IdentityGroupSnapshot.group_size, func.count(IdentityGroupSnapshot.id)
        ).filter_by(projection_run_id=run.id).group_by(IdentityGroupSnapshot.group_size).all()
        aggregate = self.db.query(
            func.sum(IdentityGroupSnapshot.same_uom_pair_count),
            func.sum(IdentityGroupSnapshot.convertible_uom_pair_count),
            func.sum(IdentityGroupSnapshot.different_basis_pair_count),
            func.sum(IdentityGroupSnapshot.missing_or_wildcard_pair_count),
            func.sum(IdentityGroupSnapshot.malformed_or_unknown_pair_count),
            func.sum(IdentityGroupSnapshot.possible_mapping_error_count),
        ).filter_by(projection_run_id=run.id).one()
        distinct_uoms = set()
        for (value,) in self.db.query(IdentityGroupSnapshot.distinct_uoms_json).filter_by(
            projection_run_id=run.id
        ).all():
            distinct_uoms.update(_json_list(value))
        largest_diagnostic = self.db.query(func.max(IdentityFamilyDiagnosticSnapshot.member_count)).filter_by(
            projection_run_id=run.id
        ).scalar() or 0
        names = (
            "same_uom_pair_count", "convertible_uom_pair_count", "different_basis_pair_count",
            "missing_or_wildcard_pair_count", "malformed_or_unknown_pair_count",
            "possible_mapping_error_count",
        )
        uom = {name: aggregate[index] or 0 for index, name in enumerate(names)}
        uom["distinct_uoms"] = sorted(distinct_uoms)
        return {
            "snapshot_available": True,
            "selected_projection": _run_json(run),
            "accepted_groups": run.accepted_groups,
            "likely_groups": run.likely_groups,
            "review_groups": run.review_groups,
            "diagnostic_families": run.conflicting_families + run.oversized_families + run.ambiguous_families,
            "conflicting_families": run.conflicting_families,
            "oversized_families": run.oversized_families,
            "ambiguous_families": run.ambiguous_families,
            "group_size_distribution": {size: count for size, count in size_rows},
            "largest_accepted_group": run.max_accepted_group_size,
            "largest_diagnostic_family": largest_diagnostic,
            "uom_summary": _uom_json(aggregate=uom),
        }

    def list_groups(self, scan_id, projection_run_id=None, status=None, minimum_group_size=None,
                    maximum_group_size=None, limit=50, offset=0):
        run = self.resolve_run(scan_id, projection_run_id)
        if run is None:
            return {"selected_projection": None, "limit": limit, "offset": offset, "total": 0, "items": []}
        query = self.db.query(IdentityGroupSnapshot).filter_by(projection_run_id=run.id)
        if status is not None:
            query = query.filter(IdentityGroupSnapshot.group_status == status)
        if minimum_group_size is not None:
            query = query.filter(IdentityGroupSnapshot.group_size >= minimum_group_size)
        if maximum_group_size is not None:
            query = query.filter(IdentityGroupSnapshot.group_size <= maximum_group_size)
        total = query.count()
        status_order = case((IdentityGroupSnapshot.group_status == "LIKELY_DUPLICATE_GROUP", 0), else_=1)
        rows = query.order_by(
            status_order, IdentityGroupSnapshot.group_size.desc(), IdentityGroupSnapshot.hypothesis_key
        ).offset(offset).limit(limit).all()
        review_states = self._current_review_states([row.id for row in rows])
        return {"selected_projection": _run_json(run), "limit": limit, "offset": offset,
                "total": total, "items": [
                    _group_json(row, review_states.get(row.id)) for row in rows
                ]}

    def group_detail(self, scan_id, group_snapshot_id, projection_run_id=None):
        run = self.resolve_run(scan_id, projection_run_id)
        if run is None:
            raise SnapshotNotFoundError("No completed identity projection snapshot exists for scan")
        group = self.db.query(IdentityGroupSnapshot).filter_by(
            id=group_snapshot_id, scan_id=scan_id, projection_run_id=run.id
        ).one_or_none()
        if group is None:
            raise SnapshotNotFoundError("Identity group snapshot not found")
        member_rows = self.db.query(IdentityGroupMemberSnapshot, ScanRecordSnapshot).join(
            ScanRecordSnapshot, ScanRecordSnapshot.id == IdentityGroupMemberSnapshot.record_snapshot_id
        ).filter(IdentityGroupMemberSnapshot.group_snapshot_id == group.id).order_by(
            IdentityGroupMemberSnapshot.member_index
        ).all()
        refs_by_id = {record.id: member.record_ref_key for member, record in member_rows}
        edges = self.db.query(IdentityGroupEdgeSnapshot).filter_by(group_snapshot_id=group.id).order_by(
            IdentityGroupEdgeSnapshot.left_record_snapshot_id,
            IdentityGroupEdgeSnapshot.right_record_snapshot_id,
        ).all()
        review_state = self._current_review_states([group.id]).get(group.id)
        return {**_group_json(group, review_state), "projection": _run_json(run),
                "members": [_member_json(member, record) for member, record in member_rows],
                "internal_edges": [_edge_json(edge, refs_by_id) for edge in edges]}

    def list_diagnostics(self, scan_id, projection_run_id=None, status=None, limit=50, offset=0):
        run = self.resolve_run(scan_id, projection_run_id)
        if run is None:
            return {"selected_projection": None, "limit": limit, "offset": offset, "total": 0, "items": []}
        query = self.db.query(IdentityFamilyDiagnosticSnapshot).filter_by(projection_run_id=run.id)
        if status is not None:
            query = query.filter(IdentityFamilyDiagnosticSnapshot.diagnostic_status == status)
        total = query.count()
        rows = query.order_by(
            IdentityFamilyDiagnosticSnapshot.diagnostic_status,
            IdentityFamilyDiagnosticSnapshot.member_count.desc(),
            IdentityFamilyDiagnosticSnapshot.diagnostic_key,
        ).offset(offset).limit(limit).all()
        return {"selected_projection": _run_json(run), "limit": limit, "offset": offset,
                "total": total, "items": [_diagnostic_json(row) for row in rows]}

    def diagnostic_detail(self, scan_id, diagnostic_snapshot_id, projection_run_id=None):
        run = self.resolve_run(scan_id, projection_run_id)
        if run is None:
            raise SnapshotNotFoundError("No completed identity projection snapshot exists for scan")
        diagnostic = self.db.query(IdentityFamilyDiagnosticSnapshot).filter_by(
            id=diagnostic_snapshot_id, scan_id=scan_id, projection_run_id=run.id
        ).one_or_none()
        if diagnostic is None:
            raise SnapshotNotFoundError("Identity family diagnostic snapshot not found")
        member_rows = self.db.query(IdentityFamilyDiagnosticMemberSnapshot, ScanRecordSnapshot).join(
            ScanRecordSnapshot,
            ScanRecordSnapshot.id == IdentityFamilyDiagnosticMemberSnapshot.record_snapshot_id,
        ).filter(
            IdentityFamilyDiagnosticMemberSnapshot.diagnostic_snapshot_id == diagnostic.id
        ).order_by(IdentityFamilyDiagnosticMemberSnapshot.member_index).all()
        refs_by_id = {record.id: member.record_ref_key for member, record in member_rows}
        edges = self.db.query(IdentityGroupEdgeSnapshot).filter_by(
            diagnostic_snapshot_id=diagnostic.id
        ).order_by(
            IdentityGroupEdgeSnapshot.left_record_snapshot_id,
            IdentityGroupEdgeSnapshot.right_record_snapshot_id,
        ).all()
        return {**_diagnostic_json(diagnostic), "projection": _run_json(run),
                "members": [_member_json(member, record) for member, record in member_rows],
                "conflict_edges": [_edge_json(edge, refs_by_id) for edge in edges]}
