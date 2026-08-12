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
)
from app.schemas.identity_group_reviews import (
    GroupReviewCreateRequest,
    GroupReviewCurrentResponse,
    GroupReviewEventResponse,
    GroupReviewHistoryResponse,
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
    StaleGroupReviewError,
)
from app.services.identity_group_review_export_service import (
    reviewed_identity_decisions_to_csv,
)


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
