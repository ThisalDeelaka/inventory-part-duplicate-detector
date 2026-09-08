"""Bounded, source-aware functional/location identity facets.

Facets are record-local observations. A pair contradiction is possible only
when two trusted sources expose incompatible values on the same axis and the
same qualifier-free construct. Raw tokens alone never create a contradiction.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.normalizer import normalize_description


FUNCTIONAL_LOCATION_FACET_VERSION = "functional-location-facet-v1"

_AXIS_VALUES = {
    "longitudinal_end": {
        "head": "head",
        "tail": "tail",
    },
}
_INCOMPATIBLE_VALUES = {
    "longitudinal_end": frozenset({frozenset(("head", "tail"))}),
}
_NON_CONSTRUCT_FOLLOWERS = frozenset({
    "assembly", "assy", "component", "comp", "item", "kit", "module",
    "part", "subassembly", "unit",
})


@dataclass(frozen=True, order=True)
class FunctionalLocationFacet:
    axis: str
    value: str
    shared_construct: str
    source_family: str
    matched_evidence: str
    provenance_code: str = FUNCTIONAL_LOCATION_FACET_VERSION


@dataclass(frozen=True, order=True)
class FunctionalLocationConflict:
    axis: str
    shared_construct: str
    values_1: tuple[str, ...]
    values_2: tuple[str, ...]
    source_families_1: tuple[str, ...]
    source_families_2: tuple[str, ...]
    matched_evidence_1: tuple[str, ...]
    matched_evidence_2: tuple[str, ...]


def extract_functional_location_facets(
    value,
    *,
    source_family: str,
) -> tuple[FunctionalLocationFacet, ...]:
    """Extract explicit modifier-plus-construct facets from one bounded source."""
    normalized = normalize_description(value)
    words = normalized.split()
    facets = set()
    for index, word in enumerate(words[:-1]):
        for axis, values in _AXIS_VALUES.items():
            normalized_value = values.get(word)
            if normalized_value is None:
                continue
            follower = words[index + 1]
            if (
                follower in _NON_CONSTRUCT_FOLLOWERS
                or len(follower) < 2
                or not any(character.isalpha() for character in follower)
            ):
                continue
            construct_words = words[:index] + words[index + 1:]
            shared_construct = " ".join(construct_words).strip()
            if not shared_construct:
                continue
            facets.add(FunctionalLocationFacet(
                axis=axis,
                value=normalized_value,
                shared_construct=shared_construct,
                source_family=str(source_family).strip().upper(),
                matched_evidence=f"{word} {follower}",
            ))
    return tuple(sorted(facets))


def find_functional_location_conflicts(
    facets_1: tuple[FunctionalLocationFacet, ...],
    facets_2: tuple[FunctionalLocationFacet, ...],
) -> tuple[FunctionalLocationConflict, ...]:
    """Compare only two-sided facets with the same axis and shared construct."""
    grouped_1 = {}
    grouped_2 = {}
    for target, facets in ((grouped_1, facets_1), (grouped_2, facets_2)):
        for facet in facets:
            target.setdefault((facet.axis, facet.shared_construct), []).append(facet)

    conflicts = []
    for axis, shared_construct in sorted(set(grouped_1) & set(grouped_2)):
        left = grouped_1[(axis, shared_construct)]
        right = grouped_2[(axis, shared_construct)]
        values_1 = tuple(sorted({item.value for item in left}))
        values_2 = tuple(sorted({item.value for item in right}))
        if not any(
            frozenset((first, second)) in _INCOMPATIBLE_VALUES.get(axis, ())
            for first in values_1
            for second in values_2
        ):
            continue
        conflicts.append(FunctionalLocationConflict(
            axis=axis,
            shared_construct=shared_construct,
            values_1=values_1,
            values_2=values_2,
            source_families_1=tuple(sorted({item.source_family for item in left})),
            source_families_2=tuple(sorted({item.source_family for item in right})),
            matched_evidence_1=tuple(sorted({item.matched_evidence for item in left})),
            matched_evidence_2=tuple(sorted({item.matched_evidence for item in right})),
        ))
    return tuple(conflicts)
