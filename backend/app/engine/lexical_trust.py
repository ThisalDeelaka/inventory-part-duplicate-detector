"""Deterministic trust assessment for description-dominant identity support."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.engine.identity_signature import SignedEvidenceChannel
from app.engine.identity_signature_derivation import derive_identity_signature
from app.engine.signed_identity_evidence import (
    ShadowEvidenceBucket,
    classify_shadow_evidence,
    derive_signed_identity_evidence,
)


LEXICAL_TRUST_ASSESSMENT_VERSION = "lexical-trust-assessment-v1"
PART_NUMBER_COHERENCE_FLOOR = 80.0


def _value(record, name: str):
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _normalized_text(value) -> str:
    return str(value or "").strip().casefold()


@dataclass(frozen=True)
class LexicalTrustAssessment:
    """Auditable, provider-free reasons for retaining or reducing Strong support."""

    version: str
    support_provenance: str
    description_dominance: bool
    independent_identity_support_present: bool
    part_number_coherence: float
    part_family_coherence: bool
    cross_field_identity_anchor_present: bool
    bounded_model_alias_present: bool
    unresolved_discriminator_count: int
    cross_field_incoherence: bool
    technical_attribute_coherence: bool
    generic_or_copy_risk: bool
    risk_reasons: tuple[str, ...]

    @property
    def requires_strong_downgrade(self) -> bool:
        return bool(self.risk_reasons)

    def payload(self) -> dict[str, object]:
        return {
            **asdict(self),
            "risk_reasons": list(self.risk_reasons),
            "requires_strong_downgrade": self.requires_strong_downgrade,
        }


def assess_lexical_trust(
    record_a,
    record_b,
    score_result,
    *,
    record_reference_a: str,
    record_reference_b: str,
) -> LexicalTrustAssessment:
    """Assess whether lexical evidence has enough independent support for Strong.

    The 80-point part-number floor is deliberately below the scorer's existing
    90-point *strong* part-number rescue.  It is a cautious coherence floor, not
    a duplicate threshold: falling below it can only demote Strong to Review.
    """
    signature_a = derive_identity_signature(
        record_a, record_reference=record_reference_a
    )
    signature_b = derive_identity_signature(
        record_b, record_reference=record_reference_b
    )
    signed = derive_signed_identity_evidence(signature_a, signature_b)
    channels = {fact.channel for fact in signed.facts}
    provenance = classify_shadow_evidence(signed)
    identity_support = SignedEvidenceChannel.IDENTITY_SUPPORT in channels
    lexical_support = SignedEvidenceChannel.LEXICAL_SUPPORT in channels
    contradiction = SignedEvidenceChannel.IDENTITY_CONTRADICTION in channels
    part_number_coherence = float(score_result.get("part_no_similarity") or 0.0)

    def anchor_tokens(value) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z]+", _normalized_text(value))
            if len(token) >= 4
        }

    cross_field_identity_anchor = bool(
        anchor_tokens(_value(record_a, "PART_NO"))
        & anchor_tokens(_value(record_b, "PART_NO"))
        & anchor_tokens(_value(record_a, "DESCRIPTION"))
        & anchor_tokens(_value(record_b, "DESCRIPTION"))
    )
    part_family_coherence = (
        part_number_coherence >= PART_NUMBER_COHERENCE_FLOOR
        or cross_field_identity_anchor
    )
    description_a = _normalized_text(_value(record_a, "DESCRIPTION"))
    description_b = _normalized_text(_value(record_b, "DESCRIPTION"))
    compact_a = re.sub(r"[^a-z0-9]", "", description_a)
    compact_b = re.sub(r"[^a-z0-9]", "", description_b)
    single_model_code = re.compile(r"(?=.*[a-z])(?=.*\d)[a-z0-9]{4,8}")
    bounded_model_alias = bool(
        compact_a == compact_b
        and compact_a
        and (
            single_model_code.fullmatch(description_a)
            or single_model_code.fullmatch(description_b)
        )
    )
    description_dominance = bool(
        lexical_support
        and float(score_result.get("description_similarity") or 0.0) >= 90.0
    )
    type_a = _normalized_text(_value(record_a, "TYPE_CODE"))
    type_b = _normalized_text(_value(record_b, "TYPE_CODE"))
    cross_field_incoherence = bool(type_a and type_b and type_a != type_b)
    unresolved_count = sum(
        fact.reason_code == "SHADOW_UNRESOLVED_LEXICAL_OVERLAP_ONLY"
        for fact in signed.facts
    )
    generic_or_copy_risk = bool(
        score_result.get("generic_description_warning")
        or any(
            fact.reason_code == "SHADOW_COPIED_GENERIC_LEXICAL_OVERLAP_ONLY"
            for fact in signed.facts
        )
    )

    reasons = []
    lexical_only = (
        provenance == ShadowEvidenceBucket.SHADOW_LEXICAL_ONLY_OR_UNRESOLVED
    )
    if (
        description_dominance
        and lexical_only
        and not part_family_coherence
        and not bounded_model_alias
    ):
        reasons.append("LEXICAL_SUPPORT_NOT_INDEPENDENT")
    if description_dominance and lexical_only and cross_field_incoherence:
        reasons.append("CROSS_FIELD_IDENTITY_INCOHERENCE")

    return LexicalTrustAssessment(
        version=LEXICAL_TRUST_ASSESSMENT_VERSION,
        support_provenance=provenance.value,
        description_dominance=description_dominance,
        independent_identity_support_present=(
            identity_support or part_family_coherence
        ),
        part_number_coherence=part_number_coherence,
        part_family_coherence=part_family_coherence,
        cross_field_identity_anchor_present=cross_field_identity_anchor,
        bounded_model_alias_present=bounded_model_alias,
        unresolved_discriminator_count=unresolved_count,
        cross_field_incoherence=cross_field_incoherence,
        technical_attribute_coherence=not contradiction,
        generic_or_copy_risk=generic_or_copy_risk,
        risk_reasons=tuple(sorted(reasons)),
    )
