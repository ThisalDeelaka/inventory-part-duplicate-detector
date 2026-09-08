"""Persistence boundary for independent GF-4 machine evidence."""

from app.db.models import IdentityEvidenceEdgeSnapshot, IdentityEvidenceRun


class EvidenceRepository:
    def __init__(self, db):
        self.db = db

    def run_for_configuration(
        self, discovery_run_id: int, algorithm_version: str, configuration_fingerprint: str
    ):
        return self.db.query(IdentityEvidenceRun).filter_by(
            discovery_run_id=discovery_run_id,
            algorithm_version=algorithm_version,
            configuration_fingerprint=configuration_fingerprint,
        ).one_or_none()

    def add_run(self, **values):
        row = IdentityEvidenceRun(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def add_edges(self, rows: list[IdentityEvidenceEdgeSnapshot]) -> None:
        if rows:
            self.db.bulk_save_objects(rows)

    def edges_for_run(self, evidence_run_id: int):
        return self.db.query(IdentityEvidenceEdgeSnapshot).filter_by(
            evidence_run_id=evidence_run_id
        ).order_by(
            IdentityEvidenceEdgeSnapshot.record_id_1,
            IdentityEvidenceEdgeSnapshot.record_id_2,
        ).all()

    def runs_for_discovery(self, discovery_run_id: int):
        return self.db.query(IdentityEvidenceRun).filter_by(
            discovery_run_id=discovery_run_id
        ).order_by(IdentityEvidenceRun.id).all()
