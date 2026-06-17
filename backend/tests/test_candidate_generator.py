import pandas as pd

from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.models import PartRecord


def _keys(pairs):
    return {(p["record_a"]["PART_NO"], p["record_b"]["PART_NO"]) for p in pairs}


def _records():
    return [
        PartRecord(
            part_no="A",
            description="MCB30A",
            contract="S1",
            raw={"PART_NO": "A", "DESCRIPTION": "MCB30A", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        ),
        PartRecord(
            part_no="B",
            description="MCB 30 A",
            contract="S1",
            raw={"PART_NO": "B", "DESCRIPTION": "MCB 30 A", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        ),
        PartRecord(
            part_no="C",
            description="MCB 30 A",
            contract="S2",
            raw={"PART_NO": "C", "DESCRIPTION": "MCB 30 A", "CONTRACT": "S2", "UNIT_MEAS": "PCS"},
        ),
    ]


def test_domain_synonym_pair_is_generated_when_selected_fields_match():
    df = pd.DataFrame([
        {"PART_NO": "DEC CO1", "DESCRIPTION": "Decicated Coconut type 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "DEC C01", "DESCRIPTION": "Dec Coco 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
    ])

    pairs = generate_candidate_pairs(df, ["CONTRACT", "UNIT_MEAS"])

    assert _keys(pairs) == {("DEC CO1", "DEC C01")}
    assert "normalized_part_number_token_match" in pairs[0]["candidate_reasons"]


def test_same_site_matching_can_generate_candidates():
    pairs = generate_candidate_pairs(_records(), ["CONTRACT", "UNIT_MEAS"])

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.record_a.part_no == "A"
    assert pair.record_b.part_no == "B"
    assert set(pair.matched_fields) == {"CONTRACT", "UNIT_MEAS"}


def test_cross_site_disabled_excludes_different_contract_candidates():
    pairs = generate_candidate_pairs(_records(), ["UNIT_MEAS"], cross_site=False)

    assert {(pair.record_a.part_no, pair.record_b.part_no) for pair in pairs} == {("A", "B")}


def test_cross_site_enabled_allows_different_contract_candidates():
    pairs = generate_candidate_pairs(_records(), ["UNIT_MEAS"], cross_site=True)

    assert ("A", "C") in {(pair.record_a.part_no, pair.record_b.part_no) for pair in pairs}
    assert ("B", "C") in {(pair.record_a.part_no, pair.record_b.part_no) for pair in pairs}


def test_no_self_or_reverse_pairs():
    pairs = generate_candidate_pairs(_records(), ["UNIT_MEAS"], cross_site=True)
    keys = {(pair.record_a.part_no, pair.record_b.part_no) for pair in pairs}

    assert all(a != b for a, b in keys)
    assert not any((b, a) in keys for a, b in keys)


def test_missing_field_warns_without_crash():
    df = pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "MCB30A", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "B", "DESCRIPTION": "MCB 30A", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
    ])

    pairs = generate_candidate_pairs(df, ["MISSING"])

    assert pairs
    assert pairs[0]["warnings"][0]["warning_type"] == "MISSING_SELECTED_FIELD"


def test_high_null_selected_field_is_warned_and_not_used_for_blocking():
    df = pd.DataFrame([
        {"PART_NO": "A", "DESCRIPTION": "MCB30A", "CONTRACT": "S1", "EMPTY_CLASSIFICATION": ""},
        {"PART_NO": "B", "DESCRIPTION": "MCB 30A", "CONTRACT": "S1", "EMPTY_CLASSIFICATION": ""},
    ])

    pairs = generate_candidate_pairs(df, ["CONTRACT", "EMPTY_CLASSIFICATION"])

    assert len(pairs) == 1
    assert any(w["warning_type"] == "HIGH_NULL_FIELD" for w in pairs[0]["warnings"])


def test_same_part_number_is_not_candidate_pair():
    df = pd.DataFrame([
        {"PART_NO": "T-100", "DESCRIPTION": "T-100", "CONTRACT": "HWHSP", "UNIT_MEAS": "PCS"},
        {"PART_NO": "T-100", "DESCRIPTION": "T-100", "CONTRACT": "HWHSP", "UNIT_MEAS": "PCS"},
    ])

    assert generate_candidate_pairs(df, ["CONTRACT", "UNIT_MEAS"]) == []


def test_related_but_different_items_can_be_generated_for_later_guardrails():
    df = pd.DataFrame([
        {"PART_NO": "GEN-FUEL-FLT", "DESCRIPTION": "Generator Fuel Filter", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "GEN-AIR-FLT", "DESCRIPTION": "Generator Air Filter", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "PAINT-RED", "DESCRIPTION": "RED PAINT 1L CAN", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "PAINT-BLUE", "DESCRIPTION": "BLUE PAINT 1L CAN", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "MCB-20", "DESCRIPTION": "MCB 20A", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        {"PART_NO": "MCB-30", "DESCRIPTION": "MCB30A", "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
    ])

    pairs = generate_candidate_pairs(df, ["CONTRACT", "UNIT_MEAS"])
    keys = _keys(pairs)

    assert ("GEN-FUEL-FLT", "GEN-AIR-FLT") in keys
    assert ("PAINT-RED", "PAINT-BLUE") in keys
    assert ("MCB-20", "MCB-30") in keys
