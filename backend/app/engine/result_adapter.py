from dataclasses import asdict, is_dataclass
from typing import Any

from app.engine.models import DecisionResult


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if is_dataclass(value):
        return asdict(value)
    return {}


def _safe_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _recommended_action(status: str, confidence_level: str) -> str:
    if status == "DUPLICATE_CANDIDATE":
        return "Review as likely duplicate candidate"
    if status == "RELATED_BUT_NOT_DUPLICATE":
        return "Do not merge; related item only"
    if status == "DATA_CONFLICT_REVIEW":
        return "Resolve data conflict before duplicate review"
    if status == "CROSS_SITE_STANDARDIZATION_CANDIDATE":
        return "Review for cross-site standardization"
    if status == "INSUFFICIENT_DATA":
        return "Improve master data before deciding"
    if confidence_level in {"HIGH", "MEDIUM"}:
        return "Manual review recommended"
    return "Not likely duplicate"


def _variant_attributes(extracted: dict) -> dict:
    return {
        "product_class": _safe_list(extracted.get("product_class")),
        "type_code": _safe_list(extracted.get("type_code")),
        "rating": _safe_list(extracted.get("rating")),
        "color": _safe_list(extracted.get("color")),
        "application_context": _safe_list(extracted.get("application_context")),
        "function_or_media": _safe_list(extracted.get("function_or_media")),
        "generic_terms": _safe_list(extracted.get("generic_terms")),
    }


def decision_result_to_scan_candidate(result: DecisionResult | dict | None) -> dict:
    payload = _as_dict(result)
    status = payload.get("status") or "POSSIBLE_DUPLICATE_REVIEW"
    confidence_score = float(payload.get("confidence_score") or 0.0)
    confidence_level = payload.get("confidence_level") or "IGNORE"
    matched_evidence = _safe_list(payload.get("matched_evidence"))
    differences = _safe_list(payload.get("differences"))
    warnings = _safe_list(payload.get("warnings"))
    attrs_a = _as_dict(payload.get("extracted_attributes_a"))
    attrs_b = _as_dict(payload.get("extracted_attributes_b"))

    return {
        # Legacy/current scan candidate shape.
        "id": payload.get("id"),
        "scan_id": payload.get("scan_id"),
        "contract_a": payload.get("contract_a", ""),
        "part_no_a": payload.get("part_no_a", ""),
        "description_a": payload.get("description_a", ""),
        "contract_b": payload.get("contract_b", ""),
        "part_no_b": payload.get("part_no_b", ""),
        "description_b": payload.get("description_b", ""),
        "score": confidence_score,
        "similarity_score": confidence_score,
        "final_score": confidence_score,
        "confidence_level": confidence_level,
        "description_similarity": float(payload.get("description_similarity") or confidence_score),
        "tfidf_score": float(payload.get("tfidf_score") or 0.0),
        "fuzzy_score": float(payload.get("fuzzy_score") or 0.0),
        "part_no_similarity": float(payload.get("part_no_similarity") or 0.0),
        "technical_token_score": float(payload.get("technical_token_score") or 0.0),
        "matched_fields": matched_evidence,
        "mismatched_fields": differences,
        "reason": payload.get("explanation", ""),
        "explanation": payload.get("explanation", ""),
        "recommended_action": _recommended_action(status, confidence_level),
        "review_status": payload.get("review_status", "UNREVIEWED"),
        # New redesigned-engine fields.
        "business_status": status,
        "confidence_score": confidence_score,
        "matched_evidence": matched_evidence,
        "differences": differences,
        "warnings": warnings,
        "rule_decision": payload.get("rule_decision", "ALLOW"),
        "rejection_reason": payload.get("rejection_reason", ""),
        "scan_mode": payload.get("scan_mode", "SAME_SITE_DUPLICATE"),
        "critical_mismatches": differences,
        "variant_attributes_a": _variant_attributes(attrs_a),
        "variant_attributes_b": _variant_attributes(attrs_b),
        "generic_description_warning": any("generic" in str(w).lower() or "sparse" in str(w).lower() for w in warnings),
        "application_context_a": _safe_list(attrs_a.get("application_context")),
        "application_context_b": _safe_list(attrs_b.get("application_context")),
        "application_context_warning": any("application context" in str(w).lower() for w in warnings),
        "normalized_part_no_a": payload.get("normalized_part_no_a", ""),
        "normalized_part_no_b": payload.get("normalized_part_no_b", ""),
        "normalized_description_a": payload.get("normalized_description_a", ""),
        "normalized_description_b": payload.get("normalized_description_b", ""),
        "extracted_attributes_a": attrs_a,
        "extracted_attributes_b": attrs_b,
    }


def decision_results_to_scan_candidates(results: list[DecisionResult | dict]) -> list[dict]:
    return [decision_result_to_scan_candidate(result) for result in results or []]
