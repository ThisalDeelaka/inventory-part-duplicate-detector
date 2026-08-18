"""Canonical SHA-256 identities for pure G2-v2 manifests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum

from app.g2_v2.contracts import G2_V2_SNAPSHOT_CONTRACT_VERSION


def _canonical(value):
    if dataclasses.is_dataclass(value):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def fingerprint_g2_v2_payload(kind: str, value) -> str:
    payload = {
        "snapshot_contract_version": G2_V2_SNAPSHOT_CONTRACT_VERSION,
        "kind": kind,
        "value": _canonical(value),
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def g2_v2_group_fingerprint(group) -> str:
    return fingerprint_g2_v2_payload("g2-v2-group", {
        "group_reference": group.group_reference,
        "status": group.status,
        "validation_mode": group.validation_mode,
        "members": tuple(item.stable_record_reference for item in group.members),
        "internal_evidence": tuple({
            "pair": (
                item.stable_record_reference_1,
                item.stable_record_reference_2,
            ),
            "edge_class": item.edge_class,
            "evidence_origin": item.evidence_origin,
            "source_evidence_reference": item.source_evidence_reference,
            "supplemental_source_references": item.supplemental_source_references,
            "reason_codes": item.reason_codes,
            "evidence_summary": item.evidence_summary,
            "evaluator_version": item.evaluator_version,
            "evidence_fingerprint": item.evidence_fingerprint,
            "required_for_validation": item.required_for_validation,
        } for item in group.internal_evidence),
        "validation_coverage": group.validation_coverage,
        "group_evidence_summary": group.group_evidence_summary,
        "bridge_risk_summary": group.bridge_risk_summary,
        "genericity_risk_summary": group.genericity_risk_summary,
        "missing_evidence_summary": group.missing_evidence_summary,
        "source_hypothesis_fingerprint": group.source_hypothesis_fingerprint,
        "source_neighborhood_references": group.source_neighborhood_references,
    })


def g2_v2_conflict_fingerprint(conflict) -> str:
    return fingerprint_g2_v2_payload("g2-v2-conflict", {
        "conflict_reference": conflict.conflict_reference,
        "conflict_type": conflict.conflict_type,
        "involved_record_references": conflict.involved_record_references,
        "protected_evidence_references": conflict.protected_evidence_references,
        "source_neighborhood_references": conflict.source_neighborhood_references,
        "summary": conflict.summary,
        "source_conflict_fingerprint": conflict.source_conflict_fingerprint,
    })


def g2_v2_deferred_fingerprint(deferred) -> str:
    return fingerprint_g2_v2_payload("g2-v2-deferred", {
        "deferred_reference": deferred.deferred_reference,
        "reason": deferred.reason,
        "record_references": deferred.record_references,
        "unfinished_evidence_summary": deferred.unfinished_evidence_summary,
        "source_neighborhood_references": deferred.source_neighborhood_references,
        "source_deferred_fingerprint": deferred.source_deferred_fingerprint,
    })


def g2_v2_manifest_fingerprint(manifest) -> str:
    return fingerprint_g2_v2_payload("g2-v2-manifest", {
        "source_resolution_fingerprint": manifest.source_resolution_fingerprint,
        "adapter_algorithm_version": manifest.adapter_algorithm_version,
        "adapter_configuration_fingerprint": manifest.adapter_configuration_fingerprint,
        "group_fingerprints": tuple(item.group_fingerprint for item in manifest.groups),
        "conflict_fingerprints": tuple(
            item.conflict_fingerprint for item in manifest.conflicts
        ),
        "deferred_fingerprints": tuple(
            item.deferred_fingerprint for item in manifest.deferred_work_units
        ),
        "unassigned_record_references": manifest.unassigned_record_references,
        "counts": {
            "canonical_record_count": manifest.canonical_record_count,
            "accepted_group_count": manifest.accepted_group_count,
            "likely_group_count": manifest.likely_group_count,
            "review_group_count": manifest.review_group_count,
            "conflict_count": manifest.conflict_count,
            "deferred_count": manifest.deferred_count,
            "unassigned_record_count": manifest.unassigned_record_count,
        },
    })
