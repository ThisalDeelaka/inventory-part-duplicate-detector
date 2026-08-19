import dataclasses
import inspect
from dataclasses import replace
from itertools import combinations
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.db.migrations import ensure_shadow_comparison_tables
from app.core.config import Settings
from app.db.models import (
    G2V2ProjectionRun,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ShadowComparisonCaseDeltaRow,
    ShadowComparisonCaseGroupRow,
    ShadowComparisonCaseRecordRow,
    ShadowComparisonCaseRow,
    ShadowComparisonRun,
    ShadowComparisonSafetyDeltaRow,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.g2_v2.contracts import G2V2EvidenceOrigin
from app.repositories.shadow_comparison_repository import ShadowComparisonRepository
from app.resolution.contracts import (
    DeferredIdentityReason,
    DeferredIdentityWorkUnit,
    IdentityConflict,
    IdentityConflictType,
    IdentityGroupHypothesisStatus,
)
from app.resolution.validation import (
    with_deferred_work_unit_fingerprint,
    with_identity_conflict_fingerprint,
)
from app.services.group_llm_eligibility import GroupAdvisoryContractService
from app.services.identity_group_export_service import identity_groups_to_csv
from app.services.identity_group_query_service import IdentityGroupQueryService
from app.services.identity_group_review_service import IdentityGroupReviewService
from app.services.scan_runner import ScanRunner
from app.services.shadow_comparison_service import (
    _SUMMARY_FIELDS,
    _persist_result,
    build_and_persist_shadow_comparison,
    load_persisted_shadow_comparison,
    shadow_comparison_input_fingerprint,
)
from app.shadow_comparison.comparison import compare_g2_v1_v2
from app.shadow_comparison.contracts import (
    AdjudicationPriority,
    ShadowComparisonCaseType,
    ShadowComparisonConfiguration,
    ShadowComparisonInput,
    ShadowSafetyDeltaType,
)
from app.shadow_comparison.fingerprints import shadow_fingerprint
from test_g2_v2_adapter import RESOLUTION_RUN_ID, SCAN_ID, build, hypothesis, proposal, targeted
from test_scan_identity_group_projection import SELECTED_FIELDS, accepted_group_records
from test_shadow_comparison import LIKELY, REVIEW, records_for, v1_snapshot, v2_manifest


def configuration(enabled=False):
    return SimpleNamespace(
        hybrid_retrieval_enabled=False,
        group_first_shadow_comparison_enabled=enabled,
    )


def comparison_input(records, v1_specs, v2_specs=(), **v2_kwargs):
    v2 = v2_manifest(records, v2_specs, **v2_kwargs)
    return ShadowComparisonInput(
        scan_id=SCAN_ID,
        canonical_records=tuple(records),
        v1_snapshot=v1_snapshot(records, v1_specs),
        v2_snapshot=v2,
        v1_projection_run_id=101,
        v2_projection_run_id=202,
        v2_source_resolution_run_id=RESOLUTION_RUN_ID,
        v2_projection_status="COMPLETED",
    )


def persist_fixture(db, value):
    pure = compare_g2_v1_v2(value)
    run = ShadowComparisonRepository(db).add_run(
        scan_id=value.scan_id,
        v1_projection_run_id=value.v1_projection_run_id,
        v2_projection_run_id=value.v2_projection_run_id,
        v2_source_resolution_run_id=value.v2_source_resolution_run_id,
        comparison_algorithm_version=value.comparison_algorithm_version,
        configuration_fingerprint=pure.configuration_fingerprint,
        input_fingerprint=shadow_comparison_input_fingerprint(value),
        status="RUNNING",
    )
    repository = ShadowComparisonRepository(db)
    _persist_result(repository, run, pure, value)
    for name in _SUMMARY_FIELDS:
        setattr(run, name, getattr(pure.summary, name))
    run.comparison_fingerprint = pure.comparison_fingerprint
    run.critical_safety_delta_count = sum(
        item.delta_type in {
            ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT,
            ShadowSafetyDeltaType.V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK,
        }
        for item in pure.safety_deltas
    )
    run.status = "COMPLETED"
    db.commit()
    loaded = load_persisted_shadow_comparison(db, run.id)
    assert loaded == pure
    return run, loaded


def completed_runs(db, scan_id):
    v1 = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan_id).one()
    v2 = db.query(G2V2ProjectionRun).filter_by(scan_id=scan_id).one()
    return v1, v2


def test_controlled_shadow_setting_defaults_disabled(monkeypatch):
    monkeypatch.delenv("GROUP_FIRST_SHADOW_COMPARISON_ENABLED", raising=False)
    assert Settings().group_first_shadow_comparison_enabled is False


def test_gate_disabled_creates_no_comparison_and_keeps_normal_v1_visible(db):
    scan, _ = ScanRunner(db, configuration(False)).run(
        accepted_group_records(), "GF-7B gate disabled", SELECTED_FIELDS, 60
    )
    v1, v2 = completed_runs(db, scan.id)
    assert scan.status == "COMPLETED" and v1.status == v2.status == "COMPLETED"
    assert db.query(ShadowComparisonRun).filter_by(scan_id=scan.id).count() == 0
    assert IdentityGroupQueryService(db).resolve_run(scan.id).id == v1.id


def test_enabled_eligible_scan_persists_exact_agreement_after_current_v1(db):
    scan, _ = ScanRunner(db, configuration(True)).run(
        accepted_group_records(), "GF-7B enabled", SELECTED_FIELDS, 60
    )
    v1, v2 = completed_runs(db, scan.id)
    shadow = db.query(ShadowComparisonRun).filter_by(scan_id=scan.id).one()
    loaded = load_persisted_shadow_comparison(db, shadow.id)
    assert shadow.status == "COMPLETED"
    assert (shadow.v1_projection_run_id, shadow.v2_projection_run_id) == (v1.id, v2.id)
    assert loaded.summary.exact_match_count == 1
    assert loaded.summary.positive_pair_jaccard == 1.0
    assert loaded.cases[0].adjudication_priority == AdjudicationPriority.NONE
    assert loaded.safety_deltas == ()
    assert IdentityGroupQueryService(db).resolve_run(scan.id).id == v1.id


def test_split_case_round_trips_exact_group_and_member_relations(db):
    records = records_for(("A", "B", "C", "D"))
    run, loaded = persist_fixture(db, comparison_input(
        records,
        [(("A", "B", "C", "D"), LIKELY)],
        [(("A", "B"), LIKELY), (("C", "D"), LIKELY)],
    ))
    assert len(loaded.cases) == 1
    assert loaded.cases[0].case_type == ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2
    assert loaded.cases[0].v1_member_references == ("A", "B", "C", "D")
    assert db.query(ShadowComparisonCaseGroupRow).filter_by(
        comparison_run_id=run.id
    ).count() == 3


def test_critical_protected_conflict_round_trips_direct_provenance(db):
    records = records_for(("A", "B"))
    conflict = with_identity_conflict_fingerprint(IdentityConflict(
        conflict_id="protected-A-B",
        scan_id=SCAN_ID,
        involved_record_ids=(1, 2),
        involved_record_references=("A", "B"),
        conflict_type=IdentityConflictType.PROTECTED_CANNOT_LINK,
        protected_evidence_references=("gf4-cannot-link-A-B",),
        source_neighborhood_references=("n-A",),
        summary="protected",
        fingerprint="",
    ))
    run, loaded = persist_fixture(db, comparison_input(
        records, [(("A", "B"), LIKELY)], conflicts=(conflict,)
    ))
    case = loaded.cases[0]
    assert case.adjudication_priority == AdjudicationPriority.CRITICAL
    delta = next(item for item in case.safety_deltas if item.delta_type ==
                 ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT)
    assert delta.protected_evidence_references == ("gf4-cannot-link-A-B",)
    row = db.query(ShadowComparisonSafetyDeltaRow).filter_by(
        comparison_run_id=run.id,
        delta_fingerprint=delta.delta_fingerprint,
    ).one()
    assert "gf4-cannot-link-A-B" in row.evidence_fingerprints_json


def test_deferred_context_round_trips_without_winner_claim(db):
    records = records_for(("A", "B"))
    deferred = with_deferred_work_unit_fingerprint(DeferredIdentityWorkUnit(
        deferred_id="deferred-A-B",
        scan_id=SCAN_ID,
        record_ids=(1, 2),
        record_references=("A", "B"),
        reason=DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY,
        unfinished_evidence_summary="more evidence required",
        source_neighborhood_references=("n-A",),
        fingerprint="",
    ))
    _run, loaded = persist_fixture(db, comparison_input(
        records, [(("A", "B"), LIKELY)], deferred=(deferred,)
    ))
    case = loaded.cases[0]
    assert case.adjudication_priority == AdjudicationPriority.HIGH
    assert case.related_v2_deferred_references
    assert "winner" not in repr(loaded).lower()


def test_targeted_evidence_explanation_and_reference_round_trip(db):
    records = records_for(("A", "B", "C"))
    refs = {item.record_id: item.record_ref_key for item in records}
    proposals = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    target = targeted(1, 3, refs, IdentityEdgeClass.STRONG_SUPPORT)
    source = hypothesis(records, proposals + (target,))
    from test_g2_v2_adapter import resolution
    v2 = build(records, resolution(records, (source,), targeted_results=(target,)), proposals, (target,))
    value = ShadowComparisonInput(
        scan_id=SCAN_ID,
        canonical_records=records,
        v1_snapshot=v1_snapshot(records, [(("A", "B", "C"), LIKELY)]),
        v2_snapshot=v2,
        v1_projection_run_id=101,
        v2_projection_run_id=202,
        v2_source_resolution_run_id=RESOLUTION_RUN_ID,
        v2_projection_status="COMPLETED",
    )
    _run, loaded = persist_fixture(db, value)
    delta = next(item for item in loaded.safety_deltas if item.delta_type ==
                 ShadowSafetyDeltaType.V2_GROUP_USES_TARGETED_EVIDENCE_NOT_AVAILABLE_TO_V1)
    assert delta.involved_record_references == ("A", "B", "C")
    assert "superior" not in delta.explanation.lower()


def test_service_is_idempotent_and_changed_configuration_is_versioned(db):
    scan, _ = ScanRunner(db, configuration(False)).run(
        accepted_group_records(), "GF-7B versions", SELECTED_FIELDS, 60
    )
    v1, v2 = completed_runs(db, scan.id)
    first = build_and_persist_shadow_comparison(
        db, scan_id=scan.id, v1_projection_run_id=v1.id, v2_projection_run_id=v2.id
    )
    before = tuple(db.query(model).count() for model in (
        ShadowComparisonRun, ShadowComparisonCaseRow, ShadowComparisonCaseGroupRow,
        ShadowComparisonCaseRecordRow, ShadowComparisonSafetyDeltaRow,
    ))
    repeated = build_and_persist_shadow_comparison(
        db, scan_id=scan.id, v1_projection_run_id=v1.id, v2_projection_run_id=v2.id
    )
    after_repeat = tuple(db.query(model).count() for model in (
        ShadowComparisonRun, ShadowComparisonCaseRow, ShadowComparisonCaseGroupRow,
        ShadowComparisonCaseRecordRow, ShadowComparisonSafetyDeltaRow,
    ))
    changed = build_and_persist_shadow_comparison(
        db,
        scan_id=scan.id,
        v1_projection_run_id=v1.id,
        v2_projection_run_id=v2.id,
        configuration=ShadowComparisonConfiguration(configuration_version="changed-v2"),
    )
    assert repeated.idempotent is True and repeated.comparison_run_id == first.comparison_run_id
    assert after_repeat == before
    assert changed.comparison_run_id != first.comparison_run_id
    assert db.query(ShadowComparisonRun).count() == 2
    assert db.get(ShadowComparisonRun, first.comparison_run_id).status == "COMPLETED"


def test_atomic_child_failure_marks_failed_without_partial_graph_or_upstream_change(db):
    scan, _ = ScanRunner(db, configuration(False)).run(
        accepted_group_records(), "GF-7B rollback", SELECTED_FIELDS, 60
    )
    v1, v2 = completed_runs(db, scan.id)
    def fail(*_args):
        raise RuntimeError("forced shadow child failure")

    event.listen(ShadowComparisonCaseRecordRow, "before_insert", fail)
    try:
        failed = build_and_persist_shadow_comparison(
            db, scan_id=scan.id, v1_projection_run_id=v1.id, v2_projection_run_id=v2.id
        )
    finally:
        event.remove(ShadowComparisonCaseRecordRow, "before_insert", fail)
    assert failed.status == "FAILED"
    run = db.get(ShadowComparisonRun, failed.comparison_run_id)
    assert run.status == "FAILED" and run.safe_failure_category == "RUNTIMEERROR"
    assert all(not rows for rows in ShadowComparisonRepository(db).result_rows(run.id))
    assert db.get(IdentityGroupProjectionRun, v1.id).status == "COMPLETED"
    assert db.get(G2V2ProjectionRun, v2.id).status == "COMPLETED"


def test_normal_scan_shadow_failure_is_isolated_from_visible_v1(db):
    def fail(*_args):
        raise RuntimeError("forced normal-scan shadow failure")

    event.listen(ShadowComparisonCaseRecordRow, "before_insert", fail)
    try:
        scan, _ = ScanRunner(db, configuration(True)).run(
            accepted_group_records(), "GF-7B isolated failure", SELECTED_FIELDS, 60
        )
    finally:
        event.remove(ShadowComparisonCaseRecordRow, "before_insert", fail)
    v1, _v2 = completed_runs(db, scan.id)
    assert scan.status == "COMPLETED"
    assert db.query(ShadowComparisonRun).filter_by(scan_id=scan.id).one().status == "FAILED"
    assert IdentityGroupQueryService(db).resolve_run(scan.id).id == v1.id


def test_comparison_does_not_contaminate_current_g3_g5_g6_or_g7_readers(db):
    scan, _ = ScanRunner(db, configuration(False)).run(
        accepted_group_records(), "GF-7B reader isolation", SELECTED_FIELDS, 60
    )
    v1, v2 = completed_runs(db, scan.id)
    group = db.query(IdentityGroupSnapshot).filter_by(projection_run_id=v1.id).one()
    query = IdentityGroupQueryService(db)
    before = (
        query.summary(scan.id),
        query.list_groups(scan.id),
        query.group_detail(scan.id, group.id),
        identity_groups_to_csv(db, scan.id),
        IdentityGroupReviewService(db).group_members(
            scan.id, v1.id, group.id, group.hypothesis_key
        ),
        GroupAdvisoryContractService(db).load(scan.id, v1.id, group.id)[0].id,
    )
    persisted = build_and_persist_shadow_comparison(
        db, scan_id=scan.id, v1_projection_run_id=v1.id, v2_projection_run_id=v2.id
    )
    assert persisted.status == "COMPLETED"
    after = (
        query.summary(scan.id),
        query.list_groups(scan.id),
        query.group_detail(scan.id, group.id),
        identity_groups_to_csv(db, scan.id),
        IdentityGroupReviewService(db).group_members(
            scan.id, v1.id, group.id, group.hypothesis_key
        ),
        GroupAdvisoryContractService(db).load(scan.id, v1.id, group.id)[0].id,
    )
    assert before == after
    assert after[0]["snapshot_available"] is True
    assert after[0]["selected_projection"]["projection_run_id"] == v1.id


def test_historical_reads_create_no_comparison_and_schema_has_no_truth_fields(db):
    scan, _ = ScanRunner(db, configuration(False)).run(
        accepted_group_records(), "GF-7B historical", SELECTED_FIELDS, 60
    )
    query = IdentityGroupQueryService(db)
    query.summary(scan.id)
    query.list_groups(scan.id)
    assert db.query(ShadowComparisonRun).count() == 0
    fields = {
        column.name for model in (
            ShadowComparisonRun, ShadowComparisonCaseRow,
            ShadowComparisonSafetyDeltaRow,
        ) for column in model.__table__.columns
    }
    forbidden = {
        "winner", "correct_version", "accuracy", "precision", "recall",
        "false_positive", "false_negative", "promotion_score",
    }
    assert not fields & forbidden


def test_additive_migration_terminal_immutability_and_bounded_bulk_reload(db):
    ensure_shadow_comparison_tables(db.get_bind())
    ensure_shadow_comparison_tables(db.get_bind())
    records = records_for(("A", "B", "C", "D"))
    conflict = with_identity_conflict_fingerprint(IdentityConflict(
        conflict_id="protected-A-B",
        scan_id=SCAN_ID,
        involved_record_ids=(1, 2),
        involved_record_references=("A", "B"),
        conflict_type=IdentityConflictType.PROTECTED_CANNOT_LINK,
        protected_evidence_references=("gf4-cannot-link-A-B",),
        source_neighborhood_references=("n-A",),
        summary="protected",
        fingerprint="",
    ))
    run, expected = persist_fixture(db, comparison_input(
        records,
        [(("A", "B"), LIKELY), (("C", "D"), REVIEW)],
        [(("C", "D"), REVIEW)],
        conflicts=(conflict,),
    ))
    run.status = "FAILED"
    with pytest.raises(ValueError, match="terminal shadow comparison"):
        db.flush()
    db.rollback()
    db.expire_all()
    statements = []
    listener = lambda *_args: statements.append(1)
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        loaded = load_persisted_shadow_comparison(db, run.id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert dataclasses.is_dataclass(loaded)
    assert len(statements) == 6
    assert loaded == expected
    assert loaded.summary.records_total == 4
    assert (loaded.summary.v1_group_count, loaded.summary.v2_group_count) == (2, 1)
    assert len(loaded.cases) == 2
    assert len(loaded.safety_deltas) >= 1


def test_provider_and_public_surface_boundaries_are_absent():
    import app.services.shadow_comparison_service as service
    import app.repositories.shadow_comparison_repository as repository

    source = inspect.getsource(service) + inspect.getsource(repository)
    forbidden = (
        "create_llm_provider", "create_group_advisory_provider", "GROQ_API_KEY",
        "ANTHROPIC_API_KEY", "FastAPI", "APIRouter", "promotion_score",
    )
    assert not any(value in source for value in forbidden)
