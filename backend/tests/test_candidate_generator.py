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


def test_primary_blocking_is_case_insensitive_for_selected_fields():
    df = pd.DataFrame([
        {"PART_NO": "KM-FM", "DESCRIPTION": "KM Fan Module", "CONTRACT": "K-MRO", "UNIT_MEAS": "pcs"},
        {"PART_NO": "KM/FANMODULE", "DESCRIPTION": "KM Fan Module", "CONTRACT": "K-MRO", "UNIT_MEAS": "PCS"},
    ])

    pairs = generate_candidate_pairs(df, ["CONTRACT", "UNIT_MEAS"])

    assert len(pairs) == 1
    assert {pairs[0]["record_a"]["PART_NO"], pairs[0]["record_b"]["PART_NO"]} == {"KM-FM", "KM/FANMODULE"}


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


def test_secondary_root_blocking_recovers_variant_part_numbers():
    df = pd.DataFrame([
        {"PART_NO": "KM-FM", "DESCRIPTION": "KM Fan Module", "CONTRACT": "SITE-A", "UNIT_MEAS": "EA"},
        {"PART_NO": "KM/FANMODULE", "DESCRIPTION": "KM Fan Module", "CONTRACT": "SITE-B", "UNIT_MEAS": "EA"},
    ])

    result = generate_candidate_pairs(df, [], debug_mode=True)

    assert len(result["pairs"]) == 1
    assert result["diagnostics"]["candidate_pair_count"] == 1
    assert any(row["block_sources"] for row in result["diagnostics"]["rows"])


def test_ranked_quota_keeps_pairs_from_a_small_block_when_large_block_exceeds_cap():
    large_block = [
        {"PART_NO": f"LARGE-{index}", "DESCRIPTION": f"large item {index}", "CONTRACT": "LARGE", "UNIT_MEAS": "PCS"}
        for index in range(201)
    ]
    small_block = [
        {"PART_NO": f"SMALL-{index}", "DESCRIPTION": f"small item {index}", "CONTRACT": "SMALL", "UNIT_MEAS": "PCS"}
        for index in range(4)
    ]

    pairs = generate_candidate_pairs(pd.DataFrame(large_block + small_block), ["CONTRACT", "UNIT_MEAS"])

    small_pairs = [pair for pair in pairs if pair["record_a"]["CONTRACT"] == "SMALL"]
    assert len(pairs) == 20_000
    assert len(small_pairs) >= 5
