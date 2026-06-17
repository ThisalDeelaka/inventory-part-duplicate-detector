import pandas as pd

from app.engine.semantic_policy import REQUIRED_FIELDS


def profile_dataframe(df: pd.DataFrame, selected_fields: list[str] | None = None) -> dict:
    selected_fields = selected_fields or []
    missing_required = [field for field in REQUIRED_FIELDS if field not in df.columns]
    empty_descriptions = int(df["DESCRIPTION"].fillna("").str.strip().eq("").sum()) if "DESCRIPTION" in df else len(df)
    duplicate_part_rows = int(df["PART_NO"].fillna("").duplicated(keep=False).sum()) if "PART_NO" in df else 0
    high_null_selected_fields = {}
    for field in selected_fields:
        if field in df.columns and len(df):
            null_ratio = float(df[field].fillna("").astype(str).str.strip().eq("").sum()) / len(df)
            if null_ratio >= 0.5:
                high_null_selected_fields[field] = round(null_ratio * 100, 1)
    return {
        "record_count": len(df),
        "missing_required_columns": missing_required,
        "empty_descriptions_count": empty_descriptions,
        "duplicate_part_number_count": duplicate_part_rows,
        "high_null_selected_fields": high_null_selected_fields,
    }

