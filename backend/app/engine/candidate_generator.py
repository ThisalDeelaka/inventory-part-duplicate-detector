from itertools import combinations

import pandas as pd

from app.engine.normalizer import normalize_description

MAX_CANDIDATE_PAIRS = 20_000


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


def generate_candidate_pairs(df: pd.DataFrame, selected_fields: list[str]):
    warnings = []
    available = []
    for field in selected_fields:
        if field not in df.columns:
            warnings.append({"warning_type": "MISSING_SELECTED_FIELD", "message": f"Selected field {field} is unavailable and was ignored."})
        else:
            null_ratio = df[field].fillna("").astype(str).str.strip().eq("").mean()
            if null_ratio >= 0.5:
                warnings.append({"warning_type": "HIGH_NULL_FIELD", "message": f"Selected field {field} is {round(null_ratio * 100, 1)}% empty."})
                continue
            available.append(field)

    pairs, seen = [], set()
    if available:
        usable = df.dropna(subset=available, how="any")
        group_key = available[0] if len(available) == 1 else available
        groups = (group for _, group in usable.groupby(group_key, dropna=False))
    else:
        blocks = {}
        for idx, row in df.iterrows():
            tokens = normalize_description(row.get("DESCRIPTION", "")).split()
            key = tokens[0] if tokens else f"empty-{idx}"
            blocks.setdefault(key, []).append(idx)
        groups = (df.loc[indexes] for indexes in blocks.values())

    limit_reached = False
    for group in groups:
        for idx_a, idx_b in combinations(group.index.tolist(), 2):
            key = tuple(sorted((int(idx_a), int(idx_b))))
            if key in seen:
                continue
            if _same_part_number(df.loc[idx_a], df.loc[idx_b]):
                continue
            seen.add(key)
            pairs.append(_pair(df.loc[idx_a].to_dict(), df.loc[idx_b].to_dict(), selected_fields, warnings))
            if len(pairs) >= MAX_CANDIDATE_PAIRS:
                warnings.append({"warning_type": "PAIR_LIMIT_REACHED", "message": f"Candidate generation stopped at the safety limit of {MAX_CANDIDATE_PAIRS} pairs. Use more selective business fields or a background-worker deployment for broader scans."})
                limit_reached = True
                break
        if limit_reached:
            break
    return pairs
