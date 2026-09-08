"""Canonical GF-9 backend reader selected by persisted scan orchestration."""

from __future__ import annotations

from collections import defaultdict

from app.identity_read.adapters import (
    adapt_g2_v1_to_identity_read_snapshot,
    adapt_g2_v2_to_identity_read_snapshot,
)
from app.identity_read.authority import determine_identity_read_authority
from app.identity_read.contracts import (
    G2V1ReadSourceGroup,
    G2V1ReadSourceMember,
    G2V1ReadSourceSnapshot,
    IdentityReadAuthorityContext,
    IdentityReadAuthorityStatus,
    IdentityReadProjectionAvailability,
    IdentityReadProjectionContract,
    IdentityReadSourceRecord,
    VersionedIdentityGroupKey,
)
from app.repositories.identity_read_repository import IdentityReadRepository
from app.services.canonical_record_service import load_scan_record_catalog


class IdentityReadError(RuntimeError):
    pass


class IdentityReadNotReady(IdentityReadError):
    pass


class IdentityReadAuthorityInconsistent(IdentityReadError):
    pass


class IdentityReadGroupNotFound(LookupError):
    pass


class IdentityReadGroupProjectionMismatch(IdentityReadError):
    pass


def _source_reference_id(value: str | None, expected_kind: str) -> int | None:
    if not value:
        return None
    try:
        kind, raw_id = value.split(":", 1)
        run_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    return run_id if kind == expected_kind and run_id > 0 else None


def _source_record(record) -> IdentityReadSourceRecord:
    return IdentityReadSourceRecord(
        record_id=record.record_id,
        scan_id=record.scan_id,
        stable_record_reference=record.record_ref_key,
        source_row_index=record.source_row_index,
        part_no=record.part_no,
        description=record.description,
        normalized_part_no=record.normalized_part_no,
        normalized_description=record.normalized_description,
        contract=record.contract,
        uom=record.uom,
        type_code=record.type_code,
        prime_commodity=record.prime_commodity,
        second_commodity=record.second_commodity,
        accounting_group=record.accounting_group,
        part_product_code=record.part_product_code,
        part_product_family=record.part_product_family,
        product_category_id=record.product_category_id,
        hsn_sac_code=record.hsn_sac_code,
        hazard_code=record.hazard_code,
    )


class IdentityReadService:
    """Loads one validated projection; it never consults current configuration."""

    def __init__(self, db):
        self.db = db
        self.repository = IdentityReadRepository(db)

    def _audit_selection(self, scan_id: int):
        orchestration = self.repository.orchestration_for_scan(scan_id)
        if orchestration is None:
            return None, self.repository.latest_v1_run(scan_id), None, True
        stages = {
            row.stage_id: row
            for row in self.repository.orchestration_stages(orchestration.id)
        }
        v1_id = _source_reference_id(
            getattr(stages.get("G2_V1_COMPATIBILITY_PROJECTION"), "source_run_reference", None),
            "identity_group_projection_run",
        )
        v2_id = _source_reference_id(
            getattr(stages.get("G2_V2_PROJECTION"), "source_run_reference", None),
            "g2_v2_projection_run",
        )
        v1 = self.repository.v1_run(v1_id) if v1_id else None
        v2 = self.repository.v2_run(v2_id) if v2_id else None
        references_valid = not (
            (v1_id and (v1 is None or v1.scan_id != scan_id))
            or (v2_id and (v2 is None or v2.scan_id != scan_id))
        )
        return orchestration, v1, v2, references_valid

    def _availability(self, contract, scan_id, row, provenance=True):
        if row is None:
            return None
        return IdentityReadProjectionAvailability(
            projection_contract=contract,
            scan_id=row.scan_id,
            source_projection_run_id=row.id,
            status=row.status,
            snapshot_valid=True,
            provenance_compatible=provenance and row.scan_id == scan_id,
        )

    def _decision_and_rows(self, scan_id: int):
        orchestration, v1, v2, references_valid = self._audit_selection(scan_id)
        v2_provenance = references_valid
        if v2 is not None:
            resolution = self.repository.resolution_run(v2.source_resolution_run_id)
            v2_provenance = v2_provenance and bool(
                resolution is not None
                and resolution.scan_id == scan_id
                and resolution.status == "COMPLETED"
            )
        context = IdentityReadAuthorityContext(
            scan_id=scan_id,
            orchestration_run_id=orchestration.id if orchestration else None,
            persisted_orchestration_mode=orchestration.mode if orchestration else None,
            orchestration_status=orchestration.status if orchestration else None,
            v1_projection=self._availability(
                IdentityReadProjectionContract.G2_V1, scan_id, v1, references_valid
            ),
            v2_projection=self._availability(
                IdentityReadProjectionContract.G2_V2, scan_id, v2, v2_provenance
            ),
        )
        return determine_identity_read_authority(context), orchestration, v1, v2

    def authority_decision(self, scan_id: int):
        return self._decision_and_rows(scan_id)[0]

    def _raise_decision(self, decision):
        if decision.authority_status == IdentityReadAuthorityStatus.READ_NOT_READY:
            raise IdentityReadNotReady(decision.reason_code)
        raise IdentityReadAuthorityInconsistent(decision.reason_code)

    def _v1_source(self, run, records):
        groups, members = self.repository.v1_groups_and_members(run.id)
        by_group = defaultdict(list)
        for member in members:
            by_group[member.group_snapshot_id].append(member)
        return G2V1ReadSourceSnapshot(
            scan_id=run.scan_id,
            source_projection_run_id=run.id,
            status=run.status,
            canonical_record_count=len(records),
            groups=tuple(G2V1ReadSourceGroup(
                group_reference=group.hypothesis_key,
                scan_id=group.scan_id,
                status=group.group_status,
                members=tuple(G2V1ReadSourceMember(
                    record_id=member.record_snapshot_id,
                    stable_record_reference=member.record_ref_key,
                    member_order=member.member_index,
                ) for member in by_group[group.id]),
                source_group_fingerprint=group.hypothesis_key,
            ) for group in groups),
            source_snapshot_fingerprint=run.evidence_fingerprint,
        )

    def load_identity_read_snapshot(self, scan_id: int):
        decision, orchestration, v1, v2 = self._decision_and_rows(scan_id)
        if decision.authority_status != IdentityReadAuthorityStatus.READY:
            self._raise_decision(decision)
        records = tuple(_source_record(item) for item in load_scan_record_catalog(self.db, scan_id))
        try:
            if decision.projection_contract == IdentityReadProjectionContract.G2_V1:
                return adapt_g2_v1_to_identity_read_snapshot(
                    self._v1_source(v1, records), records,
                    source_orchestration_run_id=orchestration.id if orchestration else None,
                )
            from app.services.g2_v2_projection_service import (
                load_persisted_g2_v2_manifest,
            )

            manifest = load_persisted_g2_v2_manifest(self.db, v2.id)
            return adapt_g2_v2_to_identity_read_snapshot(
                manifest, records, source_projection_run_id=v2.id,
                source_orchestration_run_id=orchestration.id,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise IdentityReadAuthorityInconsistent(
                "SELECTED_PROJECTION_INVALID"
            ) from exc

    def load_identity_read_summary(self, scan_id: int):
        return self.load_identity_read_snapshot(scan_id).summary

    def load_identity_read_group(
        self, scan_id: int, versioned_group_key: VersionedIdentityGroupKey
    ):
        snapshot = self.load_identity_read_snapshot(scan_id)
        return self.group_from_snapshot(scan_id, versioned_group_key, snapshot)

    def group_from_snapshot(self, scan_id, versioned_group_key, snapshot):
        """Resolve an exact opaque target from an already selected snapshot."""
        if versioned_group_key.scan_id != scan_id:
            raise IdentityReadGroupProjectionMismatch("GROUP_KEY_SCAN_MISMATCH")
        if versioned_group_key.projection_contract != snapshot.projection_contract:
            raise IdentityReadGroupProjectionMismatch("GROUP_KEY_PROJECTION_MISMATCH")
        group = next(
            (item for item in snapshot.groups if item.versioned_group_key == versioned_group_key),
            None,
        )
        if group is None:
            raise IdentityReadGroupNotFound("Identity read group not found")
        return group

    def system_group_export_allowed(self, scan_id: int) -> bool:
        decision = self.authority_decision(scan_id)
        if decision.authority_status != IdentityReadAuthorityStatus.READY:
            self._raise_decision(decision)
        return decision.projection_contract == IdentityReadProjectionContract.G2_V1
