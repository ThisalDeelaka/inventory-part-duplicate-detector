"""Persistence boundary for GF-2 runs and neutral neighbor proposals."""

from __future__ import annotations

from app.db.models import IdentityDiscoveryRun, IdentityNeighborProposal


class DiscoveryRepository:
    def __init__(self, db):
        self.db = db

    def run_for_scan(self, scan_id: int):
        return self.db.query(IdentityDiscoveryRun).filter_by(scan_id=scan_id).one_or_none()

    def add_run(self, **values):
        row = IdentityDiscoveryRun(**values)
        self.db.add(row)
        self.db.flush()
        return row

    def add_proposals(self, rows: list[IdentityNeighborProposal]) -> None:
        if rows:
            self.db.bulk_save_objects(rows)

    def proposals_for_run(self, discovery_run_id: int):
        return (
            self.db.query(IdentityNeighborProposal)
            .filter_by(discovery_run_id=discovery_run_id)
            .order_by(IdentityNeighborProposal.proposal_order, IdentityNeighborProposal.id)
            .all()
        )
