"""GF-3 bounded direct-adjacency identity neighborhoods.

Neighborhoods are overlapping discovery work units. This service consumes only
the GF-1 canonical catalog and persisted GF-2 proposals; it never evaluates or
classifies duplicate identity.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.models import (
    IdentityDiscoveryRun as IdentityDiscoveryRunRow,
    IdentityNeighborhoodMember as IdentityNeighborhoodMemberRow,
    IdentityNeighborhoodSnapshot,
)
from app.discovery.contracts import (
    DiscoveryChannel,
    DiscoveryRunStatus,
    IdentityNeighborhood,
    IdentityNeighborhoodMember,
    NeighborhoodMemberRole,
)
from app.repositories.discovery_repository import DiscoveryRepository
from app.services.canonical_record_service import load_scan_record_catalog
from app.services.identity_discovery_service import DISCOVERY_ALGORITHM_VERSION


NEIGHBORHOOD_ALGORITHM_VERSION = "identity-neighborhood-direct-v1"
NEIGHBORHOOD_CONFIGURATION_VERSION = "identity-neighborhood-config-v1"
MEMBER_CAP_WARNING = "MEMBER_CAP_REACHED"
_MAX_WARNING_CODES = 20


@dataclass(frozen=True)
class NeighborhoodBuildResult:
    discovery_run_id: int
    neighborhood_count: int
    member_count: int
    records_in_at_least_one_neighborhood: int
    records_with_proposals_but_no_neighborhood: int
    records_without_proposals: int
    truncated_neighborhood_count: int
    max_candidate_neighbor_count: int
    max_included_member_count: int
    idempotent: bool
    neighborhoods: tuple[IdentityNeighborhood, ...]
    members: tuple[IdentityNeighborhoodMember, ...]


@dataclass(frozen=True)
class _PlannedNeighborhood:
    anchor_record_id: int
    fingerprint: str
    candidate_neighbor_count: int
    selected: tuple[tuple[int, object], ...]
    truncated: bool
    degraded: bool
    warning_codes: tuple[str, ...]


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha256(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def neighborhood_configuration_fingerprint(max_members: int) -> str:
    if max_members < 2:
        raise ValueError("identity neighborhood cap must include at least two members")
    return _sha256({
        "configuration_version": NEIGHBORHOOD_CONFIGURATION_VERSION,
        "max_members_including_anchor": max_members,
    })


def _plan_neighborhoods(run, records, proposals, max_members: int):
    by_id = {record.record_id: record for record in records}
    if len(by_id) != len(records) or any(record.scan_id != run.scan_id for record in records):
        raise ValueError("GF-1 catalog is not a unique same-scan record set")
    adjacency = defaultdict(list)
    for proposal in proposals:
        if proposal.discovery_run_id != run.id or proposal.scan_id != run.scan_id:
            raise ValueError("neighbor proposal belongs to a different run or scan")
        if proposal.record_id_1 not in by_id or proposal.record_id_2 not in by_id:
            raise ValueError("neighbor proposal endpoint is missing from the GF-1 catalog")
        if proposal.record_id_1 == proposal.record_id_2:
            raise ValueError("self proposals cannot form an identity neighborhood")
        adjacency[proposal.record_id_1].append((proposal.record_id_2, proposal))
        adjacency[proposal.record_id_2].append((proposal.record_id_1, proposal))

    configuration_fingerprint = neighborhood_configuration_fingerprint(max_members)
    inherited_warnings = tuple(sorted(set(json.loads(run.warning_codes_json or "[]"))))
    plans = []
    for anchor_id in sorted(adjacency, key=lambda value: by_id[value].record_ref_key):
        direct = sorted(
            adjacency[anchor_id],
            key=lambda item: (
                -float(item[1].proposal_priority or 0),
                int(item[1].proposal_order),
                by_id[item[0]].record_ref_key,
            ),
        )
        selected = tuple(direct[: max_members - 1])
        truncated = len(direct) > len(selected)
        warnings = set(inherited_warnings)
        if truncated:
            warnings.add(MEMBER_CAP_WARNING)
        warning_codes = tuple(sorted(warnings)[:_MAX_WARNING_CODES])
        included_refs = [by_id[anchor_id].record_ref_key] + [
            by_id[record_id].record_ref_key for record_id, _proposal in selected
        ]
        fingerprint = _sha256({
            "contract_version": NEIGHBORHOOD_ALGORITHM_VERSION,
            "discovery_fingerprint": run.discovery_fingerprint,
            "configuration_fingerprint": configuration_fingerprint,
            "anchor_record_ref_key": by_id[anchor_id].record_ref_key,
            "ordered_included_member_ref_keys": included_refs,
            "candidate_neighbor_count": len(direct),
            "is_truncated": truncated,
            "degraded": bool(run.degraded or truncated),
            "warning_codes": warning_codes,
        })
        plans.append(_PlannedNeighborhood(
            anchor_record_id=anchor_id,
            fingerprint=fingerprint,
            candidate_neighbor_count=len(direct),
            selected=selected,
            truncated=truncated,
            degraded=bool(run.degraded or truncated),
            warning_codes=warning_codes,
        ))
    return tuple(plans), configuration_fingerprint


def _load_contracts(db, discovery_run_id: int):
    repository = DiscoveryRepository(db)
    run = db.get(IdentityDiscoveryRunRow, discovery_run_id)
    if run is None:
        raise ValueError("discovery run does not exist")
    records = load_scan_record_catalog(db, run.scan_id)
    records_by_id = {record.record_id: record for record in records}
    proposals = repository.proposals_for_run(discovery_run_id)
    proposals_by_id = {proposal.id: proposal for proposal in proposals}
    neighborhood_rows = repository.neighborhoods_for_run(discovery_run_id)
    member_rows = repository.members_for_run(discovery_run_id)
    members_by_neighborhood = defaultdict(list)
    for row in member_rows:
        members_by_neighborhood[row.neighborhood_id].append(row)

    neighborhoods = []
    members = []
    for row in neighborhood_rows:
        if row.scan_id != run.scan_id or row.anchor_record_id not in records_by_id:
            raise ValueError("neighborhood anchor is outside its canonical scan catalog")
        rows = members_by_neighborhood[row.id]
        if (
            len(rows) != row.member_count
            or sum(item.role == NeighborhoodMemberRole.DIRECT_NEIGHBOR.value for item in rows)
            != row.included_neighbor_count
        ):
            raise ValueError("neighborhood membership counts do not match its snapshot")
        anchors = [item for item in rows if item.role == NeighborhoodMemberRole.ANCHOR.value]
        if (
            len(anchors) != 1
            or anchors[0].record_id != row.anchor_record_id
            or anchors[0].member_order != 0
            or anchors[0].source_proposal_id is not None
        ):
            raise ValueError("neighborhood must contain exactly its declared anchor")
        for item in rows:
            if item.scan_id != run.scan_id or item.record_id not in records_by_id:
                raise ValueError("neighborhood member is outside its canonical scan catalog")
            if item.role == NeighborhoodMemberRole.DIRECT_NEIGHBOR.value:
                proposal = proposals_by_id.get(item.source_proposal_id)
                if proposal is None or proposal.discovery_run_id != run.id or {
                    proposal.record_id_1, proposal.record_id_2
                } != {row.anchor_record_id, item.record_id}:
                    raise ValueError("direct neighborhood member lacks its anchor proposal")
            members.append(IdentityNeighborhoodMember(
                member_id=item.id,
                neighborhood_id=item.neighborhood_id,
                scan_id=item.scan_id,
                record_id=item.record_id,
                role=NeighborhoodMemberRole(item.role),
                member_order=item.member_order,
                source_proposal_id=item.source_proposal_id,
                discovery_priority=item.discovery_priority,
                proposal_order=item.proposal_order,
                source_channels=tuple(
                    DiscoveryChannel(value) for value in json.loads(item.source_channels_json)
                ),
            ))
        neighborhoods.append(IdentityNeighborhood(
            neighborhood_id=row.id,
            discovery_run_id=row.discovery_run_id,
            scan_id=row.scan_id,
            anchor_record_id=row.anchor_record_id,
            algorithm_version=row.algorithm_version,
            configuration_fingerprint=row.configuration_fingerprint,
            max_members=row.max_members,
            candidate_neighbor_count=row.candidate_neighbor_count,
            included_neighbor_count=row.included_neighbor_count,
            member_count=row.member_count,
            is_truncated=bool(row.is_truncated),
            degraded=bool(row.degraded),
            warning_codes=tuple(json.loads(row.warning_codes_json)),
            created_at=row.created_at,
            neighborhood_fingerprint=row.neighborhood_fingerprint,
        ))
    return run, records, proposals, tuple(neighborhoods), tuple(members)


def _result(run, records, proposals, neighborhoods, members, *, idempotent):
    proposal_record_ids = {
        record_id for proposal in proposals
        for record_id in (proposal.record_id_1, proposal.record_id_2)
    }
    neighborhood_record_ids = {member.record_id for member in members}
    return NeighborhoodBuildResult(
        discovery_run_id=run.id,
        neighborhood_count=len(neighborhoods),
        member_count=len(members),
        records_in_at_least_one_neighborhood=len(neighborhood_record_ids),
        records_with_proposals_but_no_neighborhood=len(
            proposal_record_ids - neighborhood_record_ids
        ),
        records_without_proposals=len(records) - len(proposal_record_ids),
        truncated_neighborhood_count=sum(item.is_truncated for item in neighborhoods),
        max_candidate_neighbor_count=max(
            (item.candidate_neighbor_count for item in neighborhoods), default=0
        ),
        max_included_member_count=max(
            (item.member_count for item in neighborhoods), default=0
        ),
        idempotent=idempotent,
        neighborhoods=neighborhoods,
        members=members,
    )


def build_and_persist_identity_neighborhoods(
    db, *, discovery_run_id: int, scan_id: int, max_members: int = 20
) -> NeighborhoodBuildResult:
    """Persist one bounded direct-adjacency neighborhood per proposal endpoint."""
    repository = DiscoveryRepository(db)
    run = db.get(IdentityDiscoveryRunRow, discovery_run_id)
    if run is None or run.scan_id != scan_id:
        raise ValueError("discovery run does not belong to the scan")
    if run.algorithm_version != DISCOVERY_ALGORITHM_VERSION:
        raise ValueError("historical GF-2 discovery runs are not backfilled by GF-3")
    configured_cap = json.loads(run.configuration_json).get(
        "neighborhood_max_members"
    )
    if configured_cap != max_members:
        raise ValueError("neighborhood cap does not match the discovery configuration")
    if run.status == DiscoveryRunStatus.COMPLETED.value:
        loaded = _load_contracts(db, discovery_run_id)
        return _result(*loaded, idempotent=True)
    if run.status != DiscoveryRunStatus.RUNNING.value:
        raise ValueError("only a running GF-3 discovery run can build neighborhoods")
    if repository.neighborhoods_for_run(discovery_run_id):
        raise ValueError("running discovery run already has incomplete neighborhood rows")

    records = load_scan_record_catalog(db, scan_id)
    proposals = repository.proposals_for_run(discovery_run_id)
    plans, configuration_fingerprint = _plan_neighborhoods(
        run, records, proposals, max_members
    )
    neighborhood_rows = [IdentityNeighborhoodSnapshot(
        discovery_run_id=run.id,
        scan_id=scan_id,
        anchor_record_id=plan.anchor_record_id,
        algorithm_version=NEIGHBORHOOD_ALGORITHM_VERSION,
        configuration_fingerprint=configuration_fingerprint,
        max_members=max_members,
        candidate_neighbor_count=plan.candidate_neighbor_count,
        included_neighbor_count=len(plan.selected),
        member_count=len(plan.selected) + 1,
        is_truncated=plan.truncated,
        degraded=plan.degraded,
        warning_codes_json=_canonical_json(list(plan.warning_codes)),
        neighborhood_fingerprint=plan.fingerprint,
    ) for plan in plans]
    repository.add_neighborhoods(neighborhood_rows)
    persisted = {
        row.neighborhood_fingerprint: row
        for row in repository.neighborhoods_for_run(discovery_run_id)
    }
    member_rows = []
    for plan in plans:
        neighborhood = persisted.get(plan.fingerprint)
        if neighborhood is None:
            raise ValueError("persisted neighborhood could not be resolved")
        member_rows.append(IdentityNeighborhoodMemberRow(
            neighborhood_id=neighborhood.id,
            scan_id=scan_id,
            record_id=plan.anchor_record_id,
            role=NeighborhoodMemberRole.ANCHOR.value,
            member_order=0,
            source_proposal_id=None,
            discovery_priority=None,
            proposal_order=None,
            source_channels_json="[]",
        ))
        for member_order, (record_id, proposal) in enumerate(plan.selected, 1):
            member_rows.append(IdentityNeighborhoodMemberRow(
                neighborhood_id=neighborhood.id,
                scan_id=scan_id,
                record_id=record_id,
                role=NeighborhoodMemberRole.DIRECT_NEIGHBOR.value,
                member_order=member_order,
                source_proposal_id=proposal.id,
                discovery_priority=proposal.proposal_priority,
                proposal_order=proposal.proposal_order,
                source_channels_json=proposal.source_channels_json,
            ))
    repository.add_neighborhood_members(member_rows)

    run.neighborhood_count = len(plans)
    covered = {plan.anchor_record_id for plan in plans}
    for plan in plans:
        covered.update(record_id for record_id, _proposal in plan.selected)
    proposal_records = {
        record_id for proposal in proposals
        for record_id in (proposal.record_id_1, proposal.record_id_2)
    }
    run.records_in_at_least_one_neighborhood = len(covered)
    run.records_with_proposals_but_no_neighborhood = len(proposal_records - covered)
    run.truncated_neighborhood_count = sum(plan.truncated for plan in plans)
    run.max_candidate_neighbor_count = max(
        (plan.candidate_neighbor_count for plan in plans), default=0
    )
    run.max_included_member_count = max(
        (len(plan.selected) + 1 for plan in plans), default=0
    )
    run.status = DiscoveryRunStatus.COMPLETED.value
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
    loaded = _load_contracts(db, discovery_run_id)
    return _result(*loaded, idempotent=False)


def load_identity_neighborhoods(db, discovery_run_id: int) -> NeighborhoodBuildResult:
    """Load and validate persisted neighborhoods without creating/backfilling them."""
    loaded = _load_contracts(db, discovery_run_id)
    return _result(*loaded, idempotent=True)
