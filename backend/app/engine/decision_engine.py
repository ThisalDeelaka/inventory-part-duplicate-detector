from app.core.constants import CONFIDENCE_ACTIONS
from app.engine.attribute_extractor import profile_record
from app.engine.column_semantics import normalize_scan_mode
from app.engine.explanations import append_warning, critical_mismatch_explanation, duplicate_explanation, generate_explanation
from app.engine.guardrails import (
    application_context_guard,
    critical_variant_guard,
    generic_description_guard,
    hard_field_guard,
    same_part_guard,
)
from app.engine.attribute_extractor import extract_attributes
from app.engine.models import CandidatePair, Decision, DecisionResult, GuardrailResult, SimilarityResult
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


def _decision_confidence(score: float) -> str:
    return confidence_for(score)


def _field_values(candidate: CandidatePair, field: str) -> tuple[str, str]:
    left = candidate.record_a.raw.get(field)
    right = candidate.record_b.raw.get(field)
    return "" if left is None else str(left), "" if right is None else str(right)


def _contracts_differ(candidate: CandidatePair) -> bool:
    left, right = _field_values(candidate, "CONTRACT")
    return bool(left and right and left.strip().lower() != right.strip().lower())


def _candidate_attributes(candidate: CandidatePair):
    attrs_a = extract_attributes(
        candidate.record_a.part_no,
        candidate.record_a.description,
        candidate.record_a.raw.get("MASTER_PART_DESCRIPTION"),
    )
    attrs_b = extract_attributes(
        candidate.record_b.part_no,
        candidate.record_b.description,
        candidate.record_b.raw.get("MASTER_PART_DESCRIPTION"),
    )
    return attrs_a, attrs_b


def _decision_result(
    candidate: CandidatePair,
    similarity: SimilarityResult,
    guardrails: GuardrailResult,
    status: str,
    rule_decision: str,
    rejection_reason: str = "",
) -> DecisionResult:
    attrs_a, attrs_b = _candidate_attributes(candidate)
    warnings = list(guardrails.messages)
    differences = list(guardrails.rule_evidence) + list(similarity.mismatched_features)
    matched = list(similarity.matched_features)
    confidence_score = round(similarity.overall_similarity, 2)
    decision = DecisionResult(
        status=status,
        confidence_score=confidence_score,
        confidence_level=_decision_confidence(confidence_score),
        explanation="",
        matched_evidence=matched,
        differences=differences,
        warnings=warnings,
        rule_decision=rule_decision,
        rejection_reason=rejection_reason,
        normalized_part_no_a=attrs_a.normalized_part_no,
        normalized_part_no_b=attrs_b.normalized_part_no,
        normalized_description_a=attrs_a.normalized_description,
        normalized_description_b=attrs_b.normalized_description,
        extracted_attributes_a={
            "product_class": attrs_a.product_class,
            "type_code": attrs_a.type_code,
            "rating": attrs_a.rating,
            "color": attrs_a.color,
            "application_context": attrs_a.application_context,
            "function_or_media": attrs_a.function_or_media,
            "generic_terms": attrs_a.generic_terms,
        },
        extracted_attributes_b={
            "product_class": attrs_b.product_class,
            "type_code": attrs_b.type_code,
            "rating": attrs_b.rating,
            "color": attrs_b.color,
            "application_context": attrs_b.application_context,
            "function_or_media": attrs_b.function_or_media,
            "generic_terms": attrs_b.generic_terms,
        },
    )
    decision.explanation = generate_explanation(candidate, similarity, guardrails, decision)
    return decision


def make_decision(
    candidate: CandidatePair,
    similarity: SimilarityResult,
    guardrails: GuardrailResult,
    cross_site: bool = False,
) -> DecisionResult:
    if guardrails.data_conflict:
        return _decision_result(
            candidate,
            similarity,
            guardrails,
            "DATA_CONFLICT_REVIEW",
            "DATA_CONFLICT",
            ",".join(guardrails.conflict_types),
        )

    hard_non_scope_conflicts = [
        conflict
        for conflict in guardrails.conflict_types
        if conflict != "contract_scope_mismatch"
    ]
    if hard_non_scope_conflicts:
        return _decision_result(
            candidate,
            similarity,
            guardrails,
            "RELATED_BUT_NOT_DUPLICATE",
            "REJECT_BY_DIFFERENTIATOR",
            ",".join(hard_non_scope_conflicts),
        )

    if _contracts_differ(candidate):
        if cross_site and similarity.overall_similarity >= 60:
            return _decision_result(
                candidate,
                similarity,
                guardrails,
                "CROSS_SITE_STANDARDIZATION_CANDIDATE",
                "CROSS_SITE_REVIEW",
                "CONTRACT_MISMATCH",
            )
        return _decision_result(
            candidate,
            similarity,
            guardrails,
            "UNIQUE_NO_MATCH",
            "SCOPE_REJECT",
            "CONTRACT_MISMATCH",
        )

    if "generic_or_sparse_description" in guardrails.warning_types:
        status = "POSSIBLE_DUPLICATE_REVIEW" if similarity.overall_similarity >= 75 else "INSUFFICIENT_DATA"
        return _decision_result(
            candidate,
            similarity,
            guardrails,
            status,
            "GENERIC_REVIEW",
            "GENERIC_OR_SPARSE_DESCRIPTION",
        )

    if similarity.overall_similarity >= 85:
        return _decision_result(candidate, similarity, guardrails, "DUPLICATE_CANDIDATE", "ALLOW")
    if similarity.overall_similarity >= 60:
        return _decision_result(candidate, similarity, guardrails, "POSSIBLE_DUPLICATE_REVIEW", "ALLOW")
    return _decision_result(candidate, similarity, guardrails, "UNIQUE_NO_MATCH", "LOW_SIMILARITY")


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

