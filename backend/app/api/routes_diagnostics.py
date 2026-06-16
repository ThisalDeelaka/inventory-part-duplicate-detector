from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.constants import MODEL_VERSION
from app.db.database import get_db
from app.db.models import DuplicateCandidate, DuplicateFeedback, DuplicateScan

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    last = db.query(DuplicateScan).order_by(DuplicateScan.started_at.desc()).first()
    return {"service_status": "healthy", "model_version": MODEL_VERSION, "database_status": "connected", "total_scans": db.query(DuplicateScan).count(), "total_candidates": db.query(DuplicateCandidate).count(), "total_feedback_records": db.query(DuplicateFeedback).count(), "last_scan": {"id": last.id, "scan_name": last.scan_name, "status": last.status, "total_candidates": last.total_candidates} if last else None}
