import re
from dataclasses import dataclass
from enum import Enum


class UomRelationship(str, Enum):
    SAME_UOM = "SAME_UOM"
    CONVERTIBLE_SAME_DIMENSION = "CONVERTIBLE_SAME_DIMENSION"
    DIFFERENT_DIMENSION_OR_BASIS = "DIFFERENT_DIMENSION_OR_BASIS"
    MISSING_OR_WILDCARD = "MISSING_OR_WILDCARD"
    MALFORMED_OR_UNKNOWN = "MALFORMED_OR_UNKNOWN"


class MappingQuality(str, Enum):
    CONSISTENT = "CONSISTENT"
    POSSIBLE_MAPPING_ERROR = "POSSIBLE_MAPPING_ERROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class UomEvidence:
    relationship: UomRelationship
    reason_code: str
    penalty: float
    mapping_quality: MappingQuality


_MISSING_OR_WILDCARD = {
    "", "*", "-", "--", "n/a", "na", "n.a.", "none", "null", "nil",
}

# Deliberately small and deterministic. These are normalization aliases and
# dimensions, not a quantity-conversion engine.
_ALIASES = {
    "pc": ("piece", "count"),
    "pcs": ("piece", "count"),
    "piece": ("piece", "count"),
    "pieces": ("piece", "count"),
    "ea": ("piece", "count"),
    "each": ("piece", "count"),
    "unit": ("piece", "count"),
    "units": ("piece", "count"),
    "l": ("litre", "volume"),
    "lt": ("litre", "volume"),
    "ltr": ("litre", "volume"),
    "liter": ("litre", "volume"),
    "liters": ("litre", "volume"),
    "litre": ("litre", "volume"),
    "litres": ("litre", "volume"),
    "ml": ("millilitre", "volume"),
    "milliliter": ("millilitre", "volume"),
    "millilitre": ("millilitre", "volume"),
    "gal": ("gallon", "volume"),
    "gallon": ("gallon", "volume"),
    "gallons": ("gallon", "volume"),
    "qt": ("liquid_quart", "volume"),
    "quart": ("liquid_quart", "volume"),
    "liquid quart": ("liquid_quart", "volume"),
    "liq qt": ("liquid_quart", "volume"),
    "m3": ("cubic_metre", "volume"),
    "kg": ("kilogram", "mass"),
    "kilogram": ("kilogram", "mass"),
    "g": ("gram", "mass"),
    "gram": ("gram", "mass"),
    "lb": ("pound", "mass"),
    "lbs": ("pound", "mass"),
    "pound": ("pound", "mass"),
    "m": ("metre", "length"),
    "meter": ("metre", "length"),
    "metre": ("metre", "length"),
    "cm": ("centimetre", "length"),
    "mm": ("millimetre", "length"),
    "box": ("box", "package"),
    "pack": ("pack", "package"),
    "set": ("set", "package"),
    "roll": ("roll", "package"),
}

_RELATIONSHIP_EVIDENCE = {
    UomRelationship.SAME_UOM: ("UOM_MATCH", 0.0, MappingQuality.CONSISTENT),
    UomRelationship.CONVERTIBLE_SAME_DIMENSION: (
        "UOM_CONVERTIBLE", 3.0, MappingQuality.UNKNOWN,
    ),
    UomRelationship.DIFFERENT_DIMENSION_OR_BASIS: (
        "UOM_DIFFERENT_BASIS", 20.0, MappingQuality.POSSIBLE_MAPPING_ERROR,
    ),
    UomRelationship.MISSING_OR_WILDCARD: (
        "UOM_MISSING_OR_WILDCARD", 8.0, MappingQuality.UNKNOWN,
    ),
    UomRelationship.MALFORMED_OR_UNKNOWN: (
        "UOM_MALFORMED_OR_UNKNOWN", 12.0, MappingQuality.UNKNOWN,
    ),
}


def _normalized(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
    return "" if text in {"nan", "nat"} else text


def classify_uom_relationship(left, right) -> UomEvidence:
    left_value = _normalized(left)
    right_value = _normalized(right)
    if left_value in _MISSING_OR_WILDCARD or right_value in _MISSING_OR_WILDCARD:
        relationship = UomRelationship.MISSING_OR_WILDCARD
    else:
        left_unit = _ALIASES.get(left_value)
        right_unit = _ALIASES.get(right_value)
        if left_unit is None or right_unit is None:
            relationship = UomRelationship.MALFORMED_OR_UNKNOWN
        elif left_unit[0] == right_unit[0]:
            relationship = UomRelationship.SAME_UOM
        elif left_unit[1] == right_unit[1]:
            relationship = UomRelationship.CONVERTIBLE_SAME_DIMENSION
        else:
            relationship = UomRelationship.DIFFERENT_DIMENSION_OR_BASIS
    reason_code, penalty, mapping_quality = _RELATIONSHIP_EVIDENCE[relationship]
    return UomEvidence(relationship, reason_code, penalty, mapping_quality)
