import csv
import io
import json

import numpy as np
import pandas as pd

from app.core.config import Settings
from app.db.models import CandidateDiscoveryMetadata, DuplicateCandidate, HybridRetrievalRun, LocalEmbeddingCache
from app.services.hybrid_retrieval import (
    HybridCandidateRetriever, MemoryEmbeddingVectorCache, RetrievalSource,
    SklearnHashingEmbedder, canonical_record_pair,
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
    model_version = "fake-semantic-v1"
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


def test_exact_block_is_deterministic_and_canonical():
    data = frame([("A", "MILK SOAP", "S1", {}), ("B", "Milk-Soap", "S1", {})])
    retriever = HybridCandidateRetriever(cfg(), embedder=FakeEmbedder(), cache=MemoryEmbeddingVectorCache())
    first = retriever.retrieve(data, "SAME_SITE_DUPLICATE")
    second = retriever.retrieve(data, "SAME_SITE_DUPLICATE")
    assert first.candidates == second.candidates
    assert first.candidates[0].left_record_id < first.candidates[0].right_record_id
    assert "EXACT_BLOCK" in first.candidates[0].evidence.retrieval_sources


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
    assert "VECTOR" in pairs(first)[(2, 3)].evidence.retrieval_sources


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
