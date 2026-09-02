"""IQR-1C diagnostic characterization of current GF5 review disposition."""

from itertools import combinations

from app.engine.identity_edge import IdentityEdgeClass
from app.resolution import resolver as resolver_module
from app.resolution.contracts import (
    DeferredIdentityReason,
    IdentityConflictType,
    IdentityGroupHypothesisStatus,
    IdentityResolutionEvidenceEdge,
    IdentityResolutionInput,
    IdentityResolutionNeighborhood,
    ResolverConfiguration,
)
from app.resolution.resolver import resolve_identity_groups
from app.services.canonical_record_service import CanonicalScanRecord


def record(record_id):
    return CanonicalScanRecord(
        record_id=record_id,
        scan_id=1,
        source_row_index=record_id - 1,
        record_ref_key=f"record-{record_id}",
        source_record_fingerprint=f"source-{record_id}",
        part_no=f"P-{record_id}",
        description=f"Specific item {record_id}",
        contract=f"S{record_id}",
        uom="PCS",
        type_code=None,
        prime_commodity=None,
        second_commodity=None,
        accounting_group=None,
        part_product_code=None,
        part_product_family=None,
        product_category_id=None,
        hsn_sac_code=None,
        hazard_code=None,
        normalized_part_no=f"p {record_id}",
        normalized_description=f"specific item {record_id}",
        normalization_version="iqr1c-audit-v1",
    )


def edge(left, right, edge_class, *, generic=False):
    return IdentityResolutionEvidenceEdge(
        scan_id=1,
        evidence_run_id=30,
        record_id_1=left,
        record_id_2=right,
        edge_class=edge_class,
        reason_codes=(f"IQR1C_{edge_class.value}",),
        evidence_fingerprint=f"edge-{left}-{right}-{edge_class.value}",
        generic_only=generic,
    )


def resolver_input(size, overrides=None, *, generic=False):
    overrides = overrides or {}
    members = tuple(range(1, size + 1))
    edges = tuple(
        edge(
            left,
            right,
            overrides.get((left, right), IdentityEdgeClass.REVIEW_SUPPORT),
            generic=generic,
        )
        for left, right in combinations(members, 2)
    )
    return IdentityResolutionInput(
        scan_id=1,
        discovery_run_id=20,
        evidence_run_id=30,
        canonical_records=tuple(record(item) for item in members),
        identity_neighborhoods=(IdentityResolutionNeighborhood(
            "iqr1c-audit", 1, 20, members, False, False
        ),),
        machine_evidence_edges=edges,
        human_constraints=(),
        resolver_algorithm_version="constrained-identity-resolver-v1",
        resolver_configuration=ResolverConfiguration(
            20, 40, 8, "constrained-identity-resolver-config-v1"
        ),
    )


def resolve(size, overrides=None, *, generic=False):
    return resolve_identity_groups(
        resolver_input(size, overrides, generic=generic), None
    )


def test_case_a_seven_complete_all_review_is_bounded_partition_deferred():
    result = resolve(7)

    assert result.accepted_groups == ()
    assert tuple(item.reason for item in result.deferred_work_units) == (
        DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY,
    )
    assert result.metrics.candidate_partitions_explored == 16521


def test_case_b_one_strong_edge_does_not_resolve_seven_member_partition_search():
    result = resolve(7, {(1, 2): IdentityEdgeClass.STRONG_SUPPORT})

    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY
    )


def test_case_c_one_neutral_edge_remains_partition_stability_deferred():
    result = resolve(7, {(1, 2): IdentityEdgeClass.NON_GROUPABLE})

    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY
    )


def test_case_d_cannot_link_never_enters_one_group_and_remains_visible():
    result = resolve(7, {(1, 2): IdentityEdgeClass.CANNOT_LINK})

    assert result.accepted_groups == ()
    assert tuple(item.conflict_type for item in result.conflicts) == (
        IdentityConflictType.PROTECTED_CANNOT_LINK,
    )
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY
    )


def test_case_e_four_complete_all_review_has_equal_pair_partitions():
    result = resolve(4)

    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.UNRESOLVED_OWNERSHIP_AMBIGUITY
    )
    assert result.metrics.candidate_partitions_explored == 104


def test_case_f_two_member_review_is_an_accepted_review_hypothesis():
    result = resolve(2)

    assert len(result.accepted_groups) == 1
    assert result.accepted_groups[0].member_record_ids == (1, 2)
    assert result.accepted_groups[0].status == (
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
    )
    assert result.deferred_work_units == ()


def test_bicycle_shape_generic_only_clique_fails_group_cohesion_before_partition():
    value = resolver_input(7, generic=True)
    unit = resolver_module._work_units(value)[0]
    lookup = resolver_module._effective_lookup(value, ())

    assert resolver_module._build_group(
        value, unit, unit.member_ids, lookup, ()
    ) is None
    bridge = resolver_module._bridge_summary(unit.member_ids, lookup)
    assert bridge.generic_hub_record_ids == unit.member_ids
    assert bridge.unresolved is True

    result = resolve_identity_groups(value, None)
    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.UNRESOLVED_OWNERSHIP_AMBIGUITY
    )
    assert result.metrics.candidate_partitions_explored == 1730


def test_non_generic_full_clique_is_valid_before_current_partition_objective():
    value = resolver_input(7)
    unit = resolver_module._work_units(value)[0]
    lookup = resolver_module._effective_lookup(value, ())
    group = resolver_module._build_group(value, unit, unit.member_ids, lookup, ())

    assert group is not None
    assert group.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
    assert group.evidence_summary.review_support_count == 21
    assert group.evidence_summary.strong_support_count == 0
    assert group.evidence_summary.support_density == 1.0
    assert group.bridge_risk_summary.unresolved is False
