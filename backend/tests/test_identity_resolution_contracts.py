import dataclasses
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.engine.identity_edge import IdentityEdgeClass
from app.resolution.contracts import (
    BridgeRiskSummary,
    DeferredIdentityReason,
    DeferredIdentityWorkUnit,
    GenericityRiskSummary,
    GroupEvidenceSummary,
    IdentityConflict,
    IdentityConflictType,
    IdentityGroupHypothesis,
    IdentityGroupHypothesisStatus,
    IdentityResolutionConstraint,
    IdentityResolutionConstraintType,
    IdentityResolutionEvidenceEdge,
    IdentityResolutionInput,
    IdentityResolutionMetrics,
    IdentityResolutionNeighborhood,
    IdentityResolutionResult,
    IdentityValidationMode,
    MissingEvidenceSummary,
    ResolverConfiguration,
    TargetedEvidenceReason,
    TargetedEvidenceRequest,
    TargetedEvidenceResult,
)
from app.resolution.validation import (
    IdentityResolutionValidationError,
    adapt_effective_human_constraints,
    validate_group_hypothesis,
    validate_resolution_input,
    validate_resolution_result,
    validate_targeted_evidence_request,
    targeted_result_from_evaluation,
    with_deferred_work_unit_fingerprint,
    with_group_hypothesis_fingerprint,
    with_identity_conflict_fingerprint,
    with_resolution_result_fingerprint,
    with_targeted_request_fingerprint,
)
from app.services.canonical_record_service import CanonicalScanRecord


def record(record_id, *, scan_id=1, source_row_index=None, part_no=None, uom="EA"):
    source_row_index = record_id - 1 if source_row_index is None else source_row_index
    return CanonicalScanRecord(
        record_id=record_id,
        scan_id=scan_id,
        source_row_index=source_row_index,
        record_ref_key=f"scan-{scan_id}-row-{source_row_index}",
        source_record_fingerprint=f"source-{record_id}",
        part_no=part_no or f"P-{record_id}",
        description=f"ITEM {record_id}",
        contract="S1",
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
        normalized_part_no=(part_no or f"P-{record_id}").replace("-", ""),
        normalized_description=f"ITEM {record_id}",
        normalization_version="test-v1",
    )


def edge(left, right, edge_class, *, generic=False, scan_id=1):
    left, right = sorted((left, right))
    return IdentityResolutionEvidenceEdge(
        scan_id=scan_id,
        evidence_run_id=30,
        record_id_1=left,
        record_id_2=right,
        edge_class=edge_class,
        reason_codes=(f"TEST_{edge_class.value}",),
        evidence_fingerprint=f"edge-{left}-{right}-{edge_class.value}",
        generic_only=generic,
    )


def resolution_input(
    size,
    edges=(),
    *,
    constraints=(),
    neighborhoods=None,
    records=None,
):
    records = tuple(records or (record(index) for index in range(1, size + 1)))
    if neighborhoods is None:
        neighborhoods = (
            IdentityResolutionNeighborhood(
                neighborhood_reference="n-1",
                scan_id=1,
                discovery_run_id=20,
                member_record_ids=tuple(range(1, size + 1)),
                truncated=False,
                degraded=False,
            ),
        ) if size >= 2 else ()
    return IdentityResolutionInput(
        scan_id=1,
        discovery_run_id=20,
        evidence_run_id=30,
        canonical_records=records,
        identity_neighborhoods=tuple(neighborhoods),
        machine_evidence_edges=tuple(sorted(edges, key=lambda item: (
            item.record_id_1, item.record_id_2
        ))),
        human_constraints=tuple(sorted(constraints, key=lambda item: (
            item.record_id_1, item.record_id_2, item.constraint_type.value
        ))),
        resolver_algorithm_version="constrained-identity-resolver-v1",
        resolver_configuration=ResolverConfiguration(20, 40, 8, "resolver-config-v1"),
    )


def group(
    value,
    members,
    status,
    *,
    bridge=None,
    genericity=None,
    missing=None,
    validation_mode=IdentityValidationMode.COMPLETE_PAIRWISE,
):
    members = tuple(sorted(members))
    pairs = [
        item for item in value.machine_evidence_edges
        if item.record_id_1 in members and item.record_id_2 in members
    ]
    possible = len(members) * (len(members) - 1) // 2
    counts = {
        edge_class: sum(item.edge_class == edge_class for item in pairs)
        for edge_class in IdentityEdgeClass
    }
    generic_count = sum(item.generic_only for item in pairs)
    summary = GroupEvidenceSummary(
        member_count=len(members),
        validation_mode=validation_mode,
        evaluated_pair_count=len(pairs),
        possible_pair_count=possible,
        strong_support_count=counts[IdentityEdgeClass.STRONG_SUPPORT],
        review_support_count=counts[IdentityEdgeClass.REVIEW_SUPPORT],
        non_groupable_count=counts[IdentityEdgeClass.NON_GROUPABLE],
        cannot_link_count=counts[IdentityEdgeClass.CANNOT_LINK],
        support_density=(
            (counts[IdentityEdgeClass.STRONG_SUPPORT]
             + counts[IdentityEdgeClass.REVIEW_SUPPORT]) / possible
            if possible else None
        ),
        strong_support_density=(
            counts[IdentityEdgeClass.STRONG_SUPPORT] / possible if possible else None
        ),
        generic_evidence_edge_count=generic_count,
        generic_member_count=None,
        protected_conflict_count=counts[IdentityEdgeClass.CANNOT_LINK],
        technical_consensus_summary=None,
        missing_evidence_count=possible - len(pairs),
        bridge_risk_flag_count=0,
        required_conflict_checks_total=possible,
        required_conflict_checks_completed=len(pairs),
        discovery_truncated=False,
        discovery_degraded=False,
        source_neighborhood_count=1,
    )
    member_references = tuple(
        next(record.record_ref_key for record in value.canonical_records
             if record.record_id == record_id)
        for record_id in members
    )
    result = IdentityGroupHypothesis(
        hypothesis_id=f"group-{'-'.join(member_references)}",
        scan_id=1,
        member_record_ids=members,
        member_record_references=member_references,
        status=status,
        validation_mode=validation_mode,
        evidence_summary=summary,
        bridge_risk_summary=bridge or BridgeRiskSummary(),
        genericity_risk_summary=genericity or GenericityRiskSummary(),
        missing_evidence_summary=missing or MissingEvidenceSummary(),
        source_neighborhood_references=("n-1",),
        hypothesis_fingerprint="",
    )
    return with_group_hypothesis_fingerprint(result)


def result(value, *, groups=(), conflicts=(), deferred=(), unassigned=(), requests=(), results=()):
    groups = tuple(groups)
    conflicts = tuple(conflicts)
    deferred = tuple(deferred)
    requests = tuple(requests)
    results = tuple(results)
    metrics = IdentityResolutionMetrics(
        source_record_count=len(value.canonical_records),
        accepted_group_count=len(groups),
        likely_group_count=sum(
            item.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
            for item in groups
        ),
        review_group_count=sum(
            item.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
            for item in groups
        ),
        conflict_count=len(conflicts),
        deferred_work_unit_count=len(deferred),
        unassigned_record_count=len(unassigned),
        targeted_evidence_request_count=len(requests),
        targeted_evidence_result_count=len(results),
    )
    built = IdentityResolutionResult(
        scan_id=1,
        accepted_groups=groups,
        conflicts=conflicts,
        deferred_work_units=deferred,
        unassigned_record_ids=tuple(unassigned),
        unassigned_record_references=tuple(
            next(record.record_ref_key for record in value.canonical_records
                 if record.record_id == record_id)
            for record_id in unassigned
        ),
        targeted_evidence_requests=requests,
        targeted_evidence_results=results,
        metrics=metrics,
        resolver_algorithm_version=value.resolver_algorithm_version,
        resolution_fingerprint="",
    )
    return with_resolution_result_fingerprint(built)


def constraint(left, right, kind):
    left, right = sorted((left, right))
    return IdentityResolutionConstraint(
        1, left, right, kind, "G6_EFFECTIVE_GROUP_REVIEW", "review-1"
    )


def test_all_gf5a_contracts_are_immutable_and_exclude_pair_business_and_llm_authority():
    contracts = (
        ResolverConfiguration, IdentityResolutionNeighborhood,
        IdentityResolutionEvidenceEdge, IdentityResolutionConstraint,
        TargetedEvidenceRequest, TargetedEvidenceResult, BridgeRiskSummary,
        GenericityRiskSummary, MissingEvidenceSummary, GroupEvidenceSummary,
        IdentityGroupHypothesis, IdentityConflict, DeferredIdentityWorkUnit,
        IdentityResolutionMetrics, IdentityResolutionInput, IdentityResolutionResult,
    )
    forbidden = {
        "duplicate_candidate_status", "pair_llm_result", "pair_feedback",
        "g1_group_result", "g2_group_result", "final_reviewed_identity_set",
        "group_confidence", "provider_response",
    }
    for contract_type in contracts:
        assert dataclasses.is_dataclass(contract_type)
        assert contract_type.__dataclass_params__.frozen is True
        assert not forbidden & {field.name for field in dataclasses.fields(contract_type)}


def test_resolution_input_rejects_cross_scan_noncanonical_and_duplicate_references():
    valid = resolution_input(2, [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)])
    validate_resolution_input(valid)
    with pytest.raises(IdentityResolutionValidationError, match="crosses resolution scan"):
        validate_resolution_input(replace(
            valid, canonical_records=(record(1), record(2, scan_id=2))
        ))
    with pytest.raises(IdentityResolutionValidationError, match="must be unique"):
        validate_resolution_input(replace(
            valid, machine_evidence_edges=(
                edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
                edge(1, 2, IdentityEdgeClass.REVIEW_SUPPORT),
            )
        ))


def test_targeted_request_rejects_self_pair_noncanonical_pair_and_tampering():
    request = with_targeted_request_fingerprint(TargetedEvidenceRequest(
        1, 1, 2, TargetedEvidenceReason.BRIDGE_CROSS_CHECK, "n-1", "",
        "scan-1-row-0", "scan-1-row-1",
    ))
    validate_targeted_evidence_request(request)
    with pytest.raises(IdentityResolutionValidationError, match="self-pair"):
        validate_targeted_evidence_request(replace(request, record_id_2=1))
    with pytest.raises(IdentityResolutionValidationError, match="canonical order"):
        validate_targeted_evidence_request(replace(request, record_id_1=2, record_id_2=1))
    with pytest.raises(IdentityResolutionValidationError, match="fingerprint"):
        validate_targeted_evidence_request(replace(request, requesting_work_unit_reference="other"))


def test_g6_effective_constraint_adapter_uses_canonical_record_ids_and_keeps_authority():
    records = (record(1), record(2))
    source = SimpleNamespace(
        scan_id=1,
        left_record_ref_key=records[1].record_ref_key,
        right_record_ref_key=records[0].record_ref_key,
        constraint_type=SimpleNamespace(value="CANNOT_LINK"),
        source_review_event_ids=(8, 4, 8),
    )
    assert adapt_effective_human_constraints(
        scan_id=1, canonical_records=records, effective_constraints=(source,)
    ) == (IdentityResolutionConstraint(
        1, 1, 2, IdentityResolutionConstraintType.CANNOT_LINK,
        "G6_EFFECTIVE_GROUP_REVIEW", "4,8",
    ),)


def test_all_strong_complete_pairwise_group_validates_and_false_complete_claim_fails():
    value = resolution_input(3, [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    likely = group(value, (1, 2, 3), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    validate_group_hypothesis(likely, value)
    incomplete_input = resolution_input(3, value.machine_evidence_edges[:2])
    incomplete = group(
        incomplete_input, (1, 2, 3),
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
    )
    with pytest.raises(IdentityResolutionValidationError, match="missing internal evidence"):
        validate_group_hypothesis(incomplete, incomplete_input)


@pytest.mark.parametrize("human", [False, True])
def test_machine_and_human_cannot_links_prevent_accepted_co_membership(human):
    constraints = (
        constraint(1, 2, IdentityResolutionConstraintType.CANNOT_LINK),
    ) if human else ()
    machine = IdentityEdgeClass.STRONG_SUPPORT if human else IdentityEdgeClass.CANNOT_LINK
    value = resolution_input(2, [edge(1, 2, machine)], constraints=constraints)
    candidate = group(
        value, (1, 2),
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
    )
    expected = "human CANNOT_LINK" if human else "protected cannot-link"
    with pytest.raises(IdentityResolutionValidationError, match=expected):
        validate_group_hypothesis(candidate, value)


def test_human_must_link_cannot_override_protected_machine_cannot_link():
    value = resolution_input(
        2,
        [edge(1, 2, IdentityEdgeClass.CANNOT_LINK)],
        constraints=(constraint(1, 2, IdentityResolutionConstraintType.MUST_LINK),),
    )
    conflict = with_identity_conflict_fingerprint(IdentityConflict(
        "conflict-1", 1, (1, 2), ("scan-1-row-0", "scan-1-row-1"),
        IdentityConflictType.HUMAN_MACHINE_AUTHORITY_CONFLICT,
        ("edge-1-2-CANNOT_LINK",), ("n-1",),
        "human must-link conflicts with protected machine cannot-link", "",
    ))
    output = result(value, conflicts=(conflict,), unassigned=(1, 2))
    validate_resolution_result(output, value)


def test_generic_pair_may_be_review_but_generic_only_chain_cannot_validate():
    pair_input = resolution_input(2, [
        edge(1, 2, IdentityEdgeClass.REVIEW_SUPPORT, generic=True)
    ])
    pair_group = group(
        pair_input, (1, 2),
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        genericity=GenericityRiskSummary(True, True, (), True),
    )
    validate_group_hypothesis(pair_group, pair_input)

    chain_input = resolution_input(3, [
        edge(1, 2, IdentityEdgeClass.REVIEW_SUPPORT, generic=True),
        edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
        edge(2, 3, IdentityEdgeClass.REVIEW_SUPPORT, generic=True),
    ])
    chain = group(
        chain_input, (1, 2, 3),
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        genericity=GenericityRiskSummary(True, True, (2,), True),
    )
    with pytest.raises(IdentityResolutionValidationError, match="generic-only"):
        validate_group_hypothesis(chain, chain_input)


def test_unresolved_bridge_and_progressive_mode_cannot_validate_as_likely():
    value = resolution_input(3, [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    bridged = group(
        value, (1, 2, 3), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP,
        bridge=BridgeRiskSummary(articulation_record_ids=(2,), unresolved=True),
    )
    with pytest.raises(IdentityResolutionValidationError, match="unresolved bridge"):
        validate_group_hypothesis(bridged, value)
    progressive = group(
        value, (1, 2, 3), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP,
        validation_mode=IdentityValidationMode.PROGRESSIVE_TARGETED,
    )
    with pytest.raises(IdentityResolutionValidationError, match="progressive likely"):
        validate_group_hypothesis(progressive, value)


def test_resolution_result_rejects_duplicate_accepted_membership():
    value = resolution_input(3, [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    left = group(value, (1, 2), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    right = group(value, (2, 3), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    output = result(value, groups=(left, right))
    with pytest.raises(IdentityResolutionValidationError, match="two accepted groups"):
        validate_resolution_result(output, value)


def test_fingerprints_ignore_collection_input_order_and_reject_semantic_tampering():
    request = TargetedEvidenceRequest(
        1, 1, 2, TargetedEvidenceReason.PARTITION_CROSS_CHECK, "n-1", "",
        "scan-1-row-0", "scan-1-row-1",
    )
    first = with_targeted_request_fingerprint(request)
    second = with_targeted_request_fingerprint(replace(request))
    assert first.request_fingerprint == second.request_fingerprint
    different_database_ids = with_targeted_request_fingerprint(replace(
        request, record_id_1=101, record_id_2=202
    ))
    assert different_database_ids.request_fingerprint == first.request_fingerprint

    value = resolution_input(2, [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)])
    accepted = group(value, (1, 2), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    assert accepted.hypothesis_fingerprint == with_group_hypothesis_fingerprint(
        replace(accepted, source_neighborhood_references=tuple(reversed(
            accepted.source_neighborhood_references
        )))
    ).hypothesis_fingerprint
    with pytest.raises(IdentityResolutionValidationError, match="fingerprint"):
        validate_group_hypothesis(replace(accepted, hypothesis_id="tampered"), value)


def test_deferred_bounds_are_not_conflicts_and_unassigned_is_not_non_duplicate():
    value = resolution_input(1)
    deferred = with_deferred_work_unit_fingerprint(DeferredIdentityWorkUnit(
        "deferred-1", 1, (1,), ("scan-1-row-0",),
        DeferredIdentityReason.RESOLUTION_MEMBER_CAP_REACHED,
        "bounded work remains unfinished", (), "",
    ))
    output = result(value, deferred=(deferred,), unassigned=(1,))
    validate_resolution_result(output, value)
    assert output.conflicts == ()
    assert output.unassigned_record_ids == (1,)


def test_missing_bridge_requires_targeted_request_before_likely_acceptance():
    value = resolution_input(3, [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    request = with_targeted_request_fingerprint(TargetedEvidenceRequest(
        1, 1, 3, TargetedEvidenceReason.BRIDGE_CROSS_CHECK, "n-1", "",
        "scan-1-row-0", "scan-1-row-2",
    ))
    output = result(value, unassigned=(1, 2, 3), requests=(request,))
    validate_resolution_result(output, value)
    premature = group(
        value, (1, 2, 3), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
    )
    with pytest.raises(IdentityResolutionValidationError, match="missing internal evidence"):
        validate_group_hypothesis(premature, value)


def test_targeted_result_adapts_pure_gf4_shape_without_reclassification():
    request = with_targeted_request_fingerprint(TargetedEvidenceRequest(
        1, 1, 3, TargetedEvidenceReason.BRIDGE_CROSS_CHECK, "n-1", "",
        "scan-1-row-0", "scan-1-row-2",
    ))
    evaluated = SimpleNamespace(
        record_id_1=1,
        record_id_2=3,
        edge_class=IdentityEdgeClass.CANNOT_LINK,
        classification_reason_codes=("CRITICAL_MISMATCH_SIZE",),
        rule_decision="BLOCK",
        evaluation_algorithm_version="canonical-identity-evaluator-v1",
        evidence_fingerprint="evaluated-1-3",
        generic_evidence_json='{"generic_guard_reason":""}',
    )
    adapted = targeted_result_from_evaluation(request, evaluated)
    assert adapted.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert adapted.evidence_fingerprint == "evaluated-1-3"
    assert adapted.request is request


def test_hard_triangle_conflict_allows_safe_subgroup_salvage_with_traceability():
    value = resolution_input(3, [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.CANNOT_LINK),
        edge(2, 3, IdentityEdgeClass.REVIEW_SUPPORT),
    ])
    safe = group(value, (1, 2), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    conflict = with_identity_conflict_fingerprint(IdentityConflict(
        "conflict-abc", 1, (1, 2, 3),
        ("scan-1-row-0", "scan-1-row-1", "scan-1-row-2"),
        IdentityConflictType.PROTECTED_CANNOT_LINK,
        ("edge-1-3-CANNOT_LINK",), ("n-1",),
        "the original family contains a protected contradiction", "",
    ))
    output = result(value, groups=(safe,), conflicts=(conflict,), unassigned=(3,))
    validate_resolution_result(output, value)
    assert output.accepted_groups[0].member_record_ids == (1, 2)
    assert output.conflicts[0].involved_record_ids == (1, 2, 3)


def test_neutral_cross_branch_chain_cannot_validate_from_connectivity_alone():
    value = resolution_input(3, [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
        edge(2, 3, IdentityEdgeClass.REVIEW_SUPPORT),
    ])
    connected = group(
        value, (1, 2, 3),
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
    )
    with pytest.raises(IdentityResolutionValidationError, match="neutral gaps"):
        validate_group_hypothesis(connected, value)


def test_two_disjoint_groups_validate_without_merging_broader_context():
    neighborhoods = (
        IdentityResolutionNeighborhood("n-1", 1, 20, (1, 2), False, False),
        IdentityResolutionNeighborhood("n-2", 1, 20, (3, 4), False, False),
    )
    value = resolution_input(4, [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(3, 4, IdentityEdgeClass.STRONG_SUPPORT),
    ], neighborhoods=neighborhoods)
    first = replace(
        group(value, (1, 2), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP),
        source_neighborhood_references=("n-1",), hypothesis_fingerprint="",
    )
    first = with_group_hypothesis_fingerprint(first)
    second = replace(
        group(value, (3, 4), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP),
        source_neighborhood_references=("n-2",), hypothesis_fingerprint="",
    )
    second = with_group_hypothesis_fingerprint(second)
    output = result(value, groups=(first, second))
    validate_resolution_result(output, value)


def test_site_and_uom_context_do_not_override_strong_gf4_edge_semantics():
    records = (
        record(1, uom="EA"),
        replace(record(2, uom="BOX"), contract="S2"),
    )
    value = resolution_input(
        2, [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)], records=records
    )
    accepted = group(value, (1, 2), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    validate_group_hypothesis(accepted, value)


def test_protected_variant_and_discovery_truncation_cannot_be_likely():
    variant_input = resolution_input(2, [edge(1, 2, IdentityEdgeClass.CANNOT_LINK)])
    variant = group(
        variant_input, (1, 2),
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
    )
    with pytest.raises(IdentityResolutionValidationError, match="protected cannot-link"):
        validate_group_hypothesis(variant, variant_input)

    value = resolution_input(2, [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)])
    accepted = group(value, (1, 2), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    truncated_summary = replace(accepted.evidence_summary, discovery_truncated=True)
    truncated = with_group_hypothesis_fingerprint(replace(
        accepted, evidence_summary=truncated_summary, hypothesis_fingerprint=""
    ))
    with pytest.raises(IdentityResolutionValidationError, match="truncated discovery"):
        validate_group_hypothesis(truncated, value)


def test_identical_business_values_remain_distinct_canonical_members():
    first = record(1, source_row_index=10, part_no="SAME")
    second = replace(
        record(2, source_row_index=11, part_no="SAME"),
        description=first.description,
        normalized_description=first.normalized_description,
        source_record_fingerprint=first.source_record_fingerprint,
    )
    value = resolution_input(
        2, [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)], records=(first, second)
    )
    accepted = group(value, (1, 2), IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP)
    validate_group_hypothesis(accepted, value)
    assert accepted.member_record_ids == (1, 2)
    assert value.canonical_records[0].record_ref_key != value.canonical_records[1].record_ref_key
