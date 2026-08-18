"""Persistence boundary for GF-2 runs and neutral neighbor proposals."""

from __future__ import annotations

from app.db.models import (
    IdentityDiscoveryRun,
    IdentityNeighborProposal,
    IdentityNeighborhoodMember,
    IdentityNeighborhoodSnapshot,
)


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

    def add_neighborhoods(self, rows: list[IdentityNeighborhoodSnapshot]) -> None:
        if rows:
            self.db.bulk_save_objects(rows)

    def add_neighborhood_members(self, rows: list[IdentityNeighborhoodMember]) -> None:
        if rows:
            self.db.bulk_save_objects(rows)

    def neighborhoods_for_run(self, discovery_run_id: int):
        return (
            self.db.query(IdentityNeighborhoodSnapshot)
            .filter_by(discovery_run_id=discovery_run_id)
            .order_by(IdentityNeighborhoodSnapshot.anchor_record_id)
            .all()
        )

    def members_for_run(self, discovery_run_id: int):
        return (
            self.db.query(IdentityNeighborhoodMember)
            .join(
                IdentityNeighborhoodSnapshot,
                IdentityNeighborhoodSnapshot.id == IdentityNeighborhoodMember.neighborhood_id,
            )
            .filter(IdentityNeighborhoodSnapshot.discovery_run_id == discovery_run_id)
            .order_by(
                IdentityNeighborhoodMember.neighborhood_id,
                IdentityNeighborhoodMember.member_order,
            )
            .all()
        )
