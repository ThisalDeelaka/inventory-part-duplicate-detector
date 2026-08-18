"""Pure, bounded, deterministic GF-5B constrained identity resolver."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations
from typing import Protocol

from app.engine.identity_edge import IdentityEdgeClass
from app.engine.identity_evidence_evaluator import (
    DeterministicIdentityContext,
    evaluate_canonical_identity_relationship,
)
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
    IdentityResolutionConstraintType,
    IdentityResolutionInput,
    IdentityResolutionMetrics,
    IdentityResolutionResult,
    IdentityValidationMode,
    MissingEvidenceSummary,
    TargetedEvidenceReason,
    TargetedEvidenceRequest,
    TargetedEvidenceResult,
)
from app.resolution.fingerprints import fingerprint_payload
from app.resolution.validation import (
    IdentityResolutionValidationError,
    targeted_result_from_evaluation,
    validate_group_hypothesis,
    validate_resolution_input,
    validate_resolution_result,
    validate_targeted_evidence_request,
    with_deferred_work_unit_fingerprint,
    with_group_hypothesis_fingerprint,
    with_identity_conflict_fingerprint,
    with_resolution_result_fingerprint,
    with_targeted_request_fingerprint,
)


class TargetedEvidenceProvider(Protocol):
    def evaluate(self, request: TargetedEvidenceRequest) -> TargetedEvidenceResult:
        """Return deterministic evidence for one canonical relationship."""


class CanonicalEvaluatorTargetedEvidenceProvider:
    """In-memory adapter over the existing pure GF-4 canonical evaluator."""

    def __init__(
        self,
        canonical_records,
        context: DeterministicIdentityContext,
    ):
        self._records = {record.record_id: record for record in canonical_records}
        self._context = context

    def evaluate(self, request: TargetedEvidenceRequest) -> TargetedEvidenceResult:
        validate_targeted_evidence_request(request)
        try:
            left = self._records[request.record_id_1]
            right = self._records[request.record_id_2]
        except KeyError as exc:
            raise IdentityResolutionValidationError(
                "targeted request references a record outside the evaluator catalog"
            ) from exc
        evaluated = evaluate_canonical_identity_relationship(left, right, self._context)
        return targeted_result_from_evaluation(request, evaluated)


@dataclass(frozen=True)
class _WorkUnit:
    member_ids: tuple[int, ...]
    neighborhood_references: tuple[str, ...]
    truncated: bool
    degraded: bool


@dataclass
class _ExecutionCounters:
    candidate_partitions_explored: int = 0
    targeted_cache_hits: int = 0


@dataclass(frozen=True)
class _Candidate:
    group: IdentityGroupHypothesis
    members: frozenset[int]
    objective: tuple[int, int, int]


_REQUEST_PRIORITY = {
    TargetedEvidenceReason.BRIDGE_CROSS_CHECK: 0,
    TargetedEvidenceReason.OWNERSHIP_AMBIGUITY_CHECK: 1,
    TargetedEvidenceReason.LIKELY_GROUP_COMPLETENESS_CHECK: 2,
    TargetedEvidenceReason.PARTITION_CROSS_CHECK: 3,
}


def _pair(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left < right else (right, left)


def _normalize_input(value: IdentityResolutionInput) -> IdentityResolutionInput:
    """Canonicalize collection order before applying strict GF-5A validation."""
    neighborhoods = tuple(sorted((
        replace(item, member_record_ids=tuple(sorted(item.member_record_ids)))
        for item in value.identity_neighborhoods
    ), key=lambda item: item.neighborhood_reference))
    edges = tuple(sorted(value.machine_evidence_edges, key=lambda item: (
        item.record_id_1, item.record_id_2
    )))
    constraints = tuple(sorted(value.human_constraints, key=lambda item: (
        item.record_id_1, item.record_id_2, item.constraint_type.value
    )))
    normalized = replace(
        value,
        canonical_records=tuple(sorted(value.canonical_records, key=lambda item: item.record_id)),
        identity_neighborhoods=neighborhoods,
        machine_evidence_edges=edges,
        human_constraints=constraints,
    )
    validate_resolution_input(normalized)
    return normalized


class _UnionFind:
    def __init__(self, members):
        self.parent = {member: member for member in members}

    def find(self, member):
        parent = self.parent[member]
        if parent != member:
            self.parent[member] = self.find(parent)
        return self.parent[member]

    def union(self, left, right):
        first, second = self.find(left), self.find(right)
        if first == second:
            return
        low, high = sorted((first, second))
        self.parent[high] = low


def _work_units(value: IdentityResolutionInput) -> tuple[_WorkUnit, ...]:
    record_ids = tuple(record.record_id for record in value.canonical_records)
    union = _UnionFind(record_ids)
    active = set()
    for neighborhood in value.identity_neighborhoods:
        members = neighborhood.member_record_ids
        active.update(members)
        for member in members[1:]:
            union.union(members[0], member)
    for edge in value.machine_evidence_edges:
        active.update((edge.record_id_1, edge.record_id_2))
        union.union(edge.record_id_1, edge.record_id_2)
    for constraint in value.human_constraints:
        if constraint.constraint_type == IdentityResolutionConstraintType.MUST_LINK:
            active.update((constraint.record_id_1, constraint.record_id_2))
            union.union(constraint.record_id_1, constraint.record_id_2)

    components = {}
    for member in sorted(active):
        components.setdefault(union.find(member), []).append(member)
    output = []
    for members in components.values():
        member_set = set(members)
        neighborhoods = tuple(
            item for item in value.identity_neighborhoods
            if member_set.intersection(item.member_record_ids)
        )
        output.append(_WorkUnit(
            member_ids=tuple(sorted(members)),
            neighborhood_references=tuple(sorted(
                item.neighborhood_reference for item in neighborhoods
            )),
            truncated=any(item.truncated for item in neighborhoods),
            degraded=any(item.degraded for item in neighborhoods),
        ))
    return tuple(sorted(output, key=lambda item: item.member_ids))


def _machine_lookup(value):
    return {
        (edge.record_id_1, edge.record_id_2): (edge.edge_class, edge.generic_only)
        for edge in value.machine_evidence_edges
    }


def _effective_lookup(value, targeted_results):
    lookup = _machine_lookup(value)
    for result in targeted_results:
        request = result.request
        lookup[(request.record_id_1, request.record_id_2)] = (
            result.edge_class, result.generic_only
        )
    for constraint in value.human_constraints:
        pair = (constraint.record_id_1, constraint.record_id_2)
        current = lookup.get(pair)
        if constraint.constraint_type == IdentityResolutionConstraintType.CANNOT_LINK:
            lookup[pair] = (IdentityEdgeClass.CANNOT_LINK, False)
        elif not current or current[0] != IdentityEdgeClass.CANNOT_LINK:
            lookup[pair] = (IdentityEdgeClass.STRONG_SUPPORT, False)
    return lookup


def _positive_adjacency(member_ids, lookup):
    adjacency = {member: set() for member in member_ids}
    for left, right in combinations(member_ids, 2):
        evidence = lookup.get((left, right))
        if evidence and evidence[0] in {
            IdentityEdgeClass.STRONG_SUPPORT, IdentityEdgeClass.REVIEW_SUPPORT
        }:
            adjacency[left].add(right)
            adjacency[right].add(left)
    return adjacency


def _has_positive_path(left, right, adjacency):
    pending = [left]
    seen = {left}
    while pending:
        current = pending.pop()
        if current == right:
            return True
        for neighbor in sorted(adjacency[current], reverse=True):
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return False


def _target_reason(left, right, member_ids, lookup):
    adjacency = _positive_adjacency(member_ids, lookup)
    if _has_positive_path(left, right, adjacency):
        return TargetedEvidenceReason.BRIDGE_CROSS_CHECK
    if adjacency[left] and adjacency[right]:
        return TargetedEvidenceReason.OWNERSHIP_AMBIGUITY_CHECK
    known = [lookup.get(pair) for pair in combinations(member_ids, 2)]
    if known and all(item is None or item[0] == IdentityEdgeClass.STRONG_SUPPORT for item in known):
        return TargetedEvidenceReason.LIKELY_GROUP_COMPLETENESS_CHECK
    return TargetedEvidenceReason.PARTITION_CROSS_CHECK


def _targeted_requests(value, unit, lookup):
    references = {record.record_id: record.record_ref_key for record in value.canonical_records}
    requests = []
    for left, right in combinations(unit.member_ids, 2):
        if (left, right) in lookup:
            continue
        reason = _target_reason(left, right, unit.member_ids, lookup)
        request = TargetedEvidenceRequest(
            scan_id=value.scan_id,
            record_id_1=left,
            record_id_2=right,
            reason=reason,
            requesting_work_unit_reference=(
                "|".join(unit.neighborhood_references)
                or f"records:{','.join(map(str, unit.member_ids))}"
            ),
            request_fingerprint="",
            record_reference_1=references[left],
            record_reference_2=references[right],
        )
        requests.append(with_targeted_request_fingerprint(request))
    return tuple(sorted(requests, key=lambda item: (
        _REQUEST_PRIORITY[item.reason], item.record_id_1, item.record_id_2,
        item.request_fingerprint,
    )))


def _connected_count(member_ids, adjacency, *, excluded=None):
    remaining = [member for member in member_ids if member != excluded]
    if not remaining:
        return 0
    pending = [remaining[0]]
    seen = {remaining[0]}
    while pending:
        current = pending.pop()
        for neighbor in adjacency[current]:
            if neighbor != excluded and neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return len(seen)


def _bridge_summary(member_ids, lookup):
    adjacency = _positive_adjacency(member_ids, lookup)
    connected = _connected_count(member_ids, adjacency) == len(member_ids)
    articulation = tuple(sorted(
        member for member in member_ids
        if len(member_ids) >= 3 and connected
        and _connected_count(member_ids, adjacency, excluded=member) < len(member_ids) - 1
    ))
    branches = tuple(sorted(member for member in member_ids if len(adjacency[member]) == 1))
    neutral = tuple(
        pair for pair in combinations(member_ids, 2)
        if lookup.get(pair, (None, False))[0] == IdentityEdgeClass.NON_GROUPABLE
    )
    missing = tuple(pair for pair in combinations(member_ids, 2) if pair not in lookup)
    generic_hubs = []
    for member in member_ids:
        incident = []
        for neighbor in adjacency[member]:
            incident.append(lookup[_pair(member, neighbor)])
        if len(incident) >= 2 and all(item[1] for item in incident):
            generic_hubs.append(member)
    unresolved = bool(missing or generic_hubs or (
        neutral and (articulation or branches or not connected)
    ))
    return BridgeRiskSummary(
        articulation_record_ids=articulation,
        single_edge_branch_record_ids=branches,
        neutral_cross_branch_pairs=neutral,
        missing_cross_branch_pairs=missing,
        generic_hub_record_ids=tuple(generic_hubs),
        competing_partition_evidence=(),
        unresolved=unresolved,
    )


def _build_group(value, unit, members, lookup, targeted_results):
    members = tuple(sorted(members))
    internal = [lookup.get(pair) for pair in combinations(members, 2)]
    if any(item is None for item in internal):
        return None
    counts = {
        edge_class: sum(item[0] == edge_class for item in internal)
        for edge_class in IdentityEdgeClass
    }
    if counts[IdentityEdgeClass.CANNOT_LINK]:
        return None
    positive = counts[IdentityEdgeClass.STRONG_SUPPORT] + counts[IdentityEdgeClass.REVIEW_SUPPORT]
    if not positive:
        return None
    possible = len(internal)
    generic_count = sum(item[1] for item in internal)
    generic_members = {
        member for pair, evidence in zip(combinations(members, 2), internal)
        if evidence[1] for member in pair
    }
    bridge = _bridge_summary(members, lookup)
    genericity = GenericityRiskSummary(
        generic_description_burden=bool(generic_count),
        review_only_support=(
            counts[IdentityEdgeClass.STRONG_SUPPORT] == 0
            and counts[IdentityEdgeClass.REVIEW_SUPPORT] > 0
        ),
        hub_dependency_record_ids=bridge.generic_hub_record_ids,
        insufficient_independent_identity_evidence=(
            len(members) >= 3
            and counts[IdentityEdgeClass.STRONG_SUPPORT] == 0
            and generic_count == counts[IdentityEdgeClass.REVIEW_SUPPORT]
        ),
    )
    status = (
        IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
        if counts[IdentityEdgeClass.STRONG_SUPPORT] == possible
        else IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
    )
    summary = GroupEvidenceSummary(
        member_count=len(members),
        validation_mode=IdentityValidationMode.COMPLETE_PAIRWISE,
        evaluated_pair_count=possible,
        possible_pair_count=possible,
        strong_support_count=counts[IdentityEdgeClass.STRONG_SUPPORT],
        review_support_count=counts[IdentityEdgeClass.REVIEW_SUPPORT],
        non_groupable_count=counts[IdentityEdgeClass.NON_GROUPABLE],
        cannot_link_count=0,
        support_density=positive / possible,
        strong_support_density=counts[IdentityEdgeClass.STRONG_SUPPORT] / possible,
        generic_evidence_edge_count=generic_count,
        generic_member_count=len(generic_members),
        protected_conflict_count=0,
        technical_consensus_summary=None,
        missing_evidence_count=0,
        bridge_risk_flag_count=(
            len(bridge.articulation_record_ids)
            + len(bridge.single_edge_branch_record_ids)
            + len(bridge.neutral_cross_branch_pairs)
            + len(bridge.generic_hub_record_ids)
        ),
        required_conflict_checks_total=possible,
        required_conflict_checks_completed=possible,
        discovery_truncated=unit.truncated,
        discovery_degraded=unit.degraded,
        source_neighborhood_count=len(unit.neighborhood_references),
    )
    references = {
        record.record_id: record.record_ref_key for record in value.canonical_records
    }
    member_references = tuple(references[member] for member in members)
    hypothesis_reference = "gf5b-" + fingerprint_payload("hypothesis-reference", {
        "scan_id": value.scan_id,
        "members": member_references,
        "resolver_version": value.resolver_algorithm_version,
    })
    group = IdentityGroupHypothesis(
        hypothesis_id=hypothesis_reference,
        scan_id=value.scan_id,
        member_record_ids=members,
        member_record_references=member_references,
        status=status,
        validation_mode=IdentityValidationMode.COMPLETE_PAIRWISE,
        evidence_summary=summary,
        bridge_risk_summary=bridge,
        genericity_risk_summary=genericity,
        missing_evidence_summary=MissingEvidenceSummary(),
        source_neighborhood_references=unit.neighborhood_references,
        hypothesis_fingerprint="",
    )
    group = with_group_hypothesis_fingerprint(group)
    try:
        validate_group_hypothesis(
            group, value, targeted_results=tuple(targeted_results)
        )
    except IdentityResolutionValidationError:
        return None
    return group


def _candidate_groups(value, unit, lookup, targeted_results, counters):
    limit = value.resolver_configuration.complete_pairwise_member_limit
    maximum_explored = (
        value.resolver_configuration.max_resolution_members ** 2
        * max(1, value.resolver_configuration.max_targeted_checks_per_work_unit + 1)
    )
    candidates = []
    exhausted = False
    starting_count = counters.candidate_partitions_explored
    for size in range(min(len(unit.member_ids), limit), 1, -1):
        for members in combinations(unit.member_ids, size):
            counters.candidate_partitions_explored += 1
            if counters.candidate_partitions_explored - starting_count > maximum_explored:
                exhausted = True
                break
            group = _build_group(value, unit, members, lookup, targeted_results)
            if group is None:
                continue
            summary = group.evidence_summary
            candidates.append(_Candidate(
                group=group,
                members=frozenset(members),
                objective=(
                    len(members),
                    len(members) if group.status
                    == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP else 0,
                    summary.strong_support_count,
                ),
            ))
        if exhausted:
            break
    unique = {candidate.group.hypothesis_fingerprint: candidate for candidate in candidates}
    return tuple(sorted(unique.values(), key=lambda item: item.group.hypothesis_id)), exhausted


def _select_partition(value, candidates, counters):
    maximum_explored = (
        value.resolver_configuration.max_resolution_members ** 2
        * max(1, value.resolver_configuration.max_targeted_checks_per_work_unit + 1)
    )
    best_objective = None
    best_partitions = set()
    exhausted = False
    starting_count = counters.candidate_partitions_explored

    def visit(index, selected, used):
        nonlocal best_objective, exhausted
        counters.candidate_partitions_explored += 1
        if counters.candidate_partitions_explored - starting_count > maximum_explored:
            exhausted = True
            return
        if index == len(candidates):
            groups = tuple(candidates[item].group for item in selected)
            covered = len(used)
            likely_members = sum(
                len(group.member_record_ids)
                for group in groups
                if group.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
            )
            strong = sum(group.evidence_summary.strong_support_count for group in groups)
            review = sum(group.evidence_summary.review_support_count for group in groups)
            objective = (covered, likely_members, strong, -review, -len(groups))
            signature = tuple(sorted(group.hypothesis_fingerprint for group in groups))
            if best_objective is None or objective > best_objective:
                best_objective = objective
                best_partitions.clear()
                best_partitions.add(signature)
            elif objective == best_objective:
                best_partitions.add(signature)
            return
        visit(index + 1, selected, used)
        if exhausted:
            return
        candidate = candidates[index]
        if not (used & candidate.members):
            visit(index + 1, selected + (index,), used | candidate.members)

    visit(0, (), frozenset())
    if exhausted or not best_partitions:
        return (), True, False
    by_fingerprint = {
        candidate.group.hypothesis_fingerprint: candidate.group
        for candidate in candidates
    }
    if len(best_partitions) == 1:
        signature = next(iter(best_partitions))
        return tuple(sorted((by_fingerprint[item] for item in signature),
                            key=lambda item: item.hypothesis_id)), False, False
    common = set.intersection(*(set(partition) for partition in best_partitions))
    stable = tuple(sorted((by_fingerprint[item] for item in common),
                          key=lambda item: item.hypothesis_id))
    return stable, False, True


def _artifact_reference(kind, payload):
    return f"gf5b-{kind}-" + fingerprint_payload(kind, payload)


def _conflict(value, unit, conflict_type, involved_ids, evidence_references, summary):
    references = {record.record_id: record.record_ref_key for record in value.canonical_records}
    involved_ids = tuple(sorted(set(involved_ids)))
    involved_refs = tuple(references[item] for item in involved_ids)
    artifact = IdentityConflict(
        conflict_id=_artifact_reference("conflict-reference", {
            "type": conflict_type,
            "members": involved_refs,
            "evidence": tuple(sorted(set(evidence_references))),
        }),
        scan_id=value.scan_id,
        involved_record_ids=involved_ids,
        involved_record_references=involved_refs,
        conflict_type=conflict_type,
        protected_evidence_references=tuple(sorted(set(evidence_references))),
        source_neighborhood_references=unit.neighborhood_references,
        summary=summary,
        fingerprint="",
    )
    return with_identity_conflict_fingerprint(artifact)


def _deferred(value, unit, reason, summary, member_ids=None):
    references = {record.record_id: record.record_ref_key for record in value.canonical_records}
    member_ids = tuple(sorted(member_ids or unit.member_ids))
    member_refs = tuple(references[item] for item in member_ids)
    artifact = DeferredIdentityWorkUnit(
        deferred_id=_artifact_reference("deferred-reference", {
            "reason": reason, "members": member_refs,
            "neighborhoods": unit.neighborhood_references,
        }),
        scan_id=value.scan_id,
        record_ids=member_ids,
        record_references=member_refs,
        reason=reason,
        unfinished_evidence_summary=summary,
        source_neighborhood_references=unit.neighborhood_references,
        fingerprint="",
    )
    return with_deferred_work_unit_fingerprint(artifact)


def _constraint_conflicts(value, unit):
    machine = _machine_lookup(value)
    must_links = [
        item for item in value.human_constraints
        if item.constraint_type == IdentityResolutionConstraintType.MUST_LINK
        and item.record_id_1 in unit.member_ids and item.record_id_2 in unit.member_ids
    ]
    cannot_links = {
        (item.record_id_1, item.record_id_2): item
        for item in value.human_constraints
        if item.constraint_type == IdentityResolutionConstraintType.CANNOT_LINK
    }
    conflicts = []
    direct_authority = []
    for item in must_links:
        pair = (item.record_id_1, item.record_id_2)
        if machine.get(pair, (None, False))[0] == IdentityEdgeClass.CANNOT_LINK:
            direct_authority.append(item)
    if direct_authority:
        conflicts.append(_conflict(
            value, unit, IdentityConflictType.HUMAN_MACHINE_AUTHORITY_CONFLICT,
            tuple(member for item in direct_authority
                  for member in (item.record_id_1, item.record_id_2)),
            tuple(item.source_reference for item in direct_authority),
            "human must-link conflicts with protected deterministic cannot-link",
        ))

    union = _UnionFind(unit.member_ids)
    for item in must_links:
        union.union(item.record_id_1, item.record_id_2)
    closure_conflicts = []
    for left, right in combinations(unit.member_ids, 2):
        if union.find(left) != union.find(right):
            continue
        pair = (left, right)
        if (
            machine.get(pair, (None, False))[0] == IdentityEdgeClass.CANNOT_LINK
            or pair in cannot_links
        ):
            closure_conflicts.append(pair)
    if closure_conflicts and not direct_authority:
        conflicts.append(_conflict(
            value, unit, IdentityConflictType.INCOMPATIBLE_MUST_LINK_CONSTRAINTS,
            tuple(member for pair in closure_conflicts for member in pair),
            tuple(
                cannot_links[pair].source_reference
                if pair in cannot_links else f"machine:{pair[0]}:{pair[1]}"
                for pair in closure_conflicts
            ),
            "must-link closure would force a protected cannot-link into one partition",
        ))
    blocked = {
        member for pair in closure_conflicts for member in pair
    } | {
        member for item in direct_authority
        for member in (item.record_id_1, item.record_id_2)
    }
    return tuple(conflicts), blocked


def _protected_conflict(value, unit, lookup, targeted_results=()):
    machine_by_pair = {
        (edge.record_id_1, edge.record_id_2): edge
        for edge in value.machine_evidence_edges
    }
    human_by_pair = {
        (item.record_id_1, item.record_id_2): item
        for item in value.human_constraints
        if item.constraint_type == IdentityResolutionConstraintType.CANNOT_LINK
    }
    targeted_by_pair = {
        (item.request.record_id_1, item.request.record_id_2): item
        for item in targeted_results
    }
    pairs = tuple(
        pair for pair in combinations(unit.member_ids, 2)
        if lookup.get(pair, (None, False))[0] == IdentityEdgeClass.CANNOT_LINK
    )
    if not pairs:
        return None
    evidence = []
    for pair in pairs:
        if pair in machine_by_pair:
            evidence.append(machine_by_pair[pair].evidence_fingerprint)
        if pair in human_by_pair:
            evidence.append(human_by_pair[pair].source_reference)
        if pair in targeted_by_pair:
            evidence.append(targeted_by_pair[pair].evidence_fingerprint)
    return _conflict(
        value, unit, IdentityConflictType.PROTECTED_CANNOT_LINK,
        tuple(member for pair in pairs for member in pair),
        tuple(evidence) or tuple(f"protected:{left}:{right}" for left, right in pairs),
        "work unit contains protected cannot-link evidence",
    )


def resolve_identity_groups(
    resolution_input: IdentityResolutionInput,
    targeted_evidence_provider: TargetedEvidenceProvider | None,
) -> IdentityResolutionResult:
    """Resolve immutable GF-5 inputs without persistence or external authority."""
    value = _normalize_input(resolution_input)
    units = _work_units(value)
    counters = _ExecutionCounters()
    accepted = []
    conflicts = []
    deferred = []
    all_requests = []
    all_results = []
    targeted_cache = {}

    for unit in units:
        constraint_conflicts, blocked = _constraint_conflicts(value, unit)
        conflicts.extend(constraint_conflicts)
        base_lookup = _effective_lookup(value, ())
        protected = _protected_conflict(value, unit, base_lookup)
        if protected is not None:
            conflicts.append(protected)
        if len(unit.member_ids) > value.resolver_configuration.max_resolution_members:
            deferred.append(_deferred(
                value, unit, DeferredIdentityReason.RESOLUTION_MEMBER_CAP_REACHED,
                "overlapping discovery work unit exceeds max_resolution_members",
            ))
            continue
        if unit.truncated:
            deferred.append(_deferred(
                value, unit,
                DeferredIdentityReason.DISCOVERY_TRUNCATION_REQUIRES_LATER_ANALYSIS,
                "truncated discovery may affect membership or ownership",
            ))
            continue

        schedulable = replace(
            unit,
            member_ids=tuple(member for member in unit.member_ids if member not in blocked),
        )
        if len(schedulable.member_ids) < 2:
            continue
        planned = _targeted_requests(value, schedulable, base_lookup)
        budget = value.resolver_configuration.max_targeted_checks_per_work_unit
        scheduled = planned[:budget]
        all_requests.extend(scheduled)
        evaluation_failed = False
        unit_results = []
        for request in scheduled:
            pair = (request.record_id_1, request.record_id_2)
            if pair in targeted_cache:
                counters.targeted_cache_hits += 1
                unit_results.append(targeted_cache[pair])
                continue
            if targeted_evidence_provider is None:
                evaluation_failed = True
                continue
            try:
                result = targeted_evidence_provider.evaluate(request)
                if result.request.request_fingerprint != request.request_fingerprint:
                    raise IdentityResolutionValidationError(
                        "targeted provider returned a result for another request"
                    )
                targeted_cache[pair] = result
                unit_results.append(result)
            except Exception:
                evaluation_failed = True
        all_results.extend(unit_results)
        if len(planned) > budget:
            deferred.append(_deferred(
                value, unit,
                DeferredIdentityReason.TARGETED_EVIDENCE_BUDGET_EXHAUSTED,
                "required deterministic targeted checks exceed the work-unit budget",
            ))
            continue
        if planned and (evaluation_failed or len(unit_results) != len(planned)):
            deferred.append(_deferred(
                value, unit, DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY,
                "required deterministic targeted evidence could not be completed",
            ))
            continue

        lookup = _effective_lookup(value, unit_results)
        targeted_protected = _protected_conflict(
            value, unit, lookup, targeted_results=unit_results
        )
        if targeted_protected is not None:
            conflicts.append(targeted_protected)
        candidates, generation_exhausted = _candidate_groups(
            value, schedulable, lookup, unit_results, counters
        )
        if generation_exhausted:
            deferred.append(_deferred(
                value, unit, DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY,
                "bounded candidate generation limit was reached",
            ))
            continue
        selected, search_exhausted, ambiguous = _select_partition(
            value, candidates, counters
        )
        if search_exhausted:
            deferred.append(_deferred(
                value, unit, DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY,
                "bounded partition-search limit was reached",
            ))
            continue
        accepted.extend(selected)
        if ambiguous:
            deferred.append(_deferred(
                value, unit, DeferredIdentityReason.UNRESOLVED_OWNERSHIP_AMBIGUITY,
                "equally supported disjoint partitions leave ownership unresolved",
            ))

    accepted = tuple(sorted(accepted, key=lambda item: item.hypothesis_id))
    conflicts = tuple(sorted(
        {item.fingerprint: item for item in conflicts}.values(),
        key=lambda item: item.conflict_id,
    ))
    deferred = tuple(sorted(
        {item.fingerprint: item for item in deferred}.values(),
        key=lambda item: item.deferred_id,
    ))
    requests = tuple(sorted(
        {item.request_fingerprint: item for item in all_requests}.values(),
        key=lambda item: (item.record_id_1, item.record_id_2, item.reason.value),
    ))
    results = tuple(sorted(
        {item.request.request_fingerprint: item for item in all_results}.values(),
        key=lambda item: item.request.request_fingerprint,
    ))
    accepted_members = {
        member for group in accepted for member in group.member_record_ids
    }
    unassigned_ids = tuple(
        record.record_id for record in value.canonical_records
        if record.record_id not in accepted_members
    )
    references = {record.record_id: record.record_ref_key for record in value.canonical_records}
    metrics = IdentityResolutionMetrics(
        source_record_count=len(value.canonical_records),
        accepted_group_count=len(accepted),
        likely_group_count=sum(
            group.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
            for group in accepted
        ),
        review_group_count=sum(
            group.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
            for group in accepted
        ),
        conflict_count=len(conflicts),
        deferred_work_unit_count=len(deferred),
        unassigned_record_count=len(unassigned_ids),
        targeted_evidence_request_count=len(requests),
        targeted_evidence_result_count=len(results),
        work_unit_count=len(units),
        candidate_partitions_explored=counters.candidate_partitions_explored,
        targeted_evidence_cache_hit_count=counters.targeted_cache_hits,
    )
    output = IdentityResolutionResult(
        scan_id=value.scan_id,
        accepted_groups=accepted,
        conflicts=conflicts,
        deferred_work_units=deferred,
        unassigned_record_ids=unassigned_ids,
        unassigned_record_references=tuple(references[item] for item in unassigned_ids),
        targeted_evidence_requests=requests,
        targeted_evidence_results=results,
        metrics=metrics,
        resolver_algorithm_version=value.resolver_algorithm_version,
        resolution_fingerprint="",
    )
    output = with_resolution_result_fingerprint(output)
    validate_resolution_result(output, value)
    return output
