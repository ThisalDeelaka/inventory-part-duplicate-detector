"""GF-12C1-R9 bounded discriminator-coverage acceptance tests."""

from __future__ import annotations

import inspect
import json

import pytest

from app.engine import identity_discriminator as discriminator_module
from app.engine.identity_discriminator import evaluate_identity_discriminators
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
    uom: str | None = "PCS",
    contract: str = "S1",
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


RIM = record(1, "CS RIM 17", "CS Rim 17")
TYRE = record(2, "CS TIRE 17", "CS Tire 17")
TABLE = record(3, "TABLE PRODUCT", "SHARED TEST")
NAILS = record(4, "NAILS", "SHARED TEST")
CONDITION = record(5, "CONDITION X", "CONDITION X")
DISCOUNT = record(6, "DISCOUNT X", "CONDITION X")
CLUTCH = record(7, "CLUTCH DISK", "DUST CAPS")
DUST_CAP = record(8, "DUST CAPS", "DUST CAPS")
COIL_SPRING = record(9, "COIL SPRING", "DUST CAPS")


def test_r9_1_to_r9_6_pref_fix_shapes_and_root_clusters_are_frozen():
    assert raw(RIM, TYRE).edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert raw(TABLE, NAILS).edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert raw(CONDITION, DISCOUNT).edge_class in {
        IdentityEdgeClass.STRONG_SUPPORT, IdentityEdgeClass.REVIEW_SUPPORT
    }
    for pair in ((CLUTCH, DUST_CAP), (DUST_CAP, COIL_SPRING), (CLUTCH, COIL_SPRING)):
        assert raw(*pair).edge_class in {
            IdentityEdgeClass.STRONG_SUPPORT, IdentityEdgeClass.REVIEW_SUPPORT
        }


@pytest.mark.parametrize(
    ("left", "right", "group", "provenance"),
    [
        (RIM, TYRE, "IDENTITY_OBJECT_CLASS", "EXPLICIT_TWO_SIDED_OBJECT_CLASS"),
        (TABLE, NAILS, "IDENTITY_OBJECT_CLASS", "EXPLICIT_TWO_SIDED_OBJECT_CLASS"),
        (CONDITION, DISCOUNT, "IDENTITY_CONSTRUCT_CLASS", "EXPLICIT_TWO_SIDED_OBJECT_CLASS"),
        (CLUTCH, DUST_CAP, "IDENTITY_OBJECT_CLASS", "EXPLICIT_TWO_SIDED_PART_NUMBER_CLASS"),
        (DUST_CAP, COIL_SPRING, "IDENTITY_OBJECT_CLASS", "EXPLICIT_TWO_SIDED_PART_NUMBER_CLASS"),
        (CLUTCH, COIL_SPRING, "IDENTITY_OBJECT_CLASS", "EXPLICIT_TWO_SIDED_PART_NUMBER_CLASS"),
    ],
)
def test_r9_11_r9_12_r9_17_r9_18_explicit_conflicts_are_protected(
    left, right, group, provenance
):
    edge = evaluated(left, right)
    assert edge.edge_class == IdentityEdgeClass.CANNOT_LINK
    conflict = json.loads(edge.protected_conflicts_json)[-1]
    assert conflict["group"] == group
    assert conflict["provenance"] == provenance
    assert json.loads(edge.technical_evidence_json)["identity_discriminator"][
        "version"
    ] == "identity-discriminator-v4"


def test_r9_8_to_r9_10_unknown_and_generic_evidence_do_not_invent_conflicts():
    cases = (
        (record(1, "UNKNOWN", "SPECIAL ITEM"), record(2, "ROAD TYRE", "ROAD TYRE")),
        (record(3, "A", "BEARING"), record(4, "B", "BEARING")),
        (record(5, "A", "205 70 15"), record(6, "B", "205 70 15")),
        # Commercial constructs are deliberately part-number-only.
        (record(7, "A", "DISCOUNT VALVE"), record(8, "B", "CONDITION VALVE")),
    )
    for left, right in cases:
        assert evaluated(left, right).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_r9_13_same_known_class_and_alias_canonicalization_are_compatible():
    first = evaluate_identity_discriminators(
        "ROAD RIM", "ROAD RIM", "PCS", "ROAD WHEEL", "ROAD WHEEL", "PCS"
    )
    assert first.protected_conflicts == ()
    assert first.evidence_payload["record_1"]["resolved_object_class"] == "wheel"
    assert first.evidence_payload["record_2"]["resolved_object_class"] == "wheel"


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (record(1, "BRG-6205-A", "Bearing 6205"), record(2, "BRG6205A", "BEARING 6205")),
        (record(3, "LOCAL-A", "MOTOR 10 KW"), record(4, "LOCAL-B", "10KW MOTOR")),
        (record(5, "SITE-A", "VALVE MODEL 100", contract="S1"), record(6, "SITE-B", "VALVE MODEL 100", contract="S2")),
        (record(7, "PUMP-A", "PUMP MODEL 100", uom=None), record(8, "PUMP-B", "PUMP MODEL 100")),
        (record(9, "OIL-A", "TURBINE LUBRICATING OIL", uom="l"), record(10, "OIL-B", "TURBINE LUBRICATING OIL")),
        (record(11, "CB-CC", "CONTACT CLEANER CAN"), record(12, "AP-CC", "Contact cleaner can")),
        (record(13, "BRG-FR-22-A", "FRANCIS TURBINE LOWER BEARING"), record(14, "BRG-FR-22-B", "Francis Turbine Lower Bearing")),
        (record(15, "FAN-BLADE-A", "FAN BLADE MODEL 5"), record(16, "FAN-BLADE-B", "Fan blade model 5")),
        (record(17, "AS-B38-H", "B38 ENGINE HEAD"), record(18, "ES-AS-B38-H", "B38 Engine Head")),
        (record(19, "AS-COM-ROT", "F30 COMPRESSOR ROTOR"), record(20, "KA-ASCOMROT1", "F30 Compressor Rotor")),
        (record(21, "CLUTCH DISK A", "CLUTCH DISK HEAVY"), record(22, "CLUTCH DISC B", "CLUTCH DISC LIGHT")),
        (record(23, "ITEM-A", "VALVE MODEL 5", accounting_group="A"), record(24, "ITEM-B", "VALVE MODEL 5", accounting_group="B")),
    ],
)
def test_r9_14_to_r9_16_r9_20_to_r9_24_positive_controls_are_preserved(left, right):
    assert evaluated(left, right).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_r9_25_multi_component_and_bridge_cannot_override_cannot_link():
    records = (CLUTCH, DUST_CAP, COIL_SPRING)
    relationships = [
        evaluated(records[0], records[1]),
        evaluated(records[1], records[2]),
        evaluated(records[0], records[2]),
    ]
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
            "n-1", 1, 20, (7, 8, 9), False, False
        ),),
        machine_evidence_edges=edges,
        human_constraints=(),
        resolver_algorithm_version="constrained-identity-resolver-v1",
        resolver_configuration=ResolverConfiguration(20, 40, 8, "test-v1"),
    )
    result = resolve_identity_groups(
        value, CanonicalEvaluatorTargetedEvidenceProvider(records, CONTEXT)
    )
    assert not any(group.member_record_ids == (7, 8, 9) for group in result.accepted_groups)
    assert result.conflicts


def test_r9_7_r9_26_to_r9_35_static_scope_and_provenance_guards():
    source = inspect.getsource(discriminator_module).casefold()
    for forbidden in (
        "scan 29", "list_20260709", "22f757478113", "237359b9bce0",
        "2fc76089884a", "398549408563", "source_row_index",
        "cs-rim17", "ns-table-product", "35-discount-x", "rp-clutchdisk",
    ):
        assert forbidden not in source
    assert "threshold" not in source
    edge = evaluated(TABLE, NAILS)
    conflict = json.loads(edge.protected_conflicts_json)[-1]
    assert conflict["values_a"] and conflict["values_b"]
    assert conflict["provenance"] == "EXPLICIT_TWO_SIDED_OBJECT_CLASS"


def test_r9_27_weak_watchlist_shapes_are_not_broadly_overcorrected():
    weak = (
        (record(1, "FIFO-A", "FIFO-A"), record(2, "FIFO-B", "FIFO-B")),
        (record(3, "PART-01", "SHARED PROCESS"), record(4, "PART-02", "SHARED PROCESS")),
        (record(5, "TRANSACTION-INVENTORY", "ITEM"), record(6, "TRANSACTION-PURCHASE", "ITEM")),
        (record(7, "CONDITION-X", "CONDITION-X"), record(8, "CONDITION-01", "CONDITION-01")),
    )
    for left, right in weak:
        assert evaluated(left, right).edge_class != IdentityEdgeClass.CANNOT_LINK
