from app.engine.application_context import extract_application_context
from app.engine.generic_description_guard import is_generic_description
from app.engine.models import ItemProfile
from app.engine.normalizer import (
    extract_technical_tokens,
    normalize_description,
    normalize_part_no_with_dictionary,
)
from app.engine.variant_extractor import extract_variant_attributes


def extract_attributes(part_no, description) -> dict:
    variants = extract_variant_attributes(description)
    technical = extract_technical_tokens(description)
    return {
        "variants": variants,
        "technical": technical,
    }


def profile_record(record: dict) -> ItemProfile:
    part_no = "" if record.get("PART_NO") is None else str(record.get("PART_NO"))
    description = "" if record.get("DESCRIPTION") is None else str(record.get("DESCRIPTION"))
    return ItemProfile(
        raw=record,
        part_no=part_no,
        description=description,
        normalized_part_no=normalize_part_no_with_dictionary(part_no),
        normalized_description=normalize_description(description),
        attributes=extract_attributes(part_no, description),
        application_context=extract_application_context(part_no, description),
        is_generic_description=is_generic_description(description),
    )

