"""Strict pure validators for GF-6A G2-v2 manifests."""

from __future__ import annotations

from collections import defaultdict

from app.engine.identity_edge import IdentityEdgeClass
from app.g2_v2.contracts import (
    G2_V2_ADAPTER_ALGORITHM_VERSION,
    G2_V2_SNAPSHOT_CONTRACT_VERSION,
    G2V2EvidenceOrigin,
)
from app.g2_v2.fingerprints import (
    g2_v2_conflict_fingerprint,
    g2_v2_deferred_fingerprint,
    g2_v2_group_fingerprint,
    g2_v2_manifest_fingerprint,
)
from app.resolution.contracts import (
    IdentityGroupHypothesisStatus,
    IdentityValidationMode,
)
from app.resolution.fingerprints import (
    deferred_identity_work_unit_fingerprint,
    identity_conflict_fingerprint,
    identity_group_hypothesis_fingerprint,
    identity_resolution_result_fingerprint,
)


class G2V2ManifestValidationError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise G2V2ManifestValidationError(message)


def _pair(left, right):
    return (left, right) if left < right else (right, left)


def _unique_map(items, key, label):
    output = {}
    for item in items:
        identity = key(item)
        _require(identity not in output, f"duplicate {label}")
        output[identity] = item
    return output


def _validate_source_result(result):
    _require(
        result.resolution_fingerprint == identity_resolution_result_fingerprint(result),
        "source resolution fingerprint mismatch",
    )
    for group in result.accepted_groups:
        _require(
            group.hypothesis_fingerprint
            == identity_group_hypothesis_fingerprint(group),
            "source hypothesis fingerprint mismatch",
        )
    for conflict in result.conflicts:
        _require(
            conflict.fingerprint == identity_conflict_fingerprint(conflict),
            "source conflict fingerprint mismatch",
        )
    for deferred in result.deferred_work_units:
        _require(
            deferred.fingerprint == deferred_identity_work_unit_fingerprint(deferred),
            "source deferred fingerprint mismatch",
        )


def _validate_group(group, source, records_by_id, source_requests):
    _require(group.scan_id == source.scan_id, "G2-v2 group crosses scans")
    _require(group.status == source.status, "G2-v2 group status differs from source")
    _require(
        group.validation_mode == source.validation_mode,
        "G2-v2 validation mode differs from source",
    )
    _require(group.member_count >= 2, "G2-v2 accepted group is a singleton")
    _require(
        group.member_count == len(group.members),
        "G2-v2 member count is inconsistent",
    )
    member_ids = tuple(item.record_id for item in group.members)
    member_refs = tuple(item.stable_record_reference for item in group.members)
    _require(len(set(member_ids)) == len(member_ids), "duplicate G2-v2 group member")
    _require(len(set(member_refs)) == len(member_refs), "duplicate G2-v2 member reference")
    _require(
        tuple(item.member_order for item in group.members) == tuple(range(len(group.members))),
        "G2-v2 member order is not contiguous",
    )
    _require(
        tuple(sorted(zip(member_refs, member_ids))) == tuple(zip(member_refs, member_ids)),
        "G2-v2 member order is not canonical",
    )
    _require(set(member_ids) == set(source.member_record_ids), "G2-v2 membership differs from source")
    _require(
        {
            records_by_id[record_id].record_ref_key
            for record_id in source.member_record_ids
        } == set(source.member_record_references),
        "source hypothesis member reference differs from GF-1",
    )
    for member in group.members:
        record = records_by_id.get(member.record_id)
        _require(record is not None, "G2-v2 member is outside canonical records")
        _require(record.scan_id == group.scan_id, "G2-v2 member crosses scans")
        _require(
            record.record_ref_key == member.stable_record_reference,
            "G2-v2 member reference differs from GF-1",
        )
        _require(
            member.group_reference == group.group_reference,
            "G2-v2 member has another group owner",
        )

    evidence_by_pair = {}
    for evidence in group.internal_evidence:
        _require(
            evidence.group_reference == group.group_reference,
            "G2-v2 evidence has another group owner",
        )
        _require(
            evidence.record_id_1 < evidence.record_id_2,
            "G2-v2 evidence endpoints are not canonical",
        )
        pair = (evidence.record_id_1, evidence.record_id_2)
        _require(pair not in evidence_by_pair, "duplicate effective G2-v2 evidence pair")
        evidence_by_pair[pair] = evidence
        _require(set(pair) <= set(member_ids), "G2-v2 evidence pair is outside group")
        _require(
            evidence.stable_record_reference_1
            == records_by_id[evidence.record_id_1].record_ref_key
            and evidence.stable_record_reference_2
            == records_by_id[evidence.record_id_2].record_ref_key,
            "G2-v2 evidence references differ from GF-1",
        )
        _require(
            isinstance(evidence.edge_class, IdentityEdgeClass),
            "G2-v2 evidence class is invalid",
        )
        _require(
            isinstance(evidence.evidence_origin, G2V2EvidenceOrigin),
            "G2-v2 evidence origin is invalid",
        )
        _require(bool(evidence.evidence_fingerprint), "G2-v2 evidence lacks fingerprint")
        _require(evidence.required_for_validation, "materialized G2-v2 evidence is not required")

    coverage = group.validation_coverage
    possible = group.member_count * (group.member_count - 1) // 2
    class_counts = {
        edge_class: sum(item.edge_class == edge_class for item in group.internal_evidence)
        for edge_class in IdentityEdgeClass
    }
    expected_coverage = (
        group.validation_mode,
        group.member_count,
        possible,
        len(group.internal_evidence),
        sum(item.required_for_validation for item in group.internal_evidence),
        class_counts[IdentityEdgeClass.STRONG_SUPPORT],
        class_counts[IdentityEdgeClass.REVIEW_SUPPORT],
        class_counts[IdentityEdgeClass.NON_GROUPABLE],
        class_counts[IdentityEdgeClass.CANNOT_LINK],
        possible - len(group.internal_evidence),
        sum(item.evidence_origin == G2V2EvidenceOrigin.TARGETED_RESOLUTION_EVIDENCE
            for item in group.internal_evidence),
        sum(item.evidence_origin == G2V2EvidenceOrigin.PROPOSAL_EVIDENCE
            for item in group.internal_evidence),
    )
    actual_coverage = tuple(getattr(coverage, name) for name in (
        "validation_mode", "member_count", "possible_internal_pair_count",
        "evaluated_internal_pair_count", "required_validation_evidence_count",
        "strong_support_count", "review_support_count", "non_groupable_count",
        "cannot_link_count", "missing_nonrequired_pair_count",
        "targeted_evidence_count", "proposal_evidence_count",
    ))
    _require(actual_coverage == expected_coverage, "G2-v2 validation coverage is inconsistent")
    _require(coverage.cannot_link_count == 0, "accepted G2-v2 group contains CANNOT_LINK")
    summary = source.evidence_summary
    _require(
        (
            summary.member_count, summary.possible_pair_count,
            summary.evaluated_pair_count, summary.strong_support_count,
            summary.review_support_count, summary.non_groupable_count,
            summary.cannot_link_count, summary.missing_evidence_count,
        ) == (
            group.member_count, possible, coverage.evaluated_internal_pair_count,
            coverage.strong_support_count, coverage.review_support_count,
            coverage.non_groupable_count, coverage.cannot_link_count,
            coverage.missing_nonrequired_pair_count,
        ),
        "G2-v2 coverage differs from source GF-5 summary",
    )
    if group.validation_mode == IdentityValidationMode.COMPLETE_PAIRWISE:
        _require(
            coverage.evaluated_internal_pair_count == possible
            and coverage.missing_nonrequired_pair_count == 0,
            "false COMPLETE_PAIRWISE G2-v2 claim",
        )
    else:
        _require(
            coverage.evaluated_internal_pair_count < possible
            and coverage.missing_nonrequired_pair_count > 0,
            "PROGRESSIVE_TARGETED must explicitly preserve incomplete all-pairs coverage",
        )
    if group.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP:
        _require(
            group.validation_mode == IdentityValidationMode.COMPLETE_PAIRWISE
            and coverage.strong_support_count == possible,
            "GF-5-v1 likely group is not complete all-strong evidence",
        )

    internal_requests = {
        request.request_fingerprint: request
        for request in source_requests
        if {request.record_id_1, request.record_id_2} <= set(member_ids)
    }
    evidence_refs = {
        reference
        for item in group.internal_evidence
        for reference in (
            item.source_evidence_reference,
            item.evidence_fingerprint,
            *item.supplemental_source_references,
        )
    }
    for fingerprint in internal_requests:
        _require(
            fingerprint in evidence_refs,
            "accepted G2-v2 group is missing required targeted evidence",
        )

    _require(
        group.source_hypothesis_fingerprint == source.hypothesis_fingerprint,
        "G2-v2 source hypothesis fingerprint mismatch",
    )
    _require(
        group.group_evidence_summary == source.evidence_summary
        and group.bridge_risk_summary == source.bridge_risk_summary
        and group.genericity_risk_summary == source.genericity_risk_summary
        and group.missing_evidence_summary == source.missing_evidence_summary,
        "G2-v2 group summaries differ from source",
    )
    _require(
        group.group_fingerprint == g2_v2_group_fingerprint(group),
        "G2-v2 group fingerprint mismatch",
    )


def validate_g2_v2_manifest(
    manifest,
    persisted_resolution_result,
    canonical_records,
    proposal_evidence_edges,
    targeted_resolution_evidence,
    source_provenance,
) -> None:
    """Reject semantic drift between a pure v2 manifest and its GF-5C source."""
    _validate_source_result(persisted_resolution_result)
    records = tuple(canonical_records)
    records_by_id = _unique_map(records, lambda item: item.record_id, "canonical record ID")
    records_by_ref = _unique_map(records, lambda item: item.record_ref_key, "canonical record reference")
    _require(
        all(item.scan_id == persisted_resolution_result.scan_id for item in records),
        "canonical record crosses source scan",
    )
    _require(source_provenance.source_resolution_status == "COMPLETED", "source resolution is not completed")
    _require(
        source_provenance.scan_id == persisted_resolution_result.scan_id
        and manifest.scan_id == persisted_resolution_result.scan_id,
        "source resolution scan mismatch",
    )
    _require(
        source_provenance.source_resolution_fingerprint
        == persisted_resolution_result.resolution_fingerprint
        == manifest.source_resolution_fingerprint,
        "source resolution fingerprint mismatch",
    )
    _require(
        source_provenance.source_resolver_algorithm_version
        == persisted_resolution_result.resolver_algorithm_version,
        "source resolver algorithm mismatch",
    )
    _require(
        (
            manifest.source_resolution_run_id,
            manifest.source_discovery_run_id,
            manifest.source_evidence_run_id,
        ) == (
            source_provenance.source_resolution_run_id,
            source_provenance.source_discovery_run_id,
            source_provenance.source_evidence_run_id,
        ),
        "source resolution-run provenance mismatch",
    )
    _require(
        manifest.snapshot_contract_version == G2_V2_SNAPSHOT_CONTRACT_VERSION
        and manifest.adapter_algorithm_version == G2_V2_ADAPTER_ALGORITHM_VERSION,
        "G2-v2 contract or adapter version mismatch",
    )

    proposal_by_pair = _unique_map(
        proposal_evidence_edges,
        lambda item: _pair(item.record_id_1, item.record_id_2),
        "GF-4 proposal evidence pair",
    )
    targeted_by_pair = _unique_map(
        targeted_resolution_evidence,
        lambda item: _pair(item.request.record_id_1, item.request.record_id_2),
        "GF-5 targeted evidence pair",
    )
    for item in proposal_by_pair.values():
        _require(
            item.scan_id == manifest.scan_id
            and item.discovery_run_id == manifest.source_discovery_run_id
            and item.evidence_run_id == manifest.source_evidence_run_id,
            "GF-4 proposal evidence provenance mismatch",
        )
        _require(item.record_id_1 < item.record_id_2, "GF-4 evidence endpoints are not canonical")
        _require(
            item.record_id_1 in records_by_id and item.record_id_2 in records_by_id,
            "GF-4 proposal evidence is outside canonical records",
        )
    source_targeted = {
        item.request.request_fingerprint: item
        for item in persisted_resolution_result.targeted_evidence_results
    }
    supplied_targeted = {
        item.request.request_fingerprint: item for item in targeted_by_pair.values()
    }
    _require(
        supplied_targeted == source_targeted,
        "targeted evidence differs from persisted GF-5C results",
    )
    for item in targeted_by_pair.values():
        _require(item.request.scan_id == manifest.scan_id, "targeted evidence crosses scans")
        _require(
            item.request.record_id_1 < item.request.record_id_2,
            "targeted evidence endpoints are not canonical",
        )
        _require(
            item.request.record_id_1 in records_by_id
            and item.request.record_id_2 in records_by_id,
            "targeted evidence is outside canonical records",
        )
        _require(
            item.request.record_reference_1
            == records_by_id[item.request.record_id_1].record_ref_key
            and item.request.record_reference_2
            == records_by_id[item.request.record_id_2].record_ref_key,
            "targeted evidence reference differs from GF-1",
        )

    source_groups = _unique_map(
        persisted_resolution_result.accepted_groups,
        lambda item: item.hypothesis_fingerprint,
        "source accepted hypothesis",
    )
    groups = _unique_map(
        manifest.groups, lambda item: item.source_hypothesis_fingerprint,
        "G2-v2 source hypothesis",
    )
    _require(set(groups) == set(source_groups), "G2-v2 accepted groups differ from source")
    seen_members = set()
    for fingerprint in sorted(groups):
        group = groups[fingerprint]
        _validate_group(
            group, source_groups[fingerprint], records_by_id,
            persisted_resolution_result.targeted_evidence_requests,
        )
        current = {item.record_id for item in group.members}
        _require(not (seen_members & current), "record appears in two accepted G2-v2 groups")
        seen_members.update(current)

    _require(len(manifest.conflicts) == len(persisted_resolution_result.conflicts), "G2-v2 conflict count differs from source")
    source_conflicts = {item.fingerprint: item for item in persisted_resolution_result.conflicts}
    for conflict in manifest.conflicts:
        source = source_conflicts.get(conflict.source_conflict_fingerprint)
        _require(source is not None, "G2-v2 conflict lacks source")
        _require(
            all(
                record_id in records_by_id
                and records_by_id[record_id].record_ref_key == record_ref
                for record_id, record_ref in zip(
                    conflict.involved_record_ids,
                    conflict.involved_record_references,
                )
            ),
            "G2-v2 conflict member differs from GF-1",
        )
        _require(
            (
                conflict.scan_id, conflict.conflict_type,
                conflict.involved_record_ids, conflict.involved_record_references,
                conflict.protected_evidence_references,
                conflict.source_neighborhood_references, conflict.summary,
            ) == (
                source.scan_id, source.conflict_type, source.involved_record_ids,
                source.involved_record_references,
                source.protected_evidence_references,
                source.source_neighborhood_references, source.summary,
            ),
            "G2-v2 conflict differs from source",
        )
        _require(conflict.conflict_fingerprint == g2_v2_conflict_fingerprint(conflict), "G2-v2 conflict fingerprint mismatch")

    _require(len(manifest.deferred_work_units) == len(persisted_resolution_result.deferred_work_units), "G2-v2 deferred count differs from source")
    source_deferred = {item.fingerprint: item for item in persisted_resolution_result.deferred_work_units}
    for deferred in manifest.deferred_work_units:
        source = source_deferred.get(deferred.source_deferred_fingerprint)
        _require(source is not None, "G2-v2 deferred unit lacks source")
        _require(
            all(
                record_id in records_by_id
                and records_by_id[record_id].record_ref_key == record_ref
                for record_id, record_ref in zip(
                    deferred.record_ids, deferred.record_references
                )
            ),
            "G2-v2 deferred member differs from GF-1",
        )
        _require(
            (
                deferred.scan_id, deferred.reason, deferred.record_ids,
                deferred.record_references, deferred.unfinished_evidence_summary,
                deferred.source_neighborhood_references,
            ) == (
                source.scan_id, source.reason, source.record_ids,
                source.record_references, source.unfinished_evidence_summary,
                source.source_neighborhood_references,
            ),
            "G2-v2 deferred unit differs from source",
        )
        _require(deferred.deferred_fingerprint == g2_v2_deferred_fingerprint(deferred), "G2-v2 deferred fingerprint mismatch")

    expected_unassigned = tuple(sorted(zip(
        persisted_resolution_result.unassigned_record_references,
        persisted_resolution_result.unassigned_record_ids,
    )))
    _require(
        tuple(zip(manifest.unassigned_record_references, manifest.unassigned_record_ids))
        == expected_unassigned,
        "G2-v2 unassigned records differ from source",
    )
    _require(
        all(record_id in records_by_id for record_id in manifest.unassigned_record_ids)
        and all(reference in records_by_ref for reference in manifest.unassigned_record_references),
        "G2-v2 unassigned record is outside canonical records",
    )
    _require(
        all(
            records_by_id[record_id].record_ref_key == reference
            for record_id, reference in zip(
                manifest.unassigned_record_ids,
                manifest.unassigned_record_references,
            )
        ),
        "G2-v2 unassigned reference differs from GF-1",
    )
    expected_counts = (
        len(records), len(manifest.groups),
        sum(item.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP for item in manifest.groups),
        sum(item.status == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW for item in manifest.groups),
        len(manifest.conflicts), len(manifest.deferred_work_units),
        len(manifest.unassigned_record_ids),
    )
    actual_counts = (
        manifest.canonical_record_count, manifest.accepted_group_count,
        manifest.likely_group_count, manifest.review_group_count,
        manifest.conflict_count, manifest.deferred_count,
        manifest.unassigned_record_count,
    )
    _require(actual_counts == expected_counts, "G2-v2 manifest counts do not reconcile")
    _require(
        manifest.manifest_fingerprint == g2_v2_manifest_fingerprint(manifest),
        "G2-v2 manifest fingerprint mismatch",
    )
