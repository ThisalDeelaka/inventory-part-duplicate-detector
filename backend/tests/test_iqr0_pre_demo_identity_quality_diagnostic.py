"""IQR-0 characterization and explicit next-correction contracts.

These tests deliberately do not alter runtime semantics. Strict xfails name the
two required future behaviors so the correction phase cannot silently claim
that the current implementation already satisfies them.
"""

import pytest

from app.engine.identity_evidence_evaluator import (
    DeterministicIdentityContext,
    evaluate_canonical_identity_relationship,
)
from app.engine.identity_signature_derivation import derive_identity_signature
from app.engine.identity_edge import IdentityEdgeClass
from app.orchestration.contracts import (
    identity_discovery_scan_mode_for_orchestration,
)
from app.services.canonical_record_service import CanonicalScanRecord
from app.services.hybrid_retrieval import _allowed_pair


def engine_record(part_no, description, contract):
    return {
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "CONTRACT": contract,
        "UNIT_MEAS": "PCS",
    }


def canonical(record_id, part_no, description, contract="MRO"):
    return CanonicalScanRecord(
        record_id=record_id,
        scan_id=1,
        source_row_index=record_id,
        record_ref_key=f"record-{record_id}",
        source_record_fingerprint=f"source-{record_id}",
        part_no=part_no,
        description=description,
        contract=contract,
        uom="PCS",
        type_code="Purchased",
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
        normalization_version="iqr0-diagnostic-v1",
    )


def signature(part_no, description, reference):
    return derive_identity_signature(
        {
            "PART_NO": part_no,
            "DESCRIPTION": description,
            "MASTER_DESCRIPTION": None,
            "TYPE_DESIGNATION": None,
            "DIMENSION_QUALITY": None,
        },
        record_reference=reference,
    )


def test_iqr0_characterizes_site_as_legacy_pre_evidence_hard_boundary():
    left = engine_record("AB-BICYCLE", "Bicycle", "AB-SA")
    right = engine_record("SD-BICYCLE", "Bicycle", "SD-SA")

    assert not _allowed_pair(left, right, "SAME_SITE_DUPLICATE")
    assert _allowed_pair(left, right, "DISCOVERY")


def test_iqr0_future_contract_site_alone_cannot_block_identity_discovery():
    left = engine_record("AB-BICYCLE", "Bicycle", "AB-SA")
    right = engine_record("SD-BICYCLE", "Bicycle", "SD-SA")

    current_product_mode = identity_discovery_scan_mode_for_orchestration(
        "group_first_primary", "SAME_SITE_DUPLICATE"
    )

    assert current_product_mode == "DISCOVERY"
    assert _allowed_pair(left, right, current_product_mode)


def test_iqr0_characterizes_head_tail_as_unresolved_not_typed_identity_role():
    head = signature("AB-LIGHT", "LED Head Light", "head")
    tail = signature("AB-TAIL LIGHT", "LED Tail Light", "tail")

    assert not head.assembly_component_role_observations
    assert not head.variant_observations
    assert not tail.assembly_component_role_observations
    assert not tail.variant_observations
    assert "head" in {item.normalized_value for item in head.unresolved_observations}
    assert "tail" in {item.normalized_value for item in tail.unresolved_observations}


@pytest.mark.xfail(
    strict=True,
    reason="IQR-0: general functional/location-role extraction does not expose Head/Tail",
)
def test_iqr0_future_contract_head_tail_distinction_reaches_typed_evidence():
    head = signature("AB-LIGHT", "LED Head Light", "head")
    tail = signature("AB-TAIL LIGHT", "LED Tail Light", "tail")
    head_values = {
        item.normalized_value
        for item in head.assembly_component_role_observations + head.variant_observations
    }
    tail_values = {
        item.normalized_value
        for item in tail.assembly_component_role_observations + tail.variant_observations
    }

    assert "head" in head_values
    assert "tail" in tail_values


@pytest.mark.xfail(
    strict=True,
    reason="IQR-0: copied generic text can still independently create strong support",
)
def test_iqr0_future_contract_copied_generic_description_is_not_identity_proof():
    context = DeterministicIdentityContext(
        "SAME_SITE_DUPLICATE", ("CONTRACT", "UNIT_MEAS")
    )
    relationship = evaluate_canonical_identity_relationship(
        canonical(1, "XX-BRUSH", "Exercise 3"),
        canonical(2, "XX-PAINT", "Exercise 3"),
        context,
    )

    assert relationship.edge_class != IdentityEdgeClass.STRONG_SUPPORT


def test_iqr0_existing_general_cannot_link_safety_remains_intact():
    context = DeterministicIdentityContext(
        "SAME_SITE_DUPLICATE", ("CONTRACT", "UNIT_MEAS")
    )
    relationship = evaluate_canonical_identity_relationship(
        canonical(1, "PUMP L/S", "Pump"),
        canonical(2, "PUMP R/S", "Pump"),
        context,
    )

    assert relationship.edge_class == IdentityEdgeClass.CANNOT_LINK
