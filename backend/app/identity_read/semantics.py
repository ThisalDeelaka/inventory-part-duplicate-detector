"""Stable-reference semantic payloads shared by GF-9A adapters and validators."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum


def _stable(value, references_by_id, field_name=""):
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _stable(
                getattr(value, field.name), references_by_id, field.name
            )
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): _stable(item, references_by_id, str(key))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        if field_name.endswith("record_ids"):
            return tuple(references_by_id.get(item, item) for item in value)
        if field_name.endswith("pairs"):
            return tuple(
                tuple(references_by_id.get(part, part) for part in item)
                for item in value
            )
        return tuple(_stable(item, references_by_id, field_name) for item in value)
    if field_name in {"record_id", "record_id_1", "record_id_2"}:
        return references_by_id.get(value, value)
    return value


def group_semantic_payload(group):
    references_by_id = {
        member.record_id: member.stable_record_reference for member in group.members
    }
    evidence = tuple(
        _stable(item, references_by_id)
        for item in group.internal_evidence
    )
    return {
        "key": group.versioned_group_key,
        "status": group.status,
        "members": tuple(
            (member.stable_record_reference, member.source_row_index, member.member_order)
            for member in group.members
        ),
        "validation_mode": group.validation_mode,
        "validation_coverage": group.validation_coverage,
        "group_evidence_summary": _stable(group.group_evidence_summary, references_by_id),
        "bridge_risk_summary": _stable(group.bridge_risk_summary, references_by_id),
        "genericity_risk_summary": _stable(group.genericity_risk_summary, references_by_id),
        "missing_evidence_summary": _stable(group.missing_evidence_summary, references_by_id),
        "internal_evidence": evidence,
        "source_group_fingerprint": group.source_group_fingerprint,
    }


def conflict_semantic_payload(conflict):
    return {
        "scan_id": conflict.scan_id,
        "conflict_reference": conflict.conflict_reference,
        "conflict_type": conflict.conflict_type,
        "involved_record_references": conflict.involved_record_references,
        "protected_evidence_references": conflict.protected_evidence_references,
        "source_neighborhood_references": conflict.source_neighborhood_references,
        "summary": conflict.summary,
        "source_conflict_fingerprint": conflict.source_conflict_fingerprint,
    }


def deferred_semantic_payload(work):
    return {
        "scan_id": work.scan_id,
        "deferred_reference": work.deferred_reference,
        "reason": work.reason,
        "record_references": work.record_references,
        "unfinished_evidence_summary": work.unfinished_evidence_summary,
        "source_neighborhood_references": work.source_neighborhood_references,
        "source_deferred_fingerprint": work.source_deferred_fingerprint,
    }
