import io
import json
import re
import unicodedata

import pandas as pd
from fastapi import HTTPException, UploadFile

from app.core.constants import (
    FALLBACK_FIELD_ALIASES,
    FIELD_ALIASES,
    FIELD_DEFINITIONS,
    REQUIRED_FIELDS,
)
from app.core.config import settings
from app.repositories.custom_field_repository import CustomFieldRepository
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


def normalize_column_name(value: str) -> str:
    """Convert display-style ERP headers to stable machine-style names."""
    text = unicodedata.normalize("NFKC", str(value)).lstrip("\ufeff").strip().upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def parse_column_mapping(value: str | None, custom_field_keys: set[str] | None = None) -> dict[str, str]:
    """Parse a canonical-field -> uploaded-column mapping supplied by the UI/API."""
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(400, "column_mapping must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(400, "column_mapping must be a JSON object")

    allowed = {item["field"] for item in FIELD_DEFINITIONS} | set(custom_field_keys or [])
    result = {}
    for canonical, source in parsed.items():
        canonical_name = normalize_column_name(canonical)
        source_name = str(source).strip()
        if canonical_name not in allowed:
            raise HTTPException(400, f"Unsupported canonical field in column_mapping: {canonical}")
        if source_name:
            result[canonical_name] = source_name
    return result


def apply_column_mapping(
    df: pd.DataFrame,
    explicit_mapping: dict[str, str] | None = None,
    custom_field_aliases: dict[str, str] | None = None,
    custom_field_keys: set[str] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Resolve uploaded headers to canonical fields, with explicit mappings winning."""
    explicit_mapping = explicit_mapping or {}
    custom_field_aliases = custom_field_aliases or {}
    original_columns = [str(column) for column in df.columns]
    normalized_lookup: dict[str, list[str]] = {}
    for column in original_columns:
        normalized_lookup.setdefault(normalize_column_name(column), []).append(column)

    # A historical IFS export can contain both a preferred description column
    # and a compatibility fallback.  Decide whether the fallback is needed
    # before iterating so source-column order cannot create a false collision.
    primary_targets = {
        FIELD_ALIASES.get(normalized, normalized)
        for normalized in normalized_lookup
        if normalized not in FALLBACK_FIELD_ALIASES
    }

    explicit_sources = {}
    for canonical, requested_source in explicit_mapping.items():
        matches = normalized_lookup.get(normalize_column_name(requested_source), [])
        if len(matches) != 1:
            detail = "was not found" if not matches else "matches multiple uploaded columns"
            raise HTTPException(400, f"Mapped column {requested_source!r} for {canonical} {detail}")
        if matches[0] in explicit_sources:
            raise HTTPException(400, f"Uploaded column {requested_source!r} cannot map to more than one canonical field")
        explicit_sources[matches[0]] = canonical

    reserved_targets = set(explicit_sources.values())
    renamed = {}
    resolved = {}
    target_sources: dict[str, list[str]] = {}
    canonical_fields = {item["field"] for item in FIELD_DEFINITIONS} | set(custom_field_keys or [])
    for position, source in enumerate(original_columns, start=1):
        normalized = normalize_column_name(source)
        if source in explicit_sources:
            target = explicit_sources[source]
        else:
            if normalized in FALLBACK_FIELD_ALIASES:
                fallback_target = FALLBACK_FIELD_ALIASES[normalized]
                automatic = (
                    normalized if fallback_target in primary_targets else fallback_target
                )
            else:
                automatic = FIELD_ALIASES.get(normalized, custom_field_aliases.get(normalized, normalized))
            target = f"UNMAPPED_{normalized}_{position}" if automatic in reserved_targets else automatic
        renamed[source] = target
        target_sources.setdefault(target, []).append(source)
        if target in canonical_fields:
            resolved[target] = source

    collisions = {target: sources for target, sources in target_sources.items() if len(sources) > 1}
    for target, sources in collisions.items():
        resolved.pop(target, None)
        for source in sources:
            position = original_columns.index(source) + 1
            renamed[source] = f"UNMAPPED_{normalize_column_name(source)}_{position}"

    mapped = df.rename(columns=renamed)
    return mapped, {
        "available_columns": original_columns,
        "resolved_column_mapping": resolved,
        "normalized_columns": list(mapped.columns),
        "column_mapping_conflicts": collisions,
    }


def bounded_nonblank_samples(values, limit: int = 5, max_characters: int = 512) -> list[str]:
    """Collect a bounded useful prefix without consuming the remaining iterable."""
    samples = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value)
        if not text.strip():
            continue
        samples.append(text[:max_characters])
        if len(samples) == limit:
            break
    return samples


def bounded_column_samples(
    df: pd.DataFrame, unresolved_columns: list[str]
) -> dict[str, list[str]]:
    """Return bounded samples for unresolved source columns in source order."""
    unresolved = set(unresolved_columns)
    return {
        str(column): bounded_nonblank_samples(df[column])
        for column in df.columns
        if str(column) in unresolved
    }


XLSX_EXTENSIONS = (".xlsx",)


def _parse_upload_dataframe(filename: str | None, content: bytes) -> pd.DataFrame:
    """Parse an uploaded CSV or XLSX file into a DataFrame, so both formats share the same downstream flow."""
    is_xlsx = str(filename or "").strip().lower().endswith(XLSX_EXTENSIONS)
    try:
        if is_xlsx:
            return pd.read_excel(io.BytesIO(content), dtype=str, engine="openpyxl")
        return pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=True)
    except Exception as exc:
        kind = "XLSX" if is_xlsx else "CSV"
        raise HTTPException(400, f"Unable to parse {kind} file: {exc}") from exc


async def read_csv_upload_with_metadata(
    file: UploadFile,
    column_mapping: dict[str, str] | None = None,
    custom_fields: list | None = None,
    db=None,
) -> tuple[pd.DataFrame, dict]:
    content = await file.read()
    if not content:
        raise HTTPException(400, "Uploaded file is empty")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f"Uploaded file exceeds the configured upload limit of {settings.max_upload_bytes} bytes")
    df = _parse_upload_dataframe(file.filename, content)
    source_df = df
    custom_fields = custom_fields or []
    custom_field_keys = {field.field_key for field in custom_fields}
    custom_field_aliases = {}
    for field in custom_fields:
        for alias in json.loads(field.aliases or "[]"):
            custom_field_aliases[alias] = field.field_key
    df, column_metadata = apply_column_mapping(source_df, column_mapping, custom_field_aliases, custom_field_keys)
    if db is not None and column_mapping:
        field_by_key = {field.field_key: field for field in custom_fields}
        repo = CustomFieldRepository(db)
        for canonical, requested_source in column_mapping.items():
            field = field_by_key.get(canonical)
            if not field:
                continue
            normalized_source = normalize_column_name(requested_source)
            known_aliases = set(json.loads(field.aliases or "[]"))
            if normalized_source != field.field_key and normalized_source not in known_aliases:
                repo.record_alias(field, normalized_source)
    if df.empty:
        raise HTTPException(400, "CSV contains no data rows")
    if len(df) > settings.max_csv_records:
        raise HTTPException(413, f"CSV contains {len(df)} records, above the configured synchronous scan limit of {settings.max_csv_records}")
    resolved_sources = set(column_metadata["resolved_column_mapping"].values())
    unresolved_columns = [
        column
        for column in column_metadata["available_columns"]
        if column not in resolved_sources
    ]
    column_samples = bounded_column_samples(source_df, unresolved_columns)
    return df, {
        "file_sha256": file_sha256(content),
        "file_size_bytes": len(content),
        "column_samples": column_samples,
        **column_metadata,
    }


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
