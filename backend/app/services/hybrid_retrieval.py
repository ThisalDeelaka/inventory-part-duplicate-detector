import hashlib
import json
import math
import re
import time
from collections import Counter, defaultdict
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
from app.engine.normalizer import (
    extract_technical_tokens,
    normalize_description,
    normalize_part_no_with_dictionary,
)
from app.engine.uom_relationship import UomRelationship, classify_uom_relationship
from app.engine.variant_extractor import extract_variant_attributes, find_critical_mismatches


RRF_K = 60
CHANNEL_WEIGHTS = {
    "EXACT_DESCRIPTION": 2.4,
    "PART_NUMBER_FAMILY": 2.2,
    "TECHNICAL_IDENTITY": 1.8,
    "LEXICAL": 1.0,
    "CHAR_VECTOR": 0.9,
}
_MAX_RRF = sum(weight / (RRF_K + 1) for weight in CHANNEL_WEIGHTS.values())


class RetrievalSource(str, Enum):
    EXACT_DESCRIPTION = "EXACT_DESCRIPTION"
    PART_NUMBER_FAMILY = "PART_NUMBER_FAMILY"
    LEXICAL = "LEXICAL"
    CHAR_VECTOR = "CHAR_VECTOR"
    TECHNICAL_IDENTITY = "TECHNICAL_IDENTITY"
    MULTI_SOURCE = "MULTI_SOURCE"


class RetrievalTier(str, Enum):
    TIER_A = "TIER_A"
    TIER_B = "TIER_B"
    TIER_C = "TIER_C"


@dataclass(frozen=True)
class RetrievalEvidence:
    retrieval_sources: tuple[str, ...]
    lexical_score: float
    vector_score: float
    blocking_signals: tuple[str, ...]
    description_specificity_score: float
    generic_description_penalty: float
    conflict_signals: tuple[str, ...]
    reciprocal_sources: tuple[str, ...]
    uom_relationship: str
    uom_evidence: str
    uom_penalty: float
    mapping_quality: str


@dataclass(frozen=True)
class RetrievalCandidate:
    left_record_id: int
    right_record_id: int
    retrieval_priority: float
    retrieval_rank: int
    retrieval_source: RetrievalSource
    retrieval_tier: RetrievalTier
    evidence: RetrievalEvidence

    @property
    def retrieval_score(self) -> float:
        """Historical API alias. This is retrieval priority, never confidence."""
        return self.retrieval_priority


@dataclass(frozen=True)
class RetrievalMetrics:
    records_indexed: int
    exact_description_candidates: int
    part_family_candidates: int
    lexical_candidates_generated: int
    vector_candidates_generated: int
    technical_identity_candidates: int
    reciprocal_candidates: int
    generic_penalized_candidates: int
    conflict_penalized_candidates: int
    uom_same_pairs_considered: int
    uom_convertible_pairs_considered: int
    uom_different_basis_pairs_considered: int
    uom_missing_or_wildcard_pairs_considered: int
    uom_malformed_or_unknown_pairs_considered: int
    multi_source_candidates: int
    tier_a_candidates: int
    tier_b_candidates: int
    tier_c_candidates: int
    hybrid_candidates_skipped_by_cap: int
    average_candidates_per_record: float
    max_candidates_for_any_record: int
    largest_description_family_candidates: int
    candidate_family_concentration: float
    retrieval_runtime_ms: float
    provider_request_count: int = 0


@dataclass(frozen=True)
class HybridRetrievalResult:
    candidates: tuple[RetrievalCandidate, ...]
    metrics: RetrievalMetrics
    embedding_model_version: str


@dataclass(frozen=True)
class DescriptionSpecificity:
    score: float
    generic_penalty: float
    reasons: tuple[str, ...]


class LocalEmbedder(Protocol):
    model_version: str

    def encode(self, texts: list[str]) -> np.ndarray: ...


_RETRIEVAL_ALIASES = {
    "mtr": "motor", "brg": "bearing", "de": "drive end", "nde": "non drive end",
    "assy": "assembly", "bkt": "bracket", "pnl": "panel", "vlv": "valve",
}
_PART_CODE_ALIASES = {
    "fp": "fuelpump", "com": "compressor", "stat": "stator", "rot": "rotor",
    "brg": "bearing", "mtr": "motor", "assy": "assembly", "pnl": "panel",
}
_GENERIC_DESCRIPTIONS = {
    "part", "inventory part", "normal time", "sales part", "bracket", "test",
    "circuit board", "item", "material", "miscellaneous", "service",
}
_GENERIC_TOKENS = {
    "part", "inventory", "normal", "time", "sales", "test", "item", "material",
    "miscellaneous", "service", "generic", "board", "bracket",
}
_OPPOSITE_VARIANTS = (
    ("serial", "non serial"), ("left", "right"), ("lh", "rh"),
    ("inlet", "outlet"), ("male", "female"), ("red", "blue"),
)


def semantic_retrieval_text(record: dict) -> str:
    """Historical name retained for cache compatibility; output feeds char features."""
    normalized = normalize_description(record.get("DESCRIPTION", ""))
    expanded = []
    for token in normalized.split():
        expanded.extend(_RETRIEVAL_ALIASES.get(token, token).split())
    return " ".join(expanded)


class SklearnHashingEmbedder:
    """Offline character-vector runtime; not a semantic embedding model."""

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
        return {
            fingerprint: self.values[(fingerprint, model_version)]
            for fingerprint in fingerprints
            if (fingerprint, model_version) in self.values
        }

    def save(self, vectors, model_version):
        for fingerprint, vector in vectors.items():
            self.values[(fingerprint, model_version)] = vector


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
    if evaluate_hard_business_rules(
        left, right, scan_mode, allow_uom_mapping_review=True
    )["blocked"]:
        return False
    if find_critical_mismatches(
        extract_variant_attributes(left.get("DESCRIPTION")),
        extract_variant_attributes(right.get("DESCRIPTION")),
    ):
        return False
    return True


def _blocking_signals(left: dict, right: dict, scan_mode: str) -> tuple[str, ...]:
    signals = []
    left_site = str(left.get("CONTRACT") or "").strip().casefold()
    right_site = str(right.get("CONTRACT") or "").strip().casefold()
    if left_site and right_site:
        signals.append("SAME_SITE_SCOPE" if left_site == right_site else "CROSS_SITE_SCOPE")
    signals.append(f"SCAN_MODE_{scan_mode}")
    return tuple(sorted(set(signals)))


def description_specificity_statistics(descriptions: list[str]) -> list[DescriptionSpecificity]:
    normalized = [normalize_description(value) for value in descriptions]
    count = max(1, len(normalized))
    description_frequency = Counter(normalized)
    token_frequency = Counter(token for value in normalized for token in set(value.split()))
    max_idf = math.log(count + 1) + 1
    output = []
    for value in normalized:
        tokens = value.split()
        frequency = description_frequency[value]
        generic_ratio = (
            sum(token in _GENERIC_TOKENS for token in tokens) / len(tokens)
            if tokens else 1.0
        )
        idf = (
            sum(math.log((count + 1) / (token_frequency[token] + 1)) + 1 for token in tokens)
            / len(tokens)
            if tokens else 0.0
        )
        idf_component = min(1.0, idf / max_idf)
        informative = [
            token for token in tokens
            if token not in _GENERIC_TOKENS and (len(token) > 2 or any(char.isdigit() for char in token))
        ]
        informative_ratio = len(informative) / len(tokens) if tokens else 0.0
        rarity = 1.0 / max(1, frequency)
        length_component = min(1.0, len(tokens) / 5)
        score = 100 * (
            0.35 * idf_component + 0.25 * rarity
            + 0.25 * informative_ratio + 0.15 * length_component
        )
        reasons = []
        penalty = 0.0
        if value in _GENERIC_DESCRIPTIONS or generic_ratio >= 0.75:
            reasons.append("GENERIC_DESCRIPTION")
            penalty += 55
        elif generic_ratio >= 0.5:
            reasons.append("GENERIC_DESCRIPTION")
            penalty += 30
        if len(tokens) == 1:
            reasons.append("GENERIC_DESCRIPTION")
            penalty += 50
        elif len(tokens) == 2:
            penalty += 15
        high_frequency = frequency >= max(4, math.ceil(count * 0.02))
        if high_frequency:
            reasons.append("HIGH_DESCRIPTION_FREQUENCY")
            penalty += min(30, 10 + 100 * frequency / count)
        output.append(DescriptionSpecificity(
            round(max(0.0, min(100.0, score)), 2),
            round(max(0.0, min(100.0, penalty)), 2),
            tuple(sorted(set(reasons))),
        ))
    return output


def _part_chunks(value) -> list[str]:
    normalized = normalize_part_no_with_dictionary(value)
    return re.findall(r"[a-z]+|\d+", normalized.casefold())


def _expand_part_chunk(chunk: str) -> str:
    if chunk in _PART_CODE_ALIASES:
        return _PART_CODE_ALIASES[chunk]
    expanded = chunk
    for alias in sorted(_PART_CODE_ALIASES, key=len, reverse=True):
        if len(chunk) >= 5 and alias in expanded:
            expanded = expanded.replace(alias, _PART_CODE_ALIASES[alias])
    return expanded


def part_number_family_keys(value) -> tuple[str, ...]:
    chunks = _part_chunks(value)
    if not chunks:
        return ()
    compound_code = any(
        alias in chunk
        for chunk in chunks[:-1]
        for alias in _PART_CODE_ALIASES
    )
    while (
        compound_code and len(chunks) > 2
        and chunks[-1].isdigit() and len(chunks[-1]) <= 2
    ):
        chunks.pop()
    expanded = [_expand_part_chunk(chunk) for chunk in chunks]
    keys = set()
    full = "".join(expanded)
    if len(full) >= 5:
        keys.add(full)
    if len(expanded) > 1 and expanded[0].isalpha() and len(expanded[0]) <= 3:
        without_prefix = "".join(expanded[1:])
        if len(without_prefix) >= 5:
            keys.add(without_prefix)
    return tuple(sorted(keys))


def _technical_keys(description) -> tuple[str, ...]:
    extracted = extract_technical_tokens(description)
    keys = set()
    for name in ("measurements", "dimensions"):
        keys.update(f"{name}:{value}" for value in extracted.get(name, [])[:6])
    keys.update(f"number:{value}" for value in extracted.get("numbers", [])[:6])
    return tuple(sorted(keys))


def _model_tokens(description) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)[A-Za-z0-9-]{2,}\b", str(description or ""))
    }


def _conflict_signals(left: dict, right: dict) -> tuple[str, ...]:
    left_text = normalize_description(left.get("DESCRIPTION", ""))
    right_text = normalize_description(right.get("DESCRIPTION", ""))
    signals = set()
    for plain, opposite in _OPPOSITE_VARIANTS:
        left_plain = re.search(rf"\b{re.escape(plain)}\b", left_text) is not None
        right_plain = re.search(rf"\b{re.escape(plain)}\b", right_text) is not None
        left_opposite = re.search(rf"\b{re.escape(opposite)}\b", left_text) is not None
        right_opposite = re.search(rf"\b{re.escape(opposite)}\b", right_text) is not None
        if (left_opposite and right_plain and not right_opposite) or (
            right_opposite and left_plain and not left_opposite
        ):
            signals.add("OPPOSITE_VARIANT_TERM")
    left_models = _model_tokens(left.get("DESCRIPTION"))
    right_models = _model_tokens(right.get("DESCRIPTION"))
    if left_models and right_models and left_models.isdisjoint(right_models):
        signals.add("TECHNICAL_CONFLICT")
    return tuple(sorted(signals))


def _nearest_pairs(matrix, top_k: int) -> list[tuple[int, int, float, bool]]:
    count = matrix.shape[0]
    if count < 2:
        return []
    neighbours = min(count, top_k + 1)
    index = NearestNeighbors(n_neighbors=neighbours, metric="cosine", algorithm="brute")
    index.fit(matrix)
    directed = {}
    for start in range(0, count, 256):
        distances, indices = index.kneighbors(matrix[start:start + 256])
        for offset, (row_distances, row_indices) in enumerate(zip(distances, indices)):
            source = start + offset
            for distance, target_value in zip(row_distances, row_indices):
                target = int(target_value)
                if source == target:
                    continue
                directed[(source, target)] = round(max(0.0, 1.0 - float(distance)) * 100, 2)
    pairs = {}
    for (source, target), score in directed.items():
        pair = tuple(sorted((source, target)))
        row = pairs.setdefault(pair, {"score": 0.0, "directions": set()})
        row["score"] = max(row["score"], score)
        row["directions"].add((source, target))
    output = [
        (left, right, row["score"], len(row["directions"]) == 2)
        for (left, right), row in pairs.items()
        if row["score"] > 0
    ]
    return sorted(output, key=lambda item: (-item[2], item[0], item[1]))


class HybridCandidateRetriever:
    def __init__(
        self,
        configuration: Settings,
        embedder: LocalEmbedder | None = None,
        cache: EmbeddingVectorCache | None = None,
    ) -> None:
        self.configuration = configuration
        self.embedder = embedder or SklearnHashingEmbedder(configuration.local_embedding_model)
        self.cache = cache or MemoryEmbeddingVectorCache()

    def retrieve(
        self,
        df: pd.DataFrame,
        scan_mode: str,
        excluded_pairs: set | None = None,
    ) -> HybridRetrievalResult:
        started = time.perf_counter()
        records = [row.to_dict() for _, row in df.reset_index(drop=True).iterrows()]
        excluded_pairs = excluded_pairs or set()
        texts = [semantic_retrieval_text(record) for record in records]
        specificity = description_specificity_statistics(
            [record.get("DESCRIPTION", "") for record in records]
        )
        evidence = {}

        def eligible(left: int, right: int) -> tuple[int, int] | None:
            if left == right:
                return None
            first, second = sorted((left, right))
            if canonical_record_pair(records[first], records[second]) in excluded_pairs:
                return None
            if not _allowed_pair(records[first], records[second], scan_mode):
                return None
            return first, second

        def add_channel(
            left: int,
            right: int,
            channel: str,
            channel_rank: int,
            raw_score: float = 0.0,
            reciprocal: bool = False,
        ) -> None:
            pair = eligible(left, right)
            if pair is None:
                return
            row = evidence.setdefault(pair, {
                "channel_ranks": {}, "lexical": 0.0, "vector": 0.0,
                "reciprocal": set(),
            })
            previous = row["channel_ranks"].get(channel)
            row["channel_ranks"][channel] = min(previous, channel_rank) if previous else channel_rank
            if channel == "LEXICAL":
                row["lexical"] = max(row["lexical"], raw_score)
            if channel == "CHAR_VECTOR":
                row["vector"] = max(row["vector"], raw_score)
            if reciprocal:
                row["reciprocal"].add(f"{channel}_RECIPROCAL")

        normalized_descriptions = [normalize_description(record.get("DESCRIPTION", "")) for record in records]

        exact_groups = defaultdict(list)
        for index, value in enumerate(normalized_descriptions):
            if value:
                exact_groups[value].append(index)
        exact_proposals = {}
        for value, indexes in exact_groups.items():
            bounded = sorted(set(indexes))[:50]
            for position, left in enumerate(bounded):
                for right in bounded[position + 1:]:
                    pair = eligible(left, right)
                    if pair:
                        exact_proposals[pair] = max(
                            exact_proposals.get(pair, 0.0),
                            (specificity[left].score + specificity[right].score) / 2,
                        )
        for rank, (pair, quality) in enumerate(
            sorted(exact_proposals.items(), key=lambda item: (-item[1], item[0])), 1
        ):
            add_channel(*pair, "EXACT_DESCRIPTION", rank, quality)

        family_groups = defaultdict(list)
        for index, record in enumerate(records):
            for key in part_number_family_keys(record.get("PART_NO", "")):
                family_groups[key].append(index)
        family_proposals = {}
        for key, indexes in sorted(family_groups.items()):
            bounded = sorted(set(indexes))[:50]
            for position, left in enumerate(bounded):
                for right in bounded[position + 1:]:
                    pair = eligible(left, right)
                    if pair:
                        family_proposals[pair] = max(family_proposals.get(pair, 0.0), len(key))
        for rank, (pair, quality) in enumerate(
            sorted(family_proposals.items(), key=lambda item: (-item[1], item[0])), 1
        ):
            add_channel(*pair, "PART_NUMBER_FAMILY", rank, quality)

        lexical_pairs = []
        if len(records) > 1 and any(texts):
            try:
                lexical_matrix = TfidfVectorizer(
                    analyzer="char_wb", ngram_range=(3, 5), min_df=1
                ).fit_transform(texts)
                lexical_pairs = _nearest_pairs(
                    lexical_matrix, self.configuration.hybrid_retrieval_lexical_top_k
                )
            except ValueError:
                lexical_pairs = []
        for rank, (left, right, score, reciprocal) in enumerate(lexical_pairs, 1):
            add_channel(left, right, "LEXICAL", rank, score, reciprocal)

        vector_pairs = []
        if self.configuration.local_embedding_enabled and records:
            fingerprints = [record_fingerprint(text) for text in texts]
            loaded = self.cache.load(fingerprints, self.embedder.model_version)
            missing_positions = [
                index for index, fingerprint in enumerate(fingerprints)
                if fingerprint not in loaded
            ]
            if missing_positions:
                generated = self.embedder.encode([texts[index] for index in missing_positions])
                additions = {
                    fingerprints[position]: generated[offset]
                    for offset, position in enumerate(missing_positions)
                }
                self.cache.save(additions, self.embedder.model_version)
                loaded.update(additions)
            matrix = normalize(np.vstack([loaded[fingerprint] for fingerprint in fingerprints]))
            vector_pairs = _nearest_pairs(
                matrix, self.configuration.hybrid_retrieval_vector_top_k
            )
        for rank, (left, right, score, reciprocal) in enumerate(vector_pairs, 1):
            add_channel(left, right, "CHAR_VECTOR", rank, score, reciprocal)

        technical_groups = defaultdict(list)
        for index, record in enumerate(records):
            for key in _technical_keys(record.get("DESCRIPTION", "")):
                technical_groups[key].append(index)
        technical_proposals = Counter()
        for key, indexes in sorted(technical_groups.items()):
            bounded = sorted(set(indexes))[:50]
            for position, left in enumerate(bounded):
                for right in bounded[position + 1:]:
                    pair = eligible(left, right)
                    if pair:
                        technical_proposals[pair] += 1
        for rank, (pair, quality) in enumerate(
            sorted(technical_proposals.items(), key=lambda item: (-item[1], item[0])), 1
        ):
            add_channel(*pair, "TECHNICAL_IDENTITY", rank, float(quality))

        prepared = []
        for (left, right), row in evidence.items():
            channel_ranks = row["channel_ranks"]
            sources = tuple(sorted(channel_ranks))
            rrf = sum(
                CHANNEL_WEIGHTS[channel] / (RRF_K + channel_ranks[channel])
                for channel in sources
            )
            priority = 94 * rrf / _MAX_RRF
            reciprocal_sources = tuple(sorted(row["reciprocal"]))
            priority += min(4.0, 1.5 * len(reciprocal_sources))
            pair_specificity = round((specificity[left].score + specificity[right].score) / 2, 2)
            generic_penalty = round(
                (specificity[left].generic_penalty + specificity[right].generic_penalty) / 2, 2
            )
            reasons = set(specificity[left].reasons) | set(specificity[right].reasons)
            conflicts = set(_conflict_signals(records[left], records[right]))
            if len(sources) == 1:
                reasons.add("WEAK_SINGLE_CHANNEL")
                priority *= 0.75
            priority *= 1 - (0.65 * generic_penalty / 100)
            if conflicts:
                priority *= 0.35
            uom = classify_uom_relationship(
                records[left].get("UNIT_MEAS"), records[right].get("UNIT_MEAS")
            )
            priority *= 1 - (uom.penalty / 100)
            priority = round(max(0.0, min(99.99, priority)), 4)
            generic = generic_penalty >= 50 or pair_specificity < 45
            source_set = set(sources)
            if (
                not conflicts
                and uom.relationship != UomRelationship.DIFFERENT_DIMENSION_OR_BASIS
                and (
                ("EXACT_DESCRIPTION" in source_set and not generic and pair_specificity >= 55)
                or {"PART_NUMBER_FAMILY", "TECHNICAL_IDENTITY"}.issubset(source_set)
                or (
                    "EXACT_DESCRIPTION" in source_set
                    and "PART_NUMBER_FAMILY" in source_set
                    and generic_penalty < 60
                )
                )
            ):
                tier = RetrievalTier.TIER_A
            elif not conflicts and (
                len(sources) >= 2 or reciprocal_sources or priority >= 25
            ):
                tier = RetrievalTier.TIER_B
            else:
                tier = RetrievalTier.TIER_C
            description_family = (
                f"description:{normalized_descriptions[left]}"
                if normalized_descriptions[left] == normalized_descriptions[right]
                else f"pair:{left}:{right}"
            )
            prepared.append({
                "left": left, "right": right, "sources": sources, "row": row,
                "priority": priority, "specificity": pair_specificity,
                "generic_penalty": generic_penalty,
                "reasons": tuple(sorted(reasons)), "conflicts": tuple(sorted(conflicts)),
                "reciprocal": reciprocal_sources, "tier": tier, "family": description_family,
                "uom": uom,
            })

        prepared.sort(key=lambda item: (
            {RetrievalTier.TIER_A: 0, RetrievalTier.TIER_B: 1, RetrievalTier.TIER_C: 2}[item["tier"]],
            -item["priority"], -item["specificity"], item["left"], item["right"],
        ))
        global_cap = self.configuration.hybrid_retrieval_max_pairs_per_scan
        tier_caps = {
            RetrievalTier.TIER_A: self.configuration.hybrid_retrieval_tier_a_max,
            RetrievalTier.TIER_B: self.configuration.hybrid_retrieval_tier_b_max,
            RetrievalTier.TIER_C: self.configuration.hybrid_retrieval_tier_c_max,
        }
        per_record = Counter()
        family_counts = Counter()
        selected = []
        for tier in (RetrievalTier.TIER_A, RetrievalTier.TIER_B, RetrievalTier.TIER_C):
            tier_selected = 0
            for item in prepared:
                if item["tier"] != tier or tier_selected >= tier_caps[tier] or len(selected) >= global_cap:
                    continue
                left, right = item["left"], item["right"]
                if (
                    per_record[left] >= self.configuration.hybrid_retrieval_final_top_k
                    or per_record[right] >= self.configuration.hybrid_retrieval_final_top_k
                ):
                    continue
                if family_counts[item["family"]] >= self.configuration.hybrid_retrieval_family_max:
                    continue
                selected.append(item)
                per_record[left] += 1
                per_record[right] += 1
                family_counts[item["family"]] += 1
                tier_selected += 1

        candidates = []
        for rank, item in enumerate(selected, 1):
            sources = item["sources"]
            source = RetrievalSource.MULTI_SOURCE if len(sources) > 1 else RetrievalSource(sources[0])
            blocking = _blocking_signals(records[item["left"]], records[item["right"]], scan_mode)
            candidates.append(RetrievalCandidate(
                item["left"], item["right"], item["priority"], rank, source, item["tier"],
                RetrievalEvidence(
                    sources, item["row"]["lexical"], item["row"]["vector"], blocking,
                    item["specificity"], item["generic_penalty"],
                    tuple(sorted(set(item["conflicts"]) | set(item["reasons"]))),
                    item["reciprocal"],
                    item["uom"].relationship.value,
                    item["uom"].reason_code,
                    item["uom"].penalty,
                    item["uom"].mapping_quality.value,
                ),
            ))

        selected_sources = [set(item["sources"]) for item in selected]
        selected_counts = [per_record[index] for index in range(len(records))]
        largest_family = max(family_counts.values(), default=0)
        metrics = RetrievalMetrics(
            records_indexed=len(records),
            exact_description_candidates=sum("EXACT_DESCRIPTION" in row["channel_ranks"] for row in evidence.values()),
            part_family_candidates=sum("PART_NUMBER_FAMILY" in row["channel_ranks"] for row in evidence.values()),
            lexical_candidates_generated=sum("LEXICAL" in row["channel_ranks"] for row in evidence.values()),
            vector_candidates_generated=sum("CHAR_VECTOR" in row["channel_ranks"] for row in evidence.values()),
            technical_identity_candidates=sum("TECHNICAL_IDENTITY" in row["channel_ranks"] for row in evidence.values()),
            reciprocal_candidates=sum(bool(item["reciprocal"]) for item in selected),
            generic_penalized_candidates=sum(item["generic_penalty"] > 0 for item in selected),
            conflict_penalized_candidates=sum(bool(item["conflicts"]) for item in selected),
            uom_same_pairs_considered=sum(
                item["uom"].relationship == UomRelationship.SAME_UOM for item in prepared
            ),
            uom_convertible_pairs_considered=sum(
                item["uom"].relationship == UomRelationship.CONVERTIBLE_SAME_DIMENSION
                for item in prepared
            ),
            uom_different_basis_pairs_considered=sum(
                item["uom"].relationship == UomRelationship.DIFFERENT_DIMENSION_OR_BASIS
                for item in prepared
            ),
            uom_missing_or_wildcard_pairs_considered=sum(
                item["uom"].relationship == UomRelationship.MISSING_OR_WILDCARD
                for item in prepared
            ),
            uom_malformed_or_unknown_pairs_considered=sum(
                item["uom"].relationship == UomRelationship.MALFORMED_OR_UNKNOWN
                for item in prepared
            ),
            multi_source_candidates=sum(len(sources) > 1 for sources in selected_sources),
            tier_a_candidates=sum(item["tier"] == RetrievalTier.TIER_A for item in selected),
            tier_b_candidates=sum(item["tier"] == RetrievalTier.TIER_B for item in selected),
            tier_c_candidates=sum(item["tier"] == RetrievalTier.TIER_C for item in selected),
            hybrid_candidates_skipped_by_cap=max(0, len(prepared) - len(selected)),
            average_candidates_per_record=(
                round(sum(selected_counts) / len(records), 2) if records else 0.0
            ),
            max_candidates_for_any_record=max(selected_counts, default=0),
            largest_description_family_candidates=largest_family,
            candidate_family_concentration=(
                round(largest_family / len(selected), 4) if selected else 0.0
            ),
            retrieval_runtime_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return HybridRetrievalResult(tuple(candidates), metrics, self.embedder.model_version)
