import dataclasses
import inspect
from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.orchestration.contracts import (
    OrchestrationConfigurationError,
    OrchestrationFailureCategory,
    PrimaryIdentityPipeline,
    ScanOrchestrationMode,
    ScanOrchestrationPolicy,
    ScanStage,
    ScanStageResult,
    StageRequirementClassification,
    VisibleProjectionContract,
)
from app.orchestration.planning import (
    build_scan_orchestration_plan,
    evaluate_scan_orchestration_outcome,
    scan_orchestration_policy,
)


def results_for(plan, *failed):
    failed = set(failed)
    return tuple(
        ScanStageResult(item.stage, item.stage not in failed)
        for item in plan.stage_requirements
        if item.classification != StageRequirementClassification.NOT_APPLICABLE
    )


def requirement_map(plan):
    return {
        item.stage: item.classification for item in plan.stage_requirements
    }


def test_o1_legacy_primary_all_success_preserves_current_readiness():
    policy = scan_orchestration_policy(ScanOrchestrationMode.LEGACY_PRIMARY)
    plan = build_scan_orchestration_plan(policy)
    outcome = evaluate_scan_orchestration_outcome(plan, results_for(plan))
    requirements = requirement_map(plan)
    assert policy.primary_identity_pipeline == PrimaryIdentityPipeline.LEGACY_PAIR_G1
    assert requirements[ScanStage.LEGACY_PAIR_COMPATIBILITY] == StageRequirementClassification.PRIMARY_REQUIRED
    assert requirements[ScanStage.G1_COMPATIBILITY_PROJECTION] == StageRequirementClassification.PRIMARY_REQUIRED
    assert requirements[ScanStage.G2_V1_COMPATIBILITY_PROJECTION] == StageRequirementClassification.PRIMARY_REQUIRED
    assert requirements[ScanStage.GROUP_RESOLUTION] == StageRequirementClassification.OPTIONAL_DIAGNOSTIC
    assert requirements[ScanStage.G2_V2_PROJECTION] == StageRequirementClassification.OPTIONAL_DIAGNOSTIC
    assert outcome.primary_identity_ready is True
    assert outcome.compatibility_projection_ready is True
    assert outcome.visible_product_ready is True
    assert outcome.safe_failure_category is None


def test_o2_group_first_primary_all_success_requires_both_authorities():
    policy = scan_orchestration_policy(ScanOrchestrationMode.GROUP_FIRST_PRIMARY)
    plan = build_scan_orchestration_plan(policy)
    outcome = evaluate_scan_orchestration_outcome(plan, results_for(plan))
    assert policy.primary_identity_pipeline == PrimaryIdentityPipeline.GROUP_FIRST_GF1_GF6
    assert outcome.primary_identity_ready is True
    assert outcome.compatibility_projection_ready is True
    assert outcome.visible_product_ready is True


@pytest.mark.parametrize(
    "stage",
    (ScanStage.GROUP_RESOLUTION, ScanStage.G2_V2_PROJECTION),
    ids=("O3-gf5", "O4-gf6"),
)
def test_o3_o4_group_first_failure_cannot_be_substituted_by_legacy_success(stage):
    plan = build_scan_orchestration_plan(scan_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    outcome = evaluate_scan_orchestration_outcome(
        plan, results_for(plan, stage)
    )
    assert outcome.primary_identity_ready is False
    assert outcome.compatibility_projection_ready is True
    assert outcome.visible_product_ready is False
    assert outcome.failed_primary_stages == (stage,)
    assert outcome.failed_compatibility_stages == ()
    assert outcome.safe_failure_category == OrchestrationFailureCategory.PRIMARY_IDENTITY_FAILED


def test_o5_compatibility_g2_v1_failure_is_distinct_from_primary_failure():
    plan = build_scan_orchestration_plan(scan_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    outcome = evaluate_scan_orchestration_outcome(
        plan,
        results_for(plan, ScanStage.G2_V1_COMPATIBILITY_PROJECTION),
    )
    assert outcome.primary_identity_ready is True
    assert outcome.compatibility_projection_ready is False
    assert outcome.visible_product_ready is False
    assert outcome.failed_primary_stages == ()
    assert outcome.failed_compatibility_stages == (
        ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
    )
    assert outcome.safe_failure_category == OrchestrationFailureCategory.COMPATIBILITY_OUTPUT_FAILED


def test_o6_shadow_failure_is_optional_and_does_not_block_visible_readiness():
    plan = build_scan_orchestration_plan(scan_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY,
        shadow_comparison_enabled=True,
    ))
    outcome = evaluate_scan_orchestration_outcome(
        plan, results_for(plan, ScanStage.SHADOW_COMPARISON)
    )
    assert outcome.primary_identity_ready is True
    assert outcome.compatibility_projection_ready is True
    assert outcome.visible_product_ready is True
    assert outcome.shadow_diagnostics_ready is False
    assert outcome.failed_optional_stages == (ScanStage.SHADOW_COMPARISON,)
    assert outcome.safe_failure_category == OrchestrationFailureCategory.OPTIONAL_DIAGNOSTIC_FAILED


def test_o7_shadow_disabled_is_not_applicable_and_needs_no_result():
    plan = build_scan_orchestration_plan(scan_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY,
        shadow_comparison_enabled=False,
    ))
    assert requirement_map(plan)[ScanStage.SHADOW_COMPARISON] == StageRequirementClassification.NOT_APPLICABLE
    outcome = evaluate_scan_orchestration_outcome(plan, results_for(plan))
    assert outcome.shadow_diagnostics_ready is True
    assert outcome.failed_optional_stages == ()
    assert outcome.visible_product_ready is True


def test_o8_invalid_mode_fails_configuration_and_never_promotes(monkeypatch):
    with pytest.raises(OrchestrationConfigurationError) as error:
        scan_orchestration_policy("automatic_from_shadow_metrics")
    assert error.value.failure_category == OrchestrationFailureCategory.CONFIGURATION_INVALID
    monkeypatch.setenv("IDENTITY_ORCHESTRATION_MODE", "invalid")
    with pytest.raises(ValidationError):
        Settings()


def test_o9_plan_order_and_fingerprints_are_deterministic():
    policy = scan_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY,
        shadow_comparison_enabled=True,
    )
    first = build_scan_orchestration_plan(policy)
    second = build_scan_orchestration_plan(policy)
    assert first == second
    assert len(first.policy_fingerprint) == len(first.plan_fingerprint) == 64
    assert tuple(item.order for item in first.stage_requirements) == tuple(range(9))
    assert tuple(item.stage for item in first.stage_requirements) == tuple(ScanStage)


def test_o10_arbitrary_shadow_metrics_cannot_affect_mode_or_plan():
    metrics = (
        {"positive_pair_jaccard": 1.0, "critical_case_count": 0},
        {"positive_pair_jaccard": 0.0, "critical_case_count": 999},
    )
    plans = []
    for _ignored_metrics in metrics:
        plans.append(build_scan_orchestration_plan(scan_orchestration_policy(
            ScanOrchestrationMode.LEGACY_PRIMARY
        )))
    assert plans[0] == plans[1]
    assert plans[0].policy.mode == ScanOrchestrationMode.LEGACY_PRIMARY


def test_group_first_pre_gf9_stage_classification_is_exact():
    plan = build_scan_orchestration_plan(scan_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    assert requirement_map(plan) == {
        ScanStage.CANONICAL_CATALOG: StageRequirementClassification.PRIMARY_REQUIRED,
        ScanStage.DISCOVERY: StageRequirementClassification.PRIMARY_REQUIRED,
        ScanStage.SIGNED_EVIDENCE: StageRequirementClassification.PRIMARY_REQUIRED,
        ScanStage.GROUP_RESOLUTION: StageRequirementClassification.PRIMARY_REQUIRED,
        ScanStage.G2_V2_PROJECTION: StageRequirementClassification.PRIMARY_REQUIRED,
        ScanStage.LEGACY_PAIR_COMPATIBILITY: StageRequirementClassification.COMPATIBILITY_REQUIRED,
        ScanStage.G1_COMPATIBILITY_PROJECTION: StageRequirementClassification.COMPATIBILITY_REQUIRED,
        ScanStage.G2_V1_COMPATIBILITY_PROJECTION: StageRequirementClassification.COMPATIBILITY_REQUIRED,
        ScanStage.SHADOW_COMPARISON: StageRequirementClassification.NOT_APPLICABLE,
    }


def test_visible_projection_is_frozen_to_g2_v1_in_every_mode():
    for mode in ScanOrchestrationMode:
        policy = scan_orchestration_policy(mode)
        plan = build_scan_orchestration_plan(policy)
        assert policy.visible_projection_contract == VisibleProjectionContract.G2_V1
        assert policy.compatibility_projection_required is True
        assert plan.policy.visible_projection_contract == VisibleProjectionContract.G2_V1


def test_legacy_gf5_gf6_failure_policy_remains_optional_but_gf4_is_required():
    plan = build_scan_orchestration_plan(scan_orchestration_policy())
    optional = evaluate_scan_orchestration_outcome(
        plan,
        results_for(plan, ScanStage.GROUP_RESOLUTION, ScanStage.G2_V2_PROJECTION),
    )
    required = evaluate_scan_orchestration_outcome(
        plan, results_for(plan, ScanStage.SIGNED_EVIDENCE)
    )
    assert optional.visible_product_ready is True
    assert optional.failed_optional_stages == (
        ScanStage.GROUP_RESOLUTION,
        ScanStage.G2_V2_PROJECTION,
    )
    assert required.primary_identity_ready is False
    assert required.visible_product_ready is False


def test_multiple_required_failure_category_is_explicit():
    plan = build_scan_orchestration_plan(scan_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    outcome = evaluate_scan_orchestration_outcome(plan, results_for(
        plan,
        ScanStage.GROUP_RESOLUTION,
        ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
    ))
    assert outcome.safe_failure_category == OrchestrationFailureCategory.MULTIPLE_REQUIRED_STAGE_FAILURES


def test_policy_contracts_are_frozen_and_inconsistent_policy_fails_closed():
    policy = scan_orchestration_policy()
    assert dataclasses.is_dataclass(ScanOrchestrationPolicy)
    assert ScanOrchestrationPolicy.__dataclass_params__.frozen is True
    with pytest.raises(OrchestrationConfigurationError):
        build_scan_orchestration_plan(replace(
            policy,
            primary_identity_pipeline=PrimaryIdentityPipeline.GROUP_FIRST_GF1_GF6,
        ))
    with pytest.raises(OrchestrationConfigurationError):
        build_scan_orchestration_plan(replace(
            policy,
            shadow_comparison_required_for_scan_success=True,
        ))


def test_default_configuration_is_legacy_and_contract_package_is_isolated(monkeypatch):
    monkeypatch.delenv("IDENTITY_ORCHESTRATION_MODE", raising=False)
    assert Settings().identity_orchestration_mode == "legacy_primary"
    import app.orchestration.contracts as contracts
    import app.orchestration.planning as planning

    source = inspect.getsource(contracts) + inspect.getsource(planning)
    forbidden = (
        "sqlalchemy", "Session", "Repository", "scan_runner",
        "IdentityGroupQueryService", "FastAPI", "APIRouter", "frontend",
        "export_service", "review_service", "create_llm_provider",
        "ShadowComparisonResult", "positive_pair_jaccard", "critical_case_count",
    )
    assert not any(value in source for value in forbidden)
