import json

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CandidateDiscoveryMetadata, HybridRetrievalRun
from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.column_semantics import normalize_scan_mode
from app.engine.scoring import score_candidate
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.scan_repository import ScanRepository
from app.repositories.rejection_repository import RejectionRepository
from app.repositories.warning_repository import WarningRepository
from app.services.validation_service import validate_dataframe
from app.services.hybrid_retrieval import (
    HybridCandidateRetriever, SqlAlchemyEmbeddingVectorCache, canonical_record_pair,
)


class ScanRunner:
    def __init__(self, db: Session, configuration=None):
        self.db = db
        self.configuration = configuration or settings
        self.scans = ScanRepository(db)
        self.candidates = CandidateRepository(db)
        self.warnings = WarningRepository(db)
        self.rejections = RejectionRepository(db)

    def run(self, df: pd.DataFrame, scan_name: str, selected_fields: list[str], threshold: float, source_type="CSV", sensitive_mode: bool = True, scan_mode: str = "SAME_SITE_DUPLICATE"):
        scan_mode = normalize_scan_mode(scan_mode)
        validation = validate_dataframe(df, selected_fields, sensitive_mode=sensitive_mode)
        if validation["missing_required_columns"]:
            raise ValueError(f"Missing required columns: {', '.join(validation['missing_required_columns'])}")

        scan = self.scans.create(scan_name, selected_fields, threshold, source_type, scan_mode)
        try:
            for warning in validation["warnings"]:
                self.warnings.save(scan.id, warning)

            usable = df[df["DESCRIPTION"].fillna("").str.strip().ne("")].copy()
            pairs = generate_candidate_pairs(usable, selected_fields)

            existing_warnings = {(w["warning_type"], w["message"]) for w in validation["warnings"]}
            generated_warnings = {(w["warning_type"], w["message"]) for pair in pairs for w in pair["warnings"]}
            for warning_type, message in generated_warnings - existing_warnings:
                self.warnings.save(scan.id, {"warning_type": warning_type, "message": message})

            candidates_found = 0
            rejections_found = 0
            standard_candidate_pairs = set()
            for pair in pairs:
                result = score_candidate(pair["record_a"], pair["record_b"], selected_fields, scan_mode)
                if result["final_score"] >= threshold:
                    self.candidates.save(scan.id, pair["record_a"], pair["record_b"], result)
                    standard_candidate_pairs.add(canonical_record_pair(pair["record_a"], pair["record_b"]))
                    candidates_found += 1
                elif result["rule_decision"] != "ALLOW":
                    self.rejections.save(scan.id, pair["record_a"], pair["record_b"], result)
                    rejections_found += 1

            if self.configuration.hybrid_retrieval_enabled:
                retrieval = HybridCandidateRetriever(
                    self.configuration,
                    cache=SqlAlchemyEmbeddingVectorCache(self.db),
                ).retrieve(usable, scan_mode, standard_candidate_pairs)
                records = [row.to_dict() for _, row in usable.reset_index(drop=True).iterrows()]
                added = 0
                for retrieved in retrieval.candidates:
                    left = records[retrieved.left_record_id]
                    right = records[retrieved.right_record_id]
                    result = score_candidate(left, right, selected_fields, scan_mode)
                    if result["rule_decision"] in {"REJECT", "DATA_CONFLICT", "CROSS_SITE"} or result["critical_mismatches"]:
                        continue
                    if result["business_status"] == "LIKELY_DUPLICATE":
                        result = dict(result)
                        result["business_status"] = "POSSIBLE_DUPLICATE_REVIEW"
                        result["explanation"] = result["explanation"] + " Hybrid retrieval additions require human review."
                    candidate = self.candidates.save(scan.id, left, right, result)
                    self.db.flush()
                    self.db.add(CandidateDiscoveryMetadata(
                        candidate_id=candidate.id,
                        source="HYBRID_RETRIEVAL",
                        signals_json=json.dumps(list(retrieved.evidence.blocking_signals), separators=(",", ":")),
                        retrieval_sources_json=json.dumps(list(retrieved.evidence.retrieval_sources), separators=(",", ":")),
                        retrieval_score=retrieved.retrieval_score,
                        lexical_score=retrieved.evidence.lexical_score,
                        vector_score=retrieved.evidence.vector_score,
                        retrieval_rank=retrieved.retrieval_rank,
                        embedding_model_version=retrieval.embedding_model_version,
                    ))
                    added += 1
                metrics = retrieval.metrics
                self.db.add(HybridRetrievalRun(
                    scan_id=scan.id,
                    records_indexed=metrics.records_indexed,
                    lexical_candidates_generated=metrics.lexical_candidates_generated,
                    vector_candidates_generated=metrics.vector_candidates_generated,
                    multi_source_candidates=metrics.multi_source_candidates,
                    hybrid_candidates_added=added,
                    hybrid_candidates_skipped_by_cap=metrics.hybrid_candidates_skipped_by_cap,
                    average_candidates_per_record=metrics.average_candidates_per_record,
                    max_candidates_for_any_record=metrics.max_candidates_for_any_record,
                    retrieval_runtime_ms=metrics.retrieval_runtime_ms,
                    embedding_model_version=retrieval.embedding_model_version,
                    provider_request_count=0,
                ))
                candidates_found += added

            self.db.commit()
            warning_count = self.warnings.count_for_scan(scan.id)
            return self.scans.update_status(
                scan,
                "COMPLETED",
                total_records=len(df),
                total_candidates=candidates_found,
                rejections_count=rejections_found,
                warnings_count=warning_count,
            ), len(pairs)
        except Exception:
            self.db.rollback()
            self.scans.update_status(scan, "FAILED", total_records=len(df))
            raise
