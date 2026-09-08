"""GF-12C1-R11 bounded buffer/mirror object-identity acceptance tests."""

from __future__ import annotations

import inspect
import json

import pytest

from app.engine import identity_discriminator as discriminator_module
from app.engine.identity_discriminator import extract_record_discriminators
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
    accounting_group: str | None = None,
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
        accounting_group=accounting_group,
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


def test_r11_1_to_r11_4_pre_fix_root_cause_strategy_and_anti_one_off_gate():
    left = record(1, "LG - BUFFER01", "Seria/condition part")
    right = record(2, "LG - MIRROR01", "Seria/condition part")
    before = raw(left, right)
    assert before.edge_class == IdentityEdgeClass.STRONG_SUPPORT

    left_evidence = extract_record_discriminators(left.part_no, left.description)
    right_evidence = extract_record_discriminators(right.part_no, right.description)
    assert left_evidence.part_number_classes == ("buffer",)
    assert right_evidence.part_number_classes == ("mirror",)
    assert left_evidence.description_classes == right_evidence.description_classes == ()
    assert left_evidence.part_number_class_matches == ("buffer",)
    assert right_evidence.part_number_class_matches == ("mirror",)

    source = inspect.getsource(discriminator_module).casefold()
    for forbidden in (
        "buffer01", "mirror01", "1511", "1512", "d7c16998f587",
        "scan 31", "list_20260709",
    ):
        assert forbidden not in source


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (record(1, "PLANT BUFFER 77", "COMMON PART"), record(2, "PLANT MIRROR 77", "COMMON PART")),
        (record(3, "SAFETY-BUFFER-A", "COPIED ITEM"), record(4, "SAFETY-MIRROR-A", "COPIED ITEM")),
        (record(5, "BUFFER 101", "SPARE"), record(6, "MIRROR 101", "SPARE")),
        (record(7, "BUFFER", "SHARED GENERIC TEXT"), record(8, "MIRROR", "SHARED GENERIC TEXT")),
    ],
)
def test_r11_5_r11_9_n1_to_n4_known_incompatible_classes_are_protected(
    left, right
):
    edge = evaluated(left, right)
    assert edge.edge_class == IdentityEdgeClass.CANNOT_LINK
    conflict = json.loads(edge.protected_conflicts_json)[-1]
    assert conflict["group"] == "IDENTITY_OBJECT_CLASS"
    assert conflict["provenance"] == "EXPLICIT_TWO_SIDED_OBJECT_CLASS"
    assert conflict["source_fields_a"] == conflict["source_fields_b"] == [
        "PART_NUMBER"
    ]
    assert conflict["incompatibility_relation"] == (
        "BOUNDED_OBJECT_CLASS_INCOMPATIBILITY"
    )


def test_r11_6_to_r11_12_n5_to_n10_do_not_invent_cannot_links():
    cases = (
        (record(1, "BUFFER 1", "COMMON"), record(2, "UNKNOWN 1", "COMMON")),
        (record(3, "ALPHA WIDGET", "COMMON"), record(4, "BETA GADGET", "COMMON")),
        (record(5, "BUFFER 1", "BUFFER"), record(6, "BUFFERS 1", "BUFFER")),
        (record(7, "SITE-A BUFFER 1", "BUFFER"), record(8, "SITE-B BUFFER 1 REV2", "BUFFER")),
        (record(9, "ITEM-A", "COMMON PART"), record(10, "ITEM-B", "COMON PART")),
        (record(11, "ITEM-A", "SAME MODEL", uom="kg"), record(12, "ITEM-B", "SAME MODEL", uom="pcs")),
    )
    for left, right in cases:
        assert evaluated(left, right).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_r11_13_whole_group_bridge_cannot_override_object_conflict():
    records = (
        record(1, "BUFFER 77", "COMMON PART"),
        record(2, "ITEM 77", "COMMON PART"),
        record(3, "MIRROR 77", "COMMON PART"),
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
    assert not any(
        group.member_record_ids == (1, 2, 3) for group in result.accepted_groups
    )
    assert result.conflicts


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (record(1, "BRG-6205-A", "Bearing 6205"), record(2, "BRG6205A", "BEARING 6205")),
        (record(3, "BUFFER-A", "BUFFER ASSEMBLY"), record(4, "BUFFERS-A", "BUFFER ASSEMBLY")),
        (record(5, "SITE-A", "VALVE MODEL 100", contract="S1"), record(6, "SITE-B", "VALVE MODEL 100", contract="S2")),
        (record(7, "PUMP-A", "PUMP MODEL 100", uom=None), record(8, "PUMP-B", "PUMP MODEL 100")),
        (record(9, "CB-CC", "CONTACT CLEANER CAN"), record(10, "AP-CC", "Contact cleaner can")),
        (record(11, "BRG-FR-A", "FRANCIS TURBINE LOWER BEARING"), record(12, "BRG-FR-B", "Francis Turbine Lower Bearing")),
        (record(13, "FAN-BLADE-A", "FAN BLADE MODEL 5"), record(14, "FAN-BLADE-B", "Fan blade model 5")),
        (record(15, "AS-COM-ROT", "F30 COMPRESSOR ROTOR"), record(16, "KA-ASCOMROT1", "F30 Compressor Rotor")),
        (record(17, "AS-B38-H", "B38 ENGINE HEAD"), record(18, "ES-AS-B38-H", "B38 Engine Head")),
        (record(19, "LOCAL-A LEFT", "MOTOR"), record(20, "LOCAL-B LH", "MOTOR")),
        (record(21, "MODEL-X-A", "MODEL X"), record(22, "MODEL-X-B-REV2", "MODEL X")),
        (record(23, "ITEM-A", "VALVE MODEL 5", accounting_group="A"), record(24, "ITEM-B", "VALVE MODEL 5", accounting_group="B")),
    ],
)
def test_r11_14_to_r11_18_p1_to_p12_positive_controls_are_preserved(left, right):
    assert evaluated(left, right).edge_class != IdentityEdgeClass.CANNOT_LINK


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (record(1, "AT TYRE", "205 70 15"), record(2, "SLICK TYRE", "205 70 15")),
        (record(3, "ROAD TIRE", "ROAD TIRE"), record(4, "ROAD WHEEL", "ROAD WHEEL")),
        (record(5, "CARBON STICK", "CARBON STICK", uom="g"), record(6, "PENCIL", "CARBON STICK", uom="pcs")),
        (record(7, "ROAD RIM", "ROAD RIM"), record(8, "ROAD TYRE", "ROAD TYRE")),
        (record(9, "TABLE PRODUCT", "SHARED"), record(10, "NAILS", "SHARED")),
        (record(11, "CONDITION X", "CONDITION X"), record(12, "DISCOUNT X", "CONDITION X")),
        (record(13, "CLUTCH DISK", "DUST CAPS"), record(14, "COIL SPRING", "DUST CAPS")),
        (record(15, "PUMP L/S", "PUMP"), record(16, "PUMP R/S", "PUMP")),
    ],
)
def test_r11_19_to_r11_26_r7_r9_r10_controls_remain_protected(left, right):
    assert evaluated(left, right).edge_class == IdentityEdgeClass.CANNOT_LINK


def test_r11_27_provenance_is_deterministic_complete_and_orientation_stable():
    left = record(1, "PLANT BUFFER 77", "COMMON PART")
    right = record(2, "PLANT MIRROR 77", "COMMON PART")
    runs = [evaluated(left, right) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2] == evaluated(right, left)
    conflict = json.loads(runs[0].protected_conflicts_json)[-1]
    assert conflict["matched_normalized_evidence_a"] == ["buffer"]
    assert conflict["matched_normalized_evidence_b"] == ["mirror"]
    assert conflict["description_reliability"] == {
        "classification": "IDENTICAL_NON_OBJECT_BEARING_TEXT",
        "description_1_generic": False,
        "description_2_generic": False,
        "normalized_descriptions_equal": True,
    }
    technical = json.loads(runs[0].technical_evidence_json)[
        "identity_discriminator"
    ]
    assert technical["version"] == "identity-discriminator-v5"
    assert runs[0].evaluation_algorithm_version == "canonical-identity-evaluator-v7"


def test_r11_28_to_r11_32_provider_input_authority_and_secret_scope_guards():
    source = inspect.getsource(discriminator_module).casefold()
    for forbidden in (
        "provider", "api_key", ".env", "authorization", "threshold",
        "group_size", "review", "export", "source_row_index",
    ):
        assert forbidden not in source
    assert source.count('"buffer":') == 1
    assert source.count('"mirror":') == 1
    assert "frozenset((\"buffer\", \"mirror\"))" in source
