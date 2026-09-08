from app.engine.scoring import score_candidate
from app.engine.generic_description_guard import is_generic_description


def rec(
    part, description, site="S1", unit="PCS", commodity="X", hsn="1000",
    accounting_group="A",
):
    return {
        "PART_NO": part,
        "DESCRIPTION": description,
        "CONTRACT": site,
        "UNIT_MEAS": unit,
        "PRIME_COMMODITY": commodity,
        "ACCOUNTING_GROUP": accounting_group,
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


def test_desiccated_coconut_domain_synonyms_are_likely_duplicate():
    result = score_candidate(
        rec("DEC CO1", "Decicated Coconut type 1"),
        rec("DEC C01", "Dec Coco 1"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["business_status"] == "LIKELY_DUPLICATE"
    assert result["confidence_level"] in {"HIGH", "MEDIUM"}
    assert result["final_score"] >= 90
    assert "business synonym normalization" in result["explanation"]
    assert result["normalized_description_a"] == "desiccated coconut type 1"
    assert result["normalized_description_b"] == "desiccated coconut type 1"
    assert result["normalized_part_no_a"] == "desiccated type 1"
    assert result["normalized_part_no_b"] == "desiccated type 1"


def test_same_part_number_is_not_duplicate_candidate():
    result = score_candidate(
        rec("T-100", "T-100", site="HWHSP"),
        rec("T-100", "T-100", site="B"),
        ["UNIT_MEAS"],
    )

    assert result["final_score"] == 0
    assert result["confidence_level"] == "IGNORE"
    assert "Same PART_NO" in result["explanation"]


def test_generic_label_description_is_low_confidence_review():
    result = score_candidate(
        rec("TR LABELS", "Labels"),
        rec("TR WARNING LABELS", "Warning labels"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["business_status"] == "INSUFFICIENT_DATA"
    assert result["generic_description_warning"] is True
    assert result["confidence_level"] not in {"HIGH", "MEDIUM"}
    assert result["final_score"] <= 65
    assert "One description is too generic to confirm duplicate identity." in result["explanation"]


def test_known_generic_business_descriptions_raise_warning():
    for description in ("test part", "sales part", "component", "inventory part"):
        assert is_generic_description(description) is True
        result = score_candidate(
            rec("GENERIC", description),
            rec("SPECIFIC", "Hydraulic pump assembly"),
            ["CONTRACT", "UNIT_MEAS"],
        )
        assert result["generic_description_warning"] is True
        assert result["business_status"] == "INSUFFICIENT_DATA"
        assert result["final_score"] <= 65


def test_two_generic_descriptions_are_also_insufficient():
    result = score_candidate(
        rec("GENERIC-1", "Test Part"),
        rec("GENERIC-2", "Sales Part"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["generic_description_warning"] is True
    assert result["business_status"] == "INSUFFICIENT_DATA"
    assert result["final_score"] <= 65


def test_identical_single_noun_is_review_only_without_independent_identity_evidence():
    assert is_generic_description("BEARING") is True
    left = rec("A", "BEARING")
    right = rec("B", "BEARING")
    left["PRODUCT_CATEGORY_ID"] = right["PRODUCT_CATEGORY_ID"] = "CAT1"
    result = score_candidate(
        left,
        right,
        ["CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP", "PRODUCT_CATEGORY_ID"],
        allow_uom_mapping_review=True,
    )

    assert result["generic_description_warning"] is True
    assert result["business_status"] == "POSSIBLE_DUPLICATE_REVIEW"
    assert result["business_status"] != "LIKELY_DUPLICATE"
    assert result["rule_decision"] == "DOWNGRADE"
    assert result["rejection_reason"] == "GENERIC_DESCRIPTION"
    assert result["final_score"] <= 65


def test_generic_description_can_be_strong_with_existing_strong_part_number_evidence():
    result = score_candidate(
        rec("BRG-6205-A", "BEARING"),
        rec("BRG6205A", "BEARING"),
        ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    )

    assert result["generic_description_warning"] is True
    assert result["part_no_similarity"] >= 90
    assert result["business_status"] == "LIKELY_DUPLICATE"
    assert result["rule_decision"] == "ALLOW"


def test_different_generic_single_nouns_remain_non_positive():
    result = score_candidate(
        rec("N1", "BEARING"),
        rec("N2", "FILTER"),
        ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    )

    assert result["generic_description_warning"] is True
    assert result["business_status"] == "INSUFFICIENT_DATA"
    assert result["business_status"] != "LIKELY_DUPLICATE"


def test_mutually_exclusive_qualifiers_are_not_duplicates():
    cases = [
        ("Wired User Interface", "Wireless User Interface", "connectivity differs"),
        ("Indoor Fan Unit", "Outdoor Fan Unit", "environment differs"),
        ("Manual Control Valve", "Automatic Control Valve", "operation mode differs"),
        ("Internal Sensor", "External Sensor", "placement differs"),
        ("Primary Pump", "Secondary Pump", "hierarchy differs"),
        ("Analog Input", "Digital Input", "signal type differs"),
    ]
    for left, right, explanation in cases:
        result = score_candidate(rec("A", left), rec("B", right), ["CONTRACT", "UNIT_MEAS"])
        assert result["business_status"] == "RELATED_BUT_NOT_DUPLICATE"
        assert result["final_score"] <= 55
        assert explanation in result["explanation"]


def test_matching_description_bases_with_different_trailing_variants_are_not_duplicates():
    cases = [
        ("Serial Part 1", "Serial Part 2"),
        ("Raw Material 01", "Raw Material 02"),
        ("Pump Assembly First", "Pump Assembly Second"),
    ]
    for left, right in cases:
        result = score_candidate(rec("A", left), rec("B", right), ["CONTRACT", "UNIT_MEAS"])
        assert result["business_status"] == "RELATED_BUT_NOT_DUPLICATE"
        assert result["rejection_reason"] == "TRAILING_VARIANT_SUFFIX_MISMATCH"
        assert result["final_score"] <= 55
        assert "trailing variant suffix differs" in result["explanation"]


def test_reported_false_positive_pairs_remain_below_duplicate_confidence():
    serial = score_candidate(
        rec("SN-P1", "Serial Part 1"),
        rec("SN-P2", "Serial Part 2"),
        ["CONTRACT", "UNIT_MEAS"],
    )
    connectivity = score_candidate(
        rec("P10009845", "Wired User Interface"),
        rec("P12509845", "Wireless User Interface"),
        ["CONTRACT", "UNIT_MEAS"],
    )
    base_variant = score_candidate(
        rec("VTZSR55", "Ventechi Z series units"),
        rec("VTZSR55-I", "Ventechi Z series indoor unit"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert serial["final_score"] < 75
    assert serial["rejection_reason"] == "TRAILING_VARIANT_SUFFIX_MISMATCH"
    assert connectivity["final_score"] < 75
    assert connectivity["rejection_reason"] == "CONNECTIVITY_MISMATCH"
    assert base_variant["final_score"] < 75
    assert base_variant["rejection_reason"] == "ENVIRONMENT_UNSPECIFIED"
    assert base_variant["generic_description_warning"] is True


def test_structural_role_differences_are_visible_review_candidates():
    cases = [
        ("SJ COMP PART1", "SJ TOP PART1", "component", "top"),
        ("AM SC PART Top part", "AM SC PART comp part", "top", "component"),
        ("TOP PART", "COMPONENT PART", "top", "component"),
    ]
    for left, right, role_a, role_b in cases:
        result = score_candidate(rec(left, left), rec(right, right), ["CONTRACT", "UNIT_MEAS"])
        assert result["business_status"] in {"POSSIBLE_DUPLICATE_REVIEW", "INSUFFICIENT_DATA"}
        assert result["business_status"] != "LIKELY_DUPLICATE"
        assert result["rule_decision"] == "DOWNGRADE"
        assert result["rejection_reason"] == "STRUCTURAL_ROLE_MISMATCH"
        assert result["final_score"] < 90
        assert result["critical_mismatches"][0]["group"] == "STRUCTURAL_ROLE"
        assert result["critical_mismatches"][0]["values_a"] == [role_a]
        assert result["critical_mismatches"][0]["values_b"] == [role_b]
        assert "Different structural role detected" in result["explanation"]


def test_known_true_positive_families_are_not_overcorrected():
    likely_cases = [
        ("RPSMD1", "RPSMD1", "RPSMD2", "RPSMD1"),
        ("KETTLE", "Singer Kettles", "KETTLES", "Singer Kettles"),
        ("AP-BRG-FR-22", "FRANCIS TURBINE LOWER BEARING", "CB-BRG-FR-22", "Francis Turbine Lower Bearing"),
    ]
    for part_a, description_a, part_b, description_b in likely_cases:
        result = score_candidate(rec(part_a, description_a), rec(part_b, description_b), ["CONTRACT", "UNIT_MEAS"])
        assert result["business_status"] == "LIKELY_DUPLICATE"
        assert result["confidence_level"] == "HIGH"

    fan_blade = score_candidate(
        rec("SP-FAN BLADE", "fan blade"),
        rec("SH- FAN BLADE", "fan bladeSH- FAN BLADE"),
        ["CONTRACT", "UNIT_MEAS"],
    )
    assert fan_blade["final_score"] >= 75
    assert fan_blade["rule_decision"] == "ALLOW"


def test_application_context_mismatch_warns_without_rejecting():
    result = score_candidate(
        rec("SP-GEN-AIR-FLT", "Generator Air Filter"),
        rec("HVAC-FILTER-01", "Air Filter"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["business_status"] == "POSSIBLE_DUPLICATE_REVIEW"
    assert result["application_context_a"] == ["generator"]
    assert result["application_context_b"] == ["hvac"]
    assert result["application_context_warning"] is True
    assert result["final_score"] <= 78
    assert result["rule_decision"] == "DOWNGRADE"
    assert "Application context appears different: generator vs hvac." in result["explanation"]


def test_same_application_context_does_not_warn():
    result = score_candidate(
        rec("SP-GEN-OIL-FLT-1", "GEN Oil Filter"),
        rec("SP-GEN-OIL-FLT-2", "Generator Oil Filter"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert "Application context appears different" not in result["explanation"]


def test_hsn_sac_mismatch_blocks_otherwise_similar_candidate():
    result = score_candidate(
        rec("A", "Stainless Steel Pipe", hsn="7306"),
        rec("B", "SS Pipe", hsn="3917"),
        ["CONTRACT", "UNIT_MEAS"],
    )

    assert result["final_score"] < 60
    assert result["confidence_level"] == "IGNORE"
    assert "HSN_SAC_CODE differs" in result["explanation"]
