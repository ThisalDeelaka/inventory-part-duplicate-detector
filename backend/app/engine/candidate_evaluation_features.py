"""Immutable scan-local record features reused by candidate evaluation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.engine.application_context import extract_application_context
from app.engine.generic_description_guard import is_generic_description
from app.engine.normalizer import (
    extract_technical_tokens,
    normalize_description,
    normalize_part_no_with_dictionary,
)
from app.engine.variant_extractor import extract_variant_attributes


def _immutable_mapping(value: dict[str, list[str]]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((key, tuple(items)) for key, items in value.items())


@dataclass(frozen=True)
class CandidateEvaluationFeatures:
    """Deterministic record-local inputs; pair decisions remain outside this type."""

    record_ref_key: str
    normalized_description: str
    normalized_part_no: str
    site_context: str
    variant_attributes: tuple[tuple[str, tuple[str, ...]], ...]
    technical_tokens: tuple[tuple[str, tuple[str, ...]], ...]
    application_context: tuple[str, ...]
    generic_description: bool
    model_tokens: tuple[str, ...]

    def variant_mapping(self) -> dict[str, tuple[str, ...]]:
        return dict(self.variant_attributes)

    def variant_payload(self) -> dict[str, list[str]]:
        return {key: list(values) for key, values in self.variant_attributes}

    def technical_mapping(self) -> dict[str, tuple[str, ...]]:
        return dict(self.technical_tokens)


def build_candidate_evaluation_features(
    record: dict, *, record_ref_key: str = ""
) -> CandidateEvaluationFeatures:
    """Build one pure feature bundle without retaining mutable source records."""

    description = record.get("DESCRIPTION")
    part_no = record.get("PART_NO")
    normalized_description = normalize_description(description)
    model_tokens = tuple(sorted({
        token.casefold()
        for token in re.findall(
            r"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9-]{2,}\b",
            str(description or ""),
        )
    }))
    return CandidateEvaluationFeatures(
        record_ref_key=str(record_ref_key or "").strip(),
        normalized_description=normalized_description,
        normalized_part_no=normalize_part_no_with_dictionary(part_no),
        site_context=str(record.get("CONTRACT") or "").strip().casefold(),
        variant_attributes=_immutable_mapping(extract_variant_attributes(description)),
        technical_tokens=_immutable_mapping(extract_technical_tokens(description)),
        application_context=tuple(extract_application_context(part_no, description)),
        generic_description=is_generic_description(description),
        model_tokens=model_tokens,
    )
