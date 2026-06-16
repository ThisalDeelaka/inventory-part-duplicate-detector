REQUIRED_FIELDS = {"PART_NO", "DESCRIPTION"}
SCOPE_FIELD = "CONTRACT"

HARD_IDENTITY_FIELDS = {
    "HSN_SAC_CODE",
    "UNIT_MEAS",
    "TYPE_CODE",
    "PRODUCT_CATEGORY_ID",
    "HAZARD_CODE",
}

SUPPORTING_FIELDS = {
    "PRIME_COMMODITY",
    "SECOND_COMMODITY",
    "ACCOUNTING_GROUP",
    "PART_PRODUCT_CODE",
    "PART_PRODUCT_FAMILY",
}

SCAN_MODES = {
    "SAME_SITE_DUPLICATE",
    "CROSS_SITE_STANDARDIZATION",
    "DISCOVERY",
}

DEFAULT_SCAN_MODE = "SAME_SITE_DUPLICATE"

BUSINESS_STATUSES = {
    "LIKELY_DUPLICATE",
    "POSSIBLE_DUPLICATE_REVIEW",
    "RELATED_BUT_NOT_DUPLICATE",
    "REJECTED_BY_BUSINESS_RULE",
    "DATA_CONFLICT_REVIEW",
    "CROSS_SITE_STANDARDIZATION_CANDIDATE",
    "INSUFFICIENT_DATA",
}

RULE_DECISIONS = {
    "ALLOW",
    "DOWNGRADE",
    "REJECT",
    "DATA_CONFLICT",
    "CROSS_SITE",
    "INSUFFICIENT_DATA",
}


def normalize_scan_mode(scan_mode: str | None) -> str:
    value = str(scan_mode or DEFAULT_SCAN_MODE).strip().upper()
    return value if value in SCAN_MODES else DEFAULT_SCAN_MODE


def clean_field_value(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text
