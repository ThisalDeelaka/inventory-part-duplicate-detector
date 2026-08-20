import csv
import dataclasses
import io

import pytest
from sqlalchemy import event, text

from app.db.models import DuplicateScan, IdentityGroupProjectionRun, IdentityGroupSnapshot
from app.identity_read.adapters import adapt_g2_v2_to_identity_read_snapshot
from app.identity_read.contracts import (
    IdentityReadDeferredWork,
    IdentityReadProjectionContract,
    IdentityReadSummary,
    IdentityReadValidationMode,
    VersionedIdentityGroupKey,
)
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    IdentityGroupReviewService,
    VersionedIdentityGroupReviewService,
)
from app.services.identity_read_export_service import SYSTEM_GROUP_EXPORT_FIELDS
from app.services.identity_read_service import IdentityReadService
from test_group_first_backend_inversion import authoritative_group, review_scan
from test_group_llm_contracts import persisted_review_group
from test_identity_read_contracts import all_records, v2_source


def rows(response):
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.text)))


def add_scan(db, scan_id=21):
    db.add(DuplicateScan(
        id=scan_id, scan_name="GF-9C", threshold=60, status="COMPLETED",
        model_version="deterministic-v1", selected_fields="[]",
    ))
    db.commit()


def test_e1_historical_authoritative_system_export_uses_v1_adapter(db, client):
    run, group, refs = persisted_review_group(db, size=3)
    exported = rows(client.get("/api/scans/1/identity-read/system-groups/export.csv"))
    assert len(exported) == 3
    assert {row["projection_contract"] for row in exported} == {"G2_V1"}
    assert {row["source_projection_run_id"] for row in exported} == {str(run.id)}
    assert {row["group_reference"] for row in exported} == {group.hypothesis_key}
    assert {row["stable_record_reference"] for row in exported} == set(refs)
    assert next(csv.reader(io.StringIO(client.get(
        "/api/scans/1/identity-read/system-groups/export.csv"
    ).text))) == SYSTEM_GROUP_EXPORT_FIELDS


@pytest.mark.parametrize("decision", [
    GroupReviewDecision.KEEP_ALL_SEPARATE,
    GroupReviewDecision.UNSURE,
])
def test_e7_historical_v1_nonaffirmative_review_exports_no_operational_set(
    db, client, decision
):
    run, group, refs = persisted_review_group(db, size=3)
    IdentityGroupReviewService(db).create_review(
        scan_id=1, projection_run_id=run.id, group_snapshot_id=group.id,
        group_hypothesis_key=group.hypothesis_key, decision_type=decision,
        reviewer="legacy", submitted_members=refs,
    )
    assert rows(client.get(
        "/api/scans/1/identity-read/reviewed-identities/export.csv"
    )) == []


def test_e2_e3_group_first_system_export_uses_v2_not_compatibility_v1(db, client):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1
    exported = rows(client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.csv"
    ))
    assert len(exported) == group.member_count
    assert {row["projection_contract"] for row in exported} == {"G2_V2"}
    assert {row["source_projection_run_id"] for row in exported} == {
        str(snapshot.source_projection_run_id)
    }
    assert all(row["group_key"].startswith("igk1.") for row in exported)
    assert all("part_a" not in row and "part_b" not in row for row in exported)


def test_e4_progressive_export_has_three_members_and_truthful_two_of_three(
    db, client, monkeypatch
):
    add_scan(db)
    snapshot = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    monkeypatch.setattr(
        IdentityReadService, "load_identity_read_snapshot",
        lambda _self, _scan_id: snapshot,
    )
    exported = rows(client.get("/api/scans/21/identity-read/system-groups/export.csv"))
    assert len(exported) == 3
    assert {row["validation_mode"] for row in exported} == {"PROGRESSIVE_TARGETED"}
    assert {row["evaluated_relationship_count"] for row in exported} == {"2"}
    assert {row["possible_relationship_count"] for row in exported} == {"3"}
    assert {row["missing_nonrequired_relationship_count"] for row in exported} == {"1"}


def test_e5_e6_conflict_and_deferred_are_separate_typed_exports(
    db, client, monkeypatch
):
    add_scan(db)
    snapshot = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    monkeypatch.setattr(
        IdentityReadService, "load_identity_read_snapshot",
        lambda _self, _scan_id: snapshot,
    )
    conflict = rows(client.get("/api/scans/21/identity-read/conflicts/export.csv"))
    deferred = rows(client.get("/api/scans/21/identity-read/deferred/export.csv"))
    assert conflict and deferred
    assert all(row["conflict_type"] for row in conflict)
    assert all(row["deferred_reason"] for row in deferred)
    assert all("deferred_reason" not in row for row in conflict)
    assert all("conflict_type" not in row for row in deferred)


def test_e8_e9_v2_reviewed_export_uses_only_exact_v2_review_chain(db, client):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    legacy_run = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    legacy_group = db.query(IdentityGroupSnapshot).filter_by(
        projection_run_id=legacy_run.id
    ).one()
    legacy = IdentityGroupReviewService(db)
    legacy_members = legacy.group_members(
        scan.id, legacy_run.id, legacy_group.id, legacy_group.hypothesis_key
    )
    legacy.create_review(
        scan_id=scan.id, projection_run_id=legacy_run.id,
        group_snapshot_id=legacy_group.id,
        group_hypothesis_key=legacy_group.hypothesis_key,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        reviewer="legacy", submitted_members=legacy_members,
    )
    assert rows(client.get(
        f"/api/scans/{scan.id}/identity-read/reviewed-identities/export.csv"
    )) == []
    refs = tuple(member.stable_record_reference for member in group.members)
    VersionedIdentityGroupReviewService(db).create_review(
        scan_id=scan.id, key=group.versioned_group_key,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        reviewer="v2", submitted_members=refs,
    )
    exported = rows(client.get(
        f"/api/scans/{scan.id}/identity-read/reviewed-identities/export.csv"
    ))
    assert len(exported) == len(refs)
    assert {row["projection_contract"] for row in exported} == {"G2_V2"}
    assert {row["reviewer"] for row in exported} == {"v2"}


def test_group_list_review_state_cannot_leak_from_v1_to_v2(db, client):
    scan = review_scan(db)
    _, group = authoritative_group(db, scan)
    legacy_run = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    legacy_group = db.query(IdentityGroupSnapshot).filter_by(
        projection_run_id=legacy_run.id
    ).one()
    legacy = IdentityGroupReviewService(db)
    legacy_refs = legacy.group_members(
        scan.id, legacy_run.id, legacy_group.id, legacy_group.hypothesis_key
    )
    legacy.create_review(
        scan_id=scan.id, projection_run_id=legacy_run.id,
        group_snapshot_id=legacy_group.id,
        group_hypothesis_key=legacy_group.hypothesis_key,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        reviewer="legacy", submitted_members=legacy_refs,
    )
    before = client.get(f"/api/scans/{scan.id}/identity-read/groups").json()
    assert before["items"][0]["review_state"]["reviewed"] is False
    refs = tuple(member.stable_record_reference for member in group.members)
    VersionedIdentityGroupReviewService(db).create_review(
        scan_id=scan.id, key=group.versioned_group_key,
        decision_type=GroupReviewDecision.UNSURE,
        reviewer="v2", submitted_members=refs,
    )
    after = client.get(f"/api/scans/{scan.id}/identity-read/groups").json()
    assert after["items"][0]["review_state"]["reviewed"] is True
    assert after["items"][0]["review_state"]["reviewer"] == "v2"


@pytest.mark.parametrize("decision", [
    GroupReviewDecision.KEEP_ALL_SEPARATE,
    GroupReviewDecision.UNSURE,
])
def test_e10_separate_and_unsure_create_no_operational_identity_set(
    db, client, decision
):
    scan = review_scan(db)
    _, group = authoritative_group(db, scan)
    refs = tuple(member.stable_record_reference for member in group.members)
    VersionedIdentityGroupReviewService(db).create_review(
        scan_id=scan.id, key=group.versioned_group_key,
        decision_type=decision, reviewer="v2", submitted_members=refs,
    )
    assert rows(client.get(
        f"/api/scans/{scan.id}/identity-read/reviewed-identities/export.csv"
    )) == []


def test_e12_missing_v2_fails_all_canonical_exports_without_v1_fallback(db, client):
    scan = review_scan(db)
    db.execute(text(
        "UPDATE scan_orchestration_stage_result SET source_run_reference = NULL "
        "WHERE orchestration_run_id = (SELECT id FROM scan_orchestration_run "
        "WHERE scan_id = :scan_id) AND stage_id = 'G2_V2_PROJECTION'"
    ), {"scan_id": scan.id})
    db.commit()
    for suffix in (
        "system-groups/export.csv", "reviewed-identities/export.csv",
        "conflicts/export.csv", "deferred/export.csv",
    ):
        response = client.get(f"/api/scans/{scan.id}/identity-read/{suffix}")
        assert response.status_code == 409
        assert "G2_V2_PROJECTION_MISSING" in response.json()["detail"]


def test_e13_ready_zero_group_snapshot_exports_valid_empty_csv(
    db, client, monkeypatch
):
    add_scan(db)
    original = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    empty = dataclasses.replace(original, groups=(), group_count=0,
                                likely_group_count=0, review_group_count=0)
    monkeypatch.setattr(
        IdentityReadService, "load_identity_read_snapshot",
        lambda _self, _scan_id: empty,
    )
    response = client.get("/api/scans/21/identity-read/system-groups/export.csv")
    assert response.status_code == 200
    assert rows(response) == []


def test_e14_legacy_pair_export_is_unchanged_and_explicitly_separate(db, client):
    scan = review_scan(db)
    before = client.get(f"/api/scans/{scan.id}/export").content
    client.get(f"/api/scans/{scan.id}/identity-read/system-groups/export.csv")
    assert client.get(f"/api/scans/{scan.id}/export").content == before


def test_graduation_v1_abc_disagrees_with_authoritative_v2_ab_and_c_deferred(
    db, client, monkeypatch
):
    run, legacy_group, refs = persisted_review_group(db, size=3)
    source = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(conflicts=(), deferred=(), unassigned=()), all_records(),
        source_projection_run_id=202, source_orchestration_run_id=9,
    )
    original = source.groups[0]
    coverage = dataclasses.replace(
        original.validation_coverage,
        validation_mode=IdentityReadValidationMode.COMPLETE_PAIRWISE,
        member_count=2, possible_internal_pair_count=1,
        evaluated_internal_pair_count=1, required_validation_evidence_count=1,
        strong_support_count=1, review_support_count=0,
        missing_nonrequired_pair_count=0, targeted_evidence_count=0,
    )
    v2_group = dataclasses.replace(
        original,
        versioned_group_key=VersionedIdentityGroupKey(
            1, IdentityReadProjectionContract.G2_V2, "authoritative-AB"
        ),
        member_count=2, members=original.members[:2],
        validation_mode=IdentityReadValidationMode.COMPLETE_PAIRWISE,
        validation_coverage=coverage, internal_evidence=original.internal_evidence[:1],
    )
    deferred = IdentityReadDeferredWork(
        scan_id=1, deferred_reference="deferred-C", reason="INSUFFICIENT_REQUIRED_EVIDENCE",
        record_ids=(original.members[2].record_id,),
        record_references=(original.members[2].stable_record_reference,),
        unfinished_evidence_summary="C requires more evidence",
        source_neighborhood_references=("neighborhood-ABC",),
        source_deferred_fingerprint="deferred-C-source",
        read_deferred_fingerprint="deferred-C-read",
    )
    summary = IdentityReadSummary(6, 1, 0, 1, 0, 1, 1)
    authoritative = dataclasses.replace(
        source, scan_id=1, groups=(v2_group,), conflicts=(),
        deferred_work_units=(deferred,),
        unassigned_records=source.unassigned_records[:1], group_count=1,
        likely_group_count=0, review_group_count=1, conflict_count=0,
        deferred_count=1, unassigned_count=1, summary=summary,
    )
    monkeypatch.setattr(
        IdentityReadService, "load_identity_read_snapshot",
        lambda _self, _scan_id: authoritative,
    )
    exported = rows(client.get("/api/scans/1/identity-read/system-groups/export.csv"))
    deferred_rows = rows(client.get("/api/scans/1/identity-read/deferred/export.csv"))
    assert {row["stable_record_reference"] for row in exported} == {
        item.stable_record_reference for item in v2_group.members
    }
    assert len(exported) == 2 and len(deferred_rows) == 1
    assert {row["group_reference"] for row in exported} == {"authoritative-AB"}
    assert legacy_group.hypothesis_key not in {row["group_reference"] for row in exported}
    assert len(refs) == 3 and run.id > 0


def test_authoritative_export_query_shapes_are_bounded(db, client):
    scan = review_scan(db)
    _, group = authoritative_group(db, scan)
    refs = tuple(member.stable_record_reference for member in group.members)
    VersionedIdentityGroupReviewService(db).create_review(
        scan_id=scan.id, key=group.versioned_group_key,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        reviewer="query-shape", submitted_members=refs,
    )
    selects = []

    def count(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        assert client.get(
            f"/api/scans/{scan.id}/identity-read/system-groups/export.csv"
        ).status_code == 200
        system_count = len(selects)
        selects.clear()
        assert client.get(
            f"/api/scans/{scan.id}/identity-read/reviewed-identities/export.csv"
        ).status_code == 200
        reviewed_count = len(selects)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    assert system_count <= 16
    assert reviewed_count <= 18
    print(f"GF9C_SELECT_COUNTS system={system_count} reviewed={reviewed_count}")
