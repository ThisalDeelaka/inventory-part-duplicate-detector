"""Deterministic contracts for the assessment-only R18D analysis."""

from copy import deepcopy

import pytest

from app.benchmarks.r18d_review_support_burden import (
    GF5_PARTITION_OBJECTIVE,
    _scan33_summary,
    bounded_group_counterfactual,
    group_impact,
    matrix_report,
    review_origin,
    review_usefulness,
)


def _row(label, edge_class):
    return {"expert_label": label, "post_r18c_edge_class": edge_class}


def _assessment(*, dominance=False, independent=True, incoherent=False):
    return {
        "description_dominance": dominance,
        "independent_identity_support_present": independent,
        "cross_field_incoherence": incoherent,
    }


def _context():
    return {
        "groups": {
            1: {"members": {"A", "B", "C"}, "status": "POSSIBLE_DUPLICATE_GROUP_REVIEW"},
            2: {"members": {"D", "E"}, "status": "LIKELY_DUPLICATE_GROUP"},
        },
        "deferred": {3: {"members": {"F", "G"}, "status": "AMBIGUOUS"}},
        "conflicts": {4: {"members": {"H", "I"}, "status": "PROTECTED"}},
        "work_units": ({"A", "B", "C", "J"}, {"D", "E"}, {"F", "G"}, {"H", "I"}),
        "internal_by_group": {
            1: [
                {"stable_record_reference_1": "A", "stable_record_reference_2": "B", "edge_class": "REVIEW_SUPPORT"},
                {"stable_record_reference_1": "B", "stable_record_reference_2": "C", "edge_class": "REVIEW_SUPPORT"},
            ],
            2: [
                {"stable_record_reference_1": "D", "stable_record_reference_2": "E", "edge_class": "STRONG_SUPPORT"},
            ],
        },
    }


def test_post_r18c_matrix_accounts_for_every_row_and_percentages():
    rows = [
        _row("SAME_IDENTITY", "REVIEW_SUPPORT"),
        _row("SAME_IDENTITY", "STRONG_SUPPORT"),
        _row("DIFFERENT_IDENTITY", "CANNOT_LINK"),
        _row("INSUFFICIENT_INFORMATION", "NON_GROUPABLE"),
    ]
    report = matrix_report(rows)
    assert sum(sum(values.values()) for values in report["counts"].values()) == 4
    assert report["counts"]["SAME_IDENTITY"]["REVIEW_SUPPORT"] == 1
    assert report["row_percentages"]["SAME_IDENTITY"]["REVIEW_SUPPORT"] == 50.0
    assert report["column_percentages"]["CANNOT_LINK"]["DIFFERENT_IDENTITY"] == 100.0


def test_native_and_r18c_demoted_review_are_separate():
    assert review_origin("REVIEW_SUPPORT", "REVIEW_SUPPORT") == "NATIVE_REVIEW"
    assert review_origin("STRONG_SUPPORT", "REVIEW_SUPPORT") == "R18C_DEMOTED_STRONG_TO_REVIEW"
    with pytest.raises(ValueError):
        review_origin("STRONG_SUPPORT", "STRONG_SUPPORT")


def test_review_usefulness_categories_are_analysis_only_and_complete():
    assert review_usefulness("SAME_IDENTITY", _assessment()) == "USEFUL_REVIEW_SUPPORT"
    assert review_usefulness("INSUFFICIENT_INFORMATION", _assessment()) == "OVERCOMMITTED_REVIEW_SUPPORT"
    assert review_usefulness(
        "DIFFERENT_IDENTITY", _assessment(dominance=True, independent=False)
    ) == "NOISY_REVIEW_SUPPORT"
    assert review_usefulness("DIFFERENT_IDENTITY", _assessment()) == "AMBIGUOUS_REVIEW_SUPPORT"


def test_group_impact_mapping_uses_only_persisted_membership():
    context = _context()
    assert group_impact("A", "B", context)[0] == "SUPPORTS_ACCEPTED_REVIEW_GROUP"
    assert group_impact("D", "E", context)[0] == "SUPPORTS_ACCEPTED_LIKELY_GROUP"
    assert group_impact("F", "G", context)[0] == "CONTRIBUTES_TO_DEFERRED_FAMILY"
    assert group_impact("H", "I", context)[0] == "CONTRIBUTES_TO_CONFLICT_CONTEXT"
    assert group_impact("A", "J", context)[0] == "BRIDGE_OR_PARTITION_RELEVANT"
    assert group_impact("X", "Y", context)[0] == "NOT_IN_ANY_RESOLUTION_WORK_UNIT"


def test_counterfactual_is_deterministic_and_does_not_mutate_evidence():
    context = _context()
    rows = [{
        "record_a_stable_ref": "A", "record_b_stable_ref": "B",
        "risk_high_specificity": "true", "expert_label": "SAME_IDENTITY",
    }]
    before_context, before_rows = deepcopy(context), deepcopy(rows)
    first = bounded_group_counterfactual(rows, context, "risk_high_specificity")
    second = bounded_group_counterfactual(rows, context, "risk_high_specificity")
    assert first == second
    assert first["accepted_groups_connectivity_lost"] == 1
    assert first["expert_same_supported_groups_harmed"] == 1
    assert first["cannot_link_safety"] == "UNCHANGED"
    assert context == before_context and rows == before_rows


def test_scan33_reference_preserves_bicycle_and_head_tail():
    summary = _scan33_summary(None)
    assert summary["proposal_count"] == summary["evidence_edge_count"] == 1124
    assert summary["cross_site_proposal_count"] == 21
    assert summary["bicycle_relationship_count"] == 21
    assert summary["bicycle_all_review"] is True
    assert summary["head_tail_cannot_link"] is True
    assert summary["provider_calls"] == 0


def test_gf5_partition_policy_debt_is_explicit_and_not_silently_corrected():
    assert GF5_PARTITION_OBJECTIVE == "(covered, likely_members, strong, -review, -group_count)"
