"""Pure deterministic GF-8A policy planning and readiness evaluation."""

from __future__ import annotations

import hashlib
import json

from app.orchestration.contracts import (
    SCAN_ORCHESTRATION_POLICY_VERSION,
    OrchestrationConfigurationError,
    OrchestrationFailureCategory,
    PrimaryIdentityPipeline,
    ScanOrchestrationMode,
    ScanOrchestrationOutcome,
    ScanOrchestrationPlan,
    ScanOrchestrationPolicy,
    ScanStage,
    ScanStageRequirement,
    ScanStageResult,
    StageRequirementClassification,
    VisibleProjectionContract,
)


_STAGE_ORDER = tuple(ScanStage)


def _fingerprint(kind: str, value) -> str:
    payload = json.dumps(
        {
            "contract": SCAN_ORCHESTRATION_POLICY_VERSION,
            "kind": kind,
            "value": value,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def scan_orchestration_policy(
    mode: ScanOrchestrationMode | str = ScanOrchestrationMode.LEGACY_PRIMARY,
    *,
    shadow_comparison_enabled: bool = False,
) -> ScanOrchestrationPolicy:
    """Build one allowlisted pre-GF-9 policy; invalid modes fail closed."""
    try:
        mode = ScanOrchestrationMode(mode)
    except (TypeError, ValueError) as error:
        raise OrchestrationConfigurationError(
            "invalid identity orchestration mode"
        ) from error
    group_first = mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    return ScanOrchestrationPolicy(
        mode=mode,
        policy_version=SCAN_ORCHESTRATION_POLICY_VERSION,
        primary_identity_pipeline=(
            PrimaryIdentityPipeline.GROUP_FIRST_GF1_GF6
            if group_first
            else PrimaryIdentityPipeline.LEGACY_PAIR_G1
        ),
        visible_projection_contract=VisibleProjectionContract.G2_V1,
        compatibility_projection_required=True,
        require_gf1_catalog=True,
        require_gf2_gf3_discovery=True,
        require_gf4_evidence=True,
        require_gf5_resolution=group_first,
        require_gf6_v2_projection=group_first,
        require_legacy_pair_persistence=True,
        require_g1_projection=True,
        require_g2_v1_compatibility_projection=True,
        shadow_comparison_enabled=bool(shadow_comparison_enabled),
        shadow_comparison_required_for_scan_success=False,
    )


def _validate_policy(policy: ScanOrchestrationPolicy) -> None:
    if not isinstance(policy, ScanOrchestrationPolicy):
        raise OrchestrationConfigurationError("orchestration policy is invalid")
    if not isinstance(policy.mode, ScanOrchestrationMode):
        raise OrchestrationConfigurationError("orchestration mode is invalid")
    expected = scan_orchestration_policy(
        policy.mode,
        shadow_comparison_enabled=policy.shadow_comparison_enabled,
    )
    if policy != expected:
        raise OrchestrationConfigurationError(
            "orchestration policy differs from the frozen pre-GF-9 contract"
        )
    if policy.visible_projection_contract != VisibleProjectionContract.G2_V1:
        raise OrchestrationConfigurationError(
            "GF-8A visible projection must remain G2-v1"
        )
    if policy.shadow_comparison_required_for_scan_success:
        raise OrchestrationConfigurationError(
            "shadow comparison cannot become required in GF-8A"
        )


def _classifications(policy: ScanOrchestrationPolicy):
    primary = StageRequirementClassification.PRIMARY_REQUIRED
    compatibility = StageRequirementClassification.COMPATIBILITY_REQUIRED
    optional = StageRequirementClassification.OPTIONAL_DIAGNOSTIC
    not_applicable = StageRequirementClassification.NOT_APPLICABLE
    if policy.mode == ScanOrchestrationMode.LEGACY_PRIMARY:
        return {
            ScanStage.CANONICAL_CATALOG: primary,
            ScanStage.DISCOVERY: primary,
            ScanStage.SIGNED_EVIDENCE: primary,
            ScanStage.GROUP_RESOLUTION: optional,
            ScanStage.G2_V2_PROJECTION: optional,
            ScanStage.LEGACY_PAIR_COMPATIBILITY: primary,
            ScanStage.G1_COMPATIBILITY_PROJECTION: primary,
            ScanStage.G2_V1_COMPATIBILITY_PROJECTION: primary,
            ScanStage.SHADOW_COMPARISON: (
                optional if policy.shadow_comparison_enabled else not_applicable
            ),
        }
    return {
        ScanStage.CANONICAL_CATALOG: primary,
        ScanStage.DISCOVERY: primary,
        ScanStage.SIGNED_EVIDENCE: primary,
        ScanStage.GROUP_RESOLUTION: primary,
        ScanStage.G2_V2_PROJECTION: primary,
        ScanStage.LEGACY_PAIR_COMPATIBILITY: compatibility,
        ScanStage.G1_COMPATIBILITY_PROJECTION: compatibility,
        ScanStage.G2_V1_COMPATIBILITY_PROJECTION: compatibility,
        ScanStage.SHADOW_COMPARISON: (
            optional if policy.shadow_comparison_enabled else not_applicable
        ),
    }


def build_scan_orchestration_plan(
    policy: ScanOrchestrationPolicy,
) -> ScanOrchestrationPlan:
    """Create a stable stage-authority plan without executing any stage."""
    _validate_policy(policy)
    classifications = _classifications(policy)
    requirements = tuple(
        ScanStageRequirement(stage, classifications[stage], order)
        for order, stage in enumerate(_STAGE_ORDER)
    )
    policy_payload = {
        "mode": policy.mode.value,
        "policy_version": policy.policy_version,
        "primary_identity_pipeline": policy.primary_identity_pipeline.value,
        "visible_projection_contract": policy.visible_projection_contract.value,
        "compatibility_projection_required": policy.compatibility_projection_required,
        "requirements": {
            "gf1": policy.require_gf1_catalog,
            "gf2_gf3": policy.require_gf2_gf3_discovery,
            "gf4": policy.require_gf4_evidence,
            "gf5": policy.require_gf5_resolution,
            "gf6": policy.require_gf6_v2_projection,
            "legacy_pairs": policy.require_legacy_pair_persistence,
            "g1": policy.require_g1_projection,
            "g2_v1": policy.require_g2_v1_compatibility_projection,
            "shadow_enabled": policy.shadow_comparison_enabled,
            "shadow_required": policy.shadow_comparison_required_for_scan_success,
        },
    }
    policy_fingerprint = _fingerprint("scan-orchestration-policy", policy_payload)
    plan_fingerprint = _fingerprint("scan-orchestration-plan", {
        "policy_fingerprint": policy_fingerprint,
        "stages": tuple(
            (item.order, item.stage.value, item.classification.value)
            for item in requirements
        ),
    })
    return ScanOrchestrationPlan(
        policy=policy,
        stage_requirements=requirements,
        policy_fingerprint=policy_fingerprint,
        plan_fingerprint=plan_fingerprint,
    )


def evaluate_scan_orchestration_outcome(
    plan: ScanOrchestrationPlan,
    stage_results: tuple[ScanStageResult, ...],
) -> ScanOrchestrationOutcome:
    """Evaluate readiness from categorical stage outcomes only."""
    if not isinstance(plan, ScanOrchestrationPlan):
        raise OrchestrationConfigurationError("orchestration plan is invalid")
    if build_scan_orchestration_plan(plan.policy) != plan:
        raise OrchestrationConfigurationError("orchestration plan fingerprint is invalid")
    results = {}
    for result in stage_results:
        if not isinstance(result, ScanStageResult) or not isinstance(result.stage, ScanStage):
            raise OrchestrationConfigurationError("stage result is invalid")
        if result.stage in results:
            raise OrchestrationConfigurationError("stage result is duplicated")
        results[result.stage] = result

    failed = {
        classification: tuple(
            requirement.stage
            for requirement in plan.stage_requirements
            if requirement.classification == classification
            and (
                not results.get(
                    requirement.stage,
                    ScanStageResult(requirement.stage, False),
                ).succeeded
                and not results.get(
                    requirement.stage,
                    ScanStageResult(requirement.stage, False),
                ).skipped
            )
        )
        for classification in (
            StageRequirementClassification.PRIMARY_REQUIRED,
            StageRequirementClassification.COMPATIBILITY_REQUIRED,
            StageRequirementClassification.OPTIONAL_DIAGNOSTIC,
        )
    }
    failed_primary = failed[StageRequirementClassification.PRIMARY_REQUIRED]
    failed_compatibility = failed[
        StageRequirementClassification.COMPATIBILITY_REQUIRED
    ]
    failed_optional = failed[StageRequirementClassification.OPTIONAL_DIAGNOSTIC]
    primary_ready = not failed_primary
    compatibility_stage = results.get(
        ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
        ScanStageResult(ScanStage.G2_V1_COMPATIBILITY_PROJECTION, False),
    )
    compatibility_ready = (
        not failed_compatibility and compatibility_stage.succeeded
    )
    visible_ready = primary_ready and compatibility_ready
    shadow_requirement = next(
        item for item in plan.stage_requirements
        if item.stage == ScanStage.SHADOW_COMPARISON
    )
    shadow_ready = (
        True
        if shadow_requirement.classification
        == StageRequirementClassification.NOT_APPLICABLE
        else results.get(
            ScanStage.SHADOW_COMPARISON,
            ScanStageResult(ScanStage.SHADOW_COMPARISON, False),
        ).succeeded
    )
    if failed_primary and failed_compatibility:
        category = OrchestrationFailureCategory.MULTIPLE_REQUIRED_STAGE_FAILURES
    elif failed_primary:
        category = OrchestrationFailureCategory.PRIMARY_IDENTITY_FAILED
    elif failed_compatibility or not compatibility_ready:
        category = OrchestrationFailureCategory.COMPATIBILITY_OUTPUT_FAILED
    elif failed_optional:
        category = OrchestrationFailureCategory.OPTIONAL_DIAGNOSTIC_FAILED
    else:
        category = None
    return ScanOrchestrationOutcome(
        mode=plan.policy.mode,
        plan_fingerprint=plan.plan_fingerprint,
        primary_identity_ready=primary_ready,
        compatibility_projection_ready=compatibility_ready,
        visible_product_ready=visible_ready,
        shadow_diagnostics_ready=shadow_ready,
        failed_primary_stages=failed_primary,
        failed_compatibility_stages=failed_compatibility,
        failed_optional_stages=failed_optional,
        safe_failure_category=category,
    )
