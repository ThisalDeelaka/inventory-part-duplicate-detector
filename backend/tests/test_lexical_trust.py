import json

from app.engine.identity_edge import IdentityEdgeClass
from app.engine.identity_evidence_evaluator import (
    DeterministicIdentityContext,
    evaluate_canonical_identity_relationship,
)
from app.engine.lexical_trust import (
    LEXICAL_TRUST_ASSESSMENT_VERSION,
    PART_NUMBER_COHERENCE_FLOOR,
    assess_lexical_trust,
)
from app.services.canonical_record_service import CanonicalScanRecord


CONTEXT = DeterministicIdentityContext("DISCOVERY", ("CONTRACT", "UNIT_MEAS"))


def record(record_id, part_no, description, *, type_code="Purchased"):
    return CanonicalScanRecord(
        record_id=record_id,
        scan_id=1,
        source_row_index=record_id - 1,
        record_ref_key=f"record-{record_id}",
        source_record_fingerprint=f"source-{record_id}",
        part_no=part_no,
        description=description,
        contract="S1",
        uom="PCS",
        type_code=type_code,
        prime_commodity=None,
        second_commodity=None,
        accounting_group=None,
        part_product_code=None,
        part_product_family=None,
        product_category_id=None,
        hsn_sac_code=None,
        hazard_code=None,
        normalized_part_no=part_no.casefold(),
        normalized_description=description.casefold(),
        normalization_version="r18c-test-v1",
    )


def assessment(left, right, *, part=50.0, description=100.0):
    def payload(item):
        return {
            "PART_NO": item.part_no,
            "DESCRIPTION": item.description,
            "TYPE_CODE": item.type_code,
        }

    return assess_lexical_trust(
        payload(left), payload(right),
        {
            "part_no_similarity": part,
            "description_similarity": description,
            "generic_description_warning": False,
        },
        record_reference_a=left.record_ref_key,
        record_reference_b=right.record_ref_key,
    )


def test_assessment_is_deterministic_and_orientation_stable():
    left = record(1, "XX-BRUSH", "Exercise 3")
    right = record(2, "XX-PAINT", "Exercise 3")
    first = assessment(left, right)
    assert first == assessment(left, right) == assessment(right, left)
    assert first.version == LEXICAL_TRUST_ASSESSMENT_VERSION
    assert first.requires_strong_downgrade
    assert first.risk_reasons == ("LEXICAL_SUPPORT_NOT_INDEPENDENT",)


def test_substantial_part_number_coherence_preserves_lexical_alias():
    left = record(1, "AG-LOT-TRACKED-1", "Lot tracked part")
    right = record(2, "AG-LOT-TRACKED", "Lot tracked part")
    value = assessment(
        left, right, part=PART_NUMBER_COHERENCE_FLOOR
    )
    assert value.part_family_coherence
    assert not value.requires_strong_downgrade


def test_populated_cross_field_incoherence_is_caution_not_conflict():
    left = record(1, "CHW-P-2", "CHW part 2", type_code="Purchased")
    right = record(2, "CHW-IP-2", "CHW part 2", type_code="Manufactured")
    value = assessment(left, right, part=95.0)
    assert value.cross_field_incoherence
    assert value.risk_reasons == ("CROSS_FIELD_IDENTITY_INCOHERENCE",)
    relationship = evaluate_canonical_identity_relationship(left, right, CONTEXT)
    assert relationship.edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert "CROSS_FIELD_IDENTITY_INCOHERENCE" in relationship.classification_reason_codes


def test_missing_type_is_not_treated_as_match_or_incoherence():
    left = record(1, "A", "copied description", type_code=None)
    right = record(2, "B", "copied description", type_code="Purchased")
    value = assessment(left, right)
    assert not value.cross_field_incoherence
    assert not value.independent_identity_support_present
    assert value.requires_strong_downgrade


def test_runtime_downgrade_is_auditable_and_never_promotes():
    left = record(1, "KR-BU01", "Bottle unit 01")
    right = record(2, "GR-BOTTLE-UNIT-01", "Bottle unit 01")
    value = evaluate_canonical_identity_relationship(left, right, CONTEXT)
    trust = json.loads(value.technical_evidence_json)["lexical_trust_assessment"]
    assert value.edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert trust["requires_strong_downgrade"] is True
    assert trust["risk_reasons"] == ["LEXICAL_SUPPORT_NOT_INDEPENDENT"]


def test_trusted_typed_identity_support_is_preserved():
    left = record(1, "WHEEL-18-A", "Wheel 18")
    right = record(2, "WHL-18-B", "Wheel 18")
    value = assessment(left, right, part=50.0)
    assert value.independent_identity_support_present
    assert not value.requires_strong_downgrade


def test_cross_field_identity_anchor_preserves_legitimate_lexical_alias():
    left = record(1, "SEAL-32-A", "Mechanical seal for pump shaft 32 mm")
    right = record(2, "MECH-SEAL-32B", "Pump mechanical seal 32mm shaft")
    value = assessment(left, right, part=66.67, description=91.57)
    assert value.cross_field_identity_anchor_present
    assert value.independent_identity_support_present
    assert not value.requires_strong_downgrade
    assert evaluate_canonical_identity_relationship(
        left, right, CONTEXT
    ).edge_class == IdentityEdgeClass.STRONG_SUPPORT


def test_bounded_compact_model_alias_preserves_existing_identity_group():
    left = record(1, "A", "MCB30A")
    right = record(2, "B", "MCB 30 A")
    value = assessment(left, right, part=0.0)
    assert value.bounded_model_alias_present
    assert not value.requires_strong_downgrade
    assert evaluate_canonical_identity_relationship(
        left, right, CONTEXT
    ).edge_class == IdentityEdgeClass.STRONG_SUPPORT


def test_exact_generic_guard_and_cannot_link_are_unchanged():
    generic = evaluate_canonical_identity_relationship(
        record(1, "A", "BEARING"), record(2, "B", "BEARING"), CONTEXT
    )
    conflict = evaluate_canonical_identity_relationship(
        record(3, "PUMP L/S", "Pump"), record(4, "PUMP R/S", "Pump"), CONTEXT
    )
    assert generic.edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert generic.rejection_reason == "GENERIC_DESCRIPTION"
    assert conflict.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert json.loads(conflict.technical_evidence_json)["lexical_trust_assessment"] is None
