import inspect
from pathlib import Path

import pytest

from app.identity_read.authority import determine_identity_read_authority
from app.identity_read.contracts import (
    IdentityReadAuthorityContext,
    IdentityReadProjectionAvailability,
    IdentityReadProjectionContract,
)
from app.orchestration.contracts import (
    ScanOrchestrationMode,
    ScanStage,
    ScanStageResult,
    StageRequirementClassification,
    VisibleProjectionContract,
)
from app.orchestration.pair_path_deprecation import (
    HISTORICAL_ORCHESTRATION_POLICY_VERSION,
    POST_GF9_ORCHESTRATION_POLICY_VERSION,
    PAIR_PATH_DEPENDENCIES,
    PairDiagnosticsAvailability,
    PairPathDependencyClass,
    PairPathDependencyKind,
    build_orchestration_plan_for_persisted_policy,
    build_post_gf9_orchestration_plan,
    evaluate_persisted_orchestration_outcome,
    evaluate_post_gf9_orchestration_outcome,
    pair_diagnostics_state,
    pair_path_write_policy,
    post_gf9_orchestration_policy,
    validate_pair_path_dependency_inventory,
)


def requirements(plan):
    return {item.stage: item.classification for item in plan.stage_requirements}


def successful_results(plan, *failed):
    failed = set(failed)
    return tuple(
        ScanStageResult(item.stage, item.stage not in failed)
        for item in plan.stage_requirements
        if item.classification != StageRequirementClassification.NOT_APPLICABLE
    )


def availability(contract, status="COMPLETED"):
    return IdentityReadProjectionAvailability(
        projection_contract=contract,
        scan_id=41,
        source_projection_run_id=101 if contract == IdentityReadProjectionContract.G2_V1 else 202,
        status=status,
        snapshot_valid=True,
        provenance_compatible=True,
    )


def test_d1_policy_v1_group_first_historical_plan_retains_compatibility_stages():
    plan = build_orchestration_plan_for_persisted_policy(
        HISTORICAL_ORCHESTRATION_POLICY_VERSION,
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY,
    )
    assert requirements(plan)[ScanStage.LEGACY_PAIR_COMPATIBILITY] == StageRequirementClassification.COMPATIBILITY_REQUIRED
    assert requirements(plan)[ScanStage.G1_COMPATIBILITY_PROJECTION] == StageRequirementClassification.COMPATIBILITY_REQUIRED
    assert requirements(plan)[ScanStage.G2_V1_COMPATIBILITY_PROJECTION] == StageRequirementClassification.COMPATIBILITY_REQUIRED


def test_d2_policy_v2_group_first_marks_pair_g1_v1_not_applicable():
    plan = build_post_gf9_orchestration_plan(post_gf9_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    for stage in (
        ScanStage.LEGACY_PAIR_COMPATIBILITY,
        ScanStage.G1_COMPATIBILITY_PROJECTION,
        ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
    ):
        assert requirements(plan)[stage] == StageRequirementClassification.NOT_APPLICABLE


def test_d3_policy_v2_group_first_visible_projection_is_g2_v2():
    policy = post_gf9_orchestration_policy(ScanOrchestrationMode.GROUP_FIRST_PRIMARY)
    assert policy.policy_version == POST_GF9_ORCHESTRATION_POLICY_VERSION
    assert policy.visible_projection_contract == VisibleProjectionContract.G2_V2
    assert policy.compatibility_projection_required is False


@pytest.mark.parametrize("failed", (
    ScanStage.CANONICAL_CATALOG,
    ScanStage.DISCOVERY,
    ScanStage.SIGNED_EVIDENCE,
    ScanStage.GROUP_RESOLUTION,
    ScanStage.G2_V2_PROJECTION,
))
def test_d4_policy_v2_group_first_readiness_depends_only_on_gf1_through_gf6(failed):
    plan = build_post_gf9_orchestration_plan(post_gf9_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    ready = evaluate_post_gf9_orchestration_outcome(plan, successful_results(plan))
    not_ready = evaluate_post_gf9_orchestration_outcome(
        plan, successful_results(plan, failed)
    )
    assert ready.primary_identity_ready is ready.visible_product_ready is True
    assert ready.compatibility_projection_ready is True
    assert not_ready.primary_identity_ready is not_ready.visible_product_ready is False


def test_d4_skipped_required_group_first_stage_is_not_ready():
    plan = build_post_gf9_orchestration_plan(post_gf9_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    results = tuple(
        ScanStageResult(
            item.stage,
            item.stage != ScanStage.GROUP_RESOLUTION,
            skipped=item.stage == ScanStage.GROUP_RESOLUTION,
        )
        for item in plan.stage_requirements
        if item.classification != StageRequirementClassification.NOT_APPLICABLE
    )
    outcome = evaluate_post_gf9_orchestration_outcome(plan, results)
    assert outcome.primary_identity_ready is False
    assert outcome.visible_product_ready is False


def test_d5_policy_v2_group_first_shadow_is_not_applicable():
    plan = build_post_gf9_orchestration_plan(post_gf9_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    assert requirements(plan)[ScanStage.SHADOW_COMPARISON] == StageRequirementClassification.NOT_APPLICABLE
    assert evaluate_post_gf9_orchestration_outcome(
        plan, successful_results(plan)
    ).shadow_diagnostics_ready is True


def test_d6_policy_v2_legacy_primary_preserves_pair_g1_v1_behavior():
    policy = post_gf9_orchestration_policy(
        ScanOrchestrationMode.LEGACY_PRIMARY,
        shadow_comparison_enabled=True,
    )
    plan = build_post_gf9_orchestration_plan(policy)
    stage_map = requirements(plan)
    assert policy.visible_projection_contract == VisibleProjectionContract.G2_V1
    assert policy.compatibility_projection_required is True
    for stage in (
        ScanStage.LEGACY_PAIR_COMPATIBILITY,
        ScanStage.G1_COMPATIBILITY_PROJECTION,
        ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
    ):
        assert stage_map[stage] == StageRequirementClassification.PRIMARY_REQUIRED
    assert stage_map[ScanStage.SHADOW_COMPARISON] == StageRequirementClassification.OPTIONAL_DIAGNOSTIC


def test_d7_d8_pair_write_policies_disable_group_first_and_preserve_legacy():
    group_first = pair_path_write_policy(ScanOrchestrationMode.GROUP_FIRST_PRIMARY)
    legacy = pair_path_write_policy(
        ScanOrchestrationMode.LEGACY_PRIMARY,
        shadow_comparison_enabled=True,
    )
    assert (group_first.write_legacy_pairs, group_first.write_g1_projection,
            group_first.write_g2_v1_projection, group_first.run_shadow_comparison) == (
        False, False, False, False
    )
    assert group_first.pair_diagnostics_available_for_new_scan is False
    assert group_first.legacy_numeric_group_routes_authoritative is False
    assert (legacy.write_legacy_pairs, legacy.write_g1_projection,
            legacy.write_g2_v1_projection, legacy.run_shadow_comparison) == (
        True, True, True, True
    )
    assert legacy.pair_diagnostics_available_for_new_scan is True
    assert legacy.legacy_numeric_group_routes_authoritative is True
    assert len(group_first.fingerprint) == len(legacy.fingerprint) == 64


def test_d9_group_first_diagnostics_are_not_generated_not_zero():
    state = pair_diagnostics_state(pair_path_write_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ), generated_candidate_count=0)
    assert state.availability == PairDiagnosticsAvailability.NOT_GENERATED_NOT_APPLICABLE
    assert state.candidate_pair_count is None
    generated_zero = pair_diagnostics_state(pair_path_write_policy(
        ScanOrchestrationMode.LEGACY_PRIMARY
    ), generated_candidate_count=0)
    assert generated_zero.availability == PairDiagnosticsAvailability.GENERATED_AVAILABLE
    assert generated_zero.candidate_pair_count == 0


def test_d10_shadow_absence_for_policy_v2_group_first_is_not_failure():
    plan = build_post_gf9_orchestration_plan(post_gf9_orchestration_policy(
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    ))
    outcome = evaluate_post_gf9_orchestration_outcome(plan, successful_results(plan))
    assert outcome.shadow_diagnostics_ready is True
    assert outcome.failed_optional_stages == ()
    assert outcome.safe_failure_category is None


def test_d11_gf9_read_authority_remains_persisted_mode_based():
    group_first = determine_identity_read_authority(IdentityReadAuthorityContext(
        scan_id=41,
        orchestration_run_id=1,
        persisted_orchestration_mode="group_first_primary",
        orchestration_status="COMPLETED",
        v1_projection=availability(IdentityReadProjectionContract.G2_V1),
        v2_projection=availability(IdentityReadProjectionContract.G2_V2),
    ))
    legacy = determine_identity_read_authority(IdentityReadAuthorityContext(
        scan_id=41,
        orchestration_run_id=2,
        persisted_orchestration_mode="legacy_primary",
        orchestration_status="COMPLETED",
        v1_projection=availability(IdentityReadProjectionContract.G2_V1),
        v2_projection=availability(IdentityReadProjectionContract.G2_V2),
    ))
    assert group_first.projection_contract == IdentityReadProjectionContract.G2_V2
    assert legacy.projection_contract == IdentityReadProjectionContract.G2_V1


def test_d12_current_policy_cannot_reinterpret_historical_policy_v1_audit():
    historical = build_orchestration_plan_for_persisted_policy(
        HISTORICAL_ORCHESTRATION_POLICY_VERSION,
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY,
    )
    current = build_orchestration_plan_for_persisted_policy(
        POST_GF9_ORCHESTRATION_POLICY_VERSION,
        ScanOrchestrationMode.GROUP_FIRST_PRIMARY,
    )
    historical_outcome = evaluate_persisted_orchestration_outcome(
        historical,
        successful_results(historical, ScanStage.G2_V1_COMPATIBILITY_PROJECTION),
    )
    current_outcome = evaluate_persisted_orchestration_outcome(
        current, successful_results(current)
    )
    assert historical.policy.policy_version == HISTORICAL_ORCHESTRATION_POLICY_VERSION
    assert historical_outcome.visible_product_ready is False
    assert current.policy.policy_version == POST_GF9_ORCHESTRATION_POLICY_VERSION
    assert current_outcome.visible_product_ready is True


def test_dependency_manifest_has_no_authoritative_or_allowed_write_dependency():
    validate_pair_path_dependency_inventory()
    assert not [
        item for item in PAIR_PATH_DEPENDENCIES
        if item.classification == PairPathDependencyClass.AUTHORITATIVE_REQUIRED
    ]
    write_kinds = {
        PairPathDependencyKind.PAIR_WRITE,
        PairPathDependencyKind.G1_WRITE,
        PairPathDependencyKind.G2_V1_WRITE,
    }
    assert not [
        item for item in PAIR_PATH_DEPENDENCIES
        if item.dependency_kind in write_kinds
        and item.allowed_in_group_first_policy_v2
    ]
    assert {
        item.dependency_kind for item in PAIR_PATH_DEPENDENCIES
        if item.classification == PairPathDependencyClass.TEST_ONLY
    } == set(PairPathDependencyKind)
    assert not [
        item for item in PAIR_PATH_DEPENDENCIES
        if item.classification == PairPathDependencyClass.MIGRATION_SHADOW_ONLY
        and item.allowed_in_group_first_policy_v2
    ]


def test_every_direct_runtime_pair_g1_v1_source_module_is_classified():
    backend = Path(__file__).resolve().parents[1]
    roots = tuple(backend / "app" / name for name in (
        "api", "engine", "repositories", "services"
    ))
    markers = (
        "DuplicateCandidate",
        "IdentityGroupProjectionRun",
        "project_identity_groups",
        "project_and_persist_identity_groups",
    )
    discovered = {
        path.relative_to(backend.parent).as_posix()
        for root in roots
        for path in root.rglob("*.py")
        if any(marker in path.read_text(encoding="utf-8") for marker in markers)
    }
    classified = {item.source_file for item in PAIR_PATH_DEPENDENCIES}
    assert discovered <= classified, f"unclassified pair-path modules: {sorted(discovered - classified)}"


def test_gf9_product_g6_g7_v2_paths_do_not_require_pair_g1_or_v1():
    from app.services import group_llm_eligibility, identity_group_review_service
    from app.services import identity_read_service

    read_source = inspect.getsource(identity_read_service.IdentityReadService)
    review_source = inspect.getsource(
        identity_group_review_service.VersionedIdentityGroupReviewService
    )
    advisory_source = inspect.getsource(
        group_llm_eligibility.GroupAdvisoryContractService.load_authoritative
    ) + inspect.getsource(
        group_llm_eligibility.GroupAdvisoryContractService.build_request_for_versioned_group
    )
    assert "IdentityReadService" in review_source
    assert "IdentityReadService" in advisory_source
    assert "DuplicateCandidate" not in read_source + review_source + advisory_source
    assert "project_identity_groups" not in read_source + advisory_source
    assert "IDENTITY_ORCHESTRATION_MODE" not in read_source


def test_gf10b_runner_consumes_frozen_policy_and_write_guards():
    from app.orchestration import pair_path_deprecation
    from app.services import scan_runner

    contract_source = inspect.getsource(pair_path_deprecation)
    runner_source = inspect.getsource(scan_runner)
    assert not any(token in contract_source for token in (
        "sqlalchemy", "Session", "app.db", "create_llm_provider", ".env"
    ))
    assert "pair_path_deprecation" in runner_source
    assert "post_gf9_orchestration_policy(" in runner_source
    assert "build_post_gf9_orchestration_plan(" in runner_source
    assert "pair_path_write_policy(" in runner_source
    assert "if write_policy.write_legacy_pairs:" in runner_source
    assert "if write_policy.write_g1_projection and write_policy.write_g2_v1_projection:" in runner_source
    assert "write_policy.run_shadow_comparison" in runner_source
