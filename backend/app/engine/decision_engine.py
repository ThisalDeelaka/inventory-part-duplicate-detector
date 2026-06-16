from app.core.constants import CONFIDENCE_ACTIONS
from app.engine.business_rules import evaluate_hard_business_rules
from app.engine.column_semantics import clean_field_value, normalize_scan_mode
from app.engine.explanation import build_explanation
from app.engine.item_family_classifier import shared_family
from app.engine.normalizer import extract_technical_tokens
from app.engine.similarity_model import (
    calculate_fuzzy_similarity,
    calculate_part_no_similarity,
    calculate_technical_token_score,
    calculate_tfidf_similarity,
)
from app.engine.variant_extractor import extract_variant_attributes, find_critical_mismatches


def confidence_for(score):
    if score >= 90:
        return "HIGH"
    if score >= 75:
        return "MEDIUM"
    if score >= 60:
        return "LOW"
    return "IGNORE"


def business_status_for(score):
    if score >= 90:
        return "LIKELY_DUPLICATE"
    if score >= 60:
        return "POSSIBLE_DUPLICATE_REVIEW"
    return "INSUFFICIENT_DATA"


def _empty_scores():
    return {
        "description_similarity": 0.0,
        "tfidf_score": 0.0,
        "fuzzy_score": 0.0,
        "part_no_similarity": 0.0,
        "technical_token_score": 0.0,
    }


def _field_matches(record_a, record_b, selected_fields):
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
    business = (len(matched) / comparable * 100) if comparable else 50.0
    return matched, mismatched, business


def _critical_mismatch_explanation(record_a, record_b, mismatch):
    family = shared_family(record_a.get("DESCRIPTION"), record_b.get("DESCRIPTION"))
    left = ", ".join(mismatch["values_a"])
    right = ", ".join(mismatch["values_b"])
    return f"Both are {family}, but {mismatch['label']} differs: {left} vs {right}."


def _base_payload(record_a, record_b, selected_fields, scan_mode):
    matched, mismatched, _business = _field_matches(record_a, record_b, selected_fields)
    attributes_a = extract_variant_attributes(record_a.get("DESCRIPTION"))
    attributes_b = extract_variant_attributes(record_b.get("DESCRIPTION"))
    return matched, mismatched, attributes_a, attributes_b


def _blocked_result(record_a, record_b, selected_fields, scan_mode, rule):
    matched, mismatched, attributes_a, attributes_b = _base_payload(record_a, record_b, selected_fields, scan_mode)
    score = rule["score_cap"]
    return {
        "final_score": score,
        "confidence_level": confidence_for(score),
        **_empty_scores(),
        "matched_fields": matched,
        "mismatched_fields": mismatched,
        "explanation": rule["explanation"],
        "recommended_action": CONFIDENCE_ACTIONS[confidence_for(score)],
        "business_status": rule["business_status"],
        "rule_decision": rule["rule_decision"],
        "rejection_reason": rule["rejection_reason"],
        "scan_mode": normalize_scan_mode(scan_mode),
        "critical_mismatches": rule["critical_mismatches"],
        "variant_attributes_a": attributes_a,
        "variant_attributes_b": attributes_b,
    }


def evaluate_candidate(record_a, record_b, selected_fields, scan_mode="SAME_SITE_DUPLICATE"):
    scan_mode = normalize_scan_mode(scan_mode)
    rule = evaluate_hard_business_rules(record_a, record_b, scan_mode)
    if rule["blocked"]:
        return _blocked_result(record_a, record_b, selected_fields, scan_mode, rule)

    matched, mismatched, attributes_a, attributes_b = _base_payload(record_a, record_b, selected_fields, scan_mode)
    critical_mismatches = find_critical_mismatches(attributes_a, attributes_b)
    if critical_mismatches:
        mismatch = critical_mismatches[0]
        score = 55.0
        return {
            "final_score": score,
            "confidence_level": confidence_for(score),
            **_empty_scores(),
            "matched_fields": matched,
            "mismatched_fields": mismatched,
            "explanation": _critical_mismatch_explanation(record_a, record_b, mismatch),
            "recommended_action": CONFIDENCE_ACTIONS[confidence_for(score)],
            "business_status": "RELATED_BUT_NOT_DUPLICATE",
            "rule_decision": "DOWNGRADE",
            "rejection_reason": f"{mismatch['group']}_MISMATCH",
            "scan_mode": scan_mode,
            "critical_mismatches": critical_mismatches,
            "variant_attributes_a": attributes_a,
            "variant_attributes_b": attributes_b,
        }

    desc_a, desc_b = record_a.get("DESCRIPTION"), record_b.get("DESCRIPTION")
    tfidf = calculate_tfidf_similarity(desc_a, desc_b)
    fuzzy = calculate_fuzzy_similarity(desc_a, desc_b)
    description = round(tfidf * 0.6 + fuzzy * 0.4, 2)
    part_no = calculate_part_no_similarity(record_a.get("PART_NO"), record_b.get("PART_NO"))
    tokens_a = extract_technical_tokens(desc_a)
    tokens_b = extract_technical_tokens(desc_b)
    token_score = calculate_technical_token_score(tokens_a, tokens_b)
    _matched, _mismatched, business = _field_matches(record_a, record_b, selected_fields)

    final = description * 0.6 + business * 0.2 + part_no * 0.1 + token_score * 0.1
    final = round(max(0.0, min(100.0, final)), 2)
    confidence = confidence_for(final)
    return {
        "final_score": final,
        "confidence_level": confidence,
        "description_similarity": description,
        "tfidf_score": tfidf,
        "fuzzy_score": fuzzy,
        "part_no_similarity": part_no,
        "technical_token_score": token_score,
        "matched_fields": matched,
        "mismatched_fields": mismatched,
        "explanation": build_explanation(record_a, record_b, matched, mismatched, description),
        "recommended_action": CONFIDENCE_ACTIONS[confidence],
        "business_status": business_status_for(final),
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "scan_mode": scan_mode,
        "critical_mismatches": [],
        "variant_attributes_a": attributes_a,
        "variant_attributes_b": attributes_b,
    }
