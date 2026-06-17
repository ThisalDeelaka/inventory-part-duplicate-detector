from app.engine.attribute_extractor import extract_attributes


def test_generator_fuel_filter_attributes():
    attrs = extract_attributes("SP-GEN-FUEL-FLT", "Generator Fuel Filter")

    assert "filter" in attrs.product_class
    assert "generator" in attrs.application_context
    assert "fuel" in attrs.function_or_media


def test_generator_air_filter_attributes():
    attrs = extract_attributes("SP-GEN-AIR-FLT", "Generator Air Filter")

    assert "filter" in attrs.product_class
    assert "generator" in attrs.application_context
    assert "air" in attrs.function_or_media


def test_red_paint_can_attributes():
    attrs = extract_attributes("PAINT-RED", "RED PAINT 1L CAN")

    assert "paint" in attrs.product_class
    assert "red" in attrs.color
    assert "1l" in attrs.volume
    assert "can" in attrs.packaging


def test_blue_paint_can_attributes():
    attrs = extract_attributes("PAINT-BLUE", "BLUE PAINT 1L CAN")

    assert "paint" in attrs.product_class
    assert "blue" in attrs.color
    assert "1l" in attrs.volume
    assert "can" in attrs.packaging


def test_mcb_20a_attributes():
    attrs = extract_attributes("MCB-20", "MCB 20A")

    assert "mcb" in attrs.product_class
    assert "20a" in attrs.rating


def test_mcb30a_attributes():
    attrs = extract_attributes("MCB30A", "MCB30A")

    assert "mcb" in attrs.product_class
    assert "30a" in attrs.rating


def test_dec_co1_coconut_attributes():
    attrs = extract_attributes("DEC CO1", "Decicated Coconut type 1")

    assert "coconut" in attrs.product_class
    assert "type 1" in attrs.type_code
    assert "desiccated" in attrs.normalized_text
    assert "coconut" in attrs.normalized_text
    assert "type 1" in attrs.normalized_text


def test_dec_c01_coconut_attributes():
    attrs = extract_attributes("DEC C01", "Dec Coco 1")

    assert "coconut" in attrs.product_class
    assert "type 1" in attrs.type_code
    assert "desiccated" in attrs.normalized_text
    assert "coconut" in attrs.normalized_text
    assert "type 1" in attrs.normalized_text


def test_labels_generic_attributes():
    attrs = extract_attributes("TR LABELS", "Labels")

    assert {"label", "labels"} & set(attrs.generic_terms)
    assert attrs.is_generic_description is True


def test_warning_labels_attributes():
    attrs = extract_attributes("TR WARNING LABELS", "Warning labels")

    assert {"label", "labels"} & set(attrs.generic_terms)
    assert "warning" in attrs.function_or_media
