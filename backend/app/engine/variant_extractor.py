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
CONNECTIVITY = {"wired", "wireless"}
ENVIRONMENT = {"indoor", "outdoor"}
OPERATION_MODE = {"manual", "automatic"}

VARIANT_GROUP_LABELS = {
    "FILTER_FUNCTION": "critical function",
    "COLOR": "color",
    "SIZE": "size",
    "TYPE_OR_GRADE": "type",
    "ELECTRICAL_RATING": "ampere rating",
    "DIMENSION": "dimension",
    "SENSOR_TYPE": "sensor type",
    "SIDE": "side",
    "CONNECTIVITY": "connectivity",
    "ENVIRONMENT": "environment",
    "OPERATION_MODE": "operation mode",
}

ONE_SIDED_QUALIFIER_GROUPS = {"CONNECTIVITY", "ENVIRONMENT", "OPERATION_MODE"}
ORDINAL_WORDS = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "fifth": "5",
    "sixth": "6",
    "seventh": "7",
    "eighth": "8",
    "ninth": "9",
    "tenth": "10",
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
    for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*a\b", raw, flags=re.IGNORECASE):
        values.add(f"{match.upper()}A")
    for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*amp\b", normalized):
        values.add(f"{match.upper()}A")
    for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*v\b", raw, flags=re.IGNORECASE):
        values.add(f"{match.upper()}V")
    for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*volt\b", normalized):
        values.add(f"{match.upper()}V")
    return sorted(values)


def _find_dimensions(raw: str, normalized: str) -> list[str]:
    values = set()
    for source in (raw, normalized):
        for match in re.findall(r"\b(\d+(?:\.\d+)?)\s*mm\b", source, flags=re.IGNORECASE):
            values.add(f"{match.upper()}MM")
    return sorted(values)


def _find_trailing_variant(description) -> tuple[list[str], list[str]]:
    raw = "" if description is None else str(description).strip().lower()
    numeric = re.match(r"^(.*?\S)[\s_-]+(\d+)(?:st|nd|rd|th)?$", raw)
    if numeric:
        base = normalize_description(numeric.group(1))
        return [str(int(numeric.group(2)))], [base] if base else []

    normalized = normalize_description(description)
    words = normalized.split()
    if len(words) >= 2 and words[-1] in ORDINAL_WORDS:
        return [ORDINAL_WORDS[words[-1]]], [" ".join(words[:-1])]
    return [], []


def extract_variant_attributes(description) -> dict[str, list[str]]:
    raw = "" if description is None else str(description).lower()
    normalized = normalize_description(description)
    words = _words(normalized)
    trailing_suffix, trailing_base = _find_trailing_variant(description)
    return {
        "FILTER_FUNCTION": sorted(words & FILTER_FUNCTION),
        "COLOR": sorted(words & COLOR),
        "SIZE": _find_size(normalized),
        "TYPE_OR_GRADE": _find_type_or_grade(normalized),
        "ELECTRICAL_RATING": _find_electrical(raw, normalized),
        "DIMENSION": _find_dimensions(raw, normalized),
        "SENSOR_TYPE": sorted(words & SENSOR_TYPE),
        "SIDE": sorted(words & SIDE),
        "CONNECTIVITY": sorted(words & CONNECTIVITY),
        "ENVIRONMENT": sorted(words & ENVIRONMENT),
        "OPERATION_MODE": sorted(words & OPERATION_MODE),
        "TRAILING_VARIANT_SUFFIX": trailing_suffix,
        "TRAILING_VARIANT_BASE": trailing_base,
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
    suffix_a = set(attributes_a.get("TRAILING_VARIANT_SUFFIX", []))
    suffix_b = set(attributes_b.get("TRAILING_VARIANT_SUFFIX", []))
    base_a = set(attributes_a.get("TRAILING_VARIANT_BASE", []))
    base_b = set(attributes_b.get("TRAILING_VARIANT_BASE", []))
    if suffix_a and suffix_b and suffix_a != suffix_b and base_a == base_b and base_a:
        mismatches.append({
            "group": "TRAILING_VARIANT_SUFFIX",
            "label": "trailing variant suffix",
            "values_a": sorted(suffix_a),
            "values_b": sorted(suffix_b),
        })
    return mismatches


def find_one_sided_qualifier(attributes_a: dict, attributes_b: dict) -> dict | None:
    """Find a defining qualifier present on only one side of a candidate pair."""
    for group in sorted(ONE_SIDED_QUALIFIER_GROUPS):
        values_a = set(attributes_a.get(group, []))
        values_b = set(attributes_b.get(group, []))
        if bool(values_a) != bool(values_b):
            return {
                "group": group,
                "label": VARIANT_GROUP_LABELS[group],
                "values_a": sorted(values_a),
                "values_b": sorted(values_b),
            }
    return None
