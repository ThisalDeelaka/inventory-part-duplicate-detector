"""Pure GF-10A contracts for post-GF-9 pair-path write deprecation.

Nothing in this module is selected by the scan runner.  Policy v1 remains the
runtime contract until GF-10B explicitly wires policy v2 for future scans.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from app.orchestration.contracts import (
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
from app.orchestration.planning import (
    build_scan_orchestration_plan,
    evaluate_scan_orchestration_outcome,
    scan_orchestration_policy,
)


POST_GF9_ORCHESTRATION_POLICY_VERSION = "group-first-orchestration-policy-v2"
HISTORICAL_ORCHESTRATION_POLICY_VERSION = "group-first-orchestration-policy-v1"


class PairPathDependencyClass(str, Enum):
    AUTHORITATIVE_REQUIRED = "AUTHORITATIVE_REQUIRED"
    LEGACY_MODE_REQUIRED = "LEGACY_MODE_REQUIRED"
    HISTORICAL_READ_ONLY = "HISTORICAL_READ_ONLY"
    DIAGNOSTIC_READ_ONLY = "DIAGNOSTIC_READ_ONLY"
    MIGRATION_SHADOW_ONLY = "MIGRATION_SHADOW_ONLY"
    TEST_ONLY = "TEST_ONLY"
    DEPRECATED_WRITE = "DEPRECATED_WRITE"


class PairPathDependencyKind(str, Enum):
    PAIR_WRITE = "PAIR_WRITE"
    PAIR_READ = "PAIR_READ"
    G1_WRITE = "G1_WRITE"
    G1_READ = "G1_READ"
    G2_V1_WRITE = "G2_V1_WRITE"
    G2_V1_READ = "G2_V1_READ"


class PairDiagnosticsAvailability(str, Enum):
    GENERATED_AVAILABLE = "GENERATED_AVAILABLE"
    NOT_GENERATED_NOT_APPLICABLE = "NOT_GENERATED_NOT_APPLICABLE"


@dataclass(frozen=True)
class PairPathDependency:
    component: str
    source_file: str
    dependency_kind: PairPathDependencyKind
    classification: PairPathDependencyClass
    allowed_in_group_first_policy_v2: bool
    reason: str
    replacement_authority: str | None


@dataclass(frozen=True)
class PairPathWritePolicy:
    orchestration_mode: ScanOrchestrationMode
    policy_version: str
    write_legacy_pairs: bool
    write_g1_projection: bool
    write_g2_v1_projection: bool
    run_shadow_comparison: bool
    pair_diagnostics_available_for_new_scan: bool
    legacy_numeric_group_routes_authoritative: bool
    reason: str
    fingerprint: str


@dataclass(frozen=True)
class PairDiagnosticsState:
    availability: PairDiagnosticsAvailability
    candidate_pair_count: int | None
    reason: str


def _fingerprint(kind: str, value) -> str:
    payload = json.dumps(
        {
            "contract": POST_GF9_ORCHESTRATION_POLICY_VERSION,
            "kind": kind,
            "value": value,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def post_gf9_orchestration_policy(
    mode: ScanOrchestrationMode | str,
    *,
    shadow_comparison_enabled: bool = False,
) -> ScanOrchestrationPolicy:
    """Return the frozen policy-v2 contract; this does not activate it."""
    try:
        mode = ScanOrchestrationMode(mode)
    except (TypeError, ValueError) as error:
        raise OrchestrationConfigurationError(
            "invalid identity orchestration mode"
        ) from error
    group_first = mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY
    if group_first and shadow_comparison_enabled:
        raise OrchestrationConfigurationError(
            "policy-v2 group-first scans cannot fabricate v1 for shadow comparison"
        )
    return ScanOrchestrationPolicy(
        mode=mode,
        policy_version=POST_GF9_ORCHESTRATION_POLICY_VERSION,
        primary_identity_pipeline=(
            PrimaryIdentityPipeline.GROUP_FIRST_GF1_GF6
            if group_first
            else PrimaryIdentityPipeline.LEGACY_PAIR_G1
        ),
        visible_projection_contract=(
            VisibleProjectionContract.G2_V2
            if group_first
            else VisibleProjectionContract.G2_V1
        ),
        compatibility_projection_required=not group_first,
        require_gf1_catalog=True,
        require_gf2_gf3_discovery=True,
        require_gf4_evidence=True,
        require_gf5_resolution=group_first,
        require_gf6_v2_projection=group_first,
        require_legacy_pair_persistence=not group_first,
        require_g1_projection=not group_first,
        require_g2_v1_compatibility_projection=not group_first,
        shadow_comparison_enabled=(
            bool(shadow_comparison_enabled) if not group_first else False
        ),
        shadow_comparison_required_for_scan_success=False,
    )


def _policy_v2_classifications(policy: ScanOrchestrationPolicy):
    primary = StageRequirementClassification.PRIMARY_REQUIRED
    optional = StageRequirementClassification.OPTIONAL_DIAGNOSTIC
    not_applicable = StageRequirementClassification.NOT_APPLICABLE
    if policy.mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY:
        return {
            ScanStage.CANONICAL_CATALOG: primary,
            ScanStage.DISCOVERY: primary,
            ScanStage.SIGNED_EVIDENCE: primary,
            ScanStage.GROUP_RESOLUTION: primary,
            ScanStage.G2_V2_PROJECTION: primary,
            ScanStage.LEGACY_PAIR_COMPATIBILITY: not_applicable,
            ScanStage.G1_COMPATIBILITY_PROJECTION: not_applicable,
            ScanStage.G2_V1_COMPATIBILITY_PROJECTION: not_applicable,
            ScanStage.SHADOW_COMPARISON: not_applicable,
        }
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


def build_post_gf9_orchestration_plan(
    policy: ScanOrchestrationPolicy,
) -> ScanOrchestrationPlan:
    expected = post_gf9_orchestration_policy(
        policy.mode,
        shadow_comparison_enabled=policy.shadow_comparison_enabled,
    )
    if policy != expected:
        raise OrchestrationConfigurationError(
            "orchestration policy differs from the frozen post-GF-9 contract"
        )
    classifications = _policy_v2_classifications(policy)
    requirements = tuple(
        ScanStageRequirement(stage, classifications[stage], order)
        for order, stage in enumerate(ScanStage)
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
    plan_fingerprint = _fingerprint(
        "scan-orchestration-plan",
        {
            "policy_fingerprint": policy_fingerprint,
            "stages": tuple(
                (item.order, item.stage.value, item.classification.value)
                for item in requirements
            ),
        },
    )
    return ScanOrchestrationPlan(
        policy=policy,
        stage_requirements=requirements,
        policy_fingerprint=policy_fingerprint,
        plan_fingerprint=plan_fingerprint,
    )


def build_orchestration_plan_for_persisted_policy(
    policy_version: str,
    mode: ScanOrchestrationMode | str,
    *,
    shadow_comparison_enabled: bool = False,
) -> ScanOrchestrationPlan:
    """Reconstruct only the policy generation persisted by an audit row."""
    if policy_version == HISTORICAL_ORCHESTRATION_POLICY_VERSION:
        return build_scan_orchestration_plan(scan_orchestration_policy(
            mode, shadow_comparison_enabled=shadow_comparison_enabled
        ))
    if policy_version == POST_GF9_ORCHESTRATION_POLICY_VERSION:
        return build_post_gf9_orchestration_plan(post_gf9_orchestration_policy(
            mode, shadow_comparison_enabled=shadow_comparison_enabled
        ))
    raise OrchestrationConfigurationError("unknown persisted orchestration policy")


def evaluate_post_gf9_orchestration_outcome(
    plan: ScanOrchestrationPlan,
    stage_results: tuple[ScanStageResult, ...],
) -> ScanOrchestrationOutcome:
    if build_post_gf9_orchestration_plan(plan.policy) != plan:
        raise OrchestrationConfigurationError("orchestration plan fingerprint is invalid")
    results = {}
    for result in stage_results:
        if not isinstance(result, ScanStageResult) or result.stage in results:
            raise OrchestrationConfigurationError("stage result is invalid or duplicated")
        results[result.stage] = result
    failed = {}
    for classification in (
        StageRequirementClassification.PRIMARY_REQUIRED,
        StageRequirementClassification.COMPATIBILITY_REQUIRED,
        StageRequirementClassification.OPTIONAL_DIAGNOSTIC,
    ):
        failed[classification] = tuple(
            item.stage
            for item in plan.stage_requirements
            if item.classification == classification
            and not results.get(item.stage, ScanStageResult(item.stage, False)).succeeded
            and (
                classification
                != StageRequirementClassification.OPTIONAL_DIAGNOSTIC
                or not results.get(
                    item.stage, ScanStageResult(item.stage, False)
                ).skipped
            )
        )
    failed_primary = failed[StageRequirementClassification.PRIMARY_REQUIRED]
    failed_compatibility = failed[
        StageRequirementClassification.COMPATIBILITY_REQUIRED
    ]
    failed_optional = failed[StageRequirementClassification.OPTIONAL_DIAGNOSTIC]
    primary_ready = not failed_primary
    if plan.policy.mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY:
        compatibility_ready = True
        visible_ready = primary_ready
    else:
        v1 = results.get(ScanStage.G2_V1_COMPATIBILITY_PROJECTION)
        compatibility_ready = bool(v1 and v1.succeeded)
        visible_ready = primary_ready and compatibility_ready
    shadow_requirement = next(
        item for item in plan.stage_requirements
        if item.stage == ScanStage.SHADOW_COMPARISON
    )
    shadow_ready = (
        shadow_requirement.classification
        == StageRequirementClassification.NOT_APPLICABLE
        or bool(results.get(ScanStage.SHADOW_COMPARISON)
                and results[ScanStage.SHADOW_COMPARISON].succeeded)
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


def evaluate_persisted_orchestration_outcome(
    plan: ScanOrchestrationPlan,
    stage_results: tuple[ScanStageResult, ...],
) -> ScanOrchestrationOutcome:
    if plan.policy.policy_version == HISTORICAL_ORCHESTRATION_POLICY_VERSION:
        return evaluate_scan_orchestration_outcome(plan, stage_results)
    if plan.policy.policy_version == POST_GF9_ORCHESTRATION_POLICY_VERSION:
        return evaluate_post_gf9_orchestration_outcome(plan, stage_results)
    raise OrchestrationConfigurationError("unknown persisted orchestration policy")


def pair_path_write_policy(
    mode: ScanOrchestrationMode | str,
    *,
    shadow_comparison_enabled: bool = False,
) -> PairPathWritePolicy:
    policy = post_gf9_orchestration_policy(
        mode, shadow_comparison_enabled=shadow_comparison_enabled
    )
    legacy = policy.mode == ScanOrchestrationMode.LEGACY_PRIMARY
    reason = (
        "legacy-primary retains its authoritative pair/G1/G2-v1 compatibility path"
        if legacy
        else "group-first-primary product authority is G2-v2 after GF-9 graduation"
    )
    values = {
        "orchestration_mode": policy.mode.value,
        "policy_version": policy.policy_version,
        "write_legacy_pairs": legacy,
        "write_g1_projection": legacy,
        "write_g2_v1_projection": legacy,
        "run_shadow_comparison": legacy and policy.shadow_comparison_enabled,
        "pair_diagnostics_available_for_new_scan": legacy,
        "legacy_numeric_group_routes_authoritative": legacy,
        "reason": reason,
    }
    return PairPathWritePolicy(
        orchestration_mode=policy.mode,
        policy_version=policy.policy_version,
        write_legacy_pairs=values["write_legacy_pairs"],
        write_g1_projection=values["write_g1_projection"],
        write_g2_v1_projection=values["write_g2_v1_projection"],
        run_shadow_comparison=values["run_shadow_comparison"],
        pair_diagnostics_available_for_new_scan=(
            values["pair_diagnostics_available_for_new_scan"]
        ),
        legacy_numeric_group_routes_authoritative=(
            values["legacy_numeric_group_routes_authoritative"]
        ),
        reason=reason,
        fingerprint=_fingerprint("pair-path-write-policy", values),
    )


def pair_diagnostics_state(
    policy: PairPathWritePolicy,
    *,
    generated_candidate_count: int | None = None,
) -> PairDiagnosticsState:
    if not policy.pair_diagnostics_available_for_new_scan:
        return PairDiagnosticsState(
            PairDiagnosticsAvailability.NOT_GENERATED_NOT_APPLICABLE,
            None,
            "legacy pair diagnostics were not generated for this policy-v2 scan",
        )
    if generated_candidate_count is None or generated_candidate_count < 0:
        raise ValueError("generated pair diagnostics require a non-negative count")
    return PairDiagnosticsState(
        PairDiagnosticsAvailability.GENERATED_AVAILABLE,
        generated_candidate_count,
        "legacy pair diagnostics were generated",
    )


def _dependency(component, source_file, kind, classification, allowed, reason, replacement):
    return PairPathDependency(
        component=component,
        source_file=source_file,
        dependency_kind=kind,
        classification=classification,
        allowed_in_group_first_policy_v2=allowed,
        reason=reason,
        replacement_authority=replacement,
    )


D = PairPathDependencyKind
C = PairPathDependencyClass

# Code-backed inventory of every current service/repository/API module with a
# direct legacy candidate, G1, or G2-v1 dependency.  Multiple entries are used
# where one module has distinct read and write responsibilities.
PAIR_PATH_DEPENDENCIES = (
    _dependency("normal-scan legacy candidate transaction", "backend/app/services/scan_runner.py", D.PAIR_WRITE, C.DEPRECATED_WRITE, False, "GF-8 compatibility writes remain runtime-only until GF-10B", "GF-4 independent evidence"),
    _dependency("normal-scan G1 compatibility projection", "backend/app/services/scan_runner.py", D.G1_WRITE, C.DEPRECATED_WRITE, False, "G1 is not product authority for group-first policy-v2", "GF-5 constrained resolver"),
    _dependency("normal-scan G2-v1 compatibility projection", "backend/app/services/scan_runner.py", D.G2_V1_WRITE, C.DEPRECATED_WRITE, False, "G2-v1 is not product authority for group-first policy-v2", "GF-6 G2-v2 projection"),
    _dependency("candidate repository persistence", "backend/app/repositories/candidate_repository.py", D.PAIR_WRITE, C.DEPRECATED_WRITE, False, "new DuplicateCandidate business writes are deprecated for group-first policy-v2", "GF-4 independent evidence"),
    _dependency("candidate repository historical listing", "backend/app/repositories/candidate_repository.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "legacy candidate rows remain readable", "authority-selected identity groups"),
    _dependency("legacy candidate scan API", "backend/app/api/routes_scans.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "candidate lists and pair exports are advanced compatibility diagnostics", "identity-read APIs and canonical exports"),
    _dependency("legacy diagnostic summary", "backend/app/api/routes_diagnostics.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "aggregate historical pair telemetry remains readable", "identity-read summary"),
    _dependency("legacy pair advisory endpoint", "backend/app/api/routes_llm.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "pair advisory remains a compatibility endpoint, not group-first authority", "versioned group advisory eligibility"),
    _dependency("pair feedback service", "backend/app/services/feedback_service.py", D.PAIR_WRITE, C.DEPRECATED_WRITE, False, "pair feedback is a legacy business write", "versioned G6 group review"),
    _dependency("pair LLM enhancement input", "backend/app/services/llm_enhancement_service.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "historical enhancement evidence may be inspected", "G7 group advisory"),
    _dependency("pair LLM enhancement candidate creation", "backend/app/services/llm_enhancement_service.py", D.PAIR_WRITE, C.DEPRECATED_WRITE, False, "recall-rescue candidate creation is not a group-first product dependency", "GF-2 discovery and GF-4 evidence"),
    _dependency("pair LLM triage input", "backend/app/services/llm_triage_service.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "historical pair triage remains inspectable", "G7 group advisory"),
    _dependency("pair LLM triage snapshot", "backend/app/services/llm_triage_service.py", D.PAIR_WRITE, C.DEPRECATED_WRITE, False, "new pair advisory writes are not required by group-first authority", "G7 group advisory"),
    _dependency("recall rescue pair pool", "backend/app/services/recall_rescue_service.py", D.PAIR_WRITE, C.DEPRECATED_WRITE, False, "pair recall-rescue persistence is not authoritative identity", "GF-2 bounded neighbor proposals"),
    _dependency("recall rescue candidate exclusion lookup", "backend/app/services/recall_rescue_service.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "legacy candidate lookup prevents compatibility duplicates only", "GF-2 proposal identity"),
    _dependency("pure legacy G1 projection", "backend/app/services/identity_group_projection.py", D.G1_WRITE, C.LEGACY_MODE_REQUIRED, False, "legacy-primary still requires G1; group-first policy-v2 does not", "GF-5 constrained resolver"),
    _dependency("G2-v1 snapshot consumes G1", "backend/app/services/identity_group_snapshot_service.py", D.G1_READ, C.LEGACY_MODE_REQUIRED, False, "G1 is consumed only to create legacy-authoritative v1", "GF-6 G2-v2 adapter"),
    _dependency("G2-v1 snapshot persistence", "backend/app/services/identity_group_snapshot_service.py", D.G2_V1_WRITE, C.LEGACY_MODE_REQUIRED, False, "legacy-primary retains immutable v1 persistence", "GF-6 G2-v2 persistence"),
    _dependency("historical/current v1 query service", "backend/app/services/identity_group_query_service.py", D.G2_V1_READ, C.HISTORICAL_READ_ONLY, True, "legacy numeric queries remain readable", "IdentityReadService for product reads"),
    _dependency("legacy system-group export", "backend/app/services/identity_group_export_service.py", D.G2_V1_READ, C.LEGACY_MODE_REQUIRED, True, "existing G5 route remains compatible for historical/legacy scans", "authority-selected System Group Export"),
    _dependency("legacy and versioned G6 review", "backend/app/services/identity_group_review_service.py", D.G2_V1_READ, C.LEGACY_MODE_REQUIRED, True, "v1 review chain remains valid; v2 uses projection-safe review rows", "versioned G6 review"),
    _dependency("legacy G6 constraint reprojection", "backend/app/services/identity_group_review_service.py", D.G1_WRITE, C.LEGACY_MODE_REQUIRED, False, "legacy re-projection is scoped to the v1 review chain", "versioned G6 v2 review constraints"),
    _dependency("persisted orchestration v1 source audit", "backend/app/services/scan_orchestration_service.py", D.G2_V1_READ, C.HISTORICAL_READ_ONLY, True, "historical source references must remain truthful", "persisted policy-version audit"),
    _dependency("GF-7 v1-v2 comparison", "backend/app/services/shadow_comparison_service.py", D.G2_V1_READ, C.MIGRATION_SHADOW_ONLY, False, "policy-v2 group-first creates no legitimate v1 comparison side", None),
    _dependency("authority-selected historical/legacy v1 source", "backend/app/repositories/identity_read_repository.py", D.G2_V1_READ, C.HISTORICAL_READ_ONLY, True, "no-audit and legacy-primary scans remain v1-authoritative", "persisted-mode IdentityReadService"),
    _dependency("canonical product v1 adapter", "backend/app/services/identity_read_service.py", D.G2_V1_READ, C.HISTORICAL_READ_ONLY, True, "v1 is selected only for no-audit or persisted legacy-primary scans", "G2-v2 for persisted group-first-primary"),
    _dependency("canonical authority-selected exports", "backend/app/services/identity_read_export_service.py", D.G2_V1_READ, C.HISTORICAL_READ_ONLY, True, "the v1 branch serves only authority-selected historical/legacy scans", "G2-v2 export branch for group-first-primary"),
    _dependency("legacy G7 advisory request", "backend/app/services/group_llm_eligibility.py", D.G2_V1_READ, C.LEGACY_MODE_REQUIRED, True, "v1 advisory stays valid for v1 authority; versioned group-first reads v2", "G2-v2 versioned G7 request"),
    _dependency("legacy numeric group API", "backend/app/api/routes_identity_groups.py", D.G2_V1_READ, C.HISTORICAL_READ_ONLY, True, "numeric group identities cannot represent v2 and remain compatibility-only", "opaque identity-read group routes"),
    _dependency("legacy scan candidate service", "backend/app/services/scan_service.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "candidate list is a legacy diagnostic", "identity-read group list"),
    _dependency("legacy candidate CSV", "backend/app/services/export_service.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "pair-shaped CSV remains historical/diagnostic", "canonical member-shaped identity exports"),
    _dependency("legacy pair advisory CSV", "backend/app/services/llm_export_service.py", D.PAIR_READ, C.DIAGNOSTIC_READ_ONLY, True, "pair LLM export remains compatibility-only", "canonical identity exports"),
    _dependency("legacy rejection persistence", "backend/app/repositories/rejection_repository.py", D.PAIR_WRITE, C.DEPRECATED_WRITE, False, "pair-shaped rejection writes are part of the compatibility transaction", "GF-4 cannot-link evidence"),
    _dependency("pair-path regression fixtures", "backend/tests/", D.PAIR_WRITE, C.TEST_ONLY, False, "tests construct isolated legacy candidate fixtures", None),
    _dependency("pair-path regression assertions", "backend/tests/", D.PAIR_READ, C.TEST_ONLY, True, "tests verify historical and legacy compatibility", None),
    _dependency("G1 regression fixtures", "backend/tests/", D.G1_WRITE, C.TEST_ONLY, False, "tests execute the isolated legacy G1 contract", None),
    _dependency("G1 regression assertions", "backend/tests/", D.G1_READ, C.TEST_ONLY, True, "tests verify historical G1 semantics", None),
    _dependency("G2-v1 regression fixtures", "backend/tests/", D.G2_V1_WRITE, C.TEST_ONLY, False, "tests construct immutable historical v1 fixtures", None),
    _dependency("G2-v1 regression assertions", "backend/tests/", D.G2_V1_READ, C.TEST_ONLY, True, "tests verify historical and legacy v1 behavior", None),
)


def validate_pair_path_dependency_inventory(
    dependencies: tuple[PairPathDependency, ...] = PAIR_PATH_DEPENDENCIES,
) -> None:
    if not dependencies:
        raise ValueError("pair-path dependency inventory is empty")
    identities = set()
    for item in dependencies:
        if not isinstance(item, PairPathDependency):
            raise TypeError("pair-path dependency has an invalid type")
        identity = (item.component, item.source_file, item.dependency_kind)
        if identity in identities:
            raise ValueError("pair-path dependency is duplicated")
        identities.add(identity)
        if item.classification == C.AUTHORITATIVE_REQUIRED:
            raise ValueError("authoritative pair-path dependency remains")
        if item.dependency_kind in {D.PAIR_WRITE, D.G1_WRITE, D.G2_V1_WRITE}:
            if item.allowed_in_group_first_policy_v2:
                raise ValueError("legacy write is allowed in group-first policy-v2")
        if item.classification == C.MIGRATION_SHADOW_ONLY:
            if item.allowed_in_group_first_policy_v2:
                raise ValueError("migration shadow dependency is allowed in policy-v2")


validate_pair_path_dependency_inventory()
