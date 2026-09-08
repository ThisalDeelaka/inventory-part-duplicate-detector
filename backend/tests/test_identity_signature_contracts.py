import dataclasses
from dataclasses import FrozenInstanceError, replace

import pytest

from app.engine.identity_signature import (
    IDENTITY_SIGNATURE_CONTRACT_VERSION,
    SIGNED_IDENTITY_EVIDENCE_CONTRACT_VERSION,
    IdentityObservation,
    IdentityObservationState,
    IdentitySemanticCategory,
    IdentitySignature,
    IdentitySourceField,
    SignedEvidenceChannel,
    SignedEvidenceFact,
    SignedIdentityEvidence,
    SourceObservation,
    canonical_identity_json,
    with_identity_signature_fingerprint,
    with_signed_identity_evidence_fingerprint,
)


DERIVATION_VERSION = "r14-golden-fixture-v1"


def source(field, *values, provenance="EXPLICIT_TEST_OBSERVATION"):
    return SourceObservation(field, tuple(values), provenance)


def observation(category, key, value, *sources, state=IdentityObservationState.OBSERVED):
    return IdentityObservation(
        category, key, value, state, tuple(sources), f"TEST_{state.value}"
    )


def empty_signature(reference, **changes):
    values = {
        "contract_version": IDENTITY_SIGNATURE_CONTRACT_VERSION,
        "derivation_version": DERIVATION_VERSION,
        "record_reference": reference,
        "object_construct_observations": (),
        "assembly_component_role_observations": (),
        "model_type_observations": (),
        "variant_observations": (),
        "critical_attribute_observations": (),
        "unresolved_observations": (),
        "unknown_categories": (),
    }
    values.update(changes)
    return with_identity_signature_fingerprint(IdentitySignature(**values))


def category_field(category):
    return {
        IdentitySemanticCategory.OBJECT_OR_CONSTRUCT: "object_construct_observations",
        IdentitySemanticCategory.ASSEMBLY_COMPONENT_ROLE: (
            "assembly_component_role_observations"
        ),
        IdentitySemanticCategory.MODEL_TYPE_IDENTITY: "model_type_observations",
        IdentitySemanticCategory.VARIANT_IDENTITY: "variant_observations",
        IdentitySemanticCategory.CRITICAL_IDENTITY_ATTRIBUTE: (
            "critical_attribute_observations"
        ),
    }[category]


def signature_with_fact(reference, category, key, value, field=IdentitySourceField.PART_NUMBER):
    item = observation(category, key, value, source(field, value))
    return empty_signature(reference, **{category_field(category): (item,)})


def signed(left, right, *facts):
    return with_signed_identity_evidence_fingerprint(SignedIdentityEvidence(
        contract_version=SIGNED_IDENTITY_EVIDENCE_CONTRACT_VERSION,
        record_reference_1=left.record_reference,
        record_reference_2=right.record_reference,
        signature_version_1=left.contract_version,
        signature_version_2=right.contract_version,
        signature_fingerprint_1=left.signature_fingerprint,
        signature_fingerprint_2=right.signature_fingerprint,
        facts=tuple(facts),
    ))


def lexical_fact(text):
    observed = source(IdentitySourceField.DESCRIPTION, text, provenance="COPIED_TEXT")
    return SignedEvidenceFact(
        SignedEvidenceChannel.LEXICAL_SUPPORT,
        IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
        "description_similarity",
        "normalized description text matches",
        (observed,),
        (observed,),
        (text,),
        "TEST_LEXICAL_MATCH_ONLY",
    )


HISTORICAL_CASES = (
    ("G1", "carbon-stick", "pencil", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "copied carbon stick"),
    ("G2", "rim", "tyre", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "wheel size 17"),
    ("G3", "table", "nail", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "test item"),
    ("G4", "condition", "discount", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "commercial condition"),
    ("G5", "clutch-disk", "dust-cap", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "dust cap"),
    ("G6", "left", "right", IdentitySemanticCategory.VARIANT_IDENTITY, "shock absorber left"),
    ("G7", "buffer", "mirror", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "condition part"),
    ("G8", "brush", "paint", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "exercise 3"),
    ("G9", "model-s", "model-x", IdentitySemanticCategory.MODEL_TYPE_IDENTITY, "model s"),
    ("G10", "wood", "steel-frame", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "nsudlk test"),
    ("G11", "coil-spring", "staplers", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT, "coil spring"),
)


@pytest.mark.parametrize(
    ("case_id", "left_value", "right_value", "category", "copied_text"),
    HISTORICAL_CASES,
    ids=[item[0] for item in HISTORICAL_CASES],
)
def test_g1_g11_historical_cases_preserve_identity_and_copied_lexical_provenance(
    case_id, left_value, right_value, category, copied_text
):
    left = signature_with_fact(f"{case_id}-left", category, "identity", left_value)
    right = signature_with_fact(f"{case_id}-right", category, "identity", right_value)
    evidence = signed(left, right, lexical_fact(copied_text))

    assert left_value != right_value
    assert getattr(left, category_field(category))[0].normalized_value == left_value
    assert getattr(right, category_field(category))[0].normalized_value == right_value
    assert evidence.facts[0].channel == SignedEvidenceChannel.LEXICAL_SUPPORT
    assert evidence.facts[0].source_observations_1[0].provenance_code == "COPIED_TEXT"
    assert not any(
        fact.channel == SignedEvidenceChannel.IDENTITY_CONTRADICTION
        for fact in evidence.facts
    ), "R14 represents facts; it does not pretend to detect the historical conflict"


def test_g5_three_member_family_preserves_each_object_observation_independently():
    category = IdentitySemanticCategory.OBJECT_OR_CONSTRUCT
    values = ("clutch-disk", "dust-cap", "coil-spring")
    signatures = tuple(
        signature_with_fact(f"G5-{index}", category, "identity", value)
        for index, value in enumerate(values, start=1)
    )
    assert tuple(
        item.object_construct_observations[0].normalized_value
        for item in signatures
    ) == values


POSITIVE_CASES = (
    ("P1", "contact-cleaner", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT),
    ("P2", "turbine-lubricating-oil", IdentitySemanticCategory.OBJECT_OR_CONSTRUCT),
    ("P3", "francis-turbine-lower-bearing", IdentitySemanticCategory.ASSEMBLY_COMPONENT_ROLE),
    ("P4", "pump-x500", IdentitySemanticCategory.MODEL_TYPE_IDENTITY),
    ("P5", "fan-blade", IdentitySemanticCategory.ASSEMBLY_COMPONENT_ROLE),
    ("P6", "f30", IdentitySemanticCategory.MODEL_TYPE_IDENTITY),
    ("P7", "b38", IdentitySemanticCategory.MODEL_TYPE_IDENTITY),
)


@pytest.mark.parametrize(
    ("case_id", "value", "category"),
    POSITIVE_CASES,
    ids=[item[0] for item in POSITIVE_CASES],
)
def test_p1_p7_positive_controls_represent_explicit_identity_support(
    case_id, value, category
):
    left = signature_with_fact(f"{case_id}-a", category, "canonical_identity", value)
    right = signature_with_fact(
        f"{case_id}-b", category, "canonical_identity", value,
        IdentitySourceField.DESCRIPTION,
    )
    fact = SignedEvidenceFact(
        SignedEvidenceChannel.IDENTITY_SUPPORT,
        category,
        "canonical_identity",
        "canonical identity agrees",
        getattr(left, category_field(category))[0].sources,
        getattr(right, category_field(category))[0].sources,
        (value,),
        "TEST_EXPLICIT_IDENTITY_AGREEMENT",
    )
    evidence = signed(left, right, fact)
    assert {item.channel for item in evidence.facts} == {
        SignedEvidenceChannel.IDENTITY_SUPPORT
    }


def test_p8_same_identity_with_different_part_numbers_is_not_a_contradiction():
    identity = IdentitySemanticCategory.OBJECT_OR_CONSTRUCT
    left = signature_with_fact("P8-a-part-100", identity, "object", "pump")
    right = signature_with_fact("P8-b-part-900", identity, "object", "pump")
    evidence = signed(left, right, SignedEvidenceFact(
        SignedEvidenceChannel.IDENTITY_SUPPORT, identity, "object",
        "canonical object agrees despite different references",
        left.object_construct_observations[0].sources,
        right.object_construct_observations[0].sources,
        ("pump",), "TEST_DIFFERENT_PART_NUMBERS_COMPATIBLE",
    ))
    assert evidence.facts[0].channel == SignedEvidenceChannel.IDENTITY_SUPPORT


def test_p9_cross_site_same_identity_keeps_site_context_non_authoritative():
    category = IdentitySemanticCategory.OBJECT_OR_CONSTRUCT
    left = signature_with_fact("P9-site-a", category, "object", "valve")
    right = signature_with_fact("P9-site-b", category, "object", "valve")
    site_a = source(
        IdentitySourceField.OTHER_EXISTING_BOUNDED_SOURCE, "site-a", provenance="SITE_CONTEXT"
    )
    site_b = source(
        IdentitySourceField.OTHER_EXISTING_BOUNDED_SOURCE, "site-b", provenance="SITE_CONTEXT"
    )
    fact = SignedEvidenceFact(
        SignedEvidenceChannel.IDENTITY_SUPPORT, category, "object",
        "physical identity agrees across context", (site_a,), (site_b,),
        ("valve",), "TEST_CROSS_SITE_IDENTITY",
    )
    assert signed(left, right, fact).facts[0].channel != (
        SignedEvidenceChannel.IDENTITY_CONTRADICTION
    )


def test_p10_aliases_preserve_distinct_sources_and_canonical_identity():
    category = IdentitySemanticCategory.OBJECT_OR_CONSTRUCT
    first = observation(
        category, "object", "wheel",
        source(IdentitySourceField.PART_NUMBER, "rim"),
        source(IdentitySourceField.DESCRIPTION, "wheel"),
    )
    signature = empty_signature("P10", object_construct_observations=(first,))
    assert len(signature.object_construct_observations[0].sources) == 2
    assert {item.source_field for item in signature.object_construct_observations[0].sources} == {
        IdentitySourceField.PART_NUMBER, IdentitySourceField.DESCRIPTION
    }


def test_p11_missing_identity_fields_are_explicit_unknown_not_contradiction():
    signature = empty_signature(
        "P11", unknown_categories=(IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,)
    )
    assert signature.unknown_categories == (
        IdentitySemanticCategory.OBJECT_OR_CONSTRUCT,
    )
    assert signature.unresolved_observations == ()


def test_p12_generic_copied_description_stays_lexical_with_unknown_identity():
    category = IdentitySemanticCategory.OBJECT_OR_CONSTRUCT
    left = empty_signature("P12-a", unknown_categories=(category,))
    right = empty_signature("P12-b", unknown_categories=(category,))
    evidence = signed(left, right, lexical_fact("generic copied item"))
    assert tuple(item.channel for item in evidence.facts) == (
        SignedEvidenceChannel.LEXICAL_SUPPORT,
    )
    assert left.unknown_categories == right.unknown_categories == (category,)


def test_contracts_are_frozen_versioned_and_have_no_runtime_decision_fields():
    contract_types = (
        SourceObservation, IdentityObservation, IdentitySignature,
        SignedEvidenceFact, SignedIdentityEvidence,
    )
    for contract_type in contract_types:
        assert dataclasses.is_dataclass(contract_type)
        assert contract_type.__dataclass_params__.frozen is True
    value = empty_signature("immutable")
    with pytest.raises(FrozenInstanceError):
        value.record_reference = "changed"
    forbidden = {"threshold", "edge_class", "support_gate_result", "runtime_status"}
    assert not forbidden & {field.name for field in dataclasses.fields(IdentitySignature)}
    assert not forbidden & {field.name for field in dataclasses.fields(SignedIdentityEvidence)}


def test_unknown_unresolved_and_explicit_contradiction_are_three_distinct_states():
    category = IdentitySemanticCategory.VARIANT_IDENTITY
    unresolved = observation(
        category, "side", "left|right",
        source(IdentitySourceField.PART_NUMBER, "left"),
        source(IdentitySourceField.DESCRIPTION, "right"),
        state=IdentityObservationState.UNRESOLVED,
    )
    signature = empty_signature(
        "states", unresolved_observations=(unresolved,), unknown_categories=(category,)
    )
    contradiction = SignedEvidenceFact(
        SignedEvidenceChannel.IDENTITY_CONTRADICTION, category, "side",
        "recognized protected variants are incompatible",
        unresolved.sources[:1], unresolved.sources[1:], ("left", "right"),
        "TEST_EXPLICIT_PROTECTED_CONTRADICTION",
    )
    assert signature.unknown_categories == (category,)
    assert signature.unresolved_observations[0].state == IdentityObservationState.UNRESOLVED
    assert contradiction.channel == SignedEvidenceChannel.IDENTITY_CONTRADICTION


def test_signed_channels_remain_independent_and_are_never_collapsed_to_a_score():
    category = IdentitySemanticCategory.CRITICAL_IDENTITY_ATTRIBUTE
    base = dict(
        semantic_category=category,
        semantic_key="rated_voltage",
        source_observations_1=(source(IdentitySourceField.DIMENSION_QUALITY, "24v"),),
        source_observations_2=(source(IdentitySourceField.TYPE_DESIGNATION, "24v"),),
        normalized_matches=("24v",),
    )
    facts = tuple(
        SignedEvidenceFact(
            channel, observed_fact=f"fact for {channel.value}",
            reason_code=f"TEST_{channel.value}", **base
        )
        for channel in SignedEvidenceChannel
    )
    left = empty_signature("channels-a", unknown_categories=(category,))
    right = empty_signature("channels-b", unknown_categories=(category,))
    evidence = signed(left, right, *facts)
    assert {item.channel for item in evidence.facts} == set(SignedEvidenceChannel)
    assert "score" not in {field.name for field in dataclasses.fields(SignedIdentityEvidence)}


def test_collection_order_endpoint_orientation_and_fingerprints_are_deterministic():
    category = IdentitySemanticCategory.OBJECT_OR_CONSTRUCT
    first = observation(
        category, "object", "pump",
        source(IdentitySourceField.DESCRIPTION, "pump"),
        source(IdentitySourceField.PART_NUMBER, "pmp"),
    )
    second = observation(
        category, "construct", "physical-item",
        source(IdentitySourceField.TYPE_DESIGNATION, "physical-item"),
    )
    left = empty_signature(
        "A", object_construct_observations=(first, second),
        unknown_categories=(IdentitySemanticCategory.VARIANT_IDENTITY,
                            IdentitySemanticCategory.MODEL_TYPE_IDENTITY),
    )
    shuffled = empty_signature(
        "A", object_construct_observations=(second, first),
        unknown_categories=(IdentitySemanticCategory.MODEL_TYPE_IDENTITY,
                            IdentitySemanticCategory.VARIANT_IDENTITY),
    )
    assert left == shuffled
    assert left.signature_fingerprint == shuffled.signature_fingerprint
    right = signature_with_fact("B", category, "object", "pump")
    fact = lexical_fact("pump")
    forward = signed(left, right, fact)
    reverse = signed(right, left, replace(
        fact,
        source_observations_1=fact.source_observations_2,
        source_observations_2=fact.source_observations_1,
    ))
    assert forward == reverse
    assert forward.evidence_fingerprint == reverse.evidence_fingerprint
    assert canonical_identity_json(forward) == canonical_identity_json(reverse)


def test_multiple_conflicting_source_observations_coexist_without_silent_collapse():
    category = IdentitySemanticCategory.MODEL_TYPE_IDENTITY
    item = observation(
        category, "model", "unresolved-model",
        source(IdentitySourceField.PART_NUMBER, "model-x"),
        source(IdentitySourceField.DESCRIPTION, "model-s"),
        source(IdentitySourceField.MASTER_DESCRIPTION, "model-s"),
        state=IdentityObservationState.UNRESOLVED,
    )
    signature = empty_signature("multi-source", unresolved_observations=(item,))
    assert len(signature.unresolved_observations[0].sources) == 3
    assert {entry.normalized_evidence for entry in item.sources} == {
        ("model-x",), ("model-s",)
    }


def test_raw_token_and_part_number_difference_do_not_create_contradiction_implicitly():
    left = empty_signature("raw-part-a")
    right = empty_signature("raw-part-b")
    evidence = signed(left, right, lexical_fact("similar item"))
    assert all(
        item.channel != SignedEvidenceChannel.IDENTITY_CONTRADICTION
        for item in evidence.facts
    )
