"""GF-12C1-R10 bounded directional-side identity acceptance tests."""

from __future__ import annotations

import inspect
import json

import pytest

from app.engine import identity_discriminator as discriminator_module
from app.engine.identity_discriminator import (
    evaluate_identity_discriminators,
    extract_record_discriminators,
)
from app.engine.identity_edge import IdentityEdgeClass, classify_identity_edge
from app.engine.identity_evidence_evaluator import (
    DeterministicIdentityContext,
    evaluate_canonical_identity_relationship,
)
from app.engine.scoring import score_candidate
from app.resolution.contracts import (
    IdentityResolutionEvidenceEdge,
    IdentityResolutionInput,
    IdentityResolutionNeighborhood,
    ResolverConfiguration,
)
from app.resolution.resolver import (
    CanonicalEvaluatorTargetedEvidenceProvider,
    resolve_identity_groups,
)
from app.services.canonical_record_service import CanonicalScanRecord


CONTEXT = DeterministicIdentityContext(
    "SAME_SITE_DUPLICATE", ("CONTRACT", "UNIT_MEAS")
)


def record(
    record_id: int,
    part_no: str,
    description: str,
    *,
    contract: str = "S1",
    uom: str | None = "PCS",
) -> CanonicalScanRecord:
    return CanonicalScanRecord(
        record_id=record_id,
        scan_id=1,
        source_row_index=record_id - 1,
        record_ref_key=f"record-{record_id}",
        source_record_fingerprint=f"source-{record_id}",
        part_no=part_no,
        description=description,
        contract=contract,
        uom=uom,
        type_code=None,
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
        normalization_version="test-v1",
    )


def raw(left: CanonicalScanRecord, right: CanonicalScanRecord):
    return classify_identity_edge(score_candidate(
        {
            "PART_NO": left.part_no,
            "DESCRIPTION": left.description,
            "CONTRACT": left.contract,
            "UNIT_MEAS": left.uom,
        },
        {
            "PART_NO": right.part_no,
            "DESCRIPTION": right.description,
            "CONTRACT": right.contract,
            "UNIT_MEAS": right.uom,
        },
        ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    ))


def evaluated(left: CanonicalScanRecord, right: CanonicalScanRecord):
    return evaluate_canonical_identity_relationship(left, right, CONTEXT)


def side_conflict(left: CanonicalScanRecord, right: CanonicalScanRecord) -> dict:
    edge = evaluated(left, right)
    assert edge.edge_class == IdentityEdgeClass.CANNOT_LINK
    conflicts = json.loads(edge.protected_conflicts_json)
    return next(item for item in conflicts if item["group"] == "IDENTITY_SIDE_VARIANT")


def test_r10_1_r10_2_pre_fix_shape_and_root_cause_are_frozen():
    left = record(1, "FRONT L/S SHOCK", "Front L/S Shock")
    right = record(2, "FRONT R/S SHOCK", "Front L/S Shock")
    result = raw(left, right)
    assert result.edge_class == IdentityEdgeClass.STRONG_SUPPORT


@pytest.mark.parametrize(
    ("left_no", "right_no", "expected_matches"),
    [
        ("PUMP LEFT", "PUMP RIGHT", ("left", "right")),
        ("PUMP LH", "PUMP RH", ("lh", "rh")),
        ("PUMP L/H", "PUMP R/H", ("l h", "r h")),
        ("PUMP L/S", "PUMP R/S", ("l s", "r s")),
        ("PUMP LEFT SIDE", "PUMP RIGHT SIDE", ("left side", "right side")),
        ("PUMP LEFT HAND", "PUMP RIGHT HAND", ("left hand", "right hand")),
    ],
)
def test_r10_3_to_r10_8_r10_11_explicit_forms_are_protected(
    left_no, right_no, expected_matches
):
    left = record(1, left_no, "PUMP ASSEMBLY")
    right = record(2, right_no, "PUMP ASSEMBLY")
    conflict = side_conflict(left, right)
    assert conflict == {
        "group": "IDENTITY_SIDE_VARIANT",
        "label": "explicit directional side variant",
        "values_a": ["LEFT"],
        "values_b": ["RIGHT"],
        "provenance": "EXPLICIT_TWO_SIDED_DIRECTIONAL_VARIANT",
    }
    payload = json.loads(evaluated(left, right).technical_evidence_json)[
        "identity_discriminator"
    ]
    assert payload["record_1"]["part_number_side_matches"] == [expected_matches[0]]
    assert payload["record_2"]["part_number_side_matches"] == [expected_matches[1]]


def test_r10_9_r10_10_bare_letters_and_substrings_are_not_sides():
    for value in ("MODEL L 100", "MODEL R 100", "LR-100", "RL-100", "LEFTOVER", "RIGHTEOUS"):
        item = extract_record_discriminators(value, value)
        assert item.resolved_side is None
        assert item.part_number_sides == item.description_sides == ()


def test_r10_12_to_r10_14_same_side_and_unknown_are_non_conflicting():
    pairs = (
        (record(1, "PUMP LEFT", "PUMP"), record(2, "PUMP LH", "PUMP")),
        (record(3, "PUMP RIGHT", "PUMP"), record(4, "PUMP RH", "PUMP")),
        (record(5, "PUMP LEFT", "PUMP"), record(6, "PUMP", "PUMP")),
    )
    for left, right in pairs:
        assert evaluated(left, right).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_r10_15_copied_description_cannot_erase_part_number_side():
    left = record(1, "FRONT L/S DAMPER", "Front L/S Damper")
    right = record(2, "FRONT R/S DAMPER", "Front L/S Damper")
    side_conflict(left, right)
    payload = evaluate_identity_discriminators(
        left.part_no, left.description, left.uom,
        right.part_no, right.description, right.uom,
    ).evidence_payload
    assert payload["record_1"]["resolved_side"] == "LEFT"
    assert payload["record_2"]["resolved_side"] == "RIGHT"
    assert payload["record_2"]["side_provenance"] == "EXPLICIT_PART_NUMBER_SIDE"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (record(1, "LOCAL-A LEFT", "MOTOR"), record(2, "LOCAL-B LH", "MOTOR")),
        (record(3, "SITE-A RIGHT", "VALVE", contract="S1"), record(4, "SITE-B RH", "VALVE", contract="S2")),
        (record(5, "CB-CC", "CONTACT CLEANER CAN"), record(6, "AP-CC", "Contact cleaner can")),
        (record(7, "BRG-FR-A", "FRANCIS TURBINE LOWER BEARING"), record(8, "BRG-FR-B", "Francis Turbine Lower Bearing")),
        (record(9, "FAN-BLADE-A", "FAN BLADE MODEL 5"), record(10, "FAN-BLADE-B", "Fan blade model 5")),
        (record(11, "AS-COM-ROT", "F30 COMPRESSOR ROTOR"), record(12, "KA-ASCOMROT1", "F30 Compressor Rotor")),
        (record(13, "AS-B38-H", "B38 ENGINE HEAD"), record(14, "ES-AS-B38-H", "B38 Engine Head")),
        (record(15, "LR-100-A", "MODEL LR 100"), record(16, "LR-100-B", "MODEL LR 100")),
        (record(17, "ITEM-A", "STOCK LEFT WAREHOUSE"), record(18, "ITEM-B", "STOCK LEFT DEPOT")),
    ],
)
def test_r10_16_r10_17_and_positive_controls_are_preserved(left, right):
    assert evaluated(left, right).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_r10_18_whole_group_bridge_cannot_override_side_conflict():
    records = (
        record(1, "PUMP LEFT", "PUMP ASSEMBLY"),
        record(2, "PUMP", "PUMP ASSEMBLY"),
        record(3, "PUMP RIGHT", "PUMP ASSEMBLY"),
    )
    relationships = tuple(
        evaluated(records[left], records[right])
        for left, right in ((0, 1), (1, 2), (0, 2))
    )
    assert relationships[2].edge_class == IdentityEdgeClass.CANNOT_LINK
    edges = tuple(IdentityResolutionEvidenceEdge(
        scan_id=1,
        evidence_run_id=30,
        record_id_1=item.record_id_1,
        record_id_2=item.record_id_2,
        edge_class=item.edge_class,
        reason_codes=item.classification_reason_codes,
        evidence_fingerprint=item.evidence_fingerprint,
    ) for item in relationships)
    value = IdentityResolutionInput(
        scan_id=1,
        discovery_run_id=20,
        evidence_run_id=30,
        canonical_records=records,
        identity_neighborhoods=(IdentityResolutionNeighborhood(
            "n-1", 1, 20, (1, 2, 3), False, False
        ),),
        machine_evidence_edges=edges,
        human_constraints=(),
        resolver_algorithm_version="constrained-identity-resolver-v1",
        resolver_configuration=ResolverConfiguration(20, 40, 8, "test-v1"),
    )
    result = resolve_identity_groups(
        value, CanonicalEvaluatorTargetedEvidenceProvider(records, CONTEXT)
    )
    assert not any(group.member_record_ids == (1, 2, 3) for group in result.accepted_groups)
    assert result.conflicts


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (record(1, "AT TYRE", "205 70 15"), record(2, "SLICK TYRE", "205 70 15")),
        (record(3, "ROAD TIRE", "ROAD TIRE"), record(4, "ROAD WHEEL", "ROAD WHEEL")),
        (record(5, "CARBON STICK", "CARBON STICK", uom="g"), record(6, "PENCIL", "CARBON STICK", uom="pcs")),
        (record(7, "ROAD RIM", "ROAD RIM"), record(8, "ROAD TYRE", "ROAD TYRE")),
        (record(9, "TABLE PRODUCT", "SHARED"), record(10, "NAILS", "SHARED")),
        (record(11, "CONDITION X", "CONDITION X"), record(12, "DISCOUNT X", "CONDITION X")),
        (record(13, "CLUTCH DISK", "DUST CAPS"), record(14, "DUST CAPS", "DUST CAPS")),
        (record(15, "DUST CAPS", "DUST CAPS"), record(16, "COIL SPRING", "DUST CAPS")),
    ],
)
def test_r10_19_to_r10_24_r7_r9_controls_remain_protected(left, right):
    assert evaluated(left, right).edge_class == IdentityEdgeClass.CANNOT_LINK


def test_r10_25_to_r10_28_provenance_scope_and_hard_coding_guards():
    source = inspect.getsource(discriminator_module).casefold()
    for forbidden in (
        "scan 30", "25353d2b0aac", "source_row_index",
        "front l/s shock", "front r/s shock", "list_20260709",
    ):
        assert forbidden not in source
    for forbidden in ("threshold", "provider", "group_size", "review", "export"):
        assert forbidden not in source
    edge = evaluated(
        record(1, "PUMP L/S", "PUMP"), record(2, "PUMP R/S", "PUMP")
    )
    conflict = json.loads(edge.protected_conflicts_json)[-1]
    assert conflict["provenance"] == "EXPLICIT_TWO_SIDED_DIRECTIONAL_VARIANT"
    technical = json.loads(edge.technical_evidence_json)["identity_discriminator"]
    assert technical["version"] == "identity-discriminator-v3"
    assert technical["record_1"]["side_provenance"] == "EXPLICIT_PART_NUMBER_SIDE"
