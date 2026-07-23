import json

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.core.config import Settings
from app.db.models import LlmAdvisorySnapshot, utcnow
from app.engine.column_semantics import normalize_scan_mode
from app.services.export_service import candidates_to_csv, rejections_to_csv
from app.services.grouping_service import build_duplicate_groups
from app.services.llm_export_service import (
    candidate_snapshot_capability,
    candidates_with_llm_to_csv,
    rejections_with_llm_to_csv,
)
from app.llm.runtime import get_llm_settings
from app.llm.service_contracts import LLMCapability
from app.services.llm_triage_service import (
    automatic_triage_ready,
    candidate_triage_fields,
    get_llm_triage_scheduler,
    get_triage_run,
    LlmTriageScheduler,
    prepare_triage_run,
    schedule_automatic_triage,
    triage_failure_categories,
    triage_run_json,
)
from app.services.scan_service import get_scan, get_scan_candidates, get_scan_rejections, get_scan_warnings, list_scans, run_scan
from app.services.privacy_service import security_transparency
from app.services.validation_service import parse_column_mapping, parse_selected_fields, read_csv_upload_with_metadata, validate_dataframe

router = APIRouter(prefix="/api/scans", tags=["scans"])


def _json_attr(obj, name, default):
    try:
        return json.loads(getattr(obj, name, None) or default)
    except (TypeError, json.JSONDecodeError):
        return json.loads(default)


def _bool_attr(obj, name):
    return str(getattr(obj, name, "false") or "false").lower() == "true"


def scan_json(scan, privacy=None):
    payload = {
        "id": scan.id, "scan_id": scan.id, "scan_name": scan.scan_name, "source_type": scan.source_type,
        "selected_fields": json.loads(scan.selected_fields), "threshold": scan.threshold, "status": scan.status,
        "total_records": scan.total_records, "total_candidates": scan.total_candidates, "warnings_count": scan.warnings_count,
        "rejections_count": getattr(scan, "rejections_count", 0) or 0,
        "started_at": scan.started_at, "completed_at": scan.completed_at, "model_version": scan.model_version,
        "scan_mode": getattr(scan, "scan_mode", "SAME_SITE_DUPLICATE"),
    }
    if privacy:
        payload["privacy"] = privacy
    return payload


def candidate_json(c, triage_snapshot=None, triage_run_state=None):
    payload = {
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
    payload.update(candidate_triage_fields(c, triage_snapshot, triage_run_state))
    return payload


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
    records = get_scan_candidates(db, scan_id)
    candidate_ids = [candidate.id for candidate in records]
    snapshots = db.query(LlmAdvisorySnapshot).filter(
        LlmAdvisorySnapshot.candidate_id.in_(candidate_ids),
        LlmAdvisorySnapshot.capability == LLMCapability.CANDIDATE_TRIAGE.value,
    ).all() if candidate_ids else []
    snapshot_map = {snapshot.candidate_id: snapshot for snapshot in snapshots}
    run = get_triage_run(db, scan_id)
    return [
        candidate_json(c, snapshot_map.get(c.id), run.state if run else None)
        for c in records
    ]


@router.get("/{scan_id}/groups")
def duplicate_groups(scan_id: int, db: Session = Depends(get_db)):
    if not get_scan(db, scan_id): raise HTTPException(404, "Scan not found")
    return build_duplicate_groups(get_scan_candidates(db, scan_id))


@router.get("/{scan_id}/warnings")
def warnings(scan_id: int, db: Session = Depends(get_db)):
    if not get_scan(db, scan_id): raise HTTPException(404, "Scan not found")
    return [{"id": w.id, "scan_id": w.scan_id, "warning_type": w.warning_type, "message": w.message, "record_reference": w.record_reference, "created_at": w.created_at} for w in get_scan_warnings(db, scan_id)]


@router.get("/{scan_id}/rejections")
def rejections(scan_id: int, db: Session = Depends(get_db)):
    if not get_scan(db, scan_id): raise HTTPException(404, "Scan not found")
    return [{
        "id": item.id,
        "scan_id": item.scan_id,
        "contract_a": item.contract_a,
        "part_no_a": item.part_no_a,
        "description_a": item.description_a,
        "contract_b": item.contract_b,
        "part_no_b": item.part_no_b,
        "description_b": item.description_b,
        "similarity_score": item.similarity_score,
        "confidence_level": item.confidence_level,
        "business_status": item.business_status,
        "rule_decision": item.rule_decision,
        "rejection_reason": item.rejection_reason,
        "critical_mismatches": _json_attr(item, "critical_mismatches", "[]"),
        "explanation": item.explanation,
        "created_at": item.created_at,
    } for item in get_scan_rejections(db, scan_id)]


@router.post("/validate-only")
async def validate_only(file: UploadFile = File(...), selected_fields: str = Form("[]"), column_mapping: str = Form("{}"), sensitive_mode: bool = Form(True)):
    df, metadata = await read_csv_upload_with_metadata(file, parse_column_mapping(column_mapping))
    result = validate_dataframe(df, parse_selected_fields(selected_fields), sensitive_mode=sensitive_mode)
    result.update({key: metadata[key] for key in ("available_columns", "resolved_column_mapping", "normalized_columns", "column_mapping_conflicts", "column_samples")})
    for target, sources in metadata["column_mapping_conflicts"].items():
        result["warnings"].append({
            "warning_type": "AMBIGUOUS_COLUMN_MAPPING",
            "message": f"Multiple uploaded columns could be {target}: {', '.join(sources)}. Choose the correct column in CSV column mapping and validate again.",
        })
    result["privacy"] = security_transparency(file_hash=metadata["file_sha256"], sensitive_mode=sensitive_mode)
    result["privacy"]["file_size_bytes"] = metadata["file_size_bytes"]
    return result


@router.post("/upload")
async def upload(background_tasks: BackgroundTasks, file: UploadFile = File(...), selected_fields: str = Form("[]"), column_mapping: str = Form("{}"), threshold: float = Form(75), scan_name: str = Form("Inventory duplicate scan"), sensitive_mode: bool = Form(True), scan_mode: str = Form("SAME_SITE_DUPLICATE"), db: Session = Depends(get_db), configuration: Settings = Depends(get_llm_settings), triage_scheduler: LlmTriageScheduler = Depends(get_llm_triage_scheduler)):
    if threshold < 0 or threshold > 100: raise HTTPException(400, "threshold must be between 0 and 100")
    df, metadata = await read_csv_upload_with_metadata(file, parse_column_mapping(column_mapping))
    validation = validate_dataframe(df, parse_selected_fields(selected_fields), sensitive_mode=sensitive_mode)
    if validation["missing_required_columns"]: raise HTTPException(422, {"message": "Missing required columns", "columns": validation["missing_required_columns"]})
    try:
        scan, _ = run_scan(db, df, scan_name.strip() or "Inventory duplicate scan", parse_selected_fields(selected_fields), threshold, sensitive_mode=sensitive_mode, scan_mode=normalize_scan_mode(scan_mode))
        try:
            schedule_automatic_triage(
                db, background_tasks, scan.id, configuration, triage_scheduler
            )
        except Exception:
            db.rollback()
            run = get_triage_run(db, scan.id)
            if run is not None:
                run.state = "FAILED"
                run.last_safe_error_category = "scheduling_failure"
                run.completed_at = utcnow()
                run.updated_at = utcnow()
                db.commit()
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


@router.get("/{scan_id}/rejections/export")
def export_rejections(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan(db, scan_id)
    if not scan: raise HTTPException(404, "Scan not found")
    return Response(
        rejections_to_csv(get_scan_rejections(db, scan_id)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="scan-{scan_id}-rule-exclusions.csv"'},
    )


@router.get("/{scan_id}/export-with-llm")
def export_with_llm(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan(db, scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    candidates = get_scan_candidates(db, scan_id)
    candidate_ids = [candidate.id for candidate in candidates]
    snapshots = []
    if candidate_ids:
        snapshots = db.query(LlmAdvisorySnapshot).filter(
            LlmAdvisorySnapshot.candidate_id.in_(candidate_ids),
            LlmAdvisorySnapshot.capability.in_([
                candidate_snapshot_capability(),
                LLMCapability.CANDIDATE_TRIAGE.value,
            ]),
        ).all()
    snapshot_map = {
        snapshot.candidate_id: snapshot for snapshot in snapshots
        if snapshot.capability == candidate_snapshot_capability()
    }
    triage_snapshot_map = {
        snapshot.candidate_id: snapshot for snapshot in snapshots
        if snapshot.capability == LLMCapability.CANDIDATE_TRIAGE.value
    }
    run = get_triage_run(db, scan_id)
    return Response(
        candidates_with_llm_to_csv(
            candidates,
            snapshot_map,
            triage_snapshot_map,
            run.state if run else "NOT_STARTED",
        ),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="scan-{scan_id}-candidates-with-llm.csv"'},
    )


@router.get("/{scan_id}/rejections/export-with-llm")
def export_rejections_with_llm(scan_id: int, db: Session = Depends(get_db)):
    scan = get_scan(db, scan_id)
    if not scan:
        raise HTTPException(404, "Scan not found")
    return Response(
        rejections_with_llm_to_csv(get_scan_rejections(db, scan_id)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="scan-{scan_id}-rule-exclusions-with-llm.csv"'},
    )


def _require_triage_ready(configuration: Settings) -> None:
    if not automatic_triage_ready(configuration):
        raise HTTPException(
            503,
            {
                "category": "configuration",
                "message": "Automatic LLM triage is disabled or unavailable",
            },
        )


@router.post("/{scan_id}/llm-triage")
def start_llm_triage(
    scan_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    configuration: Settings = Depends(get_llm_settings),
    triage_scheduler: LlmTriageScheduler = Depends(get_llm_triage_scheduler),
):
    if not get_scan(db, scan_id):
        raise HTTPException(404, "Scan not found")
    _require_triage_ready(configuration)
    run, should_schedule = prepare_triage_run(
        db,
        scan_id,
        configuration,
        active=triage_scheduler.is_active(scan_id),
    )
    if should_schedule:
        try:
            triage_scheduler.schedule(background_tasks, scan_id)
        except Exception:
            run.state = "FAILED"
            run.last_safe_error_category = "scheduling_failure"
            run.completed_at = utcnow()
            run.updated_at = utcnow()
            db.commit()
            raise HTTPException(
                500,
                {
                    "category": "scheduling_failure",
                    "message": "LLM triage could not be scheduled safely",
                },
            ) from None
    return triage_run_json(run, triage_failure_categories(db, scan_id))


@router.get("/{scan_id}/llm-triage")
def llm_triage_status(scan_id: int, db: Session = Depends(get_db)):
    if not get_scan(db, scan_id):
        raise HTTPException(404, "Scan not found")
    run = get_triage_run(db, scan_id)
    if run is None:
        raise HTTPException(404, "LLM triage has not been started")
    return triage_run_json(run, triage_failure_categories(db, scan_id))


@router.post("/{scan_id}/llm-triage/retry-failed")
def retry_failed_llm_triage(
    scan_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    configuration: Settings = Depends(get_llm_settings),
    triage_scheduler: LlmTriageScheduler = Depends(get_llm_triage_scheduler),
):
    if not get_scan(db, scan_id):
        raise HTTPException(404, "Scan not found")
    _require_triage_ready(configuration)
    run, should_schedule = prepare_triage_run(
        db,
        scan_id,
        configuration,
        retry_failed=True,
        active=triage_scheduler.is_active(scan_id),
    )
    if should_schedule:
        try:
            triage_scheduler.schedule(background_tasks, scan_id, retry_failed=True)
        except Exception:
            run.state = "FAILED"
            run.last_safe_error_category = "scheduling_failure"
            run.completed_at = utcnow()
            run.updated_at = utcnow()
            db.commit()
            raise HTTPException(
                500,
                {
                    "category": "scheduling_failure",
                    "message": "Failed LLM triage items could not be scheduled safely",
                },
            ) from None
    return triage_run_json(run, triage_failure_categories(db, scan_id))
