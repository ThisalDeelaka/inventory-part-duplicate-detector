import hashlib
import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import normalize
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import LocalEmbeddingCache, utcnow
from app.engine.business_rules import evaluate_hard_business_rules
from app.engine.normalizer import extract_technical_tokens, normalize_description, normalize_part_no_with_dictionary
from app.engine.variant_extractor import extract_variant_attributes, find_critical_mismatches


class RetrievalSource(str, Enum):
    EXACT_BLOCK = "EXACT_BLOCK"
    LEXICAL = "LEXICAL"
    VECTOR = "VECTOR"
    MULTI_SOURCE = "MULTI_SOURCE"


@dataclass(frozen=True)
class RetrievalEvidence:
    retrieval_sources: tuple[str, ...]
    lexical_score: float
    vector_score: float
    blocking_signals: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalCandidate:
    left_record_id: int
    right_record_id: int
    retrieval_score: float
    retrieval_rank: int
    retrieval_source: RetrievalSource
    evidence: RetrievalEvidence


@dataclass(frozen=True)
class RetrievalMetrics:
    records_indexed: int
    lexical_candidates_generated: int
    vector_candidates_generated: int
    multi_source_candidates: int
    hybrid_candidates_skipped_by_cap: int
    average_candidates_per_record: float
    max_candidates_for_any_record: int
    retrieval_runtime_ms: float
    provider_request_count: int = 0


@dataclass(frozen=True)
class HybridRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    metrics: RetrievalMetrics
    embedding_model_version: str


class LocalEmbedder(Protocol):
    model_version: str
    def encode(self, texts: list[str]) -> np.ndarray: ...


_RETRIEVAL_ALIASES = {
    "mtr": "motor", "brg": "bearing", "de": "drive end", "nde": "non drive end",
    "assy": "assembly", "bkt": "bracket", "pnl": "panel", "vlv": "valve",
}


def semantic_retrieval_text(record: dict) -> str:
    normalized = normalize_description(record.get("DESCRIPTION", ""))
    expanded = []
    for token in normalized.split():
        expanded.extend(_RETRIEVAL_ALIASES.get(token, token).split())
    return " ".join(expanded)


class SklearnHashingEmbedder:
    """Offline, fixed-feature local embedding; no fit, network or provider call."""
    def __init__(self, model_version: str = "sklearn-hashing-domain-v1") -> None:
        self.model_version = model_version
        self._vectorizer = HashingVectorizer(
            n_features=384, analyzer="char_wb", ngram_range=(3, 5),
            alternate_sign=False, norm="l2", lowercase=False,
        )

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        return self._vectorizer.transform(texts).astype(np.float32).toarray()


class EmbeddingVectorCache(Protocol):
    def load(self, fingerprints: list[str], model_version: str) -> dict[str, np.ndarray]: ...
    def save(self, vectors: dict[str, np.ndarray], model_version: str) -> None: ...


class SqlAlchemyEmbeddingVectorCache:
    def __init__(self, db: Session) -> None:
        self.db = db

    def load(self, fingerprints: list[str], model_version: str) -> dict[str, np.ndarray]:
        rows = self.db.query(LocalEmbeddingCache).filter(
            LocalEmbeddingCache.record_fingerprint.in_(fingerprints),
            LocalEmbeddingCache.embedding_model_version == model_version,
            LocalEmbeddingCache.state == "AVAILABLE",
        ).all() if fingerprints else []
        result = {}
        for row in rows:
            try:
                vector = np.asarray(json.loads(row.vector_json), dtype=np.float32)
                if vector.shape == (384,):
                    result[row.record_fingerprint] = vector
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return result

    def save(self, vectors: dict[str, np.ndarray], model_version: str) -> None:
        for fingerprint, vector in vectors.items():
            row = self.db.query(LocalEmbeddingCache).filter_by(
                record_fingerprint=fingerprint,
                embedding_model_version=model_version,
            ).first()
            if row is None:
                row = LocalEmbeddingCache(
                    record_fingerprint=fingerprint,
                    embedding_model_version=model_version,
                )
                self.db.add(row)
            row.vector_json = json.dumps(
                [round(float(value), 7) for value in vector], separators=(",", ":")
            )
            row.state = "AVAILABLE"
            row.generated_at = utcnow()
        self.db.flush()


class MemoryEmbeddingVectorCache:
    def __init__(self) -> None:
        self.values = {}
    def load(self, fingerprints, model_version):
        return {fp: self.values[(fp, model_version)] for fp in fingerprints if (fp, model_version) in self.values}
    def save(self, vectors, model_version):
        for fp, vector in vectors.items(): self.values[(fp, model_version)] = vector


def record_fingerprint(text: str) -> str:
    return hashlib.sha256(("hybrid-record-v1\0" + text).encode("utf-8")).hexdigest()


def record_identity_key(record: dict) -> tuple[str, str, str]:
    return (
        str(record.get("CONTRACT") or "").strip().casefold(),
        normalize_part_no_with_dictionary(record.get("PART_NO", "")),
        normalize_description(record.get("DESCRIPTION", "")),
    )


def canonical_record_pair(left: dict, right: dict):
    return tuple(sorted((record_identity_key(left), record_identity_key(right))))


def _part_root(value) -> str:
    normalized = normalize_part_no_with_dictionary(value).replace(" ", "")
    return re.sub(r"[-_/]?\d+$", "", normalized)


def _allowed_pair(left: dict, right: dict, scan_mode: str) -> bool:
    if record_identity_key(left) == record_identity_key(right):
        return False
    left_part = normalize_part_no_with_dictionary(left.get("PART_NO", ""))
    right_part = normalize_part_no_with_dictionary(right.get("PART_NO", ""))
    if left_part and left_part == right_part:
        return False
    left_site = str(left.get("CONTRACT") or "").strip().casefold()
    right_site = str(right.get("CONTRACT") or "").strip().casefold()
    if scan_mode == "SAME_SITE_DUPLICATE" and left_site and right_site and left_site != right_site:
        return False
    if scan_mode == "CROSS_SITE_STANDARDIZATION" and left_site and right_site and left_site == right_site:
        return False
    if evaluate_hard_business_rules(left, right, scan_mode)["blocked"]:
        return False
    if find_critical_mismatches(
        extract_variant_attributes(left.get("DESCRIPTION")),
        extract_variant_attributes(right.get("DESCRIPTION")),
    ):
        return False
    return True


def _nearest(matrix, top_k: int):
    count = matrix.shape[0]
    if count < 2:
        return []
    neighbours = min(count, top_k + 1)
    index = NearestNeighbors(n_neighbors=neighbours, metric="cosine", algorithm="brute")
    index.fit(matrix)
    output = []
    batch_size = 256
    for start in range(0, count, batch_size):
        distances, indices = index.kneighbors(matrix[start:start + batch_size])
        for offset, (row_distances, row_indices) in enumerate(zip(distances, indices)):
            source = start + offset
            for distance, target in zip(row_distances, row_indices):
                if source == int(target):
                    continue
                output.append((source, int(target), round(max(0.0, 1.0 - float(distance)) * 100, 2)))
    return output


class HybridCandidateRetriever:
    def __init__(self, configuration: Settings, embedder: LocalEmbedder | None = None, cache: EmbeddingVectorCache | None = None) -> None:
        self.configuration = configuration
        self.embedder = embedder or SklearnHashingEmbedder(configuration.local_embedding_model)
        self.cache = cache or MemoryEmbeddingVectorCache()

    def retrieve(self, df: pd.DataFrame, scan_mode: str, excluded_pairs: set | None = None) -> HybridRetrievalResult:
        started = time.perf_counter()
        records = [row.to_dict() for _, row in df.reset_index(drop=True).iterrows()]
        excluded_pairs = excluded_pairs or set()
        texts = [semantic_retrieval_text(record) for record in records]
        channels = {}

        def add(left, right, channel, score=0.0, signal=None):
            if left == right:
                return
            a, b = sorted((left, right))
            if canonical_record_pair(records[a], records[b]) in excluded_pairs or not _allowed_pair(records[a], records[b], scan_mode):
                return
            row = channels.setdefault((a, b), {"sources": set(), "lexical": 0.0, "vector": 0.0, "signals": set()})
            row["sources"].add(channel)
            if channel == "LEXICAL": row["lexical"] = max(row["lexical"], score)
            if channel == "VECTOR": row["vector"] = max(row["vector"], score)
            if signal: row["signals"].add(signal)

        blocks = {}
        for index, record in enumerate(records):
            normalized = normalize_description(record.get("DESCRIPTION", ""))
            root = _part_root(record.get("PART_NO", ""))
            keys = []
            if normalized: keys.append(("NORMALIZED_DESCRIPTION", normalized))
            if root and len(root) >= 3: keys.append(("PART_NUMBER_ROOT", root))
            for token in extract_technical_tokens(record.get("DESCRIPTION", "")).get("measurements", [])[:4]:
                keys.append(("TECHNICAL_MEASUREMENT", token))
            for key in keys: blocks.setdefault(key, []).append(index)
        for (signal, _), indexes in sorted(blocks.items(), key=lambda item: str(item[0])):
            bounded = sorted(set(indexes))[:50]
            for position, left in enumerate(bounded):
                for right in bounded[position + 1:]: add(left, right, "EXACT_BLOCK", 100.0, signal)

        lexical_count = 0
        if len(records) > 1 and any(texts):
            try:
                lexical_matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1).fit_transform(texts)
                for left, right, score in _nearest(lexical_matrix, self.configuration.hybrid_retrieval_lexical_top_k):
                    before = len(channels); add(left, right, "LEXICAL", score); lexical_count += len(channels) >= before
            except ValueError:
                pass

        vector_count = 0
        if self.configuration.local_embedding_enabled and records:
            fingerprints = [record_fingerprint(text) for text in texts]
            loaded = self.cache.load(fingerprints, self.embedder.model_version)
            missing_positions = [i for i, fp in enumerate(fingerprints) if fp not in loaded]
            if missing_positions:
                generated = self.embedder.encode([texts[i] for i in missing_positions])
                additions = {fingerprints[position]: generated[offset] for offset, position in enumerate(missing_positions)}
                self.cache.save(additions, self.embedder.model_version); loaded.update(additions)
            matrix = normalize(np.vstack([loaded[fp] for fp in fingerprints]))
            for left, right, score in _nearest(matrix, self.configuration.hybrid_retrieval_vector_top_k):
                before = len(channels); add(left, right, "VECTOR", score); vector_count += len(channels) >= before

        weight = self.configuration.hybrid_retrieval_vector_weight
        ranked = []
        for (left, right), row in channels.items():
            sources = tuple(sorted(row["sources"]))
            multi = len(sources) > 1
            score = min(100.0, (row["lexical"] * (1 - weight)) + (row["vector"] * weight) + (15 if "EXACT_BLOCK" in sources else 0) + (10 if multi else 0))
            if score < self.configuration.hybrid_retrieval_min_score:
                continue
            ranked.append((left, right, round(score, 2), sources, row))
        ranked.sort(key=lambda item: (-len(item[3]), -item[2], item[0], item[1]))

        per_record = {index: 0 for index in range(len(records))}
        selected = []
        for item in ranked:
            left, right = item[0], item[1]
            if per_record[left] >= self.configuration.hybrid_retrieval_final_top_k or per_record[right] >= self.configuration.hybrid_retrieval_final_top_k:
                continue
            selected.append(item); per_record[left] += 1; per_record[right] += 1
        skipped = max(0, len(selected) - self.configuration.hybrid_retrieval_max_pairs_per_scan)
        selected = selected[:self.configuration.hybrid_retrieval_max_pairs_per_scan]
        candidates = []
        for rank, (left, right, score, sources, row) in enumerate(selected, 1):
            source = RetrievalSource.MULTI_SOURCE if len(sources) > 1 else RetrievalSource(sources[0])
            candidates.append(RetrievalCandidate(
                left, right, score, rank, source,
                RetrievalEvidence(sources, row["lexical"], row["vector"], tuple(sorted(row["signals"]))),
            ))
        counts = list(per_record.values())
        metrics = RetrievalMetrics(
            records_indexed=len(records), lexical_candidates_generated=lexical_count,
            vector_candidates_generated=vector_count,
            multi_source_candidates=sum(len(item[3]) > 1 for item in selected),
            hybrid_candidates_skipped_by_cap=skipped,
            average_candidates_per_record=round(sum(counts) / len(records), 2) if records else 0.0,
            max_candidates_for_any_record=max(counts, default=0),
            retrieval_runtime_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return HybridRetrievalResult(tuple(candidates), metrics, self.embedder.model_version)
