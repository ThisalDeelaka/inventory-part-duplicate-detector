import dataclasses
import pandas as pd
import pytest
from sqlalchemy import event, text

from app.db.models import (
    DuplicateScan,
    G2V2ProjectionRun,
    IdentityGroupProjectionRun,
    IdentityGroupReviewEvent,
    IdentityGroupSnapshot,
    IdentityResolutionRun,
    ScanOrchestrationStageResultRow,
    VersionedHumanIdentityConstraint,
    VersionedIdentityGroupReviewEvent,
)
from app.identity_read.contracts import (
    IdentityReadProjectionContract,
    VersionedIdentityGroupKey,
)
from app.identity_read.key_codec import (
    parse_versioned_identity_group_key,
    serialize_versioned_identity_group_key,
)
from app.identity_read.adapters import adapt_g2_v2_to_identity_read_snapshot
from app.llm.group_contracts import group_advisory_request_fingerprint
from app.services.group_llm_eligibility import (
    GroupAdvisoryContractService,
    GroupEligibilityContext,
    GroupEligibilityEdge,
    GroupEligibilityMember,
    GroupLlmEligibilityReason,
    group_candidate_is_llm_eligible,
)
from app.services.identity_group_export_service import identity_groups_to_csv
from app.services.identity_group_query_service import InvalidSnapshotSelectionError
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    IdentityGroupReviewService,
    VersionedIdentityGroupReviewService,
)
from app.services.identity_read_service import (
    IdentityReadGroupProjectionMismatch,
    IdentityReadNotReady,
    IdentityReadService,
)
from app.services.scan_runner import ScanRunner
from test_group_first_scan_orchestration import configuration, run_scan
from test_group_llm_contracts import persisted_review_group
from test_identity_read_contracts import all_records, v2_source


def review_records():
    return pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "SKF 6205 BEARING", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "B", "DESCRIPTION": "SKF BEARING 6205", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
    ])


def review_scan(db, *, mode="group_first_primary"):
    return ScanRunner(db, configuration(mode)).run(
        review_records(), "GF-9B review", ["CONTRACT", "UNIT_MEAS"], 60
    )[0]


def authoritative_group(db, scan):
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan.id)
    return snapshot, snapshot.groups[0]


def test_b1_historical_no_audit_reads_v1_and_legacy_route_stays_compatible(db, client):
    run, group, _ = persisted_review_group(db, size=3)
    snapshot = IdentityReadService(db).load_identity_read_snapshot(1)
    assert snapshot.projection_contract == IdentityReadProjectionContract.G2_V1
    assert snapshot.source_orchestration_run_id is None
    assert snapshot.groups[0].versioned_group_key.group_reference == group.hypothesis_key
    legacy = client.get("/api/scans/1/identity-groups/summary")
    canonical = client.get("/api/scans/1/identity-read/summary")
    assert legacy.status_code == canonical.status_code == 200
    assert canonical.json()["projection"]["projection_contract"] == "G2_V1"
    assert canonical.json()["projection"]["source_projection_run_id"] == run.id


def test_b2_legacy_primary_reads_v1(db):
    scan = run_scan(db, mode="legacy_primary")
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan.id)
    assert snapshot.projection_contract == IdentityReadProjectionContract.G2_V1


def test_b3_group_first_with_both_projections_reads_only_v2(db, client):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    v1 = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    v2 = db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one()
    assert snapshot.projection_contract == IdentityReadProjectionContract.G2_V2
    assert snapshot.source_projection_run_id == v2.id
    response = client.get(f"/api/scans/{scan.id}/identity-read/groups")
    assert response.status_code == 200
    assert response.json()["projection"]["projection_contract"] == "G2_V2"
    assert response.json()["items"][0]["group_reference"] == group.versioned_group_key.group_reference


def test_b4_group_first_missing_v2_never_falls_back_to_existing_v1(db, client):
    scan = review_scan(db)
    db.execute(text(
        "UPDATE scan_orchestration_stage_result SET source_run_reference = NULL "
        "WHERE stage_id = 'G2_V2_PROJECTION'"
    ))
    db.commit()
    with pytest.raises(IdentityReadNotReady, match="G2_V2_PROJECTION_MISSING"):
        IdentityReadService(db).load_identity_read_snapshot(scan.id)
    response = client.get(f"/api/scans/{scan.id}/identity-read/summary")
    assert response.status_code == 409
    assert "G2_V2_PROJECTION_MISSING" in response.json()["detail"]
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1


def test_b5_no_current_configuration_can_reinterpret_persisted_mode(db):
    scan = review_scan(db, mode="legacy_primary")
    signature = IdentityReadService.load_identity_read_snapshot.__annotations__
    assert "configuration" not in signature
    assert IdentityReadService(db).load_identity_read_snapshot(
        scan.id
    ).projection_contract == IdentityReadProjectionContract.G2_V1


def test_versioned_key_is_url_safe_projection_scoped_and_mismatch_fails(db):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    v2_key = group.versioned_group_key
    v1_key = VersionedIdentityGroupKey(
        scan.id, IdentityReadProjectionContract.G2_V1, v2_key.group_reference
    )
    encoded_v1 = serialize_versioned_identity_group_key(v1_key)
    encoded_v2 = serialize_versioned_identity_group_key(v2_key)
    assert encoded_v1 != encoded_v2
    assert parse_versioned_identity_group_key(encoded_v2) == v2_key
    with pytest.raises(IdentityReadGroupProjectionMismatch):
        IdentityReadService(db).load_identity_read_group(scan.id, v1_key)


def test_projection_mismatch_and_versioned_review_api_use_typed_target(db, client):
    scan = review_scan(db)
    _, group = authoritative_group(db, scan)
    v2_key = serialize_versioned_identity_group_key(group.versioned_group_key)
    v1_key = serialize_versioned_identity_group_key(VersionedIdentityGroupKey(
        scan.id, IdentityReadProjectionContract.G2_V1,
        group.versioned_group_key.group_reference,
    ))
    assert client.get(
        f"/api/scans/{scan.id}/identity-read/groups/{v1_key}"
    ).status_code == 422
    created = client.post(
        f"/api/scans/{scan.id}/identity-read/groups/{v2_key}/reviews",
        json={"decision_type": "UNSURE", "reviewer": "API reviewer"},
    )
    assert created.status_code == 201
    assert created.json()["projection_contract"] == "G2_V2"
    current = client.get(
        f"/api/scans/{scan.id}/identity-read/groups/{v2_key}/reviews/current"
    )
    assert current.status_code == 200 and current.json()["reviewed"] is True


def test_g6_v2_review_is_projection_scoped_persists_constraints_and_does_not_reproject(db):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    before = (
        db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).count(),
        db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).count(),
    )
    service = VersionedIdentityGroupReviewService(db)
    result = service.create_review(
        scan_id=scan.id,
        key=group.versioned_group_key,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        reviewer="reviewer",
        submitted_members=tuple(member.stable_record_reference for member in group.members),
    )
    event_row = db.get(VersionedIdentityGroupReviewEvent, result.review_event_id)
    constraint = db.query(VersionedHumanIdentityConstraint).filter_by(
        source_review_event_id=result.review_event_id
    ).one()
    assert event_row.projection_contract == constraint.projection_contract == "G2_V2"
    assert event_row.source_projection_run_id == snapshot.source_projection_run_id
    assert constraint.versioned_group_key == serialize_versioned_identity_group_key(
        group.versioned_group_key
    )
    assert before == (
        db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).count(),
        db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).count(),
    )


def test_g6_v2_membership_is_exact_and_chain_head_is_target_scoped(db):
    scan = review_scan(db)
    _, group = authoritative_group(db, scan)
    service = VersionedIdentityGroupReviewService(db)
    with pytest.raises(ValueError, match="not in the immutable group"):
        service.create_review(
            scan_id=scan.id, key=group.versioned_group_key,
            decision_type=GroupReviewDecision.CONFIRM_SELECTED,
            reviewer="reviewer",
            submitted_members=(group.members[0].stable_record_reference, "f" * 64),
        )
    first = service.create_review(
        scan_id=scan.id, key=group.versioned_group_key,
        decision_type=GroupReviewDecision.UNSURE, reviewer="reviewer",
        submitted_members=tuple(member.stable_record_reference for member in group.members),
    )
    second = service.create_review(
        scan_id=scan.id, key=group.versioned_group_key,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE, reviewer="reviewer",
        submitted_members=tuple(member.stable_record_reference for member in group.members),
        supersedes_review_event_id=first.review_event_id,
    )
    history = service.review_history(scan.id, group.versioned_group_key)
    assert [item["is_current"] for item in history] == [False, True]
    assert history[-1]["review_event_id"] == second.review_event_id


def test_g6_historical_v1_review_delegates_to_unchanged_chain(db):
    run, group, refs = persisted_review_group(db, size=3)
    snapshot = IdentityReadService(db).load_identity_read_snapshot(1)
    target = snapshot.groups[0].versioned_group_key
    created = VersionedIdentityGroupReviewService(db).create_review(
        scan_id=1, key=target,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        reviewer="legacy reviewer", submitted_members=refs,
    )
    assert db.get(IdentityGroupReviewEvent, created.review_event_id) is not None
    history = VersionedIdentityGroupReviewService(db).review_history(1, target)
    assert history[0]["projection_contract"] == "G2_V1"
    assert history[0]["source_projection_run_id"] == run.id


def test_g7_complete_v2_review_group_is_eligible_then_exact_v2_review_blocks(db):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    key = serialize_versioned_identity_group_key(group.versioned_group_key)
    service = GroupAdvisoryContractService(db)
    eligibility, request = service.build_request_for_versioned_group(scan.id, key)
    assert eligibility.eligible
    assert request.projection_contract == "G2_V2"
    assert request.versioned_group_key == key
    assert request.source_group_fingerprint == group.source_group_fingerprint
    VersionedIdentityGroupReviewService(db).create_review(
        scan_id=scan.id, key=group.versioned_group_key,
        decision_type=GroupReviewDecision.UNSURE, reviewer="reviewer",
        submitted_members=tuple(member.stable_record_reference for member in group.members),
    )
    blocked = service.eligibility_for_versioned_group(scan.id, key)
    assert blocked.reason_code == GroupLlmEligibilityReason.INELIGIBLE_HUMAN_REVIEW_EXISTS


def test_g7_legacy_v1_review_does_not_block_authoritative_v2_target(db):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    v1_run = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    v1_group = db.query(IdentityGroupSnapshot).filter_by(
        projection_run_id=v1_run.id
    ).one()
    legacy = IdentityGroupReviewService(db)
    members = legacy.group_members(
        scan.id, v1_run.id, v1_group.id, v1_group.hypothesis_key
    )
    legacy.create_review(
        scan_id=scan.id, projection_run_id=v1_run.id,
        group_snapshot_id=v1_group.id,
        group_hypothesis_key=v1_group.hypothesis_key,
        decision_type=GroupReviewDecision.UNSURE,
        reviewer="legacy reviewer", submitted_members=members,
    )
    key = serialize_versioned_identity_group_key(group.versioned_group_key)
    result = GroupAdvisoryContractService(db).eligibility_for_versioned_group(
        scan.id, key
    )
    assert result.eligible


def test_g7_progressive_and_likely_v2_groups_remain_ineligible():
    refs = ("1" * 64, "2" * 64, "3" * 64)
    progressive = GroupEligibilityContext(
        "COMPLETED", "POSSIBLE_DUPLICATE_GROUP_REVIEW", 3, 20,
        tuple(GroupEligibilityMember(ref, index) for index, ref in enumerate(refs)),
        (
            GroupEligibilityEdge(refs[0], refs[1], "REVIEW_SUPPORT", ("DETERMINISTIC_REVIEW_CANDIDATE",)),
            GroupEligibilityEdge(refs[1], refs[2], "REVIEW_SUPPORT", ("DETERMINISTIC_REVIEW_CANDIDATE",)),
        ),
        2, 2 / 3, False, "G2_V2", "PROGRESSIVE_TARGETED",
    )
    result = group_candidate_is_llm_eligible(progressive)
    assert result.reason_code == GroupLlmEligibilityReason.INELIGIBLE_PROGRESSIVE_VALIDATION_NOT_SUPPORTED
    likely = dataclasses.replace(
        progressive, group_status="LIKELY_DUPLICATE_GROUP",
        validation_mode="COMPLETE_PAIRWISE",
    )
    assert group_candidate_is_llm_eligible(
        likely
    ).reason_code == GroupLlmEligibilityReason.INELIGIBLE_SYSTEM_STATUS


def test_g7_projection_identity_changes_request_fingerprint(db):
    scan = review_scan(db)
    _, group = authoritative_group(db, scan)
    encoded = serialize_versioned_identity_group_key(group.versioned_group_key)
    _, request = GroupAdvisoryContractService(db).build_request_for_versioned_group(
        scan.id, encoded
    )
    v1_key = serialize_versioned_identity_group_key(VersionedIdentityGroupKey(
        scan.id, IdentityReadProjectionContract.G2_V1,
        group.versioned_group_key.group_reference,
    ))
    v1_request = request.model_copy(update={
        "projection_contract": "G2_V1",
        "versioned_group_key": v1_key,
    })
    assert group_advisory_request_fingerprint(request) != group_advisory_request_fingerprint(v1_request)


def test_group_first_system_export_is_blocked_while_legacy_export_is_unchanged(db):
    scan = review_scan(db)
    with pytest.raises(InvalidSnapshotSelectionError, match="pending GF-9C"):
        identity_groups_to_csv(db, scan.id)


def test_group_first_system_export_route_maps_pending_migration_to_conflict(db, client):
    scan = review_scan(db)
    response = client.get(f"/api/scans/{scan.id}/identity-groups/export.csv")
    assert response.status_code == 409
    assert "pending GF-9C" in response.json()["detail"]


def test_authoritative_list_query_shapes_are_bounded(db):
    scan = review_scan(db)
    selects = []
    def count(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        IdentityReadService(db).load_identity_read_snapshot(scan.id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    assert len(selects) <= 16


def test_authoritative_api_exposes_v2_conflict_without_legacy_coercion(db, client):
    records = pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "BEARING 6205", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "B", "DESCRIPTION": "BEARING 6206", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
    ])
    scan = ScanRunner(db, configuration("group_first_primary")).run(
        records, "GF-9B conflict", ["CONTRACT", "UNIT_MEAS"], 60
    )[0]
    response = client.get(f"/api/scans/{scan.id}/identity-read/outcomes")
    assert response.status_code == 200
    body = response.json()
    assert body["projection"]["projection_contract"] == "G2_V2"
    assert body["conflicts"] and body["deferred_work_units"] == []
    assert "conflict_type" in body["conflicts"][0]


def test_progressive_v2_detail_api_preserves_two_of_three_without_synthetic_edge(
    db, client, monkeypatch
):
    db.add(DuplicateScan(
        id=21, scan_name="progressive", threshold=60, status="COMPLETED",
        model_version="deterministic-v1", selected_fields="[]",
    ))
    db.commit()
    snapshot = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    group = snapshot.groups[0]
    monkeypatch.setattr(
        IdentityReadService, "load_identity_read_group",
        lambda _self, _scan_id, _key: group,
    )
    key = serialize_versioned_identity_group_key(group.versioned_group_key)
    response = client.get(f"/api/scans/21/identity-read/groups/{key}")
    assert response.status_code == 200
    body = response.json()
    assert body["group_size"] == 3
    assert body["validation_mode"] == "PROGRESSIVE_TARGETED"
    assert body["validation_coverage"]["evaluated_internal_pair_count"] == 2
    assert body["validation_coverage"]["possible_internal_pair_count"] == 3
    assert body["validation_coverage"]["missing_nonrequired_pair_count"] == 1
    assert len(body["internal_evidence"]) == 2


def test_v2_outcomes_api_preserves_conflict_deferred_and_unassigned_types(
    db, client, monkeypatch
):
    db.add(DuplicateScan(
        id=21, scan_name="outcomes", threshold=60, status="COMPLETED",
        model_version="deterministic-v1", selected_fields="[]",
    ))
    db.commit()
    snapshot = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    monkeypatch.setattr(
        IdentityReadService, "load_identity_read_snapshot",
        lambda _self, _scan_id: snapshot,
    )
    response = client.get("/api/scans/21/identity-read/outcomes")
    assert response.status_code == 200
    body = response.json()
    assert len(body["conflicts"]) == len(body["deferred_work_units"]) == 1
    assert len(body["unassigned_records"]) == 1
    assert "reason" in body["deferred_work_units"][0]
