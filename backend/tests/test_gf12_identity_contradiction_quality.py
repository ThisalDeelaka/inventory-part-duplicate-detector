"""GF-12C1-R7 deterministic identity-contradiction acceptance tests."""

from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path

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


REPO_ROOT = Path(__file__).resolve().parents[2]
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


def engine_record(item: CanonicalScanRecord) -> dict:
    return {
        "PART_NO": item.part_no,
        "DESCRIPTION": item.description,
        "CONTRACT": item.contract,
        "UNIT_MEAS": item.uom,
        "ACCOUNTING_GROUP": item.accounting_group,
    }


def raw_class(left: CanonicalScanRecord, right: CanonicalScanRecord):
    return classify_identity_edge(score_candidate(
        engine_record(left), engine_record(right),
        ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    ))


def evaluated(
    left: CanonicalScanRecord,
    right: CanonicalScanRecord,
    context: DeterministicIdentityContext = CONTEXT,
):
    return evaluate_canonical_identity_relationship(left, right, context)


def test_iq1_iq3_pre_fix_false_edges_are_frozen_before_gf4_discriminator():
    at = record(1, "AT TYRE", "205 70 15")
    slick = record(2, "SLICK TYRE", "205 70 15")
    tyre = record(3, "MLR-TIRE17-03.10.2023", "MLR-TIRE17-03.10.2023")
    wheel = record(4, "MLR-WHEEL-03.10.2023", "MLR-WHEEL-03.10.2023")
    carbon = record(5, "INV-CARBON-STICK", "INV-CARBON-STICK", uom="g")
    pencil = record(6, "INV-PENCIL", "INV-CARBON-STICK", uom="pcs")

    assert raw_class(at, slick).edge_class == IdentityEdgeClass.STRONG_SUPPORT
    assert raw_class(tyre, wheel).edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert raw_class(carbon, pencil).edge_class == IdentityEdgeClass.REVIEW_SUPPORT


@pytest.mark.parametrize(
    ("left", "right", "reason"),
    [
        (record(1, "AT TYRE", "205 70 15"), record(2, "SLICK TYRE", "205 70 15"), "MUTUALLY_EXCLUSIVE_TYRE_VARIANT"),
        (record(3, "SNOW TYRE", "205 70 15 snow"), record(4, "AT TYRE", "205 70 15"), "MUTUALLY_EXCLUSIVE_TYRE_VARIANT"),
        (record(5, "ROAD TIRE", "ROAD TIRE"), record(6, "ROAD WHEEL", "ROAD WHEEL"), "IDENTITY_OBJECT_CLASS"),
        (record(7, "PUMP ASSY", "PUMP ASSEMBLY"), record(8, "PUMP COMP", "PUMP COMPONENT"), "STRUCTURAL_ROLE"),
        (record(9, "ROTOR", "F30 COMPRESSOR ROTOR"), record(10, "STATOR", "F30 COMPRESSOR STATOR"), "STRUCTURAL_ROLE"),
        (record(11, "ROAD WHEEL", "COMMON ROAD ITEM"), record(12, "ROAD TYRE", "COMMON ROAD ITEM"), "IDENTITY_OBJECT_CLASS"),
        (record(13, "CARBON STICK", "CARBON STICK", uom="g"), record(14, "PENCIL", "CARBON STICK", uom="pcs"), "IDENTITY_OBJECT_CLASS"),
    ],
)
def test_n1_n6_explicit_negative_fixtures_become_cannot_link(left, right, reason):
    edge = evaluated(left, right)
    assert edge.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert f"CRITICAL_MISMATCH_{reason}" in edge.classification_reason_codes
    conflicts = json.loads(edge.protected_conflicts_json)
    if reason != "STRUCTURAL_ROLE":
        assert conflicts[-1]["provenance"] in {
            "EXPLICIT_TWO_SIDED_OBJECT_CLASS",
            "EXPLICIT_TWO_SIDED_PART_NUMBER_CLASS",
            "EXPLICIT_TWO_SIDED_VARIANT",
            "PART_NUMBER_DESCRIPTION_UOM_COMPOSITE",
        }


def test_n7_generic_noun_alone_is_not_strong_identity_proof():
    edge = evaluated(record(1, "A", "BEARING"), record(2, "B", "BEARING"))
    assert edge.edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert json.loads(edge.technical_evidence_json)["identity_discriminator"][
        "protected_conflict_count"
    ] == 0


def test_n8_generic_dimension_emits_no_discriminator_identity_or_conflict():
    result = evaluate_identity_discriminators(
        "A", "205 70 15", "PCS", "B", "205 70 15", "PCS"
    )
    assert result.protected_conflicts == ()
    assert result.evidence_payload["record_1"]["resolved_object_class"] is None
    assert result.evidence_payload["record_2"]["resolved_object_class"] is None


def test_n9_support_bridge_cannot_override_protected_endpoint_contradiction():
    records = (
        record(1, "AT TYRE", "205 70 15"),
        record(2, "TYRE", "205 70 15"),
        record(3, "SNOW TYRE", "205 70 15 snow"),
    )
    relationships = [
        evaluated(records[0], records[1]),
        evaluated(records[1], records[2]),
        evaluated(records[0], records[2]),
    ]
    assert relationships[0].edge_class in {
        IdentityEdgeClass.STRONG_SUPPORT, IdentityEdgeClass.REVIEW_SUPPORT
    }
    assert relationships[1].edge_class in {
        IdentityEdgeClass.STRONG_SUPPORT, IdentityEdgeClass.REVIEW_SUPPORT
    }
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
    ("left", "right", "context"),
    [
        (record(1, "BRG-6205-A", "Bearing 6205"), record(2, "BRG6205A", "BEARING 6205"), CONTEXT),
        (record(3, "LOCAL-A", "MOTOR 10 KW"), record(4, "LOCAL-B", "10KW MOTOR"), CONTEXT),
        (record(5, "SITE-A", "VALVE MODEL 100", contract="S1"), record(6, "SITE-B", "VALVE MODEL 100", contract="S2"), DeterministicIdentityContext("CROSS_SITE_STANDARDIZATION", ("UNIT_MEAS",))),
        (record(7, "PUMP-A", "PUMP MODEL 100", uom=None), record(8, "PUMP-B", "PUMP MODEL 100", uom="PCS"), CONTEXT),
        (record(9, "OIL-A", "TURBINE LUBRICATING OIL", uom="l"), record(10, "OIL-B", "TURBINE LUBRICATING OIL", uom="PCS"), CONTEXT),
        (record(11, "CB-CC", "CONTACT CLEANER CAN"), record(12, "AP-CC", "Contact cleaner can"), CONTEXT),
        (record(13, "BRG-FR-22-A", "FRANCIS TURBINE LOWER BEARING"), record(14, "BRG-FR-22-B", "Francis Turbine Lower Bearing"), CONTEXT),
        (record(15, "FAN-BLADE-A", "FAN BLADE MODEL 5"), record(16, "FAN-BLADE-B", "Fan blade model 5"), CONTEXT),
        (record(17, "AS-B38-H", "B38 ENGINE HEAD"), record(18, "ES-AS-B38-H", "B38 Engine Head"), CONTEXT),
        (record(19, "ITEM-A", "VALVE MODEL 5", accounting_group="A"), record(20, "ITEM-B", "VALVE MODEL 5", accounting_group="B"), CONTEXT),
    ],
)
def test_p1_p10_positive_controls_are_not_overcorrected(left, right, context):
    assert evaluated(left, right, context).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_unknown_class_missing_uom_and_part_number_difference_are_not_conflicts():
    unknown = evaluated(
        record(1, "UNKNOWN-A", "SPECIAL ITEM", uom=None),
        record(2, "UNKNOWN-B", "SPECIAL ITEM", uom="PCS"),
    )
    assert unknown.edge_class != IdentityEdgeClass.CANNOT_LINK
    evidence = json.loads(unknown.technical_evidence_json)["identity_discriminator"]
    assert evidence["record_1"]["resolved_object_class"] is None
    assert evidence["record_2"]["resolved_object_class"] is None


def test_same_explicit_variant_and_tyre_tire_synonyms_remain_compatible():
    edge = evaluated(
        record(1, "ALL TERRAIN TYRE", "ROAD TYRE"),
        record(2, "AT TIRE", "ROAD TIRE"),
    )
    assert edge.edge_class != IdentityEdgeClass.CANNOT_LINK


def test_gf4_provenance_and_fingerprint_are_orientation_stable_and_repeatable():
    left = record(1, "ROAD WHEEL", "ROAD WHEEL")
    right = record(2, "ROAD TYRE", "ROAD TYRE")
    runs = [evaluated(left, right) for _ in range(3)]
    reverse = evaluated(right, left)
    assert runs[0] == runs[1] == runs[2] == reverse
    technical = json.loads(runs[0].technical_evidence_json)
    assert technical["identity_discriminator"]["version"] == "identity-discriminator-v4"
    assert json.loads(runs[0].protected_conflicts_json)[0]["provenance"] == (
        "EXPLICIT_TWO_SIDED_OBJECT_CLASS"
    )


def test_no_demo_specific_hard_coding_and_only_bounded_production_files_changed():
    source = inspect.getsource(discriminator_module).casefold()
    for forbidden in (
        "scan 27", "list_20260709", "g2v2-group-", "source_row_index",
        "mlr-tire17", "inv-carbon-stick-luci", "205 70 15",
    ):
        assert forbidden not in source

    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "backend/app"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert set(changed) <= {
        "backend/app/api/routes_identity_groups.py",
        "backend/app/engine/identity_discriminator.py",
        "backend/app/engine/identity_evidence_evaluator.py",
        "backend/app/identity_read/explanations.py",
        "backend/app/schemas/identity_groups.py",
    }
