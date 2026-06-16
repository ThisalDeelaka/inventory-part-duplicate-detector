import hashlib
import re

import pandas as pd


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
PROJECT_RE = re.compile(r"\b(?:PROJECT|PROJ|JOB|WO|WORK\s*ORDER)[-_ /]?[A-Z0-9]{3,}\b", re.IGNORECASE)
SUPPLIER_RE = re.compile(r"\b(?:SUPPLIER|VENDOR|MAKE|BRAND|MFR|MANUFACTURER)[:\s-]+[A-Z0-9][A-Z0-9 ._-]{2,}\b", re.IGNORECASE)


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def security_transparency(file_hash: str | None = None, sensitive_mode: bool = True) -> dict:
    return {
        "sensitive_data_mode": sensitive_mode,
        "raw_csv_stored": False,
        "external_ai_used": False,
        "local_processing_only": True,
        "file_sha256": file_hash,
        "persisted_data": [
            "scan summary",
            "candidate pairs above threshold",
            "similarity scores",
            "explanations",
            "warnings",
            "review feedback",
        ],
        "not_persisted": ["uploaded raw CSV file"],
        "recommendation": "Deploy inside a customer-controlled environment for real ERP data.",
    }


def detect_sensitive_patterns(df: pd.DataFrame) -> list[dict]:
    warnings = []
    if df.empty:
        return warnings

    checks = [
        ("POSSIBLE_EMAIL", EMAIL_RE, "email-like values"),
        ("POSSIBLE_PHONE", PHONE_RE, "phone-like values"),
        ("POSSIBLE_PROJECT_REFERENCE", PROJECT_RE, "project/work-order references"),
        ("POSSIBLE_SUPPLIER_REFERENCE", SUPPLIER_RE, "supplier/vendor/manufacturer references"),
    ]

    text_columns = [column for column in df.columns if df[column].dtype == object]
    for warning_type, pattern, label in checks:
        matches = 0
        columns = set()
        for column in text_columns:
            series = df[column].fillna("").astype(str)
            column_matches = series.str.contains(pattern, regex=True).sum()
            if column_matches:
                matches += int(column_matches)
                columns.add(column)
        if matches:
            warnings.append({
                "warning_type": warning_type,
                "message": f"Detected {matches} {label} in columns: {', '.join(sorted(columns))}. Review data handling before sharing exports.",
            })
    return warnings
