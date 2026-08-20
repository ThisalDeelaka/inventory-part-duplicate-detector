"""Pure persisted-mode authority selection for future GF-9 readers."""

from __future__ import annotations

from app.identity_read.contracts import (
    IdentityReadAuthorityContext,
    IdentityReadAuthorityDecision,
    IdentityReadAuthorityStatus,
    IdentityReadProjectionAvailability,
    IdentityReadProjectionContract,
)


def _decision(context, status, projection=None, reason=""):
    return IdentityReadAuthorityDecision(
        scan_id=context.scan_id,
        authority_status=status,
        projection_contract=projection.projection_contract if projection else None,
        source_projection_run_id=projection.source_projection_run_id if projection else None,
        source_orchestration_run_id=context.orchestration_run_id,
        reason_code=reason,
    )


def _select(context, projection, expected):
    if projection is None or projection.status is None:
        return _decision(
            context, IdentityReadAuthorityStatus.READ_NOT_READY,
            reason=f"{expected.value}_PROJECTION_MISSING",
        )
    if projection.projection_contract != expected:
        return _decision(
            context, IdentityReadAuthorityStatus.READ_AUTHORITY_INCONSISTENT,
            reason="PROJECTION_CONTRACT_MISMATCH",
        )
    if projection.scan_id != context.scan_id or projection.source_projection_run_id is None:
        return _decision(
            context, IdentityReadAuthorityStatus.READ_AUTHORITY_INCONSISTENT,
            reason="PROJECTION_CROSS_SCAN_OR_UNIDENTIFIED",
        )
    if projection.status != "COMPLETED":
        return _decision(
            context, IdentityReadAuthorityStatus.READ_NOT_READY,
            reason=f"{expected.value}_PROJECTION_NOT_COMPLETED",
        )
    if not projection.provenance_compatible or not projection.snapshot_valid:
        return _decision(
            context, IdentityReadAuthorityStatus.READ_AUTHORITY_INCONSISTENT,
            reason=f"{expected.value}_PROJECTION_INVALID",
        )
    return _decision(
        context, IdentityReadAuthorityStatus.READY, projection,
        f"{expected.value}_AUTHORITY_READY",
    )


def determine_identity_read_authority(
    context: IdentityReadAuthorityContext,
) -> IdentityReadAuthorityDecision:
    """Select only from persisted per-scan facts; current config is not an input."""
    if context.scan_id <= 0:
        return _decision(
            context, IdentityReadAuthorityStatus.READ_AUTHORITY_INCONSISTENT,
            reason="INVALID_SCAN_ID",
        )
    if context.orchestration_run_id is None:
        if context.persisted_orchestration_mode is not None or context.orchestration_status is not None:
            return _decision(
                context, IdentityReadAuthorityStatus.READ_AUTHORITY_INCONSISTENT,
                reason="HISTORICAL_AUDIT_FIELDS_INCONSISTENT",
            )
        return _select(context, context.v1_projection, IdentityReadProjectionContract.G2_V1)
    if context.orchestration_status != "COMPLETED":
        return _decision(
            context, IdentityReadAuthorityStatus.READ_NOT_READY,
            reason="ORCHESTRATION_NOT_COMPLETED",
        )
    if context.persisted_orchestration_mode == "legacy_primary":
        return _select(context, context.v1_projection, IdentityReadProjectionContract.G2_V1)
    if context.persisted_orchestration_mode == "group_first_primary":
        return _select(context, context.v2_projection, IdentityReadProjectionContract.G2_V2)
    return _decision(
        context, IdentityReadAuthorityStatus.READ_AUTHORITY_INCONSISTENT,
        reason="ORCHESTRATION_MODE_INVALID",
    )
