from collections import Counter

from app.engine.candidate_generator import generate_candidate_pairs
from app.engine.guardrails import apply_guardrails
from app.engine.models import DecisionResult, PartRecord
from app.engine.decision_engine import make_decision
from app.engine.similarity import score_candidate_pair


def run_duplicate_detection_pipeline(
    records: list[PartRecord],
    selected_fields: list[str] | None = None,
    cross_site: bool = False,
) -> list[DecisionResult]:
    candidates = generate_candidate_pairs(
        records,
        selected_fields=selected_fields,
        cross_site=cross_site,
    )

    results = []
    for candidate in candidates:
        similarity = score_candidate_pair(candidate)
        guardrails = apply_guardrails(candidate, similarity, cross_site=cross_site)
        results.append(make_decision(candidate, similarity, guardrails, cross_site=cross_site))
    return results


def build_pipeline_summary(results: list[DecisionResult]) -> dict:
    counts = Counter(result.status for result in results)
    return {
        "total_results": len(results),
        "counts_by_status": dict(sorted(counts.items())),
    }
