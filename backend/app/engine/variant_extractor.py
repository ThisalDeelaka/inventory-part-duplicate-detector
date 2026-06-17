import re

from app.engine.normalizer import normalize_description


FILTER_FUNCTION = {"air", "fuel", "oil", "water", "hydraulic"}
COLOR = {"red", "blue", "green", "black", "white", "yellow"}
SIZE_PHRASES = {
    "extra small": "extra small",
    "xs": "extra small",
    "small": "small",
    "medium": "medium",
    "large": "large",
    "xl": "extra large",
    "extra large": "extra large",
}
SENSOR_TYPE = {"temperature", "pressure", "flow", "level"}
SIDE = {"left", "right", "front", "rear"}

VARIANT_GROUP_LABELS = {
    "FILTER_FUNCTION": "critical function",
    "COLOR": "color",
    "SIZE": "size",
    "TYPE_OR_GRADE": "type",
    "ELECTRICAL_RATING": "ampere rating",
    "DIMENSION": "dimension",
    "SENSOR_TYPE": "sensor type",
    "SIDE": "side",
}


def _words(text: str) -> set[str]:
    return set(text.split())


def _find_size(normalized: str) -> list[str]:
    found = []
    protected = normalized
    for phrase in ("extra small", "extra large"):
        if re.search(rf"\b{re.escape(phrase)}\b", protected):
            found.append(SIZE_PHRASES[phrase])
            protected = re.sub(rf"\b{re.escape(phrase)}\b", " ", protected)
    for token in ("xs", "xl", "small", "medium", "large"):
        if re.search(rf"\b{re.escape(token)}\b", protected):
            found.append(SIZE_PHRASES[token])
    return sorted(set(found))


def _find_type_or_grade(normalized: str) -> list[str]:
    matches = re.findall(r"\b(?:type|grade)\s+[a-z0-9]+\b", normalized)
    return sorted(set(matches))


def _find_electrical(raw: str, normalized: str) -> list[str]:
    values = set()
    for source in (raw, normalized):
        for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*a\b", source, flags=re.IGNORECASE):
            values.add(f"{match.upper()}A")
        for match in re.findall(r"\b(\d+(?:\.\d+)?)(a)\b", source, flags=re.IGNORECASE):
            values.add(f"{match[0].upper()}A")
        for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*v\b", source, flags=re.IGNORECASE):
            values.add(f"{match.upper()}V")
        for match in re.findall(r"\b(\d+(?:\.\d+)?)(v)\b", source, flags=re.IGNORECASE):
            values.add(f"{match[0].upper()}V")
    for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*amp\b", normalized):
        values.add(f"{match.upper()}A")
    for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*volt\b", normalized):
        values.add(f"{match.upper()}V")
    return sorted(values)


def _find_dimensions(raw: str, normalized: str) -> list[str]:
    values = set()
    for source in (raw, normalized):
        for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*mm\b", source, flags=re.IGNORECASE):
            values.add(f"{match.upper()}MM")
    return sorted(values)


def extract_variant_attributes(description) -> dict[str, list[str]]:
    raw = "" if description is None else str(description).lower()
    normalized = normalize_description(description)
    words = _words(normalized)
    return {
        "FILTER_FUNCTION": sorted(words & FILTER_FUNCTION),
        "COLOR": sorted(words & COLOR),
        "SIZE": _find_size(normalized),
        "TYPE_OR_GRADE": _find_type_or_grade(normalized),
        "ELECTRICAL_RATING": _find_electrical(raw, normalized),
        "DIMENSION": _find_dimensions(raw, normalized),
        "SENSOR_TYPE": sorted(words & SENSOR_TYPE),
        "SIDE": sorted(words & SIDE),
    }


def find_critical_mismatches(attributes_a: dict, attributes_b: dict) -> list[dict]:
    mismatches = []
    for group, label in VARIANT_GROUP_LABELS.items():
        values_a = set(attributes_a.get(group, []))
        values_b = set(attributes_b.get(group, []))
        if values_a and values_b and values_a != values_b:
            mismatches.append({
                "group": group,
                "label": label,
                "values_a": sorted(values_a),
                "values_b": sorted(values_b),
            })
    return mismatches
