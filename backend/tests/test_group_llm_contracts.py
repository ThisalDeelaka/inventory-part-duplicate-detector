import json
import random
from itertools import combinations

import pytest

from app.db.models import (
    DuplicateScan,
    IdentityGroupEdgeSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.llm.groq_provider import GroqLLMProvider
from app.llm.group_contracts import (
    GROUP_ADVISORY_REQUEST_VERSION,
    GROUP_ADVISORY_RESULT_VERSION,
    GroupAdvisoryConfidenceBand,
    GroupAdvisoryEdge,
    GroupAdvisoryMember,
    GroupAdvisoryOutcome,
    GroupAdvisoryRequest,
    GroupAdvisoryResult,
    GroupIdentityEvidenceSummary,
    GroupUomMappingSummary,
    canonical_group_advisory_request_json,
    group_advisory_request_fingerprint,
    validate_group_advisory_result,
)
from app.services.group_llm_eligibility import (
    GroupAdvisoryContractService,
    GroupEligibilityContext,
    GroupEligibilityEdge,
    GroupEligibilityMember,
    GroupLlmEligibilityReason,
    ReviewReasonCategory,
    classify_group_review_reason,
    group_candidate_is_llm_eligible,
)
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    IdentityGroupReviewService,
)


def refs(size):
    return tuple(f"{index:064x}" for index in range(1, size + 1))


def context(size=4, *, status="POSSIBLE_DUPLICATE_GROUP_REVIEW",
            run_status="COMPLETED", reasons=("DETERMINISTIC_REVIEW_CANDIDATE",),
            edge_class="REVIEW_SUPPORT", reviewed=False, completeness=1.0,
            critical=False, edge_count=None, max_members=20):
    member_refs = refs(size)
    pairs = list(combinations(member_refs, 2))
    if edge_count is not None:
        pairs = pairs[:edge_count]
    edges = tuple(GroupEligibilityEdge(
        left, right, edge_class, tuple(reasons),
        ({"group": "STRUCTURAL_ROLE", "values_a": ["drive-end"],
          "values_b": ["non-drive-end"]},) if critical else (),
    ) for left, right in pairs)
    return GroupEligibilityContext(
        run_status, status, size, max_members,
        tuple(GroupEligibilityMember(ref, index) for index, ref in enumerate(member_refs)),
        edges, size * (size - 1) // 2, completeness, reviewed,
    )


def assert_reason(value, reason):
    result = group_candidate_is_llm_eligible(value)
    assert result.eligible is (reason == GroupLlmEligibilityReason.ELIGIBLE_IDENTITY_AMBIGUITY)
    assert result.reason_code == reason


def test_clean_unresolved_identity_group_is_eligible():
    assert_reason(context(), GroupLlmEligibilityReason.ELIGIBLE_IDENTITY_AMBIGUITY)


def test_likely_and_incomplete_projection_stop_before_llm():
    assert_reason(context(status="LIKELY_DUPLICATE_GROUP"), GroupLlmEligibilityReason.INELIGIBLE_SYSTEM_STATUS)
    assert_reason(context(run_status="FAILED"), GroupLlmEligibilityReason.INELIGIBLE_PROJECTION_NOT_COMPLETED)


@pytest.mark.parametrize("decision", list(GroupReviewDecision))
def test_every_current_human_review_including_unsure_blocks_automatic_llm(decision):
    assert_reason(context(reviewed=True), GroupLlmEligibilityReason.INELIGIBLE_HUMAN_REVIEW_EXISTS)


def test_cannot_critical_terminal_ambiguous_and_incomplete_fail_closed():
    assert_reason(context(edge_class="CANNOT_LINK"), GroupLlmEligibilityReason.INELIGIBLE_CANNOT_LINK)
    assert_reason(context(critical=True), GroupLlmEligibilityReason.INELIGIBLE_CRITICAL_MISMATCH)
    assert_reason(context(reasons=("IDENTITY_RULE_HSN_SAC_CODE_MISMATCH",)), GroupLlmEligibilityReason.INELIGIBLE_TERMINAL_RULE)
    assert_reason(context(reasons=("AMBIGUOUS_SCAN_LOCAL_RECORD_REF",)), GroupLlmEligibilityReason.INELIGIBLE_AMBIGUOUS_RECORD)
    assert_reason(context(edge_count=5), GroupLlmEligibilityReason.INELIGIBLE_EVIDENCE_INCOMPLETE)
    assert_reason(context(completeness=.9), GroupLlmEligibilityReason.INELIGIBLE_EVIDENCE_INCOMPLETE)
    malformed = context()
    malformed_edges = tuple(
        GroupEligibilityEdge(
            edge.left_record_ref_key, edge.right_record_ref_key, edge.edge_class,
            edge.reason_codes, ({"group": "STRUCTURAL_ROLE", "values_a": "bad"},),
        ) for edge in malformed.internal_edges
    )
    assert_reason(
        GroupEligibilityContext(
            malformed.projection_status, malformed.group_status, malformed.group_size,
            malformed.max_group_validation_members, malformed.members, malformed_edges,
            malformed.internal_pair_count, malformed.evidence_completeness,
        ),
        GroupLlmEligibilityReason.INELIGIBLE_EVIDENCE_INCOMPLETE,
    )


def test_invalid_membership_and_size_bounds_fail_closed():
    invalid = context()
    invalid = GroupEligibilityContext(
        invalid.projection_status, invalid.group_status, invalid.group_size,
        invalid.max_group_validation_members,
        invalid.members[:-1], invalid.internal_edges, invalid.internal_pair_count,
        invalid.evidence_completeness,
    )
    assert_reason(invalid, GroupLlmEligibilityReason.INELIGIBLE_INVALID_MEMBERSHIP)
    assert_reason(context(size=20), GroupLlmEligibilityReason.ELIGIBLE_IDENTITY_AMBIGUITY)
    assert_reason(context(size=21), GroupLlmEligibilityReason.INELIGIBLE_OVERSIZED_GROUP)


def test_mapping_scope_and_no_identity_ambiguity_are_not_llm_work():
    assert_reason(context(reasons=("UOM_MAPPING_ONLY",)), GroupLlmEligibilityReason.INELIGIBLE_MAPPING_ONLY_UNCERTAINTY)
    assert_reason(context(reasons=("CROSS_SITE_SCOPE_ONLY",)), GroupLlmEligibilityReason.INELIGIBLE_SCOPE_OR_ADMIN_ONLY_UNCERTAINTY)
    assert_reason(context(reasons=("DETERMINISTIC_NON_GROUPABLE",)), GroupLlmEligibilityReason.INELIGIBLE_NO_IDENTITY_AMBIGUITY)
    assert_reason(context(reasons=("DETERMINISTIC_REVIEW_CANDIDATE", "UOM_MAPPING_ONLY")), GroupLlmEligibilityReason.ELIGIBLE_IDENTITY_AMBIGUITY)


def test_mapping_mismatch_context_is_not_an_identity_critical_mismatch():
    base = context(reasons=("UOM_MAPPING_ONLY",))
    mapped_edges = tuple(GroupEligibilityEdge(
        edge.left_record_ref_key, edge.right_record_ref_key, edge.edge_class,
        edge.reason_codes,
        ({"group": "UNIT_MEAS", "values_a": ["l"], "values_b": ["PCS"]},),
    ) for edge in base.internal_edges)
    mapped = GroupEligibilityContext(
        base.projection_status, base.group_status, base.group_size,
        base.max_group_validation_members, base.members, mapped_edges,
        base.internal_pair_count, base.evidence_completeness,
    )
    assert_reason(mapped, GroupLlmEligibilityReason.INELIGIBLE_MAPPING_ONLY_UNCERTAINTY)


def test_exact_review_reason_taxonomy_is_stable_and_narrow():
    assert classify_group_review_reason("DETERMINISTIC_REVIEW_CANDIDATE") == ReviewReasonCategory.IDENTITY_AMBIGUITY
    assert classify_group_review_reason("NON_TERMINAL_OR_ONE_SIDED_MISMATCH") == ReviewReasonCategory.IDENTITY_AMBIGUITY
    assert classify_group_review_reason("UOM_MAPPING_ONLY") == ReviewReasonCategory.MAPPING_ONLY
    assert classify_group_review_reason("CROSS_SITE_SCOPE_ONLY") == ReviewReasonCategory.SCOPE_OR_ADMIN_ONLY
    assert classify_group_review_reason("CRITICAL_MISMATCH_STRUCTURAL_ROLE") == ReviewReasonCategory.TERMINAL_IDENTITY_CONFLICT
    assert classify_group_review_reason("UNKNOWN_FUTURE_REASON") == ReviewReasonCategory.OTHER_NON_LLM


def persisted_review_group(db, size=4, *, key="a", status="POSSIBLE_DUPLICATE_GROUP_REVIEW",
                           reason="DETERMINISTIC_REVIEW_CANDIDATE", member_order=None,
                           edge_order=None, extra=None):
    scan = DuplicateScan(id=1, scan_name="scan", threshold=80, status="COMPLETED",
                         model_version="deterministic-v1", selected_fields="[]")
    db.add(scan); db.flush(); pairs = size * (size - 1) // 2
    run = IdentityGroupProjectionRun(
        scan_id=1, algorithm_version="constrained-group-projection-v1",
        edge_classifier_version="identity-edge-classifier-v1", evidence_fingerprint=key * 64,
        max_group_validation_members=20, engine_version="deterministic-v1", status="COMPLETED",
        records_seen=size, seed_edges=max(1, size - 1), provisional_components=1,
        accepted_groups=1, likely_groups=int(status == "LIKELY_DUPLICATE_GROUP"),
        review_groups=int(status == "POSSIBLE_DUPLICATE_GROUP_REVIEW"), conflicting_families=0,
        oversized_families=0, ambiguous_families=0, internal_pairs_total=pairs,
        internal_pairs_reused=pairs, internal_pairs_rescored=0, cannot_links_found=0,
        max_component_size=size, max_accepted_group_size=size,
    )
    db.add(run); db.flush()
    group = IdentityGroupSnapshot(
        projection_run_id=run.id, scan_id=1, hypothesis_key=key * 64,
        projection_algorithm_version=run.algorithm_version, group_status=status,
        group_size=size, supporting_edge_count=0, review_edge_count=pairs,
        non_groupable_internal_count=0, internal_pair_count=pairs,
        internal_pairs_reused=pairs, internal_pairs_rescored=0, evidence_completeness=1,
        distinct_uoms_json='["PCS","l"]', same_uom_pair_count=pairs,
        convertible_uom_pair_count=0, different_basis_pair_count=0,
        missing_or_wildcard_pair_count=0, malformed_or_unknown_pair_count=0,
        possible_mapping_error_count=0, reason_codes_json=json.dumps([reason]),
    )
    db.add(group); db.flush(); records = {}
    for index in (member_order if member_order is not None else range(size)):
        ref = refs(size)[index]
        record = ScanRecordSnapshot(
            scan_id=1, record_ref_key=ref, contract="S1", part_no=f"P-{index}",
            description=f"Component {index}", normalized_part_no=f"p {index}",
            normalized_description=f"component {index}", uom="PCS",
            product_category_id="CAT", hsn_sac_code="1000",
        )
        db.add(record); db.flush(); records[index] = record
        db.add(IdentityGroupMemberSnapshot(
            group_snapshot_id=group.id, record_snapshot_id=record.id,
            member_index=index, record_ref_key=ref,
        ))
    pair_indexes = list(combinations(range(size), 2))
    if edge_order is not None:
        pair_indexes = [pair_indexes[index] for index in edge_order]
    for left, right in pair_indexes:
        left_record_id, right_record_id = sorted((records[left].id, records[right].id))
        db.add(IdentityGroupEdgeSnapshot(
            group_snapshot_id=group.id,
            left_record_snapshot_id=left_record_id,
            right_record_snapshot_id=right_record_id,
            edge_class="REVIEW_SUPPORT", reason_codes_json=json.dumps([reason]),
            evidence_source="G1_LOCAL_RESCORING" if left == 0 and right == size - 1 else "PERSISTED_CANDIDATE",
            deterministic_status="POSSIBLE_DUPLICATE_REVIEW",
            # G2 preserves the pair row's JSON text as a bounded audit value.
            critical_mismatches_json=json.dumps("[]"),
        ))
    db.commit(); return run, group, refs(size)


@pytest.mark.parametrize("size,edges", [(2, 1), (4, 6), (7, 21), (14, 91)])
def test_one_bounded_whole_group_request_has_every_member_and_edge(db, size, edges):
    run, group, _ = persisted_review_group(db, size=size)
    eligibility, request = GroupAdvisoryContractService(db).build_request(1, run.id, group.id)
    assert eligibility.eligible
    assert request.group_size == len(request.members) == size
    assert len(request.internal_edges) == edges
    assert request.contract_version == GROUP_ADVISORY_REQUEST_VERSION


def test_request_is_order_independent_minimal_and_preserves_local_rescoring(db):
    run, group, _ = persisted_review_group(
        db, size=7, member_order=[6, 1, 5, 0, 4, 2, 3],
        edge_order=list(reversed(range(21))), extra={"SECRET": "must-not-appear"},
    )
    _, request = GroupAdvisoryContractService(db).build_request(1, run.id, group.id)
    serialized = canonical_group_advisory_request_json(request)
    assert "SECRET" not in serialized and "provider" not in serialized.lower()
    assert len(serialized) < 100_000
    assert any(edge.evidence_source == "G1_LOCAL_RESCORING" for edge in request.internal_edges)
    first = group_advisory_request_fingerprint(request)
    # Canonical serialization is independent of both DB and consumer ordering.
    _, rebuilt = GroupAdvisoryContractService(db).build_request(1, run.id, group.id)
    assert first == group_advisory_request_fingerprint(rebuilt)
    randomizer = random.Random(7)
    for _ in range(10):
        members = list(request.members); randomizer.shuffle(members)
        edges = list(request.internal_edges); randomizer.shuffle(edges)
        shuffled = request.model_copy(update={
            "members": tuple(members), "internal_edges": tuple(edges),
        })
        assert first == group_advisory_request_fingerprint(shuffled)


def base_request(size=5, cannot_pair=None):
    member_refs = refs(size)
    edges = []
    for left, right in combinations(member_refs, 2):
        edge_class = "CANNOT_LINK" if frozenset((left, right)) == cannot_pair else "REVIEW_SUPPORT"
        edges.append(GroupAdvisoryEdge(
            left_record_ref_key=left, right_record_ref_key=right,
            edge_class=edge_class, reason_codes=("DETERMINISTIC_REVIEW_CANDIDATE",),
            evidence_source="PERSISTED_CANDIDATE", deterministic_status="POSSIBLE_DUPLICATE_REVIEW",
        ))
    return GroupAdvisoryRequest(
        contract_version=GROUP_ADVISORY_REQUEST_VERSION, scan_id=1,
        projection_run_id=2, group_snapshot_id=3, group_hypothesis_key="a" * 64,
        projection_algorithm_version="constrained-group-projection-v1",
        group_status="POSSIBLE_DUPLICATE_GROUP_REVIEW", group_size=size,
        members=tuple(GroupAdvisoryMember(
            record_ref_key=ref, part_no=f"P-{index}", normalized_part_no=f"p {index}",
            description=f"Part {index}", normalized_description=f"part {index}",
            site_or_contract="S1", uom="PCS",
        ) for index, ref in enumerate(member_refs)),
        internal_edges=tuple(edges),
        group_identity_evidence_summary=GroupIdentityEvidenceSummary(
            strong_support_count=0, review_support_count=len(edges), non_groupable_count=0,
            internal_pair_count=len(edges), evidence_completeness=1,
            reason_codes=("DETERMINISTIC_REVIEW_CANDIDATE",),
        ),
        group_uom_mapping_summary=GroupUomMappingSummary(
            distinct_uoms=("PCS",), same_uom_pair_count=len(edges),
            convertible_uom_pair_count=0, different_basis_pair_count=0,
            missing_or_wildcard_pair_count=0, malformed_or_unknown_pair_count=0,
            possible_mapping_error_count=0, identity_authority=False,
        ),
        unresolved_identity_questions=("DETERMINISTIC_REVIEW_CANDIDATE",),
    )


def result(request, outcome, partitions, **overrides):
    data = dict(
        contract_version=GROUP_ADVISORY_RESULT_VERSION,
        request_fingerprint=group_advisory_request_fingerprint(request),
        group_snapshot_id=request.group_snapshot_id,
        group_hypothesis_key=request.group_hypothesis_key,
        outcome=outcome, proposed_partitions=partitions,
        confidence_band=GroupAdvisoryConfidenceBand.MEDIUM,
        reason_codes=("SEMANTIC_AMBIGUITY_REVIEWED",), rationale="Advisory only",
        mapping_observations=(),
        requires_human_review=True, deterministic_result_authoritative=True,
    )
    data.update(overrides); return data


def test_valid_single_identity_and_complete_partitions_are_advisory_only():
    request = base_request(); members = tuple(x.record_ref_key for x in request.members)
    single = validate_group_advisory_result(
        request, result(request, "SUPPORTS_SINGLE_IDENTITY", (members,))
    )
    split = validate_group_advisory_result(
        request, result(request, "PROPOSES_PARTITION", (members[:4], members[4:]))
    )
    split_three = validate_group_advisory_result(
        request, result(request, "PROPOSES_PARTITION", (members[:2], members[2:4], members[4:]))
    )
    assert [single.outcome, split.outcome, split_three.outcome] == [
        GroupAdvisoryOutcome.SUPPORTS_SINGLE_IDENTITY,
        GroupAdvisoryOutcome.PROPOSES_PARTITION,
        GroupAdvisoryOutcome.PROPOSES_PARTITION,
    ]
    assert all(x.requires_human_review and x.deterministic_result_authoritative for x in (single, split, split_three))


@pytest.mark.parametrize("mutate,reason", [
    (lambda m: (m[:-1],), "INCOMPLETE_PARTITION_MEMBERSHIP"),
    (lambda m: ((m[0], m[0], *m[1:]),), "DUPLICATE_PARTITION_MEMBER"),
    (lambda m: (("f" * 64, *m[1:]),), "UNKNOWN_PARTITION_MEMBER"),
    (lambda m: ((), m), "EMPTY_PARTITION"),
])
def test_invalid_membership_normalizes_to_inconclusive(mutate, reason):
    request = base_request(); members = tuple(x.record_ref_key for x in request.members)
    validated = validate_group_advisory_result(
        request, result(request, "PROPOSES_PARTITION", mutate(members))
    )
    assert validated.outcome == GroupAdvisoryOutcome.INCONCLUSIVE
    assert reason in validated.validation_reasons


def test_outcome_partition_semantics_fail_closed():
    request = base_request(); members = tuple(x.record_ref_key for x in request.members)
    checks = [
        result(request, "PROPOSES_PARTITION", (members,)),
        result(request, "SUPPORTS_SINGLE_IDENTITY", (members[:2], members[2:])),
        result(request, "INCONCLUSIVE", (members,)),
    ]
    assert all(validate_group_advisory_result(request, item).outcome == GroupAdvisoryOutcome.INCONCLUSIVE for item in checks)


def test_cannot_link_wrong_group_and_fingerprint_cannot_be_overridden():
    members = refs(5); protected = frozenset((members[0], members[1])); request = base_request(cannot_pair=protected)
    violation = validate_group_advisory_result(
        request, result(request, "PROPOSES_PARTITION", (members[:4], members[4:]))
    )
    mismatch = validate_group_advisory_result(
        request, result(request, "INCONCLUSIVE", (), request_fingerprint="f" * 64, group_snapshot_id=99)
    )
    assert "PROTECTED_CANNOT_LINK_VIOLATION" in violation.validation_reasons
    assert {"REQUEST_FINGERPRINT_MISMATCH", "GROUP_SNAPSHOT_MISMATCH"}.issubset(mismatch.validation_reasons)


def test_schema_extra_unknown_outcome_and_oversized_rationale_fail_closed():
    request = base_request()
    bad = result(request, "UNKNOWN", (), automatic_merge=True, rationale="x" * 5000)
    validated = validate_group_advisory_result(request, bad)
    assert validated.outcome == GroupAdvisoryOutcome.INCONCLUSIVE
    assert validated.validation_reasons == ("SCHEMA_MISMATCH",)
    assert validated.requires_human_review and validated.deterministic_result_authoritative


def test_group_contract_service_never_calls_provider(db, monkeypatch):
    run, group, _ = persisted_review_group(db, size=4)
    calls = []
    monkeypatch.setattr(GroqLLMProvider, "complete_json", lambda *_a, **_k: calls.append(True))
    eligibility, request = GroupAdvisoryContractService(db).build_request(1, run.id, group.id)
    assert eligibility.eligible and request is not None and calls == []


def test_current_real_review_blocks_contract_creation(db):
    run, group, member_refs = persisted_review_group(db, size=4)
    IdentityGroupReviewService(db).create_review(
        scan_id=1, projection_run_id=run.id, group_snapshot_id=group.id,
        group_hypothesis_key=group.hypothesis_key,
        decision_type=GroupReviewDecision.UNSURE, reviewer="reviewer",
        submitted_members=member_refs,
    )
    eligibility, request = GroupAdvisoryContractService(db).build_request(1, run.id, group.id)
    assert eligibility.reason_code == GroupLlmEligibilityReason.INELIGIBLE_HUMAN_REVIEW_EXISTS
    assert request is None


def test_malformed_persisted_mismatch_evidence_fails_closed(db):
    run, group, _ = persisted_review_group(db, size=2)
    edge = db.query(IdentityGroupEdgeSnapshot).filter_by(
        group_snapshot_id=group.id
    ).one()
    edge.critical_mismatches_json = '{"not":"a-list"}'
    db.commit()
    eligibility, request = GroupAdvisoryContractService(db).build_request(
        1, run.id, group.id
    )
    assert eligibility.reason_code == GroupLlmEligibilityReason.INELIGIBLE_EVIDENCE_INCOMPLETE
    assert request is None
