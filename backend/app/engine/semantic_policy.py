from app.engine.column_semantics import clean_field_value, normalize_scan_mode


DEFAULT_COLUMN_POLICY = {
    "CONTRACT": {
        "meaning": "Site / contract",
        "role": "scope",
        "importance": "high",
        "behavior_if_same": "Compare as same-site candidate when same-site mode is selected.",
        "behavior_if_different": "Treat as cross-site standardization candidate in cross-site mode; do not confirm as same-site duplicate.",
        "behavior_if_missing": "Continue, but scope confidence is reduced.",
    },
    "PART_NO": {
        "meaning": "Part number",
        "role": "identity_evidence",
        "importance": "high",
        "behavior_if_same": "Treat as same part reference, not a duplicate master candidate.",
        "behavior_if_different": "Use normalized part-number similarity as evidence.",
        "behavior_if_missing": "Continue from description and classification evidence.",
    },
    "DESCRIPTION": {
        "meaning": "Item description",
        "role": "semantic_description",
        "importance": "required",
        "behavior_if_same": "Strong semantic evidence.",
        "behavior_if_different": "Use normalization, attribute extraction, and local similarity.",
        "behavior_if_missing": "Record cannot be scored reliably.",
    },
    "MASTER_PART_DESCRIPTION": {
        "meaning": "Common/master item description",
        "role": "strong_semantic_description",
        "importance": "high",
        "behavior_if_same": "Stronger common-description evidence.",
        "behavior_if_different": "Review alongside DESCRIPTION and extracted attributes.",
        "behavior_if_missing": "Fall back to DESCRIPTION.",
    },
    "PART_TYPE": {
        "meaning": "Part type / purchase type",
        "role": "strong_classification",
        "importance": "high",
        "behavior_if_same": "Supports duplicate candidate.",
        "behavior_if_different": "Downgrade or review; not always a hard veto.",
        "behavior_if_missing": "Continue with warning-level uncertainty.",
    },
    "INVENTORY_UOM": {
        "meaning": "Inventory unit of measure",
        "role": "strong_identity",
        "importance": "high",
        "behavior_if_same": "Supports duplicate candidate.",
        "behavior_if_different": "Create data conflict/review state instead of confirmed duplicate.",
        "behavior_if_missing": "Continue, but unit evidence is unavailable.",
    },
    "COMMODITY_GROUP_1": {
        "meaning": "Primary commodity group",
        "role": "supporting_classification",
        "importance": "medium",
        "behavior_if_same": "Supports candidate confidence.",
        "behavior_if_different": "Downgrade/review; not a hard veto.",
        "behavior_if_missing": "Continue.",
    },
    "COMMODITY_GROUP_2": {
        "meaning": "Secondary commodity group",
        "role": "supporting_classification",
        "importance": "medium",
        "behavior_if_same": "Supports candidate confidence.",
        "behavior_if_different": "Downgrade/review; not a hard veto.",
        "behavior_if_missing": "Continue.",
    },
    "SAFETY_CODE": {
        "meaning": "Safety/hazard code",
        "role": "data_conflict_safety",
        "importance": "high",
        "behavior_if_same": "Supports duplicate candidate.",
        "behavior_if_different": "Create data conflict review; safety attributes differ.",
        "behavior_if_missing": "Continue, but safety evidence is unavailable.",
    },
    "ACCOUNTING_GROUP": {
        "meaning": "Accounting group",
        "role": "supporting_classification",
        "importance": "medium",
        "behavior_if_same": "Supports candidate confidence.",
        "behavior_if_different": "Downgrade/review; accounting treatment differs.",
        "behavior_if_missing": "Continue.",
    },
    "PART_PRODUCT_CODE": {
        "meaning": "Product code",
        "role": "supporting_classification",
        "importance": "medium",
        "behavior_if_same": "Supports candidate confidence.",
        "behavior_if_different": "Downgrade/review; product coding differs.",
        "behavior_if_missing": "Continue.",
    },
    "PART_PRODUCT_FAMILY": {
        "meaning": "Product family",
        "role": "supporting_classification",
        "importance": "medium",
        "behavior_if_same": "Supports candidate confidence.",
        "behavior_if_different": "Downgrade/review; product family differs.",
        "behavior_if_missing": "Continue.",
    },
    "PRODUCT_CATEGORY_ID": {
        "meaning": "Product category",
        "role": "strong_classification",
        "importance": "high",
        "behavior_if_same": "Supports duplicate candidate.",
        "behavior_if_different": "Data conflict/review state; category differs.",
        "behavior_if_missing": "Continue, but category evidence is unavailable.",
    },
    "HSN_SAC_CODE": {
        "meaning": "HSN/SAC compliance code",
        "role": "data_conflict_compliance",
        "importance": "high",
        "behavior_if_same": "Supports duplicate candidate.",
        "behavior_if_different": "Create DATA_CONFLICT_REVIEW, not confirmed duplicate.",
        "behavior_if_missing": "Continue, but compliance evidence is unavailable.",
    },
}

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
