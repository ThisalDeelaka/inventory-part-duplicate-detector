import json

from app.repositories.candidate_repository import CandidateRepository


def test_candidate_repository_preserves_redesigned_evidence_fields(db):
    result = {
        "final_score": 91.0,
        "confidence_score": 91.0,
        "confidence_level": "HIGH",
        "description_similarity": 95.0,
        "tfidf_score": 94.0,
        "fuzzy_score": 96.0,
        "part_no_similarity": 90.0,
        "technical_token_score": 88.0,
        "matched_fields": ["CONTRACT"],
        "mismatched_fields": [],
        "matched_evidence": ["product_class", "type_code"],
        "differences": [{"feature": "rating", "values_a": ["20a"], "values_b": ["30a"]}],
        "warnings": ["example warning"],
        "explanation": "Example explanation",
        "recommended_action": "Manual review recommended",
        "business_status": "DUPLICATE_CANDIDATE",
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "scan_mode": "SAME_SITE_DUPLICATE",
        "critical_mismatches": [],
        "variant_attributes_a": {"product_class": ["coconut"]},
        "variant_attributes_b": {"product_class": ["coconut"]},
        "normalized_description_a": "desiccated coconut type 1",
        "normalized_description_b": "desiccated coconut type 1",
        "normalized_part_no_a": "desiccated type 1",
        "normalized_part_no_b": "desiccated type 1",
        "extracted_attributes_a": {"product_class": ["coconut"]},
        "extracted_attributes_b": {"product_class": ["coconut"]},
    }

    candidate = CandidateRepository(db).save(
        1,
        {"PART_NO": "DEC CO1", "DESCRIPTION": "Decicated Coconut type 1", "CONTRACT": "SMBE"},
        {"PART_NO": "DEC C01", "DESCRIPTION": "Dec Coco 1", "CONTRACT": "SMBE"},
        result,
    )
    db.flush()

    assert candidate.confidence_score == 91.0
    assert json.loads(candidate.matched_evidence) == ["product_class", "type_code"]
    assert json.loads(candidate.differences)[0]["feature"] == "rating"
    assert json.loads(candidate.warnings) == ["example warning"]
    assert json.loads(candidate.extracted_attributes_a)["product_class"] == ["coconut"]
    assert json.loads(candidate.extracted_attributes_b)["product_class"] == ["coconut"]
