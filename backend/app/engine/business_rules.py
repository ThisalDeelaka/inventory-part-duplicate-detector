from app.engine.column_semantics import clean_field_value, normalize_scan_mode


def _differs(record_a, record_b, field: str) -> tuple[bool, str, str]:
    value_a = clean_field_value(record_a.get(field))
    value_b = clean_field_value(record_b.get(field))
    return bool(value_a and value_b and value_a.lower() != value_b.lower()), value_a, value_b


def evaluate_hard_business_rules(record_a, record_b, scan_mode: str):
    scan_mode = normalize_scan_mode(scan_mode)
    part_a = clean_field_value(record_a.get("PART_NO"))
    part_b = clean_field_value(record_b.get("PART_NO"))
    if part_a and part_b and part_a.lower() == part_b.lower():
        return {
            "blocked": True,
            "business_status": "REJECTED_BY_BUSINESS_RULE",
            "rule_decision": "REJECT",
            "rejection_reason": "SAME_PART_NO",
            "score_cap": 0.0,
            "explanation": "Same PART_NO detected. This is the same part reference, not a duplicate candidate.",
            "critical_mismatches": [],
        }

    contract_differs, contract_a, contract_b = _differs(record_a, record_b, "CONTRACT")

    hsn_differs, hsn_a, hsn_b = _differs(record_a, record_b, "HSN_SAC_CODE")
    if hsn_differs:
        return {
            "blocked": True,
            "business_status": "DATA_CONFLICT_REVIEW",
            "rule_decision": "DATA_CONFLICT",
            "rejection_reason": "HSN_SAC_CODE_MISMATCH",
            "score_cap": 45.0,
            "explanation": "HSN/SAC Code differs (HSN_SAC_CODE differs), so this cannot be treated as a confirmed duplicate.",
            "critical_mismatches": [{
                "group": "HSN_SAC_CODE",
                "label": "HSN/SAC Code",
                "values_a": [hsn_a],
                "values_b": [hsn_b],
            }],
        }

    unit_differs, unit_a, unit_b = _differs(record_a, record_b, "UNIT_MEAS")
    if unit_differs:
        return {
            "blocked": True,
            "business_status": "REJECTED_BY_BUSINESS_RULE",
            "rule_decision": "REJECT",
            "rejection_reason": "UNIT_MEAS_MISMATCH",
            "score_cap": 45.0,
            "explanation": f"Inventory UOM differs ({unit_a} vs {unit_b}).",
            "critical_mismatches": [{
                "group": "UNIT_MEAS",
                "label": "Inventory UOM",
                "values_a": [unit_a],
                "values_b": [unit_b],
            }],
        }

    category_differs, category_a, category_b = _differs(record_a, record_b, "PRODUCT_CATEGORY_ID")
    if category_differs:
        return {
            "blocked": True,
            "business_status": "REJECTED_BY_BUSINESS_RULE",
            "rule_decision": "REJECT",
            "rejection_reason": "PRODUCT_CATEGORY_ID_MISMATCH",
            "score_cap": 50.0,
            "explanation": "Product category differs.",
            "critical_mismatches": [{
                "group": "PRODUCT_CATEGORY_ID",
                "label": "Product category",
                "values_a": [category_a],
                "values_b": [category_b],
            }],
        }

    if scan_mode == "SAME_SITE_DUPLICATE" and contract_differs:
        return {
            "blocked": True,
            "business_status": "CROSS_SITE_STANDARDIZATION_CANDIDATE",
            "rule_decision": "CROSS_SITE",
            "rejection_reason": "CONTRACT_MISMATCH_IN_SAME_SITE_MODE",
            "score_cap": 55.0,
            "explanation": (
                "Different site detected in same-site duplicate mode. "
                "Treat this as a cross-site standardization candidate, not a normal duplicate."
            ),
            "critical_mismatches": [{
                "group": "CONTRACT",
                "label": "Site",
                "values_a": [contract_a],
                "values_b": [contract_b],
            }],
        }

    return {
        "blocked": False,
        "business_status": "",
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "score_cap": None,
        "explanation": "",
        "critical_mismatches": [],
    }
