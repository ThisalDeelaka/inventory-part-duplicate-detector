import json
import re

from sqlalchemy.orm import Session

from app.db.models import HybridRetrievalRun


def _bounded_reason_counts(value: str | None) -> dict[str, int] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    result = {}
    for reason in sorted(parsed)[:20]:
        count = parsed[reason]
        if re.fullmatch(r"[A-Z0-9_]{1,80}", str(reason)) and isinstance(count, int) and count > 0:
            result[str(reason)] = count
    return result


def hybrid_retrieval_metrics(db: Session, scan_id: int) -> dict:
    row = db.query(HybridRetrievalRun).filter_by(scan_id=scan_id).first()
    if row is None:
        return {
            "records_indexed": 0, "lexical_candidates_generated": 0,
            "vector_candidates_generated": 0, "char_vector_candidates_generated": 0,
            "multi_source_candidates": 0,
            "exact_description_candidates": 0, "part_family_candidates": 0,
            "technical_identity_candidates": 0, "reciprocal_candidates": 0,
            "generic_penalized_candidates": 0, "conflict_penalized_candidates": 0,
            "uom_same_pairs_considered": 0,
            "uom_convertible_pairs_considered": 0,
            "uom_different_basis_pairs_considered": 0,
            "uom_missing_or_wildcard_pairs_considered": 0,
            "uom_malformed_or_unknown_pairs_considered": 0,
            "tier_a_candidates": 0, "tier_b_candidates": 0, "tier_c_candidates": 0,
            "hybrid_retrieval_selected_count": 0,
            "hybrid_retrieval_selected_tier_a": 0,
            "hybrid_retrieval_selected_tier_b": 0,
            "hybrid_retrieval_selected_tier_c": 0,
            "hybrid_post_scoring_excluded_count": 0,
            "hybrid_post_scoring_exclusion_reasons": {},
            "hybrid_candidates_added": 0, "hybrid_candidates_skipped_by_cap": 0,
            "hybrid_candidates_added_with_uom_difference": 0,
            "hybrid_candidates_added_with_uom_unknown": 0,
            "hybrid_candidates_skipped_by_budget": 0,
            "average_candidates_per_record": 0.0, "max_candidates_for_any_record": 0,
            "largest_description_family_candidates": 0, "candidate_family_concentration": 0.0,
            "retrieval_runtime_ms": 0.0, "retrieval_provider_request_count": 0,
            "embedding_model_version": None,
        }
    tier_a = int(row.tier_a_candidates or 0)
    tier_b = int(row.tier_b_candidates or 0)
    tier_c = int(row.tier_c_candidates or 0)
    post_scoring_excluded = row.hybrid_post_scoring_excluded_count
    return {
        "records_indexed": row.records_indexed,
        "lexical_candidates_generated": row.lexical_candidates_generated,
        "vector_candidates_generated": row.vector_candidates_generated,
        "char_vector_candidates_generated": row.vector_candidates_generated,
        "exact_description_candidates": row.exact_description_candidates,
        "part_family_candidates": row.part_family_candidates,
        "technical_identity_candidates": row.technical_identity_candidates,
        "reciprocal_candidates": row.reciprocal_candidates,
        "generic_penalized_candidates": row.generic_penalized_candidates,
        "conflict_penalized_candidates": row.conflict_penalized_candidates,
        "uom_same_pairs_considered": row.uom_same_pairs_considered,
        "uom_convertible_pairs_considered": row.uom_convertible_pairs_considered,
        "uom_different_basis_pairs_considered": row.uom_different_basis_pairs_considered,
        "uom_missing_or_wildcard_pairs_considered": row.uom_missing_or_wildcard_pairs_considered,
        "uom_malformed_or_unknown_pairs_considered": row.uom_malformed_or_unknown_pairs_considered,
        "multi_source_candidates": row.multi_source_candidates,
        "tier_a_candidates": tier_a,
        "tier_b_candidates": tier_b,
        "tier_c_candidates": tier_c,
        "hybrid_retrieval_selected_count": tier_a + tier_b + tier_c,
        "hybrid_retrieval_selected_tier_a": tier_a,
        "hybrid_retrieval_selected_tier_b": tier_b,
        "hybrid_retrieval_selected_tier_c": tier_c,
        "hybrid_post_scoring_excluded_count": (
            int(post_scoring_excluded) if post_scoring_excluded is not None else None
        ),
        "hybrid_post_scoring_exclusion_reasons": _bounded_reason_counts(
            row.hybrid_post_scoring_exclusion_reasons_json
        ),
        "hybrid_candidates_added": row.hybrid_candidates_added,
        "hybrid_candidates_added_with_uom_difference": (
            row.hybrid_candidates_added_with_uom_difference
        ),
        "hybrid_candidates_added_with_uom_unknown": (
            row.hybrid_candidates_added_with_uom_unknown
        ),
        "hybrid_candidates_skipped_by_cap": row.hybrid_candidates_skipped_by_cap,
        "hybrid_candidates_skipped_by_budget": row.hybrid_candidates_skipped_by_cap,
        "average_candidates_per_record": row.average_candidates_per_record,
        "max_candidates_for_any_record": row.max_candidates_for_any_record,
        "largest_description_family_candidates": row.largest_description_family_candidates,
        "candidate_family_concentration": row.candidate_family_concentration,
        "retrieval_runtime_ms": row.retrieval_runtime_ms,
        "retrieval_provider_request_count": row.provider_request_count,
        "embedding_model_version": row.embedding_model_version,
    }
