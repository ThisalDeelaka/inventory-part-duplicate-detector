import dataclasses
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.db.migrations import ensure_scan_orchestration_tables
from app.db.models import (
    DuplicateCandidate,
    DuplicateScan,
    G2V2GroupMemberRow,
    G2V2ProjectionRun,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    IdentityResolutionGroupMember,
    IdentityResolutionRun,
    ScanOrchestrationRun,
    ScanOrchestrationStageResultRow,
    ShadowComparisonCaseRecordRow,
)
from app.orchestration.contracts import (
    OrchestrationFailureCategory,
    ScanOrchestrationMode,
    ScanStage,
    ScanStageExecutionStatus,
    StageRequirementClassification,
)
from app.orchestration.planning import (
    build_scan_orchestration_plan,
    scan_orchestration_policy,
)
from app.services.group_llm_eligibility import GroupAdvisoryContractService
from app.services.identity_group_export_service import identity_groups_to_csv
from app.services.identity_group_query_service import IdentityGroupQueryService
from app.services.identity_group_review_service import IdentityGroupReviewService
from app.services.scan_orchestration_service import start_scan_orchestration
from app.services.scan_runner import ScanRunner
from test_scan_identity_group_projection import (
    SELECTED_FIELDS,
    accepted_group_records,
)


def configuration(mode="legacy_primary", shadow=False):
    return SimpleNamespace(
        hybrid_retrieval_enabled=False,
        identity_orchestration_mode=mode,
        group_first_shadow_comparison_enabled=shadow,
    )


def run_scan(db, *, mode="group_first_primary", shadow=False, name="GF-8B"):
    return ScanRunner(db, configuration(mode, shadow)).run(
        accepted_group_records(), name, SELECTED_FIELDS, 60
    )[0]


def audit(db, scan_id):
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=scan_id).one()
    stages = db.query(ScanOrchestrationStageResultRow).filter_by(
        orchestration_run_id=run.id
    ).order_by(ScanOrchestrationStageResultRow.execution_order).all()
    return run, stages


def stages_by_id(rows):
    return {row.stage_id: row for row in rows}


def test_group_first_success_persists_exact_plan_and_keeps_v1_current(db, monkeypatch):
    def provider_called(*_args, **_kwargs):
        raise AssertionError("deterministic orchestration invoked a provider")

    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr(
        "app.llm.groq_group_provider.create_group_advisory_provider", provider_called
    )
    scan = run_scan(db)
    run, stages = audit(db, scan.id)

    assert scan.status == run.status == "COMPLETED"
    assert run.mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY.value
    assert run.primary_identity_ready is True
    assert run.compatibility_projection_ready is True
    assert run.visible_product_ready is True
    assert [row.stage_id for row in stages] == [stage.value for stage in ScanStage]
    assert [row.execution_order for row in stages] == list(range(9))
    assert [row.stage_authority for row in stages[:5]] == [
        StageRequirementClassification.PRIMARY_REQUIRED.value
    ] * 5
    assert [row.stage_authority for row in stages[5:8]] == [
        StageRequirementClassification.COMPATIBILITY_REQUIRED.value
    ] * 3
    assert all(row.status == "SUCCEEDED" for row in stages[:8])
    assert stages[8].status == "NOT_APPLICABLE"
    v1 = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    v2 = db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one()
    assert v1.status == v2.status == "COMPLETED"
    assert not hasattr(v2, "is_current")
    assert IdentityGroupQueryService(db).resolve_run(scan.id).id == v1.id


def test_legacy_success_uses_legacy_authority_and_same_visible_contract(db):
    scan = run_scan(db, mode="legacy_primary")
    run, rows = audit(db, scan.id)
    by_stage = stages_by_id(rows)
    assert scan.status == run.status == "COMPLETED"
    assert run.mode == "legacy_primary"
    assert run.visible_projection_contract == "G2_V1"
    assert by_stage[ScanStage.GROUP_RESOLUTION.value].stage_authority == "OPTIONAL_DIAGNOSTIC"
    assert by_stage[ScanStage.G2_V2_PROJECTION.value].stage_authority == "OPTIONAL_DIAGNOSTIC"
    assert by_stage[ScanStage.LEGACY_PAIR_COMPATIBILITY.value].stage_authority == "PRIMARY_REQUIRED"
    v1 = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    assert IdentityGroupQueryService(db).resolve_run(scan.id).id == v1.id


def test_legacy_gf5_failure_remains_visible_and_is_audited_optional(db):
    def fail(*_args):
        raise RuntimeError("forced resolver child failure")

    event.listen(IdentityResolutionGroupMember, "before_insert", fail)
    try:
        scan = run_scan(db, mode="legacy_primary")
    finally:
        event.remove(IdentityResolutionGroupMember, "before_insert", fail)
    run, rows = audit(db, scan.id)
    assert scan.status == run.status == "COMPLETED"
    assert run.visible_product_ready is True
    assert run.safe_failure_category == "OPTIONAL_DIAGNOSTIC_FAILED"
    assert stages_by_id(rows)[ScanStage.GROUP_RESOLUTION.value].status == "FAILED"
    assert IdentityGroupQueryService(db).summary(scan.id)["snapshot_available"] is True


def test_legacy_gf6_failure_remains_visible_and_is_audited_optional(db):
    def fail(*_args):
        raise RuntimeError("forced v2 child failure")

    event.listen(G2V2GroupMemberRow, "before_insert", fail)
    try:
        scan = run_scan(db, mode="legacy_primary")
    finally:
        event.remove(G2V2GroupMemberRow, "before_insert", fail)
    run, rows = audit(db, scan.id)
    assert scan.status == run.status == "COMPLETED"
    assert run.visible_product_ready is True
    assert stages_by_id(rows)[ScanStage.G2_V2_PROJECTION.value].status == "FAILED"
    assert IdentityGroupQueryService(db).summary(scan.id)["snapshot_available"] is True


def test_group_first_gf5_failure_fails_without_legacy_rescue(db):
    def fail(*_args):
        raise RuntimeError("forced resolver child failure")

    event.listen(IdentityResolutionGroupMember, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="required group resolution failed"):
            run_scan(db)
    finally:
        event.remove(IdentityResolutionGroupMember, "before_insert", fail)
    scan = db.query(DuplicateScan).one()
    run, rows = audit(db, scan.id)
    by_stage = stages_by_id(rows)
    assert scan.status == run.status == "FAILED"
    assert run.primary_identity_ready is False
    assert run.visible_product_ready is False
    assert run.safe_failure_category == "PRIMARY_IDENTITY_FAILED"
    assert by_stage[ScanStage.GROUP_RESOLUTION.value].status == "FAILED"
    assert by_stage[ScanStage.LEGACY_PAIR_COMPATIBILITY.value].status == "SKIPPED"
    assert db.query(DuplicateCandidate).filter_by(scan_id=scan.id).count() == 0
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 0


def test_group_first_gf6_failure_fails_and_retains_completed_resolution(db):
    def fail(*_args):
        raise RuntimeError("forced v2 child failure")

    event.listen(G2V2GroupMemberRow, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="required G2-v2 projection failed"):
            run_scan(db)
    finally:
        event.remove(G2V2GroupMemberRow, "before_insert", fail)
    scan = db.query(DuplicateScan).one()
    run, rows = audit(db, scan.id)
    assert scan.status == run.status == "FAILED"
    assert run.primary_identity_ready is False and run.visible_product_ready is False
    assert stages_by_id(rows)[ScanStage.G2_V2_PROJECTION.value].status == "FAILED"
    assert db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 0


@pytest.mark.parametrize("model", [DuplicateCandidate, IdentityGroupMemberSnapshot])
def test_group_first_compatibility_failure_preserves_primary_and_fails_visible(db, model):
    def fail(*_args):
        raise RuntimeError("forced compatibility failure")

    event.listen(model, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="forced compatibility failure"):
            run_scan(db)
    finally:
        event.remove(model, "before_insert", fail)
    scan = db.query(DuplicateScan).one()
    run, rows = audit(db, scan.id)
    assert scan.status == run.status == "FAILED"
    assert run.primary_identity_ready is True
    assert run.compatibility_projection_ready is False
    assert run.visible_product_ready is False
    assert run.safe_failure_category == "COMPATIBILITY_OUTPUT_FAILED"
    assert db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    assert all(
        stages_by_id(rows)[stage.value].status == "FAILED"
        for stage in (
            ScanStage.LEGACY_PAIR_COMPATIBILITY,
            ScanStage.G1_COMPATIBILITY_PROJECTION,
            ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
        )
    )


def test_group_first_shadow_failure_is_optional_and_visible_scan_completes(db):
    def fail(*_args):
        raise RuntimeError("forced shadow failure")

    event.listen(ShadowComparisonCaseRecordRow, "before_insert", fail)
    try:
        scan = run_scan(db, shadow=True)
    finally:
        event.remove(ShadowComparisonCaseRecordRow, "before_insert", fail)
    run, rows = audit(db, scan.id)
    assert scan.status == run.status == "COMPLETED"
    assert run.primary_identity_ready is True
    assert run.compatibility_projection_ready is True
    assert run.visible_product_ready is True
    assert run.shadow_diagnostics_ready is False
    assert run.safe_failure_category == "OPTIONAL_DIAGNOSTIC_FAILED"
    assert stages_by_id(rows)[ScanStage.SHADOW_COMPARISON.value].status == "FAILED"


def test_group_first_shadow_disabled_is_not_applicable(db):
    scan = run_scan(db, shadow=False)
    run, rows = audit(db, scan.id)
    shadow = stages_by_id(rows)[ScanStage.SHADOW_COMPARISON.value]
    assert scan.status == run.status == "COMPLETED"
    assert run.shadow_diagnostics_ready is True
    assert shadow.status == ScanStageExecutionStatus.NOT_APPLICABLE.value


def test_explicit_modes_do_not_change_deterministic_v1_visible_result(db):
    legacy = run_scan(db, mode="legacy_primary", name="legacy")
    group = run_scan(db, mode="group_first_primary", name="group")
    legacy_run = db.query(ScanOrchestrationRun).filter_by(scan_id=legacy.id).one()
    group_run = db.query(ScanOrchestrationRun).filter_by(scan_id=group.id).one()
    legacy_v1 = IdentityGroupQueryService(db).summary(legacy.id)
    group_v1 = IdentityGroupQueryService(db).summary(group.id)
    assert (legacy_run.mode, group_run.mode) == (
        "legacy_primary", "group_first_primary"
    )
    assert legacy_v1["accepted_groups"] == group_v1["accepted_groups"]
    assert legacy_v1["likely_groups"] == group_v1["likely_groups"]
    assert legacy_v1["review_groups"] == group_v1["review_groups"]


def test_shadow_metrics_cannot_promote_or_demote_explicit_mode(db):
    legacy = run_scan(db, mode="legacy_primary", shadow=True, name="high agreement")
    group = run_scan(db, mode="group_first_primary", shadow=False, name="explicit group")
    assert db.query(ScanOrchestrationRun).filter_by(scan_id=legacy.id).one().mode == "legacy_primary"
    assert db.query(ScanOrchestrationRun).filter_by(scan_id=group.id).one().mode == "group_first_primary"


def test_start_is_idempotent_and_terminal_audit_is_immutable(db):
    scan = run_scan(db)
    run, rows = audit(db, scan.id)
    plan = build_scan_orchestration_plan(scan_orchestration_policy("group_first_primary"))
    repeated = start_scan_orchestration(db, scan_id=scan.id, plan=plan)
    assert repeated.idempotent is True
    assert repeated.orchestration_run_id == run.id
    assert db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).count() == 1
    assert len(rows) == db.query(ScanOrchestrationStageResultRow).filter_by(
        orchestration_run_id=run.id
    ).count() == 9
    run.mode = "legacy_primary"
    with pytest.raises(ValueError, match="terminal scan orchestration"):
        db.flush()
    db.rollback()
    rows[0].status = "FAILED"
    with pytest.raises(ValueError, match="stage history is immutable"):
        db.flush()
    db.rollback()


def test_historical_scan_read_does_not_create_orchestration_audit(db):
    historical = DuplicateScan(
        scan_name="historical",
        source_type="CSV",
        selected_fields="[]",
        threshold=60,
        status="COMPLETED",
        scan_mode="SAME_SITE_DUPLICATE",
        model_version="historical",
    )
    db.add(historical)
    db.commit()
    assert IdentityGroupQueryService(db).summary(historical.id)["snapshot_available"] is False
    assert db.query(ScanOrchestrationRun).filter_by(scan_id=historical.id).count() == 0


def test_group_first_current_readers_remain_v1_backed(db):
    scan = run_scan(db)
    v1 = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    group = db.query(IdentityGroupSnapshot).filter_by(projection_run_id=v1.id).one()
    query = IdentityGroupQueryService(db)
    assert query.summary(scan.id)["selected_projection"]["projection_run_id"] == v1.id
    assert query.list_groups(scan.id)["selected_projection"]["projection_run_id"] == v1.id
    assert query.group_detail(scan.id, group.id)["projection"]["projection_run_id"] == v1.id
    assert f",{v1.id}," in identity_groups_to_csv(db, scan.id)
    assert IdentityGroupReviewService(db).group_members(
        scan.id, v1.id, group.id, group.hypothesis_key
    )
    assert GroupAdvisoryContractService(db).load(scan.id, v1.id, group.id)[0].id == v1.id


def test_audit_schema_is_additive_and_writes_are_bounded_by_stage_count(db):
    ensure_scan_orchestration_tables(db.get_bind())
    ensure_scan_orchestration_tables(db.get_bind())
    statements = []

    def observe(_conn, _cursor, statement, *_args):
        lowered = statement.lower()
        if "scan_orchestration_" in lowered:
            statements.append(lowered.split(None, 1)[0])

    event.listen(db.get_bind(), "before_cursor_execute", observe)
    try:
        scan = run_scan(db)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", observe)
    run, rows = audit(db, scan.id)
    assert len(rows) == len(tuple(ScanStage)) == 9
    assert statements.count("insert") == 10
    assert statements.count("update") == 1
    assert len(statements) < 80
    assert dataclasses.is_dataclass(
        build_scan_orchestration_plan(scan_orchestration_policy()).policy
    )
    assert run.policy_fingerprint and run.plan_fingerprint


def test_source_run_references_are_same_scan_and_bounded(db):
    scan = run_scan(db, shadow=True)
    _run, rows = audit(db, scan.id)
    references = {
        row.stage_id: row.source_run_reference
        for row in rows if row.source_run_reference
    }
    assert references[ScanStage.DISCOVERY.value].startswith("identity_discovery_run:")
    assert references[ScanStage.SIGNED_EVIDENCE.value].startswith("identity_evidence_run:")
    assert references[ScanStage.GROUP_RESOLUTION.value].startswith("identity_resolution_run:")
    assert references[ScanStage.G2_V2_PROJECTION.value].startswith("g2_v2_projection_run:")
    assert references[ScanStage.G2_V1_COMPATIBILITY_PROJECTION.value].startswith(
        "identity_group_projection_run:"
    )
    assert references[ScanStage.SHADOW_COMPARISON.value].startswith("shadow_comparison_run:")
    assert all(len(value) <= 200 for value in references.values())
    assert all(row.diagnostic_summary is None or len(row.diagnostic_summary) <= 500 for row in rows)


def test_failure_categories_are_frozen_outcome_values():
    assert {item.value for item in OrchestrationFailureCategory} == {
        "PRIMARY_IDENTITY_FAILED",
        "COMPATIBILITY_OUTPUT_FAILED",
        "CONFIGURATION_INVALID",
        "OPTIONAL_DIAGNOSTIC_FAILED",
        "MULTIPLE_REQUIRED_STAGE_FAILURES",
    }


def test_audit_write_failure_cannot_report_scan_success(db):
    def fail(*_args):
        raise RuntimeError("forced orchestration audit failure")

    event.listen(ScanOrchestrationStageResultRow, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="forced orchestration audit failure"):
            run_scan(db)
    finally:
        event.remove(ScanOrchestrationStageResultRow, "before_insert", fail)
    scan = db.query(DuplicateScan).one()
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).one()
    assert scan.status == "FAILED"
    assert run.status == "FAILED"
    assert run.safe_failure_category == "CONFIGURATION_INVALID"
