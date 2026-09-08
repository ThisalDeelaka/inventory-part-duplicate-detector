"""Pure deterministic GF-5C result to G2-v2 snapshot-manifest adapter."""

from __future__ import annotations

from dataclasses import replace

from app.g2_v2.contracts import (
    G2_V2_ADAPTER_ALGORITHM_VERSION,
    G2_V2_SNAPSHOT_CONTRACT_VERSION,
    G2V2AdapterConfiguration,
    G2V2ConflictSnapshot,
    G2V2DeferredSnapshot,
    G2V2EvidenceOrigin,
    G2V2GroupMember,
    G2V2GroupSnapshot,
    G2V2InternalEvidence,
    G2V2SnapshotManifest,
    G2V2SourceProvenance,
    G2V2ValidationCoverage,
)
from app.g2_v2.fingerprints import (
    fingerprint_g2_v2_payload,
    g2_v2_conflict_fingerprint,
    g2_v2_deferred_fingerprint,
    g2_v2_group_fingerprint,
    g2_v2_manifest_fingerprint,
)
from app.resolution.contracts import (
    IdentityGroupHypothesisStatus,
    IdentityValidationMode,
)


def _pair(left: int, right: int) -> tuple[int, int]:
    return (left, right) if left < right else (right, left)


def _proposal_evidence(item, group_reference, references, required):
    return G2V2InternalEvidence(
        group_reference=group_reference,
        record_id_1=item.record_id_1,
        record_id_2=item.record_id_2,
        stable_record_reference_1=references[item.record_id_1],
        stable_record_reference_2=references[item.record_id_2],
        edge_class=item.edge_class,
        evidence_origin=G2V2EvidenceOrigin.PROPOSAL_EVIDENCE,
        source_evidence_reference=item.evidence_fingerprint,
        supplemental_source_references=(),
        reason_codes=tuple(sorted(item.classification_reason_codes)),
        evidence_summary=item.rule_decision,
        evaluator_version=item.evaluation_algorithm_version,
        evidence_fingerprint=item.evidence_fingerprint,
        required_for_validation=required,
    )


def _targeted_evidence(item, group_reference, required):
    request = item.request
    return G2V2InternalEvidence(
        group_reference=group_reference,
        record_id_1=request.record_id_1,
        record_id_2=request.record_id_2,
        stable_record_reference_1=request.record_reference_1,
        stable_record_reference_2=request.record_reference_2,
        edge_class=item.edge_class,
        evidence_origin=G2V2EvidenceOrigin.TARGETED_RESOLUTION_EVIDENCE,
        source_evidence_reference=item.evidence_fingerprint,
        supplemental_source_references=(request.request_fingerprint,),
        reason_codes=tuple(sorted(item.reason_codes)),
        evidence_summary=item.evidence_summary,
        evaluator_version=item.evaluator_version,
        evidence_fingerprint=item.evidence_fingerprint,
        required_for_validation=required,
    )


def _unique_by_pair(items, label, pair_getter):
    output = {}
    for item in items:
        pair = pair_getter(item)
        if pair in output:
            raise ValueError(f"duplicate {label} for canonical pair")
        output[pair] = item
    return output


def _effective_internal_evidence(
    group, group_reference, references, proposal_by_pair, targeted_by_pair,
    configuration,
):
    members = set(group.member_record_ids)
    pairs = sorted(
        pair for pair in set(proposal_by_pair) | set(targeted_by_pair)
        if set(pair) <= members
    )
    output = []
    for pair in pairs:
        proposal = proposal_by_pair.get(pair)
        targeted = targeted_by_pair.get(pair)
        if proposal is not None and targeted is not None:
            if (
                proposal.edge_class != targeted.edge_class
                or proposal.evaluation_algorithm_version != targeted.evaluator_version
                or proposal.evidence_fingerprint != targeted.evidence_fingerprint
            ):
                raise ValueError(
                    "proposal and targeted evidence disagree for one canonical pair"
                )
            if configuration.prefer_proposal_evidence:
                evidence = _proposal_evidence(
                    proposal, group_reference, references, True
                )
                evidence = replace(
                    evidence,
                    supplemental_source_references=tuple(sorted({
                        targeted.evidence_fingerprint,
                        targeted.request.request_fingerprint,
                    })),
                )
            else:
                evidence = _targeted_evidence(targeted, group_reference, True)
                evidence = replace(
                    evidence,
                    supplemental_source_references=tuple(sorted({
                        proposal.evidence_fingerprint,
                        targeted.request.request_fingerprint,
                    })),
                )
        elif proposal is not None:
            evidence = _proposal_evidence(proposal, group_reference, references, True)
        else:
            evidence = _targeted_evidence(targeted, group_reference, True)
        output.append(evidence)
    return tuple(sorted(output, key=lambda item: (
        item.stable_record_reference_1,
        item.stable_record_reference_2,
        item.evidence_origin.value,
    )))


def _group_snapshot(
    group, records_by_id, proposal_by_pair, targeted_by_pair, configuration,
):
    group_reference = "g2v2-group-" + group.hypothesis_fingerprint
    members = tuple(G2V2GroupMember(
        group_reference=group_reference,
        record_id=record_id,
        stable_record_reference=record_ref,
        member_order=index,
    ) for index, (record_ref, record_id) in enumerate(sorted(
        (records_by_id[record_id].record_ref_key, record_id)
        for record_id in group.member_record_ids
    )))
    references = {
        record_id: records_by_id[record_id].record_ref_key
        for record_id in group.member_record_ids
    }
    evidence = _effective_internal_evidence(
        group, group_reference, references, proposal_by_pair, targeted_by_pair,
        configuration,
    )
    possible = len(members) * (len(members) - 1) // 2
    coverage = G2V2ValidationCoverage(
        validation_mode=group.validation_mode,
        member_count=len(members),
        possible_internal_pair_count=possible,
        evaluated_internal_pair_count=len(evidence),
        required_validation_evidence_count=sum(
            item.required_for_validation for item in evidence
        ),
        strong_support_count=sum(
            item.edge_class.value == "STRONG_SUPPORT" for item in evidence
        ),
        review_support_count=sum(
            item.edge_class.value == "REVIEW_SUPPORT" for item in evidence
        ),
        non_groupable_count=sum(
            item.edge_class.value == "NON_GROUPABLE" for item in evidence
        ),
        cannot_link_count=sum(
            item.edge_class.value == "CANNOT_LINK" for item in evidence
        ),
        missing_nonrequired_pair_count=possible - len(evidence),
        targeted_evidence_count=sum(
            item.evidence_origin == G2V2EvidenceOrigin.TARGETED_RESOLUTION_EVIDENCE
            for item in evidence
        ),
        proposal_evidence_count=sum(
            item.evidence_origin == G2V2EvidenceOrigin.PROPOSAL_EVIDENCE
            for item in evidence
        ),
    )
    snapshot = G2V2GroupSnapshot(
        group_reference=group_reference,
        scan_id=group.scan_id,
        status=group.status,
        validation_mode=group.validation_mode,
        member_count=len(members),
        members=members,
        internal_evidence=evidence,
        validation_coverage=coverage,
        group_evidence_summary=group.evidence_summary,
        bridge_risk_summary=group.bridge_risk_summary,
        genericity_risk_summary=group.genericity_risk_summary,
        missing_evidence_summary=group.missing_evidence_summary,
        source_hypothesis_fingerprint=group.hypothesis_fingerprint,
        source_neighborhood_references=tuple(sorted(
            group.source_neighborhood_references
        )),
        group_fingerprint="",
    )
    return replace(snapshot, group_fingerprint=g2_v2_group_fingerprint(snapshot))


def build_g2_v2_manifest(
    persisted_resolution_result,
    canonical_records,
    proposal_evidence_edges,
    targeted_resolution_evidence,
    source_provenance: G2V2SourceProvenance,
    configuration: G2V2AdapterConfiguration = G2V2AdapterConfiguration(),
) -> G2V2SnapshotManifest:
    """Map authoritative GF-1/GF-4/GF-5C inputs without I/O or side effects."""
    records = tuple(canonical_records)
    proposal_evidence = tuple(proposal_evidence_edges)
    targeted_evidence = tuple(targeted_resolution_evidence)
    records_by_id = {item.record_id: item for item in records}
    if len(records_by_id) != len(records):
        raise ValueError("canonical record IDs must be unique")
    proposal_by_pair = _unique_by_pair(
        proposal_evidence, "proposal evidence",
        lambda item: _pair(item.record_id_1, item.record_id_2),
    )
    targeted_by_pair = _unique_by_pair(
        targeted_evidence, "targeted evidence",
        lambda item: _pair(item.request.record_id_1, item.request.record_id_2),
    )
    groups = tuple(sorted((
        _group_snapshot(
            group, records_by_id, proposal_by_pair, targeted_by_pair, configuration
        ) for group in persisted_resolution_result.accepted_groups
    ), key=lambda item: item.group_reference))
    conflicts = []
    for item in persisted_resolution_result.conflicts:
        row = G2V2ConflictSnapshot(
            conflict_reference="g2v2-conflict-" + item.fingerprint,
            scan_id=item.scan_id,
            conflict_type=item.conflict_type,
            involved_record_ids=item.involved_record_ids,
            involved_record_references=item.involved_record_references,
            protected_evidence_references=item.protected_evidence_references,
            source_neighborhood_references=item.source_neighborhood_references,
            summary=item.summary,
            source_conflict_fingerprint=item.fingerprint,
            conflict_fingerprint="",
        )
        conflicts.append(replace(
            row, conflict_fingerprint=g2_v2_conflict_fingerprint(row)
        ))
    deferred = []
    for item in persisted_resolution_result.deferred_work_units:
        row = G2V2DeferredSnapshot(
            deferred_reference="g2v2-deferred-" + item.fingerprint,
            scan_id=item.scan_id,
            reason=item.reason,
            record_ids=item.record_ids,
            record_references=item.record_references,
            unfinished_evidence_summary=item.unfinished_evidence_summary,
            source_neighborhood_references=item.source_neighborhood_references,
            source_deferred_fingerprint=item.fingerprint,
            deferred_fingerprint="",
        )
        deferred.append(replace(
            row, deferred_fingerprint=g2_v2_deferred_fingerprint(row)
        ))
    unassigned = tuple(sorted(zip(
        persisted_resolution_result.unassigned_record_references,
        persisted_resolution_result.unassigned_record_ids,
    )))
    configuration_fingerprint = fingerprint_g2_v2_payload(
        "g2-v2-adapter-configuration", configuration
    )
    manifest = G2V2SnapshotManifest(
        scan_id=persisted_resolution_result.scan_id,
        source_resolution_run_id=source_provenance.source_resolution_run_id,
        source_discovery_run_id=source_provenance.source_discovery_run_id,
        source_evidence_run_id=source_provenance.source_evidence_run_id,
        snapshot_contract_version=G2_V2_SNAPSHOT_CONTRACT_VERSION,
        adapter_algorithm_version=G2_V2_ADAPTER_ALGORITHM_VERSION,
        adapter_configuration_fingerprint=configuration_fingerprint,
        source_resolution_fingerprint=source_provenance.source_resolution_fingerprint,
        groups=groups,
        conflicts=tuple(sorted(conflicts, key=lambda item: item.conflict_reference)),
        deferred_work_units=tuple(sorted(
            deferred, key=lambda item: item.deferred_reference
        )),
        unassigned_record_ids=tuple(item[1] for item in unassigned),
        unassigned_record_references=tuple(item[0] for item in unassigned),
        canonical_record_count=len(records),
        accepted_group_count=len(groups),
        likely_group_count=sum(
            item.status == IdentityGroupHypothesisStatus.LIKELY_DUPLICATE_GROUP
            for item in groups
        ),
        review_group_count=sum(
            item.status
            == IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
            for item in groups
        ),
        conflict_count=len(conflicts),
        deferred_count=len(deferred),
        unassigned_record_count=len(unassigned),
        manifest_fingerprint="",
    )
    manifest = replace(
        manifest, manifest_fingerprint=g2_v2_manifest_fingerprint(manifest)
    )
    from app.g2_v2.validation import validate_g2_v2_manifest

    validate_g2_v2_manifest(
        manifest,
        persisted_resolution_result,
        records,
        proposal_evidence,
        targeted_evidence,
        source_provenance,
    )
    return manifest
