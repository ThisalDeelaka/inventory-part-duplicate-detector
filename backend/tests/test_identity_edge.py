from types import SimpleNamespace

import pytest

from app.engine.identity_edge import (
    IdentityEdgeClass,
    classify_identity_edge,
    group_has_cannot_link,
)
from app.engine.scoring import score_candidate


def record(part_number, description, *, uom="PCS"):
    return {
        "PART_NO": part_number,
        "DESCRIPTION": description,
        "CONTRACT": "S1",
        "UNIT_MEAS": uom,
        "HSN_SAC_CODE": "1000",
    }


def score(left, right, *, uom_a="PCS", uom_b="PCS"):
    return score_candidate(
        record("A", left, uom=uom_a),
        record("B", right, uom=uom_b),
        ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    )


def edge(left, right, **kwargs):
    result = score(left, right, **kwargs)
    return result, classify_identity_edge(result)


def test_mlr_bridge_cannot_erase_endpoint_conflict():
    endpoint_result, endpoint = edge(
        "MLR-TOP-02.28.2023", "MLR-COMPONENT-02.28.2023"
    )
    support = classify_identity_edge({
        "business_status": "POSSIBLE_DUPLICATE_REVIEW",
        "rule_decision": "ALLOW",
        "critical_mismatches": [],
    })
    assert endpoint_result["rejection_reason"] == "STRUCTURAL_ROLE_MISMATCH"
    assert endpoint.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert group_has_cannot_link(
        ["top", "bridge", "component"],
        {
            frozenset(("top", "bridge")): support,
            frozenset(("bridge", "component")): support,
            frozenset(("top", "component")): endpoint,
        },
    ) is True


def test_rotor_generic_stator_bridge_is_vetoed():
    _, rotor_stator = edge("F30 Compressor Rotor", "F30 Compressor Stator")
    _, rotor_generic = edge("F30 Compressor Rotor", "F30 Compressor")
    _, generic_stator = edge("F30 Compressor", "F30 Compressor Stator")
    assert rotor_stator.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert "CRITICAL_MISMATCH_STRUCTURAL_ROLE" in rotor_stator.reason_codes
    assert rotor_generic.edge_class != IdentityEdgeClass.CANNOT_LINK
    assert generic_stator.edge_class != IdentityEdgeClass.CANNOT_LINK
    assert group_has_cannot_link(
        ["rotor", "generic", "stator"],
        {
            frozenset(("rotor", "generic")): rotor_generic,
            frozenset(("generic", "stator")): generic_stator,
            frozenset(("rotor", "stator")): rotor_stator,
        },
    ) is True


@pytest.mark.parametrize(
    ("left", "right", "group"),
    [
        ("Motor Drive End Bearing", "Motor Non-Drive End Bearing", "END_POSITION"),
        ("Motor DE Bearing", "Motor NDE Bearing", "END_POSITION"),
        ("Rental Part Serial", "Rental Part Non Serial", "SERIALIZATION_ROLE"),
        ("Pump Inlet Valve", "Pump Outlet Valve", "FLOW_ROLE"),
        ("Left Pump Housing", "Right Pump Housing", "SIDE"),
        ("LH Pump Housing", "RH Pump Housing", "SIDE"),
    ],
)
def test_explicit_opposite_roles_are_cannot_links(left, right, group):
    result, classification = edge(left, right)
    assert classification.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert f"CRITICAL_MISMATCH_{group}" in classification.reason_codes
    assert result["critical_mismatches"][0]["group"] == group


@pytest.mark.parametrize(
    ("generic", "specific"),
    [
        ("Motor Bearing", "Motor DE Bearing"),
        ("Rental Part", "Rental Part Non Serial"),
        ("Pump Valve", "Pump Inlet Valve"),
        ("Compressor", "Compressor Rotor"),
    ],
)
def test_missing_role_is_not_an_opposite_role_conflict(generic, specific):
    result, classification = edge(generic, specific)
    assert classification.edge_class != IdentityEdgeClass.CANNOT_LINK
    assert not any(
        mismatch["group"] in {
            "END_POSITION", "SERIALIZATION_ROLE", "FLOW_ROLE", "STRUCTURAL_ROLE"
        }
        for mismatch in result["critical_mismatches"]
    )


def test_explicit_b38_engine_components_conflict_without_hardening_generic_engine():
    _, component_conflict = edge("B38 Engine Block", "B38 Engine Head")
    generic_result, generic_pair = edge("B38 Engine", "B38 Engine Block")
    assert component_conflict.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert component_conflict.reason_codes == (
        "CRITICAL_MISMATCH_ENGINE_COMPONENT_ROLE",
    )
    assert generic_pair.edge_class != IdentityEdgeClass.CANNOT_LINK
    assert not any(
        mismatch["group"] == "ENGINE_COMPONENT_ROLE"
        for mismatch in generic_result["critical_mismatches"]
    )


def test_de_and_nde_use_token_boundaries_and_are_orientation_stable():
    forward_result, forward = edge("Motor DE Bearing", "Motor NDE Bearing")
    reverse_result, reverse = edge("Motor NDE Bearing", "Motor DE Bearing")
    incidental_result, incidental = edge("Device Bearing", "Spindle Bearing")
    assert forward.edge_class == reverse.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert forward.reason_codes == reverse.reason_codes
    assert forward_result["critical_mismatches"][0]["values_a"] == ["drive-end"]
    assert reverse_result["critical_mismatches"][0]["values_a"] == ["non-drive-end"]
    assert incidental.edge_class != IdentityEdgeClass.CANNOT_LINK
    assert not incidental_result["critical_mismatches"]


def test_existing_top_component_dimension_and_rating_safety_remains():
    for left, right, reason in (
        ("TOP PART", "COMPONENT PART", "CRITICAL_MISMATCH_STRUCTURAL_ROLE"),
        ("Bearing 10MM", "Bearing 20MM", "CRITICAL_MISMATCH_DIMENSION"),
        ("Motor 10A", "Motor 20A", "CRITICAL_MISMATCH_ELECTRICAL_RATING"),
    ):
        _, classification = edge(left, right)
        assert classification.edge_class == IdentityEdgeClass.CANNOT_LINK
        assert reason in classification.reason_codes


def test_uom_difference_alone_never_creates_cannot_link():
    result, classification = edge(
        "Turbine Lubricating Oil", "Turbine Lubricating Oil", uom_a="l", uom_b="PCS"
    )
    assert not result["critical_mismatches"]
    assert classification.edge_class in {
        IdentityEdgeClass.STRONG_SUPPORT,
        IdentityEdgeClass.REVIEW_SUPPORT,
    }
    historical = classify_identity_edge({
        "business_status": "REJECTED_BY_BUSINESS_RULE",
        "rule_decision": "REJECT",
        "rejection_reason": "UNIT_MEAS_MISMATCH",
        "critical_mismatches": [{
            "group": "UNIT_MEAS", "values_a": ["l"], "values_b": ["PCS"]
        }],
    })
    assert historical.edge_class == IdentityEdgeClass.NON_GROUPABLE


def test_generic_text_and_context_only_are_never_strong_identity_support():
    left = record("A", "BEARING")
    right = record("B", "BEARING")
    left["ACCOUNTING_GROUP"] = right["ACCOUNTING_GROUP"] = "AG1"
    left["PRODUCT_CATEGORY_ID"] = right["PRODUCT_CATEGORY_ID"] = "CAT1"
    result = score_candidate(
        left, right,
        ["CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP", "PRODUCT_CATEGORY_ID"],
        allow_uom_mapping_review=True,
    )
    classification = classify_identity_edge(result)

    assert result["business_status"] == "POSSIBLE_DUPLICATE_REVIEW"
    assert classification.edge_class == IdentityEdgeClass.REVIEW_SUPPORT


def test_generic_text_with_strong_part_number_evidence_can_remain_strong():
    result = score_candidate(
        record("BRG-6205-A", "BEARING"),
        record("BRG6205A", "BEARING"),
        ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    )
    assert classify_identity_edge(result).edge_class == IdentityEdgeClass.STRONG_SUPPORT


@pytest.mark.parametrize("context_field", ["CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP"])
def test_context_difference_alone_does_not_create_cannot_link(context_field):
    left = record("A", "BEARING")
    right = record("B", "BEARING")
    left["ACCOUNTING_GROUP"] = right["ACCOUNTING_GROUP"] = "AG1"
    right[context_field] = "DIFFERENT"
    result = score_candidate(
        left, right, [context_field],
        allow_uom_mapping_review=True,
    )
    assert classify_identity_edge(result).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_human_feedback_precedence_and_unsure_semantics():
    strong = {
        "business_status": "LIKELY_DUPLICATE",
        "rule_decision": "ALLOW",
        "critical_mismatches": [],
    }
    assert classify_identity_edge(
        strong, feedback=SimpleNamespace(user_decision="NOT_DUPLICATE")
    ).edge_class == IdentityEdgeClass.CANNOT_LINK
    assert classify_identity_edge(
        strong, feedback=SimpleNamespace(user_decision="DUPLICATE")
    ).edge_class == IdentityEdgeClass.STRONG_SUPPORT
    assert classify_identity_edge(
        strong, feedback=SimpleNamespace(user_decision="UNSURE")
    ).reason_codes == ("DETERMINISTIC_LIKELY_DUPLICATE",)


def test_llm_support_cannot_override_critical_deterministic_conflict():
    result = score("F30 Compressor Rotor", "F30 Compressor Stator")
    result["llm_assessment"] = "SUPPORTS_DUPLICATE"
    classification = classify_identity_edge(result)
    assert classification.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert classification.reason_codes == ("CRITICAL_MISMATCH_STRUCTURAL_ROLE",)


def test_clean_review_and_non_identity_rules_have_conservative_classes():
    review = classify_identity_edge({
        "business_status": "POSSIBLE_DUPLICATE_REVIEW",
        "rule_decision": "ALLOW",
        "critical_mismatches": [],
    })
    cross_site = classify_identity_edge({
        "business_status": "CROSS_SITE_STANDARDIZATION_CANDIDATE",
        "rule_decision": "CROSS_SITE",
        "rejection_reason": "CONTRACT_MISMATCH_IN_SAME_SITE_MODE",
        "critical_mismatches": [{
            "group": "CONTRACT", "values_a": ["S1"], "values_b": ["S2"]
        }],
    })
    assert review.edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert cross_site.edge_class == IdentityEdgeClass.NON_GROUPABLE
