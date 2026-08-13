"""Central provider-independent safety gate for automatic whole-group advisory."""

import json
from dataclasses import dataclass
from enum import Enum
from itertools import combinations

from sqlalchemy.orm import aliased

from app.db.models import (
    IdentityGroupEdgeSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupReviewEvent,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.llm.group_contracts import (
    GROUP_ADVISORY_REQUEST_VERSION,
    GroupAdvisoryCriticalMismatch,
    GroupAdvisoryEdge,
    GroupAdvisoryMember,
    GroupAdvisoryRequest,
    GroupIdentityEvidenceSummary,
    GroupUomMappingSummary,
    MAX_GROUP_ADVISORY_MEMBERS,
)


class GroupLlmEligibilityReason(str, Enum):
    ELIGIBLE_IDENTITY_AMBIGUITY = "ELIGIBLE_IDENTITY_AMBIGUITY"
    INELIGIBLE_SYSTEM_STATUS = "INELIGIBLE_SYSTEM_STATUS"
    INELIGIBLE_PROJECTION_NOT_COMPLETED = "INELIGIBLE_PROJECTION_NOT_COMPLETED"
    INELIGIBLE_INVALID_MEMBERSHIP = "INELIGIBLE_INVALID_MEMBERSHIP"
    INELIGIBLE_EVIDENCE_INCOMPLETE = "INELIGIBLE_EVIDENCE_INCOMPLETE"
    INELIGIBLE_CANNOT_LINK = "INELIGIBLE_CANNOT_LINK"
    INELIGIBLE_CRITICAL_MISMATCH = "INELIGIBLE_CRITICAL_MISMATCH"
    INELIGIBLE_TERMINAL_RULE = "INELIGIBLE_TERMINAL_RULE"
    INELIGIBLE_AMBIGUOUS_RECORD = "INELIGIBLE_AMBIGUOUS_RECORD"
    INELIGIBLE_OVERSIZED_GROUP = "INELIGIBLE_OVERSIZED_GROUP"
    INELIGIBLE_HUMAN_REVIEW_EXISTS = "INELIGIBLE_HUMAN_REVIEW_EXISTS"
    INELIGIBLE_MAPPING_ONLY_UNCERTAINTY = "INELIGIBLE_MAPPING_ONLY_UNCERTAINTY"
    INELIGIBLE_SCOPE_OR_ADMIN_ONLY_UNCERTAINTY = "INELIGIBLE_SCOPE_OR_ADMIN_ONLY_UNCERTAINTY"
    INELIGIBLE_NO_IDENTITY_AMBIGUITY = "INELIGIBLE_NO_IDENTITY_AMBIGUITY"


class ReviewReasonCategory(str, Enum):
    IDENTITY_AMBIGUITY = "IDENTITY_AMBIGUITY"
    MAPPING_ONLY = "MAPPING_ONLY"
    SCOPE_OR_ADMIN_ONLY = "SCOPE_OR_ADMIN_ONLY"
    TERMINAL_IDENTITY_CONFLICT = "TERMINAL_IDENTITY_CONFLICT"
    OTHER_NON_LLM = "OTHER_NON_LLM"


IDENTITY_AMBIGUITY_REASONS = frozenset({
    "DETERMINISTIC_REVIEW_CANDIDATE",
    "NON_TERMINAL_OR_ONE_SIDED_MISMATCH",
})
MAPPING_ONLY_REASONS = frozenset({"UOM_MAPPING_ONLY"})
SCOPE_OR_ADMIN_ONLY_REASONS = frozenset({"CROSS_SITE_SCOPE_ONLY"})
OTHER_NON_LLM_REASONS = frozenset({
    "DETERMINISTIC_LIKELY_DUPLICATE", "HUMAN_DUPLICATE",
    "SAME_PART_REFERENCE", "DETERMINISTIC_NON_GROUPABLE",
    "INVALID_CRITICAL_MISMATCH_EVIDENCE",
})
NON_IDENTITY_MISMATCH_GROUPS = frozenset({"CONTRACT", "UNIT_MEAS"})


def classify_group_review_reason(reason: str) -> ReviewReasonCategory:
    reason = str(reason or "").strip().upper()
    if reason in IDENTITY_AMBIGUITY_REASONS:
        return ReviewReasonCategory.IDENTITY_AMBIGUITY
    if reason in MAPPING_ONLY_REASONS:
        return ReviewReasonCategory.MAPPING_ONLY
    if reason in SCOPE_OR_ADMIN_ONLY_REASONS:
        return ReviewReasonCategory.SCOPE_OR_ADMIN_ONLY
    if reason.startswith("CRITICAL_MISMATCH_") or reason.startswith("IDENTITY_RULE_"):
        return ReviewReasonCategory.TERMINAL_IDENTITY_CONFLICT
    return ReviewReasonCategory.OTHER_NON_LLM


@dataclass(frozen=True)
class GroupEligibilityMember:
    record_ref_key: str
    member_index: int


@dataclass(frozen=True)
class GroupEligibilityEdge:
    left_record_ref_key: str
    right_record_ref_key: str
    edge_class: str
    reason_codes: tuple[str, ...]
    critical_mismatches: tuple[dict, ...] = ()


@dataclass(frozen=True)
class GroupEligibilityContext:
    projection_status: str
    group_status: str
    group_size: int
    max_group_validation_members: int
    members: tuple[GroupEligibilityMember, ...]
    internal_edges: tuple[GroupEligibilityEdge, ...]
    internal_pair_count: int
    evidence_completeness: float
    current_human_review_exists: bool = False


@dataclass(frozen=True)
class GroupLlmEligibilityResult:
    eligible: bool
    reason_code: GroupLlmEligibilityReason
    details: tuple[str, ...] = ()


def group_candidate_is_llm_eligible(
    context: GroupEligibilityContext,
) -> GroupLlmEligibilityResult:
    """Canonical pure gate; provider choice must occur strictly downstream."""
    fail = lambda reason, *details: GroupLlmEligibilityResult(False, reason, tuple(details)[:16])
    if context.projection_status != "COMPLETED":
        return fail(GroupLlmEligibilityReason.INELIGIBLE_PROJECTION_NOT_COMPLETED)
    if context.group_status != "POSSIBLE_DUPLICATE_GROUP_REVIEW":
        return fail(GroupLlmEligibilityReason.INELIGIBLE_SYSTEM_STATUS)
    limit = min(context.max_group_validation_members, MAX_GROUP_ADVISORY_MEMBERS)
    if context.group_size > limit:
        return fail(GroupLlmEligibilityReason.INELIGIBLE_OVERSIZED_GROUP)
    if context.group_size < 2:
        return fail(GroupLlmEligibilityReason.INELIGIBLE_INVALID_MEMBERSHIP)
    refs = [member.record_ref_key for member in context.members]
    indexes = [member.member_index for member in context.members]
    if (
        len(refs) != context.group_size or len(set(refs)) != len(refs)
        or indexes != list(range(context.group_size))
        or any(len(ref) != 64 for ref in refs)
    ):
        return fail(GroupLlmEligibilityReason.INELIGIBLE_INVALID_MEMBERSHIP)
    expected_pairs = context.group_size * (context.group_size - 1) // 2
    pair_keys = []
    for edge in context.internal_edges:
        if (
            edge.left_record_ref_key >= edge.right_record_ref_key
            or edge.left_record_ref_key not in refs or edge.right_record_ref_key not in refs
            or edge.edge_class not in {
                "STRONG_SUPPORT", "REVIEW_SUPPORT", "NON_GROUPABLE", "CANNOT_LINK"
            }
            or len(edge.reason_codes) > 32
            or any(not isinstance(reason, str) or not reason.strip()
                   for reason in edge.reason_codes)
            or not _mismatch_evidence_is_valid(edge.critical_mismatches)
        ):
            return fail(GroupLlmEligibilityReason.INELIGIBLE_EVIDENCE_INCOMPLETE)
        pair_keys.append((edge.left_record_ref_key, edge.right_record_ref_key))
    if (
        context.internal_pair_count != expected_pairs
        or len(context.internal_edges) != expected_pairs
        or len(set(pair_keys)) != expected_pairs
        or set(pair_keys) != set(combinations(sorted(refs), 2))
        or context.evidence_completeness != 1.0
    ):
        return fail(GroupLlmEligibilityReason.INELIGIBLE_EVIDENCE_INCOMPLETE)
    if any(edge.edge_class == "CANNOT_LINK" for edge in context.internal_edges):
        return fail(GroupLlmEligibilityReason.INELIGIBLE_CANNOT_LINK)
    all_reasons = tuple(sorted({
        reason for edge in context.internal_edges for reason in edge.reason_codes
    }))
    if any(
        _has_affirmative_identity_mismatch(edge.critical_mismatches)
        for edge in context.internal_edges
    ) or any(
        reason.startswith("CRITICAL_MISMATCH_") for reason in all_reasons
    ):
        return fail(GroupLlmEligibilityReason.INELIGIBLE_CRITICAL_MISMATCH)
    if any(reason.startswith("IDENTITY_RULE_") for reason in all_reasons):
        return fail(GroupLlmEligibilityReason.INELIGIBLE_TERMINAL_RULE)
    if "AMBIGUOUS_SCAN_LOCAL_RECORD_REF" in all_reasons:
        return fail(GroupLlmEligibilityReason.INELIGIBLE_AMBIGUOUS_RECORD)
    if context.current_human_review_exists:
        return fail(GroupLlmEligibilityReason.INELIGIBLE_HUMAN_REVIEW_EXISTS)
    categories = {classify_group_review_reason(reason) for reason in all_reasons}
    if ReviewReasonCategory.IDENTITY_AMBIGUITY in categories:
        return GroupLlmEligibilityResult(
            True, GroupLlmEligibilityReason.ELIGIBLE_IDENTITY_AMBIGUITY,
            tuple(reason for reason in all_reasons if classify_group_review_reason(reason)
                  == ReviewReasonCategory.IDENTITY_AMBIGUITY)[:16],
        )
    if categories and categories <= {ReviewReasonCategory.MAPPING_ONLY, ReviewReasonCategory.OTHER_NON_LLM} and ReviewReasonCategory.MAPPING_ONLY in categories:
        return fail(GroupLlmEligibilityReason.INELIGIBLE_MAPPING_ONLY_UNCERTAINTY, *all_reasons)
    if categories and categories <= {ReviewReasonCategory.SCOPE_OR_ADMIN_ONLY, ReviewReasonCategory.OTHER_NON_LLM} and ReviewReasonCategory.SCOPE_OR_ADMIN_ONLY in categories:
        return fail(GroupLlmEligibilityReason.INELIGIBLE_SCOPE_OR_ADMIN_ONLY_UNCERTAINTY, *all_reasons)
    return fail(GroupLlmEligibilityReason.INELIGIBLE_NO_IDENTITY_AMBIGUITY, *all_reasons)


def _json_list(value, *, limit):
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, list) or len(parsed) > limit:
        return None
    return parsed


def _valid_mismatch_rows(value) -> tuple[dict, ...] | None:
    try:
        decoded = json.loads(value or "[]")
        # G2 snapshots created from persisted pair rows retain that row's JSON
        # text as their audit value. Decode that bounded legacy representation
        # exactly once; arbitrary nested or malformed values still fail closed.
        if isinstance(decoded, str):
            decoded = json.loads(decoded)
    except (TypeError, json.JSONDecodeError):
        return None
    rows = decoded if isinstance(decoded, list) and len(decoded) <= 10 else None
    if rows is None:
        return None
    validated = []
    for item in rows:
        if not isinstance(item, dict) or not str(item.get("group") or "").strip():
            return None
        for key in ("values_a", "values_b"):
            values = item.get(key, [])
            if not isinstance(values, list) or len(values) > 10 or any(
                not isinstance(entry, (str, int, float, bool)) for entry in values
            ):
                return None
        validated.append(item)
    return tuple(validated)


def _has_affirmative_identity_mismatch(mismatches: tuple[dict, ...]) -> bool:
    for mismatch in mismatches:
        group = str(mismatch.get("group") or "").strip().upper()
        if group in NON_IDENTITY_MISMATCH_GROUPS:
            continue
        if mismatch.get("values_a") and mismatch.get("values_b"):
            return True
    return False


def _mismatch_evidence_is_valid(mismatches: tuple[dict, ...]) -> bool:
    if not isinstance(mismatches, tuple) or len(mismatches) > 10:
        return False
    for item in mismatches:
        if not isinstance(item, dict) or not str(item.get("group") or "").strip():
            return False
        for key in ("values_a", "values_b"):
            values = item.get(key, [])
            if not isinstance(values, list) or len(values) > 10 or any(
                not isinstance(entry, (str, int, float, bool)) for entry in values
            ):
                return False
    return True


class GroupAdvisoryContractService:
    """Read immutable G2 evidence and build at most one bounded request per group."""

    def __init__(self, db):
        self.db = db

    def load(self, scan_id: int, projection_run_id: int, group_snapshot_id: int):
        group_run = self.db.query(IdentityGroupSnapshot, IdentityGroupProjectionRun).join(
            IdentityGroupProjectionRun,
            IdentityGroupProjectionRun.id == IdentityGroupSnapshot.projection_run_id,
        ).filter(
            IdentityGroupSnapshot.id == group_snapshot_id,
            IdentityGroupSnapshot.scan_id == scan_id,
            IdentityGroupSnapshot.projection_run_id == projection_run_id,
            IdentityGroupProjectionRun.scan_id == scan_id,
        ).one_or_none()
        if group_run is None:
            raise LookupError("identity group snapshot not found")
        group, run = group_run
        member_rows = self.db.query(
            IdentityGroupMemberSnapshot, ScanRecordSnapshot
        ).join(
            ScanRecordSnapshot,
            ScanRecordSnapshot.id == IdentityGroupMemberSnapshot.record_snapshot_id,
        ).filter(
            IdentityGroupMemberSnapshot.group_snapshot_id == group.id
        ).order_by(IdentityGroupMemberSnapshot.member_index).all()
        record_by_id = {record.id: (member, record) for member, record in member_rows}
        edge_rows = self.db.query(IdentityGroupEdgeSnapshot).filter_by(
            group_snapshot_id=group.id
        ).order_by(
            IdentityGroupEdgeSnapshot.left_record_snapshot_id,
            IdentityGroupEdgeSnapshot.right_record_snapshot_id,
        ).all()
        successor = aliased(IdentityGroupReviewEvent)
        current_review = self.db.query(IdentityGroupReviewEvent.id).outerjoin(
            successor,
            successor.supersedes_review_event_id == IdentityGroupReviewEvent.id,
        ).filter(
            IdentityGroupReviewEvent.group_snapshot_id == group.id,
            successor.id.is_(None),
        ).first() is not None
        parsed_edges = []
        invalid_json = False
        for edge in edge_rows:
            reasons = _json_list(edge.reason_codes_json, limit=32)
            mismatches = _valid_mismatch_rows(edge.critical_mismatches_json)
            if reasons is None or mismatches is None:
                invalid_json = True; reasons = reasons or (); mismatches = mismatches or ()
            left = record_by_id.get(edge.left_record_snapshot_id)
            right = record_by_id.get(edge.right_record_snapshot_id)
            if left is None or right is None:
                left_ref = right_ref = ""
            else:
                left_ref, right_ref = sorted((left[0].record_ref_key, right[0].record_ref_key))
            parsed_edges.append(GroupEligibilityEdge(
                left_ref, right_ref, edge.edge_class, tuple(str(x) for x in reasons),
                tuple(mismatches),
            ))
        context = GroupEligibilityContext(
            run.status, group.group_status, group.group_size,
            run.max_group_validation_members,
            tuple(GroupEligibilityMember(member.record_ref_key, member.member_index)
                  for member, _ in member_rows),
            tuple(parsed_edges), group.internal_pair_count,
            -1 if invalid_json else group.evidence_completeness,
            current_review,
        )
        return run, group, member_rows, edge_rows, context

    def eligibility(self, scan_id: int, projection_run_id: int, group_snapshot_id: int):
        return group_candidate_is_llm_eligible(
            self.load(scan_id, projection_run_id, group_snapshot_id)[4]
        )

    def build_request(self, scan_id: int, projection_run_id: int, group_snapshot_id: int):
        run, group, member_rows, edge_rows, context = self.load(
            scan_id, projection_run_id, group_snapshot_id
        )
        eligibility = group_candidate_is_llm_eligible(context)
        if not eligibility.eligible:
            return eligibility, None
        records = {record.id: (member, record) for member, record in member_rows}
        members = tuple(sorted((GroupAdvisoryMember(
            record_ref_key=member.record_ref_key,
            part_no=str(record.part_no or "")[:200],
            normalized_part_no=str(record.normalized_part_no or "")[:512],
            description=str(record.description or "")[:2048],
            normalized_description=str(record.normalized_description or "")[:2048],
            site_or_contract=str(record.contract)[:200] if record.contract else None,
            uom=str(record.uom)[:200] if record.uom else None,
            product_category=str(record.product_category_id)[:200] if record.product_category_id else None,
            hsn_sac=str(record.hsn_sac_code)[:200] if record.hsn_sac_code else None,
        ) for member, record in member_rows), key=lambda item: item.record_ref_key))
        edges = []
        for row in edge_rows:
            left, right = records[row.left_record_snapshot_id], records[row.right_record_snapshot_id]
            left_ref, right_ref = sorted((left[0].record_ref_key, right[0].record_ref_key))
            reasons = tuple(sorted(set(_json_list(row.reason_codes_json, limit=32) or ())))
            mismatches = []
            for item in _valid_mismatch_rows(row.critical_mismatches_json) or ():
                mismatches.append(GroupAdvisoryCriticalMismatch(
                    group=str(item.get("group") or "UNKNOWN")[:128],
                    label=str(item.get("label"))[:200] if item.get("label") else None,
                    values_left=tuple(str(x)[:200] for x in item.get("values_a", [])[:10]),
                    values_right=tuple(str(x)[:200] for x in item.get("values_b", [])[:10]),
                ))
            edges.append(GroupAdvisoryEdge(
                left_record_ref_key=left_ref, right_record_ref_key=right_ref,
                edge_class=row.edge_class, reason_codes=reasons,
                evidence_source=row.evidence_source,
                deterministic_status=row.deterministic_status,
                critical_mismatches=tuple(mismatches),
            ))
        edges = tuple(sorted(edges, key=lambda item: (
            item.left_record_ref_key, item.right_record_ref_key
        )))
        reasons = tuple(sorted({reason for edge in edges for reason in edge.reason_codes}))
        request = GroupAdvisoryRequest(
            contract_version=GROUP_ADVISORY_REQUEST_VERSION,
            scan_id=scan_id, projection_run_id=run.id, group_snapshot_id=group.id,
            group_hypothesis_key=group.hypothesis_key,
            projection_algorithm_version=group.projection_algorithm_version,
            group_status=group.group_status, group_size=group.group_size,
            members=members, internal_edges=edges,
            group_identity_evidence_summary=GroupIdentityEvidenceSummary(
                strong_support_count=sum(edge.edge_class == "STRONG_SUPPORT" for edge in edges),
                review_support_count=sum(edge.edge_class == "REVIEW_SUPPORT" for edge in edges),
                non_groupable_count=sum(edge.edge_class == "NON_GROUPABLE" for edge in edges),
                internal_pair_count=len(edges), evidence_completeness=group.evidence_completeness,
                reason_codes=reasons,
            ),
            group_uom_mapping_summary=GroupUomMappingSummary(
                distinct_uoms=tuple(sorted(set(_json_list(group.distinct_uoms_json, limit=20) or ()))),
                same_uom_pair_count=group.same_uom_pair_count,
                convertible_uom_pair_count=group.convertible_uom_pair_count,
                different_basis_pair_count=group.different_basis_pair_count,
                missing_or_wildcard_pair_count=group.missing_or_wildcard_pair_count,
                malformed_or_unknown_pair_count=group.malformed_or_unknown_pair_count,
                possible_mapping_error_count=group.possible_mapping_error_count,
                identity_authority=False,
            ),
            unresolved_identity_questions=eligibility.details,
        )
        return eligibility, request
