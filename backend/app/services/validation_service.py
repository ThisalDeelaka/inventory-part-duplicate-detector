import io

import pandas as pd
from fastapi import HTTPException, UploadFile

from app.core.constants import FIELD_ALIASES, REQUIRED_FIELDS
from app.core.config import settings
from app.services.privacy_service import detect_sensitive_patterns, file_sha256, security_transparency


def parse_selected_fields(value: str | None) -> list[str]:
    if not value:
        return []
    value = value.strip()
    if value.startswith("["):
        import json
        try:
            parsed = json.loads(value)
            return [str(item).strip().upper() for item in parsed]
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(400, "selected_fields must be a JSON list or comma-separated fields")
    return [item.strip().upper() for item in value.split(",") if item.strip()]


async def read_csv_upload_with_metadata(file: UploadFile) -> tuple[pd.DataFrame, dict]:
    content = await file.read()
    if not content:
        raise HTTPException(400, "CSV file is empty")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f"CSV file exceeds the configured upload limit of {settings.max_upload_bytes} bytes")
    try:
        df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=True)
    except Exception as exc:
        raise HTTPException(400, f"Unable to parse CSV: {exc}") from exc
    df.columns = [str(c).strip().upper() for c in df.columns]
    df = df.rename(columns={old: new for old, new in FIELD_ALIASES.items() if new not in df.columns})
    if df.empty:
        raise HTTPException(400, "CSV contains no data rows")
    if len(df) > settings.max_csv_records:
        raise HTTPException(413, f"CSV contains {len(df)} records, above the configured synchronous scan limit of {settings.max_csv_records}")
    return df, {"file_sha256": file_sha256(content), "file_size_bytes": len(content)}


async def read_csv_upload(file: UploadFile) -> pd.DataFrame:
    df, _ = await read_csv_upload_with_metadata(file)
    return df


def validate_dataframe(df: pd.DataFrame, selected_fields: list[str], sensitive_mode: bool = True):
    missing_required = [field for field in REQUIRED_FIELDS if field not in df.columns]
    missing_selected = [field for field in selected_fields if field not in df.columns]
    empty_descriptions = int(df["DESCRIPTION"].fillna("").str.strip().eq("").sum()) if "DESCRIPTION" in df else len(df)
    duplicate_parts = int(df["PART_NO"].fillna("").duplicated(keep=False).sum()) if "PART_NO" in df else 0
    high_null = {}
    for field in selected_fields:
        if field in df:
            ratio = float(df[field].fillna("").str.strip().eq("").sum()) / len(df)
            if ratio >= 0.5:
                high_null[field] = round(ratio * 100, 1)
    warnings = []
    if empty_descriptions:
        warnings.append({"warning_type": "EMPTY_DESCRIPTION", "message": f"{empty_descriptions} record(s) have empty descriptions and will be skipped."})
    if duplicate_parts:
        warnings.append({"warning_type": "DUPLICATE_PART_NO", "message": f"{duplicate_parts} row(s) use a repeated part number."})
    for field in missing_selected:
        warnings.append({"warning_type": "MISSING_SELECTED_FIELD", "message": f"Selected field {field} is unavailable and will be ignored."})
    for field, percent in high_null.items():
        warnings.append({"warning_type": "HIGH_NULL_FIELD", "message": f"Selected field {field} is {percent}% empty."})
    if sensitive_mode:
        warnings.extend(detect_sensitive_patterns(df))
    return {
        "valid": not missing_required,
        "record_count": len(df), "missing_required_columns": missing_required,
        "missing_optional_selected_columns": missing_selected,
        "empty_descriptions_count": empty_descriptions,
        "duplicate_part_number_count": duplicate_parts,
        "high_null_selected_fields": high_null, "warnings": warnings,
        "privacy": security_transparency(sensitive_mode=sensitive_mode),
    }
