from app.engine.application_context import find_application_context_mismatch
from app.engine.models import Decision
from app.engine.semantic_policy import field_diff, scan_mode_allows_cross_site
from app.engine.variant_extractor import find_critical_mismatches


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
