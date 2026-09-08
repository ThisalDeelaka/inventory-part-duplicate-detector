import dataclasses
import inspect
from dataclasses import replace
from itertools import combinations

import pytest

from app.engine.identity_edge import IdentityEdgeClass
from app.g2_v2.contracts import G2V2EvidenceOrigin
from app.resolution.contracts import (
    DeferredIdentityReason,
    DeferredIdentityWorkUnit,
    IdentityConflict,
    IdentityConflictType,
    IdentityGroupHypothesisStatus,
)
from app.resolution.validation import (
    with_deferred_work_unit_fingerprint,
    with_identity_conflict_fingerprint,
)
from app.shadow_comparison.comparison import (
    ShadowComparisonValidationError,
    compare_g2_v1_v2,
)
from app.shadow_comparison.contracts import (
    AdjudicationPriority,
    ComparisonIdentitySet,
    ComparisonSourceVersion,
    ShadowComparisonCaseType,
    ShadowComparisonInput,
    ShadowComparisonSummary,
    ShadowSafetyDeltaType,
    V1ComparisonSnapshot,
)
from app.shadow_comparison.fingerprints import shadow_fingerprint
from test_g2_v2_adapter import (
    RESOLUTION_RUN_ID,
    SCAN_ID,
    build,
    hypothesis,
    proposal,
    record,
    resolution,
    targeted,
)


LIKELY = IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
REVIEW = IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW


def records_for(refs, *, duplicate_values=False):
    return tuple(record(
        index + 1, reference,
        part_no="SAME" if duplicate_values else reference,
        description="SAME BEARING 6205" if duplicate_values else f"BEARING {reference} 6205",
    ) for index, reference in enumerate(refs))


def v1_group(records, refs, status=LIKELY, group_reference=None, reverse=False):
    selected = [item for item in records if item.record_ref_key in set(refs)]
    if reverse: selected.reverse()
    semantic = {
        "members": tuple(sorted(refs)), "status": status.value,
        "contract": "neutral-v1-comparison-fixture",
    }
    return ComparisonIdentitySet(
        source_version=ComparisonSourceVersion.V1,
        group_reference=group_reference or "v1-" + "-".join(refs),
        status=status,
        member_record_ids=tuple(item.record_id for item in selected),
        stable_member_references=tuple(item.record_ref_key for item in selected),
        member_count=len(selected),
        source_fingerprint=shadow_fingerprint("test-v1-group", semantic),
    )


def v1_snapshot(records, specs, *, group_ids=None, reverse_members=False):
    groups = tuple(v1_group(
        records, refs, status,
        group_reference=(group_ids[index] if group_ids else None),
        reverse=reverse_members,
    ) for index, (refs, status) in enumerate(specs))
    grouped = {ref for refs, _status in specs for ref in refs}
    semantic = tuple(sorted(
        (group.source_fingerprint, group.status.value,
         tuple(sorted(group.stable_member_references))) for group in groups
    ))
    return V1ComparisonSnapshot(
        scan_id=SCAN_ID, status="COMPLETED", snapshot_contract_version=1,
        canonical_record_count=len(records), groups=groups,
        source_fingerprint=shadow_fingerprint("test-v1-snapshot", semantic),
        unassigned_record_references=tuple(sorted(
            item.record_ref_key for item in records
            if item.record_ref_key not in grouped
        )),
    )


def v2_manifest(records, specs=(), *, conflicts=(), deferred=(), unassigned=None):
    by_ref = {item.record_ref_key: item for item in records}
    edges, groups = [], []
    for group_index, (refs, status) in enumerate(specs):
        group_records = tuple(sorted(
            (by_ref[item] for item in refs), key=lambda item: item.record_id
        ))
        group_edges = tuple(proposal(
            left.record_id, right.record_id,
            (IdentityEdgeClass.STRONG_SUPPORT if status == LIKELY
             else IdentityEdgeClass.REVIEW_SUPPORT),
            suffix=f"g{group_index}-{left.record_ref_key}-{right.record_ref_key}",
        ) for left, right in combinations(group_records, 2))
        edges.extend(group_edges)
        groups.append(hypothesis(group_records, group_edges, status=status))
    result = resolution(
        records, groups, conflicts=conflicts, deferred=deferred,
        unassigned=(tuple(by_ref[item].record_id for item in unassigned)
                    if unassigned is not None else None),
    )
    return build(records, result, tuple(edges))


def comparison(records, v1_specs, v2_specs=(), **v2_kwargs):
    v2 = v2_manifest(records, v2_specs, **v2_kwargs)
    return compare_g2_v1_v2(ShadowComparisonInput(
        scan_id=SCAN_ID, canonical_records=tuple(records),
        v1_snapshot=v1_snapshot(records, v1_specs), v2_snapshot=v2,
        v1_projection_run_id=101, v2_projection_run_id=202,
        v2_source_resolution_run_id=RESOLUTION_RUN_ID,
        v2_projection_status="COMPLETED",
    ))


@pytest.mark.parametrize(("case_id", "v1_specs", "v2_specs", "expected"), [
    ("C1", [(('A', 'B', 'C'), LIKELY)], [(('A', 'B', 'C'), LIKELY)], ShadowComparisonCaseType.EXACT_MATCH),
    ("C2", [(('A', 'B'), LIKELY)], [(('A', 'B'), REVIEW)], ShadowComparisonCaseType.STATUS_CHANGE),
    ("C3", [(('A', 'B', 'C', 'D'), LIKELY)], [(('A', 'B'), LIKELY), (('C', 'D'), LIKELY)], ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2),
    ("C4", [(('A', 'B'), LIKELY), (('C', 'D'), LIKELY)], [(('A', 'B', 'C', 'D'), LIKELY)], ShadowComparisonCaseType.V2_GROUP_MERGE_OF_V1),
    ("C5", [(('A', 'B'), REVIEW)], [], ShadowComparisonCaseType.V1_ONLY_GROUP),
    ("C6", [], [(('A', 'B'), REVIEW)], ShadowComparisonCaseType.V2_ONLY_GROUP),
    ("C7", [(('A', 'B'), LIKELY), (('C', 'D'), LIKELY)], [(('A', 'C'), LIKELY), (('B', 'D'), LIKELY)], ShadowComparisonCaseType.PARTIAL_REASSIGNMENT),
], ids=lambda value: value if isinstance(value, str) else None)
def test_c1_through_c7_structural_golden_cases(case_id, v1_specs, v2_specs, expected):
    del case_id
    result = comparison(records_for(('A', 'B', 'C', 'D')), v1_specs, v2_specs)
    assert len(result.cases) == 1
    assert result.cases[0].case_type == expected


def test_c1_exact_positive_pair_and_assignment_metrics_are_agreement_only():
    result = comparison(
        records_for(('A', 'B', 'C', 'D')),
        [(('A', 'B', 'C'), LIKELY)], [(('C', 'B', 'A'), LIKELY)],
    )
    summary = result.summary
    assert (summary.v1_positive_pair_count, summary.v2_positive_pair_count) == (3, 3)
    assert summary.positive_pair_intersection_count == 3
    assert summary.positive_pair_jaccard == 1.0
    assert summary.v1_membership_retained_in_v2_ratio == 1.0
    assert summary.v2_membership_also_present_in_v1_ratio == 1.0
    assert (summary.records_grouped_both, summary.records_unassigned_both) == (3, 1)


def test_c8_protected_v2_cannot_link_is_critical_only_with_direct_provenance():
    records = records_for(('A', 'B'))
    conflict = with_identity_conflict_fingerprint(IdentityConflict(
        conflict_id="protected-A-B", scan_id=SCAN_ID,
        involved_record_ids=(1, 2), involved_record_references=('A', 'B'),
        conflict_type=IdentityConflictType.PROTECTED_CANNOT_LINK,
        protected_evidence_references=("gf4-cannot-link-A-B",),
        source_neighborhood_references=("n-A",), summary="protected", fingerprint="",
    ))
    result = comparison(records, [(('A', 'B'), LIKELY)], conflicts=(conflict,))
    case = result.cases[0]
    assert case.adjudication_priority == AdjudicationPriority.CRITICAL
    assert ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT in {
        item.delta_type for item in case.safety_deltas
    }
    protected = next(item for item in case.safety_deltas
                     if item.delta_type == ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT)
    assert protected.protected_evidence_references == ("gf4-cannot-link-A-B",)


def test_c9_v1_likely_v2_deferred_is_high_without_a_verdict():
    records = records_for(('A', 'B'))
    deferred = with_deferred_work_unit_fingerprint(DeferredIdentityWorkUnit(
        deferred_id="deferred-A-B", scan_id=SCAN_ID,
        record_ids=(1, 2), record_references=('A', 'B'),
        reason=DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY,
        unfinished_evidence_summary="more evidence required",
        source_neighborhood_references=("n-A",), fingerprint="",
    ))
    result = comparison(records, [(('A', 'B'), LIKELY)], deferred=(deferred,))
    case = result.cases[0]
    assert case.adjudication_priority == AdjudicationPriority.HIGH
    assert ShadowSafetyDeltaType.V2_DEFERRED_WHERE_V1_ACCEPTED in {
        item.delta_type for item in case.safety_deltas
    }


def test_c10_targeted_bridge_evidence_is_explanatory_not_superior():
    records = records_for(('A', 'B', 'C'))
    refs = {item.record_id: item.record_ref_key for item in records}
    proposals = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    target = targeted(1, 3, refs, IdentityEdgeClass.STRONG_SUPPORT)
    source = hypothesis(records, proposals + (target,))
    source_result = resolution(records, (source,), targeted_results=(target,))
    v2 = build(records, source_result, proposals, (target,))
    result = compare_g2_v1_v2(ShadowComparisonInput(
        scan_id=SCAN_ID, canonical_records=records,
        v1_snapshot=v1_snapshot(records, [(('A', 'B', 'C'), LIKELY)]),
        v2_snapshot=v2, v1_projection_run_id=1, v2_projection_run_id=2,
        v2_source_resolution_run_id=RESOLUTION_RUN_ID,
        v2_projection_status="COMPLETED",
    ))
    assert result.summary.targeted_evidence_case_count == 1
    delta = next(item for item in result.safety_deltas
                 if item.delta_type == ShadowSafetyDeltaType.V2_GROUP_USES_TARGETED_EVIDENCE_NOT_AVAILABLE_TO_V1)
    assert "superior" not in delta.explanation.lower()


def test_c11_duplicate_valued_rows_remain_distinct_gf1_identities():
    records = records_for(('row-1', 'row-2'), duplicate_values=True)
    result = comparison(
        records, [(('row-1', 'row-2'), LIKELY)],
        [(('row-1', 'row-2'), LIKELY)],
    )
    assert result.summary.records_grouped_both == 2
    assert result.summary.v1_positive_pair_count == 1
    assert result.cases[0].involved_record_references == ('row-1', 'row-2')


def test_c12_shuffled_input_and_member_order_are_identical():
    records = records_for(('A', 'B', 'C', 'D'))
    v2 = v2_manifest(records, [(('A', 'B'), LIKELY), (('C', 'D'), REVIEW)])
    first_input = ShadowComparisonInput(
        scan_id=SCAN_ID, canonical_records=records,
        v1_snapshot=v1_snapshot(records, [(('A', 'B'), LIKELY), (('C', 'D'), REVIEW)]),
        v2_snapshot=v2, v1_projection_run_id=1, v2_projection_run_id=2,
        v2_source_resolution_run_id=RESOLUTION_RUN_ID, v2_projection_status="COMPLETED",
    )
    second_input = replace(
        first_input, canonical_records=tuple(reversed(records)),
        v1_snapshot=replace(
            v1_snapshot(records, [(('A', 'B'), LIKELY), (('C', 'D'), REVIEW)], reverse_members=True),
            groups=tuple(reversed(v1_snapshot(
                records, [(('A', 'B'), LIKELY), (('C', 'D'), REVIEW)], reverse_members=True
            ).groups)),
        ),
        v2_snapshot=v2,
    )
    assert compare_g2_v1_v2(first_input) == compare_g2_v1_v2(second_input)


def test_e1_split_with_residual_unassigned_is_one_split_case():
    records = records_for(('A', 'B', 'C'))
    result = comparison(
        records, [(('A', 'B', 'C'), REVIEW)], [(('A', 'B'), REVIEW)],
        unassigned=('C',),
    )
    assert len(result.cases) == 1
    assert result.cases[0].case_type == ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2
    assert result.cases[0].related_v2_unassigned_record_references == ('C',)


def test_e2_many_to_many_outside_precise_rule_is_complex():
    records = records_for(('A', 'B', 'C', 'D', 'E'))
    result = comparison(
        records,
        [(('A', 'B'), REVIEW), (('C', 'D'), REVIEW)],
        [(('A', 'C'), REVIEW), (('B', 'D', 'E'), REVIEW)],
    )
    assert result.cases[0].case_type == ShadowComparisonCaseType.COMPLEX_OVERLAP


def test_e3_same_part_values_with_different_record_membership_are_not_exact():
    records = records_for(('A', 'B', 'C'), duplicate_values=True)
    result = comparison(
        records, [(('A', 'B'), REVIEW)], [(('A', 'C'), REVIEW)]
    )
    assert result.cases[0].case_type == ShadowComparisonCaseType.PARTIAL_REASSIGNMENT
    assert result.summary.exact_match_count == 0


def test_e4_unprotected_conflict_is_never_called_protected_cannot_link():
    records = records_for(('A', 'B'))
    conflict = with_identity_conflict_fingerprint(IdentityConflict(
        conflict_id="ordinary-conflict", scan_id=SCAN_ID,
        involved_record_ids=(1, 2), involved_record_references=('A', 'B'),
        conflict_type=IdentityConflictType.OVERLAPPING_ACCEPTED_MEMBERSHIP_CONFLICT,
        protected_evidence_references=(), source_neighborhood_references=("n",),
        summary="ownership differs", fingerprint="",
    ))
    result = comparison(records, [(('A', 'B'), REVIEW)], conflicts=(conflict,))
    assert ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT not in {
        item.delta_type for item in result.safety_deltas
    }


def test_e5_generic_or_neutral_split_is_not_a_safety_correction():
    result = comparison(
        records_for(('A', 'B', 'C')),
        [(('A', 'B', 'C'), REVIEW)], [(('A', 'B'), REVIEW)], unassigned=('C',),
    )
    assert result.cases[0].case_type == ShadowComparisonCaseType.V1_GROUP_SPLIT_IN_V2
    assert not result.cases[0].related_v2_conflict_references
    assert not any(item.delta_type in {
        ShadowSafetyDeltaType.V1_ACCEPTED_PAIR_V2_PROTECTED_CONFLICT,
        ShadowSafetyDeltaType.V1_ACCEPTED_GROUP_SPLIT_BY_V2_CANNOT_LINK,
    } for item in result.safety_deltas)


def test_empty_positive_pair_jaccard_is_one_and_no_quality_fields_exist():
    result = comparison(records_for(('A', 'B')), [], [])
    assert result.summary.positive_pair_jaccard == 1.0
    fields = set(ShadowComparisonSummary.__dataclass_fields__)
    forbidden = {"accuracy", "precision", "recall", "winner", "promotion_score"}
    assert not fields & forbidden
    assert not any(term in inspect.getsource(compare_g2_v1_v2).lower()
                   for term in forbidden)


def test_group_ids_do_not_affect_matching_or_semantic_fingerprints():
    records = records_for(('A', 'B'))
    v2 = v2_manifest(records, [(('A', 'B'), LIKELY)])
    first = ShadowComparisonInput(
        scan_id=SCAN_ID, canonical_records=records,
        v1_snapshot=v1_snapshot(records, [(('A', 'B'), LIKELY)], group_ids=("db-group-1",)),
        v2_snapshot=v2, v1_projection_run_id=1, v2_projection_run_id=2,
        v2_source_resolution_run_id=RESOLUTION_RUN_ID, v2_projection_status="COMPLETED",
    )
    second = replace(
        first,
        v1_snapshot=v1_snapshot(records, [(('A', 'B'), LIKELY)], group_ids=("db-group-999",)),
        v1_projection_run_id=999, v2_projection_run_id=888,
    )
    left, right = compare_g2_v1_v2(first), compare_g2_v1_v2(second)
    assert left.summary.exact_match_count == right.summary.exact_match_count == 1
    assert left.comparison_fingerprint == right.comparison_fingerprint
    assert left.cases[0].case_fingerprint == right.cases[0].case_fingerprint


def test_no_global_negative_pair_enumeration_and_controlled_work_is_bounded():
    records = records_for(tuple(f"R{i:03d}" for i in range(100)))
    result = comparison(
        records,
        [(("R000", "R001", "R002"), LIKELY), (("R010", "R011"), REVIEW)],
        [(("R000", "R001", "R002"), LIKELY), (("R010", "R012"), REVIEW)],
    )
    assert result.summary.records_total == 100
    assert result.summary.v1_group_count == result.summary.v2_group_count == 2
    assert result.summary.v1_positive_pair_count == result.summary.v2_positive_pair_count == 4
    assert result.summary.overlap_graph_edge_count == 2
    assert len(result.cases) == 2
    assert result.summary.v1_positive_pair_count < 100 * 99 // 2


def test_contracts_are_frozen_and_package_has_no_forbidden_runtime_dependency():
    import app.shadow_comparison.comparison as comparison_module
    import app.shadow_comparison.contracts as contracts_module

    assert dataclasses.is_dataclass(ShadowComparisonInput)
    assert ShadowComparisonInput.__dataclass_params__.frozen is True
    source = inspect.getsource(comparison_module) + inspect.getsource(contracts_module)
    forbidden = (
        "sqlalchemy", "Session", "Repository", "scan_runner",
        "IdentityGroupQueryService", "create_llm_provider", "GroupAdvisory",
    )
    assert not any(name in source for name in forbidden)


def test_input_boundary_rejects_cross_scan_incomplete_runs_and_catalog_drift():
    records = records_for(('A', 'B'))
    base = ShadowComparisonInput(
        scan_id=SCAN_ID, canonical_records=records,
        v1_snapshot=v1_snapshot(records, [(('A', 'B'), LIKELY)]),
        v2_snapshot=v2_manifest(records, [(('A', 'B'), LIKELY)]),
        v1_projection_run_id=1, v2_projection_run_id=2,
        v2_source_resolution_run_id=RESOLUTION_RUN_ID,
        v2_projection_status="COMPLETED",
    )
    malformed = (
        replace(base, v2_projection_status="RUNNING"),
        replace(base, canonical_records=records[:1]),
        replace(base, v1_snapshot=replace(base.v1_snapshot, scan_id=SCAN_ID + 1)),
    )
    for value in malformed:
        with pytest.raises(ShadowComparisonValidationError):
            compare_g2_v1_v2(value)
