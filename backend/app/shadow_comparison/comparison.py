"""Pure deterministic GF-7A v1-to-v2 hypothesis comparison."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import replace
from itertools import combinations

from app.g2_v2.contracts import (
    G2_V2_SNAPSHOT_CONTRACT_VERSION,
    G2V2EvidenceOrigin,
)
from app.g2_v2.fingerprints import g2_v2_manifest_fingerprint
from app.resolution.contracts import (
    IdentityConflictType,
    IdentityGroupHypothesisStatus,
)
from app.shadow_comparison.contracts import (
    SHADOW_COMPARISON_ALGORITHM_VERSION,
    AdjudicationPriority,
    ComparisonIdentitySet,
    ComparisonSourceVersion,
    GroupOverlapMetrics,
    ShadowComparisonCase,
    ShadowComparisonCaseType,
    ShadowComparisonInput,
    ShadowComparisonResult,
    ShadowComparisonSummary,
    ShadowSafetyDelta,
    ShadowSafetyDeltaType,
    StatusTransition,
)
from app.shadow_comparison.fingerprints import shadow_fingerprint


class ShadowComparisonValidationError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ShadowComparisonValidationError(message)


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def _identity_pairs(groups):
    pairs = set()
    for group in groups:
        pairs.update(combinations(group.stable_member_references, 2))
    return pairs


def _normalize_group(group, source_version):
    paired = tuple(sorted(zip(
        group.stable_member_references, group.member_record_ids
    )))
    return ComparisonIdentitySet(
        source_version=source_version,
        group_reference=group.group_reference,
        status=IdentityGroupHypothesisStatus(group.status),
        member_record_ids=tuple(item[1] for item in paired),
        stable_member_references=tuple(item[0] for item in paired),
        member_count=len(paired),
        source_fingerprint=group.source_fingerprint,
    )


def _normalize_v2_group(group):
    paired = tuple(sorted(
        (item.stable_record_reference, item.record_id) for item in group.members
    ))
    return ComparisonIdentitySet(
        source_version=ComparisonSourceVersion.V2,
        group_reference=group.group_reference,
        status=group.status,
        member_record_ids=tuple(item[1] for item in paired),
        stable_member_references=tuple(item[0] for item in paired),
        member_count=len(paired),
        source_fingerprint=group.group_fingerprint,
    )


def _validate_and_normalize(value: ShadowComparisonInput):
    _require(value.scan_id > 0, "comparison scan ID must be positive")
    _require(
        value.comparison_algorithm_version == SHADOW_COMPARISON_ALGORITHM_VERSION,
        "unsupported shadow-comparison algorithm version",
    )
    _require(value.v1_projection_run_id > 0 and value.v2_projection_run_id > 0,
             "comparison projection run IDs must be positive")
    _require(value.v2_source_resolution_run_id > 0,
             "comparison source resolution run ID must be positive")
    _require(value.v1_snapshot.status == "COMPLETED", "v1 snapshot is not completed")
    _require(value.v2_projection_status == "COMPLETED", "v2 snapshot is not completed")
    _require(
        value.v1_snapshot.scan_id == value.v2_snapshot.scan_id == value.scan_id,
        "comparison snapshots cross scans",
    )
    _require(value.v1_snapshot.snapshot_contract_version == 1,
             "v1 comparison snapshot must declare contract version 1")
    _require(len(value.v1_snapshot.source_fingerprint) == 64,
             "v1 comparison snapshot lacks a source fingerprint")
    _require(
        value.v2_snapshot.snapshot_contract_version == G2_V2_SNAPSHOT_CONTRACT_VERSION,
        "v2 comparison snapshot must declare contract version 2",
    )
    _require(
        value.v2_snapshot.source_resolution_run_id == value.v2_source_resolution_run_id,
        "v2 resolution provenance mismatch",
    )
    _require(
        value.v2_snapshot.manifest_fingerprint
        == g2_v2_manifest_fingerprint(value.v2_snapshot),
        "v2 manifest fingerprint mismatch",
    )
    _require(
        value.v2_snapshot.accepted_group_count == len(value.v2_snapshot.groups)
        and value.v2_snapshot.conflict_count == len(value.v2_snapshot.conflicts)
        and value.v2_snapshot.deferred_count == len(value.v2_snapshot.deferred_work_units)
        and value.v2_snapshot.unassigned_record_count
        == len(value.v2_snapshot.unassigned_record_references),
        "v2 manifest outcome counts do not reconcile",
    )
    records_by_id, records_by_ref = {}, {}
    for record in value.canonical_records:
        _require(record.scan_id == value.scan_id, "canonical record crosses scans")
        _require(record.record_id not in records_by_id, "duplicate canonical record ID")
        _require(record.record_ref_key not in records_by_ref,
                 "duplicate canonical record reference")
        records_by_id[record.record_id] = record
        records_by_ref[record.record_ref_key] = record
    _require(
        len(records_by_id) == value.v1_snapshot.canonical_record_count
        == value.v2_snapshot.canonical_record_count,
        "comparison lacks complete canonical-record coverage",
    )

    for group in value.v1_snapshot.groups:
        _require(group.source_version == ComparisonSourceVersion.V1,
                 "v1 snapshot contains a non-v1 group")
        _require(
            group.member_count == len(group.member_record_ids)
            == len(group.stable_member_references),
            "v1 comparison group member counts do not reconcile",
        )
        _require(group.status in {
            IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP,
            IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        }, "v1 comparison group status is not accepted")
    v1_groups = tuple(_normalize_group(group, ComparisonSourceVersion.V1)
                      for group in value.v1_snapshot.groups)
    v2_groups = tuple(_normalize_v2_group(group) for group in value.v2_snapshot.groups)
    for expected_source, groups in (
        (ComparisonSourceVersion.V1, v1_groups),
        (ComparisonSourceVersion.V2, v2_groups),
    ):
        seen = set()
        for group in groups:
            _require(group.source_version == expected_source,
                     "comparison group has the wrong source version")
            _require(group.member_count == len(group.stable_member_references) >= 2,
                     "comparison accepted group has invalid membership")
            _require(len(set(group.stable_member_references)) == group.member_count,
                     "comparison group repeats a member")
            _require(len(group.source_fingerprint) == 64,
                     "comparison group lacks a stable fingerprint")
            for record_id, record_ref in zip(
                group.member_record_ids, group.stable_member_references
            ):
                _require(
                    record_id in records_by_id
                    and records_by_id[record_id].record_ref_key == record_ref,
                    "comparison group member differs from GF-1",
                )
            current = set(group.stable_member_references)
            _require(not seen.intersection(current),
                     "comparison source contains overlapping accepted groups")
            seen.update(current)
    for record_id, record_ref in zip(
        value.v2_snapshot.unassigned_record_ids,
        value.v2_snapshot.unassigned_record_references,
    ):
        _require(
            record_id in records_by_id
            and records_by_id[record_id].record_ref_key == record_ref,
            "v2 unassigned identity differs from GF-1",
        )
    _require(
        set(value.v1_snapshot.unassigned_record_references) <= set(records_by_ref),
        "v1 unassigned identity is outside GF-1",
    )
    _require(
        not (set(value.v1_snapshot.unassigned_record_references)
             & {member for group in v1_groups for member in group.stable_member_references}),
        "v1 record is both accepted and unassigned",
    )
    return (
        tuple(sorted(v1_groups, key=lambda item: (
            item.stable_member_references, item.status.value, item.source_fingerprint
        ))),
        tuple(sorted(v2_groups, key=lambda item: (
            item.stable_member_references, item.status.value, item.source_fingerprint
        ))),
        frozenset(records_by_ref),
    )


def _overlap(v1, v2):
    left, right = set(v1.stable_member_references), set(v2.stable_member_references)
    intersection, union = left & right, left | right
    return GroupOverlapMetrics(
        v1_group_reference=v1.group_reference,
        v2_group_reference=v2.group_reference,
        intersection_count=len(intersection), union_count=len(union),
        member_jaccard=len(intersection) / len(union),
        v1_containment_ratio=len(intersection) / len(left),
        v2_containment_ratio=len(intersection) / len(right),
    )


def _graph(v1_groups, v2_groups):
    v1_by_member, v2_by_member = defaultdict(list), defaultdict(list)
    for index, group in enumerate(v1_groups):
        for member in group.stable_member_references: v1_by_member[member].append(index)
    for index, group in enumerate(v2_groups):
        for member in group.stable_member_references: v2_by_member[member].append(index)
    edges = set()
    for member in set(v1_by_member) & set(v2_by_member):
        edges.update((left, right) for left in v1_by_member[member] for right in v2_by_member[member])
    left_adj, right_adj = defaultdict(set), defaultdict(set)
    for left, right in edges:
        left_adj[left].add(right); right_adj[right].add(left)
    components, visited_left, visited_right = [], set(), set()
    for start in range(len(v1_groups)):
        if start in visited_left: continue
        if not left_adj[start]:
            visited_left.add(start); components.append(((start,), ())); continue
        queue, lefts, rights = deque((("v1", start),)), set(), set()
        while queue:
            side, index = queue.popleft()
            if side == "v1":
                if index in lefts: continue
                lefts.add(index); visited_left.add(index)
                queue.extend(("v2", item) for item in left_adj[index])
            else:
                if index in rights: continue
                rights.add(index); visited_right.add(index)
                queue.extend(("v1", item) for item in right_adj[index])
        components.append((tuple(sorted(lefts)), tuple(sorted(rights))))
    for start in range(len(v2_groups)):
        if start not in visited_right:
            components.append(((), (start,)))
    return tuple(components), frozenset(edges), left_adj, right_adj


def _case_type(lefts, rights, v1_groups, v2_groups, left_adj, right_adj):
    if not rights: return ShadowComparisonCaseType.V1_ONLY_GROUP
    if not lefts: return ShadowComparisonCaseType.V2_ONLY_GROUP
    if len(lefts) == len(rights) == 1:
        left, right = v1_groups[lefts[0]], v2_groups[rights[0]]
        if set(left.stable_member_references) == set(right.stable_member_references):
            return (ShadowComparisonCaseType.EXACT_MATCH if left.status == right.status
                    else ShadowComparisonCaseType.STATUS_CHANGE)
        return ShadowComparisonCaseType.PARTIAL_REASSIGNMENT
    if len(lefts) == 1: return ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2
    if len(rights) == 1: return ShadowComparisonCaseType.V2_GROUP_MERGE_OF_V1
    left_union = set().union(*(set(v1_groups[item].stable_member_references) for item in lefts))
    right_union = set().union(*(set(v2_groups[item].stable_member_references) for item in rights))
    precise_reassignment = (
        len(lefts) == len(rights)
        and left_union == right_union
        and all(len(left_adj[item]) >= 2 for item in lefts)
        and all(len(right_adj[item]) >= 2 for item in rights)
    )
    return (ShadowComparisonCaseType.PARTIAL_REASSIGNMENT
            if precise_reassignment else ShadowComparisonCaseType.COMPLEX_OVERLAP)


def _delta(delta_type, records, evidence=()):
    records, evidence = tuple(sorted(set(records))), tuple(sorted(set(evidence)))
    explanations = {
        ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT:
            "V1 accepted co-membership intersects a directly referenced protected v2 conflict.",
        ShadowSafetyDeltaType.V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK:
            "A v1 group is split in v2 with directly referenced protected cannot-link evidence.",
        ShadowSafetyDeltaType.V2_ACCEPTED_PAIR_ABSENT_FROM_V1:
            "V2 contains accepted co-membership that is absent from the v1 positive-pair set.",
        ShadowSafetyDeltaType.V2_GROUP_USES_TARGETED_EVIDENCE_NOT_AVAILABLE_TO_V1:
            "V2 uses targeted resolution evidence that was not part of v1 evidence.",
        ShadowSafetyDeltaType.V2_DEFERRED_WHERE_V1_ACCEPTED:
            "V2 defers records that participate in a v1 accepted hypothesis.",
        ShadowSafetyDeltaType.V2_CONFLICT_WHERE_V1_ACCEPTED:
            "V2 records a conflict involving records from a v1 accepted hypothesis.",
        ShadowSafetyDeltaType.V1_ACCEPTED_WHERE_V2_UNASSIGNED:
            "V2 leaves unassigned records that participate in a v1 accepted hypothesis.",
    }
    payload = {"type": delta_type, "records": records, "evidence": evidence}
    return ShadowSafetyDelta(
        delta_type, records, evidence, explanations[delta_type],
        shadow_fingerprint("shadow-safety-delta", payload),
    )


def _priority(case_type, left_groups, right_groups, related_conflicts, deltas):
    delta_types = {item.delta_type for item in deltas}
    reasons = []
    protected = {
        ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT,
        ShadowSafetyDeltaType.V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK,
    }
    if delta_types & protected:
        return AdjudicationPriority.CRITICAL, ("PROTECTED_ACCEPTED_MEMBERSHIP_CONFLICT",)
    if any(item.conflict_type in {
        IdentityConflictType.HUMAN_MACHINE_AUTHORITY_CONFLICT,
        IdentityConflictType.INCOMPATIBLE_MUST_LINK_CONSTRAINTS,
    } for item in related_conflicts):
        return AdjudicationPriority.CRITICAL, ("AUTHORITY_CONFLICT_AFFECTS_ACCEPTED_MEMBERSHIP",)
    has_likely = any(item.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
                     for item in (*left_groups, *right_groups))
    structural = case_type in {
        ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2,
        ShadowComparisonCaseType.V2_GROUP_MERGE_OF_V1,
        ShadowComparisonCaseType.PARTIAL_REASSIGNMENT,
        ShadowComparisonCaseType.COMPLEX_OVERLAP,
    }
    if (structural and has_likely) or (has_likely and related_conflicts) or (
        has_likely and ShadowSafetyDeltaType.V2_DEFERRED_WHERE_V1_ACCEPTED in delta_types
    ):
        reasons.append("LIKELY_MEMBERSHIP_REQUIRES_ADJUDICATION")
        return AdjudicationPriority.HIGH, tuple(reasons)
    if structural or case_type == ShadowComparisonCaseType.STATUS_CHANGE:
        return AdjudicationPriority.MEDIUM, ("REVIEW_LEVEL_STRUCTURE_OR_STATUS_DIFFERS",)
    if case_type in {ShadowComparisonCaseType.V1_ONLY_GROUP, ShadowComparisonCaseType.V2_ONLY_GROUP}:
        return (AdjudicationPriority.HIGH if has_likely else AdjudicationPriority.MEDIUM,
                ("ONE_VERSION_ONLY_ACCEPTED_HYPOTHESIS",))
    if deltas:
        return AdjudicationPriority.LOW, ("EXPLANATORY_EVIDENCE_OR_MEMBERSHIP_DELTA",)
    return AdjudicationPriority.NONE, ()


def _build_case(component, value, v1_groups, v2_groups, v1_pairs, left_adj, right_adj):
    lefts, rights = component
    left_groups = tuple(v1_groups[item] for item in lefts)
    right_groups = tuple(v2_groups[item] for item in rights)
    case_type = _case_type(lefts, rights, v1_groups, v2_groups, left_adj, right_adj)
    v1_members = set().union(*(set(item.stable_member_references) for item in left_groups)) if left_groups else set()
    v2_members = set().union(*(set(item.stable_member_references) for item in right_groups)) if right_groups else set()
    scope = v1_members | v2_members
    overlaps = tuple(sorted((
        _overlap(left, right) for left in left_groups for right in right_groups
        if set(left.stable_member_references) & set(right.stable_member_references)
    ), key=lambda item: (item.v1_group_reference, item.v2_group_reference)))
    transitions = tuple(StatusTransition(
        item.v1_group_reference, item.v2_group_reference,
        next(group.status for group in left_groups if group.group_reference == item.v1_group_reference),
        next(group.status for group in right_groups if group.group_reference == item.v2_group_reference),
    ) for item in overlaps if next(
        group.status for group in left_groups if group.group_reference == item.v1_group_reference
    ) != next(
        group.status for group in right_groups if group.group_reference == item.v2_group_reference
    ))
    related_conflicts = tuple(item for item in value.v2_snapshot.conflicts
                              if set(item.involved_record_references) & v1_members)
    related_deferred = tuple(item for item in value.v2_snapshot.deferred_work_units
                             if set(item.record_references) & v1_members)
    related_unassigned = tuple(sorted(set(value.v2_snapshot.unassigned_record_references) & v1_members))
    residual_context = set(related_unassigned)
    residual_context.update(record for item in related_conflicts
                            for record in item.involved_record_references)
    residual_context.update(record for item in related_deferred
                            for record in item.record_references)
    if (
        case_type == ShadowComparisonCaseType.PARTIAL_REASSIGNMENT
        and len(left_groups) == len(right_groups) == 1
        and v2_members < v1_members
        and (v1_members - v2_members) <= residual_context
    ):
        case_type = ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2
    deltas = []
    for conflict in related_conflicts:
        conflict_members = set(conflict.involved_record_references)
        accepted_conflict_pairs = v1_pairs & set(combinations(sorted(conflict_members), 2))
        protected = (
            conflict.conflict_type in {
                IdentityConflictType.PROTECTED_CANNOT_LINK,
                IdentityConflictType.HUMAN_MACHINE_AUTHORITY_CONFLICT,
            }
            and bool(conflict.protected_evidence_references)
            and bool(accepted_conflict_pairs)
        )
        if protected:
            records = set().union(*(set(item) for item in accepted_conflict_pairs))
            deltas.append(_delta(
                ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT,
                records, conflict.protected_evidence_references,
            ))
            if case_type == ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2:
                deltas.append(_delta(
                    ShadowSafetyDeltaType.V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK,
                    records, conflict.protected_evidence_references,
                ))
        deltas.append(_delta(
            ShadowSafetyDeltaType.V2_CONFLICT_WHERE_V1_ACCEPTED,
            conflict_members & v1_members, conflict.protected_evidence_references,
        ))
    for item in related_deferred:
        deltas.append(_delta(
            ShadowSafetyDeltaType.V2_DEFERRED_WHERE_V1_ACCEPTED,
            set(item.record_references) & v1_members,
        ))
    if related_unassigned:
        deltas.append(_delta(
            ShadowSafetyDeltaType.V1_ACCEPTED_WHERE_V2_UNASSIGNED,
            related_unassigned,
        ))
    v2_case_pairs = _identity_pairs(right_groups)
    absent_pairs = v2_case_pairs - v1_pairs
    if absent_pairs:
        deltas.append(_delta(
            ShadowSafetyDeltaType.V2_ACCEPTED_PAIR_ABSENT_FROM_V1,
            set().union(*(set(item) for item in absent_pairs)),
        ))
    targeted_groups = [
        source for source in value.v2_snapshot.groups
        if source.group_reference in {item.group_reference for item in right_groups}
        and any(edge.evidence_origin == G2V2EvidenceOrigin.TARGETED_RESOLUTION_EVIDENCE
                for edge in source.internal_evidence)
    ]
    if targeted_groups:
        deltas.append(_delta(
            ShadowSafetyDeltaType.V2_GROUP_USES_TARGETED_EVIDENCE_NOT_AVAILABLE_TO_V1,
            set().union(*(set(item.stable_record_reference for item in group.members)
                          for group in targeted_groups)),
        ))
    deltas = tuple(sorted({item.delta_fingerprint: item for item in deltas}.values(),
                          key=lambda item: (item.delta_type.value, item.delta_fingerprint)))
    priority, reasons = _priority(case_type, left_groups, right_groups, related_conflicts, deltas)
    semantic = {
        "case_type": case_type,
        "v1": tuple(sorted((item.source_fingerprint, item.status, item.stable_member_references)
                           for item in left_groups)),
        "v2": tuple(sorted((item.source_fingerprint, item.status, item.stable_member_references)
                           for item in right_groups)),
        "conflicts": tuple(sorted(item.conflict_fingerprint for item in related_conflicts)),
        "deferred": tuple(sorted(item.deferred_fingerprint for item in related_deferred)),
        "unassigned": related_unassigned,
        "deltas": tuple(item.delta_fingerprint for item in deltas),
        "priority": priority,
    }
    fingerprint = shadow_fingerprint("shadow-comparison-case", semantic)
    return ShadowComparisonCase(
        case_reference="shadow-case-" + fingerprint,
        case_type=case_type,
        v1_group_references=tuple(sorted(item.group_reference for item in left_groups)),
        v2_group_references=tuple(sorted(item.group_reference for item in right_groups)),
        involved_record_references=tuple(sorted(scope | set(related_unassigned))),
        v1_member_references=tuple(sorted(v1_members)),
        v2_member_references=tuple(sorted(v2_members)),
        overlap_metrics=overlaps, status_transitions=transitions,
        related_v2_conflict_references=tuple(sorted(item.conflict_reference for item in related_conflicts)),
        related_v2_deferred_references=tuple(sorted(item.deferred_reference for item in related_deferred)),
        related_v2_unassigned_record_references=related_unassigned,
        safety_deltas=deltas, adjudication_priority=priority,
        adjudication_reasons=reasons, case_fingerprint=fingerprint,
    )


def compare_g2_v1_v2(comparison_input: ShadowComparisonInput) -> ShadowComparisonResult:
    """Compare accepted positive hypotheses without treating either as truth."""
    value = comparison_input
    v1_groups, v2_groups, all_records = _validate_and_normalize(value)
    v1_pairs, v2_pairs = _identity_pairs(v1_groups), _identity_pairs(v2_groups)
    pair_intersection = v1_pairs & v2_pairs
    components, graph_edges, left_adj, right_adj = _graph(v1_groups, v2_groups)
    cases = tuple(sorted((
        _build_case(component, value, v1_groups, v2_groups, v1_pairs, left_adj, right_adj)
        for component in components
    ), key=lambda item: (item.case_type.value, item.case_fingerprint)))
    deltas = tuple(sorted({item.delta_fingerprint: item
                           for case in cases for item in case.safety_deltas}.values(),
                          key=lambda item: (item.delta_type.value, item.delta_fingerprint)))
    grouped_v1 = set().union(*(set(item.stable_member_references) for item in v1_groups)) if v1_groups else set()
    grouped_v2 = set().union(*(set(item.stable_member_references) for item in v2_groups)) if v2_groups else set()
    case_counts = {kind: sum(item.case_type == kind for item in cases)
                   for kind in ShadowComparisonCaseType}
    priority_counts = {kind: sum(item.adjudication_priority == kind for item in cases)
                       for kind in AdjudicationPriority}
    union_pairs = v1_pairs | v2_pairs
    jaccard = (value.comparison_configuration.empty_positive_pair_jaccard
               if not union_pairs else len(pair_intersection) / len(union_pairs))
    summary = ShadowComparisonSummary(
        scan_id=value.scan_id,
        v1_projection_run_id=value.v1_projection_run_id,
        v2_projection_run_id=value.v2_projection_run_id,
        v2_source_resolution_run_id=value.v2_source_resolution_run_id,
        v1_group_count=len(v1_groups), v2_group_count=len(v2_groups),
        v1_likely_group_count=sum(item.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP for item in v1_groups),
        v2_likely_group_count=sum(item.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP for item in v2_groups),
        v1_review_group_count=sum(item.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW for item in v1_groups),
        v2_review_group_count=sum(item.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW for item in v2_groups),
        exact_match_count=case_counts[ShadowComparisonCaseType.EXACT_MATCH],
        exact_member_status_change_count=case_counts[ShadowComparisonCaseType.STATUS_CHANGE],
        split_count=case_counts[ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2],
        merge_count=case_counts[ShadowComparisonCaseType.V2_GROUP_MERGE_OF_V1],
        reassignment_count=case_counts[ShadowComparisonCaseType.PARTIAL_REASSIGNMENT],
        v1_only_count=case_counts[ShadowComparisonCaseType.V1_ONLY_GROUP],
        v2_only_count=case_counts[ShadowComparisonCaseType.V2_ONLY_GROUP],
        complex_overlap_count=case_counts[ShadowComparisonCaseType.COMPLEX_OVERLAP],
        v1_positive_pair_count=len(v1_pairs), v2_positive_pair_count=len(v2_pairs),
        positive_pair_intersection_count=len(pair_intersection),
        v1_only_positive_pair_count=len(v1_pairs - v2_pairs),
        v2_only_positive_pair_count=len(v2_pairs - v1_pairs),
        positive_pair_jaccard=jaccard,
        v1_membership_retained_in_v2_ratio=_ratio(len(pair_intersection), len(v1_pairs)),
        v2_membership_also_present_in_v1_ratio=_ratio(len(pair_intersection), len(v2_pairs)),
        records_total=len(all_records), records_grouped_v1=len(grouped_v1),
        records_grouped_v2=len(grouped_v2), records_grouped_both=len(grouped_v1 & grouped_v2),
        records_grouped_v1_only=len(grouped_v1 - grouped_v2),
        records_grouped_v2_only=len(grouped_v2 - grouped_v1),
        records_unassigned_both=len(all_records - grouped_v1 - grouped_v2),
        v2_conflict_count=len(value.v2_snapshot.conflicts),
        v2_deferred_count=len(value.v2_snapshot.deferred_work_units),
        critical_case_count=priority_counts[AdjudicationPriority.CRITICAL],
        high_case_count=priority_counts[AdjudicationPriority.HIGH],
        medium_case_count=priority_counts[AdjudicationPriority.MEDIUM],
        low_case_count=priority_counts[AdjudicationPriority.LOW],
        none_case_count=priority_counts[AdjudicationPriority.NONE],
        targeted_evidence_case_count=sum(
            any(delta.delta_type == ShadowSafetyDeltaType.V2_GROUP_USES_TARGETED_EVIDENCE_NOT_AVAILABLE_TO_V1
                for delta in case.safety_deltas) for case in cases
        ),
        overlap_graph_edge_count=len(graph_edges), comparison_fingerprint="",
    )
    configuration_fingerprint = shadow_fingerprint(
        "shadow-comparison-configuration", value.comparison_configuration
    )
    semantic_summary = {
        field: getattr(summary, field)
        for field in summary.__dataclass_fields__
        if field not in {
            "scan_id", "v1_projection_run_id", "v2_projection_run_id",
            "v2_source_resolution_run_id", "comparison_fingerprint",
        }
    }
    fingerprint = shadow_fingerprint("shadow-comparison-result", {
        "algorithm": value.comparison_algorithm_version,
        "configuration": configuration_fingerprint,
        "canonical_records": tuple(sorted(
            (record.record_ref_key, record.source_record_fingerprint)
            for record in value.canonical_records
        )),
        "v1_source": value.v1_snapshot.source_fingerprint,
        "v2_source": value.v2_snapshot.manifest_fingerprint,
        "summary": semantic_summary,
        "cases": tuple(item.case_fingerprint for item in cases),
        "deltas": tuple(item.delta_fingerprint for item in deltas),
    })
    summary = replace(summary, comparison_fingerprint=fingerprint)
    return ShadowComparisonResult(
        summary=summary, cases=cases, safety_deltas=deltas,
        comparison_algorithm_version=value.comparison_algorithm_version,
        configuration_fingerprint=configuration_fingerprint,
        comparison_fingerprint=fingerprint,
    )
