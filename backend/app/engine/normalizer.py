import re
from functools import lru_cache
from typing import Any

from app.core.constants import CRITICAL_MODIFIERS


DOMAIN_ABBREVIATIONS = {
    "dec": "desiccated",
    "desicated": "desiccated",
    "decicated": "desiccated",
    "decicatted": "desiccated",
    "coco": "coconut",
    "co": "coconut",
    "c01": "type 1",
    "co1": "type 1",
    "c02": "type 2",
    "co2": "type 2",
    "flt": "filter",
    "filt": "filter",
    "gen": "generator",
    "hvac": "hvac",
    "ss": "stainless steel",
    "stl": "steel",
    "bat": "battery",
    "temp": "temperature",
    "press": "pressure",
    "elec": "electrical",
    "hyd": "hydraulic",
    "pneu": "pneumatic",
}

UNITS = {"mm", "cm", "m", "kg", "g", "l", "ml", "v", "volt", "a", "amp", "ph"}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return "" if text in {"", "nan", "none"} else text


@lru_cache(maxsize=100_000)
def normalize_text(text: Any) -> str:
    value = _stringify(text)
    if not value:
        return ""
    value = re.sub(r"\bm\s*[.]\s*c\s*[.]\s*b\b", "mcb", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\b([a-z]+)(\d+(?:a|v|mm|cm|kg|g|l|ml|ph))\b", r"\1 \2", value)
    value = re.sub(r"\b(\d+)(mm|cm|kg|g|l|ml|v|ph|amp)\b", r"\1\2", value)
    value = re.sub(r"\b(\d+)\s+(a)\b", r"\1a", value)
    return re.sub(r"\s+", " ", value).strip()


def tokenize_normalized_text(text: Any) -> list[str]:
    normalized = normalize_text(text)
    return normalized.split() if normalized else []


@lru_cache(maxsize=100_000)
def expand_domain_abbreviations(text: Any) -> str:
    tokens = tokenize_normalized_text(text)
    words = []
    for token in tokens:
        replacement = DOMAIN_ABBREVIATIONS.get(token, token)
        words.extend(replacement.split())

    # ERP shorthand often uses "Dec Coco 1" to mean "desiccated coconut type 1".
    if "coconut" in words:
        expanded = []
        for index, word in enumerate(words):
            if word.isdigit() and index > 0 and words[index - 1] == "coconut":
                expanded.extend(["type", word])
            else:
                expanded.append(word)
        words = expanded
    return " ".join(words)


@lru_cache(maxsize=100_000)
def normalize_description(description: Any) -> str:
    return expand_domain_abbreviations(description)


@lru_cache(maxsize=100_000)
def normalize_part_no(part_no: Any) -> str:
    return expand_domain_abbreviations(part_no)


# Compatibility alias used by the existing app while the engine is redesigned.
normalize_part_no_with_dictionary = normalize_part_no


@lru_cache(maxsize=100_000)
def extract_technical_tokens(text: Any) -> dict:
    normalized = normalize_description(text)
    words = normalized.split()
    numbers = []
    measurements = []
    for word in words:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)(mm|cm|kg|g|l|ml|v|ph|a|amp)", word)
        if match:
            number, unit = match.groups()
            canonical_unit = "amp" if unit in {"a", "amp"} else unit
            numbers.append(number)
            measurements.append(f"{number}{canonical_unit}")
        elif re.fullmatch(r"\d+(?:\.\d+)?", word):
            numbers.append(word)
    dimensions = re.findall(r"\b\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)?\b", normalized)
    modifiers = sorted(set(words) & CRITICAL_MODIFIERS)
    units = sorted({re.sub(r"^\d+(?:\.\d+)?", "", word) for word in words if re.fullmatch(r"\d+(?:\.\d+)?[a-z]+", word)} | (set(words) & UNITS))
    return {
        "numbers": sorted(set(numbers)),
        "measurements": sorted(set(measurements)),
        "dimensions": dimensions,
        "modifiers": modifiers,
        "units": units,
    }
