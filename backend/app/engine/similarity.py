from difflib import SequenceMatcher

from app.engine.attribute_extractor import extract_attributes
from app.engine.models import CandidatePair, SimilarityResult, SimilarityScores
from app.engine.similarity_model import (
    calculate_fuzzy_similarity,
    calculate_part_no_similarity,
    calculate_technical_token_score,
    calculate_tfidf_similarity,
)


STRUCTURED_FEATURES = (
    "product_class",
    "type_code",
    "rating",
    "color",
    "volume",
    "material",
    "application_context",
    "function_or_media",
)


def _fallback_similarity(text_a: str, text_b: str) -> float:
    if not text_a or not text_b:
        return 0.0
    return round(SequenceMatcher(None, text_a, text_b).ratio() * 100, 2)


def _text_similarity(text_a: str, text_b: str) -> float:
    try:
        fuzzy = calculate_fuzzy_similarity(text_a, text_b)
        tfidf = calculate_tfidf_similarity(text_a, text_b)
        return round(tfidf * 0.6 + fuzzy * 0.4, 2)
    except Exception:
        return _fallback_similarity(text_a, text_b)


def _record_value(record, field: str) -> str:
    value = record.raw.get(field)
    return "" if value is None else str(value)


def _feature_match(attrs_a, attrs_b, feature: str):
    values_a = set(getattr(attrs_a, feature))
    values_b = set(getattr(attrs_b, feature))
    if not values_a and not values_b:
        return None
    if not values_a or not values_b:
        return None
    return values_a == values_b


def _compare_features(attrs_a, attrs_b):
    matched = []
    mismatched = []
    missing = []
    flags = {}
    for feature in STRUCTURED_FEATURES:
        values_a = getattr(attrs_a, feature)
        values_b = getattr(attrs_b, feature)
        match = _feature_match(attrs_a, attrs_b, feature)
        flags[f"{feature}_match"] = match
        if match is True:
            matched.append(feature)
        elif match is False:
            mismatched.append({
                "feature": feature,
                "values_a": values_a,
                "values_b": values_b,
            })
        else:
            missing.append(feature)
    return matched, mismatched, missing, flags


def _structured_overlap_score(attrs_a, attrs_b) -> float:
    comparable = 0
    score = 0.0
    for feature in STRUCTURED_FEATURES:
        values_a = set(getattr(attrs_a, feature))
        values_b = set(getattr(attrs_b, feature))
        if not values_a and not values_b:
            continue
        comparable += 1
        if values_a and values_b:
            score += len(values_a & values_b) / len(values_a | values_b)
    if comparable == 0:
        return 50.0
    return round(score / comparable * 100, 2)


def _selected_field_feature(candidate: CandidatePair) -> tuple[list[str], list[dict]]:
    matched = [f"field:{field}" for field in candidate.matched_fields]
    mismatched = [{"feature": f"field:{field}", "values_a": [], "values_b": []} for field in candidate.mismatched_fields]
    return matched, mismatched


def score_candidate_pair(candidate: CandidatePair) -> SimilarityResult:
    attrs_a = extract_attributes(
        candidate.record_a.part_no,
        candidate.record_a.description,
        candidate.record_a.raw.get("MASTER_PART_DESCRIPTION"),
    )
    attrs_b = extract_attributes(
        candidate.record_b.part_no,
        candidate.record_b.description,
        candidate.record_b.raw.get("MASTER_PART_DESCRIPTION"),
    )

    part_no_similarity = calculate_part_no_similarity(candidate.record_a.part_no, candidate.record_b.part_no)
    description_similarity = _text_similarity(attrs_a.normalized_description, attrs_b.normalized_description)
    master_description_similarity = _text_similarity(
        _record_value(candidate.record_a, "MASTER_PART_DESCRIPTION"),
        _record_value(candidate.record_b, "MASTER_PART_DESCRIPTION"),
    )
    technical_token_score = calculate_technical_token_score(attrs_a.technical_tokens, attrs_b.technical_tokens)
    structured_score = _structured_overlap_score(attrs_a, attrs_b)
    matched_features, mismatched_features, missing_features, flags = _compare_features(attrs_a, attrs_b)
    selected_matches, selected_mismatches = _selected_field_feature(candidate)
    matched_features.extend(selected_matches)
    mismatched_features.extend(selected_mismatches)

    description_component = max(description_similarity, master_description_similarity)
    overall = (
        description_component * 0.45
        + part_no_similarity * 0.20
        + structured_score * 0.25
        + technical_token_score * 0.10
    )

    return SimilarityResult(
        overall_similarity=round(max(0.0, min(100.0, overall)), 2),
        tfidf_score=calculate_tfidf_similarity(attrs_a.normalized_description, attrs_b.normalized_description),
        fuzzy_score=calculate_fuzzy_similarity(attrs_a.normalized_description, attrs_b.normalized_description),
        description_similarity=description_similarity,
        master_description_similarity=master_description_similarity,
        part_no_similarity=part_no_similarity,
        technical_token_score=technical_token_score,
        final_score=round(max(0.0, min(100.0, overall)), 2),
        product_class_match=flags["product_class_match"],
        type_code_match=flags["type_code_match"],
        rating_match=flags["rating_match"],
        color_match=flags["color_match"],
        volume_match=flags["volume_match"],
        material_match=flags["material_match"],
        application_context_match=flags["application_context_match"],
        function_or_media_match=flags["function_or_media_match"],
        generic_description_warning=attrs_a.is_generic_description or attrs_b.is_generic_description,
        matched_features=sorted(set(matched_features)),
        mismatched_features=mismatched_features,
        missing_features=sorted(set(missing_features)),
        rating_a=attrs_a.rating,
        rating_b=attrs_b.rating,
        color_a=attrs_a.color,
        color_b=attrs_b.color,
        function_or_media_a=attrs_a.function_or_media,
        function_or_media_b=attrs_b.function_or_media,
        generic_terms_a=attrs_a.generic_terms,
        generic_terms_b=attrs_b.generic_terms,
    )


def calculate_similarity(profile_a, profile_b, business_score: float) -> SimilarityScores:
    tfidf = calculate_tfidf_similarity(profile_a.description, profile_b.description)
    fuzzy = calculate_fuzzy_similarity(profile_a.description, profile_b.description)
    description = round(tfidf * 0.6 + fuzzy * 0.4, 2)
    part_no = calculate_part_no_similarity(profile_a.part_no, profile_b.part_no)
    token_score = calculate_technical_token_score(
        profile_a.attributes["technical"],
        profile_b.attributes["technical"],
    )
    final = description * 0.6 + business_score * 0.2 + part_no * 0.1 + token_score * 0.1
    return SimilarityScores(
        tfidf_score=tfidf,
        fuzzy_score=fuzzy,
        description_similarity=description,
        part_no_similarity=part_no,
        technical_token_score=token_score,
        final_score=round(max(0.0, min(100.0, final)), 2),
    )
