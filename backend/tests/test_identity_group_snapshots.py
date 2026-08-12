import random
from dataclasses import replace

import pytest
from sqlalchemy import create_engine, event, inspect

from app.db.models import (
    DuplicateCandidate,
    DuplicateScan,
    IdentityFamilyDiagnosticMemberSnapshot,
    IdentityFamilyDiagnosticSnapshot,
    IdentityGroupEdgeSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.db.migrations import ensure_identity_group_snapshot_tables
from app.engine.identity_edge import IdentityEdgeClass
from app.engine.scoring import score_candidate
from app.services.identity_group_projection import (
    FamilyDiagnosticStatus,
    project_identity_groups,
)
from app.services.identity_group_snapshot_service import (
    load_identity_group_snapshot_manifest,
    persist_identity_group_projection,
)


def record(name, description="Precision hydraulic valve", uom="PCS"):
    return {
        "CONTRACT": "S1", "PART_NO": name, "DESCRIPTION": description,
        "UNIT_MEAS": uom, "PRODUCT_CATEGORY_ID": "", "HSN_SAC_CODE": "",
    }


def pair(left, right, edge="review", candidate_id=None, **extra):
    status, decision = {
        "strong": ("LIKELY_DUPLICATE", "ALLOW"),
        "review": ("POSSIBLE_DUPLICATE_REVIEW", "ALLOW"),
    }[edge]
    return {
        "id": candidate_id,
        "contract_a": left["CONTRACT"], "part_no_a": left["PART_NO"],
        "description_a": left["DESCRIPTION"],
        "contract_b": right["CONTRACT"], "part_no_b": right["PART_NO"],
        "description_b": right["DESCRIPTION"],
        "business_status": status, "rule_decision": decision,
        "rejection_reason": "", "critical_mismatches": [],
        "similarity_score": 92.0, **extra,
    }


def scored_pair(left, right, **extra):
    scored = score_candidate(
        left, right, ["CONTRACT", "UNIT_MEAS"], allow_uom_mapping_review=True
    )
    return {**pair(left, right), **scored, **extra}


def scan(db, scan_id=7):
    row = DuplicateScan(
        id=scan_id, scan_name=f"scan-{scan_id}", threshold=80, status="COMPLETED",
        total_records=0, model_version="deterministic-v1", scan_mode="SAME_SITE_DUPLICATE",
    )
    db.add(row)
    db.commit()
    return row


def project(scan_id, records, candidates, exclusions=(), feedback=None):
    return project_identity_groups(
        scan_id=scan_id, records=records, candidates=candidates, exclusions=exclusions,
        feedback_by_candidate_id=feedback or {},
        selected_fields=["CONTRACT", "UNIT_MEAS"],
    )


def persist(db, scan_row, records, candidates, projection, exclusions=(), feedback=None):
    return persist_identity_group_projection(
        db, scan=scan_row, records=records, candidates=candidates,
        exclusions=exclusions, feedback_by_candidate_id=feedback or {},
        selected_fields=["CONTRACT", "UNIT_MEAS"], projection=projection,
    )


def test_persists_size_two_likely_group_and_reloads_without_projection(db):
    scan_row = scan(db)
    items = [record("A"), record("B")]
    candidates = [pair(*items, edge="strong")]
    result = persist(db, scan_row, items, candidates, project(7, items, candidates))
    assert (result.group_snapshots, result.member_snapshots, result.edge_snapshots) == (1, 2, 1)
    manifest = load_identity_group_snapshot_manifest(db, result.projection_run_id)
    assert manifest["run"]["metrics"]["accepted_groups"] == 1
    assert manifest["groups"][0]["status"] == "LIKELY_DUPLICATE_GROUP"
    assert len(manifest["groups"][0]["members"]) == 2
    projected_edge = project(7, items, candidates).groups[0].internal_edges[0]
    persisted_edge = manifest["edges"][0]
    assert (
        persisted_edge["left_record_ref_key"], persisted_edge["right_record_ref_key"],
        persisted_edge["edge_class"], persisted_edge["reason_codes"],
    ) == (
        projected_edge.left_ref, projected_edge.right_ref,
        projected_edge.edge_class.value, list(projected_edge.reason_codes),
    )


def test_persists_size_seven_with_all_twenty_one_edges_in_stable_order(db):
    scan_row = scan(db)
    items = [record(str(index)) for index in range(7)]
    candidates = [pair(items[i], items[j], "strong") for i in range(7) for j in range(i + 1, 7)]
    projection = project(7, items, candidates)
    result = persist(db, scan_row, items, candidates, projection)
    members = db.query(IdentityGroupMemberSnapshot).order_by(IdentityGroupMemberSnapshot.member_index).all()
    assert len(members) == 7
    assert [row.record_ref_key for row in members] == [member.key for member in projection.groups[0].members]
    assert result.edge_snapshots == 21


def test_review_status_and_uom_summary_are_persisted_without_identity_reinterpretation(db):
    scan_row = scan(db)
    items = [record("A", uom="l"), record("B", uom="PCS")]
    candidates = [pair(*items)]
    persist(db, scan_row, items, candidates, project(7, items, candidates))
    group = db.query(IdentityGroupSnapshot).one()
    assert group.group_status == "POSSIBLE_DUPLICATE_GROUP_REVIEW"
    assert group.different_basis_pair_count == 1


def test_conflict_is_diagnostic_with_cannot_link_and_human_authority(db):
    scan_row = scan(db)
    a, b, c = [record(name) for name in "ABC"]
    candidates = [pair(a, b, candidate_id=1), pair(b, c, candidate_id=2), pair(a, c, "strong", candidate_id=3)]
    feedback = {3: {"user_decision": "NOT_DUPLICATE"}}
    projection = project(7, [a, b, c], candidates, feedback=feedback)
    result = persist(db, scan_row, [a, b, c], candidates, projection, feedback=feedback)
    assert result.group_snapshots == 0
    diagnostic = db.query(IdentityFamilyDiagnosticSnapshot).one()
    edge = db.query(IdentityGroupEdgeSnapshot).one()
    assert diagnostic.diagnostic_status == "CONFLICTING_FAMILY"
    assert db.query(IdentityFamilyDiagnosticMemberSnapshot).count() == 3
    assert (edge.edge_class, edge.evidence_source) == ("CANNOT_LINK", "HUMAN_FEEDBACK")


def test_oversized_family_persists_all_members_without_edges_or_truncation(db):
    scan_row = scan(db)
    items = [record(f"P{index}") for index in range(21)]
    candidates = [pair(items[index], items[index + 1]) for index in range(20)]
    projection = project(7, items, candidates)
    result = persist(db, scan_row, items, candidates, projection)
    assert result.group_snapshots == result.edge_snapshots == 0
    assert db.query(IdentityFamilyDiagnosticSnapshot).one().diagnostic_status == "DEFERRED_OVERSIZED_FAMILY"
    assert db.query(IdentityFamilyDiagnosticMemberSnapshot).count() == 21


def test_ambiguous_record_family_persists_diagnostic_reason(db):
    scan_row = scan(db)
    first = record("A", uom="PCS")
    conflicting = record("A", uom="l")
    other = record("B")
    candidates = [pair(first, other)]
    projection = project(7, [first, conflicting, other], candidates)
    persist(db, scan_row, [first, conflicting, other], candidates, projection)
    diagnostic = db.query(IdentityFamilyDiagnosticSnapshot).one()
    assert diagnostic.diagnostic_status == "DEFERRED_AMBIGUOUS_RECORD_FAMILY"
    assert "AMBIGUOUS_SCAN_LOCAL_RECORD_REF" in diagnostic.reason_codes_json


def test_local_rescoring_is_snapshot_provenance_not_candidate(db):
    scan_row = scan(db)
    items = [record(name) for name in "ABC"]
    candidates = [pair(items[0], items[1]), pair(items[1], items[2])]
    projection = project(7, items, candidates)
    persist(db, scan_row, items, candidates, projection)
    assert db.query(IdentityGroupEdgeSnapshot).filter_by(evidence_source="G1_LOCAL_RESCORING").count() == 1
    assert db.query(DuplicateCandidate).count() == 0


def test_direct_cannot_link_in_accepted_group_is_rejected_without_rows(db):
    scan_row = scan(db)
    items = [record("A"), record("B")]
    candidates = [pair(*items, edge="strong")]
    projection = project(7, items, candidates)
    group = projection.groups[0]
    bad_edge = replace(group.internal_edges[0], edge_class=IdentityEdgeClass.CANNOT_LINK)
    malformed = replace(projection, groups=(replace(group, internal_edges=(bad_edge,)),))
    with pytest.raises(ValueError, match="CANNOT_LINK"):
        persist(db, scan_row, items, candidates, malformed)
    assert db.query(IdentityGroupProjectionRun).count() == 0


def test_transaction_failure_rolls_back_entire_snapshot_graph(db):
    scan_row = scan(db)
    items = [record("A"), record("B")]
    candidates = [pair(*items, edge="strong")]
    projection = project(7, items, candidates)

    def fail_member(_mapper, _connection, _target):
        raise RuntimeError("forced member failure")

    event.listen(IdentityGroupMemberSnapshot, "before_insert", fail_member)
    try:
        with pytest.raises(RuntimeError, match="forced member failure"):
            persist(db, scan_row, items, candidates, projection)
    finally:
        event.remove(IdentityGroupMemberSnapshot, "before_insert", fail_member)
    assert db.query(IdentityGroupProjectionRun).count() == 0
    assert db.query(ScanRecordSnapshot).count() == 0
    assert db.query(IdentityGroupSnapshot).count() == 0
    assert db.query(IdentityGroupMemberSnapshot).count() == 0
    assert db.query(IdentityGroupEdgeSnapshot).count() == 0


def test_identical_projection_is_idempotent(db):
    scan_row = scan(db)
    items = [record("A"), record("B")]
    candidates = [pair(*items, edge="strong")]
    projection = project(7, items, candidates)
    first = persist(db, scan_row, items, candidates, projection)
    second = persist(db, scan_row, items, candidates, projection)
    assert second.idempotent and second.projection_run_id == first.projection_run_id
    assert db.query(IdentityGroupProjectionRun).count() == 1
    assert db.query(IdentityGroupSnapshot).count() == 1


def test_input_order_stability_reuses_same_snapshot(db):
    scan_row = scan(db)
    items = [record(name) for name in "ABCD"]
    candidates = [pair(items[0], items[1]), pair(items[1], items[2]), pair(items[2], items[3])]
    first_projection = project(7, items, candidates)
    first = persist(db, scan_row, items, candidates, first_projection)
    shuffled_items, shuffled_candidates = list(items), list(candidates)
    random.Random(17).shuffle(shuffled_items)
    random.Random(19).shuffle(shuffled_candidates)
    second_projection = project(7, shuffled_items, shuffled_candidates)
    second = persist(db, scan_row, shuffled_items, shuffled_candidates, second_projection)
    assert first_projection == second_projection
    assert second.idempotent and second.projection_run_id == first.projection_run_id


def test_historical_scan_has_no_fabricated_snapshots(db):
    scan(db, scan_id=99)
    assert db.query(IdentityGroupProjectionRun).count() == 0
    assert db.query(ScanRecordSnapshot).count() == 0


def test_additive_migration_creates_snapshot_tables_without_backfill(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'historical.db'}")
    DuplicateScan.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(DuplicateScan.__table__.insert().values(
            id=41, scan_name="historical", threshold=80, status="COMPLETED",
            model_version="deterministic-v1", selected_fields="[]",
        ))
    ensure_identity_group_snapshot_tables(engine)
    tables = set(inspect(engine).get_table_names())
    assert {
        "identity_group_projection_run", "scan_record_snapshot", "identity_group_snapshot",
        "identity_group_member_snapshot", "identity_family_diagnostic_snapshot",
        "identity_family_diagnostic_member_snapshot", "identity_group_edge_snapshot",
    }.issubset(tables)
    with engine.connect() as connection:
        assert connection.execute(IdentityGroupProjectionRun.__table__.select()).all() == []


def test_persistence_select_count_is_bounded_not_per_member_or_edge(db):
    scan_row = scan(db)
    items = [record(str(index)) for index in range(7)]
    candidates = [pair(items[i], items[j], "strong") for i in range(7) for j in range(i + 1, 7)]
    projection = project(7, items, candidates)
    selects = []

    def count_select(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count_select)
    try:
        persist(db, scan_row, items, candidates, projection)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count_select)
    assert len(selects) <= 4
