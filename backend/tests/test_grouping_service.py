import json
from types import SimpleNamespace

from app.services.grouping_service import build_duplicate_groups


def candidate(
    candidate_id,
    part_a,
    part_b,
    score,
    confidence="MEDIUM",
    matched=None,
    mismatched=None,
):
    return SimpleNamespace(
        id=candidate_id,
        contract_a="S1",
        part_no_a=part_a,
        description_a=f"{part_a} description",
        contract_b="S1",
        part_no_b=part_b,
        description_b=f"{part_b} description",
        similarity_score=score,
        confidence_level=confidence,
        matched_fields=json.dumps(matched or ["CONTRACT", "UNIT_MEAS"]),
        mismatched_fields=json.dumps(mismatched or []),
        explanation="Descriptions are similar and selected business fields match.",
    )


def test_build_duplicate_groups_connects_medium_high_pairs():
    groups = build_duplicate_groups([
        candidate(1, "A", "B", 88, "MEDIUM"),
        candidate(2, "B", "C", 92, "HIGH"),
    ])

    assert len(groups) == 1
    assert groups[0]["part_count"] == 3
    assert groups[0]["pair_count"] == 2
    assert groups[0]["top_score"] == 92
    assert groups[0]["confidence_level"] == "HIGH"
    assert groups[0]["matched_fields"] == ["CONTRACT", "UNIT_MEAS"]


def test_build_duplicate_groups_ignores_low_confidence_pairs():
    groups = build_duplicate_groups([
        candidate(1, "A", "B", 65, "LOW"),
        candidate(2, "C", "D", 52, "IGNORE"),
    ])

    assert groups == []
