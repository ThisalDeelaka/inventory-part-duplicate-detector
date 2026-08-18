"""Pure GF-5A safety validators and normalization adapters."""

from __future__ import annotations

import json
from dataclasses import replace
from itertools import combinations

from app.engine.identity_edge import IdentityEdgeClass
from app.resolution.contracts import (
    DeferredIdentityWorkUnit,
    DeferredIdentityReason,
    IdentityConflict,
    IdentityConflictType,
    IdentityGroupHypothesis,
    IdentityGroupHypothesisStatus,
    IdentityResolutionConstraint,
    IdentityResolutionConstraintType,
    IdentityResolutionEvidenceEdge,
    IdentityResolutionInput,
    IdentityResolutionResult,
    IdentityValidationMode,
    ResolverConfiguration,
    TargetedEvidenceRequest,
    TargetedEvidenceReason,
    TargetedEvidenceResult,
)
from app.resolution.fingerprints import (
    deferred_identity_work_unit_fingerprint,
    identity_conflict_fingerprint,
    identity_group_hypothesis_fingerprint,
    identity_resolution_result_fingerprint,
    targeted_evidence_request_fingerprint,
)


class IdentityResolutionValidationError(ValueError):
    """Raised when a constructed resolver artifact violates a frozen invariant."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IdentityResolutionValidationError(message)


def _nonblank(value: str, label: str) -> None:
    _require(bool(str(value or "").strip()), f"{label} must be nonblank")


def _canonical_ids(values: tuple[int, ...], label: str, *, minimum: int = 0) -> None:
    _require(len(values) >= minimum, f"{label} requires at least {minimum} records")
    _require(all(isinstance(value, int) and value > 0 for value in values),
             f"{label} record IDs must be positive integers")
    _require(tuple(sorted(values)) == values, f"{label} must use canonical record order")
    _require(len(set(values)) == len(values), f"{label} must not contain duplicate members")


def _canonical_pair(record_id_1: int, record_id_2: int, label: str) -> None:
    _require(record_id_1 > 0 and record_id_2 > 0, f"{label} endpoints must be positive")
    _require(record_id_1 != record_id_2, f"{label} cannot be a self-pair")
    _require(record_id_1 < record_id_2, f"{label} endpoints must use canonical order")


def _canonical_texts(values: tuple[str, ...], label: str) -> None:
    _require(all(bool(str(value or "").strip()) for value in values),
             f"{label} values must be nonblank")
    _require(tuple(sorted(values)) == values, f"{label} must use canonical order")
    _require(len(set(values)) == len(values), f"{label} values must be unique")


def _unique_texts(values: tuple[str, ...], label: str) -> None:
    _require(all(bool(str(value or "").strip()) for value in values),
             f"{label} values must be nonblank")
    _require(len(set(values)) == len(values), f"{label} values must be unique")


def _canonical_pairs(values: tuple[tuple[int, int], ...], label: str) -> None:
    for left, right in values:
        _canonical_pair(left, right, label)
    _require(tuple(sorted(values)) == values, f"{label} must use canonical order")
    _require(len(set(values)) == len(values), f"{label} pairs must be unique")


def validate_resolver_configuration(configuration: ResolverConfiguration) -> None:
    _require(configuration.max_resolution_members >= 2,
             "max_resolution_members must be at least 2")
    _require(configuration.max_targeted_checks_per_work_unit >= 0,
             "max_targeted_checks_per_work_unit must be non-negative")
    _require(configuration.complete_pairwise_member_limit >= 2,
             "complete_pairwise_member_limit must be at least 2")
    _require(
        configuration.complete_pairwise_member_limit
        <= configuration.max_resolution_members,
        "complete_pairwise_member_limit cannot exceed max_resolution_members",
    )
    _nonblank(configuration.configuration_version, "configuration_version")


def validate_targeted_evidence_request(request: TargetedEvidenceRequest) -> None:
    _require(request.scan_id > 0, "targeted request scan_id must be positive")
    _canonical_pair(request.record_id_1, request.record_id_2, "targeted request")
    _require(isinstance(request.reason, TargetedEvidenceReason),
             "targeted request reason is not allowlisted")
    _nonblank(request.requesting_work_unit_reference, "requesting_work_unit_reference")
    _nonblank(request.record_reference_1, "targeted record_reference_1")
    _nonblank(request.record_reference_2, "targeted record_reference_2")
    _require(request.record_reference_1 != request.record_reference_2,
             "targeted request record references must be distinct")
    expected = targeted_evidence_request_fingerprint(request)
    _require(request.request_fingerprint == expected,
             "targeted request fingerprint does not match its canonical payload")


def with_targeted_request_fingerprint(request: TargetedEvidenceRequest):
    return replace(
        request,
        request_fingerprint=targeted_evidence_request_fingerprint(request),
    )


def targeted_result_from_evaluation(
    request: TargetedEvidenceRequest, evaluated_relationship
) -> TargetedEvidenceResult:
    """Adapt the pure GF-4 evaluator result without persistence or reclassification."""
    validate_targeted_evidence_request(request)
    _require(
        (evaluated_relationship.record_id_1, evaluated_relationship.record_id_2)
        == (request.record_id_1, request.record_id_2),
        "targeted evaluator result endpoints do not match the request",
    )
    try:
        generic_evidence = json.loads(evaluated_relationship.generic_evidence_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise IdentityResolutionValidationError(
            "targeted evaluator generic evidence is not valid JSON"
        ) from exc
    return TargetedEvidenceResult(
        request=request,
        edge_class=evaluated_relationship.edge_class,
        reason_codes=tuple(sorted(evaluated_relationship.classification_reason_codes)),
        evidence_summary=evaluated_relationship.rule_decision,
        evaluator_version=evaluated_relationship.evaluation_algorithm_version,
        evidence_fingerprint=evaluated_relationship.evidence_fingerprint,
        generic_only=bool(generic_evidence.get("generic_guard_reason")),
    )


def adapt_effective_human_constraints(
    *, scan_id: int, canonical_records, effective_constraints
) -> tuple[IdentityResolutionConstraint, ...]:
    """Normalize the narrow G6 read contract without depending on G6 persistence."""
    record_id_by_ref = {
        record.record_ref_key: record.record_id
        for record in canonical_records
        if record.scan_id == scan_id
    }
    normalized = []
    for item in effective_constraints:
        if item.scan_id != scan_id:
            raise IdentityResolutionValidationError("human constraint crosses scans")
        try:
            left = record_id_by_ref[item.left_record_ref_key]
            right = record_id_by_ref[item.right_record_ref_key]
        except KeyError as exc:
            raise IdentityResolutionValidationError(
                "human constraint references a record outside the canonical catalog"
            ) from exc
        first, second = sorted((left, right))
        source_ids = tuple(sorted(set(item.source_review_event_ids)))
        normalized.append(IdentityResolutionConstraint(
            scan_id=scan_id,
            record_id_1=first,
            record_id_2=second,
            constraint_type=IdentityResolutionConstraintType(item.constraint_type.value),
            source_authority="G6_EFFECTIVE_GROUP_REVIEW",
            source_reference=",".join(str(value) for value in source_ids),
        ))
    return tuple(sorted(
        normalized,
        key=lambda item: (item.record_id_1, item.record_id_2, item.constraint_type.value),
    ))


def validate_resolution_input(value: IdentityResolutionInput) -> None:
    _require(value.scan_id > 0, "resolution input scan_id must be positive")
    _require(value.discovery_run_id > 0, "discovery_run_id must be positive")
    _require(value.evidence_run_id > 0, "evidence_run_id must be positive")
    _nonblank(value.resolver_algorithm_version, "resolver_algorithm_version")
    validate_resolver_configuration(value.resolver_configuration)

    record_ids = tuple(record.record_id for record in value.canonical_records)
    _canonical_ids(record_ids, "canonical_records")
    _require(all(record.scan_id == value.scan_id for record in value.canonical_records),
             "canonical record crosses resolution scan")
    known = set(record_ids)

    neighborhood_order = tuple(
        neighborhood.neighborhood_reference for neighborhood in value.identity_neighborhoods
    )
    _require(tuple(sorted(neighborhood_order)) == neighborhood_order,
             "identity neighborhoods must use deterministic order")
    _require(len(set(neighborhood_order)) == len(neighborhood_order),
             "identity neighborhood references must be unique")
    for neighborhood in value.identity_neighborhoods:
        _nonblank(neighborhood.neighborhood_reference, "neighborhood_reference")
        _require(neighborhood.scan_id == value.scan_id,
                 "identity neighborhood crosses resolution scan")
        _require(neighborhood.discovery_run_id == value.discovery_run_id,
                 "identity neighborhood belongs to another discovery run")
        _canonical_ids(neighborhood.member_record_ids, "identity neighborhood", minimum=2)
        _require(set(neighborhood.member_record_ids) <= known,
                 "identity neighborhood references an unknown canonical record")

    edge_keys = []
    for edge in value.machine_evidence_edges:
        _require(edge.scan_id == value.scan_id, "machine evidence crosses resolution scan")
        _require(edge.evidence_run_id == value.evidence_run_id,
                 "machine evidence belongs to another evidence run")
        _canonical_pair(edge.record_id_1, edge.record_id_2, "machine evidence")
        _require({edge.record_id_1, edge.record_id_2} <= known,
                 "machine evidence references an unknown canonical record")
        _nonblank(edge.evidence_fingerprint, "machine evidence fingerprint")
        _require(isinstance(edge.edge_class, IdentityEdgeClass),
                 "machine evidence edge class is not allowlisted")
        _canonical_texts(edge.reason_codes, "machine evidence reason codes")
        edge_keys.append((edge.record_id_1, edge.record_id_2))
    _require(tuple(sorted(edge_keys)) == tuple(edge_keys),
             "machine evidence must use deterministic pair order")
    _require(len(set(edge_keys)) == len(edge_keys), "machine evidence pairs must be unique")

    constraint_keys = []
    for constraint in value.human_constraints:
        _require(constraint.scan_id == value.scan_id, "human constraint crosses scans")
        _canonical_pair(constraint.record_id_1, constraint.record_id_2, "human constraint")
        _require({constraint.record_id_1, constraint.record_id_2} <= known,
                 "human constraint references an unknown canonical record")
        _nonblank(constraint.source_authority, "constraint source_authority")
        _nonblank(constraint.source_reference, "constraint source_reference")
        _require(isinstance(
            constraint.constraint_type, IdentityResolutionConstraintType
        ), "human constraint type is not allowlisted")
        constraint_keys.append((
            constraint.record_id_1,
            constraint.record_id_2,
            constraint.constraint_type.value,
        ))
    _require(tuple(sorted(constraint_keys)) == tuple(constraint_keys),
             "human constraints must use deterministic order")
    _require(len(set(constraint_keys)) == len(constraint_keys),
             "human constraints must be unique")


def _evidence_lookup(
    resolution_input: IdentityResolutionInput,
    targeted_results: tuple[TargetedEvidenceResult, ...] = (),
) -> dict[tuple[int, int], tuple[IdentityEdgeClass, bool]]:
    lookup = {
        (edge.record_id_1, edge.record_id_2): (edge.edge_class, edge.generic_only)
        for edge in resolution_input.machine_evidence_edges
    }
    for result in targeted_results:
        request = result.request
        lookup[(request.record_id_1, request.record_id_2)] = (
            result.edge_class, result.generic_only
        )
    return lookup


def validate_group_hypothesis(
    group: IdentityGroupHypothesis,
    resolution_input: IdentityResolutionInput,
    *,
    targeted_results: tuple[TargetedEvidenceResult, ...] = (),
) -> None:
    _require(group.scan_id == resolution_input.scan_id, "group hypothesis crosses scans")
    _canonical_ids(group.member_record_ids, "accepted group", minimum=2)
    known = {record.record_id for record in resolution_input.canonical_records}
    _require(set(group.member_record_ids) <= known,
             "accepted group references an unknown canonical record")
    _nonblank(group.hypothesis_id, "hypothesis_id")
    _require(group.validation_mode == group.evidence_summary.validation_mode,
             "group validation mode disagrees with its evidence summary")
    _require(isinstance(group.status, IdentityGroupHypothesisStatus),
             "group status is not allowlisted")
    _require(isinstance(group.validation_mode, IdentityValidationMode),
             "group validation mode is not allowlisted")
    _require(group.evidence_summary.member_count == len(group.member_record_ids),
             "group member count disagrees with its evidence summary")
    _require(len(group.member_record_references) == len(group.member_record_ids),
             "group record references do not align with member IDs")
    _unique_texts(group.member_record_references, "group member record references")
    expected_refs = tuple(
        next(record.record_ref_key for record in resolution_input.canonical_records
             if record.record_id == record_id)
        for record_id in group.member_record_ids
    )
    _require(group.member_record_references == expected_refs,
             "group member references do not match the canonical catalog")
    possible = len(group.member_record_ids) * (len(group.member_record_ids) - 1) // 2
    summary = group.evidence_summary
    count_fields = (
        summary.member_count, summary.evaluated_pair_count, summary.possible_pair_count,
        summary.strong_support_count, summary.review_support_count,
        summary.non_groupable_count, summary.cannot_link_count,
        summary.generic_evidence_edge_count, summary.protected_conflict_count,
        summary.missing_evidence_count, summary.bridge_risk_flag_count,
        summary.required_conflict_checks_total,
        summary.required_conflict_checks_completed, summary.source_neighborhood_count,
    )
    _require(all(isinstance(item, int) and item >= 0 for item in count_fields),
             "group evidence counts must be non-negative integers")
    for density in (summary.support_density, summary.strong_support_density):
        _require(density is None or 0.0 <= density <= 1.0,
                 "group evidence density must be null or between zero and one")
    _require(summary.possible_pair_count == possible,
             "possible pair count does not match group membership")
    counted = (
        summary.strong_support_count + summary.review_support_count
        + summary.non_groupable_count + summary.cannot_link_count
    )
    _require(summary.evaluated_pair_count == counted,
             "evaluated pair count does not reconcile by edge class")
    _require(summary.missing_evidence_count == possible - summary.evaluated_pair_count,
             "missing evidence count does not reconcile")
    _require(summary.cannot_link_count == 0 and summary.protected_conflict_count == 0,
             "accepted group summary contains a protected cannot-link")
    _require(summary.required_conflict_checks_completed <= summary.required_conflict_checks_total,
             "completed conflict checks exceed required checks")

    lookup = _evidence_lookup(resolution_input, targeted_results)
    internal_pairs = tuple(combinations(group.member_record_ids, 2))
    internal = [lookup.get(pair) for pair in internal_pairs]
    _require(not any(item and item[0] == IdentityEdgeClass.CANNOT_LINK for item in internal),
             "accepted group contains machine CANNOT_LINK evidence")
    human_cannot = {
        (item.record_id_1, item.record_id_2)
        for item in resolution_input.human_constraints
        if item.constraint_type == IdentityResolutionConstraintType.CANNOT_LINK
    }
    _require(not (set(internal_pairs) & human_cannot),
             "accepted group contains human CANNOT_LINK evidence")
    actual_counts = {
        edge_class: sum(item is not None and item[0] == edge_class for item in internal)
        for edge_class in IdentityEdgeClass
    }
    _require(
        (
            summary.strong_support_count,
            summary.review_support_count,
            summary.non_groupable_count,
            summary.cannot_link_count,
        ) == (
            actual_counts[IdentityEdgeClass.STRONG_SUPPORT],
            actual_counts[IdentityEdgeClass.REVIEW_SUPPORT],
            actual_counts[IdentityEdgeClass.NON_GROUPABLE],
            actual_counts[IdentityEdgeClass.CANNOT_LINK],
        ),
        "group evidence summary does not match internal evidence classes",
    )
    known_neighborhoods = {
        item.neighborhood_reference for item in resolution_input.identity_neighborhoods
    }
    _require(bool(group.source_neighborhood_references),
             "accepted group requires source neighborhood traceability")
    _canonical_texts(group.source_neighborhood_references,
                     "source neighborhood references")
    _require(set(group.source_neighborhood_references) <= known_neighborhoods,
             "accepted group references an unknown source neighborhood")

    if group.validation_mode == IdentityValidationMode.COMPLETE_PAIRWISE:
        _require(all(item is not None for item in internal),
                 "COMPLETE_PAIRWISE group has missing internal evidence")
        _require(summary.evaluated_pair_count == possible and summary.missing_evidence_count == 0,
                 "COMPLETE_PAIRWISE summary claims incomplete evidence")

    missing = group.missing_evidence_summary
    if group.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP:
        _require(group.validation_mode == IdentityValidationMode.COMPLETE_PAIRWISE,
                 "GF-5A does not authorize permissive progressive likely acceptance")
        _require(all(item and item[0] == IdentityEdgeClass.STRONG_SUPPORT for item in internal),
                 "LIKELY complete-pairwise group requires every pair to be STRONG_SUPPORT")
        _require(not group.bridge_risk_summary.unresolved,
                 "LIKELY group has unresolved bridge risk")
        _require(not missing.missing_pairs and not missing.incomplete_reason_codes,
                 "LIKELY group has unresolved required evidence")
        _require(not missing.unresolved_ownership_ambiguity,
                 "LIKELY group has unresolved ownership ambiguity")
        _require(not missing.discovery_truncation_affects_membership,
                 "LIKELY group is affected by discovery truncation")
        _require(not summary.discovery_truncated,
                 "LIKELY group cannot rely on truncated discovery")
        _require(not group.genericity_risk_summary.insufficient_independent_identity_evidence,
                 "LIKELY group relies on insufficient generic-only evidence")
        _require(summary.strong_support_count == possible,
                 "LIKELY group lacks complete strong cohesion")
    else:
        _require(summary.strong_support_count + summary.review_support_count > 0,
                 "REVIEW group lacks plausible positive identity evidence")
        generic_only_connectivity = (
            len(group.member_record_ids) >= 3
            and summary.strong_support_count == 0
            and summary.review_support_count > 0
            and summary.generic_evidence_edge_count == summary.review_support_count
        )
        _require(not generic_only_connectivity,
                 "multi-record generic-only review connectivity is not group cohesion")
        support_count = summary.strong_support_count + summary.review_support_count
        chain_only_with_neutral_gaps = (
            len(group.member_record_ids) >= 3
            and support_count <= len(group.member_record_ids) - 1
            and summary.non_groupable_count > 0
        )
        _require(not chain_only_with_neutral_gaps,
                 "support connectivity with neutral gaps is not sufficient review cohesion")
        _require(not group.bridge_risk_summary.unresolved,
                 "accepted REVIEW group has unresolved bridge risk")
        _require(not missing.missing_pairs and not missing.incomplete_reason_codes,
                 "accepted REVIEW group has unfinished required evidence")

    bridge = group.bridge_risk_summary
    _canonical_ids(bridge.articulation_record_ids, "bridge articulation records")
    _canonical_ids(bridge.single_edge_branch_record_ids, "single-edge branch records")
    _canonical_ids(bridge.generic_hub_record_ids, "generic hub records")
    _canonical_pairs(bridge.neutral_cross_branch_pairs, "neutral cross-branch pairs")
    _canonical_pairs(bridge.missing_cross_branch_pairs, "missing cross-branch pairs")
    _canonical_texts(bridge.competing_partition_evidence,
                     "competing partition evidence")
    _require(
        set(bridge.articulation_record_ids + bridge.single_edge_branch_record_ids
            + bridge.generic_hub_record_ids) <= set(group.member_record_ids),
        "bridge risk references a record outside the group",
    )
    _canonical_ids(group.genericity_risk_summary.hub_dependency_record_ids,
                   "generic hub dependencies")
    _canonical_pairs(missing.missing_pairs, "missing evidence pairs")
    _canonical_texts(missing.incomplete_reason_codes, "incomplete evidence reasons")

    expected = identity_group_hypothesis_fingerprint(group)
    _require(group.hypothesis_fingerprint == expected,
             "group hypothesis fingerprint does not match its canonical payload")


def with_group_hypothesis_fingerprint(group: IdentityGroupHypothesis):
    return replace(group, hypothesis_fingerprint=identity_group_hypothesis_fingerprint(group))


def _validate_conflict(conflict: IdentityConflict, resolution_input: IdentityResolutionInput):
    _require(conflict.scan_id == resolution_input.scan_id, "conflict crosses scans")
    _canonical_ids(conflict.involved_record_ids, "conflict", minimum=2)
    _require(set(conflict.involved_record_ids) <= {
        record.record_id for record in resolution_input.canonical_records
    }, "conflict references an unknown canonical record")
    _nonblank(conflict.conflict_id, "conflict_id")
    _nonblank(conflict.summary, "conflict summary")
    _require(len(conflict.involved_record_references) == len(conflict.involved_record_ids),
             "conflict record references do not align with record IDs")
    _unique_texts(conflict.involved_record_references,
                  "conflict record references")
    expected_refs = tuple(
        next(record.record_ref_key for record in resolution_input.canonical_records
             if record.record_id == record_id)
        for record_id in conflict.involved_record_ids
    )
    _require(conflict.involved_record_references == expected_refs,
             "conflict references do not match the canonical catalog")
    _require(isinstance(conflict.conflict_type, IdentityConflictType),
             "conflict type is not allowlisted")
    _canonical_texts(conflict.protected_evidence_references,
                     "protected evidence references")
    _canonical_texts(conflict.source_neighborhood_references,
                     "conflict source neighborhood references")
    _require(conflict.fingerprint == identity_conflict_fingerprint(conflict),
             "conflict fingerprint does not match its canonical payload")


def with_identity_conflict_fingerprint(conflict: IdentityConflict):
    return replace(conflict, fingerprint=identity_conflict_fingerprint(conflict))


def _validate_deferred(value: DeferredIdentityWorkUnit, resolution_input):
    _require(value.scan_id == resolution_input.scan_id, "deferred work unit crosses scans")
    _canonical_ids(value.record_ids, "deferred work unit", minimum=1)
    _require(set(value.record_ids) <= {
        record.record_id for record in resolution_input.canonical_records
    }, "deferred work unit references an unknown canonical record")
    _nonblank(value.deferred_id, "deferred_id")
    _nonblank(value.unfinished_evidence_summary, "unfinished_evidence_summary")
    _require(len(value.record_references) == len(value.record_ids),
             "deferred record references do not align with record IDs")
    _unique_texts(value.record_references, "deferred record references")
    expected_refs = tuple(
        next(record.record_ref_key for record in resolution_input.canonical_records
             if record.record_id == record_id)
        for record_id in value.record_ids
    )
    _require(value.record_references == expected_refs,
             "deferred references do not match the canonical catalog")
    _require(isinstance(value.reason, DeferredIdentityReason),
             "deferred reason is not allowlisted")
    _canonical_texts(value.source_neighborhood_references,
                     "deferred source neighborhood references")
    _require(value.fingerprint == deferred_identity_work_unit_fingerprint(value),
             "deferred work-unit fingerprint does not match its canonical payload")


def with_deferred_work_unit_fingerprint(value: DeferredIdentityWorkUnit):
    return replace(value, fingerprint=deferred_identity_work_unit_fingerprint(value))


def validate_resolution_result(
    result: IdentityResolutionResult, resolution_input: IdentityResolutionInput
) -> None:
    validate_resolution_input(resolution_input)
    _require(result.scan_id == resolution_input.scan_id, "resolution result crosses scans")
    _require(result.resolver_algorithm_version == resolution_input.resolver_algorithm_version,
             "resolution result uses another resolver version")

    request_keys = []
    known_record_ids = {record.record_id for record in resolution_input.canonical_records}
    record_reference_by_id = {
        record.record_id: record.record_ref_key
        for record in resolution_input.canonical_records
    }
    machine_pairs = {
        (edge.record_id_1, edge.record_id_2)
        for edge in resolution_input.machine_evidence_edges
    }
    for request in result.targeted_evidence_requests:
        validate_targeted_evidence_request(request)
        _require(request.scan_id == result.scan_id, "targeted request crosses scans")
        _require({request.record_id_1, request.record_id_2} <= known_record_ids,
                 "targeted request references an unknown canonical record")
        _require(
            (request.record_reference_1, request.record_reference_2) == (
                record_reference_by_id[request.record_id_1],
                record_reference_by_id[request.record_id_2],
            ),
            "targeted request references do not match the canonical catalog",
        )
        _require((request.record_id_1, request.record_id_2) not in machine_pairs,
                 "targeted request duplicates existing machine evidence")
        request_keys.append((request.record_id_1, request.record_id_2, request.reason.value))
    _require(tuple(sorted(request_keys)) == tuple(request_keys),
             "targeted evidence requests must use deterministic order")
    _require(len(set(request_keys)) == len(request_keys),
             "targeted evidence requests must be unique")
    _require(
        len(result.targeted_evidence_requests)
        <= resolution_input.resolver_configuration.max_targeted_checks_per_work_unit,
        "targeted evidence request budget exceeded",
    )
    requests_by_fingerprint = {
        request.request_fingerprint: request for request in result.targeted_evidence_requests
    }
    result_keys = []
    for targeted in result.targeted_evidence_results:
        validate_targeted_evidence_request(targeted.request)
        _require(targeted.request.request_fingerprint in requests_by_fingerprint,
                 "targeted evidence result lacks its declared request")
        _nonblank(targeted.evaluator_version, "targeted evaluator_version")
        _nonblank(targeted.evidence_fingerprint, "targeted evidence_fingerprint")
        _nonblank(targeted.evidence_summary, "targeted evidence_summary")
        _require(isinstance(targeted.edge_class, IdentityEdgeClass),
                 "targeted evidence edge class is not allowlisted")
        _canonical_texts(targeted.reason_codes, "targeted evidence reason codes")
        result_keys.append(targeted.request.request_fingerprint)
    _require(tuple(sorted(result_keys)) == tuple(result_keys),
             "targeted evidence results must use deterministic order")
    _require(len(set(result_keys)) == len(result_keys),
             "targeted evidence results must be unique")

    group_order = tuple(group.hypothesis_id for group in result.accepted_groups)
    _require(tuple(sorted(group_order)) == group_order,
             "accepted groups must use deterministic order")

    seen = set()
    for group in result.accepted_groups:
        validate_group_hypothesis(
            group, resolution_input, targeted_results=result.targeted_evidence_results
        )
        overlap = seen & set(group.member_record_ids)
        _require(not overlap, "record appears in two accepted groups")
        seen.update(group.member_record_ids)

    conflict_order = tuple(conflict.conflict_id for conflict in result.conflicts)
    _require(tuple(sorted(conflict_order)) == conflict_order,
             "conflicts must use deterministic order")
    for conflict in result.conflicts:
        _validate_conflict(conflict, resolution_input)
    deferred_order = tuple(item.deferred_id for item in result.deferred_work_units)
    _require(tuple(sorted(deferred_order)) == deferred_order,
             "deferred work units must use deterministic order")
    for deferred in result.deferred_work_units:
        _validate_deferred(deferred, resolution_input)

    _canonical_ids(result.unassigned_record_ids, "unassigned records")
    known = {record.record_id for record in resolution_input.canonical_records}
    _require(set(result.unassigned_record_ids) <= known,
             "unassigned records contain an unknown canonical record")
    _require(not (set(result.unassigned_record_ids) & seen),
             "accepted group member is also marked unassigned")
    _require(len(result.unassigned_record_references) == len(result.unassigned_record_ids),
             "unassigned record references do not align with record IDs")
    _unique_texts(result.unassigned_record_references,
                  "unassigned record references")
    _require(result.unassigned_record_references == tuple(
        record_reference_by_id[record_id] for record_id in result.unassigned_record_ids
    ), "unassigned references do not match the canonical catalog")

    metrics = result.metrics
    expected_counts = (
        len(resolution_input.canonical_records), len(result.accepted_groups),
        sum(group.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
            for group in result.accepted_groups),
        sum(group.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
            for group in result.accepted_groups),
        len(result.conflicts), len(result.deferred_work_units),
        len(result.unassigned_record_ids), len(result.targeted_evidence_requests),
        len(result.targeted_evidence_results),
    )
    actual_counts = (
        metrics.source_record_count, metrics.accepted_group_count,
        metrics.likely_group_count, metrics.review_group_count,
        metrics.conflict_count, metrics.deferred_work_unit_count,
        metrics.unassigned_record_count, metrics.targeted_evidence_request_count,
        metrics.targeted_evidence_result_count,
    )
    _require(actual_counts == expected_counts, "resolution metrics do not reconcile")
    _require(result.resolution_fingerprint == identity_resolution_result_fingerprint(result),
             "resolution fingerprint does not match its canonical payload")


def with_resolution_result_fingerprint(result: IdentityResolutionResult):
    return replace(result, resolution_fingerprint=identity_resolution_result_fingerprint(result))
