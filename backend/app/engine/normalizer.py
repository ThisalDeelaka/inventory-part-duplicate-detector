import re
from functools import lru_cache
from typing import Any

from app.core.constants import CRITICAL_MODIFIERS
from app.engine.domain_dictionary import expand_domain_tokens, normalize_description_with_dictionary, normalize_part_no_with_dictionary

SPELLING = {"decicated": "desiccated", "decicatted": "desiccated"}
ABBREVIATIONS = {
    "piece": "pcs", "pieces": "pcs", "pcs": "pcs",
    "ss": "stainless steel", "mcb": "miniature circuit breaker",
    "cu": "copper", "filtration": "filter", "filtering": "filter",
    "amp": "amp", "amps": "amp", "a": "amp",
}
UNITS = {"mm", "cm", "m", "kg", "g", "l", "ml", "v", "volt", "amp", "ph"}


@lru_cache(maxsize=100_000)
def normalize_description(text: Any) -> str:
    if text is None:
        return ""
    value = str(text).strip().lower()
    if value in {"", "nan", "none"}:
        return ""
    value = re.sub(r"\bm\s*[.]\s*c\s*[.]\s*b\b", "mcb", value)
    value = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", value)
    value = re.sub(r"[^a-z0-9.]+", " ", value)
    value = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", value)
    words = []
    for word in value.split():
        word = SPELLING.get(word, word)
        replacement = ABBREVIATIONS.get(word, word)
        words.extend(replacement.split())
    return expand_domain_tokens(" ".join(words))


@lru_cache(maxsize=100_000)
def extract_technical_tokens(text: Any) -> dict:
    normalized = normalize_description(text)
    words = normalized.split()
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", normalized)
    measurements = []
    for index, word in enumerate(words[:-1]):
        if re.fullmatch(r"\d+(?:\.\d+)?", word) and words[index + 1] in UNITS:
            measurements.append(f"{word}{words[index + 1]}")
    dimensions = re.findall(r"\b\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)?\b", normalized)
    modifiers = sorted(set(words) & CRITICAL_MODIFIERS)
    return {
        "numbers": sorted(set(numbers)),
        "measurements": sorted(set(measurements)),
        "dimensions": dimensions,
        "modifiers": modifiers,
        "units": sorted(set(words) & UNITS),
    }
