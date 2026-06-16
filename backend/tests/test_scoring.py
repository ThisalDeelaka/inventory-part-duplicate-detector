from app.engine.scoring import score_candidate


def rec(part, description, site="S1", unit="PCS", commodity="X", hsn="1000"):
    return {
        "PART_NO": part,
        "DESCRIPTION": description,
        "CONTRACT": site,
        "UNIT_MEAS": unit,
        "PRIME_COMMODITY": commodity,
        "HSN_SAC_CODE": hsn,
    }


def test_high_confidence_duplicate():
    result = score_candidate(rec("MCB30A-1","MCB30A"), rec("MCB30A-2","MCB 30 Amp"), ["CONTRACT","UNIT_MEAS"])
    assert result["confidence_level"] in {"HIGH", "MEDIUM"}
    assert result["final_score"] >= 75


def test_critical_modifier_and_number_mismatches_stay_low():
    oil_air = score_candidate(rec("F1","Generator Oil Filter"), rec("F2","Generator Air Filter"), ["CONTRACT","UNIT_MEAS"])
    fuel_air = score_candidate(rec("SP-GEN-FUEL-FLT", "Generator Fuel Filter"), rec("SP-GEN-AIR-FLT", "Generator Air Filter"), ["CONTRACT", "UNIT_MEAS"])
    numeric = score_candidate(rec("B1","Bolt 10MM"), rec("B2","Bolt 12MM"), ["CONTRACT","UNIT_MEAS"])
    color = score_candidate(rec("P1", "RED PAINT 1L CAN"), rec("P2", "BLUE PAINT 1L CAN"), ["CONTRACT", "UNIT_MEAS"])
    assert oil_air["final_score"] < 75
    assert fuel_air["final_score"] < 75
    assert numeric["final_score"] < 75
    assert color["final_score"] < 60
    assert "critical function differs" in oil_air["explanation"]
    assert "critical function differs" in fuel_air["explanation"]
    assert "color differs" in color["explanation"]


def test_cross_site_and_missing_classification_explanations():
    cross = score_candidate(rec("A","SS Pipe","S1"), rec("B","Stainless Steel Pipe","S2"), ["CONTRACT"])
    missing = score_candidate({"PART_NO":"A","DESCRIPTION":"MCB30A"},{"PART_NO":"B","DESCRIPTION":"MCB 30 A"},[])
    assert "Different site" in cross["explanation"]
    assert "Classification fields are missing" in missing["explanation"]


def test_inventory_uom_mismatch_blocks_apparent_description_duplicate():
    result = score_candidate(
        rec("DEC C01", "Dec Coco 1", unit="g"),
        rec("PRODUCT COCO DEC1", "Desiccated Coconut type 1", unit="PCS"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["final_score"] < 60
    assert result["confidence_level"] == "IGNORE"
    assert "Inventory UOM differs" in result["explanation"]


def test_related_but_different_variants_are_not_duplicates():
    cases = [
        ("Generator Fuel Filter", "Generator Air Filter", "critical function differs"),
        ("Generator Oil Filter", "Generator Fuel Filter", "critical function differs"),
        ("RED PAINT 1L CAN", "BLUE PAINT 1L CAN", "color differs"),
        ("Decicated Coconut type 1", "Decicated Coconut type 2", "type differs"),
        ("MCB 20A", "MCB30A", "ampere rating differs"),
        ("Small Coconut", "eXtra small Coconut", "size differs"),
        ("Temperature Sensor", "Pressure Sensor", "sensor type differs"),
    ]

    for left, right, explanation in cases:
        result = score_candidate(rec("A", left), rec("B", right), ["CONTRACT", "UNIT_MEAS"])
        assert result["business_status"] == "RELATED_BUT_NOT_DUPLICATE"
        assert result["final_score"] <= 55
        assert explanation in result["explanation"]


def test_hsn_sac_mismatch_is_data_conflict():
    left = {**rec("A", "SS Pipe"), "HSN_SAC_CODE": "1001"}
    right = {**rec("B", "Stainless Steel Pipe"), "HSN_SAC_CODE": "2002"}

    result = score_candidate(left, right, ["CONTRACT", "UNIT_MEAS", "HSN_SAC_CODE"])

    assert result["business_status"] == "DATA_CONFLICT_REVIEW"
    assert result["rule_decision"] == "DATA_CONFLICT"
    assert result["final_score"] <= 45
    assert "HSN/SAC Code differs" in result["explanation"]


def test_allowed_likely_duplicates_remain_supported():
    cases = [
        ("MCB30A", "MCB 30 Amp"),
        ("Decicated Coconut type 1", "Desiccated Coconut type 1"),
        ("SS Pipe", "Stainless Steel Pipe"),
        ("Generator Oil Filter", "Generator oil  filter"),
    ]

    for left, right in cases:
        result = score_candidate(rec("A", left), rec("B", right), ["CONTRACT", "UNIT_MEAS"])
        assert result["business_status"] in {"LIKELY_DUPLICATE", "POSSIBLE_DUPLICATE_REVIEW"}
        assert result["rule_decision"] == "ALLOW"
        assert result["final_score"] >= 60


def test_same_part_number_is_not_duplicate_candidate():
    result = score_candidate(
        rec("T-100", "T-100", site="HWHSP"),
        rec("T-100", "T-100", site="B"),
        ["UNIT_MEAS"],
    )

    assert result["final_score"] == 0
    assert result["confidence_level"] == "IGNORE"
    assert "Same PART_NO" in result["explanation"]


def test_hsn_sac_mismatch_blocks_otherwise_similar_candidate():
    result = score_candidate(
        rec("A", "Stainless Steel Pipe", hsn="7306"),
        rec("B", "SS Pipe", hsn="3917"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["final_score"] < 60
    assert result["confidence_level"] == "IGNORE"
    assert "HSN_SAC_CODE differs" in result["explanation"]
