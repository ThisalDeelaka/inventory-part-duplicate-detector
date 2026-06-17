from app.engine.scoring import score_candidate


def rec(part, description, site="S1", unit="PCS", hsn="1000"):
    return {
        "PART_NO": part,
        "DESCRIPTION": description,
        "CONTRACT": site,
        "UNIT_MEAS": unit,
        "HSN_SAC_CODE": hsn,
    }


def test_related_but_not_duplicate_examples():
    cases = [
        ("GEN-FUEL-FLT", "Generator Fuel Filter", "GEN-AIR-FLT", "Generator Air Filter"),
        ("PAINT-RED", "RED PAINT 1L CAN", "PAINT-BLUE", "BLUE PAINT 1L CAN"),
        ("MCB-20", "MCB 20A", "MCB-30", "MCB30A"),
        ("COCO-1", "Decicated Coconut type 1", "COCO-2", "Decicated Coconut type 2"),
    ]

    for part_a, desc_a, part_b, desc_b in cases:
        result = score_candidate(rec(part_a, desc_a), rec(part_b, desc_b), ["CONTRACT", "UNIT_MEAS"])
        assert result["business_status"] == "RELATED_BUT_NOT_DUPLICATE"
        assert result["final_score"] <= 55


def test_domain_synonym_duplicate_candidate():
    result = score_candidate(
        rec("DEC CO1", "Decicated Coconut type 1"),
        rec("DEC C01", "Dec Coco 1"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["business_status"] == "DUPLICATE_CANDIDATE"
    assert result["final_score"] >= 90
    assert "business synonym normalization" in result["explanation"]


def test_generic_description_is_insufficient_data():
    result = score_candidate(
        rec("TR LABELS", "Labels"),
        rec("TR WARNING LABELS", "Warning Labels"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["business_status"] in {"INSUFFICIENT_DATA", "POSSIBLE_DUPLICATE_REVIEW"}
    assert result["business_status"] != "DUPLICATE_CANDIDATE"
    assert result["generic_description_warning"] is True


def test_same_description_different_hsn_is_data_conflict():
    result = score_candidate(
        rec("A", "Stainless Steel Pipe", hsn="7306"),
        rec("B", "Stainless Steel Pipe", hsn="3917"),
        ["CONTRACT", "UNIT_MEAS", "HSN_SAC_CODE"],
    )

    assert result["business_status"] == "DATA_CONFLICT_REVIEW"
    assert result["rule_decision"] == "DATA_CONFLICT"


def test_cross_site_standardization_mode():
    same_site = score_candidate(
        rec("A", "SS Pipe", site="S1"),
        rec("B", "Stainless Steel Pipe", site="S2"),
        ["CONTRACT", "UNIT_MEAS"],
        scan_mode="SAME_SITE_DUPLICATE",
    )
    cross_site = score_candidate(
        rec("A", "SS Pipe", site="S1"),
        rec("B", "Stainless Steel Pipe", site="S2"),
        ["CONTRACT", "UNIT_MEAS"],
        scan_mode="CROSS_SITE_STANDARDIZATION",
    )

    assert same_site["business_status"] != "DUPLICATE_CANDIDATE"
    assert cross_site["business_status"] == "CROSS_SITE_STANDARDIZATION_CANDIDATE"
