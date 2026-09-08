"""Narrow persistence boundary for immutable GF-5C resolution history."""

from app.db.models import (
    IdentityResolutionConflictMember,
    IdentityResolutionConflictSnapshot,
    IdentityResolutionConstraintInput,
    IdentityResolutionDeferredMember,
    IdentityResolutionDeferredSnapshot,
    IdentityResolutionGroupMember,
    IdentityResolutionGroupSnapshot,
    IdentityResolutionRun,
    IdentityResolutionTargetedEvidence,
    IdentityResolutionUnassignedRecord,
)


class ResolutionRepository:
    def __init__(self, db):
        self.db = db

    def run_for_input(self, **identity):
        return self.db.query(IdentityResolutionRun).filter_by(**identity).one_or_none()

    def add_run(self, **values):
        row = IdentityResolutionRun(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def add_all(self, rows):
        self.db.add_all(rows)
        self.db.flush()

    def result_rows(self, run_id: int):
        groups = self.db.query(IdentityResolutionGroupSnapshot).filter_by(
            resolution_run_id=run_id
        ).order_by(IdentityResolutionGroupSnapshot.hypothesis_id).all()
        group_members = self.db.query(IdentityResolutionGroupMember).filter_by(
            resolution_run_id=run_id
        ).order_by(
            IdentityResolutionGroupMember.group_snapshot_id,
            IdentityResolutionGroupMember.member_index,
        ).all()
        conflicts = self.db.query(IdentityResolutionConflictSnapshot).filter_by(
            resolution_run_id=run_id
        ).order_by(IdentityResolutionConflictSnapshot.conflict_id).all()
        conflict_members = self.db.query(IdentityResolutionConflictMember).filter_by(
            resolution_run_id=run_id
        ).order_by(
            IdentityResolutionConflictMember.conflict_snapshot_id,
            IdentityResolutionConflictMember.member_index,
        ).all()
        deferred = self.db.query(IdentityResolutionDeferredSnapshot).filter_by(
            resolution_run_id=run_id
        ).order_by(IdentityResolutionDeferredSnapshot.deferred_id).all()
        deferred_members = self.db.query(IdentityResolutionDeferredMember).filter_by(
            resolution_run_id=run_id
        ).order_by(
            IdentityResolutionDeferredMember.deferred_snapshot_id,
            IdentityResolutionDeferredMember.member_index,
        ).all()
        targeted = self.db.query(IdentityResolutionTargetedEvidence).filter_by(
            resolution_run_id=run_id
        ).order_by(
            IdentityResolutionTargetedEvidence.record_id_1,
            IdentityResolutionTargetedEvidence.record_id_2,
            IdentityResolutionTargetedEvidence.reason,
        ).all()
        unassigned = self.db.query(IdentityResolutionUnassignedRecord).filter_by(
            resolution_run_id=run_id
        ).order_by(IdentityResolutionUnassignedRecord.unassigned_index).all()
        return groups, group_members, conflicts, conflict_members, deferred, deferred_members, targeted, unassigned

    def constraints_for_run(self, run_id: int):
        return self.db.query(IdentityResolutionConstraintInput).filter_by(
            resolution_run_id=run_id
        ).order_by(
            IdentityResolutionConstraintInput.record_id_1,
            IdentityResolutionConstraintInput.record_id_2,
            IdentityResolutionConstraintInput.constraint_type,
        ).all()
