import io
import json
import re

import pandas as pd
from fastapi import HTTPException, UploadFile

from app.core.constants import FIELD_ALIASES, FIELD_DEFINITIONS, REQUIRED_FIELDS
from app.core.config import settings
from app.services.privacy_service import detect_sensitive_patterns, file_sha256, security_transparency


CANONICAL_FIELDS = [item["field"] for item in FIELD_DEFINITIONS]
FIELD_DISPLAY_LOOKUP = {item["field"]: item["display"] for item in FIELD_DEFINITIONS}

CANONICAL_HEADER_ALIASES = {
    "PART_NO": ["PART NO", "PART NUMBER", "PART NO.", "PART#"],
    "DESCRIPTION": ["ITEM DESCRIPTION", "PART DESCRIPTION", "PART DESCRIPTION IN USE", "DESCRIPTION IN USE"],
    "CONTRACT": ["SITE", "SITE DESCRIPTION"],
    "TYPE_CODE": ["PART TYPE", "PURCHASE TYPE"],
    "UNIT_MEAS": ["INVENTORY UOM", "UNIT OF MEASURE", "UOM"],
    "PRIME_COMMODITY": ["COMMODITY GROUP 1", "COMMODITY GROUP 01", "COM GROUP 01"],
    "SECOND_COMMODITY": ["COMMODITY GROUP 2", "COMMODITY GROUP 02", "COM GROUP 02"],
    "HAZARD_CODE": ["SAFETY CODE"],
    "ACCOUNTING_GROUP": ["ACCOUNTING GROUP"],
    "PART_PRODUCT_CODE": ["PRODUCT CODE"],
    "PART_PRODUCT_FAMILY": ["PRODUCT FAMILY"],
    "PRODUCT_CATEGORY_ID": ["PRODUCT CATEGORY"],
    "HSN_SAC_CODE": ["HSN SAC CODE", "HSN/SAC CODE"],
}


def normalize_header(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").strip().upper())


def build_header_signature(columns: list[str]) -> str:
    normalized = sorted({normalize_header(column) for column in columns if normalize_header(column)})
    return "|".join(normalized)


def _load_json_list(value: str | list | None) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _build_header_lookup(profile_mapping: dict[str, str] | None = None) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for field in CANONICAL_FIELDS:
        lookup[normalize_header(field)] = (field, "exact")
        lookup[normalize_header(FIELD_DISPLAY_LOOKUP.get(field, ""))] = (field, "display")
    for source_header, canonical_field in (profile_mapping or {}).items():
        lookup[normalize_header(source_header)] = (canonical_field, "profile")
    for source, target in FIELD_ALIASES.items():
        lookup[normalize_header(source)] = (target, "alias")
    for field, aliases in CANONICAL_HEADER_ALIASES.items():
        for alias in aliases:
            lookup[normalize_header(alias)] = (field, "alias")
    return lookup


def resolve_canonical_field(column_name: str, profile_mapping: dict[str, str] | None = None) -> tuple[str | None, str]:
    normalized = normalize_header(column_name)
    if not normalized:
        return None, "unmapped"
    lookup = _build_header_lookup(profile_mapping)
    if normalized in lookup:
        return lookup[normalized]
    return None, "unmapped"


def _to_clean_series(series: pd.Series) -> pd.Series:
    cleaned = series.astype("string").fillna("").str.strip()
    return cleaned.replace({"nan": "", "None": "", "<NA>": ""})


def canonicalize_uploaded_dataframe(df: pd.DataFrame, profile_mapping: dict[str, str] | None = None) -> tuple[pd.DataFrame, dict]:
    mapped_sources: dict[str, list[dict]] = {field: [] for field in CANONICAL_FIELDS}
    mapping_preview: list[dict] = []
    unresolved_headers: list[str] = []
    source_columns = [str(column).strip() for column in df.columns]

    for source_column in source_columns:
        canonical_field, match_type = resolve_canonical_field(source_column, profile_mapping=profile_mapping)
        entry = {
            "source_column": source_column,
            "canonical_field": canonical_field,
            "match_type": match_type,
            "normalized_source": normalize_header(source_column),
        }
        mapping_preview.append(entry)
        if canonical_field:
            mapped_sources.setdefault(canonical_field, []).append(entry)
        else:
            unresolved_headers.append(source_column)

    normalized_df = df.copy()
    for field in CANONICAL_FIELDS:
        target = None
        if field in normalized_df.columns:
            target = _to_clean_series(normalized_df[field])
        for entry in mapped_sources.get(field, []):
            source_column = entry["source_column"]
            if source_column not in normalized_df.columns or source_column == field:
                continue
            source_values = _to_clean_series(normalized_df[source_column])
            if target is None:
                target = source_values
            else:
                target = target.mask(target.eq(""), source_values)
        if target is not None:
            normalized_df[field] = target

    return normalized_df, {
        "column_mapping": mapping_preview,
        "unmapped_source_columns": unresolved_headers,
        "mapped_canonical_fields": [field for field in CANONICAL_FIELDS if mapped_sources.get(field)],
        "header_signature": build_header_signature(source_columns),
    }


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
    if df.empty:
        raise HTTPException(400, "CSV contains no data rows")
    if len(df) > settings.max_csv_records:
        raise HTTPException(413, f"CSV contains {len(df)} records, above the configured synchronous scan limit of {settings.max_csv_records}")
    return df, {
        "file_sha256": file_sha256(content),
        "file_size_bytes": len(content),
        "raw_columns": [str(column).strip() for column in df.columns],
        "header_signature": build_header_signature([str(column).strip() for column in df.columns]),
    }


async def read_csv_upload(file: UploadFile) -> pd.DataFrame:
    df, _ = await read_csv_upload_with_metadata(file)
    return df


def normalize_selected_fields(selected_fields: list[str], profile_mapping: dict[str, str] | None = None) -> list[str]:
    return [resolve_canonical_field(field, profile_mapping=profile_mapping)[0] or str(field).strip().upper() for field in selected_fields]


def validate_dataframe(df: pd.DataFrame, selected_fields: list[str], sensitive_mode: bool = True, profile_mapping: dict[str, str] | None = None):
    selected_fields = normalize_selected_fields(selected_fields, profile_mapping=profile_mapping)
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
        "resolved_selected_fields": selected_fields,
        "privacy": security_transparency(sensitive_mode=sensitive_mode),
    }
