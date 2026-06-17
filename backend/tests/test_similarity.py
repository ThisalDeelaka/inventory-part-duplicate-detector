from app.engine.normalizer import extract_technical_tokens
from app.engine.models import CandidatePair, PartRecord, SimilarityResult
from app.engine.similarity import score_candidate_pair
from app.engine.similarity_model import calculate_fuzzy_similarity, calculate_part_no_similarity, calculate_technical_token_score, calculate_tfidf_similarity


def candidate(part_a, desc_a, part_b, desc_b):
    return CandidatePair(
        record_a=PartRecord(
            part_no=part_a,
            description=desc_a,
            raw={"PART_NO": part_a, "DESCRIPTION": desc_a, "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        ),
        record_b=PartRecord(
            part_no=part_b,
            description=desc_b,
            raw={"PART_NO": part_b, "DESCRIPTION": desc_b, "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
        ),
        matched_fields=["CONTRACT", "UNIT_MEAS"],
    )


def test_mcb_variation_scores_high():
    assert calculate_tfidf_similarity("MCB30A", "MCB 30 Amp") > 90
    assert calculate_fuzzy_similarity("MCB30A", "Miniature Circuit Breaker 30A") > 90


def test_spelling_variation_scores_high():
    assert calculate_tfidf_similarity("Decicated Coconut type 1", "Desiccated Coconut type 1") > 95


def test_part_number_similarity():
    assert calculate_part_no_similarity("AB-100", "AB100") > 90


def test_numeric_and_modifier_mismatches_are_penalized():
    assert calculate_technical_token_score(extract_technical_tokens("Bolt 10MM"), extract_technical_tokens("Bolt 12MM")) < 50
    assert calculate_technical_token_score(extract_technical_tokens("Generator Oil Filter"), extract_technical_tokens("Generator Air Filter")) < 50


def test_dec_synonym_pair_scores_high():
    result = score_candidate_pair(candidate(
        "DEC CO1",
        "Decicated Coconut type 1",
        "DEC C01",
        "Dec Coco 1",
    ))

    assert result.overall_similarity >= 90
    assert result.part_no_similarity >= 90
    assert result.description_similarity >= 90
    assert result.product_class_match is True
    assert result.type_code_match is True


def test_mcb_rating_mismatch_is_exposed():
    result = score_candidate_pair(candidate("MCB-20", "MCB 20A", "MCB-30", "MCB30A"))

    assert "20a" in result.rating_a
    assert "30a" in result.rating_b
    assert result.rating_match is False
    assert any(item["feature"] == "rating" for item in result.mismatched_features)


def test_paint_color_mismatch_is_exposed():
    result = score_candidate_pair(candidate("PAINT-RED", "RED PAINT 1L CAN", "PAINT-BLUE", "BLUE PAINT 1L CAN"))

    assert result.product_class_match is True
    assert result.color_match is False
    assert any(item["feature"] == "color" for item in result.mismatched_features)


def test_filter_function_or_media_mismatch_is_exposed():
    result = score_candidate_pair(candidate(
        "GEN-FUEL-FLT",
        "Generator Fuel Filter",
        "GEN-AIR-FLT",
        "Generator Air Filter",
    ))

    assert result.product_class_match is True
    assert result.application_context_match is True
    assert result.function_or_media_match is False
    assert "fuel" in result.function_or_media_a
    assert "air" in result.function_or_media_b


def test_generic_labels_expose_sparse_warning_and_terms():
    result = score_candidate_pair(candidate("TR LABELS", "Labels", "TR WARNING LABELS", "Warning labels"))

    assert result.generic_description_warning is True
    assert {"label", "labels"} & set(result.generic_terms_a)
    assert {"label", "labels"} & set(result.generic_terms_b)


def test_similarity_result_can_be_created_with_score_fields():
    result = SimilarityResult(
        overall_similarity=81.5,
        part_no_similarity=90,
        description_similarity=80,
        product_class_match=True,
    )

    assert result.overall_similarity == 81.5
    assert result.part_no_similarity == 90
    assert result.description_similarity == 80
    assert result.product_class_match is True
