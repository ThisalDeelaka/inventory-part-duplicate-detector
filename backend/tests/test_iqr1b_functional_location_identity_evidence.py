"""IQR-1B source-aware functional/location identity safety."""

import json

from app.engine.functional_location_facet import (
    FUNCTIONAL_LOCATION_FACET_VERSION,
    extract_functional_location_facets,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.engine.identity_evidence_evaluator import (
    DeterministicIdentityContext,
    evaluate_canonical_identity_relationship,
)
from app.engine.identity_signature import SignedEvidenceChannel
from app.engine.identity_signature_derivation import derive_identity_signature
from app.engine.signed_identity_evidence import derive_signed_identity_evidence
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


CONTEXT = DeterministicIdentityContext("DISCOVERY", ("CONTRACT", "UNIT_MEAS"))


def record(record_id, part_no, description):
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
        normalization_version="iqr1b-test-v1",
    )


def evaluated(left, right):
    return evaluate_canonical_identity_relationship(left, right, CONTEXT)


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


def test_general_facet_requires_modifier_construct_and_preserves_provenance():
    facets = extract_functional_location_facets(
        "LED Head Light", source_family="DESCRIPTION"
    )

    assert len(facets) == 1
    assert facets[0].axis == "longitudinal_end"
    assert facets[0].value == "head"
    assert facets[0].shared_construct == "led light"
    assert facets[0].source_family == "DESCRIPTION"
    assert facets[0].matched_evidence == "head light"
    assert facets[0].provenance_code == FUNCTIONAL_LOCATION_FACET_VERSION


def test_scan33_head_tail_pair_is_protected_cannot_link():
    edge = evaluated(
        record(1, "AB-LIGHT", "LED Head Light"),
        record(2, "AB-TAIL LIGHT", "LED Tail Light"),
    )
    conflicts = json.loads(edge.protected_conflicts_json)
    conflict = next(
        item for item in conflicts
        if item["group"] == "FUNCTIONAL_LOCATION_IDENTITY"
    )

    assert edge.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert conflict == {
        "axis": "longitudinal_end",
        "group": "FUNCTIONAL_LOCATION_IDENTITY",
        "label": "functional/location identity role",
        "matched_normalized_evidence_a": ["head light"],
        "matched_normalized_evidence_b": ["tail light"],
        "provenance": "EXPLICIT_TWO_SIDED_FUNCTIONAL_LOCATION_FACET",
        "shared_construct": "led light",
        "source_fields_a": ["DESCRIPTION"],
        "source_fields_b": ["DESCRIPTION"],
        "values_a": ["head"],
        "values_b": ["tail"],
    }


def test_same_role_alias_has_no_functional_location_contradiction():
    edge = evaluated(
        record(1, "LIGHT-HEAD-A", "LED HEAD-LIGHT"),
        record(2, "LGT-H-B", "led head light"),
    )

    assert edge.edge_class != IdentityEdgeClass.CANNOT_LINK
    assert not any(
        item["group"] == "FUNCTIONAL_LOCATION_IDENTITY"
        for item in json.loads(edge.protected_conflicts_json)
    )


def test_engine_head_alias_remains_positive_and_is_not_a_location_facet():
    assert not extract_functional_location_facets(
        "B38 Engine Head", source_family="DESCRIPTION"
    )
    left = signature("AS-B38-H", "B38 ENGINE HEAD", "b38-a")
    right = signature("ES/AS-B38-H", "B38 Engine Head", "b38-b")
    assert not any(
        item.semantic_key.startswith("functional_location::")
        for item in left.assembly_component_role_observations
        + right.assembly_component_role_observations
    )
    assert evaluated(
        record(1, "AS-B38-H", "B38 ENGINE HEAD"),
        record(2, "ES/AS-B38-H", "B38 Engine Head"),
    ).edge_class != IdentityEdgeClass.CANNOT_LINK


def test_one_sided_location_evidence_does_not_invent_contradiction():
    edge = evaluated(
        record(1, "LIGHT-H", "LED Head Light"),
        record(2, "LIGHT", "LED Light"),
    )

    assert edge.edge_class != IdentityEdgeClass.CANNOT_LINK
    assert not any(
        item["group"] == "FUNCTIONAL_LOCATION_IDENTITY"
        for item in json.loads(edge.protected_conflicts_json)
    )


def test_signed_shadow_evidence_retains_both_sources_and_shared_axis():
    left = signature("AB-LIGHT", "LED Head Light", "head")
    right = signature("AB-TAIL LIGHT", "LED Tail Light", "tail")
    evidence = derive_signed_identity_evidence(left, right)
    fact = next(
        item for item in evidence.facts
        if item.reason_code == "SHADOW_FUNCTIONAL_LOCATION_IDENTITY_INCOMPATIBILITY"
    )

    assert fact.channel == SignedEvidenceChannel.IDENTITY_CONTRADICTION
    assert fact.semantic_key == "functional_location::longitudinal_end::led light"
    assert fact.normalized_matches == ("head", "tail")
    assert {item.source_field.value for item in fact.source_observations_1} == {
        "DESCRIPTION"
    }
    assert {item.source_field.value for item in fact.source_observations_2} == {
        "DESCRIPTION"
    }


def test_existing_directional_cannot_link_remains_unchanged():
    assert evaluated(
        record(1, "PUMP L/S", "Pump Assembly"),
        record(2, "PUMP R/S", "Pump Assembly"),
    ).edge_class == IdentityEdgeClass.CANNOT_LINK


def test_whole_group_support_bridge_cannot_override_functional_conflict():
    records = (
        record(1, "LIGHT-H", "LED Head Light"),
        record(2, "LIGHT", "LED Light"),
        record(3, "LIGHT-T", "LED Tail Light"),
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
            "iqr1b-neighborhood", 1, 20, (1, 2, 3), False, False
        ),),
        machine_evidence_edges=edges,
        human_constraints=(),
        resolver_algorithm_version="constrained-identity-resolver-v1",
        resolver_configuration=ResolverConfiguration(20, 40, 8, "iqr1b-test-v1"),
    )

    result = resolve_identity_groups(
        value, CanonicalEvaluatorTargetedEvidenceProvider(records, CONTEXT)
    )

    assert not any(
        group.member_record_ids == (1, 2, 3) for group in result.accepted_groups
    )
    assert result.conflicts
