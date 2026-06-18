from app.engine.models import DecisionResult
from app.engine.result_adapter import decision_result_to_scan_candidate, decision_results_to_scan_candidates


def decision(status="DUPLICATE_CANDIDATE"):
    return DecisionResult(
        status=status,
        confidence_score=96.5,
        confidence_level="HIGH",
        explanation="Descriptions and part numbers match after normalization.",
        matched_evidence=["product_class", "type_code"],
        differences=[{"feature": "rating", "values_a": ["20a"], "values_b": ["30a"]}],
        warnings=["example warning"],
        rule_decision="ALLOW",
        rejection_reason="",
        normalized_part_no_a="desiccated type 1",
        normalized_part_no_b="desiccated type 1",
        normalized_description_a="desiccated coconut type 1",
        normalized_description_b="desiccated coconut type 1",
        extracted_attributes_a={"product_class": ["coconut"], "type_code": ["type 1"]},
        extracted_attributes_b={"product_class": ["coconut"], "type_code": ["type 1"]},
    )


def test_duplicate_candidate_decision_converts_to_dict():
    candidate = decision_result_to_scan_candidate(decision())

    assert isinstance(candidate, dict)
    assert candidate["business_status"] == "DUPLICATE_CANDIDATE"
    assert candidate["similarity_score"] == 96.5


def test_legacy_style_fields_are_present():
    candidate = decision_result_to_scan_candidate(decision())

    for field in (
        "part_no_a",
        "description_a",
        "part_no_b",
        "description_b",
        "score",
        "similarity_score",
        "final_score",
        "matched_fields",
        "mismatched_fields",
        "reason",
        "recommended_action",
        "review_status",
    ):
        assert field in candidate


def test_new_business_fields_are_present():
    candidate = decision_result_to_scan_candidate(decision())

    assert candidate["confidence_score"] == 96.5
    assert candidate["confidence_level"] == "HIGH"
    assert candidate["explanation"]
    assert candidate["rule_decision"] == "ALLOW"
    assert "normalized_description_a" in candidate
    assert "normalized_part_no_a" in candidate
    assert "normalized_description_b" in candidate
    assert "normalized_part_no_b" in candidate
    assert "extracted_attributes_a" in candidate
    assert "extracted_attributes_b" in candidate


def test_evidence_fields_are_preserved():
    candidate = decision_result_to_scan_candidate(decision())

    assert candidate["matched_evidence"] == ["product_class", "type_code"]
    assert candidate["differences"][0]["feature"] == "rating"
    assert candidate["warnings"] == ["example warning"]


def test_adapter_handles_missing_optional_fields_safely():
    candidate = decision_result_to_scan_candidate(None)

    assert candidate["business_status"] == "POSSIBLE_DUPLICATE_REVIEW"
    assert candidate["similarity_score"] == 0.0
    assert candidate["matched_evidence"] == []
    assert candidate["differences"] == []
    assert candidate["warnings"] == []


def test_decision_result_list_converts_to_candidate_dict_list():
    candidates = decision_results_to_scan_candidates([
        decision("DUPLICATE_CANDIDATE"),
        decision("RELATED_BUT_NOT_DUPLICATE"),
    ])

    assert len(candidates) == 2
    assert [item["business_status"] for item in candidates] == [
        "DUPLICATE_CANDIDATE",
        "RELATED_BUT_NOT_DUPLICATE",
    ]
