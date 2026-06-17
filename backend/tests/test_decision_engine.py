from app.engine.decision_engine import make_decision
from app.engine.guardrails import apply_guardrails
from app.engine.models import CandidatePair, PartRecord
from app.engine.similarity import score_candidate_pair


def candidate(part_a, desc_a, part_b, desc_b, extra_a=None, extra_b=None):
    raw_a = {"PART_NO": part_a, "DESCRIPTION": desc_a, "CONTRACT": "S1", "UNIT_MEAS": "PCS"}
    raw_b = {"PART_NO": part_b, "DESCRIPTION": desc_b, "CONTRACT": "S1", "UNIT_MEAS": "PCS"}
    raw_a.update(extra_a or {})
    raw_b.update(extra_b or {})
    return CandidatePair(
        record_a=PartRecord(part_no=part_a, description=desc_a, contract=raw_a.get("CONTRACT"), raw=raw_a),
        record_b=PartRecord(part_no=part_b, description=desc_b, contract=raw_b.get("CONTRACT"), raw=raw_b),
        matched_fields=["UNIT_MEAS"],
    )


def decide(part_a, desc_a, part_b, desc_b, extra_a=None, extra_b=None, cross_site=False):
    pair = candidate(part_a, desc_a, part_b, desc_b, extra_a, extra_b)
    similarity = score_candidate_pair(pair)
    guardrails = apply_guardrails(pair, similarity, cross_site=cross_site)
    return make_decision(pair, similarity, guardrails, cross_site=cross_site)


def test_dec_synonym_pair_is_duplicate_candidate():
    result = decide("DEC CO1", "Decicated Coconut type 1", "DEC C01", "Dec Coco 1")

    assert result.status == "DUPLICATE_CANDIDATE"
    assert result.confidence_score >= 85


def test_mcb_rating_mismatch_is_related_but_not_duplicate():
    result = decide("MCB-20", "MCB 20A", "MCB-30", "MCB30A")

    assert result.status == "RELATED_BUT_NOT_DUPLICATE"
    assert result.rejection_reason == "rating_mismatch"


def test_paint_color_mismatch_is_related_but_not_duplicate():
    result = decide("PAINT-RED", "RED PAINT 1L CAN", "PAINT-BLUE", "BLUE PAINT 1L CAN")

    assert result.status == "RELATED_BUT_NOT_DUPLICATE"
    assert result.rejection_reason == "color_mismatch"


def test_filter_function_mismatch_is_related_but_not_duplicate():
    result = decide("GEN-FUEL-FLT", "Generator Fuel Filter", "GEN-AIR-FLT", "Generator Air Filter")

    assert result.status == "RELATED_BUT_NOT_DUPLICATE"
    assert result.rejection_reason == "function_or_media_mismatch"


def test_coconut_type_mismatch_is_related_but_not_duplicate():
    result = decide("COCO-1", "Decicated Coconut type 1", "COCO-2", "Decicated Coconut type 2")

    assert result.status == "RELATED_BUT_NOT_DUPLICATE"
    assert result.rejection_reason == "type_code_mismatch"


def test_generic_labels_are_not_duplicate_candidate():
    result = decide("TR LABELS", "Labels", "TR WARNING LABELS", "Warning labels")

    assert result.status in {"INSUFFICIENT_DATA", "POSSIBLE_DUPLICATE_REVIEW"}
    assert result.status != "DUPLICATE_CANDIDATE"


def test_hsn_sac_mismatch_is_data_conflict_review():
    result = decide(
        "A",
        "Stainless Steel Pipe",
        "B",
        "Stainless Steel Pipe",
        {"HSN_SAC_CODE": "7306"},
        {"HSN_SAC_CODE": "3917"},
    )

    assert result.status == "DATA_CONFLICT_REVIEW"


def test_safety_code_mismatch_is_data_conflict_review():
    result = decide(
        "A",
        "Hydraulic Oil",
        "B",
        "Hydraulic Oil",
        {"SAFETY_CODE": "HZ1"},
        {"SAFETY_CODE": "HZ2"},
    )

    assert result.status == "DATA_CONFLICT_REVIEW"


def test_cross_site_similar_item_is_standardization_candidate():
    result = decide(
        "A",
        "SS Pipe",
        "B",
        "Stainless Steel Pipe",
        {"CONTRACT": "S1"},
        {"CONTRACT": "S2"},
        cross_site=True,
    )

    assert result.status == "CROSS_SITE_STANDARDIZATION_CANDIDATE"


def test_low_similarity_pair_is_unique_no_match():
    result = decide("ABC-1", "Bicycle Tire", "XYZ-9", "Paint Brush")

    assert result.status == "UNIQUE_NO_MATCH"
