"""Bounded persistence boundary for non-current immutable G2-v2 snapshots."""

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
)


class G2V2ProjectionRepository:
    def __init__(self, db):
        self.db = db

    def run_for_identity(self, **identity):
        return self.db.query(G2V2ProjectionRun).filter_by(**identity).one_or_none()

    def add_run(self, **values):
        row = G2V2ProjectionRun(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def add_all(self, rows):
        self.db.add_all(rows)
        self.db.flush()

    def result_rows(self, run_id: int):
        groups = self.db.query(G2V2GroupSnapshotRow).filter_by(
            projection_run_id=run_id
        ).order_by(G2V2GroupSnapshotRow.group_reference).all()
        members = self.db.query(G2V2GroupMemberRow).filter_by(
            projection_run_id=run_id
        ).order_by(G2V2GroupMemberRow.group_snapshot_id, G2V2GroupMemberRow.member_order).all()
        evidence = self.db.query(G2V2InternalEvidenceRow).filter_by(
            projection_run_id=run_id
        ).order_by(
            G2V2InternalEvidenceRow.group_snapshot_id,
            G2V2InternalEvidenceRow.stable_record_reference_1,
            G2V2InternalEvidenceRow.stable_record_reference_2,
            G2V2InternalEvidenceRow.evidence_origin,
        ).all()
        conflicts = self.db.query(G2V2ConflictSnapshotRow).filter_by(
            projection_run_id=run_id
        ).order_by(G2V2ConflictSnapshotRow.conflict_reference).all()
        conflict_members = self.db.query(G2V2ConflictMemberRow).filter_by(
            projection_run_id=run_id
        ).order_by(
            G2V2ConflictMemberRow.conflict_snapshot_id,
            G2V2ConflictMemberRow.member_order,
        ).all()
        deferred = self.db.query(G2V2DeferredSnapshotRow).filter_by(
            projection_run_id=run_id
        ).order_by(G2V2DeferredSnapshotRow.deferred_reference).all()
        deferred_members = self.db.query(G2V2DeferredMemberRow).filter_by(
            projection_run_id=run_id
        ).order_by(
            G2V2DeferredMemberRow.deferred_snapshot_id,
            G2V2DeferredMemberRow.member_order,
        ).all()
        unassigned = self.db.query(G2V2UnassignedRecordRow).filter_by(
            projection_run_id=run_id
        ).order_by(G2V2UnassignedRecordRow.member_order).all()
        return (
            groups, members, evidence, conflicts, conflict_members,
            deferred, deferred_members, unassigned,
        )
