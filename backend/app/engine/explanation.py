from app.core.constants import CRITICAL_MODIFIERS
from app.engine.normalizer import normalize_description


def build_explanation(record_a, record_b, matched, mismatched, description_similarity):
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
    if description_similarity >= 85 and matched:
        return "Descriptions are highly similar and selected business fields match."
    if matched:
        return f"Descriptions show meaningful similarity and {len(matched)} selected business field(s) match."
    return "Candidate is based mainly on description, part number, and technical token similarity."
