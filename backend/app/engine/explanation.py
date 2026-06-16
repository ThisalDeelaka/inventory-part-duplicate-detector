from app.core.constants import CRITICAL_MODIFIERS, STRICT_MISMATCH_FIELDS
from app.engine.normalizer import normalize_description, normalize_part_no_with_dictionary
from app.engine.similarity_model import calculate_part_no_similarity


def _clean(value):
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def build_explanation(record_a, record_b, matched, mismatched, description_similarity):
    part_a, part_b = _clean(record_a.get("PART_NO")), _clean(record_b.get("PART_NO"))
    if part_a and part_b and part_a.lower() == part_b.lower():
        return "Same PART_NO detected, so this is treated as the same part across records/sites rather than a duplicate master candidate."
    unit_a, unit_b = _clean(record_a.get("UNIT_MEAS")), _clean(record_b.get("UNIT_MEAS"))
    if unit_a and unit_b and unit_a.lower() != unit_b.lower():
        return f"Inventory UOM differs ({unit_a} vs {unit_b}), so this should not be treated as the same duplicate part without master-data review."
    strict_mismatches = []
    for field in STRICT_MISMATCH_FIELDS - {"UNIT_MEAS"}:
        value_a, value_b = _clean(record_a.get(field)), _clean(record_b.get(field))
        if value_a and value_b and value_a.lower() != value_b.lower():
            strict_mismatches.append(f"{field} differs ({value_a} vs {value_b})")
    if strict_mismatches:
        return f"{'; '.join(sorted(strict_mismatches))}, so the candidate is blocked by strict ERP field semantics."
    a_words = set(normalize_description(record_a.get("DESCRIPTION")).split())
    b_words = set(normalize_description(record_b.get("DESCRIPTION")).split())
    critical_a, critical_b = a_words & CRITICAL_MODIFIERS, b_words & CRITICAL_MODIFIERS
    if critical_a != critical_b and critical_a and critical_b:
        return f"Descriptions are similar, but critical modifier differs: {', '.join(sorted(critical_a))} vs {', '.join(sorted(critical_b))}."
    contract_a, contract_b = record_a.get("CONTRACT"), record_b.get("CONTRACT")
    if contract_a and contract_b and str(contract_a).strip().lower() != str(contract_b).strip().lower():
        return "Different site detected. Treat as cross-site possible duplicate."
    classification = {"PRIME_COMMODITY", "SECOND_COMMODITY", "PART_PRODUCT_CODE", "PART_PRODUCT_FAMILY", "PRODUCT_CATEGORY_ID"}
    if classification & set(mismatched):
        return "Selected business fields are similar, but product classification differs."
    if not (classification & set(matched)) and all(not record_a.get(f) or not record_b.get(f) for f in classification):
        return "Classification fields are missing, so the result is based mainly on description similarity."
    normalized_part_a = normalize_part_no_with_dictionary(record_a.get("PART_NO"))
    normalized_part_b = normalize_part_no_with_dictionary(record_b.get("PART_NO"))
    if description_similarity >= 80 and calculate_part_no_similarity(record_a.get("PART_NO"), record_b.get("PART_NO")) >= 90 and normalized_part_a and normalized_part_b:
        return "Descriptions and part numbers match after business synonym normalization."
    if description_similarity >= 85 and matched:
        return "Descriptions are highly similar and selected business fields match."
    if matched:
        return f"Descriptions show meaningful similarity and {len(matched)} selected business field(s) match."
    return "Candidate is based mainly on description, part number, and technical token similarity."
