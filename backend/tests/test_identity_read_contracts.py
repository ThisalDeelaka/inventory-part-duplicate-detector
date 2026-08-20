from __future__ import annotations

import inspect
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    IdentityReadValidationMode,
    VersionedIdentityGroupKey,
)
from app.identity_read.validation import (
    IdentityReadValidationError,
    validate_identity_read_snapshot,
)


def record(record_id, row, *, scan_id=21, part_no=None):
    return IdentityReadSourceRecord(
        record_id=record_id,
        scan_id=scan_id,
        stable_record_reference=f"record-{row}",
        source_row_index=row,
        part_no=part_no or f"P-{row}",
        description="same physical item",
        contract="SITE-A",
        uom="EA",
    )


def availability(contract, *, status="COMPLETED", valid=True, scan_id=21, compatible=True):
    return IdentityReadProjectionAvailability(
        projection_contract=contract,
        scan_id=scan_id,
        source_projection_run_id=101 if contract == IdentityReadProjectionContract.G2_V1 else 202,
        status=status,
        snapshot_valid=valid,
        provenance_compatible=compatible,
    )


def context(*, mode=None, status=None, run_id=None, v1=None, v2=None):
    return IdentityReadAuthorityContext(
        scan_id=21,
        orchestration_run_id=run_id,
        persisted_orchestration_mode=mode,
        orchestration_status=status,
        v1_projection=v1,
        v2_projection=v2,
    )


def v1_source(groups=None, records=4):
    group = G2V1ReadSourceGroup(
        group_reference="group-X",
        scan_id=21,
        status="LIKELY_DUPLICATE_GROUP",
        members=tuple(
            G2V1ReadSourceMember(index, f"record-{index - 1}", index - 1)
            for index in (1, 2, 3)
        ),
        source_group_fingerprint="v1-group-source",
    )
    return G2V1ReadSourceSnapshot(
        scan_id=21,
        source_projection_run_id=101,
        status="COMPLETED",
        canonical_record_count=records,
        groups=tuple(groups) if groups is not None else (group,),
        source_snapshot_fingerprint="v1-snapshot-source",
    )


@dataclass(frozen=True)
class FakeEvidence:
    stable_record_reference_1: str
    stable_record_reference_2: str
    evidence_fingerprint: str


def v2_source(*, groups=None, conflicts=None, deferred=None, unassigned=((6, "record-5"),)):
    coverage = SimpleNamespace(
        validation_mode="PROGRESSIVE_TARGETED",
        member_count=3,
        possible_internal_pair_count=3,
        evaluated_internal_pair_count=2,
        required_validation_evidence_count=2,
        strong_support_count=1,
        review_support_count=1,
        non_groupable_count=0,
        cannot_link_count=0,
        missing_nonrequired_pair_count=1,
        targeted_evidence_count=1,
        proposal_evidence_count=1,
    )
    group = SimpleNamespace(
        group_reference="group-X",
        scan_id=21,
        status="POSSIBLE_DUPLICATE_GROUP_REVIEW",
        validation_mode="PROGRESSIVE_TARGETED",
        member_count=3,
        members=tuple(
            SimpleNamespace(record_id=index, stable_record_reference=f"record-{index - 1}", member_order=index - 1)
            for index in (1, 2, 3)
        ),
        internal_evidence=(
            FakeEvidence("record-0", "record-1", "edge-a"),
            FakeEvidence("record-1", "record-2", "edge-b"),
        ),
        validation_coverage=coverage,
        group_evidence_summary={"evaluated_pair_count": 2, "possible_pair_count": 3},
        bridge_risk_summary={"unresolved": True},
        genericity_risk_summary={"review_only_support": True},
        missing_evidence_summary={"missing_pairs": ((1, 3),)},
        group_fingerprint="v2-group-source",
    )
    conflict = SimpleNamespace(
        conflict_reference="conflict-A", scan_id=21,
        conflict_type="PROTECTED_CANNOT_LINK",
        involved_record_ids=(3, 4), involved_record_references=("record-2", "record-3"),
        protected_evidence_references=("protected-1",),
        source_neighborhood_references=("neighborhood-1",), summary="protected split",
        conflict_fingerprint="v2-conflict-source",
    )
    work = SimpleNamespace(
        deferred_reference="deferred-A", scan_id=21,
        reason="UNRESOLVED_OWNERSHIP_AMBIGUITY", record_ids=(5,),
        record_references=("record-4",), unfinished_evidence_summary="one check remains",
        source_neighborhood_references=("neighborhood-2",),
        deferred_fingerprint="v2-deferred-source",
    )
    groups = tuple(groups) if groups is not None else (group,)
    conflicts = tuple(conflicts) if conflicts is not None else (conflict,)
    deferred = tuple(deferred) if deferred is not None else (work,)
    return SimpleNamespace(
        scan_id=21,
        source_resolution_run_id=77,
        groups=groups,
        conflicts=conflicts,
        deferred_work_units=deferred,
        unassigned_record_ids=tuple(item[0] for item in unassigned),
        unassigned_record_references=tuple(item[1] for item in unassigned),
        canonical_record_count=6,
        accepted_group_count=len(groups),
        likely_group_count=sum(item.status == "LIKELY_DUPLICATE_GROUP" for item in groups),
        review_group_count=sum(item.status == "POSSIBLE_DUPLICATE_GROUP_REVIEW" for item in groups),
        conflict_count=len(conflicts), deferred_count=len(deferred),
        unassigned_record_count=len(unassigned), manifest_fingerprint="v2-manifest-source",
    )


def all_records(count=6):
    return tuple(record(index + 1, index) for index in range(count))


def test_r1_historical_no_audit_selects_v1():
    decision = determine_identity_read_authority(context(v1=availability(IdentityReadProjectionContract.G2_V1)))
    assert decision.authority_status == IdentityReadAuthorityStatus.READY
    assert decision.projection_contract == IdentityReadProjectionContract.G2_V1


def test_r2_completed_legacy_primary_selects_v1():
    decision = determine_identity_read_authority(context(
        mode="legacy_primary", status="COMPLETED", run_id=8,
        v1=availability(IdentityReadProjectionContract.G2_V1),
    ))
    assert decision.projection_contract == IdentityReadProjectionContract.G2_V1


def test_r3_completed_group_first_selects_valid_v2():
    decision = determine_identity_read_authority(context(
        mode="group_first_primary", status="COMPLETED", run_id=9,
        v2=availability(IdentityReadProjectionContract.G2_V2),
    ))
    assert decision.authority_status == IdentityReadAuthorityStatus.READY
    assert decision.projection_contract == IdentityReadProjectionContract.G2_V2


@pytest.mark.parametrize("v2", [None, availability(IdentityReadProjectionContract.G2_V2, status="FAILED")])
def test_r4_group_first_missing_or_failed_v2_is_not_ready_without_fallback(v2):
    decision = determine_identity_read_authority(context(
        mode="group_first_primary", status="COMPLETED", run_id=9,
        v1=availability(IdentityReadProjectionContract.G2_V1), v2=v2,
    ))
    assert decision.authority_status == IdentityReadAuthorityStatus.READ_NOT_READY
    assert decision.projection_contract is None


def test_r5_current_config_cannot_reinterpret_persisted_scan():
    assert "current" not in inspect.signature(determine_identity_read_authority).parameters
    legacy = determine_identity_read_authority(context(
        mode="legacy_primary", status="COMPLETED", run_id=8,
        v1=availability(IdentityReadProjectionContract.G2_V1),
        v2=availability(IdentityReadProjectionContract.G2_V2),
    ))
    group_first = determine_identity_read_authority(context(
        mode="group_first_primary", status="COMPLETED", run_id=9,
        v1=availability(IdentityReadProjectionContract.G2_V1),
        v2=availability(IdentityReadProjectionContract.G2_V2),
    ))
    assert (legacy.projection_contract, group_first.projection_contract) == (
        IdentityReadProjectionContract.G2_V1, IdentityReadProjectionContract.G2_V2
    )


def test_r6_v1_adapter_preserves_groups_members_status_and_complete_pairwise():
    snapshot = adapt_g2_v1_to_identity_read_snapshot(v1_source(), all_records(4))
    group = snapshot.groups[0]
    assert group.status.value == "LIKELY_DUPLICATE_GROUP"
    assert tuple(item.stable_record_reference for item in group.members) == ("record-0", "record-1", "record-2")
    assert group.validation_mode == IdentityReadValidationMode.LEGACY_COMPLETE_PAIRWISE
    assert group.validation_coverage.evaluated_internal_pair_count == 3


def test_r7_v2_adapter_preserves_all_outcomes_and_progressive_coverage():
    snapshot = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    group = snapshot.groups[0]
    assert group.validation_mode == IdentityReadValidationMode.PROGRESSIVE_TARGETED
    assert (group.validation_coverage.evaluated_internal_pair_count,
            group.validation_coverage.possible_internal_pair_count,
            group.validation_coverage.missing_nonrequired_pair_count) == (2, 3, 1)
    assert len(group.internal_evidence) == 2
    assert (snapshot.conflict_count, snapshot.deferred_count, snapshot.unassigned_count) == (1, 1, 1)
    assert snapshot.source_resolution_run_id == 77


def test_r8_duplicate_valued_rows_remain_distinct():
    records = tuple(record(index + 1, index, part_no="SAME") for index in range(4))
    snapshot = adapt_g2_v1_to_identity_read_snapshot(v1_source(), records)
    assert len({member.record_id for member in snapshot.groups[0].members}) == 3
    assert len({member.source_row_index for member in snapshot.groups[0].members}) == 3


def test_r9_to_r11_versioned_keys_scope_group_review_and_advisory_identity():
    v1_key = VersionedIdentityGroupKey(21, IdentityReadProjectionContract.G2_V1, "group-X")
    v2_key = VersionedIdentityGroupKey(21, IdentityReadProjectionContract.G2_V2, "group-X")
    assert v1_key != v2_key
    review_targets = {v1_key: "review"}
    advisory_targets = {v1_key: "advisory"}
    assert v2_key not in review_targets and v2_key not in advisory_targets


def test_r12_shuffled_source_collections_are_deterministic():
    source = v2_source()
    shuffled_group = SimpleNamespace(**{
        **source.groups[0].__dict__,
        "members": tuple(reversed(source.groups[0].members)),
        "internal_evidence": tuple(reversed(source.groups[0].internal_evidence)),
    })
    shuffled = v2_source(groups=(shuffled_group,))
    left = adapt_g2_v2_to_identity_read_snapshot(source, all_records(), source_projection_run_id=202, source_orchestration_run_id=9)
    right = adapt_g2_v2_to_identity_read_snapshot(shuffled, tuple(reversed(all_records())), source_projection_run_id=999, source_orchestration_run_id=999)
    assert left.snapshot_fingerprint == right.snapshot_fingerprint
    assert left.groups[0].read_group_fingerprint == right.groups[0].read_group_fingerprint


def test_r13_pure_package_has_no_pair_g1_db_repository_or_provider_dependency():
    root = Path(__file__).parents[1] / "app" / "identity_read"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = ("sqlalchemy", "app.db", "repositories", "DuplicateCandidate", "G1", "provider", "llm")
    assert not any(term in source for term in forbidden)


def test_r14_historical_v1_invents_no_v2_outcomes_or_provenance():
    snapshot = adapt_g2_v1_to_identity_read_snapshot(v1_source(), all_records(4))
    group = snapshot.groups[0]
    assert snapshot.conflicts == snapshot.deferred_work_units == ()
    assert snapshot.source_resolution_run_id is None
    assert group.internal_evidence == ()
    assert group.group_evidence_summary is None


def test_running_and_failed_orchestration_are_not_ready():
    for status in ("RUNNING", "FAILED"):
        decision = determine_identity_read_authority(context(
            mode="group_first_primary", status=status, run_id=9,
            v1=availability(IdentityReadProjectionContract.G2_V1),
            v2=availability(IdentityReadProjectionContract.G2_V2),
        ))
        assert decision.authority_status == IdentityReadAuthorityStatus.READ_NOT_READY
        assert decision.projection_contract is None


@pytest.mark.parametrize("change", [
    lambda source: replace(source, canonical_record_count=99),
    lambda source: replace(source, groups=(replace(source.groups[0], scan_id=22),)),
    lambda source: replace(source, groups=(replace(source.groups[0], members=source.groups[0].members[:1]),)),
])
def test_v1_adapter_rejects_count_cross_scan_and_singleton_drift(change):
    with pytest.raises((ValueError, IdentityReadValidationError)):
        adapt_g2_v1_to_identity_read_snapshot(change(v1_source()), all_records(4))


def test_snapshot_validator_rejects_fingerprint_mismatch():
    snapshot = adapt_g2_v1_to_identity_read_snapshot(v1_source(), all_records(4))
    with pytest.raises(IdentityReadValidationError, match="fingerprint mismatch"):
        validate_identity_read_snapshot(replace(snapshot, snapshot_fingerprint="0" * 64))


def test_group_first_invalid_or_cross_scan_v2_is_inconsistent_not_v1():
    for v2 in (
        availability(IdentityReadProjectionContract.G2_V2, valid=False),
        availability(IdentityReadProjectionContract.G2_V2, scan_id=22),
        availability(IdentityReadProjectionContract.G2_V2, compatible=False),
    ):
        decision = determine_identity_read_authority(context(
            mode="group_first_primary", status="COMPLETED", run_id=9,
            v1=availability(IdentityReadProjectionContract.G2_V1), v2=v2,
        ))
        assert decision.authority_status == IdentityReadAuthorityStatus.READ_AUTHORITY_INCONSISTENT
        assert decision.projection_contract is None
