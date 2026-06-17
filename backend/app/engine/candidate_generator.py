from collections import defaultdict
from itertools import combinations
from typing import Iterable

import pandas as pd

from app.engine.attribute_extractor import extract_attributes
from app.engine.models import CandidatePair, PartRecord


MAX_CANDIDATE_PAIRS = 20_000
SELECTED_FIELD_ALIASES = {
    "PART_TYPE": "TYPE_CODE",
    "INVENTORY_UOM": "UNIT_MEAS",
    "COMMODITY_GROUP_1": "PRIME_COMMODITY",
    "COMMODITY_GROUP_2": "SECOND_COMMODITY",
    "SAFETY_CODE": "HAZARD_CODE",
}
LOW_VALUE_TOKENS = {
    "type",
    "item",
    "part",
    "spare",
    "material",
    "can",
    "box",
    "bag",
    "pack",
    "roll",
}
BLOCK_ATTRIBUTES = (
    "product_class",
    "type_code",
    "rating",
    "color",
    "application_context",
    "function_or_media",
)


def _as_records(records) -> tuple[list[PartRecord], list[dict], bool]:
    if isinstance(records, pd.DataFrame):
        raw_rows = records.to_dict("records")
        part_records = [
            PartRecord(
                part_no="" if row.get("PART_NO") is None else str(row.get("PART_NO")),
                description="" if row.get("DESCRIPTION") is None else str(row.get("DESCRIPTION")),
                contract=None if row.get("CONTRACT") is None else str(row.get("CONTRACT")),
                raw=row,
            )
            for row in raw_rows
        ]
        return part_records, raw_rows, True

    part_records = []
    raw_rows = []
    for record in records or []:
        if isinstance(record, PartRecord):
            part_records.append(record)
            raw_rows.append(record.raw)
        else:
            raw = dict(record)
            part = PartRecord(
                part_no="" if raw.get("PART_NO") is None else str(raw.get("PART_NO")),
                description="" if raw.get("DESCRIPTION") is None else str(raw.get("DESCRIPTION")),
                contract=None if raw.get("CONTRACT") is None else str(raw.get("CONTRACT")),
                raw=raw,
            )
            part_records.append(part)
            raw_rows.append(raw)
    return part_records, raw_rows, False


def _field_value(record: PartRecord, field: str) -> str:
    value = record.raw.get(field)
    if value is None or pd.isna(value):
        return ""
    return str(value).strip().lower()


def _canonical_field(field: str) -> str:
    return SELECTED_FIELD_ALIASES.get(field, field)


def _selected_field_warnings(raw_rows: list[dict], selected_fields: list[str]) -> tuple[list[str], list[dict]]:
    warnings = []
    available = []
    columns = set().union(*(row.keys() for row in raw_rows)) if raw_rows else set()
    for field in selected_fields:
        canonical = _canonical_field(field)
        if canonical not in columns:
            warnings.append({
                "warning_type": "MISSING_SELECTED_FIELD",
                "message": f"Selected field {field} is unavailable and was ignored.",
            })
            continue
        values = [row.get(canonical) for row in raw_rows]
        empty_count = sum(1 for value in values if value is None or str(value).strip() == "")
        if values and empty_count / len(values) >= 0.5:
            warnings.append({
                "warning_type": "HIGH_NULL_FIELD",
                "message": f"Selected field {field} is {round(empty_count / len(values) * 100, 1)}% empty.",
            })
            continue
        available.append(canonical)
    return available, warnings


def _selected_fields_match(a: PartRecord, b: PartRecord, fields: list[str]) -> bool:
    for field in fields:
        value_a = _field_value(a, field)
        value_b = _field_value(b, field)
        if value_a and value_b and value_a != value_b:
            return False
    return True


def _same_part_number(a: PartRecord, b: PartRecord) -> bool:
    left = a.part_no.strip().lower()
    right = b.part_no.strip().lower()
    return bool(left and right and left == right)


def _same_contract(a: PartRecord, b: PartRecord) -> bool:
    left = _field_value(a, "CONTRACT")
    right = _field_value(b, "CONTRACT")
    return not left or not right or left == right


def _make_pair(
    a: PartRecord,
    b: PartRecord,
    selected_fields: list[str],
    warnings: list[dict],
    reasons: Iterable[str],
    matched_blocks: Iterable[str],
    as_dict: bool,
):
    matched, mismatched = [], []
    for field in selected_fields:
        value_a = _field_value(a, field)
        value_b = _field_value(b, field)
        if not value_a or not value_b:
            continue
        (matched if value_a == value_b else mismatched).append(field)

    if as_dict:
        return {
            "record_a": a.raw,
            "record_b": b.raw,
            "matched_fields": matched,
            "mismatched_fields": mismatched,
            "warnings": warnings,
            "candidate_reasons": sorted(set(reasons)),
            "matched_blocks": sorted(set(matched_blocks)),
            "normalized_part_no_a": extract_attributes(a.part_no, a.description).normalized_part_no,
            "normalized_part_no_b": extract_attributes(b.part_no, b.description).normalized_part_no,
            "normalized_description_a": extract_attributes(a.part_no, a.description).normalized_description,
            "normalized_description_b": extract_attributes(b.part_no, b.description).normalized_description,
        }

    pair = CandidatePair(
        record_a=a,
        record_b=b,
        matched_fields=matched,
        mismatched_fields=mismatched,
        blocking_reason=", ".join(sorted(set(reasons))),
    )
    pair.candidate_reasons = sorted(set(reasons))
    pair.matched_blocks = sorted(set(matched_blocks))
    return pair


def _add_block(blocks: dict[str, list[int]], key: str, index: int) -> None:
    if key:
        blocks[key].append(index)


def _important_tokens(tokens: Iterable[str]) -> list[str]:
    return [
        token
        for token in tokens
        if len(token) >= 3 and token not in LOW_VALUE_TOKENS
    ]


def _build_blocks(records: list[PartRecord], selected_fields: list[str]) -> dict[str, list[int]]:
    blocks = defaultdict(list)
    for index, record in enumerate(records):
        attrs = extract_attributes(
            record.part_no,
            record.description,
            record.raw.get("MASTER_PART_DESCRIPTION"),
        )

        if selected_fields:
            selected_values = tuple(_field_value(record, field) for field in selected_fields)
            if all(selected_values):
                _add_block(blocks, f"selected:{selected_values}", index)

        for token in _important_tokens(attrs.normalized_description.split()):
            _add_block(blocks, f"desc:{token}", index)

        for token in _important_tokens(attrs.normalized_part_no.split()):
            _add_block(blocks, f"part:{token}", index)

        for attribute in BLOCK_ATTRIBUTES:
            for value in getattr(attrs, attribute):
                _add_block(blocks, f"attr:{attribute}:{value}", index)
    return blocks


def generate_candidate_pairs(
    records,
    selected_fields: list[str] | None = None,
    cross_site: bool = False,
) -> list:
    part_records, raw_rows, as_dict = _as_records(records)
    selected_fields = selected_fields or []
    selected_fields, warnings = _selected_field_warnings(raw_rows, selected_fields)
    blocks = _build_blocks(part_records, selected_fields)

    pairs = {}
    for block_name, indexes in blocks.items():
        if len(indexes) < 2:
            continue
        for idx_a, idx_b in combinations(sorted(set(indexes)), 2):
            a, b = part_records[idx_a], part_records[idx_b]
            if _same_part_number(a, b):
                continue
            if not cross_site and not _same_contract(a, b):
                continue
            if selected_fields and not _selected_fields_match(a, b, selected_fields):
                continue

            key = (idx_a, idx_b)
            entry = pairs.setdefault(key, {"reasons": set(), "blocks": set()})
            if block_name.startswith("selected:"):
                entry["reasons"].add("selected_fields_match")
            elif block_name.startswith("desc:"):
                entry["reasons"].add("normalized_description_token_match")
            elif block_name.startswith("part:"):
                entry["reasons"].add("normalized_part_number_token_match")
            elif block_name.startswith("attr:"):
                entry["reasons"].add("extracted_attribute_match")
            entry["blocks"].add(block_name)

            if len(pairs) >= MAX_CANDIDATE_PAIRS:
                warnings.append({
                    "warning_type": "PAIR_LIMIT_REACHED",
                    "message": f"Candidate generation stopped at the safety limit of {MAX_CANDIDATE_PAIRS} pairs.",
                })
                break
        if len(pairs) >= MAX_CANDIDATE_PAIRS:
            break

    output = []
    for idx_a, idx_b in sorted(pairs):
        entry = pairs[(idx_a, idx_b)]
        output.append(_make_pair(
            part_records[idx_a],
            part_records[idx_b],
            selected_fields,
            warnings,
            entry["reasons"],
            entry["blocks"],
            as_dict,
        ))
    return output
