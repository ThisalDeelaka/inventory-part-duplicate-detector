"""Pure R16 shadow-only comparison of two identity signatures."""

from __future__ import annotations

from collections import defaultdict
from enum import Enum

from app.engine.identity_discriminator import object_classes_are_incompatible
from app.engine.identity_signature import (
    SIGNED_IDENTITY_EVIDENCE_CONTRACT_VERSION,
    IdentitySemanticCategory,
    IdentitySignature,
    IdentitySourceField,
    SignedEvidenceChannel,
    SignedEvidenceFact,
    SignedIdentityEvidence,
    with_signed_identity_evidence_fingerprint,
)


SIGNED_IDENTITY_EVIDENCE_COMPARISON_VERSION = "signed-identity-comparison-v2"


class ShadowEvidenceBucket(str, Enum):
    SHADOW_TRUSTED_IDENTITY_PRESENT = "SHADOW_TRUSTED_IDENTITY_PRESENT"
    SHADOW_LEXICAL_ONLY_OR_UNRESOLVED = "SHADOW_LEXICAL_ONLY_OR_UNRESOLVED"
    SHADOW_EXPLICIT_CONTRADICTION = "SHADOW_EXPLICIT_CONTRADICTION"
    SHADOW_MIXED_EVIDENCE = "SHADOW_MIXED_EVIDENCE"
    SHADOW_INSUFFICIENT = "SHADOW_INSUFFICIENT"


_IDENTITY_ELIGIBLE_KEYS = frozenset({
    "bounded_object_or_construct",
    "end_position", "serialization_role", "flow_role",
    "engine_component_role", "structural_role",
    "explicit_type_or_grade",
})
_UNTRUSTED_PROVENANCE_MARKERS = ("GENERIC", "DESCRIPTION_MASTER_MATCH")


def _facts(signature: IdentitySignature):
    return (
        signature.object_construct_observations
        + signature.assembly_component_role_observations
        + signature.model_type_observations
        + signature.variant_observations
        + signature.critical_attribute_observations
    )


def _index(signature: IdentitySignature):
    result = defaultdict(list)
    for item in _facts(signature):
        result[(item.semantic_category, item.semantic_key, item.normalized_value)].append(item)
    return result


def _trusted(item) -> bool:
    return any(
        not any(marker in source.provenance_code for marker in _UNTRUSTED_PROVENANCE_MARKERS)
        and source.source_field in {
            IdentitySourceField.PART_NUMBER,
            IdentitySourceField.DESCRIPTION,
            IdentitySourceField.MASTER_DESCRIPTION,
            IdentitySourceField.TYPE_DESIGNATION,
            IdentitySourceField.DIMENSION_QUALITY,
        }
        for source in item.sources
    )


def _fact(channel, left, right, *, observed_fact: str, reason_code: str):
    matches = tuple(sorted({left.normalized_value, right.normalized_value}))
    return SignedEvidenceFact(
        channel=channel,
        semantic_category=left.semantic_category,
        semantic_key=left.semantic_key,
        observed_fact=observed_fact,
        source_observations_1=left.sources,
        source_observations_2=right.sources,
        normalized_matches=matches,
        reason_code=reason_code,
    )


def _copied_tokens(signature: IdentitySignature):
    values = defaultdict(list)
    for item in signature.unresolved_observations:
        if item.semantic_key != "description_reliability":
            continue
        for source in item.sources:
            if "DESCRIPTION_MASTER_MATCH" in source.provenance_code or (
                "GENERIC" in source.provenance_code
            ):
                for token in source.normalized_evidence:
                    values[token].append(source)
    return values


def _unresolved_index(signature: IdentitySignature):
    values = defaultdict(list)
    for item in signature.unresolved_observations:
        if item.semantic_key in {
            "unresolved_identity_token", "unresolved_model_or_type"
        }:
            values[(item.semantic_category, item.semantic_key, item.normalized_value)].append(item)
    return values


def derive_signed_identity_evidence(
    signature_a: IdentitySignature,
    signature_b: IdentitySignature,
) -> SignedIdentityEvidence:
    """Compare exactly two signatures; emit facts but no product decision."""
    if signature_a.record_reference == signature_b.record_reference:
        raise ValueError("signed evidence requires two distinct record references")
    left, right = sorted(
        (signature_a, signature_b), key=lambda item: item.record_reference
    )
    left_index = _index(left)
    right_index = _index(right)
    facts = []

    for key in sorted(set(left_index) & set(right_index), key=str):
        for left_item in left_index[key]:
            for right_item in right_index[key]:
                category, semantic_key, _value = key
                if (
                    semantic_key in _IDENTITY_ELIGIBLE_KEYS
                    and _trusted(left_item)
                    and _trusted(right_item)
                ):
                    facts.append(_fact(
                        SignedEvidenceChannel.IDENTITY_SUPPORT,
                        left_item, right_item,
                        observed_fact="recognized identity semantic value agrees",
                        reason_code="SHADOW_TRUSTED_RECOGNIZED_IDENTITY_AGREEMENT",
                    ))
                elif category in {
                    IdentitySemanticCategory.VARIANT_IDENTITY,
                    IdentitySemanticCategory.CRITICAL_IDENTITY_ATTRIBUTE,
                } and semantic_key != "directional_component_base":
                    facts.append(_fact(
                        SignedEvidenceChannel.ATTRIBUTE_SUPPORT,
                        left_item, right_item,
                        observed_fact="bounded typed attribute value agrees",
                        reason_code="SHADOW_TYPED_ATTRIBUTE_AGREEMENT",
                    ))
                else:
                    facts.append(_fact(
                        SignedEvidenceChannel.LEXICAL_SUPPORT,
                        left_item, right_item,
                        observed_fact="recognized but non-trusted semantic text overlaps",
                        reason_code="SHADOW_NON_TRUSTED_RECOGNIZED_OVERLAP",
                    ))

    left_functional = defaultdict(list)
    right_functional = defaultdict(list)
    for target, signature in ((left_functional, left), (right_functional, right)):
        for item in signature.assembly_component_role_observations:
            if item.semantic_key.startswith("functional_location::"):
                target[item.semantic_key].append(item)
    for semantic_key in sorted(set(left_functional) & set(right_functional)):
        for left_item in left_functional[semantic_key]:
            for right_item in right_functional[semantic_key]:
                if (
                    left_item.normalized_value != right_item.normalized_value
                    and {left_item.normalized_value, right_item.normalized_value}
                    == {"head", "tail"}
                    and _trusted(left_item)
                    and _trusted(right_item)
                ):
                    facts.append(_fact(
                        SignedEvidenceChannel.IDENTITY_CONTRADICTION,
                        left_item,
                        right_item,
                        observed_fact=(
                            "trusted mutually exclusive functional/location roles "
                            "differ on a shared construct"
                        ),
                        reason_code=(
                            "SHADOW_FUNCTIONAL_LOCATION_IDENTITY_INCOMPATIBILITY"
                        ),
                    ))

    left_objects = [
        item for item in left.object_construct_observations
        if item.semantic_key == "bounded_object_or_construct"
    ]
    right_objects = [
        item for item in right.object_construct_observations
        if item.semantic_key == "bounded_object_or_construct"
    ]
    for left_item in left_objects:
        for right_item in right_objects:
            if object_classes_are_incompatible(
                left_item.normalized_value, right_item.normalized_value
            ):
                facts.append(_fact(
                    SignedEvidenceChannel.IDENTITY_CONTRADICTION,
                    left_item, right_item,
                    observed_fact="recognized bounded object or construct classes are incompatible",
                    reason_code="SHADOW_EXISTING_BOUNDED_OBJECT_INCOMPATIBILITY",
                ))

    left_sides = [item for item in left.variant_observations if item.semantic_key == "directional_side"]
    right_sides = [item for item in right.variant_observations if item.semantic_key == "directional_side"]
    left_bases = {item.normalized_value for item in left.variant_observations
                  if item.semantic_key == "directional_component_base"}
    right_bases = {item.normalized_value for item in right.variant_observations
                   if item.semantic_key == "directional_component_base"}
    if left_bases & right_bases:
        for left_item in left_sides:
            for right_item in right_sides:
                if {left_item.normalized_value, right_item.normalized_value} == {"left", "right"}:
                    facts.append(_fact(
                        SignedEvidenceChannel.IDENTITY_CONTRADICTION,
                        left_item, right_item,
                        observed_fact="recognized opposite directional sides share a bounded component base",
                        reason_code="SHADOW_EXISTING_DIRECTIONAL_SIDE_INCOMPATIBILITY",
                    ))

    left_tyre = [item for item in left.variant_observations if item.semantic_key == "tyre_variant"]
    right_tyre = [item for item in right.variant_observations if item.semantic_key == "tyre_variant"]
    if {item.normalized_value for item in left_objects} & {"tyre"} and (
        {item.normalized_value for item in right_objects} & {"tyre"}
    ) and len(left_tyre) == len(right_tyre) == 1 and (
        left_tyre[0].normalized_value != right_tyre[0].normalized_value
    ):
        facts.append(_fact(
            SignedEvidenceChannel.IDENTITY_CONTRADICTION,
            left_tyre[0], right_tyre[0],
            observed_fact="recognized mutually exclusive tyre variants differ",
            reason_code="SHADOW_EXISTING_TYRE_VARIANT_INCOMPATIBILITY",
        ))

    left_unresolved = _unresolved_index(left)
    right_unresolved = _unresolved_index(right)
    for key in sorted(set(left_unresolved) & set(right_unresolved), key=str):
        facts.append(_fact(
            SignedEvidenceChannel.LEXICAL_SUPPORT,
            left_unresolved[key][0], right_unresolved[key][0],
            observed_fact="bounded unresolved text overlaps without semantic promotion",
            reason_code="SHADOW_UNRESOLVED_LEXICAL_OVERLAP_ONLY",
        ))

    left_copied = _copied_tokens(left)
    right_copied = _copied_tokens(right)
    for token in sorted(set(left_copied) & set(right_copied))[:4]:
        facts.append(SignedEvidenceFact(
            SignedEvidenceChannel.LEXICAL_SUPPORT,
            IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
            "copied_or_generic_lexical_overlap",
            "copied or generic normalized description token overlaps",
            tuple(left_copied[token]), tuple(right_copied[token]), (token,),
            "SHADOW_COPIED_GENERIC_LEXICAL_OVERLAP_ONLY",
        ))

    return with_signed_identity_evidence_fingerprint(SignedIdentityEvidence(
        contract_version=SIGNED_IDENTITY_EVIDENCE_CONTRACT_VERSION,
        record_reference_1=left.record_reference,
        record_reference_2=right.record_reference,
        signature_version_1=left.derivation_version,
        signature_version_2=right.derivation_version,
        signature_fingerprint_1=left.signature_fingerprint,
        signature_fingerprint_2=right.signature_fingerprint,
        facts=tuple(facts),
    ))


def classify_shadow_evidence(evidence: SignedIdentityEvidence) -> ShadowEvidenceBucket:
    channels = {item.channel for item in evidence.facts}
    contradiction = SignedEvidenceChannel.IDENTITY_CONTRADICTION in channels
    other = bool(channels - {SignedEvidenceChannel.IDENTITY_CONTRADICTION})
    if contradiction and other:
        return ShadowEvidenceBucket.SHADOW_MIXED_EVIDENCE
    if contradiction:
        return ShadowEvidenceBucket.SHADOW_EXPLICIT_CONTRADICTION
    if SignedEvidenceChannel.IDENTITY_SUPPORT in channels:
        return ShadowEvidenceBucket.SHADOW_TRUSTED_IDENTITY_PRESENT
    if SignedEvidenceChannel.LEXICAL_SUPPORT in channels:
        return ShadowEvidenceBucket.SHADOW_LEXICAL_ONLY_OR_UNRESOLVED
    return ShadowEvidenceBucket.SHADOW_INSUFFICIENT
