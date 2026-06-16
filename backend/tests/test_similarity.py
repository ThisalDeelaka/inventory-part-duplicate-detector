from app.engine.normalizer import extract_technical_tokens
from app.engine.similarity_model import calculate_fuzzy_similarity, calculate_part_no_similarity, calculate_technical_token_score, calculate_tfidf_similarity


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
