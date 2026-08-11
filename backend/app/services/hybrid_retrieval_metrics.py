from sqlalchemy.orm import Session

from app.db.models import HybridRetrievalRun


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
            "tier_a_candidates": 0, "tier_b_candidates": 0, "tier_c_candidates": 0,
            "hybrid_candidates_added": 0, "hybrid_candidates_skipped_by_cap": 0,
            "average_candidates_per_record": 0.0, "max_candidates_for_any_record": 0,
            "largest_description_family_candidates": 0, "candidate_family_concentration": 0.0,
            "retrieval_runtime_ms": 0.0, "retrieval_provider_request_count": 0,
            "embedding_model_version": None,
        }
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
        "multi_source_candidates": row.multi_source_candidates,
        "tier_a_candidates": row.tier_a_candidates,
        "tier_b_candidates": row.tier_b_candidates,
        "tier_c_candidates": row.tier_c_candidates,
        "hybrid_candidates_added": row.hybrid_candidates_added,
        "hybrid_candidates_skipped_by_cap": row.hybrid_candidates_skipped_by_cap,
        "average_candidates_per_record": row.average_candidates_per_record,
        "max_candidates_for_any_record": row.max_candidates_for_any_record,
        "largest_description_family_candidates": row.largest_description_family_candidates,
        "candidate_family_concentration": row.candidate_family_concentration,
        "retrieval_runtime_ms": row.retrieval_runtime_ms,
        "retrieval_provider_request_count": row.provider_request_count,
        "embedding_model_version": row.embedding_model_version,
    }
