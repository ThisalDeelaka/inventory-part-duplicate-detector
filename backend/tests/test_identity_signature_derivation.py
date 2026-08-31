import inspect
from dataclasses import replace

import pytest

from app.benchmarks.identity_signature_derivation_audit import (
    audit_identity_signatures,
)
from app.engine.identity_signature import (
    IdentityObservationState,
    IdentitySemanticCategory,
    IdentitySourceField,
    with_identity_signature_fingerprint,
)
from app.engine.identity_signature_derivation import (
    IDENTITY_SIGNATURE_DERIVATION_VERSION,
    MAX_UNRESOLVED_OBSERVATIONS_PER_SOURCE,
    derive_identity_signature,
)


def record(part_no="", description="", **values):
    result = {
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "MASTER_DESCRIPTION": values.pop("master_description", description),
        "TYPE_DESIGNATION": values.pop("type_designation", ""),
        "DIMENSION_QUALITY": values.pop("dimension_quality", ""),
        "CONTRACT": values.pop("contract", "S1"),
        "record_ref_key": values.pop("record_ref_key", f"ref-{part_no}-{description}"),
    }
    result.update(values)
    return result


def values(signature, field):
    return {item.normalized_value for item in getattr(signature, field)}


def unresolved_values(signature, *, key=None):
    return {
        item.normalized_value
        for item in signature.unresolved_observations
        if key is None or item.semantic_key == key
    }


HISTORICAL_GOLDENS = (
    ("G1-carbon", "CS-CARBONSTICK", "Carbon Stick", {"carbon-stick"}, set()),
    ("G1-pencil", "CS-PENCIL", "Carbon Stick", {"pencil", "carbon-stick"}, set()),
    ("G2-rim", "RIM-17", "CS Rim 17", {"wheel"}, set()),
    ("G2-tyre", "TYRE-17", "CS Tire 17", {"tyre"}, set()),
    ("G3-table", "NS-TABLE", "NSUDLK TEST", {"table"}, set()),
    ("G3-nail", "NS-NAIL", "NSUDLK TEST", {"nail"}, set()),
    ("G4-condition", "CONDITION-01", "Condition", {"commercial-condition"}, set()),
    ("G4-discount", "DISCOUNT-01", "Condition", {"commercial-discount"}, set()),
    ("G5-clutch", "CLUTCHDISK", "Dust Cap", {"clutch-disk", "dust-cap"}, set()),
    ("G5-dust", "DUSTCAP", "Dust Cap", {"dust-cap"}, set()),
    ("G5-coil", "COILSPRING", "Dust Cap", {"coil-spring", "dust-cap"}, set()),
    ("G6-left", "SHOCK-LH", "Left Side Shock", set(), {"left"}),
    ("G6-right", "SHOCK-RH", "Left Side Shock", set(), {"left", "right"}),
    ("G7-buffer", "BUFFER01", "Condition Part", {"buffer"}, set()),
    ("G7-mirror", "MIRROR01", "Condition Part", {"mirror"}, set()),
    ("G8-brush", "XX-BRUSH", "Exercise 3", set(), set()),
    ("G8-paint", "XX-PAINT", "Exercise 3", set(), set()),
    ("G9-model-s", "NE01-MODEL-S", "Model S", set(), set()),
    ("G9-model-x", "NE01-MODEL-X", "Model S", set(), set()),
    ("G10-wood", "NS-WOOD", "NSUDLK TEST", set(), set()),
    ("G10-steel", "NS-STEELFRAME", "NSUDLK TEST", set(), set()),
    ("G11-coil", "AUTO01 COILSPRING", "Coil Spring", {"coil-spring"}, set()),
    ("G11-staplers", "AUTO01 STAPLERS", "Coil Spring", {"coil-spring"}, set()),
)


@pytest.mark.parametrize(
    ("case_id", "part_no", "description", "expected_objects", "expected_sides"),
    HISTORICAL_GOLDENS,
    ids=[item[0] for item in HISTORICAL_GOLDENS],
)
def test_historical_golden_derivation_preserves_recognized_and_unresolved_evidence(
    case_id, part_no, description, expected_objects, expected_sides
):
    signature = derive_identity_signature(
        record(part_no, description, record_ref_key=case_id)
    )
    assert values(signature, "object_construct_observations") == expected_objects
    assert expected_sides <= values(signature, "variant_observations")
    assert signature.derivation_version == IDENTITY_SIGNATURE_DERIVATION_VERSION
    assert all(
        item.state == IdentityObservationState.UNRESOLVED
        for item in signature.unresolved_observations
    )
    assert any(
        "DESCRIPTION_MASTER_MATCH" in source.provenance_code
        for item in signature.unresolved_observations
        for source in item.sources
    )


@pytest.mark.parametrize(
    ("part_no", "expected"),
    (
        ("XX-BRUSH", "brush"),
        ("XX-PAINT", "paint"),
        ("NS-WOOD", "wood"),
        ("NS-STEELFRAME", "steelframe"),
        ("AUTO01 STAPLERS", "staplers"),
    ),
)
def test_r12_unknown_part_number_identity_is_bounded_unresolved(part_no, expected):
    signature = derive_identity_signature(record(part_no, "Copied Description"))
    matching = [
        item for item in signature.unresolved_observations
        if item.semantic_key == "unresolved_identity_token"
        and item.normalized_value == expected
    ]
    assert len(matching) == 1
    assert matching[0].sources[0].source_field == IdentitySourceField.PART_NUMBER
    assert IdentitySemanticCategory.OBJECT_OR_CONSTRUCT in signature.unknown_categories


def test_r12_single_character_model_qualifier_stays_unresolved():
    signature = derive_identity_signature(record("NE01-MODEL-X", "Model S"))
    assert "model x" in unresolved_values(signature, key="unresolved_model_or_type")
    assert "model s" in unresolved_values(signature, key="unresolved_model_or_type")
    assert "x" not in values(signature, "model_type_observations")
    assert "s" not in values(signature, "model_type_observations")


def test_r12_literals_are_absent_from_production_derivation_source():
    source = inspect.getsource(__import__(
        "app.engine.identity_signature_derivation", fromlist=["unused"]
    )).casefold()
    prohibited = (
        "brush", "paint", "model s", "model x", "wood", "steel-frame",
        "steelframe", "staplers", "xx-brush", "ne01-model-s",
    )
    assert not any(value in source for value in prohibited)


POSITIVE_CONTROLS = (
    ("P1", "CC-100", "Contact Cleaner"),
    ("P2", "TLO-68", "Turbine Lubricating Oil"),
    ("P3", "FT-LB-1", "Francis Turbine Lower Bearing"),
    ("P4", "PUMP-X500", "Pump X500"),
    ("P5", "FAN-BLADE-A", "Fan Blade"),
    ("P6", "F30", "F30 Compressor Rotor"),
    ("P7", "B38", "B38 Engine Block"),
)


@pytest.mark.parametrize(
    ("case_id", "part_no", "description"),
    POSITIVE_CONTROLS,
    ids=[item[0] for item in POSITIVE_CONTROLS],
)
def test_positive_controls_derive_deterministic_nonempty_representation(
    case_id, part_no, description
):
    signature = derive_identity_signature(
        record(part_no, description, record_ref_key=case_id)
    )
    assert signature.signature_fingerprint
    assert (
        signature.object_construct_observations
        or signature.assembly_component_role_observations
        or signature.model_type_observations
        or signature.variant_observations
        or signature.critical_attribute_observations
        or signature.unresolved_observations
    )


def test_p8_different_part_numbers_same_identity_are_not_adjudicated():
    left = derive_identity_signature(record("PUMP-A100", "Pump X500", record_ref_key="P8-a"))
    right = derive_identity_signature(record("PUMP-Z900", "Pump X500", record_ref_key="P8-b"))
    assert "x500" in values(left, "model_type_observations")
    assert "x500" in values(right, "model_type_observations")
    assert not hasattr(left, "contradictions")


def test_p9_cross_site_context_does_not_change_physical_signature():
    left_record = record("PUMP-X500", "Pump X500", record_ref_key="P9", contract="S1")
    right_record = {**left_record, "CONTRACT": "S2"}
    assert derive_identity_signature(left_record) == derive_identity_signature(right_record)


def test_p10_aliases_reuse_current_canonical_object_class():
    rim = derive_identity_signature(record("RIM-17", "Rim 17", record_ref_key="P10-rim"))
    wheel = derive_identity_signature(record("WHEEL-17", "Wheel 17", record_ref_key="P10-wheel"))
    assert values(rim, "object_construct_observations") == {
        "wheel"
    } == values(wheel, "object_construct_observations")


def test_p11_missing_identity_fields_are_explicit_unknown():
    signature = derive_identity_signature(record(record_ref_key="P11"))
    assert set(signature.unknown_categories) == set(IdentitySemanticCategory)
    assert signature.unresolved_observations == ()


def test_p12_generic_copied_description_is_metadata_not_recognized_identity():
    signature = derive_identity_signature(record("", "ITEM", record_ref_key="P12"))
    assert "generic-description" in unresolved_values(
        signature, key="description_reliability"
    )
    assert not signature.object_construct_observations
    assert any(
        "GENERIC" in source.provenance_code
        for item in signature.unresolved_observations
        for source in item.sources
    )


def test_m1_field_ordering_does_not_alter_signature():
    first = record("PUMP-X500", "Pump X500", record_ref_key="M1")
    second = dict(reversed(tuple(first.items())))
    assert derive_identity_signature(first) == derive_identity_signature(second)


def test_m2_observation_order_is_canonical_in_fingerprint():
    derived = derive_identity_signature(
        record("F30", "F30 Compressor Rotor 24V 10MM", record_ref_key="M2")
    )
    reordered = with_identity_signature_fingerprint(replace(
        derived,
        assembly_component_role_observations=tuple(reversed(
            derived.assembly_component_role_observations
        )),
        model_type_observations=tuple(reversed(derived.model_type_observations)),
        critical_attribute_observations=tuple(reversed(
            derived.critical_attribute_observations
        )),
        unresolved_observations=tuple(reversed(derived.unresolved_observations)),
        signature_fingerprint="",
    ))
    assert derived == reordered
    assert derived.signature_fingerprint == reordered.signature_fingerprint


def test_m3_casing_and_spacing_follow_existing_normalization():
    left = record(" pump-x500 ", "  Pump   X500 ", record_ref_key="M3")
    right = record("PUMP-X500", "PUMP X500", record_ref_key="M3")
    assert derive_identity_signature(left) == derive_identity_signature(right)


def test_m4_site_change_alone_does_not_rewrite_identity():
    base = record("F30", "F30 Compressor Rotor", record_ref_key="M4")
    assert derive_identity_signature(base) == derive_identity_signature(
        {**base, "CONTRACT": "OTHER"}
    )


def test_m5_missing_optional_field_creates_no_contradiction_or_failure():
    value = record("F30", "F30 Compressor", record_ref_key="M5")
    value.pop("TYPE_DESIGNATION")
    signature = derive_identity_signature(value)
    assert signature.signature_fingerprint
    assert not hasattr(signature, "contradictions")


def test_m6_unknown_noun_does_not_become_recognized_object_class():
    signature = derive_identity_signature(record("ZZ-QUUX", "Quux", record_ref_key="M6"))
    assert not signature.object_construct_observations
    assert "quux" in unresolved_values(signature)


def test_m7_arbitrary_part_number_residual_does_not_create_contradiction():
    left = derive_identity_signature(record("BASE-ALPHA", "Generic 10", record_ref_key="M7-a"))
    right = derive_identity_signature(record("BASE-OMEGA", "Generic 10", record_ref_key="M7-b"))
    assert "alpha" in unresolved_values(left)
    assert "omega" in unresolved_values(right)
    assert not hasattr(left, "contradictions") and not hasattr(right, "contradictions")


def test_m8_copied_description_provenance_remains_visible():
    signature = derive_identity_signature(record("A-1", "Copied Text", record_ref_key="M8"))
    assert "description-master-identical" in unresolved_values(
        signature, key="description_reliability"
    )


def test_m9_repeated_identical_evidence_is_canonicalized():
    signature = derive_identity_signature(record("RIM", "Rim", record_ref_key="M9"))
    wheel = [
        item for item in signature.object_construct_observations
        if item.normalized_value == "wheel"
    ]
    assert len(wheel) == 1
    assert {source.source_field for source in wheel[0].sources} == {
        IdentitySourceField.PART_NUMBER,
        IdentitySourceField.DESCRIPTION,
        IdentitySourceField.MASTER_DESCRIPTION,
    }


def test_m10_repeated_derivation_is_fingerprint_stable():
    value = record("PUMP-X500", "Pump X500 24V", record_ref_key="M10")
    assert derive_identity_signature(value).signature_fingerprint == (
        derive_identity_signature(value).signature_fingerprint
    )


def test_unresolved_evidence_is_bounded_per_source_and_token_length():
    text = " ".join(f"unknownidentitytoken{index}" for index in range(20))
    signature = derive_identity_signature(record(text, "", record_ref_key="bounded"))
    part_unresolved = [
        item for item in signature.unresolved_observations
        if item.semantic_key == "unresolved_identity_token"
        and item.sources[0].source_field == IdentitySourceField.PART_NUMBER
    ]
    assert len(part_unresolved) <= MAX_UNRESOLVED_OBSERVATIONS_PER_SOURCE
    assert all(len(item.normalized_value) <= 32 for item in part_unresolved)


def test_record_reference_is_required_and_derivation_has_no_pair_input():
    with pytest.raises(ValueError, match="record_reference"):
        derive_identity_signature({"PART_NO": "A", "DESCRIPTION": "Item"})
    parameters = inspect.signature(derive_identity_signature).parameters
    assert tuple(parameters) == ("record", "record_reference")


def test_offline_audit_counts_coverage_without_persistence_or_pair_evaluation():
    rows = [
        record("RIM-17", "Rim 17", record_ref_key="ignored-a"),
        record("ZZ-QUUX", "ITEM", record_ref_key="ignored-b"),
    ]
    result = audit_identity_signatures(rows, target_part_numbers=("RIM-17",))
    assert result["records_derived"] == 2
    assert result["unique_signature_fingerprints"] == 2
    assert result["recognized_object_construct_record_count"] == 1
    assert result["records_with_unresolved_observations"] == 2
    assert result["failure_count"] == 0
    assert set(result["target_signatures"]) == {"RIM-17"}
