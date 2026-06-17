from app.engine.item_family_classifier import shared_family


def critical_mismatch_explanation(profile_a, profile_b, mismatch: dict) -> str:
    family = shared_family(profile_a.description, profile_b.description)
    left = ", ".join(mismatch["values_a"])
    right = ", ".join(mismatch["values_b"])
    return f"Both are {family}, but {mismatch['label']} differs: {left} vs {right}."


def duplicate_explanation(profile_a, profile_b, matched_fields: list[str], description_similarity: float, part_no_similarity: float) -> str:
    if description_similarity >= 80 and part_no_similarity >= 90:
        return "Descriptions and part numbers match after business synonym normalization."
    if description_similarity >= 85 and matched_fields:
        return "Descriptions are highly similar and selected business fields match."
    if matched_fields:
        return f"Descriptions show meaningful similarity and {len(matched_fields)} selected business field(s) match."
    return "Candidate is based mainly on description, part number, and technical token similarity."


def append_warning(explanation: str, warning: str) -> str:
    if not warning:
        return explanation
    return f"{explanation} {warning}"


def _join(values) -> str:
    return ", ".join(str(value) for value in values if value)


def _feature_values(differences: list[dict], feature: str) -> tuple[list[str], list[str]]:
    for item in differences:
        if item.get("feature") == feature or item.get("type") == feature:
            return item.get("values_a", []), item.get("values_b", [])
    return [], []


def _normalized_phrase(decision) -> str:
    candidates = [
        decision.normalized_description_a,
        decision.normalized_description_b,
        decision.normalized_part_no_a,
        decision.normalized_part_no_b,
    ]
    for value in candidates:
        if value:
            return value
    return ""


def _matched_summary(decision) -> str:
    if not decision.matched_evidence:
        return "Matching evidence is limited."
    readable = [item.replace("_", " ").replace("field:", "field ") for item in decision.matched_evidence[:5]]
    return f"Matching evidence includes {', '.join(readable)}."


def _warning_summary(decision) -> str:
    if not decision.warnings:
        return ""
    return "Warnings: " + " ".join(decision.warnings)


def _both_are(decision, attribute: str, fallback: str) -> str:
    values_a = set(decision.extracted_attributes_a.get(attribute, []))
    values_b = set(decision.extracted_attributes_b.get(attribute, []))
    shared = sorted(values_a & values_b)
    return _join(shared) if shared else fallback


def generate_explanation(candidate, similarity, guardrails, decision) -> str:
    status = decision.status
    parts = [f"Status: {status}."]

    if status == "DUPLICATE_CANDIDATE":
        phrase = _normalized_phrase(decision)
        parts.append("Descriptions and part numbers match after business synonym normalization.")
        if phrase:
            parts.append(f"Normalized evidence includes '{phrase}'.")
        parts.append("No critical conflicts were found.")
    elif status == "RELATED_BUT_NOT_DUPLICATE":
        if "rating_mismatch" in guardrails.conflict_types:
            left, right = _feature_values(similarity.mismatched_features, "rating")
            family = _both_are(decision, "product_class", "items")
            parts.append(f"Both are {family} items, but rating differs: {_join(left)} vs {_join(right)}.")
        elif "color_mismatch" in guardrails.conflict_types:
            left, right = _feature_values(similarity.mismatched_features, "color")
            family = _both_are(decision, "product_class", "items")
            parts.append(f"Both are {family} items, but color differs: {_join(left)} vs {_join(right)}.")
        elif "function_or_media_mismatch" in guardrails.conflict_types:
            left, right = _feature_values(similarity.mismatched_features, "function_or_media")
            context = _both_are(decision, "application_context", "")
            family = _both_are(decision, "product_class", "items")
            descriptor = f"{context} {family}".strip()
            parts.append(f"Both are {descriptor}, but function/media differs: {_join(left)} vs {_join(right)}.")
        elif "type_code_mismatch" in guardrails.conflict_types:
            left, right = _feature_values(similarity.mismatched_features, "type_code")
            family = _both_are(decision, "product_class", "items")
            parts.append(f"Both are {family} items, but type code differs: {_join(left)} vs {_join(right)}.")
        else:
            parts.append("Critical differentiators differ, so the records are related but not duplicate candidates.")
    elif status in {"INSUFFICIENT_DATA", "POSSIBLE_DUPLICATE_REVIEW"} and "generic_or_sparse_description" in guardrails.warning_types:
        parts.append("One description is generic or sparse.")
        parts.append("The system cannot confirm duplicate identity with high confidence from the available evidence.")
    elif status == "DATA_CONFLICT_REVIEW":
        if "hsn_sac_mismatch" in guardrails.conflict_types:
            evidence = next((item for item in guardrails.rule_evidence if item.get("type") == "hsn_sac_mismatch"), {})
            parts.append(f"HSN/SAC values differ: {_join(evidence.get('values_a', []))} vs {_join(evidence.get('values_b', []))}.")
        elif "safety_code_mismatch" in guardrails.conflict_types:
            evidence = next((item for item in guardrails.rule_evidence if item.get("type") == "safety_code_mismatch"), {})
            parts.append(f"Safety code values differ: {_join(evidence.get('values_a', []))} vs {_join(evidence.get('values_b', []))}.")
        parts.append("This is a data conflict, not a confirmed duplicate.")
    elif status == "CROSS_SITE_STANDARDIZATION_CANDIDATE":
        left = candidate.record_a.raw.get("CONTRACT", "")
        right = candidate.record_b.raw.get("CONTRACT", "")
        parts.append(f"Records are from different CONTRACT/site values: {left} vs {right}.")
        parts.append("Treat this as a possible standardization candidate, not a same-site duplicate.")
    elif status == "UNIQUE_NO_MATCH":
        parts.append("Similarity is too low or scope rules prevent normal duplicate review.")
    else:
        parts.append("Manual review is recommended based on similarity and available business evidence.")

    parts.append(_matched_summary(decision))
    warning_text = _warning_summary(decision)
    if warning_text:
        parts.append(warning_text)
    return " ".join(part for part in parts if part)
