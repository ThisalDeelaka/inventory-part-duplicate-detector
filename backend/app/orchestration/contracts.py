"""Immutable GF-8A scan-orchestration authority contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


SCAN_ORCHESTRATION_POLICY_VERSION = "group-first-orchestration-policy-v1"


class ScanOrchestrationMode(str, Enum):
    LEGACY_PRIMARY = "legacy_primary"
    GROUP_FIRST_PRIMARY = "group_first_primary"


class PrimaryIdentityPipeline(str, Enum):
    LEGACY_PAIR_G1 = "LEGACY_PAIR_G1"
    GROUP_FIRST_GF1_GF6 = "GROUP_FIRST_GF1_GF6"


class VisibleProjectionContract(str, Enum):
    G2_V1 = "G2_V1"


class ScanStage(str, Enum):
    CANONICAL_CATALOG = "CANONICAL_CATALOG"
    DISCOVERY = "DISCOVERY"
    SIGNED_EVIDENCE = "SIGNED_EVIDENCE"
    GROUP_RESOLUTION = "GROUP_RESOLUTION"
    G2_V2_PROJECTION = "G2_V2_PROJECTION"
    LEGACY_PAIR_COMPATIBILITY = "LEGACY_PAIR_COMPATIBILITY"
    G1_COMPATIBILITY_PROJECTION = "G1_COMPATIBILITY_PROJECTION"
    G2_V1_COMPATIBILITY_PROJECTION = "G2_V1_COMPATIBILITY_PROJECTION"
    SHADOW_COMPARISON = "SHADOW_COMPARISON"


class StageRequirementClassification(str, Enum):
    PRIMARY_REQUIRED = "PRIMARY_REQUIRED"
    COMPATIBILITY_REQUIRED = "COMPATIBILITY_REQUIRED"
    OPTIONAL_DIAGNOSTIC = "OPTIONAL_DIAGNOSTIC"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OrchestrationFailureCategory(str, Enum):
    PRIMARY_IDENTITY_FAILED = "PRIMARY_IDENTITY_FAILED"
    COMPATIBILITY_OUTPUT_FAILED = "COMPATIBILITY_OUTPUT_FAILED"
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    OPTIONAL_DIAGNOSTIC_FAILED = "OPTIONAL_DIAGNOSTIC_FAILED"
    MULTIPLE_REQUIRED_STAGE_FAILURES = "MULTIPLE_REQUIRED_STAGE_FAILURES"


class OrchestrationRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScanStageExecutionStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class ScanOrchestrationPolicy:
    mode: ScanOrchestrationMode
    policy_version: str
    primary_identity_pipeline: PrimaryIdentityPipeline
    visible_projection_contract: VisibleProjectionContract
    compatibility_projection_required: bool
    require_gf1_catalog: bool
    require_gf2_gf3_discovery: bool
    require_gf4_evidence: bool
    require_gf5_resolution: bool
    require_gf6_v2_projection: bool
    require_legacy_pair_persistence: bool
    require_g1_projection: bool
    require_g2_v1_compatibility_projection: bool
    shadow_comparison_enabled: bool
    shadow_comparison_required_for_scan_success: bool


@dataclass(frozen=True)
class ScanStageRequirement:
    stage: ScanStage
    classification: StageRequirementClassification
    order: int


@dataclass(frozen=True)
class ScanOrchestrationPlan:
    policy: ScanOrchestrationPolicy
    stage_requirements: tuple[ScanStageRequirement, ...]
    policy_fingerprint: str
    plan_fingerprint: str


@dataclass(frozen=True)
class ScanStageResult:
    stage: ScanStage
    succeeded: bool
    safe_failure_category: str | None = None
    skipped: bool = False


@dataclass(frozen=True)
class ScanOrchestrationOutcome:
    mode: ScanOrchestrationMode
    plan_fingerprint: str
    primary_identity_ready: bool
    compatibility_projection_ready: bool
    visible_product_ready: bool
    shadow_diagnostics_ready: bool
    failed_primary_stages: tuple[ScanStage, ...]
    failed_compatibility_stages: tuple[ScanStage, ...]
    failed_optional_stages: tuple[ScanStage, ...]
    safe_failure_category: OrchestrationFailureCategory | None


class OrchestrationConfigurationError(ValueError):
    failure_category = OrchestrationFailureCategory.CONFIGURATION_INVALID
