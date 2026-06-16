from functools import lru_cache

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.engine.normalizer import extract_technical_tokens, normalize_description, normalize_part_no_with_dictionary


@lru_cache(maxsize=100_000)
def calculate_tfidf_similarity(text_a, text_b) -> float:
    a, b = normalize_description(text_a), normalize_description(text_b)
    if not a or not b:
        return 0.0
    try:
        matrix = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform([a, b])
        return round(float(cosine_similarity(matrix[0], matrix[1])[0, 0] * 100), 2)
    except ValueError:
        return 0.0


@lru_cache(maxsize=100_000)
def calculate_fuzzy_similarity(text_a, text_b) -> float:
    a, b = normalize_description(text_a), normalize_description(text_b)
    if not a or not b:
        return 0.0
    return round((fuzz.token_set_ratio(a, b) * 0.6) + (fuzz.partial_ratio(a, b) * 0.4), 2)


@lru_cache(maxsize=100_000)
def calculate_part_no_similarity(part_no_a, part_no_b) -> float:
    a = normalize_part_no_with_dictionary(part_no_a).replace(" ", "")
    b = normalize_part_no_with_dictionary(part_no_b).replace(" ", "")
    if not a or not b:
        return 0.0
    return round(float(fuzz.ratio(a, b)), 2)


def calculate_technical_token_score(tokens_a, tokens_b) -> float:
    if not isinstance(tokens_a, dict):
        tokens_a = extract_technical_tokens(tokens_a)
    if not isinstance(tokens_b, dict):
        tokens_b = extract_technical_tokens(tokens_b)
    comparable = 0
    total = 0.0
    for key, weight in (("numbers", 40), ("measurements", 25), ("dimensions", 15), ("units", 10), ("modifiers", 10)):
        a, b = set(tokens_a.get(key, [])), set(tokens_b.get(key, []))
        if not a and not b:
            continue
        comparable += weight
        if a == b:
            total += weight
        elif a and b:
            total += weight * (len(a & b) / len(a | b))
    if comparable == 0:
        return 50.0
    return round(max(0.0, min(100.0, total / comparable * 100)), 2)
