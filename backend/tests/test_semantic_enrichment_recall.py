import asyncio
import csv
import io
import json

import pandas as pd
from pydantic import SecretStr
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import (
    CandidateDiscoveryMetadata,
    DuplicateCandidate,
    DuplicateScan,
    LlmEnhancementRun,
    LlmSemanticProfile,
)
from app.llm.contracts import InventoryRecordEvidence, InventorySemanticProfile
from app.llm.provider import LLMProviderResult
from app.services.llm_enhancement_service import (
    LlmEnhancementProcessor,
    RECALL_SOURCE,
    SEMANTIC_RESOLUTION,
    discovery_values,
    enhancement_metrics,
)
from app.services.llm_export_service import candidates_with_llm_to_csv
from app.services.recall_rescue_service import build_recall_pool, prepare_recall_rescue
from app.services.semantic_enrichment_service import (
    SemanticEnrichmentService,
    bounded_record_evidence,
    compare_semantic_profiles,
    semantic_evidence_fingerprint,
)


def config(**overrides):
    values = dict(
        llm_demo_enabled=True,
        llm_provider="groq",
        groq_api_key=SecretStr("fake-test-key"),
        groq_model="fake-model",
        llm_triage_min_interval_ms=0,
    )
    values.update(overrides)
    return Settings(**values)


class FakeBatchProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete_json(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, json.loads(user_prompt)))
        response = self.responses.pop(0)
        return LLMProviderResult(provider="fake", model="fake-model", content=response)


def profile(record_id, canonical="centrifugal pump", **values):
    payload = dict(
        record_id=record_id,
        canonical_item=canonical,
        product_type="pump",
        purpose="water transfer",
        model=None,
        material=None,
        size_or_dimension=None,
        rating=None,
        side=None,
        placement=None,
        application="process water",
        technical_role="transfer",
        administrative_tokens=[],
        identity_qualifiers=[],
        unknown_terms=[],
        evidence=["bounded description evidence"],
    )
    payload.update(values)
    return payload


def scan(db, threshold=75):
    item = DuplicateScan(
        scan_name="semantic-test", selected_fields="[]", threshold=threshold,
        status="COMPLETED", total_records=2, total_candidates=0,
        model_version="test", scan_mode="SAME_SITE_DUPLICATE",
    )
    db.add(item); db.commit(); db.refresh(item)
    return item


def candidate(db, parent, a="P-100", b="P-101"):
    item = DuplicateCandidate(
        scan_id=parent.id, contract_a="S1", part_no_a=a,
        description_a="Centrifugal water transfer pump 10kW",
        contract_b="S1", part_no_b=b,
        description_b="10 kW centrifugal pump for water transfer",
        similarity_score=72, confidence_level="LOW", description_similarity=75,
        tfidf_score=70, fuzzy_score=82, part_no_similarity=80,
        technical_token_score=100, matched_fields="[]", mismatched_fields="[]",
        explanation="deterministic", recommended_action="review",
        business_status="POSSIBLE_DUPLICATE_REVIEW", rule_decision="ALLOW",
        rejection_reason="", scan_mode="SAME_SITE_DUPLICATE", critical_mismatches="[]",
        variant_attributes_a="{}", variant_attributes_b="{}",
        normalized_description_a="centrifugal water transfer pump 10 kw",
        normalized_description_b="10 kw centrifugal pump water transfer",
        normalized_part_no_a=a.lower(), normalized_part_no_b=b.lower(),
        review_status="UNREVIEWED",
    )
    db.add(item); parent.total_candidates += 1; db.commit(); db.refresh(item)
    return item


def test_batch_contains_independent_bounded_records_only():
    records = [
        bounded_record_evidence("a", {"PART_NO": "A", "DESCRIPTION": "Pump 10 kW"}),
        bounded_record_evidence("b", {"PART_NO": "B", "DESCRIPTION": "Motor 5 kW"}),
    ]
    provider = FakeBatchProvider([{"profiles": [profile("a"), profile("b", "electric motor")]}])
    result = asyncio.run(SemanticEnrichmentService(config(), lambda _: provider).enrich_batch(records))
    assert set(result.profiles) == {"a", "b"}
    sent = provider.calls[0][1]
    assert len(sent["records"]) == 2
    assert not ({"left", "right", "candidate", "group", "edge"} & set(sent))
    assert set(sent["records"][0]) == {
        "record_id", "part_number", "description", "uom", "site_or_contract",
        "product_category", "hsn_sac_code",
    }


def test_partial_batch_keeps_valid_profiles_and_ignores_unknown_ids():
    records = [
        bounded_record_evidence("a", {"DESCRIPTION": "Pump 10 kW"}),
        bounded_record_evidence("b", {"DESCRIPTION": "Pump 11 kW"}),
    ]
    provider = FakeBatchProvider([{"profiles": [profile("a"), profile("unknown"), {"record_id": "b", "invented": True}]}])
    result = asyncio.run(SemanticEnrichmentService(config(), lambda _: provider).enrich_batch(records))
    assert set(result.profiles) == {"a"}
    assert result.unresolved_ids == ("b",)
    assert result.unknown_ids == ("unknown",)


def test_fingerprint_is_stable_order_independent_and_secret_free():
    left = InventoryRecordEvidence(record_id="one", part_number=" P-1 ", description="Pump  10 KW")
    right = InventoryRecordEvidence(record_id="two", description="pump 10 kw", part_number="p-1")
    first = semantic_evidence_fingerprint(left, "model")
    second = semantic_evidence_fingerprint(right, "model")
    assert first == second and len(first) == 64
    assert "P-1" not in first and "Pump" not in first


def test_comparator_duplicate_conflict_and_inconclusive_rules():
    left = InventorySemanticProfile.model_validate(profile("a"))
    same = InventorySemanticProfile.model_validate(profile("b"))
    conflict = InventorySemanticProfile.model_validate(profile("c", material="steel"))
    conflict_left = InventorySemanticProfile.model_validate(profile("d", material="copper"))
    generic_a = InventorySemanticProfile(record_id="e", administrative_tokens=["site 1"])
    generic_b = InventorySemanticProfile(record_id="f", administrative_tokens=["site 1"])
    assert compare_semantic_profiles(left, same).assessment == "SUPPORTS_DUPLICATE"
    compared = compare_semantic_profiles(conflict_left, conflict)
    assert compared.assessment == "SUPPORTS_NON_DUPLICATE"
    assert "MATERIAL_CONFLICT" in compared.reason_codes
    assert compare_semantic_profiles(generic_a, generic_b).assessment == "INCONCLUSIVE"


def test_recall_pool_is_deterministic_bounded_and_blocks_unsafe_pairs():
    frame = pd.DataFrame([
        {"PART_NO": "A-1", "DESCRIPTION": "Centrifugal water transfer pump 10 kw", "CONTRACT": "S1", "UNIT_MEAS": "EA"},
        {"PART_NO": "A-2", "DESCRIPTION": "10 kw centrifugal pump for water transfer", "CONTRACT": "S1", "UNIT_MEAS": "EA"},
        {"PART_NO": "A-1", "DESCRIPTION": "Centrifugal water transfer pump 10 kw", "CONTRACT": "S1", "UNIT_MEAS": "EA"},
        {"PART_NO": "X-9", "DESCRIPTION": "pump", "CONTRACT": "S1", "UNIT_MEAS": "EA"},
        {"PART_NO": "Z-1", "DESCRIPTION": "Centrifugal water transfer pump 10 kw", "CONTRACT": "S1", "UNIT_MEAS": "BOX"},
    ])
    cfg = config(llm_recall_rescue_top_k_per_row=1, llm_recall_rescue_max_candidates_per_scan=1)
    first, skipped = build_recall_pool(frame, scan_id=1, scan_mode="SAME_SITE_DUPLICATE", standard_pairs=set(), excluded_pairs=set(), configuration=cfg)
    second, _ = build_recall_pool(frame, scan_id=1, scan_mode="SAME_SITE_DUPLICATE", standard_pairs=set(), excluded_pairs=set(), configuration=cfg)
    assert first == second and len(first) <= 1 and skipped >= 0
    if first:
        assert first[0]["left"]["PART_NO"] != first[0]["right"]["PART_NO"]
        assert "RECIPROCAL_TOP_K" in first[0]["signals"]


def test_prepare_recall_does_not_change_standard_candidates(db):
    parent = scan(db)
    existing = candidate(db, parent)
    before = (existing.id, existing.similarity_score, existing.business_status, existing.review_status)
    frame = pd.DataFrame([
        {"PART_NO": "R-1", "DESCRIPTION": "Centrifugal water transfer pump 10 kw", "CONTRACT": "S1"},
        {"PART_NO": "R-2", "DESCRIPTION": "10 kw centrifugal pump water transfer", "CONTRACT": "S1"},
    ])
    prepare_recall_rescue(db, parent, frame, config())
    db.refresh(existing)
    assert (existing.id, existing.similarity_score, existing.business_status, existing.review_status) == before
    assert db.query(LlmEnhancementRun).filter_by(scan_id=parent.id).one().standard_candidate_count == 1


def test_processor_batches_unique_records_and_resolves_standard_locally(db):
    parent = scan(db)
    item = candidate(db, parent)
    db.add(LlmEnhancementRun(scan_id=parent.id, standard_candidate_count=1)); db.commit()
    provider = FakeBatchProvider([])
    calls = []

    async def send(service, records):
        calls.append([record.record_id for record in records])
        return await SemanticEnrichmentService(
            config(),
            lambda _: FakeBatchProvider([{"profiles": [profile(record.record_id) for record in records]}]),
        ).enrich_batch(records)

    processor = LlmEnhancementProcessor(config(), lambda _: provider)
    prepared = asyncio.run(processor.prepare(db, parent.id, send))
    assert prepared.standard_residual_ids == []
    assert len(calls) == 1 and len(calls[0]) == 2
    metadata = db.query(CandidateDiscoveryMetadata).filter_by(candidate_id=item.id).one()
    assert metadata.resolution_source == SEMANTIC_RESOLUTION
    assert enhancement_metrics(db, parent.id)["locally_resolved_count"] == 1
    assert item.review_status == "UNREVIEWED" and item.business_status == "POSSIBLE_DUPLICATE_REVIEW"


def test_cross_scan_cache_hit_sends_no_records(db):
    parent = scan(db)
    item = candidate(db, parent)
    db.add(LlmEnhancementRun(scan_id=parent.id)); db.commit()
    cfg = config()
    for side in ("a", "b"):
        evidence = bounded_record_evidence(
            f"seed-{side}",
            {"PART_NO": getattr(item, f"part_no_{side}"), "DESCRIPTION": getattr(item, f"description_{side}"), "CONTRACT": "S1"},
        )
        fp = semantic_evidence_fingerprint(evidence, cfg.groq_model)
        db.add(LlmSemanticProfile(
            evidence_fingerprint=fp, model=cfg.groq_model,
            prompt_version="inventory-record-enrichment-v1", state="AVAILABLE",
            profile_json=json.dumps({k: v for k, v in profile("x").items() if k != "record_id"}),
        ))
    db.commit()

    async def must_not_send(_service, _records):
        raise AssertionError("cached successful profiles must not be resent")

    asyncio.run(LlmEnhancementProcessor(cfg, lambda _: None).prepare(db, parent.id, must_not_send))
    metrics = enhancement_metrics(db, parent.id)
    assert metrics["profiles_cached"] == 2
    assert metrics["provider_request_count"] == 0


def test_cache_only_path_is_safe_with_production_autoflush_disabled(db):
    parent = scan(db)
    item = candidate(db, parent)
    db.add(LlmEnhancementRun(scan_id=parent.id)); db.commit()
    cfg = config()
    for side in ("a", "b"):
        evidence = bounded_record_evidence(
            f"seed-{side}",
            {"PART_NO": getattr(item, f"part_no_{side}"), "DESCRIPTION": getattr(item, f"description_{side}"), "CONTRACT": "S1"},
        )
        db.add(LlmSemanticProfile(
            evidence_fingerprint=semantic_evidence_fingerprint(evidence, cfg.groq_model),
            model=cfg.groq_model, prompt_version="inventory-record-enrichment-v1",
            state="AVAILABLE",
            profile_json=json.dumps({k: v for k, v in profile("x").items() if k != "record_id"}),
        ))
    db.commit()
    production_session = sessionmaker(bind=db.get_bind(), autoflush=False)()
    async def must_not_send(_service, _records):
        raise AssertionError("cache-only path must not call provider")
    try:
        asyncio.run(LlmEnhancementProcessor(cfg, lambda _: None).prepare(
            production_session, parent.id, must_not_send
        ))
    finally:
        production_session.close()
    assert db.query(CandidateDiscoveryMetadata).filter_by(candidate_id=item.id).count() == 1


def test_recall_candidate_provenance_and_human_boundary(db):
    parent = scan(db)
    processor = LlmEnhancementProcessor(config(), lambda _: None)
    from app.db.models import RecallRescuePair
    left = bounded_record_evidence("l", {"PART_NO": "R-1", "DESCRIPTION": "Centrifugal pump 10 kw", "CONTRACT": "S1"})
    right = bounded_record_evidence("r", {"PART_NO": "R-2", "DESCRIPTION": "10 kw centrifugal pump", "CONTRACT": "S1"})
    pair = RecallRescuePair(
        scan_id=parent.id,
        left_fingerprint=semantic_evidence_fingerprint(left, "fake-model"),
        right_fingerprint=semantic_evidence_fingerprint(right, "fake-model"),
        left_evidence_json=left.model_dump_json(), right_evidence_json=right.model_dump_json(),
        rescue_score=68, rank=1, signals_json='["TFIDF_DESCRIPTION","FUZZY_DESCRIPTION"]',
    )
    db.add(pair); db.commit()
    from app.services.semantic_enrichment_service import SemanticComparison
    created = processor.persist_recall_candidate(
        db, pair, SemanticComparison("SUPPORTS_DUPLICATE", ("SEMANTIC_EQUIVALENCE",)), SEMANTIC_RESOLUTION
    )
    db.commit()
    metadata = db.query(CandidateDiscoveryMetadata).filter_by(candidate_id=created.id).one()
    assert discovery_values(metadata)["candidate_source"] == RECALL_SOURCE
    assert created.business_status == "POSSIBLE_DUPLICATE_REVIEW"
    assert created.review_status == "UNREVIEWED"
    assert created.reviewed_by is None and created.reviewed_at is None


def test_enhanced_export_appends_provenance_without_provider_call(db):
    parent = scan(db)
    item = candidate(db, parent)
    metadata = CandidateDiscoveryMetadata(
        candidate_id=item.id, source=RECALL_SOURCE, rescue_score=67, rank=1,
        signals_json='["TFIDF_DESCRIPTION"]', resolution_source=SEMANTIC_RESOLUTION,
    )
    db.add(metadata); db.commit()
    text = candidates_with_llm_to_csv([item], {}, {}, "COMPLETED", {item.id: metadata})
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["candidate_source"] == RECALL_SOURCE
    assert rows[0]["resolution_source"] == SEMANTIC_RESOLUTION
    assert rows[0]["semantic_profile_prompt_version"] == "inventory-record-enrichment-v1"
    assert list(rows[0])[-5:] == [
        "candidate_source", "rescue_score", "rescue_signals", "resolution_source",
        "semantic_profile_prompt_version",
    ]
