from itertools import combinations
from collections import defaultdict
from functools import lru_cache
import re

import pandas as pd
from rapidfuzz import fuzz

from app.engine.normalizer import normalize_description, normalize_part_no_with_dictionary

MAX_CANDIDATE_PAIRS = 20_000
MIN_CANDIDATE_PAIRS_PER_BLOCK = 5
PRELIMINARY_RANKING_SIGNAL = "TOKEN_SET_RATIO"

# TODO: This synchronous-request safety limit is only mitigated by ranked, per-block selection.
# Add background/batch scan processing when production volumes exceed what fits comfortably in
# MAX_CANDIDATE_PAIRS ranked candidates.


def _clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _tokenize(value) -> list[str]:
    text = normalize_part_no_with_dictionary(value)
    if not text:
        return []
    return re.findall(r"[a-z0-9]+", text.lower())


def _part_root_keys(value) -> list[str]:
    tokens = _tokenize(value)
    if not tokens:
        return []
    keys = [tokens[0]]
    if len(tokens) >= 2:
        keys.append(" ".join(tokens[:2]))
    collapsed = "".join(tokens)
    if collapsed and collapsed not in keys:
        keys.append(collapsed)
    return keys


def _description_root_keys(value) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", normalize_description(value).lower())
    if not tokens:
        return []
    keys = [tokens[0]]
    if len(tokens) >= 2:
        keys.append(" ".join(tokens[:2]))
    collapsed = "".join(tokens)
    if collapsed and collapsed not in keys:
        keys.append(collapsed)
    return keys


def _pair(a, b, selected_fields, warnings):
    matched, mismatched = [], []
    for field in selected_fields:
        if field not in a or field not in b:
            continue
        av, bv = a.get(field), b.get(field)
        if pd.isna(av) or pd.isna(bv) or str(av).strip() == "" or str(bv).strip() == "":
            continue
        (matched if str(av).strip().lower() == str(bv).strip().lower() else mismatched).append(field)
    return {"record_a": a, "record_b": b, "matched_fields": matched, "mismatched_fields": mismatched, "warnings": warnings}


def _same_part_number(a, b):
    part_a = str(a.get("PART_NO", "")).strip().lower()
    part_b = str(b.get("PART_NO", "")).strip().lower()
    return bool(part_a and part_b and part_a == part_b)


@lru_cache(maxsize=100_000)
def _normalized_description_for_ranking(value: str) -> str:
    return normalize_description(value)


@lru_cache(maxsize=100_000)
def _token_set_ratio(normalized_a: str, normalized_b: str) -> float:
    if not normalized_a or not normalized_b:
        return 0.0
    return float(fuzz.token_set_ratio(normalized_a, normalized_b))


def _preliminary_score(record_a, record_b) -> float:
    if PRELIMINARY_RANKING_SIGNAL != "TOKEN_SET_RATIO":
        raise ValueError(f"Unsupported preliminary ranking signal: {PRELIMINARY_RANKING_SIGNAL}")
    description_a = _normalized_description_for_ranking(_clean_text(record_a.get("DESCRIPTION")))
    description_b = _normalized_description_for_ranking(_clean_text(record_b.get("DESCRIPTION")))
    return _token_set_ratio(description_a, description_b)


def _ranked_truncate(candidate_entries: list[dict]) -> list[dict]:
    if len(candidate_entries) <= MAX_CANDIDATE_PAIRS:
        return candidate_entries

    by_block = defaultdict(list)
    for entry in candidate_entries:
        by_block[entry["block_order"]].append(entry)

    def rank_key(entry):
        return (-entry["preliminary_score"], entry["block_order"], entry["pair_order"])

    floor_count = min(MIN_CANDIDATE_PAIRS_PER_BLOCK, MAX_CANDIDATE_PAIRS // len(by_block))
    selected, selected_ids = [], set()
    for block_entries in by_block.values():
        for entry in sorted(block_entries, key=rank_key)[:floor_count]:
            selected.append(entry)
            selected_ids.add(id(entry))

    remaining_slots = MAX_CANDIDATE_PAIRS - len(selected)
    if remaining_slots > 0:
        remaining = (entry for entry in candidate_entries if id(entry) not in selected_ids)
        selected.extend(sorted(remaining, key=rank_key)[:remaining_slots])

    return selected


def _build_block_map(df: pd.DataFrame, selected_fields: list[str]):
    block_map = defaultdict(list)
    diagnostics_rows = []
    primary_fields = [field for field in selected_fields if field in df.columns]

    for idx, row in df.iterrows():
        row_blocks = []
        row_data = row.to_dict()

        primary_values = []
        for field in primary_fields:
            value = _clean_text(row_data.get(field))
            if value:
                primary_values.append((field, value.lower()))
        if primary_values:
            primary_key = tuple(primary_values)
            block_map[("primary", primary_key)].append(idx)
            row_blocks.append({"type": "primary", "key": str(primary_key), "fields": [field for field, _value in primary_values]})

        if not primary_values:
            part_keys = _part_root_keys(row_data.get("PART_NO"))
            for key in part_keys:
                block_map[("part_root", key)].append(idx)
            if part_keys:
                row_blocks.append({"type": "part_root", "key": ", ".join(part_keys)})

            desc_keys = _description_root_keys(row_data.get("DESCRIPTION"))
            for key in desc_keys:
                block_map[("description_root", key)].append(idx)
            if desc_keys:
                row_blocks.append({"type": "description_root", "key": ", ".join(desc_keys)})

        if not row_blocks:
            block_map[("fallback", f"row-{idx}")].append(idx)
            row_blocks.append({"type": "fallback", "key": f"row-{idx}"})

        diagnostics_rows.append({
            "index": int(idx),
            "part_no": _clean_text(row_data.get("PART_NO")),
            "description": _clean_text(row_data.get("DESCRIPTION")),
            "block_sources": row_blocks,
        })

    return block_map, diagnostics_rows, primary_fields


def generate_candidate_pairs(df: pd.DataFrame, selected_fields: list[str], debug_mode: bool = False):
    warnings = []
    for field in selected_fields:
        if field not in df.columns:
            warnings.append({"warning_type": "MISSING_SELECTED_FIELD", "message": f"Selected field {field} is unavailable and was ignored."})
        else:
            null_ratio = df[field].fillna("").astype(str).str.strip().eq("").mean()
            if null_ratio >= 0.5:
                warnings.append({"warning_type": "HIGH_NULL_FIELD", "message": f"Selected field {field} is {round(null_ratio * 100, 1)}% empty."})

    candidate_entries, seen = [], set()
    block_map, diagnostics_rows, primary_fields = _build_block_map(df, selected_fields)
    records = {idx: row.to_dict() for idx, row in df.iterrows()}

    for block_order, ((block_type, block_key), indexes) in enumerate(block_map.items()):
        if len(indexes) < 2:
            continue
        for pair_order, (idx_a, idx_b) in enumerate(combinations(indexes, 2)):
            key = tuple(sorted((int(idx_a), int(idx_b))))
            if key in seen:
                continue
            record_a, record_b = records[idx_a], records[idx_b]
            if _same_part_number(record_a, record_b):
                continue
            seen.add(key)
            candidate_entries.append({
                "idx_a": idx_a,
                "idx_b": idx_b,
                "block_order": block_order,
                "pair_order": pair_order,
                "preliminary_score": _preliminary_score(record_a, record_b),
            })

    raw_candidate_pair_count = len(candidate_entries)
    limit_reached = raw_candidate_pair_count > MAX_CANDIDATE_PAIRS
    if limit_reached:
        warnings.append({"warning_type": "PAIR_LIMIT_REACHED", "message": f"Candidate generation selected {MAX_CANDIDATE_PAIRS} ranked, quota-balanced pairs from {raw_candidate_pair_count} raw pairs. Use more selective business fields or a background-worker deployment for broader scans."})
    selected_entries = _ranked_truncate(candidate_entries)
    pairs = [
        _pair(records[entry["idx_a"]], records[entry["idx_b"]], selected_fields, warnings)
        for entry in selected_entries
    ]
    if not debug_mode:
        return pairs

    diagnostics = {
        "selected_fields": selected_fields,
        "primary_blocking_fields": primary_fields,
        "row_count": len(df),
        "candidate_pair_count": len(pairs),
        "raw_candidate_pair_count": raw_candidate_pair_count,
        "pair_limit_reached": limit_reached,
        "warnings": warnings,
        "rows": diagnostics_rows,
        "block_summary": [
            {"block_type": block_type, "block_key": str(block_key), "record_count": len(indexes)}
            for (block_type, block_key), indexes in block_map.items()
            if len(indexes) >= 2
        ],
    }
    return {"pairs": pairs, "diagnostics": diagnostics}
