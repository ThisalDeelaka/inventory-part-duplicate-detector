"""Typed read-only API for immutable identity-group projection snapshots."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.identity_groups import (
    AcceptedIdentityGroupStatus,
    IdentityDiagnosticDetail,
    IdentityDiagnosticStatus,
    IdentityGroupDetail,
    IdentityGroupSummaryResponse,
    PaginatedIdentityDiagnosticsResponse,
    PaginatedIdentityGroupsResponse,
    ProjectionRunResponse,
    IdentityReadGroupDetailResponse,
    IdentityReadOutcomesResponse,
    IdentityReadSummaryApiResponse,
    PaginatedIdentityReadGroupsResponse,
    VersionedGroupAdvisoryEligibilityResponse,
)
from app.schemas.identity_group_reviews import (
    GroupReviewCreateRequest,
    GroupReviewCurrentResponse,
    GroupReviewEventResponse,
    GroupReviewHistoryResponse,
    VersionedGroupReviewCreateRequest,
    VersionedGroupReviewCurrentResponse,
    VersionedGroupReviewEventResponse,
    VersionedGroupReviewHistoryResponse,
)
from app.services.identity_group_query_service import (
    IdentityGroupQueryService,
    InvalidSnapshotSelectionError,
    SnapshotNotFoundError,
)
from app.services.identity_group_export_service import (
    identity_group_diagnostics_to_csv,
    identity_groups_to_csv,
)
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    GroupReviewTargetNotFoundError,
    GroupReviewValidationError,
    IdentityGroupReviewService,
    VersionedIdentityGroupReviewService,
    StaleGroupReviewError,
)
from app.services.identity_group_review_export_service import (
    reviewed_identity_decisions_to_csv,
)
from app.services.identity_read_export_service import (
    authority_selected_conflicts_to_csv,
    authority_selected_deferred_to_csv,
    authority_selected_reviewed_identities_to_csv,
    authority_selected_system_groups_to_csv,
)
from app.identity_read.fingerprints import canonical_value
from app.identity_read.key_codec import (
    InvalidVersionedIdentityGroupKey,
    parse_versioned_identity_group_key,
    serialize_versioned_identity_group_key,
)
from app.services.identity_read_service import (
    IdentityReadAuthorityInconsistent,
    IdentityReadGroupNotFound,
    IdentityReadGroupProjectionMismatch,
    IdentityReadNotReady,
    IdentityReadService,
)
from app.llm.group_contracts import group_advisory_request_fingerprint
from app.services.group_llm_eligibility import GroupAdvisoryContractService


router = APIRouter(prefix="/api/scans", tags=["identity-group-snapshots"])


def _service(db, scan_id):
    service = IdentityGroupQueryService(db)
    if not service.scan_exists(scan_id):
        raise HTTPException(404, "Scan not found")
    return service


def _safe(call):
    try:
        return call()
    except SnapshotNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except InvalidSnapshotSelectionError as exc:
        raise HTTPException(409, str(exc)) from None


def _identity_read_safe(call):
    try:
        return call()
    except IdentityReadNotReady as exc:
        raise HTTPException(409, str(exc)) from None
    except (IdentityReadAuthorityInconsistent, IdentityReadGroupProjectionMismatch) as exc:
        raise HTTPException(422, str(exc)) from None
    except (IdentityReadGroupNotFound, InvalidVersionedIdentityGroupKey) as exc:
        raise HTTPException(404, str(exc)) from None


def _read_projection(snapshot):
    return {
        "projection_contract": snapshot.projection_contract.value,
        "source_projection_run_id": snapshot.source_projection_run_id,
        "source_orchestration_run_id": snapshot.source_orchestration_run_id,
        "source_resolution_run_id": snapshot.source_resolution_run_id,
    }


def _read_group(group, *, detail=False, review_state=None):
    payload = {
        "versioned_group_key": serialize_versioned_identity_group_key(
            group.versioned_group_key
        ),
        "group_reference": group.versioned_group_key.group_reference,
        "projection_contract": group.versioned_group_key.projection_contract.value,
        "group_status": group.status.value,
        "group_size": group.member_count,
        "validation_mode": group.validation_mode.value,
        "validation_coverage": canonical_value(group.validation_coverage),
        "source_group_fingerprint": group.source_group_fingerprint,
        "read_group_fingerprint": group.read_group_fingerprint,
        "group_evidence_summary": canonical_value(group.group_evidence_summary),
        "bridge_risk_summary": canonical_value(group.bridge_risk_summary),
        "genericity_risk_summary": canonical_value(group.genericity_risk_summary),
        "missing_evidence_summary": canonical_value(group.missing_evidence_summary),
        "member_preview": [canonical_value(item) for item in group.members[:3]],
        "review_state": review_state or {"reviewed": False},
    }
    if detail:
        payload["members"] = [canonical_value(item) for item in group.members]
        payload["internal_evidence"] = [canonical_value(item) for item in group.internal_evidence]
    return payload


@router.get(
    "/{scan_id}/identity-read/summary", response_model=IdentityReadSummaryApiResponse
)
def authoritative_identity_summary(scan_id: int, db: Session = Depends(get_db)):
    _service(db, scan_id)
    snapshot = _identity_read_safe(
        lambda: IdentityReadService(db).load_identity_read_snapshot(scan_id)
    )
    return {
        "snapshot_available": True,
        "read_ready": True,
        "projection": _read_projection(snapshot),
        **canonical_value(snapshot.summary),
        "snapshot_fingerprint": snapshot.snapshot_fingerprint,
    }


@router.get(
    "/{scan_id}/identity-read/groups", response_model=PaginatedIdentityReadGroupsResponse
)
def authoritative_identity_groups(
    scan_id: int,
    status: AcceptedIdentityGroupStatus | None = None,
    minimum_group_size: int | None = Query(default=None, ge=2),
    maximum_group_size: int | None = Query(default=None, ge=2),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if minimum_group_size is not None and maximum_group_size is not None and minimum_group_size > maximum_group_size:
        raise HTTPException(422, "minimum_group_size cannot exceed maximum_group_size")
    _service(db, scan_id)
    snapshot = _identity_read_safe(
        lambda: IdentityReadService(db).load_identity_read_snapshot(scan_id)
    )
    groups = tuple(
        group for group in snapshot.groups
        if (status is None or group.status.value == status.value)
        and (minimum_group_size is None or group.member_count >= minimum_group_size)
        and (maximum_group_size is None or group.member_count <= maximum_group_size)
    )
    review_states = VersionedIdentityGroupReviewService(db).current_states_for_snapshot(
        snapshot
    )
    items = groups[offset:offset + limit]
    return {
        "projection": _read_projection(snapshot), "limit": limit, "offset": offset,
        "total": len(groups), "items": [
            _read_group(
                item,
                review_state=review_states.get(
                    serialize_versioned_identity_group_key(item.versioned_group_key)
                ),
            )
            for item in items
        ],
    }


@router.get(
    "/{scan_id}/identity-read/groups/{versioned_group_key}",
    response_model=IdentityReadGroupDetailResponse,
)
def authoritative_identity_group_detail(
    scan_id: int, versioned_group_key: str, db: Session = Depends(get_db)
):
    _service(db, scan_id)
    key = _identity_read_safe(lambda: parse_versioned_identity_group_key(versioned_group_key))
    group = _identity_read_safe(
        lambda: IdentityReadService(db).load_identity_read_group(scan_id, key)
    )
    return _read_group(group, detail=True)


@router.get(
    "/{scan_id}/identity-read/outcomes", response_model=IdentityReadOutcomesResponse
)
def authoritative_identity_outcomes(scan_id: int, db: Session = Depends(get_db)):
    _service(db, scan_id)
    snapshot = _identity_read_safe(
        lambda: IdentityReadService(db).load_identity_read_snapshot(scan_id)
    )
    return {
        "projection": _read_projection(snapshot),
        "conflicts": [canonical_value(item) for item in snapshot.conflicts],
        "deferred_work_units": [canonical_value(item) for item in snapshot.deferred_work_units],
        "unassigned_records": [canonical_value(item) for item in snapshot.unassigned_records],
    }


def _identity_read_csv(scan_id, db, converter, filename):
    _service(db, scan_id)
    content = _identity_read_safe(lambda: converter(db, scan_id))
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{scan_id}/identity-read/system-groups/export.csv")
def export_authoritative_system_groups(scan_id: int, db: Session = Depends(get_db)):
    return _identity_read_csv(
        scan_id, db, authority_selected_system_groups_to_csv,
        f"scan-{scan_id}-system-groups.csv",
    )


@router.get("/{scan_id}/identity-read/reviewed-identities/export.csv")
def export_authoritative_reviewed_identities(
    scan_id: int, db: Session = Depends(get_db)
):
    return _identity_read_csv(
        scan_id, db, authority_selected_reviewed_identities_to_csv,
        f"scan-{scan_id}-reviewed-identities.csv",
    )


@router.get("/{scan_id}/identity-read/conflicts/export.csv")
def export_authoritative_identity_conflicts(scan_id: int, db: Session = Depends(get_db)):
    return _identity_read_csv(
        scan_id, db, authority_selected_conflicts_to_csv,
        f"scan-{scan_id}-identity-conflicts.csv",
    )


@router.get("/{scan_id}/identity-read/deferred/export.csv")
def export_authoritative_deferred_identity_work(
    scan_id: int, db: Session = Depends(get_db)
):
    return _identity_read_csv(
        scan_id, db, authority_selected_deferred_to_csv,
        f"scan-{scan_id}-deferred-identity-work.csv",
    )


@router.get(
    "/{scan_id}/identity-read/groups/{versioned_group_key}/advisory/eligibility",
    response_model=VersionedGroupAdvisoryEligibilityResponse,
)
def versioned_group_advisory_eligibility(
    scan_id: int, versioned_group_key: str, db: Session = Depends(get_db)
):
    _service(db, scan_id)
    key = _parsed_group_key(versioned_group_key)
    group = _identity_read_safe(
        lambda: IdentityReadService(db).load_identity_read_group(scan_id, key)
    )
    snapshot = _identity_read_safe(
        lambda: IdentityReadService(db).load_identity_read_snapshot(scan_id)
    )
    eligibility, request = _identity_read_safe(
        lambda: GroupAdvisoryContractService(db).build_request_for_versioned_group(
            scan_id, versioned_group_key
        )
    )
    return {
        "versioned_group_key": versioned_group_key,
        "projection_contract": snapshot.projection_contract.value,
        "source_projection_run_id": snapshot.source_projection_run_id,
        "source_group_fingerprint": group.source_group_fingerprint,
        "eligible": eligibility.eligible,
        "reason_code": eligibility.reason_code.value,
        "details": list(eligibility.details),
        "request_fingerprint": (
            group_advisory_request_fingerprint(request) if request else None
        ),
    }


@router.get("/{scan_id}/identity-group-projections", response_model=list[ProjectionRunResponse])
def projection_runs(scan_id: int, db: Session = Depends(get_db)):
    return _service(db, scan_id).list_runs(scan_id)


@router.get("/{scan_id}/identity-groups/summary", response_model=IdentityGroupSummaryResponse)
def identity_group_summary(
    scan_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    service = _service(db, scan_id)
    return _safe(lambda: service.summary(scan_id, projection_run_id))


@router.get("/{scan_id}/identity-groups", response_model=PaginatedIdentityGroupsResponse)
def identity_groups(
    scan_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    status: AcceptedIdentityGroupStatus | None = None,
    minimum_group_size: int | None = Query(default=None, ge=2),
    maximum_group_size: int | None = Query(default=None, ge=2),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if minimum_group_size is not None and maximum_group_size is not None and minimum_group_size > maximum_group_size:
        raise HTTPException(422, "minimum_group_size cannot exceed maximum_group_size")
    service = _service(db, scan_id)
    return _safe(lambda: service.list_groups(
        scan_id, projection_run_id, status.value if status else None,
        minimum_group_size, maximum_group_size, limit, offset,
    ))


@router.get("/{scan_id}/identity-groups/export.csv")
def export_identity_groups(
    scan_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    _service(db, scan_id)
    content = _safe(lambda: identity_groups_to_csv(db, scan_id, projection_run_id))
    return Response(
        content, media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="scan-{scan_id}-identity-groups.csv"'},
    )


@router.get("/{scan_id}/identity-groups/reviewed-export.csv")
def export_reviewed_identity_decisions(
    scan_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    _service(db, scan_id)
    content = _safe(lambda: reviewed_identity_decisions_to_csv(
        db, scan_id, projection_run_id
    ))
    return Response(
        content, media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="scan-{scan_id}-reviewed-identity-decisions.csv"'
        },
    )


@router.get("/{scan_id}/identity-groups/{group_snapshot_id}", response_model=IdentityGroupDetail)
def identity_group_detail(
    scan_id: int,
    group_snapshot_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    service = _service(db, scan_id)
    return _safe(lambda: service.group_detail(scan_id, group_snapshot_id, projection_run_id))


def _review_safe(call):
    try:
        return call()
    except GroupReviewTargetNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except StaleGroupReviewError as exc:
        raise HTTPException(409, str(exc)) from None
    except GroupReviewValidationError as exc:
        raise HTTPException(422, str(exc)) from None
    except IdentityReadNotReady as exc:
        raise HTTPException(409, str(exc)) from None
    except (IdentityReadAuthorityInconsistent, IdentityReadGroupProjectionMismatch) as exc:
        raise HTTPException(422, str(exc)) from None
    except IdentityReadGroupNotFound as exc:
        raise HTTPException(404, str(exc)) from None


def _parsed_group_key(value):
    return _identity_read_safe(lambda: parse_versioned_identity_group_key(value))


@router.get(
    "/{scan_id}/identity-read/groups/{versioned_group_key}/reviews",
    response_model=VersionedGroupReviewHistoryResponse,
)
def versioned_identity_group_review_history(
    scan_id: int, versioned_group_key: str, db: Session = Depends(get_db)
):
    _service(db, scan_id)
    key = _parsed_group_key(versioned_group_key)
    items = _review_safe(
        lambda: VersionedIdentityGroupReviewService(db).review_history(scan_id, key)
    )
    current = next((row for row in reversed(items) if row["is_current"]), None)
    return {
        "scan_id": scan_id,
        "versioned_group_key": versioned_group_key,
        "current_review_event_id": current["review_event_id"] if current else None,
        "items": items,
    }


@router.get(
    "/{scan_id}/identity-read/groups/{versioned_group_key}/reviews/current",
    response_model=VersionedGroupReviewCurrentResponse,
)
def versioned_identity_group_current_review(
    scan_id: int, versioned_group_key: str, db: Session = Depends(get_db)
):
    _service(db, scan_id)
    key = _parsed_group_key(versioned_group_key)
    return _review_safe(
        lambda: VersionedIdentityGroupReviewService(db).current_review_state(scan_id, key)
    )


@router.post(
    "/{scan_id}/identity-read/groups/{versioned_group_key}/reviews",
    response_model=VersionedGroupReviewEventResponse,
    status_code=201,
)
def create_versioned_identity_group_review(
    scan_id: int,
    versioned_group_key: str,
    payload: VersionedGroupReviewCreateRequest,
    db: Session = Depends(get_db),
):
    _service(db, scan_id)
    key = _parsed_group_key(versioned_group_key)
    service = VersionedIdentityGroupReviewService(db)
    group = _identity_read_safe(
        lambda: IdentityReadService(db).load_identity_read_group(scan_id, key)
    )
    decision = GroupReviewDecision(payload.decision_type.value)
    if decision in {
        GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        GroupReviewDecision.KEEP_ALL_SEPARATE,
        GroupReviewDecision.UNSURE,
    }:
        if payload.selected_record_ref_keys or payload.partitions:
            raise HTTPException(422, "this decision does not accept member selections")
        submitted_members = tuple(
            member.stable_record_reference for member in group.members
        )
        partitions = ()
    elif decision == GroupReviewDecision.CONFIRM_SELECTED:
        if payload.partitions:
            raise HTTPException(422, "CONFIRM_SELECTED does not accept partitions")
        submitted_members = payload.selected_record_ref_keys
        partitions = ()
    else:
        if payload.selected_record_ref_keys:
            raise HTTPException(422, "SPLIT_PARTITIONS does not accept selected members")
        submitted_members = ()
        partitions = payload.partitions
    result = _review_safe(lambda: service.create_review(
        scan_id=scan_id,
        key=key,
        decision_type=decision,
        reviewer=payload.reviewer,
        submitted_members=submitted_members,
        partitions=partitions,
        comment=payload.comment,
        supersedes_review_event_id=payload.supersedes_review_event_id,
    ))
    history = _review_safe(lambda: service.review_history(scan_id, key))
    return next(row for row in history if row["review_event_id"] == result.review_event_id)


@router.get(
    "/{scan_id}/identity-groups/{group_snapshot_id}/reviews",
    response_model=GroupReviewHistoryResponse,
)
def identity_group_review_history(
    scan_id: int,
    group_snapshot_id: int,
    db: Session = Depends(get_db),
):
    _service(db, scan_id)
    items = _review_safe(
        lambda: IdentityGroupReviewService(db).review_history(scan_id, group_snapshot_id)
    )
    current = next((row for row in reversed(items) if row["is_current"]), None)
    return {
        "scan_id": scan_id,
        "group_snapshot_id": group_snapshot_id,
        "current_review_event_id": current["review_event_id"] if current else None,
        "items": items,
    }


@router.get(
    "/{scan_id}/identity-groups/{group_snapshot_id}/reviews/current",
    response_model=GroupReviewCurrentResponse,
)
def identity_group_current_review(
    scan_id: int,
    group_snapshot_id: int,
    db: Session = Depends(get_db),
):
    _service(db, scan_id)
    return _review_safe(
        lambda: IdentityGroupReviewService(db).current_review_state(
            scan_id, group_snapshot_id
        )
    )


@router.post(
    "/{scan_id}/identity-groups/{group_snapshot_id}/reviews",
    response_model=GroupReviewEventResponse,
    status_code=201,
)
def create_identity_group_review(
    scan_id: int,
    group_snapshot_id: int,
    payload: GroupReviewCreateRequest,
    db: Session = Depends(get_db),
):
    _service(db, scan_id)
    service = IdentityGroupReviewService(db)
    _review_safe(lambda: service._accepted_group(scan_id, group_snapshot_id))
    decision = GroupReviewDecision(payload.decision_type.value)
    if decision in {
        GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        GroupReviewDecision.KEEP_ALL_SEPARATE,
        GroupReviewDecision.UNSURE,
    }:
        if payload.selected_record_ref_keys or payload.partitions:
            raise HTTPException(422, "this decision does not accept member selections")
        submitted_members = _review_safe(lambda: service.group_members(
            scan_id, payload.projection_run_id, group_snapshot_id,
            payload.group_hypothesis_key,
        ))
        partitions = ()
    elif decision == GroupReviewDecision.CONFIRM_SELECTED:
        if payload.partitions:
            raise HTTPException(422, "CONFIRM_SELECTED does not accept partitions")
        submitted_members = payload.selected_record_ref_keys
        partitions = ()
    else:
        if payload.selected_record_ref_keys:
            raise HTTPException(422, "SPLIT_PARTITIONS does not accept selected members")
        submitted_members = ()
        partitions = payload.partitions
    result = _review_safe(lambda: service.create_review(
        scan_id=scan_id,
        projection_run_id=payload.projection_run_id,
        group_snapshot_id=group_snapshot_id,
        group_hypothesis_key=payload.group_hypothesis_key,
        decision_type=decision,
        reviewer=payload.reviewer,
        comment=payload.comment,
        supersedes_review_event_id=payload.supersedes_review_event_id,
        submitted_members=submitted_members,
        partitions=partitions,
    ))
    history = _review_safe(lambda: service.review_history(scan_id, group_snapshot_id))
    return next(row for row in history if row["review_event_id"] == result.review_event_id)


@router.get("/{scan_id}/identity-group-diagnostics", response_model=PaginatedIdentityDiagnosticsResponse)
def identity_group_diagnostics(
    scan_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    status: IdentityDiagnosticStatus | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    service = _service(db, scan_id)
    return _safe(lambda: service.list_diagnostics(
        scan_id, projection_run_id, status.value if status else None, limit, offset
    ))


@router.get("/{scan_id}/identity-group-diagnostics/export.csv")
def export_identity_group_diagnostics(
    scan_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    _service(db, scan_id)
    content = _safe(lambda: identity_group_diagnostics_to_csv(db, scan_id, projection_run_id))
    return Response(
        content, media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="scan-{scan_id}-identity-group-diagnostics.csv"'
        },
    )


@router.get(
    "/{scan_id}/identity-group-diagnostics/{diagnostic_snapshot_id}",
    response_model=IdentityDiagnosticDetail,
)
def identity_group_diagnostic_detail(
    scan_id: int,
    diagnostic_snapshot_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    service = _service(db, scan_id)
    return _safe(lambda: service.diagnostic_detail(
        scan_id, diagnostic_snapshot_id, projection_run_id
    ))
