from dataclasses import asdict, dataclass

import pandas as pd

from app.core.config import Settings
from app.services.hybrid_retrieval import HybridCandidateRetriever, RetrievalTier


SILVER_PART_PAIRS = (
    frozenset(("AS-B38-FP", "ES/AS-B38-FP")),
    frozenset(("AS-COM-STAT", "KA/ASCOMSTAT1")),
    frozenset(("AS-COM-ROT", "KA/ASCOMROT1")),
    frozenset(("KM-FP", "KM/FUELPUMP")),
)
GENERIC_DESCRIPTIONS = frozenset(("normal time", "circuit board"))


@dataclass(frozen=True)
class RetrievalBenchmarkReport:
    silver_recall_at_global_budget: float
    silver_recall_at_top_k: float
    generic_candidate_rate: float
    conflict_candidate_rate: float
    tier_a_silver_recall: float
    average_candidates_per_record: float
    largest_family_share: float
    provider_request_count: int
    retained_pairs: int
    distinct_priorities: int


def ranking_v2_fixture() -> pd.DataFrame:
    rows = [
        ("AS-B38-FP", "B38 Engine Fuel Pump"),
        ("ES/AS-B38-FP", "B38 Engine Fuel Pump"),
        ("AS-COM-STAT", "F30 Engine Compressor Stator"),
        ("KA/ASCOMSTAT1", "F30 Engine Compressor Stator"),
        ("AS-COM-ROT", "F30 Engine Compressor Rotor"),
        ("KA/ASCOMROT1", "F30 Engine Compressor Rotor"),
        ("KM-FP", "Fuel Pump"),
        ("KM/FUELPUMP", "Fuel Pump"),
        ("SERIAL-A", "KM Rental Part Serial"),
        ("SERIAL-B", "KM Rental Part Non Serial"),
        ("RED-1", "Red Paint 1L"),
        ("BLUE-1", "Blue Paint 1L"),
    ]
    rows.extend((f"TIME-{index}", "Normal Time") for index in range(10))
    rows.extend((f"BOARD-{index}", "Circuit Board") for index in range(6))
    rows.extend((f"DISTRACTOR-{index}", f"Warehouse Consumable Item {index}") for index in range(8))
    return pd.DataFrame([
        {"PART_NO": part, "DESCRIPTION": description, "CONTRACT": "S1", "UNIT_MEAS": "EA"}
        for part, description in rows
    ])


def evaluate_retrieval_benchmark(data: pd.DataFrame, result, top_k: int = 10) -> RetrievalBenchmarkReport:
    records = [row.to_dict() for _, row in data.reset_index(drop=True).iterrows()]

    def part_pair(candidate):
        return frozenset((
            str(records[candidate.left_record_id]["PART_NO"]),
            str(records[candidate.right_record_id]["PART_NO"]),
        ))

    retained = {part_pair(candidate) for candidate in result.candidates}
    top = {part_pair(candidate) for candidate in result.candidates[:top_k]}
    tier_a = {
        part_pair(candidate) for candidate in result.candidates
        if candidate.retrieval_tier == RetrievalTier.TIER_A
    }
    generic_count = 0
    conflict_count = 0
    for candidate in result.candidates:
        left = str(records[candidate.left_record_id]["DESCRIPTION"]).casefold()
        right = str(records[candidate.right_record_id]["DESCRIPTION"]).casefold()
        generic_count += left == right and left in GENERIC_DESCRIPTIONS
        conflict_count += bool(
            {"OPPOSITE_VARIANT_TERM", "TECHNICAL_CONFLICT"}
            & set(candidate.evidence.conflict_signals)
        )
    total = max(1, len(result.candidates))
    silver_total = len(SILVER_PART_PAIRS)
    return RetrievalBenchmarkReport(
        silver_recall_at_global_budget=round(len(retained & set(SILVER_PART_PAIRS)) / silver_total, 4),
        silver_recall_at_top_k=round(len(top & set(SILVER_PART_PAIRS)) / silver_total, 4),
        generic_candidate_rate=round(generic_count / total, 4),
        conflict_candidate_rate=round(conflict_count / total, 4),
        tier_a_silver_recall=round(len(tier_a & set(SILVER_PART_PAIRS)) / silver_total, 4),
        average_candidates_per_record=result.metrics.average_candidates_per_record,
        largest_family_share=result.metrics.candidate_family_concentration,
        provider_request_count=result.metrics.provider_request_count,
        retained_pairs=len(result.candidates),
        distinct_priorities=len({candidate.retrieval_priority for candidate in result.candidates}),
    )


def run_offline_benchmark(configuration: Settings | None = None) -> dict:
    configuration = configuration or Settings(
        llm_provider="none",
        llm_demo_enabled=False,
        hybrid_retrieval_enabled=True,
        hybrid_retrieval_lexical_top_k=5,
        hybrid_retrieval_vector_top_k=5,
        hybrid_retrieval_final_top_k=5,
        hybrid_retrieval_max_pairs_per_scan=20,
        hybrid_retrieval_tier_a_max=10,
        hybrid_retrieval_tier_b_max=8,
        hybrid_retrieval_tier_c_max=2,
        hybrid_retrieval_family_max=3,
    )
    data = ranking_v2_fixture()
    result = HybridCandidateRetriever(configuration).retrieve(data, "SAME_SITE_DUPLICATE")
    return asdict(evaluate_retrieval_benchmark(data, result))
