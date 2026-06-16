from app.engine.normalizer import normalize_description


def classify_item_family(description) -> str:
    words = set(normalize_description(description).split())
    normalized = " ".join(words)
    if "filter" in words:
        return "filters"
    if "paint" in words:
        return "paint items"
    if "coconut" in words:
        return "coconut items"
    if "sensor" in words:
        return "sensors"
    if "miniature" in words and "circuit" in words and "breaker" in words:
        return "MCB items"
    if "mcb" in words or "miniature circuit breaker" in normalized:
        return "MCB items"
    if "pipe" in words:
        return "pipe items"
    return "items"


def shared_family(description_a, description_b) -> str:
    family_a = classify_item_family(description_a)
    family_b = classify_item_family(description_b)
    return family_a if family_a == family_b else "items"
