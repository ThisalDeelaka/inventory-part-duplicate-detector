"""Deterministic, persisted-evidence-only identity explanation read models."""

from __future__ import annotations

from dataclasses import dataclass


MAX_SUPPORTING_POINTS = 3
MAX_CAUTION_POINTS = 2


@dataclass(frozen=True)
class SystemExplanation:
    headline: str
    summary: str
    supporting_points: tuple[str, ...]
    caution_points: tuple[str, ...]
    review_guidance: str
    evidence_basis: tuple[str, ...]


def _value(value):
    return getattr(value, "value", value)


def _field(value, name, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _positive_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _nonblank_group_value(members, name) -> str | None:
    values = tuple(str(_field(member, name, "") or "").strip() for member in members)
    if not values or any(not value for value in values) or len(set(values)) != 1:
        return None
    return values[0]


def _different_nonblank_values(members, name) -> bool:
    values = {
        str(_field(member, name, "") or "").strip()
        for member in members
        if str(_field(member, name, "") or "").strip()
    }
    return len(values) > 1


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)


def explain_identity_group(group) -> SystemExplanation:
    """Explain one immutable group without recomputing or reclassifying evidence."""
    status = str(_value(_field(group, "status", "")) or "")
    members = tuple(_field(group, "members", ()) or ())
    coverage = _field(group, "validation_coverage")
    summary = _field(group, "group_evidence_summary")
    genericity = _field(group, "genericity_risk_summary")
    bridge = _field(group, "bridge_risk_summary")
    missing = _field(group, "missing_evidence_summary")

    evaluated = _positive_int(_field(coverage, "evaluated_internal_pair_count"))
    possible = _positive_int(_field(coverage, "possible_internal_pair_count"))
    strong = _positive_int(_field(coverage, "strong_support_count"))
    review = _positive_int(_field(coverage, "review_support_count"))
    neutral = _positive_int(_field(coverage, "non_groupable_count"))
    missing_count = _positive_int(_field(coverage, "missing_nonrequired_pair_count"))
    if not evaluated:
        evaluated = _positive_int(_field(summary, "evaluated_pair_count"))
    if not possible:
        possible = _positive_int(_field(summary, "possible_pair_count"))
    if not strong:
        strong = _positive_int(_field(summary, "strong_support_count"))
    if not review:
        review = _positive_int(_field(summary, "review_support_count"))
    if not neutral:
        neutral = _positive_int(_field(summary, "non_groupable_count"))
    if not missing_count:
        missing_count = _positive_int(_field(summary, "missing_evidence_count"))

    supporting: list[str] = []
    cautions: list[str] = []
    basis = ["GROUP_STATUS"]

    normalized_part = _nonblank_group_value(members, "normalized_part_no")
    normalized_description = _nonblank_group_value(members, "normalized_description")
    generic_burden = bool(_field(genericity, "generic_description_burden", False))

    if normalized_part:
        _append_unique(
            supporting,
            "All records share the same persisted normalized part-number value.",
        )
        basis.append("GROUP_WIDE_NORMALIZED_PART_NUMBER")

    technical_fields = (
        ("product_category_id", "product category"),
        ("hsn_sac_code", "HSN/SAC classification"),
        ("type_code", "part type"),
    )
    for field_name, label in technical_fields:
        if _nonblank_group_value(members, field_name):
            _append_unique(
                supporting,
                f"All records share the same persisted {label}.",
            )
            basis.append(f"GROUP_WIDE_{field_name.upper()}")
            break

    if strong:
        noun = "relationship" if strong == 1 else "relationships"
        verb = "provides" if strong == 1 else "provide"
        _append_unique(
            supporting,
            f"{strong} evaluated record {noun} {verb} strong deterministic support.",
        )
        basis.append("STRONG_SUPPORT_COUNT")
    if review:
        noun = "relationship" if review == 1 else "relationships"
        verb = "provides" if review == 1 else "provide"
        _append_unique(
            supporting,
            f"{review} evaluated record {noun} {verb} review-level support.",
        )
        basis.append("REVIEW_SUPPORT_COUNT")
    if normalized_description and not generic_burden:
        _append_unique(
            supporting,
            "All records share the same persisted normalized description text.",
        )
        basis.append("GROUP_WIDE_NORMALIZED_DESCRIPTION")

    if generic_burden:
        _append_unique(
            cautions,
            "Some supporting description evidence is generic or copied, so it is not identity proof by itself.",
        )
        basis.append("GENERIC_DESCRIPTION_BURDEN")
    if bool(_field(genericity, "insufficient_independent_identity_evidence", False)):
        _append_unique(
            cautions,
            "The persisted evidence does not contain enough independent identity-specific support.",
        )
        basis.append("INSUFFICIENT_INDEPENDENT_IDENTITY_EVIDENCE")
    if missing_count or bool(_field(missing, "unresolved_ownership_ambiguity", False)):
        if missing_count == 1:
            count_text = "1 non-required relationship was not evaluated"
        elif missing_count:
            count_text = f"{missing_count} non-required relationships were not evaluated"
        else:
            count_text = "Some membership evidence remains unresolved"
        _append_unique(cautions, f"{count_text}; do not assume every pair has the same support.")
        basis.append("MISSING_OR_UNRESOLVED_EVIDENCE")
    if bool(_field(bridge, "unresolved", False)):
        _append_unique(
            cautions,
            "The persisted group evidence contains unresolved bridge or membership ambiguity.",
        )
        basis.append("UNRESOLVED_BRIDGE_RISK")
    if (
        not bool(_field(genericity, "insufficient_independent_identity_evidence", False))
        and bool(_field(genericity, "review_only_support", False))
    ):
        _append_unique(
            cautions,
            "The evaluated relationships provide review-level support only.",
        )
        basis.append("REVIEW_ONLY_SUPPORT")
    if neutral:
        noun = "relationship was" if neutral == 1 else "relationships were"
        _append_unique(
            cautions,
            f"{neutral} evaluated {noun} neutral rather than supporting.",
        )
        basis.append("NON_GROUPABLE_COUNT")
    if _different_nonblank_values(members, "normalized_part_no"):
        _append_unique(
            cautions,
            "Part-number values differ across the records and should be checked during review.",
        )
        basis.append("DIFFERING_NORMALIZED_PART_NUMBERS")

    if status == "LIKELY_DUPLICATE_GROUP":
        headline = "Stronger system-generated duplicate hypothesis"
        if evaluated and strong:
            text = (
                f"The system surfaced these {len(members)} records because {strong} of "
                f"{evaluated} evaluated relationships provide strong support."
            )
        else:
            text = (
                "The system found enough persisted evidence to surface a stronger duplicate "
                "hypothesis, but no more specific evidence summary is available."
            )
        guidance = "A human must still confirm, reject, defer, or adjust this identity set."
    else:
        headline = "Possible duplicate identity - human review required"
        supported = strong + review
        if evaluated and supported:
            text = (
                f"The system surfaced these {len(members)} records because {supported} of "
                f"{evaluated} evaluated relationships support review, while the evidence is "
                "not strong or complete enough for a stronger hypothesis."
            )
        else:
            text = (
                "The system found enough similarity to surface these records for review, but "
                "the persisted evidence does not establish a clear identity-specific reason."
            )
        guidance = "Review the member details before confirming, rejecting, deferring, or adjusting the set."

    if possible and evaluated and evaluated < possible and "MISSING_OR_UNRESOLVED_EVIDENCE" not in basis:
        _append_unique(
            cautions,
            f"Only {evaluated} of {possible} possible record relationships were evaluated.",
        )
        basis.append("PARTIAL_VALIDATION_COVERAGE")

    if not supporting:
        supporting.append(
            "The persisted result supports review of this whole set without establishing a more specific group-wide fact."
        )
        basis.append("HONEST_GROUP_FALLBACK")

    return SystemExplanation(
        headline=headline,
        summary=text,
        supporting_points=tuple(supporting[:MAX_SUPPORTING_POINTS]),
        caution_points=tuple(cautions[:MAX_CAUTION_POINTS]),
        review_guidance=guidance,
        evidence_basis=tuple(dict.fromkeys(basis)),
    )


_CONFLICT_LABELS = {
    "PROTECTED_CANNOT_LINK": "Protected contradictory evidence prevents safe grouping.",
    "HUMAN_MACHINE_AUTHORITY_CONFLICT": "Persisted human and system evidence conflict.",
    "INCOMPATIBLE_MUST_LINK_CONSTRAINTS": "Persisted human identity constraints are incompatible.",
    "OVERLAPPING_ACCEPTED_MEMBERSHIP_CONFLICT": "The proposed membership overlaps another accepted identity set.",
}


def explain_identity_conflict(conflict) -> SystemExplanation:
    conflict_type = str(_value(_field(conflict, "conflict_type", "")) or "")
    count = len(tuple(_field(conflict, "involved_record_references", ()) or ()))
    persisted_summary = str(_field(conflict, "summary", "") or "").strip()
    points = [_CONFLICT_LABELS.get(
        conflict_type,
        "Persisted contradictory evidence prevents the system from accepting one safe identity set.",
    )]
    basis = ["CONFLICT_TYPE"]
    if persisted_summary:
        points.append(f"Persisted conflict detail: {persisted_summary}")
        basis.append("PERSISTED_CONFLICT_SUMMARY")
    return SystemExplanation(
        headline="Conflict - records were not grouped automatically",
        summary=(
            f"The system kept {count or 'these'} records out of an accepted duplicate group "
            "because persisted evidence prevents safe automatic grouping."
        ),
        supporting_points=tuple(points[:MAX_SUPPORTING_POINTS]),
        caution_points=("A conflict is not a duplicate-group decision.",),
        review_guidance="Inspect the conflicting record details and protected evidence before taking any operational action.",
        evidence_basis=tuple(basis),
    )


_DEFERRED_LABELS = {
    "RESOLUTION_MEMBER_CAP_REACHED": "The candidate set exceeded the bounded resolution member limit.",
    "TARGETED_EVIDENCE_BUDGET_EXHAUSTED": "The bounded targeted-evidence budget was exhausted.",
    "UNRESOLVED_BRIDGE_AMBIGUITY": "Bridge relationships remain unresolved.",
    "UNRESOLVED_OWNERSHIP_AMBIGUITY": "Record ownership between possible groups remains unresolved.",
    "INSUFFICIENT_PARTITION_STABILITY": "The available evidence did not produce a stable safe partition.",
    "DISCOVERY_TRUNCATION_REQUIRES_LATER_ANALYSIS": "Bounded discovery was truncated and requires later analysis.",
}


def explain_deferred_identity_work(work) -> SystemExplanation:
    reason = str(_value(_field(work, "reason", "")) or "")
    count = len(tuple(_field(work, "record_references", ()) or ()))
    unfinished = str(_field(work, "unfinished_evidence_summary", "") or "").strip()
    points = [_DEFERRED_LABELS.get(
        reason,
        "The persisted result does not contain enough safe evidence to resolve this work automatically.",
    )]
    basis = ["DEFERRED_REASON"]
    if unfinished:
        points.append(f"Persisted unfinished-work detail: {unfinished}")
        basis.append("PERSISTED_UNFINISHED_EVIDENCE_SUMMARY")
    return SystemExplanation(
        headline="Resolution deferred - no duplicate conclusion",
        summary=(
            f"The system did not resolve {count or 'these'} records because the persisted "
            "evidence or bounded resources were insufficient for a safe decision."
        ),
        supporting_points=tuple(points[:MAX_SUPPORTING_POINTS]),
        caution_points=("Deferred does not mean duplicate, rejected, conflicting, or unique.",),
        review_guidance="Leave this work unresolved until additional safe evidence or an authorized later process is available.",
        evidence_basis=tuple(basis),
    )
