import json
import re
from collections import Counter

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import SOURCE_ROW_INDEX_FIELD
from app.db.models import CandidateDiscoveryMetadata, HybridRetrievalRun
from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.column_semantics import normalize_scan_mode
from app.engine.scoring import score_candidate
from app.engine.identity_evidence_evaluator import DeterministicIdentityContext
from app.repositories.candidate_repository import CandidateRepository
from app.repositories.scan_repository import ScanRepository
from app.repositories.rejection_repository import RejectionRepository
from app.repositories.warning_repository import WarningRepository
from app.services.validation_service import validate_dataframe
from app.services.canonical_record_service import (
    catalog_record_to_engine_input,
    create_or_get_scan_record_catalog,
    load_scan_record_catalog,
)
from app.services.hybrid_retrieval import (
    HybridCandidateRetriever, SqlAlchemyEmbeddingVectorCache, canonical_record_pair,
)
from app.services.identity_discovery_service import (
    mark_discovery_failed,
    persist_discovery_proposals,
    start_discovery_run,
)
from app.services.identity_neighborhood_service import (
    build_and_persist_identity_neighborhoods,
)
from app.services.identity_evidence_service import (
    acquire_identity_evidence,
    mark_identity_evidence_failed,
    start_identity_evidence_run,
)
from app.services.identity_group_snapshot_service import (
    project_and_persist_identity_groups,
)


class ScanRunner:
    def __init__(self, db: Session, configuration=None):
        self.db = db
        self.configuration = configuration or settings
        self.scans = ScanRepository(db)
        self.candidates = CandidateRepository(db)
        self.warnings = WarningRepository(db)
        self.rejections = RejectionRepository(db)

    def persist_initial_identity_group_projection(
        self,
        scan,
        records: pd.DataFrame,
        selected_fields: list[str],
    ):
        """Persist the scan's initial immutable G2 projection from stored evidence."""
        del records  # G2 consumes the authoritative persisted catalog.
        catalog_records = load_scan_record_catalog(self.db, scan.id)
        return project_and_persist_identity_groups(
            self.db,
            scan=scan,
            records=[catalog_record_to_engine_input(row) for row in catalog_records],
            candidates=self.candidates.list_for_scan(scan.id),
            exclusions=self.rejections.list_for_scan(scan.id),
            selected_fields=selected_fields,
        )

    def run(self, df: pd.DataFrame, scan_name: str, selected_fields: list[str], threshold: float, source_type="CSV", sensitive_mode: bool = True, scan_mode: str = "SAME_SITE_DUPLICATE"):
        scan_mode = normalize_scan_mode(scan_mode)
        validation = validate_dataframe(df, selected_fields, sensitive_mode=sensitive_mode)
        if validation["missing_required_columns"]:
            raise ValueError(f"Missing required columns: {', '.join(validation['missing_required_columns'])}")

        scan = self.scans.create(scan_name, selected_fields, threshold, source_type, scan_mode)
        discovery_run_id = None
        evidence_run_id = None
        try:
            for warning in validation["warnings"]:
                self.warnings.save(scan.id, warning)

            source_indexed = df.copy()
            source_indexed[SOURCE_ROW_INDEX_FIELD] = range(len(source_indexed))
            usable = source_indexed[
                source_indexed["DESCRIPTION"].fillna("").str.strip().ne("")
            ].copy()
            catalog_result = create_or_get_scan_record_catalog(
                self.db,
                scan_id=scan.id,
                records=usable.to_dict(orient="records"),
            )
            # The catalog is a completed prerequisite stage. Candidate discovery
            # never begins against a partial or merely in-memory record set.
            self.db.commit()
            discovery_run = start_discovery_run(
                self.db,
                scan_id=scan.id,
                catalog_records=catalog_result.records,
                configuration=self.configuration,
                scan_mode=scan_mode,
                selected_fields=selected_fields,
            )
            discovery_run_id = discovery_run.discovery_run_id
            # Preserve RUNNING independently so a later failed proposal stage is
            # auditable while the already committed GF-1 catalog remains intact.
            self.db.commit()
            pairs = generate_candidate_pairs(usable, selected_fields)

            existing_warnings = {(w["warning_type"], w["message"]) for w in validation["warnings"]}
            generated_warnings = {(w["warning_type"], w["message"]) for pair in pairs for w in pair["warnings"]}
            for warning_type, message in generated_warnings - existing_warnings:
                self.warnings.save(scan.id, {"warning_type": warning_type, "message": message})

            candidates_found = 0
            rejections_found = 0
            standard_candidate_pairs = set()
            standard_write_plan = []
            for pair in pairs:
                result = score_candidate(pair["record_a"], pair["record_b"], selected_fields, scan_mode)
                if result["final_score"] >= threshold:
                    standard_write_plan.append(("candidate", pair, result))
                    standard_candidate_pairs.add(canonical_record_pair(pair["record_a"], pair["record_b"]))
                    candidates_found += 1
                elif result["rule_decision"] != "ALLOW":
                    standard_write_plan.append(("rejection", pair, result))
                    rejections_found += 1

            retrieval = None
            hybrid_write_plan = []
            hybrid_run_values = None
            engine_records = [
                row.to_dict() for _, row in usable.reset_index(drop=True).iterrows()
            ]
            if self.configuration.hybrid_retrieval_enabled:
                retrieval = HybridCandidateRetriever(
                    self.configuration,
                    cache=SqlAlchemyEmbeddingVectorCache(self.db),
                ).retrieve(usable, scan_mode, standard_candidate_pairs)
                added = 0
                added_with_uom_difference = 0
                added_with_uom_unknown = 0
                post_scoring_excluded = 0
                post_scoring_reasons = Counter()
                for retrieved in retrieval.candidates:
                    left = engine_records[retrieved.left_record_id]
                    right = engine_records[retrieved.right_record_id]
                    result = score_candidate(
                        left, right, selected_fields, scan_mode,
                        allow_uom_mapping_review=True,
                    )
                    if result["rule_decision"] in {"REJECT", "DATA_CONFLICT", "CROSS_SITE"} or result["critical_mismatches"]:
                        post_scoring_excluded += 1
                        reason = str(result.get("rejection_reason") or "").strip().upper()
                        if not re.fullmatch(r"[A-Z0-9_]{1,80}", reason):
                            reason = "DETERMINISTIC_POST_SCORING_EXCLUSION"
                        post_scoring_reasons[reason] += 1
                        continue
                    if result["business_status"] == "LIKELY_DUPLICATE":
                        result = dict(result)
                        result["business_status"] = "POSSIBLE_DUPLICATE_REVIEW"
                        result["explanation"] = result["explanation"] + " Hybrid retrieval additions require human review."
                    hybrid_write_plan.append((left, right, result, retrieved))
                    added += 1
                    if retrieved.evidence.uom_relationship in {
                        "CONVERTIBLE_SAME_DIMENSION", "DIFFERENT_DIMENSION_OR_BASIS",
                    }:
                        added_with_uom_difference += 1
                    elif retrieved.evidence.uom_relationship in {
                        "MISSING_OR_WILDCARD", "MALFORMED_OR_UNKNOWN",
                    }:
                        added_with_uom_unknown += 1
                metrics = retrieval.metrics
                hybrid_run_values = dict(
                    scan_id=scan.id,
                    records_indexed=metrics.records_indexed,
                    lexical_candidates_generated=metrics.lexical_candidates_generated,
                    vector_candidates_generated=metrics.vector_candidates_generated,
                    exact_description_candidates=metrics.exact_description_candidates,
                    part_family_candidates=metrics.part_family_candidates,
                    technical_identity_candidates=metrics.technical_identity_candidates,
                    reciprocal_candidates=metrics.reciprocal_candidates,
                    generic_penalized_candidates=metrics.generic_penalized_candidates,
                    conflict_penalized_candidates=metrics.conflict_penalized_candidates,
                    uom_same_pairs_considered=metrics.uom_same_pairs_considered,
                    uom_convertible_pairs_considered=metrics.uom_convertible_pairs_considered,
                    uom_different_basis_pairs_considered=metrics.uom_different_basis_pairs_considered,
                    uom_missing_or_wildcard_pairs_considered=metrics.uom_missing_or_wildcard_pairs_considered,
                    uom_malformed_or_unknown_pairs_considered=metrics.uom_malformed_or_unknown_pairs_considered,
                    multi_source_candidates=metrics.multi_source_candidates,
                    tier_a_candidates=metrics.tier_a_candidates,
                    tier_b_candidates=metrics.tier_b_candidates,
                    tier_c_candidates=metrics.tier_c_candidates,
                    hybrid_candidates_added=added,
                    hybrid_candidates_added_with_uom_difference=added_with_uom_difference,
                    hybrid_candidates_added_with_uom_unknown=added_with_uom_unknown,
                    hybrid_post_scoring_excluded_count=post_scoring_excluded,
                    hybrid_post_scoring_exclusion_reasons_json=json.dumps(
                        {
                            reason: post_scoring_reasons[reason]
                            for reason in sorted(post_scoring_reasons)[:20]
                        },
                        separators=(",", ":"),
                    ),
                    hybrid_candidates_skipped_by_cap=metrics.hybrid_candidates_skipped_by_cap,
                    average_candidates_per_record=metrics.average_candidates_per_record,
                    max_candidates_for_any_record=metrics.max_candidates_for_any_record,
                    largest_description_family_candidates=metrics.largest_description_family_candidates,
                    candidate_family_concentration=metrics.candidate_family_concentration,
                    retrieval_runtime_ms=metrics.retrieval_runtime_ms,
                    embedding_model_version=retrieval.embedding_model_version,
                    provider_request_count=0,
                )
                candidates_found += added

            persist_discovery_proposals(
                self.db,
                discovery_run_id=discovery_run_id,
                scan_id=scan.id,
                catalog_records=catalog_result.records,
                standard_pairs=pairs,
                hybrid_result=retrieval,
                engine_records=engine_records,
            )
            build_and_persist_identity_neighborhoods(
                self.db,
                discovery_run_id=discovery_run_id,
                scan_id=scan.id,
                max_members=int(getattr(
                    self.configuration, "identity_neighborhood_max_members", 20
                )),
            )

            # GF-1 and completed GF-2/GF-3 survive a later required evidence
            # failure. Legacy candidate business writes have not occurred yet.
            self.db.commit()
            evidence_run = start_identity_evidence_run(
                self.db,
                scan_id=scan.id,
                discovery_run_id=discovery_run_id,
                context=DeterministicIdentityContext(
                    scan_mode=scan_mode,
                    selected_fields=tuple(selected_fields),
                ),
            )
            evidence_run_id = evidence_run.evidence_run_id
            self.db.commit()
            acquire_identity_evidence(self.db, evidence_run_id=evidence_run_id)
            self.db.commit()

            # Preserve the legacy visible pair path after required independent
            # evidence is complete; GF-4 is not an authority for G1/G2 v1.
            for kind, pair, result in standard_write_plan:
                if kind == "candidate":
                    self.candidates.save(
                        scan.id, pair["record_a"], pair["record_b"], result
                    )
                else:
                    self.rejections.save(
                        scan.id, pair["record_a"], pair["record_b"], result
                    )
            for left, right, result, retrieved in hybrid_write_plan:
                candidate = self.candidates.save(scan.id, left, right, result)
                self.db.flush()
                self.db.add(CandidateDiscoveryMetadata(
                    candidate_id=candidate.id,
                    source="HYBRID_RETRIEVAL",
                    signals_json=json.dumps(list(retrieved.evidence.blocking_signals), separators=(",", ":")),
                    retrieval_sources_json=json.dumps(list(retrieved.evidence.retrieval_sources), separators=(",", ":")),
                    retrieval_score=retrieved.retrieval_score,
                    retrieval_priority=retrieved.retrieval_priority,
                    retrieval_tier=retrieved.retrieval_tier.value,
                    lexical_score=retrieved.evidence.lexical_score,
                    vector_score=retrieved.evidence.vector_score,
                    description_specificity_score=retrieved.evidence.description_specificity_score,
                    generic_description_penalty=retrieved.evidence.generic_description_penalty,
                    retrieval_conflict_signals_json=json.dumps(
                        list(retrieved.evidence.conflict_signals), separators=(",", ":")
                    ),
                    reciprocal_sources_json=json.dumps(
                        list(retrieved.evidence.reciprocal_sources), separators=(",", ":")
                    ),
                    uom_relationship=retrieved.evidence.uom_relationship,
                    uom_evidence=retrieved.evidence.uom_evidence,
                    uom_penalty=retrieved.evidence.uom_penalty,
                    mapping_quality=retrieved.evidence.mapping_quality,
                    retrieval_rank=retrieved.retrieval_rank,
                    embedding_model_version=retrieval.embedding_model_version,
                ))
            if hybrid_run_values is not None:
                self.db.add(HybridRetrievalRun(**hybrid_run_values))

            # G2 consumes the complete persisted legacy deterministic evidence set. Its
            # own transaction is atomic and fingerprint-idempotent, and the scan
            # is exposed as COMPLETED only after that snapshot is available.
            self.persist_initial_identity_group_projection(scan, usable, selected_fields)
            warning_count = self.warnings.count_for_scan(scan.id)
            return self.scans.update_status(
                scan,
                "COMPLETED",
                total_records=len(df),
                total_candidates=candidates_found,
                rejections_count=rejections_found,
                warnings_count=warning_count,
            ), len(pairs)
        except Exception as exc:
            self.db.rollback()
            if evidence_run_id is not None:
                mark_identity_evidence_failed(self.db, evidence_run_id, exc)
                self.db.commit()
            if discovery_run_id is not None:
                mark_discovery_failed(self.db, discovery_run_id, exc)
                self.db.commit()
            self.scans.update_status(scan, "FAILED", total_records=len(df))
            raise
