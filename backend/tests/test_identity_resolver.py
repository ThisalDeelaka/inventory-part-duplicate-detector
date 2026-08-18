import dataclasses
import inspect
from dataclasses import replace

import pytest

from app.engine.identity_edge import IdentityEdgeClass
from app.engine.identity_evidence_evaluator import DeterministicIdentityContext
from app.resolution import resolver as resolver_module
from app.resolution.contracts import (
    DeferredIdentityReason,
    IdentityConflictType,
    IdentityGroupHypothesisStatus,
    IdentityResolutionConstraint,
    IdentityResolutionConstraintType,
    IdentityResolutionEvidenceEdge,
    IdentityResolutionInput,
    IdentityResolutionNeighborhood,
    ResolverConfiguration,
    TargetedEvidenceResult,
)
from app.resolution.resolver import (
    CanonicalEvaluatorTargetedEvidenceProvider,
    resolve_identity_groups,
)
from app.services.canonical_record_service import CanonicalScanRecord


def record(
    record_id,
    *,
    source_row_index=None,
    part_no=None,
    description=None,
    contract="S1",
    uom="EA",
):
    source_row_index = record_id - 1 if source_row_index is None else source_row_index
    part_no = part_no or f"P-{record_id}"
    description = description or f"SPECIFIC ITEM MODEL {record_id}"
    return CanonicalScanRecord(
        record_id=record_id,
        scan_id=1,
        source_row_index=source_row_index,
        record_ref_key=f"scan-1-row-{source_row_index:03d}",
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
        normalized_part_no=part_no.replace("-", "").upper(),
        normalized_description=description.upper(),
        normalization_version="test-v1",
    )


def edge(left, right, edge_class, *, generic=False):
    left, right = sorted((left, right))
    return IdentityResolutionEvidenceEdge(
        scan_id=1,
        evidence_run_id=30,
        record_id_1=left,
        record_id_2=right,
        edge_class=edge_class,
        reason_codes=(f"TEST_{edge_class.value}",),
        evidence_fingerprint=f"edge-{left}-{right}-{edge_class.value}",
        generic_only=generic,
    )


def neighborhood(reference, members, *, truncated=False, degraded=False):
    return IdentityResolutionNeighborhood(
        reference, 1, 20, tuple(sorted(members)), truncated, degraded
    )


def constraint(left, right, kind, *, reference="review-1"):
    left, right = sorted((left, right))
    return IdentityResolutionConstraint(
        1, left, right, kind, "G6_EFFECTIVE_GROUP_REVIEW", reference
    )


def resolver_input(
    records,
    edges=(),
    *,
    neighborhoods=None,
    constraints=(),
    max_members=20,
    targeted_budget=40,
    pairwise_limit=8,
):
    records = tuple(records)
    if neighborhoods is None:
        neighborhoods = (
            neighborhood("n-1", tuple(item.record_id for item in records)),
        ) if len(records) >= 2 else ()
    return IdentityResolutionInput(
        scan_id=1,
        discovery_run_id=20,
        evidence_run_id=30,
        canonical_records=records,
        identity_neighborhoods=tuple(neighborhoods),
        machine_evidence_edges=tuple(edges),
        human_constraints=tuple(constraints),
        resolver_algorithm_version="constrained-identity-resolver-v1",
        resolver_configuration=ResolverConfiguration(
            max_members, targeted_budget, pairwise_limit, "resolver-config-v1"
        ),
    )


class FakeTargetedProvider:
    def __init__(self, outcomes=None, *, fail=False):
        self.outcomes = outcomes or {}
        self.fail = fail
        self.calls = []

    def evaluate(self, request):
        self.calls.append(request)
        if self.fail:
            raise RuntimeError("deterministic evaluator failed")
        edge_class, generic = self.outcomes.get(
            (request.record_id_1, request.record_id_2),
            (IdentityEdgeClass.NON_GROUPABLE, False),
        )
        return TargetedEvidenceResult(
            request=request,
            edge_class=edge_class,
            reason_codes=(f"TARGETED_{edge_class.value}",),
            evidence_summary=f"targeted {edge_class.value}",
            evaluator_version="fake-deterministic-v1",
            evidence_fingerprint=(
                f"targeted-{request.record_id_1}-{request.record_id_2}-{edge_class.value}"
            ),
            generic_only=generic,
        )


def memberships(result):
    return tuple(group.member_record_ids for group in result.accepted_groups)


def statuses(result):
    return tuple(group.status for group in result.accepted_groups)


def test_g1_all_strong_triangle_is_complete_pairwise_likely():
    value = resolver_input([record(1), record(2), record(3)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(result) == ((1, 2, 3),)
    assert statuses(result) == (IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP,)
    assert result.conflicts == result.deferred_work_units == ()


def test_g2_hard_contradiction_forbids_triangle_and_keeps_conflict_visible():
    value = resolver_input([record(1), record(2), record(3)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.CANNOT_LINK),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert (1, 2, 3) not in memberships(result)
    assert any(item.conflict_type == IdentityConflictType.PROTECTED_CANNOT_LINK
               for item in result.conflicts)
    assert result.unassigned_record_ids == (1, 2, 3)


def test_g3_missing_bridge_is_requested_before_triangle_becomes_likely():
    value = resolver_input([record(1), record(2), record(3)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    provider = FakeTargetedProvider({
        (1, 3): (IdentityEdgeClass.STRONG_SUPPORT, False)
    })
    result = resolve_identity_groups(value, provider)
    assert len(provider.calls) == 1
    assert provider.calls[0].reason.value == "BRIDGE_CROSS_CHECK"
    assert memberships(result) == ((1, 2, 3),)


def test_g4_neutral_cross_branch_salvages_strong_pair_not_broad_review_chain():
    value = resolver_input([record(1), record(2), record(3)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
        edge(2, 3, IdentityEdgeClass.REVIEW_SUPPORT),
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(result) == ((1, 2),)
    assert result.unassigned_record_ids == (3,)


def test_g5_generic_review_chain_is_not_accepted_from_connectivity():
    value = resolver_input([record(1), record(2), record(3)], [
        edge(1, 2, IdentityEdgeClass.REVIEW_SUPPORT, generic=True),
        edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
        edge(2, 3, IdentityEdgeClass.REVIEW_SUPPORT, generic=True),
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert any(item.reason == DeferredIdentityReason.UNRESOLVED_OWNERSHIP_AMBIGUITY
               for item in result.deferred_work_units)


def test_g6_generic_pair_is_review_never_likely():
    value = resolver_input([record(1), record(2)], [
        edge(1, 2, IdentityEdgeClass.REVIEW_SUPPORT, generic=True)
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(result) == ((1, 2),)
    assert statuses(result) == (
        IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
    )


def test_g7_human_cannot_link_blocks_machine_strong_pair():
    value = resolver_input(
        [record(1), record(2)],
        [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)],
        constraints=(constraint(
            1, 2, IdentityResolutionConstraintType.CANNOT_LINK
        ),),
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert result.conflicts


def test_g8_human_must_link_cannot_override_machine_cannot_link():
    value = resolver_input(
        [record(1), record(2)],
        [edge(1, 2, IdentityEdgeClass.CANNOT_LINK)],
        constraints=(constraint(
            1, 2, IdentityResolutionConstraintType.MUST_LINK
        ),),
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert any(
        item.conflict_type == IdentityConflictType.HUMAN_MACHINE_AUTHORITY_CONFLICT
        for item in result.conflicts
    )


def test_g9_equal_overlapping_ownership_is_deferred_not_duplicated():
    value = resolver_input(
        [record(1), record(2), record(3)],
        [
            edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
            edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
            edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
        ],
        neighborhoods=(neighborhood("n-ab", (1, 2)), neighborhood("n-bc", (2, 3))),
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert any(item.reason == DeferredIdentityReason.UNRESOLVED_OWNERSHIP_AMBIGUITY
               for item in result.deferred_work_units)


def test_g10_two_disconnected_strong_pairs_remain_two_groups():
    value = resolver_input(
        [record(1), record(2), record(3), record(4)],
        [
            edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
            edge(3, 4, IdentityEdgeClass.STRONG_SUPPORT),
        ],
        neighborhoods=(neighborhood("n-ab", (1, 2)), neighborhood("n-cd", (3, 4))),
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(result) == ((1, 2), (3, 4))


def test_g11_site_and_uom_context_do_not_override_strong_edge():
    value = resolver_input(
        [record(1, contract="S1", uom="EA"), record(2, contract="S2", uom="BOX")],
        [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)],
    )
    assert memberships(resolve_identity_groups(value, FakeTargetedProvider())) == ((1, 2),)


def test_g12_protected_technical_variant_remains_conflict():
    value = resolver_input([record(1), record(2)], [
        edge(1, 2, IdentityEdgeClass.CANNOT_LINK)
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert any(item.conflict_type == IdentityConflictType.PROTECTED_CANNOT_LINK
               for item in result.conflicts)


def test_g13_truncated_discovery_is_deferred_and_never_likely():
    value = resolver_input(
        [record(1), record(2)],
        [edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)],
        neighborhoods=(neighborhood("n-truncated", (1, 2), truncated=True),),
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.DISCOVERY_TRUNCATION_REQUIRES_LATER_ANALYSIS
    )


def test_g14_record_without_discovery_is_unassigned_not_non_duplicate():
    result = resolve_identity_groups(resolver_input([record(1)]), FakeTargetedProvider())
    assert result.accepted_groups == result.conflicts == result.deferred_work_units == ()
    assert result.unassigned_record_ids == (1,)


def test_g15_duplicate_valued_source_rows_remain_distinct_members():
    first = record(1, source_row_index=10, part_no="SAME", description="SAME ITEM 100")
    second = replace(
        record(2, source_row_index=11, part_no="SAME", description="SAME ITEM 100"),
        source_record_fingerprint=first.source_record_fingerprint,
    )
    value = resolver_input((first, second), [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(result) == ((1, 2),)
    assert result.accepted_groups[0].member_record_references == (
        first.record_ref_key, second.record_ref_key
    )


def test_r1_shuffled_input_order_is_semantically_and_fingerprint_deterministic():
    records = (record(1), record(2), record(3))
    edges = (
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    neighborhoods = (
        neighborhood("n-a", (1, 2)), neighborhood("n-b", (2, 3))
    )
    constraints = (
        constraint(1, 2, IdentityResolutionConstraintType.MUST_LINK, reference="r-1"),
        constraint(2, 3, IdentityResolutionConstraintType.MUST_LINK, reference="r-2"),
    )
    first = resolver_input(records, edges, neighborhoods=neighborhoods,
                           constraints=constraints)
    shuffled = replace(
        first,
        canonical_records=tuple(reversed(records)),
        identity_neighborhoods=tuple(reversed(neighborhoods)),
        machine_evidence_edges=tuple(reversed(edges)),
        human_constraints=tuple(reversed(constraints)),
    )
    left = resolve_identity_groups(first, FakeTargetedProvider())
    right = resolve_identity_groups(shuffled, FakeTargetedProvider())
    assert left == right
    assert left.resolution_fingerprint == right.resolution_fingerprint


def test_r2_targeted_budget_exhaustion_defers_without_partial_acceptance():
    value = resolver_input(
        [record(1), record(2), record(3)],
        [
            edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
            edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
        ],
        targeted_budget=0,
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.TARGETED_EVIDENCE_BUDGET_EXHAUSTED
    )


def test_r3_overlapping_neighborhood_union_over_member_cap_is_deferred():
    value = resolver_input(
        [record(1), record(2), record(3), record(4)],
        (),
        neighborhoods=(
            neighborhood("n-1", (1, 2, 3)), neighborhood("n-2", (3, 4))
        ),
        max_members=3,
        pairwise_limit=3,
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.RESOLUTION_MEMBER_CAP_REACHED
    )


def test_r4_disjoint_strong_cliques_are_salvaged_from_one_discovery_family():
    value = resolver_input([record(1), record(2), record(3), record(4)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
        edge(1, 4, IdentityEdgeClass.NON_GROUPABLE),
        edge(2, 3, IdentityEdgeClass.REVIEW_SUPPORT),
        edge(2, 4, IdentityEdgeClass.NON_GROUPABLE),
        edge(3, 4, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(result) == ((1, 2), (3, 4))


def test_r5_conflicting_must_link_closure_is_explicit_and_not_accepted():
    value = resolver_input(
        [record(1), record(2), record(3)],
        [edge(1, 3, IdentityEdgeClass.CANNOT_LINK)],
        constraints=(
            constraint(1, 2, IdentityResolutionConstraintType.MUST_LINK, reference="r-1"),
            constraint(2, 3, IdentityResolutionConstraintType.MUST_LINK, reference="r-2"),
        ),
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert any(
        item.conflict_type == IdentityConflictType.INCOMPATIBLE_MUST_LINK_CONSTRAINTS
        for item in result.conflicts
    )


def test_r6_non_groupable_is_neutral_not_a_protected_conflict():
    value = resolver_input([record(1), record(2)], [
        edge(1, 2, IdentityEdgeClass.NON_GROUPABLE)
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == result.conflicts == ()
    assert result.unassigned_record_ids == (1, 2)


def test_r7_duplicate_values_survive_partitioning_by_record_identity():
    test_g15_duplicate_valued_source_rows_remain_distinct_members()


def test_r8_targeted_evaluator_exception_defers_without_partial_acceptance():
    value = resolver_input([record(1), record(2), record(3)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    result = resolve_identity_groups(value, FakeTargetedProvider(fail=True))
    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY
    )


def test_targeted_requests_are_deduplicated_and_evaluated_once_per_pair():
    value = resolver_input(
        [record(1), record(2), record(3)],
        [
            edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
            edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
        ],
        neighborhoods=(
            neighborhood("n-1", (1, 2, 3)), neighborhood("n-2", (1, 2, 3))
        ),
    )
    provider = FakeTargetedProvider({
        (1, 3): (IdentityEdgeClass.STRONG_SUPPORT, False)
    })
    result = resolve_identity_groups(value, provider)
    assert len(result.targeted_evidence_requests) == len(provider.calls) == 1
    assert result.metrics.targeted_evidence_cache_hit_count == 0


def test_targeted_evaluation_order_is_safety_priority_then_canonical_pair():
    value = resolver_input([record(1), record(2), record(3), record(4)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    ])
    provider = FakeTargetedProvider()
    resolve_identity_groups(value, provider)
    priorities = [
        resolver_module._REQUEST_PRIORITY[item.reason] for item in provider.calls
    ]
    assert priorities == sorted(priorities)
    bridge_pairs = [
        (item.record_id_1, item.record_id_2) for item in provider.calls
        if item.reason.value == "BRIDGE_CROSS_CHECK"
    ]
    assert bridge_pairs == sorted(bridge_pairs)


def test_compatible_human_must_link_is_positive_without_overriding_machine_evidence():
    value = resolver_input(
        [record(1), record(2)],
        (),
        neighborhoods=(neighborhood("n-human", (1, 2)),),
        constraints=(constraint(
            1, 2, IdentityResolutionConstraintType.MUST_LINK
        ),),
    )
    result = resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(result) == ((1, 2),)
    assert result.targeted_evidence_requests == ()


def test_gf4_targeted_adapter_preserves_determinism_generic_conflict_and_context():
    generic_records = (
        record(1, part_no="A", description="BEARING"),
        record(2, part_no="B", description="BEARING"),
    )
    context = DeterministicIdentityContext(
        "SAME_SITE_DUPLICATE", ("CONTRACT", "UNIT_MEAS", "ACCOUNTING_GROUP")
    )
    provider = CanonicalEvaluatorTargetedEvidenceProvider(generic_records, context)
    base = resolver_input(generic_records, (), neighborhoods=(neighborhood("n-1", (1, 2)),))
    planned = resolve_identity_groups(base, provider)
    assert len(planned.targeted_evidence_results) == 1
    assert planned.targeted_evidence_results[0].edge_class == IdentityEdgeClass.REVIEW_SUPPORT
    assert memberships(planned) == ((1, 2),)

    technical_records = (
        record(1, part_no="A", description="MOTOR 10A"),
        record(2, part_no="B", description="MOTOR 20A"),
    )
    technical = resolve_identity_groups(
        resolver_input(technical_records, (), neighborhoods=(neighborhood("n-1", (1, 2)),)),
        CanonicalEvaluatorTargetedEvidenceProvider(technical_records, context),
    )
    assert technical.targeted_evidence_results[0].edge_class == IdentityEdgeClass.CANNOT_LINK
    assert technical.accepted_groups == ()
    assert any(item.conflict_type == IdentityConflictType.PROTECTED_CANNOT_LINK
               for item in technical.conflicts)

    contextual_records = (
        record(1, part_no="A", description="BEARING", contract="S1", uom="EA"),
        record(2, part_no="B", description="BEARING", contract="S2", uom="BOX"),
    )
    contextual = resolve_identity_groups(
        resolver_input(contextual_records, (), neighborhoods=(neighborhood("n-1", (1, 2)),)),
        CanonicalEvaluatorTargetedEvidenceProvider(contextual_records, context),
    )
    assert contextual.targeted_evidence_results[0].edge_class != IdentityEdgeClass.CANNOT_LINK


def test_resolver_is_library_only_and_never_imports_pair_persistence_or_providers(
    monkeypatch,
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("pure resolver attempted provider selection")

    monkeypatch.setattr("app.llm.factory.create_llm_provider", forbidden)
    monkeypatch.setattr(
        "app.llm.group_provider_factory.create_group_advisory_provider", forbidden
    )
    value = resolver_input([record(1), record(2)], [
        edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT)
    ])
    assert memberships(resolve_identity_groups(value, FakeTargetedProvider())) == ((1, 2),)
    source = inspect.getsource(resolver_module)
    forbidden_names = (
        "DuplicateCandidate", "DuplicateFeedback", "RuleExclusionAudit",
        "IdentityGroupProjectionRun", "IdentityGroupSnapshot", "sqlalchemy",
        "app.repositories", "scan_runner",
    )
    assert not any(name in source for name in forbidden_names)


def test_bounded_search_metrics_are_reported_for_controlled_six_member_case():
    records = [record(index) for index in range(1, 7)]
    edges = []
    for members in ((1, 2, 3), (4, 5, 6)):
        edges.extend(
            edge(left, right, IdentityEdgeClass.STRONG_SUPPORT)
            for left, right in __import__("itertools").combinations(members, 2)
        )
    for left in (1, 2, 3):
        for right in (4, 5, 6):
            edges.append(edge(left, right, IdentityEdgeClass.NON_GROUPABLE))
    result = resolve_identity_groups(resolver_input(records, edges), FakeTargetedProvider())
    assert set(memberships(result)) == {(1, 2, 3), (4, 5, 6)}
    assert result.metrics.work_unit_count == 1
    assert 0 < result.metrics.candidate_partitions_explored < 20 * 20 * 41
    assert result.metrics.targeted_evidence_request_count == 0
    assert result.metrics.targeted_evidence_cache_hit_count == 0
