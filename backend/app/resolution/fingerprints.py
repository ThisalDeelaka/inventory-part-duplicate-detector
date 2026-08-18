"""Canonical SHA-256 identities for GF-5A resolver artifacts."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum

from app.resolution.contracts import RESOLVER_CONTRACT_VERSION


def _canonical(value):
    if dataclasses.is_dataclass(value):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if field.name not in {
                "request_fingerprint",
                "hypothesis_fingerprint",
                "fingerprint",
                "resolution_fingerprint",
            }
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list, set, frozenset)):
        normalized = [_canonical(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def fingerprint_payload(kind: str, value) -> str:
    payload = {
        "contract_version": RESOLVER_CONTRACT_VERSION,
        "kind": kind,
        "value": _canonical(value),
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def targeted_evidence_request_fingerprint(request) -> str:
    return fingerprint_payload("targeted-evidence-request", {
        "scan_id": request.scan_id,
        "record_references": (
            request.record_reference_1, request.record_reference_2
        ),
        "reason": request.reason,
        "requesting_work_unit_reference": request.requesting_work_unit_reference,
    })


def identity_group_hypothesis_fingerprint(hypothesis) -> str:
    record_reference_by_id = dict(zip(
        hypothesis.member_record_ids, hypothesis.member_record_references
    ))

    def references(record_ids):
        return tuple(record_reference_by_id[item] for item in record_ids)

    def reference_pairs(pairs):
        return tuple(
            tuple(sorted((record_reference_by_id[left], record_reference_by_id[right])))
            for left, right in pairs
        )

    bridge = hypothesis.bridge_risk_summary
    genericity = hypothesis.genericity_risk_summary
    missing = hypothesis.missing_evidence_summary
    return fingerprint_payload("identity-group-hypothesis", {
        "hypothesis_id": hypothesis.hypothesis_id,
        "scan_id": hypothesis.scan_id,
        "member_record_references": hypothesis.member_record_references,
        "status": hypothesis.status,
        "validation_mode": hypothesis.validation_mode,
        "evidence_summary": hypothesis.evidence_summary,
        "bridge_risk_summary": {
            "articulation_record_references": references(bridge.articulation_record_ids),
            "single_edge_branch_record_references": references(
                bridge.single_edge_branch_record_ids
            ),
            "neutral_cross_branch_reference_pairs": reference_pairs(
                bridge.neutral_cross_branch_pairs
            ),
            "missing_cross_branch_reference_pairs": reference_pairs(
                bridge.missing_cross_branch_pairs
            ),
            "generic_hub_record_references": references(bridge.generic_hub_record_ids),
            "competing_partition_evidence": bridge.competing_partition_evidence,
            "unresolved": bridge.unresolved,
        },
        "genericity_risk_summary": {
            "generic_description_burden": genericity.generic_description_burden,
            "review_only_support": genericity.review_only_support,
            "hub_dependency_record_references": references(
                genericity.hub_dependency_record_ids
            ),
            "insufficient_independent_identity_evidence": (
                genericity.insufficient_independent_identity_evidence
            ),
        },
        "missing_evidence_summary": {
            "missing_reference_pairs": reference_pairs(missing.missing_pairs),
            "incomplete_reason_codes": missing.incomplete_reason_codes,
            "discovery_truncation_affects_membership": (
                missing.discovery_truncation_affects_membership
            ),
            "unresolved_ownership_ambiguity": missing.unresolved_ownership_ambiguity,
        },
        "source_neighborhood_references": hypothesis.source_neighborhood_references,
    })


def identity_conflict_fingerprint(conflict) -> str:
    return fingerprint_payload("identity-conflict", {
        "conflict_id": conflict.conflict_id,
        "scan_id": conflict.scan_id,
        "involved_record_references": conflict.involved_record_references,
        "conflict_type": conflict.conflict_type,
        "protected_evidence_references": conflict.protected_evidence_references,
        "source_neighborhood_references": conflict.source_neighborhood_references,
        "summary": conflict.summary,
    })


def deferred_identity_work_unit_fingerprint(work_unit) -> str:
    return fingerprint_payload("deferred-identity-work-unit", {
        "deferred_id": work_unit.deferred_id,
        "scan_id": work_unit.scan_id,
        "record_references": work_unit.record_references,
        "reason": work_unit.reason,
        "unfinished_evidence_summary": work_unit.unfinished_evidence_summary,
        "source_neighborhood_references": work_unit.source_neighborhood_references,
    })


def identity_resolution_result_fingerprint(result) -> str:
    return fingerprint_payload("identity-resolution-result", {
        "scan_id": result.scan_id,
        "accepted_group_fingerprints": tuple(
            item.hypothesis_fingerprint for item in result.accepted_groups
        ),
        "conflict_fingerprints": tuple(item.fingerprint for item in result.conflicts),
        "deferred_fingerprints": tuple(
            item.fingerprint for item in result.deferred_work_units
        ),
        "unassigned_record_references": result.unassigned_record_references,
        "targeted_request_fingerprints": tuple(
            item.request_fingerprint for item in result.targeted_evidence_requests
        ),
        "targeted_result_evidence_fingerprints": tuple(
            item.evidence_fingerprint for item in result.targeted_evidence_results
        ),
        "metrics": result.metrics,
        "resolver_algorithm_version": result.resolver_algorithm_version,
    })
