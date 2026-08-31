"""Pure, unused R15 derivation of record-local identity signatures."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping

from app.engine.generic_description_guard import is_generic_description
from app.engine.identity_discriminator import (
    IDENTITY_DISCRIMINATOR_VERSION,
    extract_record_discriminators,
)
from app.engine.identity_signature import (
    IDENTITY_SIGNATURE_CONTRACT_VERSION,
    IdentityObservation,
    IdentityObservationState,
    IdentitySemanticCategory,
    IdentitySignature,
    IdentitySourceField,
    SourceObservation,
    with_identity_signature_fingerprint,
)
from app.engine.normalizer import (
    extract_technical_tokens,
    normalize_description,
    normalize_part_no_with_dictionary,
)
from app.engine.variant_extractor import extract_variant_attributes


IDENTITY_SIGNATURE_DERIVATION_VERSION = "identity-signature-derivation-v1"
MAX_UNRESOLVED_OBSERVATIONS_PER_SOURCE = 4
MAX_UNRESOLVED_TOKEN_LENGTH = 32

_FIELD_KEYS = {
    IdentitySourceField.PART_NUMBER: ("PART_NO", "part_no", "Part No"),
    IdentitySourceField.DESCRIPTION: (
        "DESCRIPTION", "description", "Part Description"
    ),
    IdentitySourceField.MASTER_DESCRIPTION: (
        "MASTER_DESCRIPTION", "master_description", "Master Part Description"
    ),
    IdentitySourceField.TYPE_DESIGNATION: (
        "TYPE_DESIGNATION", "type_designation", "Type Designation"
    ),
    IdentitySourceField.DIMENSION_QUALITY: (
        "DIMENSION_QUALITY", "dimension_quality", "Dimension/ Quality"
    ),
}
_RECORD_REFERENCE_KEYS = (
    "record_ref_key", "RECORD_REF_KEY", "record_reference", "stable_ref"
)
_ROLE_GROUPS = frozenset({
    "END_POSITION", "SERIALIZATION_ROLE", "FLOW_ROLE",
    "ENGINE_COMPONENT_ROLE", "STRUCTURAL_ROLE",
})
_CRITICAL_ATTRIBUTE_GROUPS = frozenset({"ELECTRICAL_RATING", "DIMENSION"})
_MODEL_GROUPS = frozenset({"TYPE_OR_GRADE"})
_NON_SIGNATURE_VARIANT_GROUPS = frozenset({"TRAILING_VARIANT_BASE"})
_UNRESOLVED_STOPWORDS = frozenset({
    "a", "an", "and", "description", "for", "grade", "item", "master",
    "material", "model", "of", "part", "the", "type",
})


def _record_value(record, keys: tuple[str, ...]):
    if isinstance(record, Mapping):
        for key in keys:
            if key in record:
                return record[key]
        return None
    for key in keys:
        if hasattr(record, key):
            return getattr(record, key)
    return None


def _normalized_source_value(source_field: IdentitySourceField, value) -> str:
    if source_field == IdentitySourceField.PART_NUMBER:
        return normalize_part_no_with_dictionary(value)
    return normalize_description(value)


def _bounded_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token[:MAX_UNRESOLVED_TOKEN_LENGTH]
        for token in value.split()[:MAX_UNRESOLVED_OBSERVATIONS_PER_SOURCE]
        if token
    )


def _source_code(
    source_field: IdentitySourceField,
    *,
    generic: bool,
    description_master_match: bool,
    purpose: str,
) -> str:
    parts = [purpose, source_field.value]
    if generic:
        parts.append("GENERIC")
    if description_master_match and source_field in {
        IdentitySourceField.DESCRIPTION,
        IdentitySourceField.MASTER_DESCRIPTION,
    }:
        parts.append("DESCRIPTION_MASTER_MATCH")
    return "__".join(parts)


def _source_observation(
    source_field: IdentitySourceField,
    evidence: tuple[str, ...],
    *,
    generic: bool,
    description_master_match: bool,
    purpose: str,
) -> SourceObservation:
    return SourceObservation(
        source_field=source_field,
        normalized_evidence=evidence,
        provenance_code=_source_code(
            source_field,
            generic=generic,
            description_master_match=description_master_match,
            purpose=purpose,
        ),
    )


def _add_observation(
    observations,
    category: IdentitySemanticCategory,
    semantic_key: str,
    normalized_value: str,
    source: SourceObservation,
    reason_code: str,
):
    observations[(category, semantic_key, normalized_value, reason_code)].append(source)


def _model_tokens(raw_value, normalized_value: str) -> tuple[str, ...]:
    raw = "" if raw_value is None else str(raw_value)
    compact = {
        match.group(0).casefold()
        for match in re.finditer(
            r"(?<![a-z0-9])(?=[a-z0-9]*[a-z])(?=[a-z0-9]*\d)[a-z0-9]{3,}(?![a-z0-9])",
            raw,
            flags=re.IGNORECASE,
        )
    }
    explicit = set()
    for match in re.finditer(
        r"\b(?:model|type)\s+([a-z0-9]{1,16})\b", normalized_value
    ):
        value = match.group(1)
        if len(value) >= 2 or (any(char.isalpha() for char in value)
                               and any(char.isdigit() for char in value)):
            explicit.add(value)
    return tuple(sorted(compact | explicit))


def _unresolved_model_markers(normalized_value: str) -> tuple[str, ...]:
    values = set()
    for match in re.finditer(
        r"\b(model|type)\s+([a-z0-9]{1,16})\b", normalized_value
    ):
        qualifier = match.group(2)
        if len(qualifier) == 1 and qualifier.isalpha():
            values.add(f"{match.group(1)} {qualifier}")
    return tuple(sorted(values))


def derive_identity_signature(record, *, record_reference: str | None = None) -> IdentitySignature:
    """Derive one deterministic signature without pair or runtime authority."""
    reference = str(
        record_reference or _record_value(record, _RECORD_REFERENCE_KEYS) or ""
    ).strip()
    if not reference:
        raise ValueError("identity signature derivation requires record_reference")

    source_values = {
        source_field: _record_value(record, keys)
        for source_field, keys in _FIELD_KEYS.items()
    }
    normalized_values = {
        source_field: _normalized_source_value(source_field, value)
        for source_field, value in source_values.items()
    }
    description_value = normalized_values[IdentitySourceField.DESCRIPTION]
    master_value = normalized_values[IdentitySourceField.MASTER_DESCRIPTION]
    description_master_match = bool(
        description_value and master_value and description_value == master_value
    )

    grouped = defaultdict(list)
    unresolved = []
    recognized_tokens_by_source = defaultdict(set)

    for source_field, raw_value in source_values.items():
        normalized = normalized_values[source_field]
        if not normalized:
            continue
        generic = (
            source_field != IdentitySourceField.PART_NUMBER
            and is_generic_description(raw_value)
        )
        if source_field == IdentitySourceField.PART_NUMBER:
            discriminator = extract_record_discriminators(raw_value, "")
            classes = discriminator.part_number_classes
            class_matches = discriminator.part_number_class_matches
            sides = discriminator.part_number_sides
            side_matches = discriminator.part_number_side_matches
        else:
            discriminator = extract_record_discriminators("", raw_value)
            classes = discriminator.description_classes
            class_matches = discriminator.description_class_matches
            sides = discriminator.description_sides
            side_matches = discriminator.description_side_matches

        for object_class in classes:
            evidence = tuple(class_matches) or (object_class,)
            source = _source_observation(
                source_field, evidence, generic=generic,
                description_master_match=description_master_match,
                purpose=f"{IDENTITY_DISCRIMINATOR_VERSION}_OBJECT_MATCH",
            )
            _add_observation(
                grouped, IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
                "bounded_object_or_construct", object_class, source,
                "BOUNDED_OBJECT_OR_CONSTRUCT_RECOGNIZED",
            )
            recognized_tokens_by_source[source_field].update(
                token for item in evidence for token in normalize_description(item).split()
            )

        for side in sides:
            evidence = tuple(side_matches) or (side.casefold(),)
            source = _source_observation(
                source_field, evidence, generic=generic,
                description_master_match=description_master_match,
                purpose=f"{IDENTITY_DISCRIMINATOR_VERSION}_SIDE_MATCH",
            )
            _add_observation(
                grouped, IdentitySemanticCategory.VARIANT_IDENTITY,
                "directional_side", side.casefold(), source,
                "BOUNDED_DIRECTIONAL_SIDE_RECOGNIZED",
            )
            recognized_tokens_by_source[source_field].update(
                token for item in evidence for token in normalize_description(item).split()
            )

        for tyre_variant in discriminator.tyre_variants:
            source = _source_observation(
                source_field, (tyre_variant,), generic=generic,
                description_master_match=description_master_match,
                purpose=f"{IDENTITY_DISCRIMINATOR_VERSION}_TYRE_VARIANT",
            )
            _add_observation(
                grouped, IdentitySemanticCategory.VARIANT_IDENTITY,
                "tyre_variant", tyre_variant, source,
                "BOUNDED_TYRE_VARIANT_RECOGNIZED",
            )
            recognized_tokens_by_source[source_field].add(tyre_variant)

        variants = extract_variant_attributes(raw_value)
        for group, values in variants.items():
            if not values or group in _NON_SIGNATURE_VARIANT_GROUPS:
                continue
            if group in _ROLE_GROUPS:
                category = IdentitySemanticCategory.ASSEMBLY_COMPONENT_ROLE
                key = group.casefold()
            elif group in _MODEL_GROUPS:
                category = IdentitySemanticCategory.MODEL_TYPE_IDENTITY
                key = "explicit_type_or_grade"
            elif group in _CRITICAL_ATTRIBUTE_GROUPS:
                category = IdentitySemanticCategory.CRITICAL_IDENTITY_ATTRIBUTE
                key = group.casefold()
            else:
                category = IdentitySemanticCategory.VARIANT_IDENTITY
                key = group.casefold()
            for value in values:
                if group == "TYPE_OR_GRADE":
                    qualifier = value.split()[-1]
                    if len(qualifier) == 1 and qualifier.isalpha():
                        continue
                source = _source_observation(
                    source_field, (value,), generic=generic,
                    description_master_match=description_master_match,
                    purpose="VARIANT_EXTRACTOR_MATCH",
                )
                _add_observation(
                    grouped, category, key, value, source,
                    f"BOUNDED_{group}_RECOGNIZED",
                )
                recognized_tokens_by_source[source_field].update(
                    normalize_description(value).split()
                )

        for model in _model_tokens(raw_value, normalized):
            source = _source_observation(
                source_field, (model,), generic=generic,
                description_master_match=description_master_match,
                purpose="STRUCTURAL_MODEL_TOKEN",
            )
            _add_observation(
                grouped, IdentitySemanticCategory.MODEL_TYPE_IDENTITY,
                "structural_alphanumeric_model", model, source,
                "STRUCTURAL_ALPHANUMERIC_MODEL_RECOGNIZED",
            )
            recognized_tokens_by_source[source_field].add(model)

        for marker in _unresolved_model_markers(normalized):
            source = _source_observation(
                source_field, tuple(marker.split()), generic=generic,
                description_master_match=description_master_match,
                purpose="UNRESOLVED_SINGLE_CHARACTER_MODEL",
            )
            unresolved.append(IdentityObservation(
                IdentitySemanticCategory.MODEL_TYPE_IDENTITY,
                "unresolved_model_or_type", marker,
                IdentityObservationState.UNRESOLVED, (source,),
                "SINGLE_CHARACTER_MODEL_QUALIFIER_NOT_PROMOTED",
            ))
            recognized_tokens_by_source[source_field].update(marker.split())

        technical = extract_technical_tokens(raw_value)
        for key in ("measurements", "dimensions"):
            for value in technical[key]:
                source = _source_observation(
                    source_field, (value,), generic=generic,
                    description_master_match=description_master_match,
                    purpose="TECHNICAL_TOKEN_MATCH",
                )
                _add_observation(
                    grouped, IdentitySemanticCategory.CRITICAL_IDENTITY_ATTRIBUTE,
                    key[:-1] if key.endswith("s") else key, value, source,
                    "TYPED_TECHNICAL_ATTRIBUTE_RECOGNIZED",
                )
                recognized_tokens_by_source[source_field].update(
                    normalize_description(value).split()
                )

        residuals = []
        for token in normalized.split():
            if token in recognized_tokens_by_source[source_field]:
                continue
            if token in _UNRESOLVED_STOPWORDS:
                continue
            if len(token) > MAX_UNRESOLVED_TOKEN_LENGTH:
                token = token[:MAX_UNRESOLVED_TOKEN_LENGTH]
            if len(token) < 2 and not any(char.isdigit() for char in token):
                continue
            if token not in residuals:
                residuals.append(token)
            if len(residuals) >= MAX_UNRESOLVED_OBSERVATIONS_PER_SOURCE:
                break
        for token in residuals:
            source = _source_observation(
                source_field, (token,), generic=generic,
                description_master_match=description_master_match,
                purpose="BOUNDED_UNRESOLVED_TOKEN",
            )
            unresolved.append(IdentityObservation(
                IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
                "unresolved_identity_token", token,
                IdentityObservationState.UNRESOLVED, (source,),
                "UNRECOGNIZED_BOUNDED_SOURCE_TOKEN",
            ))

        if generic:
            source = _source_observation(
                source_field, _bounded_tokens(normalized), generic=True,
                description_master_match=description_master_match,
                purpose="DESCRIPTION_RELIABILITY",
            )
            unresolved.append(IdentityObservation(
                IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
                "description_reliability", "generic-description",
                IdentityObservationState.UNRESOLVED, (source,),
                "GENERIC_DESCRIPTION_METADATA_ONLY",
            ))

    if description_master_match:
        sources = tuple(
            _source_observation(
                field, _bounded_tokens(normalized_values[field]), generic=False,
                description_master_match=True, purpose="DESCRIPTION_RELIABILITY",
            )
            for field in (
                IdentitySourceField.DESCRIPTION,
                IdentitySourceField.MASTER_DESCRIPTION,
            )
        )
        unresolved.append(IdentityObservation(
            IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
            "description_reliability", "description-master-identical",
            IdentityObservationState.UNRESOLVED, sources,
            "DESCRIPTION_MASTER_NORMALIZED_MATCH_METADATA_ONLY",
        ))

    built = defaultdict(list)
    for (category, key, value, reason), sources in grouped.items():
        built[category].append(IdentityObservation(
            category, key, value, IdentityObservationState.OBSERVED,
            tuple(sources), reason,
        ))

    major_categories = tuple(IdentitySemanticCategory)
    unknown_categories = tuple(
        category for category in major_categories if not built[category]
    )
    return with_identity_signature_fingerprint(IdentitySignature(
        contract_version=IDENTITY_SIGNATURE_CONTRACT_VERSION,
        derivation_version=IDENTITY_SIGNATURE_DERIVATION_VERSION,
        record_reference=reference,
        object_construct_observations=tuple(
            built[IdentitySemanticCategory.OBJECT_OR_CONSTRUCT]
        ),
        assembly_component_role_observations=tuple(
            built[IdentitySemanticCategory.ASSEMBLY_COMPONENT_ROLE]
        ),
        model_type_observations=tuple(
            built[IdentitySemanticCategory.MODEL_TYPE_IDENTITY]
        ),
        variant_observations=tuple(
            built[IdentitySemanticCategory.VARIANT_IDENTITY]
        ),
        critical_attribute_observations=tuple(
            built[IdentitySemanticCategory.CRITICAL_IDENTITY_ATTRIBUTE]
        ),
        unresolved_observations=tuple(unresolved),
        unknown_categories=unknown_categories,
    ))
