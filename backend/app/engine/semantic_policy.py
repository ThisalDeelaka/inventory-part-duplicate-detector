from app.engine.column_semantics import clean_field_value, normalize_scan_mode


REQUIRED_FIELDS = {"PART_NO", "DESCRIPTION"}
SCOPE_FIELD = "CONTRACT"
HARD_IDENTITY_FIELDS = {"HSN_SAC_CODE", "UNIT_MEAS", "TYPE_CODE", "PRODUCT_CATEGORY_ID", "HAZARD_CODE"}
SUPPORTING_FIELDS = {
    "PRIME_COMMODITY",
    "SECOND_COMMODITY",
    "ACCOUNTING_GROUP",
    "PART_PRODUCT_CODE",
    "PART_PRODUCT_FAMILY",
}


def compare_selected_fields(record_a: dict, record_b: dict, selected_fields: list[str]):
    matched, mismatched, comparable = [], [], 0
    for field in selected_fields:
        value_a = clean_field_value(record_a.get(field))
        value_b = clean_field_value(record_b.get(field))
        if not value_a or not value_b:
            continue
        comparable += 1
        if value_a.lower() == value_b.lower():
            matched.append(field)
        else:
            mismatched.append(field)
    business_score = (len(matched) / comparable * 100) if comparable else 50.0
    return matched, mismatched, business_score


def scan_mode_allows_cross_site(scan_mode: str) -> bool:
    return normalize_scan_mode(scan_mode) in {"CROSS_SITE_STANDARDIZATION", "DISCOVERY"}


def field_diff(record_a: dict, record_b: dict, field: str):
    value_a = clean_field_value(record_a.get(field))
    value_b = clean_field_value(record_b.get(field))
    differs = bool(value_a and value_b and value_a.lower() != value_b.lower())
    return differs, value_a, value_b

