from app.engine.normalizer import extract_technical_tokens, normalize_description


def test_normalizes_abbreviations_and_alphanumeric_values():
    assert normalize_description("MCB30A") == "miniature circuit breaker 30 amp"
    assert normalize_description("M.C.B 30 AMP") == "miniature circuit breaker 30 amp"
    assert normalize_description("20MM") == "20 mm"


def test_corrects_spelling_and_preserves_critical_words():
    assert normalize_description("Decicated Coconut type 1") == "desiccated coconut type 1"
    assert "oil" in normalize_description("Generator Oil Filter")
    assert "air" in normalize_description("Generator Air Filter")
    assert "red" in extract_technical_tokens("RED PAINT 1L CAN")["modifiers"]
    assert "blue" in extract_technical_tokens("BLUE PAINT 1L CAN")["modifiers"]


def test_extracts_technical_tokens():
    tokens = extract_technical_tokens("MCB 30A 230V 20MM")
    assert set(tokens["numbers"]) == {"20", "30", "230"}
    assert {"30amp", "230v", "20mm"}.issubset(set(tokens["measurements"]))
