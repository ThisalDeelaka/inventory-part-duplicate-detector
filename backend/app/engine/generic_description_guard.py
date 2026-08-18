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
    "test",
    "sales",
    "component",
    "inventory",
}


def is_generic_description(description: str) -> bool:
    tokens = normalize_description(description).split()
    if not tokens or len(tokens) > 2:
        return False
    if all(token in GENERIC_TERMS for token in tokens):
        return True
    # A single alphabetic category/name carries no model, rating, dimension,
    # material, or other differentiating identity evidence.  Keep alphanumeric
    # model-like tokens (for example MCB30A) on the normal scorer path.
    return len(tokens) == 1 and tokens[0].isalpha()


def has_generic_specific_pair(description_a: str, description_b: str) -> bool:
    generic_a = is_generic_description(description_a)
    generic_b = is_generic_description(description_b)
    return generic_a != generic_b


def has_generic_description(description_a: str, description_b: str) -> bool:
    """Return true when either side is too generic to establish identity."""
    return is_generic_description(description_a) or is_generic_description(description_b)
