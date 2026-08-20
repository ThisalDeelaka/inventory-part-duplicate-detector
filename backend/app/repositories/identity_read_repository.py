"""Bounded ORM reads used only by the GF-9 authoritative read service."""

from __future__ import annotations

from app.db.models import (
    G2V2ProjectionRun,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    IdentityResolutionRun,
    ScanOrchestrationRun,
    ScanOrchestrationStageResultRow,
)


class IdentityReadRepository:
    def __init__(self, db):
        self.db = db

    def orchestration_for_scan(self, scan_id: int):
        return self.db.query(ScanOrchestrationRun).filter_by(scan_id=scan_id).one_or_none()

    def orchestration_stages(self, orchestration_run_id: int):
        return self.db.query(ScanOrchestrationStageResultRow).filter_by(
            orchestration_run_id=orchestration_run_id
        ).order_by(ScanOrchestrationStageResultRow.execution_order).all()

    def latest_v1_run(self, scan_id: int):
        return self.db.query(IdentityGroupProjectionRun).filter_by(
            scan_id=scan_id, status="COMPLETED"
        ).order_by(
            IdentityGroupProjectionRun.created_at.desc(),
            IdentityGroupProjectionRun.id.desc(),
        ).first()

    def v1_run(self, run_id: int):
        return self.db.get(IdentityGroupProjectionRun, run_id)

    def v2_run(self, run_id: int):
        return self.db.get(G2V2ProjectionRun, run_id)

    def latest_v2_run(self, scan_id: int):
        return self.db.query(G2V2ProjectionRun).filter_by(scan_id=scan_id).order_by(
            G2V2ProjectionRun.completed_at.desc(), G2V2ProjectionRun.id.desc()
        ).first()

    def resolution_run(self, run_id: int):
        return self.db.get(IdentityResolutionRun, run_id)

    def v1_groups_and_members(self, run_id: int):
        groups = self.db.query(IdentityGroupSnapshot).filter_by(
            projection_run_id=run_id
        ).order_by(IdentityGroupSnapshot.hypothesis_key).all()
        group_ids = [group.id for group in groups]
        members = self.db.query(IdentityGroupMemberSnapshot).filter(
            IdentityGroupMemberSnapshot.group_snapshot_id.in_(group_ids)
        ).order_by(
            IdentityGroupMemberSnapshot.group_snapshot_id,
            IdentityGroupMemberSnapshot.member_index,
        ).all() if group_ids else []
        return groups, members
