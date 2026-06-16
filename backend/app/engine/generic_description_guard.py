from app.engine.normalizer import normalize_description


GENERIC_TERMS = {
    "label",
    "labels",
    "filter",
    "pipe",
    "bolt",
    "nut",
    "screw",
    "washer",
    "cable",
    "sensor",
    "paint",
    "oil",
    "material",
    "item",
    "part",
    "spare",
    "tool",
    "kit",
}


def is_generic_description(description: str) -> bool:
    tokens = normalize_description(description).split()
    if not tokens or len(tokens) > 2:
        return False
    return all(token in GENERIC_TERMS for token in tokens)


def has_generic_specific_pair(description_a: str, description_b: str) -> bool:
    generic_a = is_generic_description(description_a)
    generic_b = is_generic_description(description_b)
    return generic_a != generic_b
