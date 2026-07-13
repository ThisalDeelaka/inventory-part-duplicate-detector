import pandas as pd

from app.engine.candidate_generator import generate_candidate_pairs


def frame():
    return pd.DataFrame([
        {"PART_NO":"A","DESCRIPTION":"MCB30A","CONTRACT":"S1","UNIT_MEAS":"PCS"},
        {"PART_NO":"B","DESCRIPTION":"MCB 30 A","CONTRACT":"S1","UNIT_MEAS":"PCS"},
        {"PART_NO":"C","DESCRIPTION":"MCB 30 A","CONTRACT":"S2","UNIT_MEAS":"PCS"},
    ])


def test_same_site_and_uom_grouping():
    pairs = generate_candidate_pairs(frame(), ["CONTRACT", "UNIT_MEAS"])
    assert len(pairs) == 1
    assert set(pairs[0]["matched_fields"]) == {"CONTRACT", "UNIT_MEAS"}


def test_missing_field_warns_without_crash():
    pairs = generate_candidate_pairs(frame(), ["MISSING"])
    assert pairs
    assert pairs[0]["warnings"][0]["warning_type"] == "MISSING_SELECTED_FIELD"


def test_high_null_selected_field_is_warned_and_not_used_for_blocking():
    df = frame()
    df["EMPTY_CLASSIFICATION"] = ""
    pairs = generate_candidate_pairs(df, ["CONTRACT", "EMPTY_CLASSIFICATION"])
    assert len(pairs) == 1
    assert any(w["warning_type"] == "HIGH_NULL_FIELD" for w in pairs[0]["warnings"])


def test_no_self_or_reverse_pairs():
    pairs = generate_candidate_pairs(frame(), ["UNIT_MEAS"])
    keys = {(p["record_a"]["PART_NO"], p["record_b"]["PART_NO"]) for p in pairs}
    assert len(keys) == 3
    assert all(a != b for a, b in keys)
    assert not any((b, a) in keys for a, b in keys)


def test_same_part_number_across_sites_is_not_candidate_pair():
    df = pd.DataFrame([
        {"PART_NO": "T-100", "DESCRIPTION": "T-100", "CONTRACT": "HWHSP", "UNIT_MEAS": "PCS"},
        {"PART_NO": "T-100", "DESCRIPTION": "T-100", "CONTRACT": "B", "UNIT_MEAS": "PCS"},
        {"PART_NO": "T-101", "DESCRIPTION": "T-100", "CONTRACT": "B", "UNIT_MEAS": "PCS"},
    ])

    pairs = generate_candidate_pairs(df, ["UNIT_MEAS"])
    keys = {(p["record_a"]["PART_NO"], p["record_b"]["PART_NO"]) for p in pairs}

    assert ("T-100", "T-100") not in keys


def test_domain_synonym_pair_is_generated_when_selected_fields_match():
    df = pd.DataFrame([
        {"PART_NO": "DEC CO1", "DESCRIPTION": "Decicated Coconut type 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "DEC C01", "DESCRIPTION": "Dec Coco 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
    ])

    pairs = generate_candidate_pairs(df, ["CONTRACT", "UNIT_MEAS"])

    assert len(pairs) == 1
    assert pairs[0]["record_a"]["PART_NO"] == "DEC CO1"
    assert pairs[0]["record_b"]["PART_NO"] == "DEC C01"
