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
from app.services.identity_group_query_service import (
    IdentityGroupQueryService,
    InvalidSnapshotSelectionError,
    SnapshotNotFoundError,
)
from app.services.identity_group_export_service import (
    identity_group_diagnostics_to_csv,
    identity_groups_to_csv,
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


@router.get("/{scan_id}/identity-groups/{group_snapshot_id}", response_model=IdentityGroupDetail)
def identity_group_detail(
    scan_id: int,
    group_snapshot_id: int,
    projection_run_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    service = _service(db, scan_id)
    return _safe(lambda: service.group_detail(scan_id, group_snapshot_id, projection_run_id))


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
