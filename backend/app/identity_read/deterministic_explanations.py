"""Deterministic group and pair explanation read models.

This module is presentation-only.  It joins immutable G2-v2 relationship
references to their persisted GF4/GF5 evidence and never evaluates records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.resolution.pair_explanation import (
    DeterministicPairExplanationV1,
    PairExplanationAvailability,
    project_proposal_pair_explanation,
    project_targeted_pair_explanation,
    project_legacy_pair_explanation,
)


GROUP_EXPLANATION_VERSION = "deterministic-group-explanation-v1"
PAIR_READ_MODEL_VERSION = "deterministic-pair-explanation-read-model-v1"


@dataclass(frozen=True)
class EvidenceItem:
    code: str
    category: str
    label: str
    detail: str
    source_field: str
    left_value: str | None = None
    right_value: str | None = None
    numeric_value: float | None = None
    numeric_scale: float | None = None


@dataclass(frozen=True)
class PairExplanationReadModel:
    version: str
    relationship_id: str
    left_record_reference: str
    right_record_reference: str
    left_display_identity: str
    right_display_identity: str
    deterministic_score: float | None
    signed_relationship: str
    group_role: str
    evidence_origin: str
    availability: str
    availability_message: str | None
    supporting_items: tuple[EvidenceItem, ...]
    weakening_items: tuple[EvidenceItem, ...]
    contradiction_items: tuple[EvidenceItem, ...]
    safety_items: tuple[EvidenceItem, ...]
    decision_reason_codes: tuple[str, ...]
    decision_summary: str
    evaluator_version: str
    evidence_version: str
    source_evidence_fingerprint: str
    pair_explanation_fingerprint: str


@dataclass(frozen=True)
class RelationshipMapItem:
    relationship_id: str
    left_record_reference: str
    right_record_reference: str
    left_display_identity: str
    right_display_identity: str
    deterministic_score: float | None
    signed_relationship: str
    evidence_origin: str
    explanation_availability: str
    group_role: str
    has_safety_or_review_reason: bool


@dataclass(frozen=True)
class GroupExplanation:
    version: str
    group_id: str
    member_count: int
    evidence_tier: str
    match_strength: float | None
    match_band: str | None
    possible_internal_pairs: int
    recorded_internal_relationships: int
    supporting_relationships: int
    cannot_link_relationships: int
    other_relationships: int
    relationship_coverage_complete: bool
    group_summary: str
    relationships: tuple[RelationshipMapItem, ...]
    pair_explanations: tuple[PairExplanationReadModel, ...] = ()


# Text is deliberately bounded to semantics already named by the authoritative
# classifier and its tests. Unknown codes remain visible without interpretation.
_REASON_RENDERERS = {
    "DETERMINISTIC_LIKELY_DUPLICATE": (
        "supporting", "Deterministic duplicate-support rule",
        "The persisted evaluator classified this relationship as duplicate support.",
    ),
    "LEXICAL_SUPPORT_NOT_INDEPENDENT": (
        "safety", "Lexical support is not independent",
        "The persisted classifier requires review because lexical support is not independent identity evidence.",
    ),
    "DETERMINISTIC_REVIEW_CANDIDATE": (
        "safety", "Deterministic review classification",
        "The persisted evaluator classified this relationship as requiring human review.",
    ),
    "CROSS_FIELD_IDENTITY_INCOHERENCE": (
        "safety", "Cross-field identity incoherence",
        "The persisted classifier found identity-relevant fields that do not form a coherent strong identity signal.",
    ),
}


def render_reason_code(code: str) -> EvidenceItem:
    category, label, detail = _REASON_RENDERERS.get(
        code,
        ("safety", code, f"Persisted classification reason code: {code}"),
    )
    return EvidenceItem(
        code=code, category=category, label=label, detail=detail,
        source_field="classification_reason_codes",
    )


def _value(value):
    return getattr(value, "value", value)


def _display(member) -> str:
    part = str(getattr(member, "part_no", "") or "").strip()
    description = str(getattr(member, "description", "") or "").strip()
    return " — ".join(item for item in (part, description) if item) or getattr(
        member, "stable_record_reference"
    )


def _relationship_id(left: str, right: str) -> str:
    return "::".join(sorted((left, right)))


def _item(code, category, label, detail, source_field, **values):
    return EvidenceItem(code, category, label, detail, source_field, **values)


def _render_pair(source, evidence, members_by_reference) -> PairExplanationReadModel:
    left = source.stable_record_reference_1
    right = source.stable_record_reference_2
    supporting: list[EvidenceItem] = []
    weakening: list[EvidenceItem] = []
    contradiction: list[EvidenceItem] = []
    safety: list[EvidenceItem] = []

    for code in evidence.classification_reason_codes:
        item = render_reason_code(code)
        (supporting if item.category == "supporting" else safety).append(item)

    score_labels = {
        "description_similarity": "Description similarity",
        "part_no_similarity": "Part-number similarity",
        "technical_token_score": "Technical-token score",
        "tfidf_score": "TF-IDF lexical score",
        "fuzzy_score": "Fuzzy lexical score",
    }
    for name in sorted(evidence.component_scores):
        value = evidence.component_scores[name]
        supporting.append(_item(
            name.upper(), "supporting", score_labels.get(name, name.replace("_", " ").title()),
            f"Recorded deterministic component: {float(value):.2f} / 100.",
            f"component_scores.{name}", numeric_value=float(value), numeric_scale=100.0,
        ))

    technical = evidence.technical_evidence
    normalized_pairs = (
        ("normalized_description", "Normalized description"),
        ("normalized_part_no", "Normalized part number"),
    )
    for prefix, label in normalized_pairs:
        left_value = str(technical.get(f"{prefix}_1") or "")
        right_value = str(technical.get(f"{prefix}_2") or "")
        if left_value or right_value:
            supporting.append(_item(
                prefix.upper(), "supporting", label,
                "Persisted normalized values used by the evaluator.",
                f"technical_evidence.{prefix}_1/.{prefix}_2",
                left_value=left_value or None, right_value=right_value or None,
            ))

    uom = evidence.uom_context
    if uom:
        relationship = str(uom.get("relationship") or "UNKNOWN")
        target = supporting if relationship in {"SAME", "SAME_BASIS"} else weakening
        target.append(_item(
            str(uom.get("reason_code") or "UOM_CONTEXT"),
            "supporting" if target is supporting else "weakening",
            "Inventory UOM relationship",
            f"Persisted UOM relationship: {relationship}; mapping quality: {uom.get('mapping_quality') or 'not recorded'}.",
            "uom_context",
        ))

    for index, conflict in enumerate(evidence.protected_conflicts):
        contradiction.append(_item(
            str(conflict.get("group") or f"PROTECTED_CONFLICT_{index + 1}"),
            "contradiction", "Protected field conflict",
            "The persisted evaluator recorded a protected identity-field conflict.",
            f"protected_conflicts[{index}]",
            left_value=str(conflict.get("values_a") or ""),
            right_value=str(conflict.get("values_b") or ""),
        ))

    generic = evidence.generic_evidence
    if generic.get("generic_description_warning"):
        weakening.append(_item(
            "GENERIC_DESCRIPTION_WARNING", "weakening", "Generic description warning",
            "Persisted evidence marks at least one description as generic.",
            "generic_evidence.generic_description_warning",
        ))
    if evidence.rejection_reason:
        safety.append(_item(
            evidence.rejection_reason, "safety", "Recorded rejection/control reason",
            f"Persisted evaluator reason: {evidence.rejection_reason}",
            "rejection_reason",
        ))

    availability = evidence.availability.value
    limited = (
        "Limited historical evidence available; missing fields were not reconstructed."
        if evidence.availability == PairExplanationAvailability.PARTIAL_LEGACY
        else None
    )
    edge = _value(evidence.signed_relationship)
    role = "SUPPORTS_FINAL_GROUP" if edge in {"STRONG_SUPPORT", "REVIEW_SUPPORT"} else "OTHER_RECORDED_RELATIONSHIP"
    decision = evidence.rule_decision or (
        "Historical relationship state is available; detailed decision evidence was not persisted."
        if limited else "No decision summary was persisted."
    )
    return PairExplanationReadModel(
        version=PAIR_READ_MODEL_VERSION,
        relationship_id=_relationship_id(left, right),
        left_record_reference=left,
        right_record_reference=right,
        left_display_identity=_display(members_by_reference[left]),
        right_display_identity=_display(members_by_reference[right]),
        deterministic_score=evidence.deterministic_score,
        signed_relationship=edge,
        group_role=role,
        evidence_origin=_value(getattr(source, "evidence_origin", "LEGACY_SNAPSHOT")),
        availability=availability,
        availability_message=limited,
        supporting_items=tuple(supporting),
        weakening_items=tuple(weakening),
        contradiction_items=tuple(contradiction),
        safety_items=tuple(safety),
        decision_reason_codes=evidence.classification_reason_codes,
        decision_summary=decision,
        evaluator_version=evidence.evaluator_version,
        evidence_version=evidence.contract_version,
        source_evidence_fingerprint=evidence.source_evidence_fingerprint,
        pair_explanation_fingerprint=evidence.explanation_fingerprint,
    )


def _pair_fact_phrases(detail: PairExplanationReadModel) -> tuple[str, ...]:
    """Render a few concrete persisted facts without inferring new evidence."""
    phrases = []
    for item in detail.supporting_items:
        if item.numeric_value is not None and item.numeric_scale == 100.0:
            phrases.append(f"{item.label.lower()} is {item.numeric_value:.2f}/100")
        elif item.source_field == "uom_context":
            if item.code == "UOM_SAME_BASIS":
                phrases.append("the Inventory UOMs share the same basis")
            elif "SAME" in item.detail:
                phrases.append("the Inventory UOMs match")
        if len(phrases) == 2:
            break
    return tuple(dict.fromkeys(phrases))


def _summary(group, details, supporting, cannot_link, complete) -> str:
    count = group.member_count
    possible = count * (count - 1) // 2
    if count == 2:
        detail = details[0] if details else None
        relationship = detail.signed_relationship if detail else "UNKNOWN"
        if relationship == "STRONG_SUPPORT":
            opening = (
                "These two records show strong evidence of representing the same "
                "inventory item."
            )
        elif relationship == "REVIEW_SUPPORT":
            opening = (
                "These two records have enough recorded matching evidence to warrant "
                "review, but the deterministic classification remains Review Support."
            )
        else:
            opening = (
                "These two records were retained as a candidate group because their "
                f"persisted relationship is classified as {relationship.replace('_', ' ').title()}."
            )
        facts = _pair_fact_phrases(detail) if detail else ()
        if facts:
            opening += " Recorded evidence shows that " + " and ".join(facts) + "."
        return opening
    if complete and supporting == possible:
        opening = (
            f"All {count} records have supporting pairwise evidence, so the system "
            f"retained them as one candidate group. All {possible} possible internal "
            "relationships support the group."
        )
    else:
        opening = (
            f"The system retained these {count} records as one candidate group because "
            f"{supporting} of {possible} possible internal relationships have persisted "
            "supporting evidence."
        )
    if any(detail.signed_relationship == "REVIEW_SUPPORT" for detail in details):
        opening += (
            " Human review is still required because one or more relationships remain "
            "Review Support."
        )
    if complete and cannot_link == 0:
        opening += " No internal cannot-link relationship is recorded."
    return opening


def review_consideration_for_group(explanation: GroupExplanation) -> str:
    """Explain the review boundary from persisted facts, separately from support."""
    limitations = []
    for detail in explanation.pair_explanations:
        for item in (
            detail.safety_items + detail.contradiction_items + detail.weakening_items
        ):
            if item.source_field == "uom_context" and "SAME" in item.detail:
                continue
            if item.detail not in limitations:
                limitations.append(item.detail)
    if explanation.evidence_tier == "Review Evidence":
        if limitations:
            return "Human review is required. " + " ".join(limitations[:2])
        return (
            "Human review is required because one or more persisted relationships "
            "remain classified as Review Support."
        )
    return (
        "Review the recorded evidence before confirming this suggestion; the system "
        "has not confirmed these records as duplicates."
    )


def project_group_explanation(group, strength, pair_sources: dict[str, DeterministicPairExplanationV1], *, include_details=False) -> GroupExplanation:
    members = {item.stable_record_reference: item for item in group.members}
    pair_details = []
    maps = []
    for source in sorted(group.internal_evidence, key=lambda item: (
        item.stable_record_reference_1, item.stable_record_reference_2
    )):
        evidence = pair_sources.get(source.evidence_fingerprint)
        if evidence is None:
            raise ValueError(
                f"persisted explanation source is missing for {source.evidence_fingerprint}"
            )
        detail = _render_pair(source, evidence, members)
        pair_details.append(detail)
        maps.append(RelationshipMapItem(
            relationship_id=detail.relationship_id,
            left_record_reference=detail.left_record_reference,
            right_record_reference=detail.right_record_reference,
            left_display_identity=detail.left_display_identity,
            right_display_identity=detail.right_display_identity,
            deterministic_score=detail.deterministic_score,
            signed_relationship=detail.signed_relationship,
            evidence_origin=detail.evidence_origin,
            explanation_availability=detail.availability,
            group_role=detail.group_role,
            has_safety_or_review_reason=bool(
                detail.safety_items or detail.weakening_items or detail.contradiction_items
                or detail.signed_relationship == "REVIEW_SUPPORT"
            ),
        ))
    possible = group.member_count * (group.member_count - 1) // 2
    supporting = sum(item.signed_relationship in {"STRONG_SUPPORT", "REVIEW_SUPPORT"} for item in maps)
    cannot_link = sum(item.signed_relationship == "CANNOT_LINK" for item in maps)
    complete = len(maps) == possible
    return GroupExplanation(
        version=GROUP_EXPLANATION_VERSION,
        group_id=group.versioned_group_key.group_reference,
        member_count=group.member_count,
        evidence_tier=("Stronger Evidence" if _value(group.status) == "LIKELY_DUPLICATE_GROUP" else "Review Evidence"),
        match_strength=getattr(strength, "match_strength", None),
        match_band=_value(getattr(strength, "match_band", None)),
        possible_internal_pairs=possible,
        recorded_internal_relationships=len(maps),
        supporting_relationships=supporting,
        cannot_link_relationships=cannot_link,
        other_relationships=len(maps) - supporting - cannot_link,
        relationship_coverage_complete=complete,
        group_summary=_summary(
            group, tuple(pair_details), supporting, cannot_link, complete
        ),
        relationships=tuple(maps),
        pair_explanations=tuple(pair_details) if include_details else (),
    )


def project_source_for_group(source, loaded_sources):
    item = loaded_sources.get(source.evidence_fingerprint)
    if item is None:
        return project_legacy_pair_explanation(source)
    if isinstance(item, DeterministicPairExplanationV1):
        return item
    return project_proposal_pair_explanation(
        item,
        record_reference_1=source.stable_record_reference_1,
        record_reference_2=source.stable_record_reference_2,
    )


def sources_for_group(group, loaded_sources) -> dict[str, DeterministicPairExplanationV1]:
    return {
        source.evidence_fingerprint: project_source_for_group(source, loaded_sources)
        for source in group.internal_evidence
    }
