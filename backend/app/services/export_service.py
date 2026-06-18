import csv
import io
import json


def sanitize_csv_cell(value):
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def serialize_csv_value(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(serialize_csv_value(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return sanitize_csv_cell(value)


def candidate_value(candidate, field):
    value = getattr(candidate, field, None)
    if value is None:
        return ""
    if field in {
        "matched_evidence",
        "differences",
        "warnings",
        "extracted_attributes_a",
        "extracted_attributes_b",
    } and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def candidates_to_csv(candidates):
    output = io.StringIO()
    fields = [
        "part_no_a", "description_a", "contract_a", "part_no_b", "description_b", "contract_b",
        "similarity_score", "confidence_level", "business_status", "rule_decision", "rejection_reason",
        "confidence_score", "matched_evidence", "differences", "warnings",
        "scan_mode", "critical_mismatches", "generic_description_warning",
        "application_context_a", "application_context_b", "application_context_warning",
        "normalized_description_a", "normalized_description_b", "normalized_part_no_a", "normalized_part_no_b",
        "extracted_attributes_a", "extracted_attributes_b",
        "variant_attributes_a", "variant_attributes_b",
        "description_similarity", "tfidf_score", "fuzzy_score", "part_no_similarity",
        "technical_token_score", "matched_fields", "mismatched_fields", "explanation",
        "reason", "final_score", "score", "recommended_action", "review_status",
    ]
    writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
    for c in candidates:
        row = {field: serialize_csv_value(candidate_value(c, field)) for field in fields}
        row["reason"] = row["reason"] or row["explanation"]
        row["final_score"] = row["final_score"] or row["similarity_score"]
        row["score"] = row["score"] or row["similarity_score"]
        writer.writerow(row)
    return output.getvalue()
