from dataclasses import replace

import pytest

from app.engine.identity_signature import (
    SignedEvidenceChannel,
    with_identity_signature_fingerprint,
    with_signed_identity_evidence_fingerprint,
)
from app.engine.identity_signature_derivation import derive_identity_signature
from app.engine.signed_identity_evidence import (
    SIGNED_IDENTITY_EVIDENCE_COMPARISON_VERSION,
    ShadowEvidenceBucket,
    classify_shadow_evidence,
    derive_signed_identity_evidence,
)


def record(ref, part_no, description, **values):
    return {
        "record_ref_key": ref,
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "MASTER_DESCRIPTION": values.pop("master", description),
        "TYPE_DESIGNATION": values.pop("type_designation", ""),
        "DIMENSION_QUALITY": values.pop("dimension_quality", ""),
        "CONTRACT": values.pop("contract", "S1"),
        **values,
    }


def compare(left, right):
    return derive_signed_identity_evidence(
        derive_identity_signature(left), derive_identity_signature(right)
    )


def channels(evidence):
    return {item.channel for item in evidence.facts}


PROTECTED_HISTORICAL = (
    ("H1", record("H1-a", "CS-CARBONSTICK", "Carbon Stick"), record("H1-b", "CS-PENCIL", "Carbon Stick")),
    ("H2", record("H2-a", "RIM-17", "Rim 17"), record("H2-b", "TYRE-17", "Tyre 17")),
    ("H3", record("H3-a", "NS-TABLE", "Test Item"), record("H3-b", "NS-NAIL", "Test Item")),
    ("H4", record("H4-a", "CONDITION-01", "Condition"), record("H4-b", "DISCOUNT-01", "Condition")),
    ("H5", record("H5-a", "CLUTCHDISK", "Dust Cap"), record("H5-b", "DUSTCAP", "Dust Cap")),
    ("H6", record("H6-a", "CLUTCHDISK", "Coil Spring"), record("H6-b", "COILSPRING", "Coil Spring")),
    ("H7", record("H7-a", "DUSTCAP", "Coil Spring"), record("H7-b", "COILSPRING", "Coil Spring")),
    ("H8", record("H8-a", "SHOCK-LH", "Left Side Shock"), record("H8-b", "SHOCK-RH", "Left Side Shock")),
    ("H9", record("H9-a", "BUFFER01", "Condition Part"), record("H9-b", "MIRROR01", "Condition Part")),
)


@pytest.mark.parametrize(
    ("case_id", "left", "right"), PROTECTED_HISTORICAL,
    ids=[item[0] for item in PROTECTED_HISTORICAL],
)
def test_h1_h9_existing_protected_families_emit_explicit_contradiction(
    case_id, left, right
):
    evidence = compare(left, right)
    assert SignedEvidenceChannel.IDENTITY_CONTRADICTION in channels(evidence)
    assert any(
        item.reason_code.startswith("SHADOW_EXISTING_")
        for item in evidence.facts
        if item.channel == SignedEvidenceChannel.IDENTITY_CONTRADICTION
    )


R12_HISTORICAL = (
    ("H10", record("H10-a", "XX-BRUSH", "Exercise 3"), record("H10-b", "XX-PAINT", "Exercise 3")),
    ("H11", record("H11-a", "NE01-MODEL-S", "Model S"), record("H11-b", "NE01-MODEL-X", "Model S")),
    ("H12", record("H12-a", "NS-WOOD", "NSUDLK TEST"), record("H12-b", "NS-STEELFRAME", "NSUDLK TEST")),
    ("H13", record("H13-a", "AUTO01 COILSPRING", "Coil Spring"), record("H13-b", "AUTO01 STAPLERS", "Coil Spring")),
)


@pytest.mark.parametrize(
    ("case_id", "left", "right"), R12_HISTORICAL,
    ids=[item[0] for item in R12_HISTORICAL],
)
def test_h10_h13_r12_pairs_stay_lexical_without_support_or_invented_conflict(
    case_id, left, right
):
    evidence = compare(left, right)
    assert SignedEvidenceChannel.LEXICAL_SUPPORT in channels(evidence)
    assert SignedEvidenceChannel.IDENTITY_SUPPORT not in channels(evidence)
    assert SignedEvidenceChannel.IDENTITY_CONTRADICTION not in channels(evidence)
    assert classify_shadow_evidence(evidence) == (
        ShadowEvidenceBucket.SHADOW_LEXICAL_ONLY_OR_UNRESOLVED
    )


POSITIVE_PAIRS = (
    ("P1", record("P1-a", "CC-A", "Contact Cleaner"), record("P1-b", "CC-B", "Contact Cleaner")),
    ("P2", record("P2-a", "TLO-A", "Turbine Lubricating Oil"), record("P2-b", "TLO-B", "Turbine Lubricating Oil")),
    ("P3", record("P3-a", "FT-A", "Francis Turbine Lower Bearing"), record("P3-b", "FT-B", "Francis Turbine Lower Bearing")),
    ("P4", record("P4-a", "PUMP-A", "Pump X500"), record("P4-b", "PUMP-B", "Pump X500")),
    ("P5", record("P5-a", "FAN-A", "Fan Blade"), record("P5-b", "FAN-B", "Fan Blade")),
    ("P6", record("P6-a", "F30-A", "F30 Compressor Rotor"), record("P6-b", "F30-B", "F30 Compressor Rotor")),
    ("P7", record("P7-a", "B38-A", "B38 Engine Block"), record("P7-b", "B38-B", "B38 Engine Block")),
    ("P8", record("P8-a", "RIM-A", "Rim 17"), record("P8-b", "WHEEL-B", "Wheel 17")),
    ("P9", record("P9-a", "RIM-A", "Rim 17", contract="S1"), record("P9-b", "WHEEL-B", "Wheel 17", contract="S2")),
    ("P10", record("P10-a", "RIM-A", ""), record("P10-b", "WHEEL-B", "Wheel")),
    ("P11", record("P11-a", "RIM-A", "ITEM"), record("P11-b", "WHEEL-B", "ITEM")),
    ("P12", record("P12-a", "AA-ALPHA", "Similar Name"), record("P12-b", "BB-BETA", "Similar Name")),
    ("P13", record("P13-a", "RIM-A", "Rim"), record("P13-b", "ZZ-QUUX", "Quux")),
    ("P14", record("P14-a", "BASE-ALPHA", "Unknown Item"), record("P14-b", "BASE-OMEGA", "Unknown Item")),
)


@pytest.mark.parametrize(
    ("case_id", "left", "right"), POSITIVE_PAIRS,
    ids=[item[0] for item in POSITIVE_PAIRS],
)
def test_p1_p14_legitimate_or_uncertain_variation_never_invents_contradiction(
    case_id, left, right
):
    assert SignedEvidenceChannel.IDENTITY_CONTRADICTION not in channels(
        compare(left, right)
    )


@pytest.mark.parametrize("case_id", ("P8", "P9", "P10", "P11"))
def test_alias_and_part_number_controls_expose_trusted_identity(case_id):
    _, left, right = next(item for item in POSITIVE_PAIRS if item[0] == case_id)
    assert SignedEvidenceChannel.IDENTITY_SUPPORT in channels(compare(left, right))


@pytest.mark.parametrize("case_id", ("P1", "P2", "P3", "P4", "P5", "P6", "P7"))
def test_named_positive_controls_expose_current_gate_readiness_risk(case_id):
    _, left, right = next(item for item in POSITIVE_PAIRS if item[0] == case_id)
    evidence = compare(left, right)
    assert SignedEvidenceChannel.IDENTITY_SUPPORT not in channels(evidence)
    assert classify_shadow_evidence(evidence) == (
        ShadowEvidenceBucket.SHADOW_LEXICAL_ONLY_OR_UNRESOLVED
    )


def test_m1_orientation_and_m4_repeated_fingerprint_are_stable():
    left, right = POSITIVE_PAIRS[7][1:]
    a = compare(left, right)
    b = compare(right, left)
    c = compare(left, right)
    assert a == b == c
    assert a.evidence_fingerprint == b.evidence_fingerprint == c.evidence_fingerprint


def test_m2_fact_construction_order_is_canonical():
    evidence = compare(*POSITIVE_PAIRS[7][1:])
    reordered = with_signed_identity_evidence_fingerprint(replace(
        evidence, facts=tuple(reversed(evidence.facts)), evidence_fingerprint=""
    ))
    assert evidence == reordered


def test_m3_signature_observation_order_is_canonical():
    left = derive_identity_signature(POSITIVE_PAIRS[7][1])
    right = derive_identity_signature(POSITIVE_PAIRS[7][2])
    shuffled = with_identity_signature_fingerprint(replace(
        left,
        object_construct_observations=tuple(reversed(left.object_construct_observations)),
        unresolved_observations=tuple(reversed(left.unresolved_observations)),
        signature_fingerprint="",
    ))
    assert derive_signed_identity_evidence(left, right) == (
        derive_signed_identity_evidence(shuffled, right)
    )


def test_m5_different_refs_preserve_same_semantic_facts():
    first = compare(record("M5-a", "RIM", "Rim"), record("M5-b", "WHEEL", "Wheel"))
    second = compare(record("M5-c", "RIM", "Rim"), record("M5-d", "WHEEL", "Wheel"))
    semantic = lambda value: tuple(
        (item.channel, item.semantic_key, item.normalized_matches, item.reason_code)
        for item in value.facts
    )
    assert semantic(first) == semantic(second)


def test_m6_unknown_unknown_m7_unknown_known_and_m8_residual_difference_are_safe():
    cases = (POSITIVE_PAIRS[13], POSITIVE_PAIRS[12])
    for _case, left, right in cases:
        assert SignedEvidenceChannel.IDENTITY_CONTRADICTION not in channels(
            compare(left, right)
        )


def test_m9_copied_lexical_agreement_is_not_identity_support_by_itself():
    evidence = compare(*POSITIVE_PAIRS[0][1:])
    assert SignedEvidenceChannel.LEXICAL_SUPPORT in channels(evidence)
    assert SignedEvidenceChannel.IDENTITY_SUPPORT not in channels(evidence)


def test_m10_site_only_difference_does_not_create_contradiction():
    evidence = compare(*POSITIVE_PAIRS[8][1:])
    assert SignedEvidenceChannel.IDENTITY_CONTRADICTION not in channels(evidence)


def test_m11_existing_protected_contradiction_remains_contradiction():
    assert SignedEvidenceChannel.IDENTITY_CONTRADICTION in channels(
        compare(*PROTECTED_HISTORICAL[0][1:])
    )


def test_m12_same_identity_and_attribute_difference_do_not_auto_contradict():
    evidence = compare(
        record("M12-a", "RIM-A", "Rim 10MM"),
        record("M12-b", "WHEEL-B", "Wheel 20MM"),
    )
    assert SignedEvidenceChannel.IDENTITY_SUPPORT in channels(evidence)
    assert SignedEvidenceChannel.IDENTITY_CONTRADICTION not in channels(evidence)
    assert SIGNED_IDENTITY_EVIDENCE_COMPARISON_VERSION == "signed-identity-comparison-v2"
