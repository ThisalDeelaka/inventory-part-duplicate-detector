from app.core.constants import CONFIDENCE_ACTIONS, STRICT_MISMATCH_FIELDS
from app.engine.explanation import build_explanation
from app.engine.normalizer import extract_technical_tokens
from app.engine.similarity_model import (
    calculate_fuzzy_similarity,
    calculate_part_no_similarity,
    calculate_technical_token_score,
    calculate_tfidf_similarity,
)


def _clean(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    return "" if text in {"", "nan", "none"} else text


def confidence_for(score):
    if score >= 90: return "HIGH"
    if score >= 75: return "MEDIUM"
    if score >= 60: return "LOW"
    return "IGNORE"


def _same_part_number(record_a, record_b):
    part_a, part_b = _clean(record_a.get("PART_NO")), _clean(record_b.get("PART_NO"))
    return bool(part_a and part_b and part_a == part_b)


def _strict_mismatches(record_a, record_b):
    mismatches = []
    for field in STRICT_MISMATCH_FIELDS:
        value_a, value_b = _clean(record_a.get(field)), _clean(record_b.get(field))
        if value_a and value_b and value_a != value_b:
            mismatches.append(field)
    return sorted(mismatches)


def score_candidate(record_a, record_b, selected_fields):
    if _same_part_number(record_a, record_b):
        return {
            "final_score": 0.0, "confidence_level": "IGNORE",
            "description_similarity": 0.0, "tfidf_score": 0.0,
            "fuzzy_score": 0.0, "part_no_similarity": 100.0,
            "technical_token_score": 0.0, "matched_fields": [],
            "mismatched_fields": [], "explanation": "Same PART_NO detected, so this is treated as the same part across records/sites rather than a duplicate master candidate.",
            "recommended_action": CONFIDENCE_ACTIONS["IGNORE"],
        }

    desc_a, desc_b = record_a.get("DESCRIPTION"), record_b.get("DESCRIPTION")
    tfidf = calculate_tfidf_similarity(desc_a, desc_b)
    fuzzy = calculate_fuzzy_similarity(desc_a, desc_b)
    description = round(tfidf * 0.6 + fuzzy * 0.4, 2)
    part_no = calculate_part_no_similarity(record_a.get("PART_NO"), record_b.get("PART_NO"))
    tokens_a = extract_technical_tokens(desc_a)
    tokens_b = extract_technical_tokens(desc_b)
    token_score = calculate_technical_token_score(tokens_a, tokens_b)
    matched, mismatched, comparable = [], [], 0
    for field in selected_fields:
        av, bv = record_a.get(field), record_b.get(field)
        if av is None or bv is None or str(av).strip() in {"", "nan"} or str(bv).strip() in {"", "nan"}:
            continue
        comparable += 1
        (matched if str(av).strip().lower() == str(bv).strip().lower() else mismatched).append(field)
    business = (len(matched) / comparable * 100) if comparable else 50.0
    final = description * 0.6 + business * 0.2 + part_no * 0.1 + token_score * 0.1

    modifiers_a = set(tokens_a["modifiers"])
    modifiers_b = set(tokens_b["modifiers"])
    if modifiers_a and modifiers_b and modifiers_a != modifiers_b:
        final -= 20
    numbers_a = set(tokens_a["numbers"])
    numbers_b = set(tokens_b["numbers"])
    if numbers_a and numbers_b and numbers_a != numbers_b:
        final -= 15
    uom_a, uom_b = _clean(record_a.get("UNIT_MEAS")), _clean(record_b.get("UNIT_MEAS"))
    if uom_a and uom_b and uom_a != uom_b:
        final -= 30
    strict_mismatches = _strict_mismatches(record_a, record_b)
    if strict_mismatches:
        final = min(final - 35, 55.0)
    final = round(max(0.0, min(100.0, final)), 2)
    confidence = confidence_for(final)
    return {
        "final_score": final, "confidence_level": confidence,
        "description_similarity": description, "tfidf_score": tfidf,
        "fuzzy_score": fuzzy, "part_no_similarity": part_no,
        "technical_token_score": token_score, "matched_fields": matched,
        "mismatched_fields": mismatched,
        "explanation": build_explanation(record_a, record_b, matched, mismatched, description),
        "recommended_action": CONFIDENCE_ACTIONS[confidence],
    }
