from app.engine.models import SimilarityScores
from app.engine.similarity_model import (
    calculate_fuzzy_similarity,
    calculate_part_no_similarity,
    calculate_technical_token_score,
    calculate_tfidf_similarity,
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

