import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Iterable, Mapping

from app.engine.identity_edge import (
    IdentityEdgeClass,
    IdentityEdgeClassification,
    classify_identity_edge,
)
from app.engine.scoring import score_candidate
from app.engine.uom_relationship import MappingQuality, UomRelationship, classify_uom_relationship


GROUP_PROJECTION_VERSION = "constrained-group-projection-v1"
MAX_GROUP_VALIDATION_MEMBERS = 20


class IdentityGroupStatus(str, Enum):
    LIKELY_DUPLICATE_GROUP = "LIKELY_DUPLICATE_GROUP"
    POSSIBLE_DUPLICATE_GROUP_REVIEW = "POSSIBLE_DUPLICATE_GROUP_REVIEW"


class FamilyDiagnosticStatus(str, Enum):
    CONFLICTING_FAMILY = "CONFLICTING_FAMILY"
    DEFERRED_OVERSIZED_FAMILY = "DEFERRED_OVERSIZED_FAMILY"
    DEFERRED_AMBIGUOUS_RECORD_FAMILY = "DEFERRED_AMBIGUOUS_RECORD_FAMILY"


@dataclass(frozen=True, order=True)
class RecordRef:
    """Temporary deterministic record identity scoped to one scan."""
    key: str
    contract: str
    part_no: str
    description: str


@dataclass(frozen=True)
class InternalIdentityEdge:
    left_ref: str
    right_ref: str
    edge_class: IdentityEdgeClass
    reason_codes: tuple[str, ...]
    reused: bool


@dataclass(frozen=True)
class GroupUomSummary:
    distinct_uoms: tuple[str, ...]
    same_uom_pair_count: int
    convertible_uom_pair_count: int
    different_basis_pair_count: int
    missing_or_wildcard_pair_count: int
    malformed_or_unknown_pair_count: int
    possible_mapping_error_count: int


@dataclass(frozen=True)
class IdentityGroupHypothesis:
    hypothesis_key: str
    scan_id: int
    members: tuple[RecordRef, ...]
    group_size: int
    group_status: IdentityGroupStatus
    supporting_edge_count: int
    review_edge_count: int
    non_groupable_internal_count: int
    internal_pair_count: int
    internal_pairs_reused: int
    internal_pairs_rescored: int
    evidence_completeness: float
    uom_summary: GroupUomSummary
    reason_codes: tuple[str, ...]
    internal_edges: tuple[InternalIdentityEdge, ...]


@dataclass(frozen=True)
class ConflictFamily:
    status: FamilyDiagnosticStatus
    members: tuple[RecordRef, ...]
    seed_edge_count: int
    internal_pair_count: int
    internal_pairs_reused: int
    internal_pairs_rescored: int
    cannot_link_count: int
    reason_codes: tuple[str, ...]
    conflict_edges: tuple[InternalIdentityEdge, ...]


@dataclass(frozen=True)
class DeferredFamily:
    status: FamilyDiagnosticStatus
    members: tuple[RecordRef, ...]
    seed_edge_count: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class GroupProjectionMetrics:
    records_seen: int
    seed_edges: int
    provisional_components: int
    accepted_groups: int
    likely_groups: int
    review_groups: int
    conflicting_families: int
    oversized_families: int
    internal_pairs_total: int
    internal_pairs_reused: int
    internal_pairs_rescored: int
    cannot_links_found: int
    max_component_size: int
    max_accepted_group_size: int


@dataclass(frozen=True)
class GroupProjectionResult:
    groups: tuple[IdentityGroupHypothesis, ...]
    conflicting_families: tuple[ConflictFamily, ...]
    deferred_families: tuple[DeferredFamily, ...]
    metrics: GroupProjectionMetrics


def _value(item, name: str, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def _record_snapshot(item, side: str | None = None) -> dict:
    suffix = f"_{side}" if side else ""
    return {
        "CONTRACT": _clean(_value(item, f"contract{suffix}", _value(item, "CONTRACT", ""))),
        "PART_NO": _clean(_value(item, f"part_no{suffix}", _value(item, "PART_NO", ""))),
        "DESCRIPTION": _clean(_value(item, f"description{suffix}", _value(item, "DESCRIPTION", ""))),
        "UNIT_MEAS": _clean(_value(item, "UNIT_MEAS", "")),
        "PRODUCT_CATEGORY_ID": _clean(_value(item, "PRODUCT_CATEGORY_ID", "")),
        "HSN_SAC_CODE": _clean(_value(item, "HSN_SAC_CODE", "")),
    }


def _identity_payload(record: dict) -> str:
    return json.dumps(
        [record["CONTRACT"], record["PART_NO"], record["DESCRIPTION"]],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _record_ref(scan_id: int, record: dict) -> RecordRef:
    payload = f"scan:{scan_id}|{_identity_payload(record)}"
    return RecordRef(
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        record["CONTRACT"],
        record["PART_NO"],
        record["DESCRIPTION"],
    )


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


_EDGE_PRECEDENCE = {
    IdentityEdgeClass.NON_GROUPABLE: 0,
    IdentityEdgeClass.REVIEW_SUPPORT: 1,
    IdentityEdgeClass.STRONG_SUPPORT: 2,
    IdentityEdgeClass.CANNOT_LINK: 3,
}


def _combine_edge(
    current: IdentityEdgeClassification | None,
    incoming: IdentityEdgeClassification,
) -> IdentityEdgeClassification:
    if current is None or _EDGE_PRECEDENCE[incoming.edge_class] > _EDGE_PRECEDENCE[current.edge_class]:
        return incoming
    if incoming.edge_class == current.edge_class:
        return IdentityEdgeClassification(
            current.edge_class, tuple(sorted(set(current.reason_codes + incoming.reason_codes)))
        )
    return current


def _components(seed_edges: Mapping[tuple[str, str], IdentityEdgeClassification]):
    adjacency = defaultdict(set)
    for left, right in seed_edges:
        adjacency[left].add(right)
        adjacency[right].add(left)
    seen = set()
    output = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component = set()
        while stack:
            item = stack.pop()
            component.add(item)
            for neighbour in sorted(adjacency[item], reverse=True):
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        output.append(tuple(sorted(component)))
    return tuple(output)


def _hypothesis_key(scan_id: int, member_keys: tuple[str, ...]) -> str:
    payload = json.dumps(
        {"scan_id": scan_id, "version": GROUP_PROJECTION_VERSION, "members": member_keys},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _uom_summary(member_keys: tuple[str, ...], records: Mapping[str, dict]) -> GroupUomSummary:
    counts = defaultdict(int)
    possible_mapping_errors = 0
    for left, right in combinations(member_keys, 2):
        evidence = classify_uom_relationship(
            records[left].get("UNIT_MEAS"), records[right].get("UNIT_MEAS")
        )
        counts[evidence.relationship] += 1
        possible_mapping_errors += evidence.mapping_quality == MappingQuality.POSSIBLE_MAPPING_ERROR
    return GroupUomSummary(
        distinct_uoms=tuple(sorted({
            _clean(records[key].get("UNIT_MEAS")) for key in member_keys
            if _clean(records[key].get("UNIT_MEAS"))
        })),
        same_uom_pair_count=counts[UomRelationship.SAME_UOM],
        convertible_uom_pair_count=counts[UomRelationship.CONVERTIBLE_SAME_DIMENSION],
        different_basis_pair_count=counts[UomRelationship.DIFFERENT_DIMENSION_OR_BASIS],
        missing_or_wildcard_pair_count=counts[UomRelationship.MISSING_OR_WILDCARD],
        malformed_or_unknown_pair_count=counts[UomRelationship.MALFORMED_OR_UNKNOWN],
        possible_mapping_error_count=possible_mapping_errors,
    )


def project_identity_groups(
    *,
    scan_id: int,
    records: Iterable,
    candidates: Iterable,
    exclusions: Iterable = (),
    feedback_by_candidate_id: Mapping[int, object] | None = None,
    selected_fields: Iterable[str] = (),
    scan_mode: str = "SAME_SITE_DUPLICATE",
    max_validation_members: int = MAX_GROUP_VALIDATION_MEMBERS,
) -> GroupProjectionResult:
    """Build bounded, non-persisted identity hypotheses from existing pair evidence."""
    if scan_id <= 0:
        raise ValueError("scan_id must be positive")
    if max_validation_members < 2:
        raise ValueError("max_validation_members must be at least 2")
    candidates = tuple(candidates)
    exclusions = tuple(exclusions)
    feedback_by_candidate_id = feedback_by_candidate_id or {}
    selected_fields = tuple(selected_fields)

    record_by_ref = {}
    identity_by_ref = {}
    ambiguous_refs = set()

    def register(record):
        snapshot = _record_snapshot(record)
        ref = _record_ref(scan_id, snapshot)
        identity = _identity_payload(snapshot)
        existing_identity = identity_by_ref.get(ref.key)
        if existing_identity is not None and existing_identity != identity:
            ambiguous_refs.add(ref.key)
        existing = record_by_ref.get(ref.key)
        if existing is not None:
            merged = dict(existing)
            for field, value in snapshot.items():
                if field in {"CONTRACT", "PART_NO", "DESCRIPTION"}:
                    continue
                if merged[field] and value and merged[field] != value:
                    ambiguous_refs.add(ref.key)
                elif value:
                    merged[field] = value
            record_by_ref[ref.key] = merged
        else:
            identity_by_ref[ref.key] = identity
            record_by_ref[ref.key] = snapshot
        return ref

    for record in records:
        register(record)

    evidence_by_pair = {}
    ref_by_key = {}
    for evidence in candidates + exclusions:
        left_record = _record_snapshot(evidence, "a")
        right_record = _record_snapshot(evidence, "b")
        left_ref, right_ref = register(left_record), register(right_record)
        ref_by_key[left_ref.key], ref_by_key[right_ref.key] = left_ref, right_ref
        candidate_id = _value(evidence, "id")
        feedback = feedback_by_candidate_id.get(candidate_id) if candidate_id is not None else None
        classification = classify_identity_edge(evidence, feedback=feedback)
        pair = _pair_key(left_ref.key, right_ref.key)
        evidence_by_pair[pair] = _combine_edge(evidence_by_pair.get(pair), classification)

    for key, record in record_by_ref.items():
        ref_by_key.setdefault(key, _record_ref(scan_id, record))

    seeds = {
        pair: edge for pair, edge in evidence_by_pair.items()
        if edge.edge_class in {IdentityEdgeClass.STRONG_SUPPORT, IdentityEdgeClass.REVIEW_SUPPORT}
    }
    components = _components(seeds)
    groups = []
    conflicts = []
    deferred = []
    total_pairs = reused_total = rescored_total = cannot_total = 0
    max_component = max((len(component) for component in components), default=0)

    for component in components:
        members = tuple(sorted((ref_by_key[key] for key in component), key=lambda item: item.key))
        seed_count = sum(1 for pair in seeds if pair[0] in component and pair[1] in component)
        if any(key in ambiguous_refs for key in component):
            deferred.append(DeferredFamily(
                FamilyDiagnosticStatus.DEFERRED_AMBIGUOUS_RECORD_FAMILY,
                members,
                seed_count,
                ("AMBIGUOUS_SCAN_LOCAL_RECORD_REF",),
            ))
            continue
        if len(component) > max_validation_members:
            deferred.append(DeferredFamily(
                FamilyDiagnosticStatus.DEFERRED_OVERSIZED_FAMILY,
                members,
                seed_count,
                (f"MAX_VALIDATION_MEMBERS_{max_validation_members}",),
            ))
            continue

        internal_edges = []
        for left, right in combinations(component, 2):
            pair = _pair_key(left, right)
            classification = evidence_by_pair.get(pair)
            reused = classification is not None
            if classification is None:
                result = score_candidate(
                    record_by_ref[left], record_by_ref[right], list(selected_fields), scan_mode,
                    allow_uom_mapping_review=True,
                )
                classification = classify_identity_edge(result)
            internal_edges.append(InternalIdentityEdge(
                pair[0], pair[1], classification.edge_class,
                tuple(sorted(classification.reason_codes)), reused,
            ))
        internal_edges = tuple(sorted(internal_edges, key=lambda edge: (edge.left_ref, edge.right_ref)))
        internal_count = len(internal_edges)
        reused_count = sum(edge.reused for edge in internal_edges)
        rescored_count = internal_count - reused_count
        cannot_edges = tuple(edge for edge in internal_edges if edge.edge_class == IdentityEdgeClass.CANNOT_LINK)
        total_pairs += internal_count
        reused_total += reused_count
        rescored_total += rescored_count
        cannot_total += len(cannot_edges)
        reasons = tuple(sorted({reason for edge in internal_edges for reason in edge.reason_codes}))

        if cannot_edges:
            conflicts.append(ConflictFamily(
                FamilyDiagnosticStatus.CONFLICTING_FAMILY,
                members,
                seed_count,
                internal_count,
                reused_count,
                rescored_count,
                len(cannot_edges),
                tuple(sorted({reason for edge in cannot_edges for reason in edge.reason_codes})),
                cannot_edges,
            ))
            continue

        all_strong = all(edge.edge_class == IdentityEdgeClass.STRONG_SUPPORT for edge in internal_edges)
        status = (
            IdentityGroupStatus.LIKELY_DUPLICATE_GROUP
            if all_strong else IdentityGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
        )
        groups.append(IdentityGroupHypothesis(
            _hypothesis_key(scan_id, component),
            scan_id,
            members,
            len(members),
            status,
            sum(edge.edge_class == IdentityEdgeClass.STRONG_SUPPORT for edge in internal_edges),
            sum(edge.edge_class == IdentityEdgeClass.REVIEW_SUPPORT for edge in internal_edges),
            sum(edge.edge_class == IdentityEdgeClass.NON_GROUPABLE for edge in internal_edges),
            internal_count,
            reused_count,
            rescored_count,
            1.0,
            _uom_summary(component, record_by_ref),
            reasons,
            internal_edges,
        ))

    groups = tuple(sorted(groups, key=lambda group: group.hypothesis_key))
    conflicts = tuple(sorted(conflicts, key=lambda family: tuple(item.key for item in family.members)))
    deferred = tuple(sorted(deferred, key=lambda family: tuple(item.key for item in family.members)))
    oversized_count = sum(
        family.status == FamilyDiagnosticStatus.DEFERRED_OVERSIZED_FAMILY
        for family in deferred
    )
    metrics = GroupProjectionMetrics(
        records_seen=len(record_by_ref),
        seed_edges=len(seeds),
        provisional_components=len(components),
        accepted_groups=len(groups),
        likely_groups=sum(group.group_status == IdentityGroupStatus.LIKELY_DUPLICATE_GROUP for group in groups),
        review_groups=sum(group.group_status == IdentityGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW for group in groups),
        conflicting_families=len(conflicts),
        oversized_families=oversized_count,
        internal_pairs_total=total_pairs,
        internal_pairs_reused=reused_total,
        internal_pairs_rescored=rescored_total,
        cannot_links_found=cannot_total,
        max_component_size=max_component,
        max_accepted_group_size=max((group.group_size for group in groups), default=0),
    )
    return GroupProjectionResult(groups, conflicts, deferred, metrics)
