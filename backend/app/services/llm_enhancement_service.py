import json
from dataclasses import dataclass
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    CandidateDiscoveryMetadata,
    DuplicateCandidate,
    DuplicateScan,
    LlmAdvisorySnapshot,
    LlmEnhancementRun,
    LlmSemanticProfile,
    RecallRescuePair,
    utcnow,
)
from app.engine.scoring import score_candidate
from app.llm.contracts import InventoryRecordEvidence
from app.llm.prompts import INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION
from app.llm.service_contracts import LLMCapability
from app.repositories.candidate_repository import CandidateRepository
from app.services.semantic_enrichment_service import (
    SemanticEnrichmentService,
    bounded_record_evidence,
    compare_semantic_profiles,
    profile_from_json,
    profile_json,
    semantic_evidence_fingerprint,
)


SEMANTIC_RESOLUTION = "SEMANTIC_PROFILE_COMPARISON"
PAIRWISE_RESOLUTION = "PAIRWISE_LLM_FALLBACK"
STANDARD_SOURCE = "DETERMINISTIC_STANDARD"
RECALL_SOURCE = "DETERMINISTIC_RECALL_EXPANSION"


def _candidate_evidence(candidate, side: str) -> InventoryRecordEvidence:
    return bounded_record_evidence(
        f"candidate-{candidate.id}-{side}",
        {
            "PART_NO": getattr(candidate, f"part_no_{side}"),
            "DESCRIPTION": getattr(candidate, f"description_{side}"),
            "CONTRACT": getattr(candidate, f"contract_{side}"),
        },
    )


def _metadata(db: Session, candidate_id: int) -> CandidateDiscoveryMetadata:
    row = db.query(CandidateDiscoveryMetadata).filter_by(candidate_id=candidate_id).first()
    if row is None:
        row = CandidateDiscoveryMetadata(candidate_id=candidate_id, source=STANDARD_SOURCE)
        db.add(row)
        db.flush()
    return row


def discovery_values(metadata: CandidateDiscoveryMetadata | None) -> dict:
    if metadata is None:
        return {
            "candidate_source": STANDARD_SOURCE,
            "resolution_source": None,
            "rescue_score": None,
            "rescue_signals": [],
            "retrieval_sources": [], "retrieval_score": None,
            "retrieval_priority": None, "retrieval_tier": None,
            "lexical_score": None, "vector_score": None, "retrieval_rank": None,
            "description_specificity_score": None, "generic_description_penalty": None,
            "retrieval_conflict_signals": [], "reciprocal_sources": [],
            "uom_relationship": None, "uom_evidence": None,
            "uom_penalty": None, "mapping_quality": None,
            "embedding_model_version": None,
        }
    try:
        signals = json.loads(metadata.signals_json or "[]")
    except (TypeError, json.JSONDecodeError):
        signals = []
    try:
        retrieval_sources = json.loads(metadata.retrieval_sources_json or "[]")
    except (TypeError, json.JSONDecodeError):
        retrieval_sources = []
    def bounded_json_list(attribute, limit=10, width=80):
        try:
            values = json.loads(getattr(metadata, attribute, None) or "[]")
        except (TypeError, json.JSONDecodeError):
            values = []
        return [str(item)[:width] for item in values[:limit]] if isinstance(values, list) else []
    return {
        "candidate_source": metadata.source,
        "resolution_source": metadata.resolution_source,
        "rescue_score": metadata.rescue_score,
        "rescue_signals": [str(item)[:80] for item in signals[:10]] if isinstance(signals, list) else [],
        "retrieval_sources": [str(item)[:40] for item in retrieval_sources[:4]] if isinstance(retrieval_sources, list) else [],
        "retrieval_score": metadata.retrieval_score,
        "retrieval_priority": metadata.retrieval_priority if metadata.retrieval_priority is not None else metadata.retrieval_score,
        "retrieval_tier": metadata.retrieval_tier,
        "lexical_score": metadata.lexical_score,
        "vector_score": metadata.vector_score,
        "description_specificity_score": metadata.description_specificity_score,
        "generic_description_penalty": metadata.generic_description_penalty,
        "retrieval_conflict_signals": bounded_json_list("retrieval_conflict_signals_json"),
        "reciprocal_sources": bounded_json_list("reciprocal_sources_json"),
        "uom_relationship": metadata.uom_relationship,
        "uom_evidence": metadata.uom_evidence,
        "uom_penalty": metadata.uom_penalty,
        "mapping_quality": metadata.mapping_quality,
        "retrieval_rank": metadata.retrieval_rank,
        "embedding_model_version": metadata.embedding_model_version,
    }


def _local_snapshot(db: Session, candidate_id: int, comparison) -> None:
    snapshot = db.query(LlmAdvisorySnapshot).filter_by(
        candidate_id=candidate_id,
        capability=LLMCapability.CANDIDATE_TRIAGE.value,
    ).first()
    if snapshot is None:
        snapshot = LlmAdvisorySnapshot(
            candidate_id=candidate_id,
            capability=LLMCapability.CANDIDATE_TRIAGE.value,
        )
        db.add(snapshot)
    now = utcnow()
    snapshot.state = "AVAILABLE"
    snapshot.llm_used = False
    snapshot.cache_hit = False
    snapshot.provider = "semantic-profile-cache"
    snapshot.prompt_version = INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION
    snapshot.assessment = comparison.assessment
    snapshot.confidence = 1.0 if comparison.assessment != "INCONCLUSIVE" else 0.0
    snapshot.recommended_action = "HUMAN_REVIEW"
    snapshot.supporting_evidence = json.dumps(list(comparison.reason_codes), separators=(",", ":"))
    snapshot.conflicting_evidence = "[]"
    snapshot.safe_error_category = None
    snapshot.deterministic_result_authoritative = True
    snapshot.generated_at = now
    snapshot.updated_at = now


@dataclass
class EnhancementPreparation:
    standard_residual_ids: list[int]
    recall_residuals: list[RecallRescuePair]
    profiles: dict[str, object]


class LlmEnhancementProcessor:
    def __init__(self, configuration: Settings, provider_factory) -> None:
        self.configuration = configuration
        self.enricher = SemanticEnrichmentService(configuration, provider_factory)

    def _run_row(self, db: Session, scan_id: int) -> LlmEnhancementRun:
        row = db.query(LlmEnhancementRun).filter_by(scan_id=scan_id).first()
        if row is None:
            row = LlmEnhancementRun(scan_id=scan_id)
            db.add(row)
            db.flush()
        return row

    async def prepare(self, db: Session, scan_id: int, send_batch) -> EnhancementPreparation:
        run = self._run_row(db, scan_id)
        standard = db.query(DuplicateCandidate).filter_by(scan_id=scan_id).order_by(DuplicateCandidate.id).all()
        standard = [item for item in standard if item.business_status == "POSSIBLE_DUPLICATE_REVIEW"]
        standard = standard[:self.configuration.llm_triage_max_candidates_per_scan]
        pools = db.query(RecallRescuePair).filter_by(scan_id=scan_id, state="PENDING").order_by(RecallRescuePair.rank).all()
        evidence_by_fp = {}
        candidate_fps = {}
        for candidate in standard:
            left, right = _candidate_evidence(candidate, "a"), _candidate_evidence(candidate, "b")
            left_fp = semantic_evidence_fingerprint(left, self.configuration.groq_model)
            right_fp = semantic_evidence_fingerprint(right, self.configuration.groq_model)
            evidence_by_fp.setdefault(left_fp, left)
            evidence_by_fp.setdefault(right_fp, right)
            candidate_fps[candidate.id] = (left_fp, right_fp)
            _metadata(db, candidate.id)
        for pair in pools:
            left = InventoryRecordEvidence.model_validate_json(pair.left_evidence_json)
            right = InventoryRecordEvidence.model_validate_json(pair.right_evidence_json)
            evidence_by_fp.setdefault(pair.left_fingerprint, left)
            evidence_by_fp.setdefault(pair.right_fingerprint, right)

        fingerprints = list(evidence_by_fp)[:self.configuration.llm_semantic_enrichment_max_records_per_scan]
        cached_rows = db.query(LlmSemanticProfile).filter(
            LlmSemanticProfile.evidence_fingerprint.in_(fingerprints),
            LlmSemanticProfile.model == self.configuration.groq_model,
            LlmSemanticProfile.prompt_version == INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
            LlmSemanticProfile.state == "AVAILABLE",
        ).all() if fingerprints else []
        profiles = {}
        for row in cached_rows:
            try:
                profiles[row.evidence_fingerprint] = profile_from_json(row.profile_json)
            except Exception:
                row.state = "FAILED"
                row.safe_error_category = "invalid_provider_output"
        misses = [fp for fp in fingerprints if fp not in profiles]
        run.unique_records_total = len(fingerprints)
        run.profiles_cached = len(profiles)
        run.profiles_requested = len(misses)
        run.enrichment_records_sent = 0
        for fp in misses:
            row = db.query(LlmSemanticProfile).filter_by(
                evidence_fingerprint=fp,
                model=self.configuration.groq_model,
                prompt_version=INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
            ).first()
            if row is None:
                db.add(LlmSemanticProfile(
                    evidence_fingerprint=fp,
                    model=self.configuration.groq_model,
                    prompt_version=INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
                    state="PENDING",
                ))
        db.commit()

        unresolved = list(misses)
        attempted = set()
        processing_paused = False
        batch_size = self.configuration.llm_semantic_enrichment_batch_size
        rounds = [batch_size, max(1, batch_size // 2), 1]
        for size in rounds:
            if not unresolved:
                break
            pending = unresolved
            unresolved = []
            for offset in range(0, len(pending), size):
                chunk_fps = pending[offset:offset + size]
                records = [evidence_by_fp[fp] for fp in chunk_fps]
                try:
                    outcome = await send_batch(self.enricher, records)
                except Exception as exc:
                    unresolved.extend(chunk_fps)
                    attempts = int(getattr(exc, "provider_attempts", 0) or 0)
                    if attempts:
                        attempted.update(chunk_fps)
                        run.enrichment_batches_sent += attempts
                        run.provider_request_count += attempts
                        run.enrichment_records_sent += len(records) * attempts
                    if type(exc).__name__ == "_PauseBeforeAttempt":
                        processing_paused = True
                        unresolved.extend(pending[offset + size:])
                        break
                    continue
                if isinstance(outcome, tuple):
                    result, attempts = outcome
                else:
                    result, attempts = outcome, 1
                attempted.update(chunk_fps)
                run.enrichment_batches_sent += attempts
                run.provider_request_count += attempts
                run.enrichment_records_sent += len(records) * attempts
                by_id = {evidence_by_fp[fp].record_id: fp for fp in chunk_fps}
                for record_id, profile in result.profiles.items():
                    fp = by_id.get(record_id)
                    if fp is None:
                        continue
                    row = db.query(LlmSemanticProfile).filter_by(
                        evidence_fingerprint=fp,
                        model=self.configuration.groq_model,
                        prompt_version=INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
                    ).first()
                    if row is None:
                        row = LlmSemanticProfile(
                            evidence_fingerprint=fp,
                            model=self.configuration.groq_model,
                            prompt_version=INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
                        )
                        db.add(row)
                    row.profile_json = profile_json(profile)
                    row.state = "AVAILABLE"
                    row.safe_error_category = None
                    row.generated_at = utcnow()
                    row.updated_at = utcnow()
                    profiles[fp] = profile
                resolved_fps = {by_id[item] for item in result.profiles if item in by_id}
                unresolved.extend(fp for fp in chunk_fps if fp not in resolved_fps)
                db.commit()
            if processing_paused:
                break

        for fp in unresolved:
            row = db.query(LlmSemanticProfile).filter_by(
                evidence_fingerprint=fp,
                model=self.configuration.groq_model,
                prompt_version=INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
            ).first()
            if row is None:
                row = LlmSemanticProfile(
                    evidence_fingerprint=fp,
                    model=self.configuration.groq_model,
                    prompt_version=INVENTORY_RECORD_ENRICHMENT_PROMPT_VERSION,
                )
                db.add(row)
            if fp in attempted:
                row.state = "FAILED"
                row.profile_json = None
                row.safe_error_category = "invalid_provider_output"
            else:
                row.state = "PENDING"
                row.safe_error_category = None
            row.updated_at = utcnow()
        run.profiles_available = len(profiles)
        run.profiles_failed = sum(fp in attempted for fp in unresolved)

        residual_ids = []
        for candidate in standard:
            left_fp, right_fp = candidate_fps[candidate.id]
            if left_fp in profiles and right_fp in profiles:
                comparison = compare_semantic_profiles(profiles[left_fp], profiles[right_fp])
                if comparison.assessment != "INCONCLUSIVE":
                    _local_snapshot(db, candidate.id, comparison)
                    meta = _metadata(db, candidate.id)
                    meta.resolution_source = SEMANTIC_RESOLUTION
                    run.locally_resolved_count += 1
                    continue
            residual_ids.append(candidate.id)

        recall_residuals = []
        for pair in pools:
            if pair.left_fingerprint in profiles and pair.right_fingerprint in profiles:
                comparison = compare_semantic_profiles(
                    profiles[pair.left_fingerprint], profiles[pair.right_fingerprint]
                )
                if comparison.assessment == "SUPPORTS_NON_DUPLICATE":
                    pair.state = "DISCARDED"
                    continue
                if comparison.assessment == "SUPPORTS_DUPLICATE":
                    self.persist_recall_candidate(db, pair, comparison, SEMANTIC_RESOLUTION)
                    run.locally_resolved_count += 1
                    continue
            recall_residuals.append(pair)
        db.commit()
        return EnhancementPreparation(residual_ids, recall_residuals, profiles)

    def persist_recall_candidate(self, db, pair, comparison, resolution_source):
        left_evidence = InventoryRecordEvidence.model_validate_json(pair.left_evidence_json)
        right_evidence = InventoryRecordEvidence.model_validate_json(pair.right_evidence_json)
        def record(item):
            return {
                "PART_NO": item.part_number or "UNKNOWN",
                "DESCRIPTION": item.description,
                "CONTRACT": item.site_or_contract,
                "UNIT_MEAS": item.uom,
                "PRODUCT_CATEGORY_ID": item.product_category,
                "HSN_SAC_CODE": item.hsn_sac_code,
            }
        left, right = record(left_evidence), record(right_evidence)
        result = score_candidate(left, right, [], "SAME_SITE_DUPLICATE")
        result.update(
            final_score=pair.rescue_score,
            confidence_level="LOW" if pair.rescue_score < 75 else "MEDIUM",
            business_status="POSSIBLE_DUPLICATE_REVIEW",
            rule_decision="ALLOW",
            rejection_reason="",
            critical_mismatches=[],
            explanation="Deterministic recall expansion produced this bounded review candidate.",
        )
        candidate = CandidateRepository(db).save(pair.scan_id, left, right, result)
        db.flush()
        scan = db.query(DuplicateScan).filter_by(id=pair.scan_id).first()
        if scan is not None:
            scan.total_candidates = int(scan.total_candidates or 0) + 1
        candidate.review_status = "UNREVIEWED"
        db.add(CandidateDiscoveryMetadata(
            candidate_id=candidate.id,
            source=RECALL_SOURCE,
            rescue_score=pair.rescue_score,
            rank=pair.rank,
            signals_json=pair.signals_json,
            resolution_source=resolution_source,
        ))
        _local_snapshot(db, candidate.id, comparison)
        pair.state = "PERSISTED"
        run = self._run_row(db, pair.scan_id)
        run.rescue_candidate_count += 1
        if comparison.assessment == "SUPPORTS_DUPLICATE":
            run.rescue_likely_duplicate_count += 1
        elif comparison.assessment == "INCONCLUSIVE":
            run.rescue_human_review_count += 1
        return candidate

    @staticmethod
    def transient_candidate(pair):
        left = InventoryRecordEvidence.model_validate_json(pair.left_evidence_json)
        right = InventoryRecordEvidence.model_validate_json(pair.right_evidence_json)
        return SimpleNamespace(
            id=pair.id,
            part_no_a=left.part_number or "UNKNOWN",
            description_a=left.description,
            contract_a=left.site_or_contract,
            part_no_b=right.part_number or "UNKNOWN",
            description_b=right.description,
            contract_b=right.site_or_contract,
            similarity_score=pair.rescue_score,
            confidence_level="LOW",
            business_status="POSSIBLE_DUPLICATE_REVIEW",
            rule_decision="ALLOW",
            rejection_reason="",
            critical_mismatches="[]",
        )


def enhancement_metrics(db: Session, scan_id: int) -> dict:
    row = db.query(LlmEnhancementRun).filter_by(scan_id=scan_id).first()
    if row is None:
        return {}
    names = (
        "unique_records_total", "profiles_cached", "profiles_requested", "profiles_available",
        "profiles_failed", "enrichment_batches_sent", "provider_request_count",
        "locally_resolved_count", "pairwise_fallback_count", "standard_candidate_count",
        "rescue_pool_considered_count", "rescue_candidate_count", "rescue_likely_duplicate_count",
        "rescue_human_review_count", "rescue_failed_count", "rescue_skipped_by_cap_count",
    )
    values = {name: int(getattr(row, name, 0) or 0) for name in names}
    values["semantic_profiles_cached"] = values["profiles_cached"]
    values["semantic_profiles_generated"] = max(0, values["profiles_available"] - values["profiles_cached"])
    values["semantic_profiles_failed"] = values["profiles_failed"]
    values["average_records_per_batch"] = round(
        (row.enrichment_records_sent / row.enrichment_batches_sent), 2
    ) if row and row.enrichment_batches_sent else 0.0
    return values
