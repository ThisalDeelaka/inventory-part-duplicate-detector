"""Bounded deterministic identity discriminators for GF-4 evidence.

The vocabulary is intentionally small and semantic.  It identifies explicit
physical object classes and mutually exclusive variants; it does not score
similarity, infer from missing values, or turn UOM into universal identity
authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.engine.normalizer import normalize_description
from app.engine.uom_relationship import UomRelationship, classify_uom_relationship


IDENTITY_DISCRIMINATOR_VERSION = "identity-discriminator-v1"

_OBJECT_CLASS_PATTERNS = {
    "carbon-stick": (r"\bcarbon\s+sticks?\b",),
    "pencil": (r"\bpencils?\b",),
    "tyre": (r"\btyres?\b", r"\btires?\b"),
    "wheel": (r"\bwheels?\b",),
}
_INCOMPATIBLE_OBJECT_CLASSES = frozenset({
    frozenset(("carbon-stick", "pencil")),
    frozenset(("tyre", "wheel")),
})
_TYRE_VARIANT_PATTERNS = {
    "all-terrain": (r"\ball\s+terrain\b", r"\bat\b"),
    "slick": (r"\bslick\b",),
    "snow": (r"\bsnow\b",),
}


@dataclass(frozen=True)
class RecordDiscriminatorEvidence:
    part_number_classes: tuple[str, ...]
    description_classes: tuple[str, ...]
    resolved_object_class: str | None
    object_class_provenance: str
    tyre_variants: tuple[str, ...]


@dataclass(frozen=True)
class IdentityDiscriminatorResult:
    protected_conflicts: tuple[dict, ...]
    evidence_payload: dict


def _classes(value) -> tuple[str, ...]:
    normalized = normalize_description(value)
    return tuple(sorted(
        object_class
        for object_class, patterns in _OBJECT_CLASS_PATTERNS.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    ))


def _tyre_variants(value, classes: tuple[str, ...]) -> set[str]:
    if "tyre" not in classes:
        return set()
    normalized = normalize_description(value)
    return {
        variant
        for variant, patterns in _TYRE_VARIANT_PATTERNS.items()
        if any(re.search(pattern, normalized) for pattern in patterns)
    }


def extract_record_discriminators(part_no, description) -> RecordDiscriminatorEvidence:
    """Extract only explicit, record-local evidence; unknown stays unknown."""
    part_classes = _classes(part_no)
    description_classes = _classes(description)
    shared = set(part_classes) & set(description_classes)
    if len(shared) == 1:
        resolved = next(iter(shared))
        provenance = "PART_NUMBER_AND_DESCRIPTION"
    elif len(part_classes) == 1 and not description_classes:
        resolved = part_classes[0]
        provenance = "EXPLICIT_PART_NUMBER"
    elif len(description_classes) == 1 and not part_classes:
        resolved = description_classes[0]
        provenance = "EXPLICIT_DESCRIPTION"
    else:
        resolved = None
        provenance = "UNKNOWN_OR_SOURCE_CONFLICT"

    variants = _tyre_variants(part_no, part_classes)
    variants.update(_tyre_variants(description, description_classes))
    return RecordDiscriminatorEvidence(
        part_number_classes=part_classes,
        description_classes=description_classes,
        resolved_object_class=resolved,
        object_class_provenance=provenance,
        tyre_variants=tuple(sorted(variants)),
    )


def _incompatible(left: str | None, right: str | None) -> bool:
    return bool(
        left and right
        and frozenset((left, right)) in _INCOMPATIBLE_OBJECT_CLASSES
    )


def _dirty_description_conflict(
    trusted: RecordDiscriminatorEvidence,
    copied: RecordDiscriminatorEvidence,
    uom_relationship: UomRelationship,
) -> tuple[str, str] | None:
    """Recognize copied-description conflict only with three independent signals."""
    trusted_class = trusted.resolved_object_class
    if (
        not trusted_class
        or len(copied.part_number_classes) != 1
        or trusted_class not in copied.description_classes
        or uom_relationship != UomRelationship.DIFFERENT_DIMENSION_OR_BASIS
    ):
        return None
    part_class = copied.part_number_classes[0]
    if not _incompatible(trusted_class, part_class):
        return None
    return trusted_class, part_class


def evaluate_identity_discriminators(
    part_no_1,
    description_1,
    uom_1,
    part_no_2,
    description_2,
    uom_2,
) -> IdentityDiscriminatorResult:
    """Return high-confidence protected conflicts plus auditable provenance."""
    first = extract_record_discriminators(part_no_1, description_1)
    second = extract_record_discriminators(part_no_2, description_2)
    uom = classify_uom_relationship(uom_1, uom_2)
    conflicts = []

    if _incompatible(first.resolved_object_class, second.resolved_object_class):
        conflicts.append({
            "group": "IDENTITY_OBJECT_CLASS",
            "label": "physical object class",
            "values_a": [first.resolved_object_class],
            "values_b": [second.resolved_object_class],
            "provenance": "EXPLICIT_TWO_SIDED_OBJECT_CLASS",
        })
    else:
        composite = _dirty_description_conflict(first, second, uom.relationship)
        if composite is None:
            reverse = _dirty_description_conflict(second, first, uom.relationship)
            if reverse is not None:
                composite = (reverse[1], reverse[0])
        if composite is not None:
            conflicts.append({
                "group": "IDENTITY_OBJECT_CLASS",
                "label": "physical object class",
                "values_a": [composite[0]],
                "values_b": [composite[1]],
                "provenance": "PART_NUMBER_DESCRIPTION_UOM_COMPOSITE",
            })

    if (
        first.resolved_object_class == second.resolved_object_class == "tyre"
        and len(first.tyre_variants) == len(second.tyre_variants) == 1
        and first.tyre_variants != second.tyre_variants
    ):
        conflicts.append({
            "group": "MUTUALLY_EXCLUSIVE_TYRE_VARIANT",
            "label": "explicit tyre variant",
            "values_a": list(first.tyre_variants),
            "values_b": list(second.tyre_variants),
            "provenance": "EXPLICIT_TWO_SIDED_VARIANT",
        })

    def payload(item: RecordDiscriminatorEvidence) -> dict:
        return {
            "part_number_classes": list(item.part_number_classes),
            "description_classes": list(item.description_classes),
            "resolved_object_class": item.resolved_object_class,
            "object_class_provenance": item.object_class_provenance,
            "tyre_variants": list(item.tyre_variants),
        }

    return IdentityDiscriminatorResult(
        protected_conflicts=tuple(conflicts),
        evidence_payload={
            "version": IDENTITY_DISCRIMINATOR_VERSION,
            "record_1": payload(first),
            "record_2": payload(second),
            "uom_relationship": uom.relationship.value,
            "protected_conflict_count": len(conflicts),
        },
    )
