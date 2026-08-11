import csv
import io
import json

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import event

from app.core.config import Settings
from app.db.models import CandidateDiscoveryMetadata, DuplicateCandidate, HybridRetrievalRun, LocalEmbeddingCache
from app.services.hybrid_retrieval import (
    CHANNEL_WEIGHTS, RRF_K, HybridCandidateRetriever, MemoryEmbeddingVectorCache,
    RetrievalSource, RetrievalTier, SklearnHashingEmbedder, canonical_record_pair,
    description_specificity_statistics, part_number_family_keys,
)
from app.services.hybrid_retrieval_benchmark import (
    SILVER_PART_PAIRS, evaluate_retrieval_benchmark, ranking_v2_fixture,
)
from app.services.llm_enhancement_service import discovery_values
from app.services.llm_export_service import candidates_with_llm_to_csv
from app.services.scan_runner import ScanRunner


def frame(rows):
    return pd.DataFrame([
        {"PART_NO": part, "DESCRIPTION": description, "CONTRACT": site, "UNIT_MEAS": "EA", **extra}
        for part, description, site, extra in rows
    ])


def cfg(**values):
    defaults = dict(
        llm_provider="none", llm_demo_enabled=False,
        hybrid_retrieval_enabled=True, hybrid_retrieval_min_score=40,
        hybrid_retrieval_lexical_top_k=2, hybrid_retrieval_vector_top_k=2,
        hybrid_retrieval_final_top_k=2, hybrid_retrieval_max_pairs_per_scan=10,
    )
    defaults.update(values)
    return Settings(**defaults)


class FakeEmbedder:
    model_version = "fake-char-vector-v1"
    def __init__(self): self.calls = 0
    def encode(self, texts):
        self.calls += 1
        values = []
        for text in texts:
            if "bearing" in text or "brg" in text: values.append([1, 0, 0])
            elif "paint" in text: values.append([0, 1, 0])
            else: values.append([0, 0, 1])
        return np.asarray(values, dtype=np.float32)


def semantic_fixture():
    return frame([
        ("A1", "MILK SOAP", "S1", {}),
        ("A2", "Milk-Soap", "S1", {}),
        ("B1", "MTR BRG DE 6205", "S1", {}),
        ("B2", "Motor Drive End Bearing 6205", "S1", {}),
        ("C1", "RED PAINT 1L", "S1", {}),
        ("C2", "BLUE PAINT 1L", "S1", {}),
        ("D1", "BRACKET", "S1", {}),
        ("D2", "BRACKET", "S1", {}),
    ])


def pairs(result):
    return {(item.left_record_id, item.right_record_id): item for item in result.candidates}


def test_feature_disabled_preserves_standard_candidate_output(db):
    data = frame([("A", "Milk Soap", "S1", {}), ("B", "Milk-Soap", "S1", {})])
    scan, _ = ScanRunner(db, cfg(hybrid_retrieval_enabled=False)).run(data, "disabled", ["CONTRACT"], 60)
    rows = db.query(DuplicateCandidate).filter_by(scan_id=scan.id).all()
    assert len(rows) == 1
    assert db.query(HybridRetrievalRun).filter_by(scan_id=scan.id).count() == 0
    assert rows[0].similarity_score == 85.0


def test_standard_candidates_are_not_duplicated_by_hybrid(db):
    data = frame([("A", "Milk Soap", "S1", {}), ("B", "Milk-Soap", "S1", {})])
    scan, _ = ScanRunner(db, cfg()).run(data, "dedupe", ["CONTRACT"], 60)
    assert db.query(DuplicateCandidate).filter_by(scan_id=scan.id).count() == 1
    assert db.query(CandidateDiscoveryMetadata).count() == 0


def test_blocking_is_separate_from_positive_exact_description_evidence():
    data = frame([("A", "MILK SOAP", "S1", {}), ("B", "Milk-Soap", "S1", {})])
    retriever = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder(), cache=MemoryEmbeddingVectorCache())
    first = retriever.retrieve(data, "SAME_SITE_DUPLICATE")
    second = retriever.retrieve(data, "SAME_SITE_DUPLICATE")
    assert first.candidates == second.candidates
    assert first.candidates[0].left_record_id < first.candidates[0].right_record_id
    assert "EXACT_DESCRIPTION" in first.candidates[0].evidence.retrieval_sources
    assert "EXACT_BLOCK" not in first.candidates[0].evidence.retrieval_sources
    assert "SAME_SITE_SCOPE" in first.candidates[0].evidence.blocking_signals
    assert not set(first.candidates[0].evidence.blocking_signals) & set(CHANNEL_WEIGHTS)


def test_lexical_and_vector_top_k_are_bounded():
    result = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder()).retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    assert result.metrics.max_candidates_for_any_record <= 2
    assert result.metrics.average_candidates_per_record <= 2


def test_fake_vector_ordering_is_repeatable_and_semantic_pair_is_found():
    retriever = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder(), cache=MemoryEmbeddingVectorCache())
    first = retriever.retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    second = retriever.retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    assert [(c.left_record_id, c.right_record_id) for c in first.candidates] == [(c.left_record_id, c.right_record_id) for c in second.candidates]
    assert (2, 3) in pairs(first)
    assert "CHAR_VECTOR" in pairs(first)[(2, 3)].evidence.retrieval_sources


def test_merge_retains_multi_source_evidence_and_deterministic_ranking():
    result = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder()).retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    item = pairs(result)[(2, 3)]
    assert item.retrieval_source == RetrievalSource.MULTI_SOURCE
    assert tuple(c.retrieval_rank for c in result.candidates) == tuple(range(1, len(result.candidates) + 1))


def test_hard_variant_conflict_is_blocked_even_with_vector_similarity():
    result = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder()).retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    assert (4, 5) not in pairs(result)


def test_same_site_and_cross_site_policies_are_explicit():
    data = frame([("A", "Milk Soap", "S1", {}), ("B", "Milk Soap", "S2", {})])
    retriever = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder())
    assert not retriever.retrieve(data, "SAME_SITE_DUPLICATE").candidates
    assert retriever.retrieve(data, "CROSS_SITE_STANDARDIZATION").candidates


def test_accounting_mapping_difference_does_not_block_identity_candidate():
    data = frame([
        ("A", "Milk Soap", "S1", {"ACCOUNTING_GROUP": "100"}),
        ("B", "Milk Soap", "S1", {"ACCOUNTING_GROUP": "200"}),
    ])
    assert HybridCandidateRetriever(cfg(), embedder=FakeEmbedder()).retrieve(data, "SAME_SITE_DUPLICATE").candidates


def test_final_scan_cap_and_per_record_cap_are_enforced():
    data = frame([(str(i), f"bearing motor {i}", "S1", {}) for i in range(12)])
    result = HybridCandidateRetriever(cfg(hybrid_retrieval_final_top_k=1, hybrid_retrieval_max_pairs_per_scan=3), embedder=FakeEmbedder()).retrieve(data, "SAME_SITE_DUPLICATE")
    assert len(result.candidates) <= 3
    assert result.metrics.max_candidates_for_any_record <= 1


def test_no_provider_required_and_no_all_pairs_materialized():
    result = HybridCandidateRetriever(cfg(llm_provider="none"), embedder=FakeEmbedder()).retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    assert result.metrics.provider_request_count == 0
    assert len(result.candidates) <= len(semantic_fixture()) * 2


def test_embedding_cache_prevents_recomputation():
    embedder = FakeEmbedder(); cache = MemoryEmbeddingVectorCache()
    retriever = HybridCandidateRetriever(cfg(), embedder=embedder, cache=cache)
    retriever.retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    retriever.retrieve(semantic_fixture(), "SAME_SITE_DUPLICATE")
    assert embedder.calls == 1


def test_hybrid_pair_enters_deterministic_scoring_and_human_boundary(db):
    data = frame([
        ("B1", "MTR BRG DE 6205", "S1", {}),
        ("B2", "Motor Drive End Bearing 6205", "S1", {}),
    ])
    scan, _ = ScanRunner(db, cfg()).run(data, "semantic", ["CONTRACT"], 75)
    item = db.query(DuplicateCandidate).filter_by(scan_id=scan.id).one()
    metadata = db.query(CandidateDiscoveryMetadata).filter_by(candidate_id=item.id).one()
    assert metadata.source == "HYBRID_RETRIEVAL"
    assert item.similarity_score < 75
    assert item.business_status != "LIKELY_DUPLICATE"
    assert item.review_status == "UNREVIEWED" and item.reviewed_by is None


def test_generic_similarity_is_not_automatic_duplicate(db):
    data = frame([("D1", "PART", "S1", {}), ("D2", "PART", "S1", {})])
    scan, _ = ScanRunner(db, cfg()).run(data, "generic", ["CONTRACT"], 90)
    item = db.query(DuplicateCandidate).filter_by(scan_id=scan.id).one()
    assert item.business_status != "LIKELY_DUPLICATE"
    assert item.review_status == "UNREVIEWED"


def test_sqlite_vector_cache_records_model_and_reuses_vectors(db):
    data = semantic_fixture().head(2)
    ScanRunner(db, cfg()).run(data, "cache", ["CONTRACT"], 99)
    rows = db.query(LocalEmbeddingCache).all()
    assert len(rows) == 1
    assert all(row.embedding_model_version == "sklearn-hashing-domain-v1" and row.state == "AVAILABLE" for row in rows)


def test_provenance_and_enhanced_export_are_safe(db):
    data = frame([("B1", "MTR BRG DE 6205", "S1", {}), ("B2", "Motor Drive End Bearing 6205", "S1", {})])
    scan, _ = ScanRunner(db, cfg()).run(data, "export", ["CONTRACT"], 75)
    item = db.query(DuplicateCandidate).filter_by(scan_id=scan.id).one()
    metadata = db.query(CandidateDiscoveryMetadata).filter_by(candidate_id=item.id).one()
    values = discovery_values(metadata)
    assert values["candidate_source"] == "HYBRID_RETRIEVAL"
    text = candidates_with_llm_to_csv([item], {}, {}, "NOT_STARTED", {item.id: metadata})
    row = next(csv.DictReader(io.StringIO(text)))
    assert row["candidate_source"] == "HYBRID_RETRIEVAL"
    assert row["retrieval_sources"] and row["embedding_model_version"] == "sklearn-hashing-domain-v1"
    assert row["retrieval_tier"] in {"TIER_A", "TIER_B", "TIER_C"}
    assert row["retrieval_priority"] and row["description_specificity_score"]
    assert row["retrieval_conflict_signals"] is not None and row["reciprocal_sources"] is not None


def test_description_specificity_is_deterministic_and_rewards_rare_informative_text():
    corpus = ["B38 Engine Fuel Pump", "PART", "PART", "PART", "PART"]
    first = description_specificity_statistics(corpus)
    second = description_specificity_statistics(corpus)
    assert first == second
    assert first[0].score > first[1].score
    assert first[0].generic_penalty < first[1].generic_penalty
    assert "GENERIC_DESCRIPTION" in first[1].reasons
    assert "HIGH_DESCRIPTION_FREQUENCY" in first[1].reasons


def test_part_number_family_uses_normalized_aliases_not_superficial_prefixes():
    examples = [
        ("AS-B38-FP", "ES/AS-B38-FP"),
        ("AS-COM-STAT", "KA/ASCOMSTAT1"),
        ("AS-COM-ROT", "KA/ASCOMROT1"),
        ("KM-FP", "KM/FUELPUMP"),
    ]
    for left, right in examples:
        assert set(part_number_family_keys(left)) & set(part_number_family_keys(right))
    assert not (set(part_number_family_keys("BOARD-1")) & set(part_number_family_keys("BOARD-2")))


def test_technical_identity_channel_requires_shared_extracted_identity():
    data = frame([
        ("X1", "Bearing 6205", "S1", {}),
        ("X2", "Motor Bearing 6205", "S1", {}),
        ("X3", "Motor Housing", "S1", {}),
    ])
    result = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder()).retrieve(data, "SAME_SITE_DUPLICATE")
    assert "TECHNICAL_IDENTITY" in pairs(result)[(0, 1)].evidence.retrieval_sources
    if (1, 2) in pairs(result):
        assert "TECHNICAL_IDENTITY" not in pairs(result)[(1, 2)].evidence.retrieval_sources


def test_soft_opposite_variant_conflict_is_penalized_and_never_tier_a():
    data = frame([
        ("SERIAL-A", "KM Rental Part Serial", "S1", {}),
        ("SERIAL-B", "KM Rental Part Non Serial", "S1", {}),
    ])
    item = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder()).retrieve(
        data, "SAME_SITE_DUPLICATE"
    ).candidates[0]
    assert "OPPOSITE_VARIANT_TERM" in item.evidence.conflict_signals
    assert item.retrieval_tier == RetrievalTier.TIER_C
    assert item.retrieval_priority < 20


def test_rrf_priorities_do_not_saturate_and_constants_are_bounded():
    result = HybridCandidateRetriever(cfg(
        hybrid_retrieval_max_pairs_per_scan=20,
        hybrid_retrieval_final_top_k=5,
    )).retrieve(ranking_v2_fixture(), "SAME_SITE_DUPLICATE")
    priorities = [candidate.retrieval_priority for candidate in result.candidates]
    assert RRF_K == 60 and set(CHANNEL_WEIGHTS) == {
        "EXACT_DESCRIPTION", "PART_NUMBER_FAMILY", "LEXICAL", "CHAR_VECTOR", "TECHNICAL_IDENTITY",
    }
    assert len(set(priorities)) > 3
    assert not all(priority == 100 for priority in priorities)
    assert priorities == sorted(priorities, reverse=True) or any(
        result.candidates[index - 1].retrieval_tier != result.candidates[index].retrieval_tier
        for index in range(1, len(result.candidates))
    )


def test_reciprocal_neighbours_receive_bounded_explicit_evidence():
    data = frame([
        ("A1", "Francis Turbine Lower Bearing", "S1", {}),
        ("A2", "Francis Turbine Lower Bearing", "S1", {}),
    ])
    item = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder()).retrieve(
        data, "SAME_SITE_DUPLICATE"
    ).candidates[0]
    assert "LEXICAL_RECIPROCAL" in item.evidence.reciprocal_sources
    assert "CHAR_VECTOR_RECIPROCAL" in item.evidence.reciprocal_sources
    assert item.retrieval_priority < 100


def test_tier_assignment_and_tie_breaking_are_stable():
    data = ranking_v2_fixture()
    retriever = HybridCandidateRetriever(cfg(
        hybrid_retrieval_max_pairs_per_scan=20,
        hybrid_retrieval_final_top_k=5,
        hybrid_retrieval_family_max=3,
    ), cache=MemoryEmbeddingVectorCache())
    first = retriever.retrieve(data, "SAME_SITE_DUPLICATE")
    second = retriever.retrieve(data, "SAME_SITE_DUPLICATE")
    signature = lambda result: [
        (item.left_record_id, item.right_record_id, item.retrieval_priority, item.retrieval_tier)
        for item in result.candidates
    ]
    assert signature(first) == signature(second)
    assert {item.retrieval_tier for item in first.candidates} >= {
        RetrievalTier.TIER_A, RetrievalTier.TIER_B, RetrievalTier.TIER_C,
    }


def test_tier_a_silver_pairs_survive_global_cap_pressure():
    data = ranking_v2_fixture()
    result = HybridCandidateRetriever(cfg(
        hybrid_retrieval_max_pairs_per_scan=4,
        hybrid_retrieval_tier_a_max=4,
        hybrid_retrieval_tier_b_max=0,
        hybrid_retrieval_tier_c_max=0,
        hybrid_retrieval_final_top_k=5,
    )).retrieve(data, "SAME_SITE_DUPLICATE")
    records = data.to_dict("records")
    retained = {
        frozenset((records[item.left_record_id]["PART_NO"], records[item.right_record_id]["PART_NO"]))
        for item in result.candidates
    }
    assert retained == set(SILVER_PART_PAIRS)
    assert all(item.retrieval_tier == RetrievalTier.TIER_A for item in result.candidates)


def test_description_family_fairness_prevents_generic_domination():
    data = frame([(f"TIME-{index}", "Normal Time", "S1", {}) for index in range(10)])
    result = HybridCandidateRetriever(cfg(
        hybrid_retrieval_max_pairs_per_scan=20,
        hybrid_retrieval_tier_b_max=20,
        hybrid_retrieval_tier_c_max=20,
        hybrid_retrieval_family_max=2,
        hybrid_retrieval_final_top_k=10,
    )).retrieve(data, "SAME_SITE_DUPLICATE")
    assert len(result.candidates) <= 2
    assert result.metrics.largest_description_family_candidates <= 2
    assert result.metrics.candidate_family_concentration <= 1


def test_offline_quality_benchmark_recovers_silver_and_demotes_generic():
    data = ranking_v2_fixture()
    result = HybridCandidateRetriever(cfg(
        hybrid_retrieval_max_pairs_per_scan=20,
        hybrid_retrieval_tier_a_max=10,
        hybrid_retrieval_tier_b_max=8,
        hybrid_retrieval_tier_c_max=2,
        hybrid_retrieval_family_max=3,
        hybrid_retrieval_final_top_k=5,
    )).retrieve(data, "SAME_SITE_DUPLICATE")
    report = evaluate_retrieval_benchmark(data, result)
    assert report.silver_recall_at_global_budget == 1
    assert report.silver_recall_at_top_k == 1
    assert report.tier_a_silver_recall == 1
    assert report.provider_request_count == 0
    assert report.distinct_priorities > 3
    assert report.largest_family_share <= 0.25


def test_real_data_regression_equivalents_rank_ahead_of_normal_time():
    data = ranking_v2_fixture()
    result = HybridCandidateRetriever(cfg(
        hybrid_retrieval_max_pairs_per_scan=20,
        hybrid_retrieval_final_top_k=5,
        hybrid_retrieval_family_max=3,
    )).retrieve(data, "SAME_SITE_DUPLICATE")
    records = data.to_dict("records")
    by_parts = {
        frozenset((records[item.left_record_id]["PART_NO"], records[item.right_record_id]["PART_NO"])): item
        for item in result.candidates
    }
    for silver in SILVER_PART_PAIRS:
        assert silver in by_parts
    rotor = by_parts[frozenset(("AS-COM-ROT", "KA/ASCOMROT1"))]
    normal_time = [
        item for item in result.candidates
        if records[item.left_record_id]["DESCRIPTION"] == records[item.right_record_id]["DESCRIPTION"] == "Normal Time"
    ]
    assert rotor.retrieval_tier == RetrievalTier.TIER_A
    assert all(item.retrieval_tier != RetrievalTier.TIER_A for item in normal_time)
    assert all(rotor.retrieval_priority > item.retrieval_priority for item in normal_time)


def test_provider_none_and_no_semantic_enrichment_are_required_for_benchmark():
    configuration = cfg(
        llm_provider="none",
        llm_semantic_enrichment_enabled=False,
        llm_recall_rescue_enabled=False,
        hybrid_retrieval_max_pairs_per_scan=8,
    )
    result = HybridCandidateRetriever(configuration).retrieve(
        ranking_v2_fixture(), "SAME_SITE_DUPLICATE"
    )
    assert result.candidates
    assert result.metrics.provider_request_count == 0


def test_scan_api_batches_v2_provenance_and_exposes_quality_metrics(client, db):
    data = frame([
        ("AS-B38-FP", "B38 Engine Fuel Pump", "S1", {}),
        ("ES/AS-B38-FP", "B38 Engine Fuel Pump", "S1", {}),
        ("AS-COM-STAT", "F30 Engine Compressor Stator", "S1", {}),
        ("KA/ASCOMSTAT1", "F30 Engine Compressor Stator", "S1", {}),
    ])
    scan, _ = ScanRunner(db, cfg(hybrid_retrieval_max_pairs_per_scan=10)).run(
        data, "api-v2", ["CONTRACT"], 99
    )
    statements = []

    def before_cursor_execute(*args):
        statements.append(args[2])

    event.listen(db.bind, "before_cursor_execute", before_cursor_execute)
    try:
        response = client.get(f"/api/scans/{scan.id}/candidates")
    finally:
        event.remove(db.bind, "before_cursor_execute", before_cursor_execute)
    assert response.status_code == 200
    hybrid = [row for row in response.json() if row["candidate_source"] == "HYBRID_RETRIEVAL"]
    assert hybrid
    assert len(statements) <= 6
    assert any(row["retrieval_tier"] == "TIER_A" for row in hybrid)
    assert all(row["retrieval_tier"] in {"TIER_A", "TIER_B", "TIER_C"} for row in hybrid)
    assert all(row["retrieval_priority"] is not None for row in hybrid)
    assert all("EXACT_BLOCK" not in row["retrieval_sources"] for row in hybrid)
    metrics = client.get(f"/api/scans/{scan.id}").json()["hybrid_retrieval"]
    assert metrics["tier_a_candidates"] >= 1
    assert "char_vector_candidates_generated" in metrics
    assert "candidate_family_concentration" in metrics


def test_tier_and_family_budget_settings_are_tightly_bounded():
    with pytest.raises(ValueError):
        Settings(hybrid_retrieval_tier_a_max=-1)
    with pytest.raises(ValueError):
        Settings(hybrid_retrieval_tier_b_max=5001)
    with pytest.raises(ValueError):
        Settings(hybrid_retrieval_family_max=0)
    assert Settings(
        hybrid_retrieval_tier_a_max=250,
        hybrid_retrieval_tier_b_max=200,
        hybrid_retrieval_tier_c_max=50,
        hybrid_retrieval_family_max=25,
    ).hybrid_retrieval_tier_c_max == 50
