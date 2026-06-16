from app.engine.scoring import score_candidate


def rec(part, description, site="S1", unit="PCS", commodity="X"):
    return {"PART_NO":part,"DESCRIPTION":description,"CONTRACT":site,"UNIT_MEAS":unit,"PRIME_COMMODITY":commodity}


def test_high_confidence_duplicate():
    result = score_candidate(rec("MCB30A-1","MCB30A"), rec("MCB30A-2","MCB 30 Amp"), ["CONTRACT","UNIT_MEAS"])
    assert result["confidence_level"] in {"HIGH", "MEDIUM"}
    assert result["final_score"] >= 75


def test_critical_modifier_and_number_mismatches_stay_low():
    oil_air = score_candidate(rec("F1","Generator Oil Filter"), rec("F2","Generator Air Filter"), ["CONTRACT","UNIT_MEAS"])
    numeric = score_candidate(rec("B1","Bolt 10MM"), rec("B2","Bolt 12MM"), ["CONTRACT","UNIT_MEAS"])
    color = score_candidate(rec("P1", "RED PAINT 1L CAN"), rec("P2", "BLUE PAINT 1L CAN"), ["CONTRACT", "UNIT_MEAS"])
    assert oil_air["final_score"] < 75
    assert numeric["final_score"] < 75
    assert color["final_score"] < 60
    assert "critical modifier differs" in oil_air["explanation"]
    assert "critical modifier differs" in color["explanation"]


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
