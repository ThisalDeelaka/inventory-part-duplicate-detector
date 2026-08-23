import json
import re
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import SOURCE_ROW_INDEX_FIELD
from app.db.models import CandidateDiscoveryMetadata, HybridRetrievalRun
from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.candidate_evaluation_features import (
    build_candidate_evaluation_features,
)
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
    CANONICAL_RECORD_REF_FIELD, HybridCandidateRetriever,
    SqlAlchemyEmbeddingVectorCache, canonical_record_pair,
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
from app.services.identity_resolution_service import (
    resolve_and_persist_identity_groups,
)
from app.services.g2_v2_projection_service import (
    build_and_persist_g2_v2_projection,
)
from app.services.identity_group_query_service import IdentityGroupQueryService
from app.services.shadow_comparison_service import (
    build_and_persist_shadow_comparison,
)
from app.orchestration.contracts import (
    ScanOrchestrationMode,
    ScanStage,
    ScanStageExecutionStatus,
)
from app.orchestration.pair_path_deprecation import (
    build_post_gf9_orchestration_plan,
    pair_path_write_policy,
    post_gf9_orchestration_policy,
)
from app.services.scan_orchestration_service import (
    complete_scan_orchestration,
    fail_scan_orchestration_audit,
    record_scan_stage_result,
    source_run_reference,
    start_scan_orchestration,
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
        mode = getattr(
            self.configuration,
            "identity_orchestration_mode",
            ScanOrchestrationMode.LEGACY_PRIMARY.value,
        )
        shadow_enabled = bool(getattr(
            self.configuration,
            "group_first_shadow_comparison_enabled",
            False,
        ))
        policy = post_gf9_orchestration_policy(
            mode, shadow_comparison_enabled=shadow_enabled
        )
        plan = build_post_gf9_orchestration_plan(policy)
        write_policy = pair_path_write_policy(
            mode, shadow_comparison_enabled=shadow_enabled
        )
        if write_policy.policy_version != plan.policy.policy_version:
            raise ValueError("pair-path write policy differs from orchestration plan")
        validation = validate_dataframe(df, selected_fields, sensitive_mode=sensitive_mode)
        if validation["missing_required_columns"]:
            raise ValueError(f"Missing required columns: {', '.join(validation['missing_required_columns'])}")

        scan = self.scans.create(scan_name, selected_fields, threshold, source_type, scan_mode)
        discovery_run_id = None
        evidence_run_id = None
        orchestration_run_id = None
        current_stage = None
        current_stage_started_at = None

        def begin_stage(stage):
            nonlocal current_stage, current_stage_started_at
            current_stage = stage
            current_stage_started_at = datetime.now(timezone.utc)

        def record_stage(
            stage,
            status,
            *,
            safe_failure_category=None,
            source_reference=None,
            diagnostic_summary=None,
        ):
            nonlocal current_stage, current_stage_started_at
            row = record_scan_stage_result(
                self.db,
                orchestration_run_id=orchestration_run_id,
                plan=plan,
                stage=stage,
                status=status,
                started_at=(
                    current_stage_started_at if current_stage == stage else None
                ),
                safe_failure_category=safe_failure_category,
                source_reference=source_reference,
                diagnostic_summary=diagnostic_summary,
            )
            if current_stage == stage:
                current_stage = None
                current_stage_started_at = None
            return row

        try:
            orchestration = start_scan_orchestration(
                self.db, scan_id=scan.id, plan=plan
            )
            orchestration_run_id = orchestration.orchestration_run_id
            if orchestration.status != "RUNNING":
                raise ValueError("scan orchestration execution is already terminal")
            begin_stage(ScanStage.CANONICAL_CATALOG)
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
            record_stage(
                ScanStage.CANONICAL_CATALOG,
                ScanStageExecutionStatus.SUCCEEDED,
            )
            begin_stage(ScanStage.DISCOVERY)
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
            canonical_refs_by_source = {
                row.source_row_index: row.record_ref_key
                for row in catalog_result.records
            }
            engine_records = [
                row.to_dict() for _, row in usable.reset_index(drop=True).iterrows()
            ]
            evaluation_features_by_source = {
                int(record[SOURCE_ROW_INDEX_FIELD]): build_candidate_evaluation_features(
                    record,
                    record_ref_key=canonical_refs_by_source[
                        int(record[SOURCE_ROW_INDEX_FIELD])
                    ],
                )
                for record in engine_records
            }
            evaluation_features_by_ref = {
                item.record_ref_key: item
                for item in evaluation_features_by_source.values()
            }

            def evaluation_features(record):
                try:
                    return evaluation_features_by_source[
                        int(record[SOURCE_ROW_INDEX_FIELD])
                    ]
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        "candidate record is missing canonical evaluation features"
                    ) from exc

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
                feature_a = evaluation_features(pair["record_a"])
                feature_b = evaluation_features(pair["record_b"])
                result = score_candidate(
                    pair["record_a"], pair["record_b"], selected_fields, scan_mode,
                    features_a=feature_a, features_b=feature_b,
                )
                if result["final_score"] >= threshold:
                    standard_write_plan.append(("candidate", pair, result))
                    standard_candidate_pairs.add(canonical_record_pair(
                        pair["record_a"], pair["record_b"], feature_a, feature_b
                    ))
                    candidates_found += 1
                elif result["rule_decision"] != "ALLOW":
                    standard_write_plan.append(("rejection", pair, result))
                    rejections_found += 1

            retrieval = None
            hybrid_write_plan = []
            hybrid_run_values = None
            if self.configuration.hybrid_retrieval_enabled:
                retrieval_input = usable.copy()
                retrieval_input[CANONICAL_RECORD_REF_FIELD] = [
                    canonical_refs_by_source[int(source_row_index)]
                    for source_row_index in retrieval_input[SOURCE_ROW_INDEX_FIELD]
                ]
                retrieval = HybridCandidateRetriever(
                    self.configuration,
                    cache=SqlAlchemyEmbeddingVectorCache(self.db),
                ).retrieve(
                    retrieval_input,
                    scan_mode,
                    standard_candidate_pairs,
                    evaluation_features=evaluation_features_by_ref,
                )
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
                        features_a=evaluation_features(left),
                        features_b=evaluation_features(right),
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
            record_stage(
                ScanStage.DISCOVERY,
                ScanStageExecutionStatus.SUCCEEDED,
                source_reference=source_run_reference(
                    "identity_discovery_run", discovery_run_id
                ),
            )
            begin_stage(ScanStage.SIGNED_EVIDENCE)
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
            record_stage(
                ScanStage.SIGNED_EVIDENCE,
                ScanStageExecutionStatus.SUCCEEDED,
                source_reference=source_run_reference(
                    "identity_evidence_run", evidence_run_id
                ),
            )

            # GF-5C is an internal, non-visible shadow stage. Its service commits
            # either a complete immutable result or a safe FAILED run and never
            # changes the authoritative legacy candidate/G1/G2-v1 path below.
            v2_projection = None
            resolution = None
            begin_stage(ScanStage.GROUP_RESOLUTION)
            try:
                resolution = resolve_and_persist_identity_groups(
                    self.db,
                    scan_id=scan.id,
                    discovery_run_id=discovery_run_id,
                    evidence_run_id=evidence_run_id,
                )
                if resolution.status == "COMPLETED":
                    record_stage(
                        ScanStage.GROUP_RESOLUTION,
                        ScanStageExecutionStatus.SUCCEEDED,
                        source_reference=source_run_reference(
                            "identity_resolution_run", resolution.resolution_run_id
                        ),
                    )
                    begin_stage(ScanStage.G2_V2_PROJECTION)
                    v2_projection = build_and_persist_g2_v2_projection(
                        self.db,
                        scan_id=scan.id,
                        resolution_run_id=resolution.resolution_run_id,
                    )
                    if v2_projection.status == "COMPLETED":
                        record_stage(
                            ScanStage.G2_V2_PROJECTION,
                            ScanStageExecutionStatus.SUCCEEDED,
                            source_reference=source_run_reference(
                                "g2_v2_projection_run",
                                v2_projection.projection_run_id,
                            ),
                        )
                    else:
                        record_stage(
                            ScanStage.G2_V2_PROJECTION,
                            ScanStageExecutionStatus.FAILED,
                            safe_failure_category=(
                                v2_projection.safe_failure_category
                                or "G2_V2_PROJECTION_FAILED"
                            ),
                            source_reference=source_run_reference(
                                "g2_v2_projection_run",
                                v2_projection.projection_run_id,
                            ),
                        )
                        if policy.mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY:
                            raise RuntimeError("required G2-v2 projection failed")
                else:
                    record_stage(
                        ScanStage.GROUP_RESOLUTION,
                        ScanStageExecutionStatus.FAILED,
                        safe_failure_category=(
                            resolution.safe_failure_category
                            or "GROUP_RESOLUTION_FAILED"
                        ),
                        source_reference=source_run_reference(
                            "identity_resolution_run", resolution.resolution_run_id
                        ),
                    )
                    if policy.mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY:
                        raise RuntimeError("required group resolution failed")
            except Exception:
                # Defensive isolation for failures before GF-5C/GF-6B can
                # create their RUNNING checkpoints. GF-4 is already committed.
                self.db.rollback()
                if current_stage is not None:
                    failed_stage = current_stage
                    record_stage(
                        failed_stage,
                        ScanStageExecutionStatus.FAILED,
                        safe_failure_category=f"{failed_stage.value}_FAILED",
                    )
                if policy.mode == ScanOrchestrationMode.GROUP_FIRST_PRIMARY:
                    raise

            v1_projection = None
            if write_policy.write_legacy_pairs:
                begin_stage(ScanStage.LEGACY_PAIR_COMPATIBILITY)
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

            if write_policy.write_g1_projection and write_policy.write_g2_v1_projection:
                current_stage = ScanStage.G2_V1_COMPATIBILITY_PROJECTION
                v1_projection = self.persist_initial_identity_group_projection(
                    scan, usable, selected_fields
                )
                record_stage(
                    ScanStage.LEGACY_PAIR_COMPATIBILITY,
                    ScanStageExecutionStatus.SUCCEEDED,
                )
                projection_reference = source_run_reference(
                    "identity_group_projection_run", v1_projection.projection_run_id
                )
                record_stage(
                    ScanStage.G1_COMPATIBILITY_PROJECTION,
                    ScanStageExecutionStatus.SUCCEEDED,
                    source_reference=projection_reference,
                )
                record_stage(
                    ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
                    ScanStageExecutionStatus.SUCCEEDED,
                    source_reference=projection_reference,
                )
            # GF-7B is explicitly controlled and diagnostic only. It reuses the
            # ordinary current-v1 selector after G2-v1 is complete, and failures
            # cannot alter or suppress that visible result.
            if (
                write_policy.run_shadow_comparison
                and v2_projection is not None
                and v2_projection.status == "COMPLETED"
            ):
                begin_stage(ScanStage.SHADOW_COMPARISON)
                try:
                    current_v1 = IdentityGroupQueryService(self.db).resolve_run(scan.id)
                    if (
                        current_v1 is not None
                        and current_v1.id == v1_projection.projection_run_id
                    ):
                        shadow = build_and_persist_shadow_comparison(
                            self.db,
                            scan_id=scan.id,
                            v1_projection_run_id=current_v1.id,
                            v2_projection_run_id=v2_projection.projection_run_id,
                        )
                        record_stage(
                            ScanStage.SHADOW_COMPARISON,
                            (
                                ScanStageExecutionStatus.SUCCEEDED
                                if shadow.status == "COMPLETED"
                                else ScanStageExecutionStatus.FAILED
                            ),
                            safe_failure_category=shadow.safe_failure_category,
                            source_reference=source_run_reference(
                                "shadow_comparison_run", shadow.comparison_run_id
                            ),
                        )
                    else:
                        record_stage(
                            ScanStage.SHADOW_COMPARISON,
                            ScanStageExecutionStatus.SKIPPED,
                            diagnostic_summary="current G2-v1 projection was unavailable",
                        )
                except Exception:
                    self.db.rollback()
                    if current_stage == ScanStage.SHADOW_COMPARISON:
                        record_stage(
                            ScanStage.SHADOW_COMPARISON,
                            ScanStageExecutionStatus.FAILED,
                            safe_failure_category="SHADOW_COMPARISON_FAILED",
                        )
            orchestration = complete_scan_orchestration(
                self.db,
                orchestration_run_id=orchestration_run_id,
                plan=plan,
            )
            if not orchestration.outcome.visible_product_ready:
                raise RuntimeError("scan orchestration did not produce a visible result")
            warning_count = self.warnings.count_for_scan(scan.id)
            return self.scans.update_status(
                scan,
                "COMPLETED",
                total_records=len(df),
                total_candidates=(candidates_found if write_policy.write_legacy_pairs else 0),
                rejections_count=(rejections_found if write_policy.write_legacy_pairs else 0),
                warnings_count=warning_count,
            ), (len(pairs) if write_policy.write_legacy_pairs else 0)
        except Exception as exc:
            self.db.rollback()
            if evidence_run_id is not None:
                mark_identity_evidence_failed(self.db, evidence_run_id, exc)
                self.db.commit()
            if discovery_run_id is not None:
                mark_discovery_failed(self.db, discovery_run_id, exc)
                self.db.commit()
            if orchestration_run_id is not None:
                try:
                    compatibility_stages = {
                        ScanStage.LEGACY_PAIR_COMPATIBILITY,
                        ScanStage.G1_COMPATIBILITY_PROJECTION,
                        ScanStage.G2_V1_COMPATIBILITY_PROJECTION,
                    }
                    if current_stage in compatibility_stages:
                        for stage in compatibility_stages:
                            record_stage(
                                stage,
                                ScanStageExecutionStatus.FAILED,
                                safe_failure_category="COMPATIBILITY_TRANSACTION_FAILED",
                                diagnostic_summary="compatibility transaction rolled back",
                            )
                    elif current_stage is not None:
                        record_stage(
                            current_stage,
                            ScanStageExecutionStatus.FAILED,
                            safe_failure_category=type(exc).__name__,
                        )
                    complete_scan_orchestration(
                        self.db,
                        orchestration_run_id=orchestration_run_id,
                        plan=plan,
                    )
                except Exception:
                    self.db.rollback()
                    fail_scan_orchestration_audit(
                        self.db, orchestration_run_id=orchestration_run_id
                    )
            self.scans.update_status(scan, "FAILED", total_records=len(df))
            raise
