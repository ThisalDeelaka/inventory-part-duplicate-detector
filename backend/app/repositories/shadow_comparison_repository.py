"""Bulk persistence boundary for immutable GF-7B shadow comparisons."""

from app.db.models import (
    ShadowComparisonCaseDeltaRow,
    ShadowComparisonCaseGroupRow,
    ShadowComparisonCaseRecordRow,
    ShadowComparisonCaseRow,
    ShadowComparisonRun,
    ShadowComparisonSafetyDeltaRow,
)


class ShadowComparisonRepository:
    def __init__(self, db):
        self.db = db

    def run_for_identity(self, **identity):
        return self.db.query(ShadowComparisonRun).filter_by(**identity).one_or_none()

    def add_run(self, **values):
        row = ShadowComparisonRun(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def add_all(self, rows):
        self.db.add_all(rows)
        self.db.flush()

    def result_rows(self, run_id: int):
        cases = self.db.query(ShadowComparisonCaseRow).filter_by(
            comparison_run_id=run_id
        ).order_by(ShadowComparisonCaseRow.case_reference).all()
        groups = self.db.query(ShadowComparisonCaseGroupRow).filter_by(
            comparison_run_id=run_id
        ).order_by(
            ShadowComparisonCaseGroupRow.case_id,
            ShadowComparisonCaseGroupRow.source_version,
            ShadowComparisonCaseGroupRow.group_reference,
        ).all()
        records = self.db.query(ShadowComparisonCaseRecordRow).filter_by(
            comparison_run_id=run_id
        ).order_by(
            ShadowComparisonCaseRecordRow.case_id,
            ShadowComparisonCaseRecordRow.record_reference,
        ).all()
        deltas = self.db.query(ShadowComparisonSafetyDeltaRow).filter_by(
            comparison_run_id=run_id
        ).order_by(
            ShadowComparisonSafetyDeltaRow.delta_type,
            ShadowComparisonSafetyDeltaRow.delta_fingerprint,
        ).all()
        links = self.db.query(ShadowComparisonCaseDeltaRow).filter_by(
            comparison_run_id=run_id
        ).order_by(
            ShadowComparisonCaseDeltaRow.case_id,
            ShadowComparisonCaseDeltaRow.safety_delta_id,
        ).all()
        return cases, groups, records, deltas, links
