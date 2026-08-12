from itertools import combinations

import pytest
from sqlalchemy import create_engine, event, inspect

from app.db.migrations import ensure_group_review_tables
from app.db.models import (
    DuplicateScan,
    HumanIdentityConstraint,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupReviewEvent,
    IdentityGroupReviewPartition,
    IdentityGroupReviewPartitionMember,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.llm.groq_provider import GroqLLMProvider
from app.services.identity_group_projection import project_identity_groups, scan_record_ref
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    GroupReviewValidationError,
    HumanConstraintType,
    IdentityGroupReviewService,
    derive_human_identity_constraints,
)


def record(name, description="Precision component", uom="PCS"):
    return {
        "CONTRACT": "S1", "PART_NO": name, "DESCRIPTION": description,
        "UNIT_MEAS": uom, "PRODUCT_CATEGORY_ID": "", "HSN_SAC_CODE": "",
    }


def persisted_group(db, size=5, *, scan_id=7, key="a", records=None):
    scan = db.query(DuplicateScan).filter_by(id=scan_id).one_or_none()
    if scan is None:
        scan = DuplicateScan(
            id=scan_id, scan_name=f"scan-{scan_id}", threshold=80, status="COMPLETED",
            model_version="deterministic-v1", selected_fields="[]",
        )
        db.add(scan); db.flush()
    run = IdentityGroupProjectionRun(
        scan_id=scan_id, algorithm_version="constrained-group-projection-v1",
        edge_classifier_version="identity-edge-classifier-v1", evidence_fingerprint=key * 64,
        max_group_validation_members=20, engine_version="deterministic-v1", status="COMPLETED",
        records_seen=size, seed_edges=0, provisional_components=1, accepted_groups=1,
        likely_groups=1, review_groups=0, conflicting_families=0, oversized_families=0,
        ambiguous_families=0, internal_pairs_total=size * (size - 1) // 2,
        internal_pairs_reused=0, internal_pairs_rescored=size * (size - 1) // 2,
        cannot_links_found=0, max_component_size=size, max_accepted_group_size=size,
    )
    db.add(run); db.flush()
    group = IdentityGroupSnapshot(
        projection_run_id=run.id, scan_id=scan_id, hypothesis_key=key * 64,
        projection_algorithm_version=run.algorithm_version, group_status="LIKELY_DUPLICATE_GROUP",
        group_size=size, supporting_edge_count=size * (size - 1) // 2,
        review_edge_count=0, non_groupable_internal_count=0,
        internal_pair_count=size * (size - 1) // 2, internal_pairs_reused=0,
        internal_pairs_rescored=size * (size - 1) // 2, evidence_completeness=1,
        distinct_uoms_json='["PCS"]', same_uom_pair_count=size * (size - 1) // 2,
        convertible_uom_pair_count=0, different_basis_pair_count=0,
        missing_or_wildcard_pair_count=0, malformed_or_unknown_pair_count=0,
        possible_mapping_error_count=0, reason_codes_json="[]",
    )
    db.add(group); db.flush()
    source_records = records or [record(chr(65 + index)) for index in range(size)]
    refs = []
    for index, source in enumerate(source_records):
        ref = scan_record_ref(scan_id, source)
        row = ScanRecordSnapshot(
            scan_id=scan_id, record_ref_key=ref.key, contract=source["CONTRACT"],
            part_no=source["PART_NO"], description=source["DESCRIPTION"],
            normalized_part_no=source["PART_NO"].lower(),
            normalized_description=source["DESCRIPTION"].lower(), uom=source["UNIT_MEAS"],
            product_category_id="", hsn_sac_code="",
        )
        db.add(row); db.flush()
        db.add(IdentityGroupMemberSnapshot(
            group_snapshot_id=group.id, record_snapshot_id=row.id,
            member_index=index, record_ref_key=ref.key,
        ))
        refs.append(ref.key)
    db.commit()
    return scan, run, group, tuple(refs), tuple(source_records)


def create(service, run, group, refs, decision, **kwargs):
    return service.create_review(
        scan_id=run.scan_id, projection_run_id=run.id, group_snapshot_id=group.id,
        group_hypothesis_key=group.hypothesis_key, decision_type=decision,
        reviewer="reviewer", submitted_members=kwargs.pop("submitted_members", refs), **kwargs,
    )


@pytest.mark.parametrize("size,expected", [(4, 6), (7, 21)])
def test_confirm_all_derives_every_must_link_without_pair_only_assumption(size, expected):
    refs = tuple(chr(65 + index) for index in range(size))
    constraints = derive_human_identity_constraints(
        GroupReviewDecision.CONFIRM_ALL_AS_ONE, refs, submitted_members=reversed(refs)
    )
    assert len(constraints) == expected
    assert {item.constraint_type for item in constraints} == {HumanConstraintType.MUST_LINK}


def test_confirm_selected_four_of_five_has_six_links_and_no_inference_for_e():
    constraints = derive_human_identity_constraints(
        GroupReviewDecision.CONFIRM_SELECTED, "ABCDE", submitted_members="DCBA"
    )
    assert len(constraints) == 6
    assert all("E" not in (item.left_record_ref_key, item.right_record_ref_key) for item in constraints)


def test_split_four_of_five_has_six_must_and_four_cannot_links():
    constraints = derive_human_identity_constraints(
        GroupReviewDecision.SPLIT_PARTITIONS, "ABCDE", partitions=["E", "DCBA"]
    )
    assert sum(item.constraint_type == HumanConstraintType.MUST_LINK for item in constraints) == 6
    assert sum(item.constraint_type == HumanConstraintType.CANNOT_LINK for item in constraints) == 4
    assert {(item.left_record_ref_key, item.right_record_ref_key) for item in constraints if item.constraint_type == HumanConstraintType.CANNOT_LINK} == {
        (letter, "E") for letter in "ABCD"
    }


def test_multi_partition_split_has_within_links_and_all_cross_cannot_links():
    constraints = derive_human_identity_constraints(
        GroupReviewDecision.SPLIT_PARTITIONS, "ABCDE", partitions=["DC", "E", "BA"]
    )
    must = {(item.left_record_ref_key, item.right_record_ref_key) for item in constraints if item.constraint_type == HumanConstraintType.MUST_LINK}
    cannot = [item for item in constraints if item.constraint_type == HumanConstraintType.CANNOT_LINK]
    assert must == {("A", "B"), ("C", "D")}
    assert len(cannot) == 8


def test_keep_all_separate_size_four_derives_six_cannot_links():
    constraints = derive_human_identity_constraints(
        GroupReviewDecision.KEEP_ALL_SEPARATE, "ABCD", submitted_members="DCBA"
    )
    assert len(constraints) == 6
    assert {item.constraint_type for item in constraints} == {HumanConstraintType.CANNOT_LINK}


def test_unsure_persists_event_with_no_constraints(db):
    _, run, group, refs, _ = persisted_group(db, 4)
    result = create(IdentityGroupReviewService(db), run, group, refs, GroupReviewDecision.UNSURE)
    assert result.constraint_count == 0
    assert db.query(IdentityGroupReviewEvent).count() == 1
    assert db.query(HumanIdentityConstraint).count() == 0


@pytest.mark.parametrize("partitions", [
    [("A", "B"), ("C", "D")],
    [("A", "B", "C"), ("C", "D", "E")],
    [("A", "B"), ("C", "D", "E", "UNKNOWN")],
    [(), ("A", "B", "C", "D", "E")],
])
def test_invalid_split_partitions_are_rejected(db, partitions):
    _, run, group, refs, _ = persisted_group(db, 5)
    with pytest.raises(GroupReviewValidationError):
        create(
            IdentityGroupReviewService(db), run, group, refs,
            GroupReviewDecision.SPLIT_PARTITIONS,
            submitted_members=(), partitions=partitions,
        )
    assert db.query(IdentityGroupReviewEvent).count() == 0


def test_cross_group_member_and_duplicate_selected_are_rejected(db):
    _, run, group, refs, _ = persisted_group(db, 5)
    service = IdentityGroupReviewService(db)
    with pytest.raises(GroupReviewValidationError):
        create(service, run, group, refs, GroupReviewDecision.CONFIRM_SELECTED, submitted_members=[refs[0], "unknown"])
    with pytest.raises(GroupReviewValidationError):
        create(service, run, group, refs, GroupReviewDecision.CONFIRM_SELECTED, submitted_members=[refs[0], refs[0]])


def test_append_only_supersession_keeps_history_and_only_new_constraints_effective(db):
    _, run, group, refs, _ = persisted_group(db, 4)
    service = IdentityGroupReviewService(db)
    first = create(service, run, group, refs, GroupReviewDecision.CONFIRM_ALL_AS_ONE)
    second = create(
        service, run, group, refs, GroupReviewDecision.KEEP_ALL_SEPARATE,
        supersedes_review_event_id=first.review_event_id,
    )
    assert [row.id for row in service.history(group.id)] == [first.review_event_id, second.review_event_id]
    assert db.query(HumanIdentityConstraint).count() == 12
    effective = service.effective_constraints(run.scan_id)
    assert len(effective) == 6
    assert {item.constraint_type for item in effective} == {HumanConstraintType.CANNOT_LINK}
    with pytest.raises(ValueError, match="append-only"):
        service.history(group.id)[0].comment = "changed"; db.commit()
    db.rollback()

    with pytest.raises(ValueError, match="append-only"):
        db.delete(service.history(group.id)[0]); db.commit()
    db.rollback()


def test_invalid_supersession_rejects_noncurrent_cross_group_and_missing(db):
    _, run, group, refs, _ = persisted_group(db, 4, key="a")
    service = IdentityGroupReviewService(db)
    first = create(service, run, group, refs, GroupReviewDecision.UNSURE)
    second = create(service, run, group, refs, GroupReviewDecision.UNSURE, supersedes_review_event_id=first.review_event_id)
    with pytest.raises(GroupReviewValidationError):
        create(service, run, group, refs, GroupReviewDecision.UNSURE, supersedes_review_event_id=first.review_event_id)
    _, other_run, other_group, other_refs, _ = persisted_group(db, 2, scan_id=8, key="b")
    with pytest.raises(GroupReviewValidationError):
        create(IdentityGroupReviewService(db), other_run, other_group, other_refs, GroupReviewDecision.UNSURE, supersedes_review_event_id=second.review_event_id)


def test_constraint_insert_failure_rolls_back_event_partitions_members_and_constraints(db):
    _, run, group, refs, _ = persisted_group(db, 4)
    def fail(_mapper, _connection, _target):
        raise RuntimeError("forced constraint failure")
    event.listen(HumanIdentityConstraint, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="forced constraint failure"):
            create(IdentityGroupReviewService(db), run, group, refs, GroupReviewDecision.CONFIRM_ALL_AS_ONE)
    finally:
        event.remove(HumanIdentityConstraint, "before_insert", fail)
    assert db.query(IdentityGroupReviewEvent).count() == 0
    assert db.query(IdentityGroupReviewPartition).count() == 0
    assert db.query(IdentityGroupReviewPartitionMember).count() == 0
    assert db.query(HumanIdentityConstraint).count() == 0


def test_future_projection_human_cannot_link_prevents_regrouping(db):
    _, run, group, refs, records = persisted_group(db, 2)
    service = IdentityGroupReviewService(db)
    create(service, run, group, refs, GroupReviewDecision.KEEP_ALL_SEPARATE)
    result = service.project_with_effective_constraints(
        scan_id=run.scan_id, records=records, candidates=(), selected_fields=["CONTRACT"]
    )
    assert result.groups == ()


def test_future_projection_human_must_link_creates_strong_support_when_safe(db):
    _, run, group, refs, records = persisted_group(db, 2)
    service = IdentityGroupReviewService(db)
    create(service, run, group, refs, GroupReviewDecision.CONFIRM_ALL_AS_ONE)
    result = service.project_with_effective_constraints(
        scan_id=run.scan_id, records=records, candidates=(), selected_fields=["CONTRACT"]
    )
    assert result.groups[0].group_status.value == "LIKELY_DUPLICATE_GROUP"
    assert "HUMAN_GROUP_MUST_LINK" in result.groups[0].internal_edges[0].reason_codes


def test_human_must_link_cannot_override_terminal_rotor_stator_conflict(db):
    records = [
        record("ROT", "F30 Compressor Rotor"),
        record("GEN", "F30 Compressor"),
        record("STAT", "F30 Compressor Stator"),
    ]
    _, run, group, refs, records = persisted_group(db, 3, records=records)
    service = IdentityGroupReviewService(db)
    create(service, run, group, refs, GroupReviewDecision.CONFIRM_ALL_AS_ONE)
    result = service.project_with_effective_constraints(
        scan_id=run.scan_id, records=records, candidates=(), selected_fields=["CONTRACT"],
    )
    assert result.groups == ()
    assert result.metrics.cannot_links_found == 1
    assert result.conflicting_families[0].conflict_edges[0].edge_class == IdentityEdgeClass.CANNOT_LINK


def test_human_confirmation_across_different_uom_is_allowed_without_uom_rule_change(db):
    records = [record("A", uom="l"), record("B", uom="PCS")]
    _, run, group, refs, records = persisted_group(db, 2, records=records)
    service = IdentityGroupReviewService(db)
    create(service, run, group, refs, GroupReviewDecision.CONFIRM_ALL_AS_ONE)
    result = service.project_with_effective_constraints(
        scan_id=run.scan_id, records=records, candidates=(), selected_fields=["CONTRACT", "UNIT_MEAS"]
    )
    assert result.groups[0].group_status.value == "LIKELY_DUPLICATE_GROUP"
    assert result.groups[0].uom_summary.different_basis_pair_count == 1


def test_additive_review_migration_creates_empty_tables_without_backfill(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'g6a.db'}")
    DuplicateScan.__table__.create(engine)
    IdentityGroupProjectionRun.__table__.create(engine)
    ScanRecordSnapshot.__table__.create(engine)
    IdentityGroupSnapshot.__table__.create(engine)
    ensure_group_review_tables(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"identity_group_review_event", "identity_group_review_partition",
            "identity_group_review_partition_member", "human_identity_constraint"}.issubset(tables)
    with engine.connect() as connection:
        assert connection.execute(IdentityGroupReviewEvent.__table__.select()).all() == []
    assert "initial_group_snapshot_id" in {
        column["name"] for column in inspect(engine).get_columns("identity_group_review_event")
    }


def test_additive_review_migration_upgrades_g6a_event_table_and_backfills_root(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'g6a-upgrade.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE identity_group_review_event ("
            "id INTEGER PRIMARY KEY, scan_id INTEGER NOT NULL, "
            "projection_run_id INTEGER NOT NULL, group_snapshot_id INTEGER NOT NULL, "
            "group_hypothesis_key VARCHAR(64) NOT NULL, decision_type VARCHAR(40) NOT NULL, "
            "reviewer VARCHAR(100) NOT NULL, comment TEXT, "
            "supersedes_review_event_id INTEGER, created_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO identity_group_review_event "
            "(id, scan_id, projection_run_id, group_snapshot_id, group_hypothesis_key, "
            "decision_type, reviewer, created_at) VALUES "
            "(1, 7, 8, 9, ?, 'UNSURE', 'reviewer', CURRENT_TIMESTAMP)",
            ("a" * 64,),
        )
    ensure_group_review_tables(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT initial_group_snapshot_id FROM identity_group_review_event WHERE id = 1"
        ).scalar_one() == 9
    assert any(
        item["name"] == "uq_group_review_initial_group" and item["unique"]
        for item in inspect(engine).get_indexes("identity_group_review_event")
    )


def test_group_review_and_future_projection_never_call_llm_provider(db, monkeypatch):
    calls = []

    async def forbidden_provider_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("group review must not call an LLM provider")

    monkeypatch.setattr(GroqLLMProvider, "complete_json", forbidden_provider_call)
    _, run, group, refs, records = persisted_group(db, 2)
    service = IdentityGroupReviewService(db)
    create(service, run, group, refs, GroupReviewDecision.CONFIRM_ALL_AS_ONE)
    result = service.project_with_effective_constraints(
        scan_id=run.scan_id, records=records, candidates=(), selected_fields=["CONTRACT"]
    )
    assert len(result.groups) == 1
    assert calls == []
