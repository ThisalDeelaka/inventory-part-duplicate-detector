"""Durable, bounded execution audit for the frozen GF-8A orchestration plan."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db.models import (
    DuplicateCandidate,
    G2V2ProjectionRun,
    IdentityDiscoveryRun,
    IdentityEvidenceRun,
    IdentityGroupProjectionRun,
    IdentityResolutionRun,
    ScanOrchestrationRun,
    ShadowComparisonRun,
)
from app.orchestration.contracts import (
    OrchestrationRunStatus,
    ScanOrchestrationOutcome,
    ScanOrchestrationPlan,
    ScanStage,
    ScanStageExecutionStatus,
    ScanStageResult,
    StageRequirementClassification,
)
from app.orchestration.pair_path_deprecation import (
    HISTORICAL_ORCHESTRATION_POLICY_VERSION,
    POST_GF9_ORCHESTRATION_POLICY_VERSION,
    PairDiagnosticsAvailability,
    PairDiagnosticsState,
    evaluate_persisted_orchestration_outcome,
    pair_diagnostics_state,
    pair_path_write_policy,
)
from app.repositories.scan_orchestration_repository import ScanOrchestrationRepository


_SOURCE_MODELS = {
    ScanStage.DISCOVERY: ("identity_discovery_run", IdentityDiscoveryRun),
    ScanStage.SIGNED_EVIDENCE: ("identity_evidence_run", IdentityEvidenceRun),
    ScanStage.GROUP_RESOLUTION: ("identity_resolution_run", IdentityResolutionRun),
    ScanStage.G2_V2_PROJECTION: ("g2_v2_projection_run", G2V2ProjectionRun),
    ScanStage.G1_COMPATIBILITY_PROJECTION: (
        "identity_group_projection_run", IdentityGroupProjectionRun,
    ),
    ScanStage.G2_V1_COMPATIBILITY_PROJECTION: (
        "identity_group_projection_run", IdentityGroupProjectionRun,
    ),
    ScanStage.SHADOW_COMPARISON: ("shadow_comparison_run", ShadowComparisonRun),
}


@dataclass(frozen=True)
class PersistedScanOrchestration:
    orchestration_run_id: int
    status: str
    idempotent: bool
    outcome: ScanOrchestrationOutcome | None = None


def _now():
    return datetime.now(timezone.utc)


def _safe_token(value: str | None) -> str | None:
    if not value:
        return None
    token = re.sub(r"[^A-Z0-9_]", "_", str(value).upper()).strip("_")
    return token[:80] or "SAFE_STAGE_FAILURE"


def _bounded_summary(value: str | None) -> str | None:
    if not value:
        return None
    return " ".join(str(value).split())[:500]


def source_run_reference(kind: str, run_id: int) -> str:
    return f"{kind}:{int(run_id)}"


def pair_diagnostics_state_for_scan(db, scan_id: int) -> PairDiagnosticsState:
    """Return persisted-policy truth, never an inference from an empty row set."""
    run = ScanOrchestrationRepository(db).run_for_scan(scan_id)
    count = db.query(DuplicateCandidate).filter_by(scan_id=scan_id).count()
    if run is None or run.policy_version == HISTORICAL_ORCHESTRATION_POLICY_VERSION:
        return PairDiagnosticsState(
            PairDiagnosticsAvailability.GENERATED_AVAILABLE,
            count,
            "historical policy generated legacy pair diagnostics",
        )
    if run.policy_version != POST_GF9_ORCHESTRATION_POLICY_VERSION:
        raise ValueError("unknown persisted orchestration policy")
    return pair_diagnostics_state(pair_path_write_policy(run.mode),
                                  generated_candidate_count=count)


def _validate_source_reference(db, scan_id: int, stage: ScanStage, value: str | None):
    if value is None:
        return
    expected = _SOURCE_MODELS.get(stage)
    if expected is None:
        raise ValueError("stage does not accept a source-run reference")
    kind, model = expected
    prefix = f"{kind}:"
    if not value.startswith(prefix) or not value[len(prefix):].isdigit():
        raise ValueError("source-run reference has an invalid shape")
    row = db.get(model, int(value[len(prefix):]))
    if row is None or row.scan_id != scan_id:
        raise ValueError("source-run reference does not belong to the scan")


def start_scan_orchestration(db, *, scan_id: int, plan: ScanOrchestrationPlan):
    repository = ScanOrchestrationRepository(db)
    existing = repository.run_for_scan(scan_id)
    if existing is not None:
        _require_matching_plan(existing, plan)
        return PersistedScanOrchestration(existing.id, existing.status, True)
    try:
        row = repository.add_run(
            scan_id=scan_id,
            mode=plan.policy.mode.value,
            policy_version=plan.policy.policy_version,
            policy_fingerprint=plan.policy_fingerprint,
            plan_fingerprint=plan.plan_fingerprint,
            primary_identity_pipeline=plan.policy.primary_identity_pipeline.value,
            visible_projection_contract=plan.policy.visible_projection_contract.value,
            compatibility_projection_required=(
                plan.policy.compatibility_projection_required
            ),
            status=OrchestrationRunStatus.RUNNING.value,
        )
        db.commit()
        return PersistedScanOrchestration(row.id, row.status, False)
    except IntegrityError:
        db.rollback()
        existing = repository.run_for_scan(scan_id)
        if existing is None:
            raise
        _require_matching_plan(existing, plan)
        return PersistedScanOrchestration(existing.id, existing.status, True)


def _require_matching_plan(row: ScanOrchestrationRun, plan: ScanOrchestrationPlan):
    actual = (
        row.mode,
        row.policy_version,
        row.policy_fingerprint,
        row.plan_fingerprint,
        row.primary_identity_pipeline,
        row.visible_projection_contract,
        row.compatibility_projection_required,
    )
    expected = (
        plan.policy.mode.value,
        plan.policy.policy_version,
        plan.policy_fingerprint,
        plan.plan_fingerprint,
        plan.policy.primary_identity_pipeline.value,
        plan.policy.visible_projection_contract.value,
        plan.policy.compatibility_projection_required,
    )
    if actual != expected:
        raise ValueError("historical orchestration run differs from the requested plan")


def record_scan_stage_result(
    db,
    *,
    orchestration_run_id: int,
    plan: ScanOrchestrationPlan,
    stage: ScanStage,
    status: ScanStageExecutionStatus,
    started_at=None,
    safe_failure_category: str | None = None,
    source_reference: str | None = None,
    diagnostic_summary: str | None = None,
):
    status = ScanStageExecutionStatus(status)
    requirement = next(item for item in plan.stage_requirements if item.stage == stage)
    if (
        requirement.classification == StageRequirementClassification.NOT_APPLICABLE
        and status != ScanStageExecutionStatus.NOT_APPLICABLE
    ):
        raise ValueError("not-applicable stage cannot record an execution result")
    if (
        requirement.classification != StageRequirementClassification.NOT_APPLICABLE
        and status == ScanStageExecutionStatus.NOT_APPLICABLE
    ):
        raise ValueError("applicable stage cannot be marked not applicable")
    repository = ScanOrchestrationRepository(db)
    run = db.get(ScanOrchestrationRun, orchestration_run_id)
    if run is None or run.status != OrchestrationRunStatus.RUNNING.value:
        raise ValueError("orchestration run is not writable")
    _require_matching_plan(run, plan)
    _validate_source_reference(db, run.scan_id, stage, source_reference)
    values = dict(
        orchestration_run_id=run.id,
        stage_id=stage.value,
        stage_authority=requirement.classification.value,
        execution_order=requirement.order,
        status=status.value,
        started_at=started_at or _now(),
        completed_at=_now(),
        safe_failure_category=_safe_token(safe_failure_category),
        source_run_reference=source_reference,
        diagnostic_summary=_bounded_summary(diagnostic_summary),
    )
    existing = repository.stage_for_run(run.id, stage.value)
    if existing is not None:
        comparable = (
            existing.stage_authority,
            existing.execution_order,
            existing.status,
            existing.safe_failure_category,
            existing.source_run_reference,
            existing.diagnostic_summary,
        )
        requested = (
            values["stage_authority"],
            values["execution_order"],
            values["status"],
            values["safe_failure_category"],
            values["source_run_reference"],
            values["diagnostic_summary"],
        )
        if comparable != requested:
            raise ValueError("orchestration stage history is immutable")
        return existing
    row = repository.add_stage(**values)
    db.commit()
    return row


def complete_scan_orchestration(
    db,
    *,
    orchestration_run_id: int,
    plan: ScanOrchestrationPlan,
) -> PersistedScanOrchestration:
    repository = ScanOrchestrationRepository(db)
    run = db.get(ScanOrchestrationRun, orchestration_run_id)
    if run is None:
        raise ValueError("orchestration run does not exist")
    _require_matching_plan(run, plan)
    if run.status != OrchestrationRunStatus.RUNNING.value:
        rows = repository.stages_for_run(run.id)
        outcome = _evaluate(plan, rows)
        return PersistedScanOrchestration(run.id, run.status, True, outcome)
    existing = {row.stage_id for row in repository.stages_for_run(run.id)}
    for requirement in plan.stage_requirements:
        if requirement.stage.value in existing:
            continue
        status = (
            ScanStageExecutionStatus.NOT_APPLICABLE
            if requirement.classification
            == StageRequirementClassification.NOT_APPLICABLE
            else ScanStageExecutionStatus.SKIPPED
        )
        record_scan_stage_result(
            db,
            orchestration_run_id=run.id,
            plan=plan,
            stage=requirement.stage,
            status=status,
        )
    rows = repository.stages_for_run(run.id)
    outcome = _evaluate(plan, rows)
    run = db.get(ScanOrchestrationRun, run.id)
    run.primary_identity_ready = outcome.primary_identity_ready
    run.compatibility_projection_ready = outcome.compatibility_projection_ready
    run.visible_product_ready = outcome.visible_product_ready
    run.shadow_diagnostics_ready = outcome.shadow_diagnostics_ready
    run.safe_failure_category = (
        outcome.safe_failure_category.value if outcome.safe_failure_category else None
    )
    run.status = (
        OrchestrationRunStatus.COMPLETED.value
        if outcome.visible_product_ready
        else OrchestrationRunStatus.FAILED.value
    )
    run.completed_at = _now()
    db.commit()
    return PersistedScanOrchestration(run.id, run.status, False, outcome)


def fail_scan_orchestration_audit(db, *, orchestration_run_id: int):
    """Fail closed when stage audit persistence itself cannot be completed."""
    db.rollback()
    run = db.get(ScanOrchestrationRun, orchestration_run_id)
    if run is None:
        return None
    if run.status == OrchestrationRunStatus.RUNNING.value:
        run.primary_identity_ready = False
        run.compatibility_projection_ready = False
        run.visible_product_ready = False
        run.shadow_diagnostics_ready = False
        run.safe_failure_category = "CONFIGURATION_INVALID"
        run.status = OrchestrationRunStatus.FAILED.value
        run.completed_at = _now()
        db.commit()
    return run


def _evaluate(plan, rows):
    return evaluate_persisted_orchestration_outcome(
        plan,
        tuple(
            ScanStageResult(
                stage=ScanStage(row.stage_id),
                succeeded=row.status == ScanStageExecutionStatus.SUCCEEDED.value,
                safe_failure_category=row.safe_failure_category,
                skipped=row.status == ScanStageExecutionStatus.SKIPPED.value,
            )
            for row in rows
        ),
    )
