"""Narrow persistence boundary for immutable GF-8B orchestration audit."""

from app.db.models import ScanOrchestrationRun, ScanOrchestrationStageResultRow


class ScanOrchestrationRepository:
    def __init__(self, db):
        self.db = db

    def run_for_scan(self, scan_id: int):
        return self.db.query(ScanOrchestrationRun).filter_by(scan_id=scan_id).one_or_none()

    def add_run(self, **values):
        row = ScanOrchestrationRun(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def stage_for_run(self, run_id: int, stage_id: str):
        return self.db.query(ScanOrchestrationStageResultRow).filter_by(
            orchestration_run_id=run_id,
            stage_id=stage_id,
        ).one_or_none()

    def add_stage(self, **values):
        row = ScanOrchestrationStageResultRow(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def stages_for_run(self, run_id: int):
        return self.db.query(ScanOrchestrationStageResultRow).filter_by(
            orchestration_run_id=run_id
        ).order_by(ScanOrchestrationStageResultRow.execution_order).all()
