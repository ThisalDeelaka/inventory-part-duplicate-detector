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

