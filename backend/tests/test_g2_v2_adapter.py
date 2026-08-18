import dataclasses
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.engine.identity_edge import IdentityEdgeClass
from app.evidence.contracts import IdentityEvidenceEdge
from app.g2_v2.adapter import build_g2_v2_manifest
from app.g2_v2.contracts import (
    G2V2EvidenceOrigin,
    G2V2SourceProvenance,
)
from app.g2_v2.validation import (
    G2V2ManifestValidationError,
    validate_g2_v2_manifest,
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
    IdentityResolutionMetrics,
    IdentityResolutionResult,
    IdentityValidationMode,
    MissingEvidenceSummary,
    TargetedEvidenceReason,
    TargetedEvidenceRequest,
    TargetedEvidenceResult,
)
from app.resolution.fingerprints import (
    targeted_evidence_request_fingerprint,
)
from app.resolution.validation import (
    with_deferred_work_unit_fingerprint,
    with_group_hypothesis_fingerprint,
    with_identity_conflict_fingerprint,
    with_resolution_result_fingerprint,
)
from app.services.canonical_record_service import CanonicalScanRecord


SCAN_ID = 41
DISCOVERY_RUN_ID = 51
EVIDENCE_RUN_ID = 61
RESOLUTION_RUN_ID = 71


def record(record_id, reference, *, part_no=None, description="BEARING 6205"):
    return CanonicalScanRecord(
        record_id=record_id, scan_id=SCAN_ID, source_row_index=record_id - 1,
        record_ref_key=reference, source_record_fingerprint=f"source-{reference}",
        part_no=part_no or reference, description=description,
        contract="S1", uom="EA", type_code=None, prime_commodity=None,
        second_commodity=None, accounting_group=None, part_product_code=None,
        part_product_family=None, product_category_id=None, hsn_sac_code=None,
        hazard_code=None, normalized_part_no=(part_no or reference).lower(),
        normalized_description=description.lower(), normalization_version="test-v1",
    )


def proposal(left, right, edge_class, suffix=None):
    suffix = suffix or f"{left}-{right}-{edge_class.value}"
    return IdentityEvidenceEdge(
        edge_id=100 + left * 10 + right, evidence_run_id=EVIDENCE_RUN_ID,
        scan_id=SCAN_ID, discovery_run_id=DISCOVERY_RUN_ID,
        record_id_1=left, record_id_2=right,
        source_proposal_id=200 + left * 10 + right, edge_class=edge_class,
        classification_reason_codes=(f"REASON_{suffix}",),
        evaluation_algorithm_version="evaluator-v1",
        evidence_fingerprint=f"evidence-{suffix}", deterministic_score=90.0,
        component_scores_json="{}", rule_decision="ALLOW", rejection_reason="",
        protected_conflicts_json="[]", generic_evidence_json="{}",
        technical_evidence_json="{}", uom_context_json="{}",
        evaluation_context_json="{}", created_at=datetime.now(timezone.utc),
    )


def targeted(left, right, references, edge_class, suffix=None):
    suffix = suffix or f"{left}-{right}-{edge_class.value}"
    request = TargetedEvidenceRequest(
        scan_id=SCAN_ID, record_id_1=left, record_id_2=right,
        reason=TargetedEvidenceReason.BRIDGE_CROSS_CHECK,
        requesting_work_unit_reference="neighborhood-1", request_fingerprint="",
        record_reference_1=references[left], record_reference_2=references[right],
    )
    request = replace(
        request, request_fingerprint=targeted_evidence_request_fingerprint(request)
    )
    return TargetedEvidenceResult(
        request=request, edge_class=edge_class, reason_codes=(f"TARGET_{suffix}",),
        evidence_summary="ALLOW", evaluator_version="evaluator-v1",
        evidence_fingerprint=f"targeted-{suffix}", generic_only=False,
    )


def hypothesis(records, edges, *, status=None, mode=IdentityValidationMode.COMPLETE_PAIRWISE):
    records = tuple(records)
    edges = tuple(edges)
    possible = len(records) * (len(records) - 1) // 2
    counts = {kind: sum(item.edge_class == kind for item in edges) for kind in IdentityEdgeClass}
    status = status or (
        IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
        if counts[IdentityEdgeClass.STRONG_SUPPORT] == possible
        else IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
    )
    summary = GroupEvidenceSummary(
        member_count=len(records), validation_mode=mode,
        evaluated_pair_count=len(edges), possible_pair_count=possible,
        strong_support_count=counts[IdentityEdgeClass.STRONG_SUPPORT],
        review_support_count=counts[IdentityEdgeClass.REVIEW_SUPPORT],
        non_groupable_count=counts[IdentityEdgeClass.NON_GROUPABLE],
        cannot_link_count=counts[IdentityEdgeClass.CANNOT_LINK],
        support_density=(
            (counts[IdentityEdgeClass.STRONG_SUPPORT]
             + counts[IdentityEdgeClass.REVIEW_SUPPORT]) / possible
        ),
        strong_support_density=counts[IdentityEdgeClass.STRONG_SUPPORT] / possible,
        generic_evidence_edge_count=0, generic_member_count=0,
        protected_conflict_count=0, technical_consensus_summary=None,
        missing_evidence_count=possible - len(edges), bridge_risk_flag_count=0,
        required_conflict_checks_total=len(edges),
        required_conflict_checks_completed=len(edges),
        discovery_truncated=False, discovery_degraded=False,
        source_neighborhood_count=1,
    )
    group = IdentityGroupHypothesis(
        hypothesis_id="hyp-" + "-".join(item.record_ref_key for item in records),
        scan_id=SCAN_ID,
        member_record_ids=tuple(item.record_id for item in records),
        member_record_references=tuple(item.record_ref_key for item in records),
        status=status, validation_mode=mode, evidence_summary=summary,
        bridge_risk_summary=BridgeRiskSummary(),
        genericity_risk_summary=GenericityRiskSummary(),
        missing_evidence_summary=MissingEvidenceSummary(),
        source_neighborhood_references=("neighborhood-1",),
        hypothesis_fingerprint="",
    )
    return with_group_hypothesis_fingerprint(group)


def resolution(records, groups=(), *, conflicts=(), deferred=(), targeted_results=(),
               targeted_requests=None, unassigned=None):
    groups, conflicts, deferred = tuple(groups), tuple(conflicts), tuple(deferred)
    targeted_results = tuple(targeted_results)
    targeted_requests = tuple(targeted_requests) if targeted_requests is not None else tuple(
        item.request for item in targeted_results
    )
    assigned = {item for group in groups for item in group.member_record_ids}
    if unassigned is None:
        unassigned_records = tuple(item for item in records if item.record_id not in assigned)
    else:
        by_id = {item.record_id: item for item in records}
        unassigned_records = tuple(by_id[item] for item in unassigned)
    metrics = IdentityResolutionMetrics(
        source_record_count=len(records), accepted_group_count=len(groups),
        likely_group_count=sum(g.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP for g in groups),
        review_group_count=sum(g.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW for g in groups),
        conflict_count=len(conflicts), deferred_work_unit_count=len(deferred),
        unassigned_record_count=len(unassigned_records),
        targeted_evidence_request_count=len(targeted_requests),
        targeted_evidence_result_count=len(targeted_results), work_unit_count=1,
    )
    result = IdentityResolutionResult(
        scan_id=SCAN_ID, accepted_groups=groups, conflicts=conflicts,
        deferred_work_units=deferred,
        unassigned_record_ids=tuple(item.record_id for item in unassigned_records),
        unassigned_record_references=tuple(item.record_ref_key for item in unassigned_records),
        targeted_evidence_requests=targeted_requests,
        targeted_evidence_results=targeted_results, metrics=metrics,
        resolver_algorithm_version="constrained-identity-resolver-v1",
        resolution_fingerprint="",
    )
    return with_resolution_result_fingerprint(result)


def provenance(result):
    return G2V2SourceProvenance(
        scan_id=SCAN_ID, source_resolution_run_id=RESOLUTION_RUN_ID,
        source_discovery_run_id=DISCOVERY_RUN_ID,
        source_evidence_run_id=EVIDENCE_RUN_ID,
        source_resolution_status="COMPLETED",
        source_resolution_fingerprint=result.resolution_fingerprint,
        source_resolver_algorithm_version=result.resolver_algorithm_version,
    )


def build(records, result, proposals=(), targets=()):
    return build_g2_v2_manifest(
        result, records, proposals, targets, provenance(result)
    )


def test_m1_all_strong_complete_triangle_and_immutable_contracts():
    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    edges = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(1, 3, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    manifest = build(records, resolution(records, (hypothesis(records, edges),)), edges)
    group = manifest.groups[0]
    assert dataclasses.is_dataclass(type(manifest))
    assert type(manifest).__dataclass_params__.frozen is True
    assert manifest.snapshot_contract_version == 2
    assert manifest.likely_group_count == 1
    assert group.validation_coverage.evaluated_internal_pair_count == 3
    assert group.validation_coverage.possible_internal_pair_count == 3
    assert group.validation_coverage.missing_nonrequired_pair_count == 0


def test_m2_complete_review_pair_is_not_upgraded():
    records = (record(1, "A"), record(2, "B"))
    edges = (proposal(1, 2, IdentityEdgeClass.REVIEW_SUPPORT),)
    group = build(records, resolution(records, (hypothesis(records, edges),)), edges).groups[0]
    assert group.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
    assert group.validation_mode == IdentityValidationMode.COMPLETE_PAIRWISE
    assert group.validation_coverage.evaluated_internal_pair_count == 1


def test_m3_targeted_bridge_completes_pairwise_evidence():
    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    refs = {item.record_id: item.record_ref_key for item in records}
    proposals = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    target = targeted(1, 3, refs, IdentityEdgeClass.STRONG_SUPPORT)
    group_source = hypothesis(records, proposals + (target,))
    group = build(
        records, resolution(records, (group_source,), targeted_results=(target,)),
        proposals, (target,),
    ).groups[0]
    assert group.validation_coverage.proposal_evidence_count == 2
    assert group.validation_coverage.targeted_evidence_count == 1
    assert group.validation_coverage.evaluated_internal_pair_count == 3


def test_m4_progressive_review_preserves_missing_nonrequired_pairs():
    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    edges = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.REVIEW_SUPPORT),
    )
    source = hypothesis(
        records, edges,
        status=IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        mode=IdentityValidationMode.PROGRESSIVE_TARGETED,
    )
    group = build(records, resolution(records, (source,)), edges).groups[0]
    assert group.validation_mode == IdentityValidationMode.PROGRESSIVE_TARGETED
    assert group.validation_coverage.evaluated_internal_pair_count == 2
    assert group.validation_coverage.possible_internal_pair_count == 3
    assert group.validation_coverage.missing_nonrequired_pair_count == 1
    assert len(group.internal_evidence) == 2


def test_m5_conflict_remains_a_conflict():
    records = (record(1, "A"), record(2, "B"))
    conflict = with_identity_conflict_fingerprint(IdentityConflict(
        conflict_id="conflict-A-B", scan_id=SCAN_ID,
        involved_record_ids=(1, 2), involved_record_references=("A", "B"),
        conflict_type=IdentityConflictType.PROTECTED_CANNOT_LINK,
        protected_evidence_references=("protected-A-B",),
        source_neighborhood_references=("neighborhood-1",),
        summary="protected difference", fingerprint="",
    ))
    manifest = build(records, resolution(records, conflicts=(conflict,)))
    assert not manifest.groups
    assert manifest.conflict_count == 1
    assert manifest.conflicts[0].source_conflict_fingerprint == conflict.fingerprint


def test_m6_deferred_remains_deferred():
    records = (record(1, "A"), record(2, "B"))
    deferred = with_deferred_work_unit_fingerprint(DeferredIdentityWorkUnit(
        deferred_id="deferred-A-B", scan_id=SCAN_ID, record_ids=(1, 2),
        record_references=("A", "B"),
        reason=DeferredIdentityReason.INSUFFICIENT_PARTITION_STABILITY,
        unfinished_evidence_summary="more evidence required",
        source_neighborhood_references=("neighborhood-1",), fingerprint="",
    ))
    manifest = build(records, resolution(records, deferred=(deferred,)))
    assert not manifest.groups and not manifest.conflicts
    assert manifest.deferred_count == 1


def test_m7_duplicate_valued_source_rows_remain_distinct_members():
    records = (
        record(1, "row-1", part_no="SAME"),
        record(2, "row-2", part_no="SAME"),
    )
    edges = (proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),)
    group = build(records, resolution(records, (hypothesis(records, edges),)), edges).groups[0]
    assert [item.record_id for item in group.members] == [1, 2]
    assert [item.stable_record_reference for item in group.members] == ["row-1", "row-2"]


def test_m8_shuffled_inputs_produce_identical_manifest_and_fingerprints():
    records = (record(1, "A"), record(2, "B"), record(3, "C"), record(4, "D"))
    edges = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(3, 4, IdentityEdgeClass.REVIEW_SUPPORT),
    )
    groups = (
        hypothesis(records[:2], edges[:1]), hypothesis(records[2:], edges[1:]),
    )
    first_result = resolution(records, groups)
    second_result = resolution(records, tuple(reversed(groups)))
    first = build(records, first_result, edges)
    second = build(tuple(reversed(records)), second_result, tuple(reversed(edges)))
    assert first == second
    assert first.manifest_fingerprint == second.manifest_fingerprint


def test_s1_rejects_accepted_group_with_cannot_link():
    records = (record(1, "A"), record(2, "B"))
    safe_source_edges = (proposal(1, 2, IdentityEdgeClass.REVIEW_SUPPORT),)
    cannot = (proposal(1, 2, IdentityEdgeClass.CANNOT_LINK),)
    with pytest.raises(G2V2ManifestValidationError, match="CANNOT_LINK|coverage"):
        build(records, resolution(records, (hypothesis(records, safe_source_edges),)), cannot)


def test_s2_rejects_complete_pairwise_group_missing_one_pair():
    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    full = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(1, 3, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    with pytest.raises(G2V2ManifestValidationError, match="COMPLETE_PAIRWISE|coverage"):
        build(records, resolution(records, (hypothesis(records, full),)), full[:2])


def test_s3_rejects_missing_required_targeted_result():
    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    refs = {item.record_id: item.record_ref_key for item in records}
    proposals = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    target = targeted(1, 3, refs, IdentityEdgeClass.STRONG_SUPPORT)
    source = resolution(
        records, (hypothesis(records, proposals + (target,)),),
        targeted_results=(target,),
    )
    with pytest.raises(G2V2ManifestValidationError, match="targeted evidence"):
        build(records, source, proposals, ())


def test_s4_rejects_record_in_two_accepted_groups():
    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    edges = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.STRONG_SUPPORT),
    )
    groups = (
        hypothesis(records[:2], edges[:1]), hypothesis(records[1:], edges[1:]),
    )
    with pytest.raises(G2V2ManifestValidationError, match="two accepted"):
        build(records, resolution(records, groups), edges)


def test_s5_rejects_evidence_endpoint_outside_group():
    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    edges = (proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),)
    source = resolution(records, (hypothesis(records[:2], edges),))
    manifest = build(records, source, edges)
    group = manifest.groups[0]
    bad_edge = replace(
        group.internal_evidence[0], record_id_2=3,
        stable_record_reference_2="C",
    )
    bad = replace(manifest, groups=(replace(group, internal_evidence=(bad_edge,)),))
    with pytest.raises(G2V2ManifestValidationError, match="outside group"):
        validate_g2_v2_manifest(
            bad, source, records, edges, (), provenance(source)
        )


def test_s6_rejects_incompatible_proposal_and_targeted_evidence():
    records = (record(1, "A"), record(2, "B"))
    refs = {item.record_id: item.record_ref_key for item in records}
    proposal_edge = proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT)
    target = targeted(1, 2, refs, IdentityEdgeClass.REVIEW_SUPPORT)
    source_group = hypothesis(records, (proposal_edge,))
    source = resolution(records, (source_group,), targeted_results=(target,))
    with pytest.raises(ValueError, match="disagree"):
        build(records, source, (proposal_edge,), (target,))


def test_s7_rejects_source_review_group_mapped_as_likely():
    records = (record(1, "A"), record(2, "B"))
    edges = (proposal(1, 2, IdentityEdgeClass.REVIEW_SUPPORT),)
    source = resolution(records, (hypothesis(records, edges),))
    manifest = build(records, source, edges)
    bad_group = replace(
        manifest.groups[0], status=IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
    )
    bad = replace(manifest, groups=(bad_group,))
    with pytest.raises(G2V2ManifestValidationError, match="status differs"):
        validate_g2_v2_manifest(
            bad, source, records, edges, (), provenance(source)
        )


def test_adapter_contract_has_no_database_pair_g1_g2_or_provider_dependency():
    import app.g2_v2.adapter as module

    source = open(module.__file__, encoding="utf-8").read()
    forbidden = (
        "DuplicateCandidate", "IdentityGroupProjectionRun", "IdentityGroupSnapshot",
        "Session", "create_llm_provider", "GroupAdvisory",
    )
    assert not any(name in source for name in forbidden)
