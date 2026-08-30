"""GF-12C1-R4 exact dense-work-unit correction acceptance tests."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations
import inspect
import statistics
import time

from app.engine.identity_edge import IdentityEdgeClass
from app.resolution import resolver
from app.resolution.contracts import DeferredIdentityReason
from test_identity_resolver import (
    FakeTargetedProvider,
    edge,
    memberships,
    neighborhood,
    record,
    resolver_input,
)


def _dense_input(
    size: int,
    *,
    pairwise_limit: int = 8,
    max_members: int = 20,
    targeted_budget: int = 40,
    cannot_links: tuple[tuple[int, int], ...] = (),
):
    cannot = {tuple(sorted(pair)) for pair in cannot_links}
    records = tuple(record(index) for index in range(1, size + 1))
    edges = tuple(
        edge(
            left,
            right,
            IdentityEdgeClass.CANNOT_LINK
            if (left, right) in cannot
            else IdentityEdgeClass.STRONG_SUPPORT,
        )
        for left, right in combinations(range(1, size + 1), 2)
    )
    return resolver_input(
        records,
        edges,
        neighborhoods=(neighborhood(f"dense-{size}", range(1, size + 1)),),
        max_members=max_members,
        targeted_budget=targeted_budget,
        pairwise_limit=pairwise_limit,
    )


def _sparse_input():
    return resolver_input(
        tuple(record(index) for index in range(1, 7)),
        (
            edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
            edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
            edge(2, 3, IdentityEdgeClass.REVIEW_SUPPORT),
            edge(4, 5, IdentityEdgeClass.STRONG_SUPPORT),
            edge(4, 6, IdentityEdgeClass.NON_GROUPABLE),
            edge(5, 6, IdentityEdgeClass.STRONG_SUPPORT),
        ),
        neighborhoods=(
            neighborhood("sparse-a", (1, 2, 3)),
            neighborhood("sparse-b", (4, 5, 6)),
        ),
    )


def _candidate_context(value):
    normalized = resolver._normalize_input(value)
    unit = resolver._work_units(normalized)[0]
    lookup = resolver._effective_lookup(normalized, ())
    return normalized, unit, lookup


def _run_generator(value, function):
    normalized, unit, lookup = _candidate_context(value)
    counters = resolver._ExecutionCounters()
    candidates, exhausted = function(normalized, unit, lookup, (), counters)
    return candidates, exhausted, counters.candidate_partitions_explored


def _assert_reference_equal(value):
    reference = _run_generator(value, resolver._candidate_groups_reference)
    corrected = _run_generator(value, resolver._candidate_groups)
    assert corrected == reference
    return corrected


def test_gf5_r1_r3_dense_shape_and_mathematical_contract_are_explicit():
    assert resolver._candidate_subset_count(18, 8) == 106_743
    value = _dense_input(18)
    assert resolver._candidate_generation_limit(value) == 16_400
    source = inspect.getsource(resolver._candidate_groups)
    assert "subset_count > maximum_explored" in source
    assert "maximum_explored + 1" in source


def test_gf5_r4_d1_sparse_reference_semantics_are_identical():
    value = _sparse_input()
    before = resolver.resolve_identity_groups(value, FakeTargetedProvider())
    assert memberships(before) == ((1, 2),)
    _assert_reference_equal(value)


def test_gf5_r5_d2_dense_10_reference_semantics_are_identical():
    candidates, exhausted, visited = _assert_reference_equal(_dense_input(10))
    assert not exhausted
    assert visited == 1_002
    assert len(candidates) == 1_002


def test_gf5_r6_d3_dense_14_bounded_reference_semantics_are_identical():
    candidates, exhausted, visited = _assert_reference_equal(
        _dense_input(14, pairwise_limit=3)
    )
    assert not exhausted
    assert visited == 455
    assert len(candidates) == 455


def test_gf5_r7_r20_d4_dense_18_uses_exact_existing_bound_in_practical_time():
    value = _dense_input(18)
    durations = []
    signatures = []
    for _ in range(3):
        started = time.perf_counter()
        result = resolver.resolve_identity_groups(value, FakeTargetedProvider())
        durations.append(time.perf_counter() - started)
        signatures.append((
            result.resolution_fingerprint,
            result.accepted_groups,
            result.deferred_work_units,
            result.targeted_evidence_requests,
            result.conflicts,
        ))
    assert statistics.median(durations) <= 25.0
    assert 129.0 / max(statistics.median(durations), 1e-9) >= 5.0
    assert signatures[0] == signatures[1] == signatures[2]
    result = resolver.resolve_identity_groups(value, FakeTargetedProvider())
    assert result.accepted_groups == ()
    assert result.deferred_work_units[0].reason == (
        DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY
    )
    assert result.metrics.candidate_partitions_explored == 16_401


def test_gf5_r9_d5_many_cannot_links_preserve_absolute_prohibition():
    cannot = tuple((1, other) for other in range(2, 11))
    value = _dense_input(10, cannot_links=cannot)
    _assert_reference_equal(value)
    result = resolver.resolve_identity_groups(value, FakeTargetedProvider())
    assert all(
        not ({1, other} <= set(group.member_record_ids))
        for other in range(2, 11)
        for group in result.accepted_groups
    )


def test_gf5_r8_r10_r12_d6_few_cannot_links_preserve_every_candidate_exactly():
    candidates, exhausted, visited = _assert_reference_equal(
        _dense_input(9, cannot_links=((1, 9),))
    )
    assert not exhausted and visited == 501
    assert candidates
    assert all(not ({1, 9} <= candidate.members) for candidate in candidates)


def test_gf5_r11_r13_r14_d7_equal_score_tie_outcome_is_unchanged():
    value = resolver_input(
        (record(1), record(2), record(3)),
        (
            edge(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
            edge(1, 3, IdentityEdgeClass.NON_GROUPABLE),
            edge(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
        ),
        neighborhoods=(neighborhood("tie", (1, 2, 3)),),
    )
    first = resolver.resolve_identity_groups(value, FakeTargetedProvider())
    second = resolver.resolve_identity_groups(value, FakeTargetedProvider())
    assert first == second
    assert first.accepted_groups == ()
    assert first.deferred_work_units[0].reason == (
        DeferredIdentityReason.UNRESOLVED_OWNERSHIP_AMBIGUITY
    )


def test_gf5_r15_d8_below_existing_boundary_uses_reference_path():
    value = _dense_input(
        12, pairwise_limit=5, max_members=13, targeted_budget=13
    )
    candidates, exhausted, visited = _assert_reference_equal(value)
    assert not exhausted and visited == 1_573 and len(candidates) == 1_573


def test_gf5_r16_d9_at_existing_boundary_uses_reference_path():
    value = _dense_input(
        13, pairwise_limit=5, max_members=13, targeted_budget=13
    )
    candidates, exhausted, visited = _assert_reference_equal(value)
    assert not exhausted and visited == 2_366 and len(candidates) == 2_366


def test_gf5_r17_d10_above_existing_boundary_matches_reference_defer_signal():
    value = _dense_input(
        14, pairwise_limit=5, max_members=14, targeted_budget=13
    )
    corrected = _run_generator(value, resolver._candidate_groups)
    reference = _run_generator(value, resolver._candidate_groups_reference)
    assert corrected == ((), True, 2_745)
    assert reference[1:] == corrected[1:]


def test_gf5_r18_r19_bounds_and_group_size_are_unchanged():
    value = _dense_input(18)
    configuration = value.resolver_configuration
    assert configuration.max_resolution_members == 20
    assert configuration.max_targeted_checks_per_work_unit == 40
    assert configuration.complete_pairwise_member_limit == 8
    assert resolver._candidate_generation_limit(value) == 20 * 20 * 41


def test_gf5_r21_three_run_dense_fixture_is_byte_deterministic():
    value = _dense_input(18)
    outputs = tuple(
        resolver.resolve_identity_groups(value, FakeTargetedProvider())
        for _ in range(3)
    )
    assert outputs[0] == outputs[1] == outputs[2]
    assert len({item.resolution_fingerprint for item in outputs}) == 1


def test_gf5_r23_r27_r28_remains_pure_provider_free_and_phase_isolated():
    source = inspect.getsource(resolver)
    assert "create_llm_provider" not in source
    assert "GROUP_LLM_PROVIDER" not in source
    assert ".env" not in source
    assert not any(
        name in source
        for name in ("NeighborProposal", "IdentityNeighborhoodSnapshot", "G2V2")
    )
