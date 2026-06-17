import re
from dataclasses import asdict
from typing import Iterable

from app.engine.application_context import extract_application_context
from app.engine.generic_description_guard import is_generic_description
from app.engine.models import ExtractedAttributes, ItemProfile
from app.engine.normalizer import (
    extract_technical_tokens,
    normalize_description,
    normalize_part_no,
)
from app.engine.variant_extractor import extract_variant_attributes


PRODUCT_CLASSES = {
    "filter",
    "paint",
    "mcb",
    "coconut",
    "label",
    "labels",
    "sensor",
    "pipe",
    "battery",
    "shoe",
    "bicycle",
}
APPLICATION_CONTEXTS = {
    "generator",
    "hvac",
    "electrical",
    "hydraulic",
    "pneumatic",
    "vehicle",
    "pump",
    "compressor",
}
FUNCTION_OR_MEDIA = {
    "fuel",
    "air",
    "oil",
    "warning",
    "temperature",
    "pressure",
}
COLORS = {"red", "blue", "black", "white", "green", "yellow", "orange", "grey", "gray"}
SIZES = {"xs", "small", "medium", "large", "xl", "extra small", "extra large"}
MATERIALS = {"stainless steel", "steel", "plastic", "rubber", "copper", "aluminium", "aluminum"}
PACKAGING = {"can", "box", "bottle", "bag", "roll", "pack"}
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


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(rf"\b{re.escape(phrase)}\b", text))


def _collect_terms(tokens: set[str], normalized_text: str, vocabulary: set[str]) -> list[str]:
    found = set()
    for term in vocabulary:
        if " " in term:
            if _contains_phrase(normalized_text, term):
                found.add(term)
        elif term in tokens:
            found.add(term)
    return _unique(found)


def _extract_type_codes(normalized_text: str) -> list[str]:
    return _unique(re.findall(r"\btype\s+[a-z0-9]+\b", normalized_text))


def _extract_ratings(tokens: set[str]) -> list[str]:
    return _unique(
        token
        for token in tokens
        if re.fullmatch(r"\d+(?:\.\d+)?(?:a|v|mm|kg|g)", token)
    )


def _extract_volumes(tokens: set[str]) -> list[str]:
    return _unique(
        token
        for token in tokens
        if re.fullmatch(r"\d+(?:\.\d+)?(?:l|ml)", token)
    )


def _normalized_parts(part_no: str, description: str, master_description: str | None) -> tuple[str, str, str]:
    normalized_part_no = normalize_part_no(part_no)
    descriptions = [
        normalize_description(description),
        normalize_description(master_description),
    ]
    normalized_description = " ".join(part for part in descriptions if part)
    normalized_text = " ".join(part for part in (normalized_part_no, normalized_description) if part)
    return normalized_part_no, normalized_description, normalized_text


def extract_attributes(
    part_no: str,
    description: str,
    master_description: str | None = None,
) -> ExtractedAttributes:
    normalized_part_no, normalized_description, normalized_text = _normalized_parts(
        part_no,
        description,
        master_description,
    )
    raw_tokens = normalized_text.split()
    token_set = set(raw_tokens)
    application_context = _unique(
        set(extract_application_context(part_no, description))
        | set(_collect_terms(token_set, normalized_text, APPLICATION_CONTEXTS))
    )
    generic_terms = set(_collect_terms(token_set, normalized_text, GENERIC_TERMS))
    if "labels" in generic_terms:
        generic_terms.add("label")

    return ExtractedAttributes(
        normalized_part_no=normalized_part_no,
        normalized_description=normalized_description,
        normalized_text=normalized_text,
        product_class=_collect_terms(token_set, normalized_text, PRODUCT_CLASSES),
        application_context=application_context,
        function_or_media=_collect_terms(token_set, normalized_text, FUNCTION_OR_MEDIA),
        color=_collect_terms(token_set, normalized_text, COLORS),
        rating=_extract_ratings(token_set),
        size=_collect_terms(token_set, normalized_text, SIZES),
        volume=_extract_volumes(token_set),
        type_code=_extract_type_codes(normalized_text),
        material=_collect_terms(token_set, normalized_text, MATERIALS),
        packaging=_collect_terms(token_set, normalized_text, PACKAGING),
        generic_terms=_unique(generic_terms),
        raw_tokens=raw_tokens,
        technical_tokens=extract_technical_tokens(normalized_text),
        variant_attributes=extract_variant_attributes(normalized_text),
        is_generic_description=is_generic_description(description),
    )


def profile_record(record: dict) -> ItemProfile:
    part_no = "" if record.get("PART_NO") is None else str(record.get("PART_NO"))
    description = "" if record.get("DESCRIPTION") is None else str(record.get("DESCRIPTION"))
    master_description = record.get("MASTER_PART_DESCRIPTION")
    attributes = extract_attributes(part_no, description, master_description)
    return ItemProfile(
        raw=record,
        part_no=part_no,
        description=description,
        normalized_part_no=attributes.normalized_part_no,
        normalized_description=attributes.normalized_description,
        attributes={
            "variants": attributes.variant_attributes,
            "technical": attributes.technical_tokens,
            "extracted": asdict(attributes),
        },
        application_context=attributes.application_context,
        is_generic_description=attributes.is_generic_description,
    )
