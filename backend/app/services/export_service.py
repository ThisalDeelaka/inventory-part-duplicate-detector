import csv
import io


def sanitize_csv_cell(value):
    if value is None:
        return ""
    text = str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def candidates_to_csv(candidates):
    output = io.StringIO()
    fields = ["part_no_a", "description_a", "contract_a", "part_no_b", "description_b", "contract_b", "similarity_score", "confidence_level", "description_similarity", "tfidf_score", "fuzzy_score", "part_no_similarity", "technical_token_score", "matched_fields", "mismatched_fields", "explanation", "recommended_action", "review_status"]
    writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
    for c in candidates:
        row = {field: sanitize_csv_cell(getattr(c, field)) for field in fields}
        writer.writerow(row)
    return output.getvalue()
