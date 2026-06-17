from app.engine.application_context import find_application_context_mismatch
from app.engine.models import CandidatePair, Decision, GuardrailResult, SimilarityResult
from app.engine.semantic_policy import field_diff, scan_mode_allows_cross_site
from app.engine.variant_extractor import find_critical_mismatches


def _value(record, field: str) -> str:
    value = record.raw.get(field)
    return "" if value is None else str(value).strip()


def _differs(candidate: CandidatePair, field: str) -> tuple[bool, str, str]:
    left = _value(candidate.record_a, field)
    right = _value(candidate.record_b, field)
    return bool(left and right and left.lower() != right.lower()), left, right


def _add_conflict(
    result: GuardrailResult,
    conflict_type: str,
    message: str,
    values_a=None,
    values_b=None,
    data_conflict: bool = False,
    recommended_next_status: str = "RELATED_BUT_NOT_DUPLICATE",
) -> None:
    result.triggered = True
    result.hard_conflict = True
    result.data_conflict = result.data_conflict or data_conflict
    result.conflict_types.append(conflict_type)
    result.messages.append(message)
    result.rule_evidence.append({
        "type": conflict_type,
        "severity": "data_conflict" if data_conflict else "hard_conflict",
        "values_a": values_a or [],
        "values_b": values_b or [],
        "message": message,
    })
    if data_conflict:
        result.recommended_next_status = "DATA_CONFLICT_REVIEW"
    elif result.recommended_next_status == "POSSIBLE_DUPLICATE_REVIEW":
        result.recommended_next_status = recommended_next_status


def _add_warning(
    result: GuardrailResult,
    warning_type: str,
    message: str,
    values_a=None,
    values_b=None,
    scope_warning: bool = False,
    recommended_next_status: str = "POSSIBLE_DUPLICATE_REVIEW",
) -> None:
    result.triggered = True
    result.review_warning = True
    result.scope_warning = result.scope_warning or scope_warning
    result.warning_types.append(warning_type)
    result.messages.append(message)
    result.rule_evidence.append({
        "type": warning_type,
        "severity": "scope_warning" if scope_warning else "review_warning",
        "values_a": values_a or [],
        "values_b": values_b or [],
        "message": message,
    })
    if result.recommended_next_status == "POSSIBLE_DUPLICATE_REVIEW":
        result.recommended_next_status = recommended_next_status


def apply_guardrails(
    candidate: CandidatePair,
    similarity: SimilarityResult,
    cross_site: bool = False,
) -> GuardrailResult:
    result = GuardrailResult()

    if similarity.rating_match is False:
        _add_conflict(
            result,
            "rating_mismatch",
            "Rating differs between the two candidate records.",
            similarity.rating_a,
            similarity.rating_b,
        )
    if similarity.color_match is False:
        _add_conflict(
            result,
            "color_mismatch",
            "Color differs between the two candidate records.",
            similarity.color_a,
            similarity.color_b,
        )
    if similarity.type_code_match is False:
        mismatch = next((item for item in similarity.mismatched_features if item.get("feature") == "type_code"), {})
        _add_conflict(
            result,
            "type_code_mismatch",
            "Type code differs between the two candidate records.",
            mismatch.get("values_a", []),
            mismatch.get("values_b", []),
        )
    if similarity.function_or_media_match is False:
        _add_conflict(
            result,
            "function_or_media_mismatch",
            "Function or media differs between the two candidate records.",
            similarity.function_or_media_a,
            similarity.function_or_media_b,
        )

    if similarity.application_context_match is False:
        mismatch = next((item for item in similarity.mismatched_features if item.get("feature") == "application_context"), {})
        _add_warning(
            result,
            "application_context_mismatch",
            "Application context differs and should be manually reviewed.",
            mismatch.get("values_a", []),
            mismatch.get("values_b", []),
        )
    if similarity.generic_description_warning:
        _add_warning(
            result,
            "generic_or_sparse_description",
            "One description is too generic or sparse to confirm duplicate identity.",
            similarity.generic_terms_a,
            similarity.generic_terms_b,
            recommended_next_status="INSUFFICIENT_DATA",
        )

    for field, conflict_type, message in (
        ("HSN_SAC_CODE", "hsn_sac_mismatch", "HSN/SAC Code differs between candidate records."),
        ("SAFETY_CODE", "safety_code_mismatch", "Safety code differs between candidate records."),
    ):
        differs, left, right = _differs(candidate, field)
        if differs:
            _add_conflict(
                result,
                conflict_type,
                message,
                [left],
                [right],
                data_conflict=True,
                recommended_next_status="DATA_CONFLICT_REVIEW",
            )

    differs, left, right = _differs(candidate, "CONTRACT")
    if differs:
        if cross_site:
            _add_warning(
                result,
                "cross_site_candidate",
                "Candidate spans different sites and should be reviewed as a cross-site standardization case.",
                [left],
                [right],
                scope_warning=True,
                recommended_next_status="CROSS_SITE_STANDARDIZATION_CANDIDATE",
            )
        else:
            _add_conflict(
                result,
                "contract_scope_mismatch",
                "Candidate spans different sites while cross-site matching is disabled.",
                [left],
                [right],
                recommended_next_status="UNIQUE_NO_MATCH",
            )
            result.scope_warning = True

    result.conflict_types = sorted(set(result.conflict_types))
    result.warning_types = sorted(set(result.warning_types))
    result.messages = list(dict.fromkeys(result.messages))
    return result


def same_part_guard(profile_a, profile_b) -> Decision | None:
    if profile_a.part_no and profile_b.part_no and profile_a.part_no.strip().lower() == profile_b.part_no.strip().lower():
        return Decision(
            status="UNIQUE_NO_MATCH",
            rule_decision="REJECT",
            rejection_reason="SAME_PART_NO",
            score_cap=0.0,
            explanation="Same PART_NO detected. This is the same part reference, not a duplicate candidate.",
        )
    return None


def hard_field_guard(profile_a, profile_b, scan_mode: str) -> Decision | None:
    for field, label, status, cap in (
        ("HSN_SAC_CODE", "HSN/SAC Code", "DATA_CONFLICT_REVIEW", 45.0),
        ("UNIT_MEAS", "Inventory UOM", "DATA_CONFLICT_REVIEW", 45.0),
        ("PRODUCT_CATEGORY_ID", "Product category", "DATA_CONFLICT_REVIEW", 50.0),
        ("HAZARD_CODE", "Safety code", "DATA_CONFLICT_REVIEW", 50.0),
    ):
        differs, value_a, value_b = field_diff(profile_a.raw, profile_b.raw, field)
        if differs:
            return Decision(
                status=status,
                rule_decision="DATA_CONFLICT" if field == "HSN_SAC_CODE" else "REJECT",
                rejection_reason=f"{field}_MISMATCH",
                score_cap=cap,
                explanation=f"{label} differs ({field} differs: {value_a} vs {value_b}), so this cannot be treated as a confirmed duplicate.",
                differences=[{"group": field, "label": label, "values_a": [value_a], "values_b": [value_b]}],
            )

    differs, value_a, value_b = field_diff(profile_a.raw, profile_b.raw, "CONTRACT")
    if differs:
        if scan_mode_allows_cross_site(scan_mode):
            return Decision(
                status="CROSS_SITE_STANDARDIZATION_CANDIDATE",
                rule_decision="CROSS_SITE",
                rejection_reason="CONTRACT_MISMATCH",
                score_cap=78.0,
                explanation="Same or similar item appears across different sites and should be reviewed for standardization.",
                differences=[{"group": "CONTRACT", "label": "Site", "values_a": [value_a], "values_b": [value_b]}],
            )
        return Decision(
            status="UNIQUE_NO_MATCH",
            rule_decision="REJECT",
            rejection_reason="CONTRACT_MISMATCH_IN_SAME_SITE_MODE",
            score_cap=55.0,
            explanation="Different site detected in same-site duplicate mode. This is not a normal same-site duplicate.",
            differences=[{"group": "CONTRACT", "label": "Site", "values_a": [value_a], "values_b": [value_b]}],
        )
    return None


def critical_variant_guard(profile_a, profile_b) -> Decision | None:
    mismatches = find_critical_mismatches(profile_a.attributes["variants"], profile_b.attributes["variants"])
    if not mismatches:
        return None
    mismatch = mismatches[0]
    return Decision(
        status="RELATED_BUT_NOT_DUPLICATE",
        rule_decision="DOWNGRADE",
        rejection_reason=f"{mismatch['group']}_MISMATCH",
        score_cap=55.0,
        differences=mismatches,
    )


def generic_description_guard(profile_a, profile_b) -> Decision | None:
    if profile_a.is_generic_description != profile_b.is_generic_description:
        return Decision(
            status="INSUFFICIENT_DATA",
            rule_decision="DOWNGRADE",
            rejection_reason="GENERIC_DESCRIPTION",
            score_cap=65.0,
            warnings=["One description is too generic to confirm duplicate identity."],
        )
    return None


def application_context_guard(profile_a, profile_b) -> Decision | None:
    mismatch = find_application_context_mismatch(profile_a.raw, profile_b.raw)
    if not mismatch:
        return None
    left = ", ".join(mismatch["values_a"])
    right = ", ".join(mismatch["values_b"])
    return Decision(
        status="POSSIBLE_DUPLICATE_REVIEW",
        rule_decision="DOWNGRADE",
        rejection_reason="APPLICATION_CONTEXT_MISMATCH",
        score_cap=78.0,
        warnings=[f"Application context appears different: {left} vs {right}."],
        differences=[{"group": "APPLICATION_CONTEXT", "label": "Application context", **mismatch}],
    )
