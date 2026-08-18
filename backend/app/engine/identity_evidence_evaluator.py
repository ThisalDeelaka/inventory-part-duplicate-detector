"""Pure GF-4 adapter over the authoritative deterministic pair evaluator."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.engine.generic_description_guard import is_generic_description
from app.engine.identity_edge import (
    IDENTITY_EDGE_CLASSIFIER_VERSION,
    IdentityEdgeClass,
    classify_identity_edge,
)
from app.engine.scoring import score_candidate
from app.engine.uom_relationship import classify_uom_relationship
from app.services.canonical_record_service import (
    CanonicalScanRecord,
    catalog_record_to_engine_input,
)


IDENTITY_EVIDENCE_CONTRACT_VERSION = "identity-evidence-edge-v1"
IDENTITY_EVIDENCE_EVALUATOR_VERSION = "canonical-identity-evaluator-v1"
_COMPONENT_FIELDS = (
    "description_similarity",
    "tfidf_score",
    "fuzzy_score",
    "part_no_similarity",
    "technical_token_score",
)


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def sha256_payload(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DeterministicIdentityContext:
    scan_mode: str
    selected_fields: tuple[str, ...]


@dataclass(frozen=True)
class EvaluatedIdentityRelationship:
    record_id_1: int
    record_id_2: int
    edge_class: IdentityEdgeClass
    classification_reason_codes: tuple[str, ...]
    evaluation_algorithm_version: str
    evidence_fingerprint: str
    deterministic_score: float
    component_scores_json: str
    rule_decision: str
    rejection_reason: str
    protected_conflicts_json: str
    generic_evidence_json: str
    technical_evidence_json: str
    uom_context_json: str
    evaluation_context_json: str


def deterministic_context_payload(context: DeterministicIdentityContext) -> dict:
    return {
        "evaluator_version": IDENTITY_EVIDENCE_EVALUATOR_VERSION,
        "edge_classifier_version": IDENTITY_EDGE_CLASSIFIER_VERSION,
        "scan_mode": str(context.scan_mode),
        "selected_fields": sorted(set(context.selected_fields)),
        "uom_is_mapping_context": True,
    }


def deterministic_context_fingerprint(context: DeterministicIdentityContext) -> str:
    return sha256_payload(deterministic_context_payload(context))


def evaluate_canonical_identity_relationship(
    record_1: CanonicalScanRecord,
    record_2: CanonicalScanRecord,
    context: DeterministicIdentityContext,
) -> EvaluatedIdentityRelationship:
    """Evaluate any two same-scan GF-1 records without persistence authority."""
    if record_1.scan_id != record_2.scan_id:
        raise ValueError("canonical identity evaluation cannot cross scans")
    if record_1.record_id == record_2.record_id:
        raise ValueError("canonical identity evaluation cannot create a self edge")
    left, right = sorted((record_1, record_2), key=lambda item: item.record_id)
    result = score_candidate(
        catalog_record_to_engine_input(left),
        catalog_record_to_engine_input(right),
        sorted(set(context.selected_fields)),
        context.scan_mode,
        allow_uom_mapping_review=True,
    )
    classification = classify_identity_edge(result)
    component_scores = {
        field: float(result.get(field) or 0.0) for field in _COMPONENT_FIELDS
    }
    protected_conflicts = list(result.get("critical_mismatches") or [])
    generic_evidence = {
        "description_1_generic": is_generic_description(left.description),
        "description_2_generic": is_generic_description(right.description),
        "generic_description_warning": bool(result.get("generic_description_warning")),
        "generic_guard_reason": (
            str(result.get("rejection_reason") or "")
            if result.get("rejection_reason") == "GENERIC_DESCRIPTION"
            else ""
        ),
    }
    technical_evidence = {
        "variant_attributes_1": result.get("variant_attributes_a") or {},
        "variant_attributes_2": result.get("variant_attributes_b") or {},
        "normalized_description_1": result.get("normalized_description_a") or "",
        "normalized_description_2": result.get("normalized_description_b") or "",
        "normalized_part_no_1": result.get("normalized_part_no_a") or "",
        "normalized_part_no_2": result.get("normalized_part_no_b") or "",
    }
    uom = classify_uom_relationship(left.uom, right.uom)
    uom_context = {
        "relationship": uom.relationship.value,
        "reason_code": uom.reason_code,
        "mapping_quality": uom.mapping_quality.value,
        "penalty": uom.penalty,
        "identity_authority": False,
    }
    evaluation_context = deterministic_context_payload(context)
    reason_codes = tuple(sorted(classification.reason_codes))
    fingerprint = sha256_payload({
        "contract_version": IDENTITY_EVIDENCE_CONTRACT_VERSION,
        "endpoint_1": {
            "record_ref_key": left.record_ref_key,
            "source_record_fingerprint": left.source_record_fingerprint,
        },
        "endpoint_2": {
            "record_ref_key": right.record_ref_key,
            "source_record_fingerprint": right.source_record_fingerprint,
        },
        "evaluation_context": evaluation_context,
        "edge_class": classification.edge_class.value,
        "classification_reason_codes": reason_codes,
        "deterministic_score": float(result.get("final_score") or 0.0),
        "component_scores": component_scores,
        "rule_decision": str(result.get("rule_decision") or ""),
        "rejection_reason": str(result.get("rejection_reason") or ""),
        "protected_conflicts": protected_conflicts,
        "generic_evidence": generic_evidence,
        "technical_evidence": technical_evidence,
        "uom_context": uom_context,
    })
    return EvaluatedIdentityRelationship(
        record_id_1=left.record_id,
        record_id_2=right.record_id,
        edge_class=classification.edge_class,
        classification_reason_codes=reason_codes,
        evaluation_algorithm_version=IDENTITY_EVIDENCE_EVALUATOR_VERSION,
        evidence_fingerprint=fingerprint,
        deterministic_score=float(result.get("final_score") or 0.0),
        component_scores_json=canonical_json(component_scores),
        rule_decision=str(result.get("rule_decision") or ""),
        rejection_reason=str(result.get("rejection_reason") or ""),
        protected_conflicts_json=canonical_json(protected_conflicts),
        generic_evidence_json=canonical_json(generic_evidence),
        technical_evidence_json=canonical_json(technical_evidence),
        uom_context_json=canonical_json(uom_context),
        evaluation_context_json=canonical_json(evaluation_context),
    )
