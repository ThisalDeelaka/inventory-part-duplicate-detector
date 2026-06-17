from app.core.constants import CONFIDENCE_ACTIONS
from app.engine.attribute_extractor import profile_record
from app.engine.column_semantics import normalize_scan_mode
from app.engine.explanations import append_warning, critical_mismatch_explanation, duplicate_explanation
from app.engine.guardrails import (
    application_context_guard,
    critical_variant_guard,
    generic_description_guard,
    hard_field_guard,
    same_part_guard,
)
from app.engine.models import Decision
from app.engine.semantic_policy import compare_selected_fields
from app.engine.similarity import calculate_similarity


def confidence_for(score):
    if score >= 90:
        return "HIGH"
    if score >= 75:
        return "MEDIUM"
    if score >= 60:
        return "LOW"
    return "IGNORE"


def business_status_for(score):
    if score >= 85:
        return "DUPLICATE_CANDIDATE"
    if score >= 60:
        return "POSSIBLE_DUPLICATE_REVIEW"
    return "UNIQUE_NO_MATCH"


def _empty_scores():
    return {
        "description_similarity": 0.0,
        "tfidf_score": 0.0,
        "fuzzy_score": 0.0,
        "part_no_similarity": 0.0,
        "technical_token_score": 0.0,
    }


def _visibility_payload(profile_a, profile_b, generic_warning=False, context_warning=False):
    return {
        "generic_description_warning": generic_warning,
        "application_context_a": profile_a.application_context,
        "application_context_b": profile_b.application_context,
        "application_context_warning": context_warning,
        "normalized_description_a": profile_a.normalized_description,
        "normalized_description_b": profile_b.normalized_description,
        "normalized_part_no_a": profile_a.normalized_part_no,
        "normalized_part_no_b": profile_b.normalized_part_no,
    }


def _result(
    profile_a,
    profile_b,
    selected_fields,
    scan_mode,
    scores=None,
    status="UNIQUE_NO_MATCH",
    rule_decision="ALLOW",
    rejection_reason="",
    explanation="",
    differences=None,
    warnings=None,
    generic_warning=False,
    context_warning=False,
):
    matched, mismatched, _business = compare_selected_fields(profile_a.raw, profile_b.raw, selected_fields)
    score_payload = _empty_scores()
    final_score = 0.0
    if scores:
        final_score = scores.final_score
        score_payload = {
            "description_similarity": scores.description_similarity,
            "tfidf_score": scores.tfidf_score,
            "fuzzy_score": scores.fuzzy_score,
            "part_no_similarity": scores.part_no_similarity,
            "technical_token_score": scores.technical_token_score,
        }
    confidence = confidence_for(final_score)
    return {
        "final_score": final_score,
        "confidence_level": confidence,
        **score_payload,
        "matched_fields": matched,
        "mismatched_fields": mismatched,
        "explanation": explanation,
        "recommended_action": CONFIDENCE_ACTIONS[confidence],
        "business_status": status,
        "rule_decision": rule_decision,
        "rejection_reason": rejection_reason,
        "scan_mode": scan_mode,
        "critical_mismatches": differences or [],
        "variant_attributes_a": profile_a.attributes["variants"],
        "variant_attributes_b": profile_b.attributes["variants"],
        **_visibility_payload(profile_a, profile_b, generic_warning, context_warning),
    }


def _guard_result(profile_a, profile_b, selected_fields, scan_mode, guard: Decision):
    score = guard.score_cap or 0.0
    scores = type("_Scores", (), {
        "final_score": score,
        "description_similarity": 0.0,
        "tfidf_score": 0.0,
        "fuzzy_score": 0.0,
        "part_no_similarity": 0.0,
        "technical_token_score": 0.0,
    })()
    explanation = guard.explanation
    if not explanation and guard.differences:
        explanation = critical_mismatch_explanation(profile_a, profile_b, guard.differences[0])
    for warning in guard.warnings:
        explanation = append_warning(explanation, warning)
    return _result(
        profile_a,
        profile_b,
        selected_fields,
        scan_mode,
        scores=scores,
        status=guard.status,
        rule_decision=guard.rule_decision,
        rejection_reason=guard.rejection_reason,
        explanation=explanation,
        differences=guard.differences,
        generic_warning=any("too generic" in warning for warning in guard.warnings),
        context_warning=any("Application context" in warning for warning in guard.warnings),
    )


def evaluate_candidate(record_a, record_b, selected_fields, scan_mode="SAME_SITE_DUPLICATE"):
    scan_mode = normalize_scan_mode(scan_mode)
    profile_a = profile_record(record_a)
    profile_b = profile_record(record_b)

    # 1-4. Semantics and deterministic hard stops before similarity.
    for guard in (
        same_part_guard(profile_a, profile_b),
        hard_field_guard(profile_a, profile_b, scan_mode),
        critical_variant_guard(profile_a, profile_b),
    ):
        if guard:
            return _guard_result(profile_a, profile_b, selected_fields, scan_mode, guard)

    # 5-6. Local similarity scoring after business-safe normalization.
    matched, mismatched, business_score = compare_selected_fields(record_a, record_b, selected_fields)
    scores = calculate_similarity(profile_a, profile_b, business_score)
    explanation = duplicate_explanation(profile_a, profile_b, matched, scores.description_similarity, scores.part_no_similarity)
    status = business_status_for(scores.final_score)
    rule_decision = "ALLOW"
    rejection_reason = ""
    differences = []
    generic_warning = False
    context_warning = False

    # 7. Soft deterministic guardrails after scoring.
    for guard in (
        generic_description_guard(profile_a, profile_b),
        application_context_guard(profile_a, profile_b),
    ):
        if not guard:
            continue
        if guard.score_cap is not None:
            scores.final_score = round(min(scores.final_score, guard.score_cap), 2)
        status = guard.status
        rule_decision = guard.rule_decision
        rejection_reason = guard.rejection_reason
        differences.extend(guard.differences)
        for warning in guard.warnings:
            explanation = append_warning(explanation, warning)
        generic_warning = generic_warning or any("too generic" in warning for warning in guard.warnings)
        context_warning = context_warning or any("Application context" in warning for warning in guard.warnings)

    return _result(
        profile_a,
        profile_b,
        selected_fields,
        scan_mode,
        scores=scores,
        status=status,
        rule_decision=rule_decision,
        rejection_reason=rejection_reason,
        explanation=explanation,
        differences=differences,
        generic_warning=generic_warning,
        context_warning=context_warning,
    )
