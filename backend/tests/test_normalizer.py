from app.engine.normalizer import (
    extract_technical_tokens,
    normalize_description,
    normalize_part_no,
    normalize_text,
    tokenize_normalized_text,
)


def test_dec_part_numbers_normalize_to_same_meaning():
    assert normalize_part_no("DEC CO1") == "desiccated type 1"
    assert normalize_part_no("DEC C01") == "desiccated type 1"


def test_coconut_descriptions_normalize_to_same_meaning():
    assert normalize_description("Decicated Coconut type 1") == "desiccated coconut type 1"
    assert normalize_description("Dec Coco 1") == "desiccated coconut type 1"


def test_mcb_ratings_are_preserved():
    assert {"mcb", "30a"}.issubset(set(tokenize_normalized_text("MCB30A")))
    assert {"mcb", "20a"}.issubset(set(tokenize_normalized_text("MCB 20A")))


def test_hyphenated_part_numbers_expose_domain_tokens():
    gen_tokens = set(tokenize_normalized_text(normalize_part_no("SP-GEN-AIR-FLT")))
    hvac_tokens = set(tokenize_normalized_text(normalize_part_no("HVAC-FILTER-01")))

    assert {"generator", "air", "filter"}.issubset(gen_tokens)
    assert {"hvac", "filter", "01"}.issubset(hvac_tokens)


def test_none_and_blank_inputs_are_safe():
    assert normalize_text(None) == ""
    assert normalize_description("  ") == ""
    assert normalize_part_no(None) == ""


def test_extracts_technical_tokens_compatibility():
    tokens = extract_technical_tokens("MCB 30A 230V 20MM")
    assert set(tokens["numbers"]) == {"20", "30", "230"}
    assert {"30amp", "230v", "20mm"}.issubset(set(tokens["measurements"]))
