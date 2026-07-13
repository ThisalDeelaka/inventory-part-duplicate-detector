import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db
from app.engine.column_semantics import normalize_scan_mode
from app.core.constants import REQUIRED_FIELDS
from app.schemas.schemas import MappingProfileCreate
from app.engine.candidate_generator import generate_candidate_pairs
from app.services.export_service import candidates_to_csv
from app.services.grouping_service import build_duplicate_groups
from app.services.scan_service import get_scan, get_scan_candidates, get_scan_warnings, list_scans, run_scan
from app.services.privacy_service import security_transparency
from app.repositories.column_mapping_profile_repository import ColumnMappingProfileRepository
from app.services.validation_service import canonicalize_uploaded_dataframe, normalize_selected_fields, parse_selected_fields, read_csv_upload_with_metadata, validate_dataframe

router = APIRouter(prefix="/api/scans", tags=["scans"])


def _json_attr(obj, name, default):
    try:
        return json.loads(getattr(obj, name, None) or default)
    except (TypeError, json.JSONDecodeError):
        return json.loads(default)


def _bool_attr(obj, name):
    return str(getattr(obj, name, "false") or "false").lower() == "true"


def _profile_mapping(profile):
    try:
        mapping_rows = json.loads(getattr(profile, "column_mapping", "[]") or "[]")
    except (TypeError, json.JSONDecodeError):
        mapping_rows = []
    return {row["source_column"]: row["canonical_field"] for row in mapping_rows if row.get("source_column") and row.get("canonical_field")}


def _profile_payload(profile):
    try:
        source_columns = json.loads(getattr(profile, "source_columns", "[]") or "[]")
    except (TypeError, json.JSONDecodeError):
        source_columns = []
    try:
        mapping_rows = json.loads(getattr(profile, "column_mapping", "[]") or "[]")
    except (TypeError, json.JSONDecodeError):
        mapping_rows = []
    return {
        "id": profile.id,
        "profile_name": profile.profile_name,
        "header_signature": profile.header_signature,
        "source_columns": source_columns,
        "column_mapping": mapping_rows,
        "usage_count": profile.usage_count,
        "last_used_at": profile.last_used_at,
        "updated_at": profile.updated_at,
    }


def _apply_mapping_profile(db: Session, df, metadata: dict):
    profiles = ColumnMappingProfileRepository(db)
    profile = profiles.get_by_signature(metadata["header_signature"])
    profile_mapping = _profile_mapping(profile) if profile else None
    normalized_df, mapping = canonicalize_uploaded_dataframe(df, profile_mapping=profile_mapping)
    if profile:
        profile = profiles.touch(profile)
    return normalized_df, {**metadata, **mapping, "profile": _profile_payload(profile) if profile else None, "profile_applied": bool(profile)}


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
        "critical_mismatches": _json_attr(c, "critical_mismatches", "[]"),
        "variant_attributes_a": _json_attr(c, "variant_attributes_a", "{}"),
        "variant_attributes_b": _json_attr(c, "variant_attributes_b", "{}"),
        "generic_description_warning": _bool_attr(c, "generic_description_warning"),
        "application_context_a": _json_attr(c, "application_context_a", "[]"),
        "application_context_b": _json_attr(c, "application_context_b", "[]"),
        "application_context_warning": _bool_attr(c, "application_context_warning"),
        "normalized_description_a": getattr(c, "normalized_description_a", "") or "",
        "normalized_description_b": getattr(c, "normalized_description_b", "") or "",
        "normalized_part_no_a": getattr(c, "normalized_part_no_a", "") or "",
        "normalized_part_no_b": getattr(c, "normalized_part_no_b", "") or "",
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
async def validate_only(file: UploadFile = File(...), selected_fields: str = Form("[]"), sensitive_mode: bool = Form(True), debug_mode: bool = Form(False), db: Session = Depends(get_db)):
    raw_df, metadata = await read_csv_upload_with_metadata(file)
    df, metadata = _apply_mapping_profile(db, raw_df, metadata)
    result = validate_dataframe(df, parse_selected_fields(selected_fields), sensitive_mode=sensitive_mode)
    result["column_mapping"] = metadata["column_mapping"]
    result["unmapped_source_columns"] = metadata["unmapped_source_columns"]
    result["mapped_canonical_fields"] = metadata["mapped_canonical_fields"]
    result["header_signature"] = metadata["header_signature"]
    result["profile"] = metadata.get("profile")
    result["profile_applied"] = metadata.get("profile_applied", False)
    if debug_mode:
        generated = generate_candidate_pairs(df[df["DESCRIPTION"].fillna("").str.strip().ne("")].copy(), parse_selected_fields(selected_fields), debug_mode=True)
        result["candidate_diagnostics"] = generated["diagnostics"]
    result["privacy"] = security_transparency(file_hash=metadata["file_sha256"], sensitive_mode=sensitive_mode)
    result["privacy"]["file_size_bytes"] = metadata["file_size_bytes"]
    return result


@router.post("/upload")
async def upload(file: UploadFile = File(...), selected_fields: str = Form("[]"), threshold: float = Form(75), scan_name: str = Form("Inventory duplicate scan"), sensitive_mode: bool = Form(True), scan_mode: str = Form("SAME_SITE_DUPLICATE"), debug_mode: bool = Form(False), db: Session = Depends(get_db)):
    if threshold < 0 or threshold > 100: raise HTTPException(400, "threshold must be between 0 and 100")
    raw_df, metadata = await read_csv_upload_with_metadata(file)
    df, metadata = _apply_mapping_profile(db, raw_df, metadata)
    validation = validate_dataframe(df, parse_selected_fields(selected_fields), sensitive_mode=sensitive_mode)
    if validation["missing_required_columns"]: raise HTTPException(422, {"message": "Missing required columns", "columns": validation["missing_required_columns"]})
    try:
        scan, pair_count, diagnostics = run_scan(db, df, scan_name.strip() or "Inventory duplicate scan", validation["resolved_selected_fields"], threshold, sensitive_mode=sensitive_mode, scan_mode=normalize_scan_mode(scan_mode), debug_mode=debug_mode)
        privacy = security_transparency(file_hash=metadata["file_sha256"], sensitive_mode=sensitive_mode)
        privacy["file_size_bytes"] = metadata["file_size_bytes"]
        payload = scan_json(scan, privacy=privacy)
        payload["candidate_pair_count"] = pair_count
        payload["column_mapping"] = metadata["column_mapping"]
        payload["unmapped_source_columns"] = metadata["unmapped_source_columns"]
        payload["mapped_canonical_fields"] = metadata["mapped_canonical_fields"]
        payload["header_signature"] = metadata["header_signature"]
        payload["profile"] = metadata.get("profile")
        payload["profile_applied"] = metadata.get("profile_applied", False)
        if debug_mode:
            payload["candidate_diagnostics"] = diagnostics
        return payload
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    except Exception as exc: raise HTTPException(500, f"Scan failed safely: {exc}") from exc


@router.post("/mapping-profiles")
def save_mapping_profile(payload: MappingProfileCreate, db: Session = Depends(get_db)):
    if not payload.header_signature.strip():
        raise HTTPException(400, "header_signature is required")
    if not payload.column_mapping:
        raise HTTPException(400, "column_mapping is required")
    mapped_fields = {row.canonical_field for row in payload.column_mapping if row.canonical_field}
    missing_required = [field for field in REQUIRED_FIELDS if field not in mapped_fields]
    if missing_required:
        raise HTTPException(422, {"message": "Missing required mapped fields", "columns": missing_required})
    profiles = ColumnMappingProfileRepository(db)
    profile = profiles.upsert(
        profile_name=payload.profile_name.strip() or "CSV mapping profile",
        header_signature=payload.header_signature.strip(),
        source_columns=payload.source_columns,
        column_mapping=[row.model_dump() for row in payload.column_mapping],
    )
    return _profile_payload(profile)


@router.get("/{scan_id}/export")
def export(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan(db, scan_id)
    if not scan: raise HTTPException(404, "Scan not found")
    return Response(candidates_to_csv(get_scan_candidates(db, scan_id)), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="scan-{scan_id}-candidates.csv"'})
