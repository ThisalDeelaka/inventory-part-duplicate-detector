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


def assert_contains(text, *words):
    lowered = text.lower()
    for word in words:
        assert word.lower() in lowered


def test_dec_synonym_duplicate_explanation_mentions_normalization():
    result = decide("DEC CO1", "Decicated Coconut type 1", "DEC C01", "Dec Coco 1")

    assert_contains(result.explanation, "duplicate_candidate", "normalization", "desiccated coconut type 1", "no critical conflicts")


def test_mcb_rating_explanation_mentions_mcb_and_ratings():
    result = decide("MCB-20", "MCB 20A", "MCB-30", "MCB30A")

    assert_contains(result.explanation, "related_but_not_duplicate", "mcb", "rating differs", "20a", "30a")


def test_paint_color_explanation_mentions_paint_and_colors():
    result = decide("PAINT-RED", "RED PAINT 1L CAN", "PAINT-BLUE", "BLUE PAINT 1L CAN")

    assert_contains(result.explanation, "related_but_not_duplicate", "paint", "color differs", "red", "blue")


def test_filter_function_explanation_mentions_generator_filter_and_media():
    result = decide("GEN-FUEL-FLT", "Generator Fuel Filter", "GEN-AIR-FLT", "Generator Air Filter")

    assert_contains(result.explanation, "related_but_not_duplicate", "generator filter", "function/media differs", "fuel", "air")


def test_generic_label_explanation_mentions_sparse_evidence():
    result = decide("TR LABELS", "Labels", "TR WARNING LABELS", "Warning labels")

    assert_contains(result.explanation, "generic or sparse", "cannot confirm duplicate identity", "high confidence")


def test_hsn_data_conflict_explanation_mentions_hsn_values():
    result = decide(
        "A",
        "Stainless Steel Pipe",
        "B",
        "Stainless Steel Pipe",
        {"HSN_SAC_CODE": "7306"},
        {"HSN_SAC_CODE": "3917"},
    )

    assert_contains(result.explanation, "data_conflict_review", "hsn/sac", "7306", "3917", "data conflict", "not a confirmed duplicate")


def test_cross_site_explanation_mentions_contract_standardization():
    result = decide(
        "A",
        "SS Pipe",
        "B",
        "Stainless Steel Pipe",
        {"CONTRACT": "S1"},
        {"CONTRACT": "S2"},
        cross_site=True,
    )

    assert_contains(result.explanation, "cross_site_standardization_candidate", "contract", "s1", "s2", "standardization", "not a same-site duplicate")
