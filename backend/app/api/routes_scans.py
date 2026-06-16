import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.engine.column_semantics import normalize_scan_mode
from app.services.export_service import candidates_to_csv
from app.services.grouping_service import build_duplicate_groups
from app.services.scan_service import get_scan, get_scan_candidates, get_scan_warnings, list_scans, run_scan
from app.services.privacy_service import security_transparency
from app.services.validation_service import parse_selected_fields, read_csv_upload_with_metadata, validate_dataframe

router = APIRouter(prefix="/api/scans", tags=["scans"])


def scan_json(scan, privacy=None):
    payload = {
        "id": scan.id, "scan_id": scan.id, "scan_name": scan.scan_name, "source_type": scan.source_type,
        "selected_fields": json.loads(scan.selected_fields), "threshold": scan.threshold, "status": scan.status,
        "total_records": scan.total_records, "total_candidates": scan.total_candidates, "warnings_count": scan.warnings_count,
        "started_at": scan.started_at, "completed_at": scan.completed_at, "model_version": scan.model_version,
        "scan_mode": getattr(scan, "scan_mode", "SAME_SITE_DUPLICATE"),
    }
    if privacy:
        payload["privacy"] = privacy
    return payload


def candidate_json(c):
    return {
        "id": c.id, "scan_id": c.scan_id, "contract_a": c.contract_a, "part_no_a": c.part_no_a, "description_a": c.description_a,
        "contract_b": c.contract_b, "part_no_b": c.part_no_b, "description_b": c.description_b, "similarity_score": c.similarity_score,
        "confidence_level": c.confidence_level, "description_similarity": c.description_similarity, "tfidf_score": c.tfidf_score,
        "fuzzy_score": c.fuzzy_score, "part_no_similarity": c.part_no_similarity, "technical_token_score": c.technical_token_score,
        "matched_fields": json.loads(c.matched_fields), "mismatched_fields": json.loads(c.mismatched_fields), "explanation": c.explanation,
        "recommended_action": c.recommended_action, "review_status": c.review_status, "reviewed_by": c.reviewed_by, "reviewed_at": c.reviewed_at,
        "business_status": getattr(c, "business_status", "POSSIBLE_DUPLICATE_REVIEW"),
        "rule_decision": getattr(c, "rule_decision", "ALLOW"),
        "rejection_reason": getattr(c, "rejection_reason", ""),
        "scan_mode": getattr(c, "scan_mode", "SAME_SITE_DUPLICATE"),
        "critical_mismatches": json.loads(getattr(c, "critical_mismatches", "[]") or "[]"),
        "variant_attributes_a": json.loads(getattr(c, "variant_attributes_a", "{}") or "{}"),
        "variant_attributes_b": json.loads(getattr(c, "variant_attributes_b", "{}") or "{}"),
    }


@router.get("")
def scans(db: Session = Depends(get_db)):
    return [scan_json(scan) for scan in list_scans(db)]


@router.get("/{scan_id}")
def scan_detail(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan(db, scan_id)
    if not scan: raise HTTPException(404, "Scan not found")
    return scan_json(scan)


@router.get("/{scan_id}/candidates")
def candidates(scan_id: int, db: Session = Depends(get_db)):
    if not get_scan(db, scan_id): raise HTTPException(404, "Scan not found")
    return [candidate_json(c) for c in get_scan_candidates(db, scan_id)]


@router.get("/{scan_id}/groups")
def duplicate_groups(scan_id: int, db: Session = Depends(get_db)):
    if not get_scan(db, scan_id): raise HTTPException(404, "Scan not found")
    return build_duplicate_groups(get_scan_candidates(db, scan_id))


@router.get("/{scan_id}/warnings")
def warnings(scan_id: int, db: Session = Depends(get_db)):
    if not get_scan(db, scan_id): raise HTTPException(404, "Scan not found")
    return [{"id": w.id, "scan_id": w.scan_id, "warning_type": w.warning_type, "message": w.message, "record_reference": w.record_reference, "created_at": w.created_at} for w in get_scan_warnings(db, scan_id)]


@router.post("/validate-only")
async def validate_only(file: UploadFile = File(...), selected_fields: str = Form("[]"), sensitive_mode: bool = Form(True)):
    df, metadata = await read_csv_upload_with_metadata(file)
    result = validate_dataframe(df, parse_selected_fields(selected_fields), sensitive_mode=sensitive_mode)
    result["privacy"] = security_transparency(file_hash=metadata["file_sha256"], sensitive_mode=sensitive_mode)
    result["privacy"]["file_size_bytes"] = metadata["file_size_bytes"]
    return result


@router.post("/upload")
async def upload(file: UploadFile = File(...), selected_fields: str = Form("[]"), threshold: float = Form(75), scan_name: str = Form("Inventory duplicate scan"), sensitive_mode: bool = Form(True), scan_mode: str = Form("SAME_SITE_DUPLICATE"), db: Session = Depends(get_db)):
    if threshold < 0 or threshold > 100: raise HTTPException(400, "threshold must be between 0 and 100")
    df, metadata = await read_csv_upload_with_metadata(file)
    validation = validate_dataframe(df, parse_selected_fields(selected_fields), sensitive_mode=sensitive_mode)
    if validation["missing_required_columns"]: raise HTTPException(422, {"message": "Missing required columns", "columns": validation["missing_required_columns"]})
    try:
        scan, _ = run_scan(db, df, scan_name.strip() or "Inventory duplicate scan", parse_selected_fields(selected_fields), threshold, sensitive_mode=sensitive_mode, scan_mode=normalize_scan_mode(scan_mode))
        privacy = security_transparency(file_hash=metadata["file_sha256"], sensitive_mode=sensitive_mode)
        privacy["file_size_bytes"] = metadata["file_size_bytes"]
        return scan_json(scan, privacy=privacy)
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    except Exception as exc: raise HTTPException(500, f"Scan failed safely: {exc}") from exc


@router.get("/{scan_id}/export")
def export(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan(db, scan_id)
    if not scan: raise HTTPException(404, "Scan not found")
    return Response(candidates_to_csv(get_scan_candidates(db, scan_id)), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="scan-{scan_id}-candidates.csv"'})
