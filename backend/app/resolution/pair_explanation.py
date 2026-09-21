"""Versioned, non-authoritative projections of persisted deterministic evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.engine.identity_edge import IdentityEdgeClass
from app.resolution.contracts import (
    TARGETED_EVIDENCE_CONTRACT_VERSION,
    TargetedEvidenceResult,
)


PAIR_EXPLANATION_CONTRACT_VERSION = "deterministic-pair-explanation-v1"


class PairExplanationAvailability(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL_LEGACY = "PARTIAL_LEGACY"


@dataclass(frozen=True)
class DeterministicPairExplanationV1:
    record_id_1: int
    record_id_2: int
    record_reference_1: str
    record_reference_2: str
    deterministic_score: float | None
    signed_relationship: IdentityEdgeClass
    component_scores: dict[str, float]
    classification_reason_codes: tuple[str, ...]
    rule_decision: str
    rejection_reason: str
    protected_conflicts: tuple[dict[str, Any], ...]
    generic_evidence: dict[str, Any]
    technical_evidence: dict[str, Any]
    uom_context: dict[str, Any]
    evaluation_context: dict[str, Any]
    evaluator_version: str
    source_evidence_fingerprint: str
    source_kind: str
    source_request_fingerprint: str | None
    availability: PairExplanationAvailability
    missing_fields: tuple[str, ...]
    contract_version: str
    explanation_fingerprint: str


_RICH_FIELDS = (
    "component_scores",
    "rejection_reason",
    "protected_conflicts",
    "generic_evidence",
    "technical_evidence",
    "uom_context",
    "evaluation_context",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _load_json(value: str, label: str, expected_type):
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(loaded, expected_type):
        raise ValueError(f"{label} has the wrong JSON shape")
    return loaded


def explanation_evidence_from_evaluated(evaluated) -> dict[str, Any]:
    """Copy existing evaluator facts without deriving new explanation semantics."""
    return {
        "component_scores": _load_json(
            evaluated.component_scores_json, "component_scores_json", dict
        ),
        "rule_decision": str(evaluated.rule_decision or ""),
        "rejection_reason": str(evaluated.rejection_reason or ""),
        "protected_conflicts": _load_json(
            evaluated.protected_conflicts_json, "protected_conflicts_json", list
        ),
        "generic_evidence": _load_json(
            evaluated.generic_evidence_json, "generic_evidence_json", dict
        ),
        "technical_evidence": _load_json(
            evaluated.technical_evidence_json, "technical_evidence_json", dict
        ),
        "uom_context": _load_json(
            evaluated.uom_context_json, "uom_context_json", dict
        ),
        "evaluation_context": _load_json(
            evaluated.evaluation_context_json, "evaluation_context_json", dict
        ),
    }


def pair_explanation_fingerprint(
    *,
    record_reference_1: str,
    record_reference_2: str,
    deterministic_score: float | None,
    signed_relationship: IdentityEdgeClass,
    classification_reason_codes: tuple[str, ...],
    evaluator_version: str,
    source_evidence_fingerprint: str,
    source_kind: str,
    source_request_fingerprint: str | None,
    explanation_evidence: dict[str, Any] | None,
    availability: PairExplanationAvailability,
) -> str:
    payload = {
        "contract_version": PAIR_EXPLANATION_CONTRACT_VERSION,
        "record_references": sorted((record_reference_1, record_reference_2)),
        "deterministic_score": deterministic_score,
        "signed_relationship": signed_relationship.value,
        "classification_reason_codes": sorted(classification_reason_codes),
        "evaluator_version": evaluator_version,
        "source_evidence_fingerprint": source_evidence_fingerprint,
        "source_kind": source_kind,
        "source_request_fingerprint": source_request_fingerprint,
        "availability": availability.value,
        "explanation_evidence": explanation_evidence,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def serialized_targeted_explanation(evaluated, request) -> tuple[str, str]:
    evidence = explanation_evidence_from_evaluated(evaluated)
    fingerprint = pair_explanation_fingerprint(
        record_reference_1=request.record_reference_1,
        record_reference_2=request.record_reference_2,
        deterministic_score=evaluated.deterministic_score,
        signed_relationship=evaluated.edge_class,
        classification_reason_codes=tuple(evaluated.classification_reason_codes),
        evaluator_version=evaluated.evaluation_algorithm_version,
        source_evidence_fingerprint=evaluated.evidence_fingerprint,
        source_kind="TARGETED_RESOLUTION_EVIDENCE",
        source_request_fingerprint=request.request_fingerprint,
        explanation_evidence=evidence,
        availability=PairExplanationAvailability.COMPLETE,
    )
    return canonical_json(evidence), fingerprint


def _projection(
    *,
    record_id_1: int,
    record_id_2: int,
    record_reference_1: str,
    record_reference_2: str,
    deterministic_score: float | None,
    signed_relationship: IdentityEdgeClass,
    reason_codes: tuple[str, ...],
    evidence_summary: str,
    evaluator_version: str,
    evidence_fingerprint: str,
    source_kind: str,
    source_request_fingerprint: str | None,
    explanation_evidence_json: str | None,
    expected_explanation_fingerprint: str | None,
    complete: bool,
) -> DeterministicPairExplanationV1:
    evidence = (
        _load_json(explanation_evidence_json, "explanation_evidence_json", dict)
        if complete and explanation_evidence_json is not None
        else None
    )
    if complete and canonical_json(evidence) != explanation_evidence_json:
        raise ValueError("explanation_evidence_json is not canonically serialized")
    availability = (
        PairExplanationAvailability.COMPLETE
        if complete
        else PairExplanationAvailability.PARTIAL_LEGACY
    )
    fingerprint = pair_explanation_fingerprint(
        record_reference_1=record_reference_1,
        record_reference_2=record_reference_2,
        deterministic_score=deterministic_score,
        signed_relationship=signed_relationship,
        classification_reason_codes=reason_codes,
        evaluator_version=evaluator_version,
        source_evidence_fingerprint=evidence_fingerprint,
        source_kind=source_kind,
        source_request_fingerprint=source_request_fingerprint,
        explanation_evidence=evidence,
        availability=availability,
    )
    if (
        expected_explanation_fingerprint is not None
        and fingerprint != expected_explanation_fingerprint
    ):
        raise ValueError("pair explanation fingerprint does not match persisted evidence")
    values = evidence or {}
    return DeterministicPairExplanationV1(
        record_id_1=record_id_1,
        record_id_2=record_id_2,
        record_reference_1=record_reference_1,
        record_reference_2=record_reference_2,
        deterministic_score=deterministic_score,
        signed_relationship=signed_relationship,
        component_scores=dict(values.get("component_scores") or {}),
        classification_reason_codes=tuple(sorted(reason_codes)),
        rule_decision=str(values.get("rule_decision") or evidence_summary or ""),
        rejection_reason=str(values.get("rejection_reason") or ""),
        protected_conflicts=tuple(values.get("protected_conflicts") or ()),
        generic_evidence=dict(values.get("generic_evidence") or {}),
        technical_evidence=dict(values.get("technical_evidence") or {}),
        uom_context=dict(values.get("uom_context") or {}),
        evaluation_context=dict(values.get("evaluation_context") or {}),
        evaluator_version=evaluator_version,
        source_evidence_fingerprint=evidence_fingerprint,
        source_kind=source_kind,
        source_request_fingerprint=source_request_fingerprint,
        availability=availability,
        missing_fields=() if complete else _RICH_FIELDS,
        contract_version=PAIR_EXPLANATION_CONTRACT_VERSION,
        explanation_fingerprint=fingerprint,
    )


def project_targeted_pair_explanation(
    result: TargetedEvidenceResult,
) -> DeterministicPairExplanationV1:
    complete = result.evidence_contract_version == TARGETED_EVIDENCE_CONTRACT_VERSION
    if complete and (
        result.explanation_evidence_json is None
        or result.pair_explanation_contract_version
        != PAIR_EXPLANATION_CONTRACT_VERSION
        or result.pair_explanation_fingerprint is None
    ):
        raise ValueError("explanation-preserving targeted evidence is incomplete")
    request = result.request
    return _projection(
        record_id_1=request.record_id_1,
        record_id_2=request.record_id_2,
        record_reference_1=request.record_reference_1,
        record_reference_2=request.record_reference_2,
        deterministic_score=result.deterministic_score,
        signed_relationship=result.edge_class,
        reason_codes=result.reason_codes,
        evidence_summary=result.evidence_summary,
        evaluator_version=result.evaluator_version,
        evidence_fingerprint=result.evidence_fingerprint,
        source_kind="TARGETED_RESOLUTION_EVIDENCE",
        source_request_fingerprint=request.request_fingerprint,
        explanation_evidence_json=result.explanation_evidence_json,
        expected_explanation_fingerprint=result.pair_explanation_fingerprint,
        complete=complete,
    )


def project_proposal_pair_explanation(
    evaluated,
    *,
    record_reference_1: str,
    record_reference_2: str,
) -> DeterministicPairExplanationV1:
    evidence = explanation_evidence_from_evaluated(evaluated)
    rendered = canonical_json(evidence)
    edge_class = (
        evaluated.edge_class
        if isinstance(evaluated.edge_class, IdentityEdgeClass)
        else IdentityEdgeClass(evaluated.edge_class)
    )
    reason_codes = getattr(evaluated, "classification_reason_codes", None)
    if reason_codes is None:
        reason_codes = tuple(_load_json(
            evaluated.classification_reason_codes_json,
            "classification_reason_codes_json",
            list,
        ))
    return _projection(
        record_id_1=evaluated.record_id_1,
        record_id_2=evaluated.record_id_2,
        record_reference_1=record_reference_1,
        record_reference_2=record_reference_2,
        deterministic_score=evaluated.deterministic_score,
        signed_relationship=edge_class,
        reason_codes=tuple(reason_codes),
        evidence_summary=evaluated.rule_decision,
        evaluator_version=evaluated.evaluation_algorithm_version,
        evidence_fingerprint=evaluated.evidence_fingerprint,
        source_kind="PROPOSAL_EVIDENCE",
        source_request_fingerprint=None,
        explanation_evidence_json=rendered,
        expected_explanation_fingerprint=None,
        complete=True,
    )
