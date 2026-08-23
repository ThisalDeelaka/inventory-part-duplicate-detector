from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from app.core.config import Settings
from app.engine.candidate_evaluation_features import (
    build_candidate_evaluation_features,
)
from app.engine.scoring import score_candidate
from app.engine.variant_extractor import extract_variant_attributes
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    MemoryEmbeddingVectorCache,
    _allowed_pair,
)


def record(ref, part, description, **values):
    return {
        "PART_NO": part,
        "DESCRIPTION": description,
        "CONTRACT": values.pop("CONTRACT", "S1"),
        "UNIT_MEAS": values.pop("UNIT_MEAS", "EA"),
        "HSN_SAC_CODE": values.pop("HSN_SAC_CODE", "1000"),
        "PRODUCT_CATEGORY_ID": values.pop("PRODUCT_CATEGORY_ID", "P1"),
        CANONICAL_RECORD_REF_FIELD: ref,
        **values,
    }


def features(value):
    return build_candidate_evaluation_features(
        value, record_ref_key=value[CANONICAL_RECORD_REF_FIELD]
    )


def configuration(**values):
    defaults = {
        "llm_provider": "none",
        "llm_demo_enabled": False,
        "hybrid_retrieval_enabled": True,
        "hybrid_retrieval_lexical_top_k": 3,
        "hybrid_retrieval_vector_top_k": 3,
        "hybrid_retrieval_final_top_k": 3,
        "hybrid_retrieval_max_pairs_per_scan": 20,
    }
    defaults.update(values)
    return Settings(**defaults)


def test_f1_feature_bundle_is_deterministic_and_immutable():
    value = record("r1", "MTR-6205", "Motor Drive End Bearing 6205")
    first = features(value)
    assert first == features(dict(reversed(tuple(value.items()))))
    with pytest.raises(FrozenInstanceError):
        first.normalized_description = "changed"


def test_f2_feature_index_is_input_order_independent():
    rows = [
        record("r2", "B", "Blue Paint 1L"),
        record("r1", "A", "Red Paint 1L"),
    ]
    forward = {item.record_ref_key: item for item in map(features, rows)}
    reverse = {item.record_ref_key: item for item in map(features, reversed(rows))}
    assert forward == reverse


def test_f3_duplicate_valued_rows_remain_distinct_by_canonical_key():
    left = features(record("r1", "A", "Bearing 6205"))
    right = features(record("r2", "A", "Bearing 6205"))
    assert left.record_ref_key != right.record_ref_key
    assert left.normalized_description == right.normalized_description
    assert left.variant_attributes == right.variant_attributes


def test_f4_raw_and_precomputed_variant_results_are_identical():
    value = record("r1", "A", "Motor NDE Bearing 6205 Type 2 30A")
    assert features(value).variant_payload() == extract_variant_attributes(
        value["DESCRIPTION"]
    )


@pytest.mark.parametrize(
    "left,right,mode",
    [
        (record("r1", "A", "Fuel Filter"), record("r2", "B", "Air Filter"), "SAME_SITE_DUPLICATE"),
        (record("r1", "A", "Bearing 6205"), record("r2", "B", "Bearing 6205"), "SAME_SITE_DUPLICATE"),
        (record("r1", "A", "Bearing", CONTRACT="S1"), record("r2", "B", "Bearing", CONTRACT="S2"), "CROSS_SITE_STANDARDIZATION"),
    ],
)
def test_f5_f6_raw_and_precomputed_eligibility_allowed_pair_are_identical(
    left, right, mode
):
    assert _allowed_pair(left, right, mode) == _allowed_pair(
        left, right, mode, features(left), features(right)
    )


@pytest.mark.parametrize(
    "left,right,selected,mode,allow_uom",
    [
        (record("r1", "A", "Bearing 6205"), record("r2", "B", "Bearing 6205"), ["CONTRACT"], "SAME_SITE_DUPLICATE", False),
        (record("r1", "A", "Filter"), record("r2", "B", "Generator Filter"), ["CONTRACT"], "SAME_SITE_DUPLICATE", False),
        (record("r1", "A", "MCB 20A"), record("r2", "B", "MCB 30A"), ["CONTRACT"], "SAME_SITE_DUPLICATE", False),
        (record("r1", "A", "Bearing", UNIT_MEAS="EA"), record("r2", "B", "Bearing", UNIT_MEAS="BOX"), ["UNIT_MEAS"], "SAME_SITE_DUPLICATE", True),
        (record("r1", "", ""), record("r2", "B", None), [], "SAME_SITE_DUPLICATE", False),
    ],
)
def test_f7_f8_f9_f10_raw_and_precomputed_scoring_is_exact(
    left, right, selected, mode, allow_uom
):
    raw = score_candidate(
        left, right, selected, mode, allow_uom_mapping_review=allow_uom
    )
    prepared = score_candidate(
        left,
        right,
        selected,
        mode,
        allow_uom_mapping_review=allow_uom,
        features_a=features(left),
        features_b=features(right),
    )
    assert prepared == raw


def test_f11_pair_order_semantics_are_preserved():
    left = record("r1", "A", "Generator Filter")
    right = record("r2", "B", "Filter")
    assert score_candidate(left, right, ["CONTRACT"]) == score_candidate(
        left,
        right,
        ["CONTRACT"],
        features_a=features(left),
        features_b=features(right),
    )
    assert score_candidate(right, left, ["CONTRACT"]) == score_candidate(
        right,
        left,
        ["CONTRACT"],
        features_a=features(right),
        features_b=features(left),
    )


def test_f12_f13_multichannel_provenance_cap_and_order_are_unchanged():
    rows = [
        record("r1", "A-6205", "Motor Bearing 6205"),
        record("r2", "B-6205", "Motor Bearing 6205"),
        record("r3", "C-6205", "Motor Drive End Bearing 6205"),
        record("r4", "D", "Unrelated Paint"),
    ]
    frame = pd.DataFrame(rows)
    retriever = HybridCandidateRetriever(
        configuration(), cache=MemoryEmbeddingVectorCache()
    )
    raw = retriever.retrieve(frame, "SAME_SITE_DUPLICATE")
    prepared = retriever.retrieve(
        frame,
        "SAME_SITE_DUPLICATE",
        evaluation_features={item.record_ref_key: item for item in map(features, rows)},
    )
    assert prepared.candidates == raw.candidates
    assert [item.retrieval_rank for item in prepared.candidates] == list(
        range(1, len(prepared.candidates) + 1)
    )
    assert any(len(item.evidence.retrieval_sources) > 1 for item in prepared.candidates)


def test_f14_f15_f16_semantic_contract_is_unchanged_by_feature_boundary():
    rows = [
        record("r1", "A-6205", "Motor Bearing 6205"),
        record("r2", "B-6205", "Motor Bearing 6205"),
        record("r3", "C-6205", "Motor Drive End Bearing 6205"),
    ]
    frame = pd.DataFrame(rows)
    retriever = HybridCandidateRetriever(
        configuration(), cache=MemoryEmbeddingVectorCache()
    )
    raw = retriever.retrieve(frame, "SAME_SITE_DUPLICATE")
    prepared = retriever.retrieve(
        frame,
        "SAME_SITE_DUPLICATE",
        evaluation_features={item.record_ref_key: item for item in map(features, rows)},
    )
    assert prepared.candidates == raw.candidates
    assert prepared.metrics.provider_request_count == 0


def test_f17_f18_instrumentation_is_bounded_and_provider_free():
    rows = [
        record("r1", "A-6205", "Motor Bearing 6205"),
        record("r2", "B-6205", "Motor Bearing 6205"),
        record("r3", "C-6205", "Motor Drive End Bearing 6205"),
    ]
    bundles = {item.record_ref_key: item for item in map(features, rows)}
    result = HybridCandidateRetriever(
        configuration(), cache=MemoryEmbeddingVectorCache()
    ).retrieve(
        pd.DataFrame(rows),
        "SAME_SITE_DUPLICATE",
        evaluation_features=bundles,
    )
    assert result.metrics.feature_bundles_built == len(rows)
    assert result.metrics.feature_reuse_hits >= len(rows)
    assert result.metrics.eligibility_calls >= result.metrics.allowed_pair_calls
    assert result.metrics.provider_request_count == 0
