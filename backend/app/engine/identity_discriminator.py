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


IDENTITY_DISCRIMINATOR_VERSION = "identity-discriminator-v3"

_OBJECT_CLASS_PATTERNS = {
    "carbon-stick": (r"\bcarbon\s+sticks?\b",),
    "clutch-disk": (r"\bclutch\s*dis[ck]s?\b",),
    "coil-spring": (r"\bcoil\s*springs?\b",),
    "commercial-condition": (r"\bconditions?\b",),
    "commercial-discount": (r"\bdiscounts?\b",),
    "dust-cap": (r"\bdust\s*caps?\b",),
    "nail": (r"\bnails?\b",),
    "pencil": (r"\bpencils?\b",),
    "table": (r"\btables?\b",),
    "tyre": (r"\btyres?\b", r"\btires?\b"),
    "wheel": (r"\bwheels?\b", r"\brims?\b"),
}
_PART_NUMBER_ONLY_CLASSES = frozenset({
    "commercial-condition",
    "commercial-discount",
})
_INCOMPATIBLE_OBJECT_CLASSES = frozenset({
    frozenset(("carbon-stick", "pencil")),
    frozenset(("clutch-disk", "coil-spring")),
    frozenset(("clutch-disk", "dust-cap")),
    frozenset(("coil-spring", "dust-cap")),
    frozenset(("commercial-condition", "commercial-discount")),
    frozenset(("nail", "table")),
    frozenset(("tyre", "wheel")),
})
_TYRE_VARIANT_PATTERNS = {
    "all-terrain": (r"\ball\s+terrain\b", r"\bat\b"),
    "slick": (r"\bslick\b",),
    "snow": (r"\bsnow\b",),
}
_DIRECTIONAL_SIDE_PATTERNS = {
    "LEFT": re.compile(
        r"(?<![a-z0-9])(?:left[\s_-]+(?:side|hand)|lh|l\s*/\s*[hs])(?![a-z0-9])",
        re.IGNORECASE,
    ),
    "RIGHT": re.compile(
        r"(?<![a-z0-9])(?:right[\s_-]+(?:side|hand)|rh|r\s*/\s*[hs])(?![a-z0-9])",
        re.IGNORECASE,
    ),
}
_PART_NUMBER_BARE_SIDE_PATTERNS = {
    "LEFT": re.compile(r"(?<![a-z0-9])left(?![a-z0-9])", re.IGNORECASE),
    "RIGHT": re.compile(r"(?<![a-z0-9])right(?![a-z0-9])", re.IGNORECASE),
}


@dataclass(frozen=True)
class RecordDiscriminatorEvidence:
    part_number_classes: tuple[str, ...]
    description_classes: tuple[str, ...]
    resolved_object_class: str | None
    object_class_provenance: str
    tyre_variants: tuple[str, ...]
    part_number_sides: tuple[str, ...]
    description_sides: tuple[str, ...]
    resolved_side: str | None
    side_provenance: str
    part_number_side_matches: tuple[str, ...]
    description_side_matches: tuple[str, ...]
    part_number_side_base: str
    description_side_base: str


@dataclass(frozen=True)
class IdentityDiscriminatorResult:
    protected_conflicts: tuple[dict, ...]
    evidence_payload: dict


def _classes(value, source_family: str) -> tuple[str, ...]:
    normalized = normalize_description(value)
    return tuple(sorted(
        object_class
        for object_class, patterns in _OBJECT_CLASS_PATTERNS.items()
        if not (
            source_family != "PART_NUMBER"
            and object_class in _PART_NUMBER_ONLY_CLASSES
        )
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


def _directional_side(value, source_family: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """Extract bounded explicit handedness while retaining a side-free base."""
    raw = "" if value is None else str(value).strip().casefold()
    if raw in {"", "nan", "none"}:
        return (), (), ""
    patterns = dict(_DIRECTIONAL_SIDE_PATTERNS)
    if source_family == "PART_NUMBER":
        patterns = {
            side: re.compile(
                rf"(?:{patterns[side].pattern})|(?:{_PART_NUMBER_BARE_SIDE_PATTERNS[side].pattern})",
                re.IGNORECASE,
            )
            for side in patterns
        }
    hits = []
    matches = []
    spans = []
    for side, pattern in patterns.items():
        for match in pattern.finditer(raw):
            hits.append(side)
            matches.append(normalize_description(match.group(0)))
            spans.append(match.span())
    if not spans:
        return (), (), ""
    base = raw
    for start, end in sorted(spans, reverse=True):
        base = f"{base[:start]} {base[end:]}"
    return tuple(sorted(set(hits))), tuple(sorted(set(matches))), normalize_description(base)


def _resolved_side(
    part_sides: tuple[str, ...], description_sides: tuple[str, ...]
) -> tuple[str | None, str]:
    if len(part_sides) == 1:
        if part_sides == description_sides:
            return part_sides[0], "PART_NUMBER_AND_DESCRIPTION_SIDE"
        return part_sides[0], "EXPLICIT_PART_NUMBER_SIDE"
    if not part_sides and len(description_sides) == 1:
        return description_sides[0], "EXPLICIT_DESCRIPTION_SIDE"
    return None, "UNKNOWN_OR_SIDE_SOURCE_CONFLICT"


def extract_record_discriminators(part_no, description) -> RecordDiscriminatorEvidence:
    """Extract only explicit, record-local evidence; unknown stays unknown."""
    part_classes = _classes(part_no, "PART_NUMBER")
    description_classes = _classes(description, "DESCRIPTION")
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
    part_sides, part_side_matches, part_side_base = _directional_side(
        part_no, "PART_NUMBER"
    )
    description_sides, description_side_matches, description_side_base = (
        _directional_side(description, "DESCRIPTION")
    )
    resolved_side, side_provenance = _resolved_side(
        part_sides, description_sides
    )
    return RecordDiscriminatorEvidence(
        part_number_classes=part_classes,
        description_classes=description_classes,
        resolved_object_class=resolved,
        object_class_provenance=provenance,
        tyre_variants=tuple(sorted(variants)),
        part_number_sides=part_sides,
        description_sides=description_sides,
        resolved_side=resolved_side,
        side_provenance=side_provenance,
        part_number_side_matches=part_side_matches,
        description_side_matches=description_side_matches,
        part_number_side_base=part_side_base,
        description_side_base=description_side_base,
    )


def _incompatible(left: str | None, right: str | None) -> bool:
    return bool(
        left and right
        and frozenset((left, right)) in _INCOMPATIBLE_OBJECT_CLASSES
    )


def _explicit_part_number_conflict(
    first: RecordDiscriminatorEvidence,
    second: RecordDiscriminatorEvidence,
) -> tuple[str, str] | None:
    """Prefer two explicit incompatible part-number nouns over copied text."""
    if len(first.part_number_classes) != 1 or len(second.part_number_classes) != 1:
        return None
    left = first.part_number_classes[0]
    right = second.part_number_classes[0]
    return (left, right) if _incompatible(left, right) else None


def _conflict_group(left: str, right: str) -> tuple[str, str]:
    if left.startswith("commercial-") and right.startswith("commercial-"):
        return "IDENTITY_CONSTRUCT_CLASS", "commercial identity construct"
    return "IDENTITY_OBJECT_CLASS", "physical object class"


def _side_bases(item: RecordDiscriminatorEvidence) -> set[str]:
    values = set()
    if item.resolved_side in item.part_number_sides and item.part_number_side_base:
        values.add(item.part_number_side_base)
    if item.resolved_side in item.description_sides and item.description_side_base:
        values.add(item.description_side_base)
    return {
        value for value in values
        if any(len(token) >= 2 and token.isalpha() for token in value.split())
    }


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
        group, label = _conflict_group(
            first.resolved_object_class, second.resolved_object_class
        )
        conflicts.append({
            "group": group,
            "label": label,
            "values_a": [first.resolved_object_class],
            "values_b": [second.resolved_object_class],
            "provenance": "EXPLICIT_TWO_SIDED_OBJECT_CLASS",
        })

    else:
        composite = _explicit_part_number_conflict(first, second)
        provenance = "EXPLICIT_TWO_SIDED_PART_NUMBER_CLASS"
        if composite is None:
            composite = _dirty_description_conflict(first, second, uom.relationship)
            provenance = "PART_NUMBER_DESCRIPTION_UOM_COMPOSITE"
        if composite is None:
            reverse = _dirty_description_conflict(second, first, uom.relationship)
            if reverse is not None:
                composite = (reverse[1], reverse[0])
        if composite is not None:
            group, label = _conflict_group(*composite)
            conflicts.append({
                "group": group,
                "label": label,
                "values_a": [composite[0]],
                "values_b": [composite[1]],
                "provenance": provenance,
            })

    if (
        first.resolved_side in {"LEFT", "RIGHT"}
        and second.resolved_side in {"LEFT", "RIGHT"}
        and first.resolved_side != second.resolved_side
        and _side_bases(first) & _side_bases(second)
    ):
        conflicts.append({
            "group": "IDENTITY_SIDE_VARIANT",
            "label": "explicit directional side variant",
            "values_a": [first.resolved_side],
            "values_b": [second.resolved_side],
            "provenance": "EXPLICIT_TWO_SIDED_DIRECTIONAL_VARIANT",
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
            "part_number_sides": list(item.part_number_sides),
            "description_sides": list(item.description_sides),
            "resolved_side": item.resolved_side,
            "side_provenance": item.side_provenance,
            "part_number_side_matches": list(item.part_number_side_matches),
            "description_side_matches": list(item.description_side_matches),
            "part_number_side_base": item.part_number_side_base,
            "description_side_base": item.description_side_base,
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
