from dataclasses import asdict
from types import SimpleNamespace

from app.identity_read.explanations import (
    explain_deferred_identity_work,
    explain_identity_conflict,
    explain_identity_group,
)


def _member(index, *, part_no=None, description=None, category="MOTOR"):
    part_no = part_no or f"P-{index}"
    description = description or f"Motor item {index}"
    return SimpleNamespace(
        normalized_part_no=part_no.lower(),
        normalized_description=description.lower(),
        product_category_id=category,
        hsn_sac_code=None,
        type_code=None,
    )


def _group(
    status="POSSIBLE_DUPLICATE_GROUP_REVIEW",
    *,
    members=None,
    strong=0,
    review=1,
    neutral=0,
    missing=0,
    generic=False,
    review_only=False,
    insufficient=False,
    bridge=False,
):
    members = tuple(members or (_member(1), _member(2)))
    possible = len(members) * (len(members) - 1) // 2
    evaluated = strong + review + neutral
    return SimpleNamespace(
        status=status,
        members=members,
        validation_coverage=SimpleNamespace(
            evaluated_internal_pair_count=evaluated,
            possible_internal_pair_count=possible,
            strong_support_count=strong,
            review_support_count=review,
            non_groupable_count=neutral,
            missing_nonrequired_pair_count=missing,
        ),
        group_evidence_summary=None,
        genericity_risk_summary=SimpleNamespace(
            generic_description_burden=generic,
            review_only_support=review_only,
            insufficient_independent_identity_evidence=insufficient,
        ),
        bridge_risk_summary=SimpleNamespace(unresolved=bridge),
        missing_evidence_summary=SimpleNamespace(
            unresolved_ownership_ambiguity=False
        ),
    )


def _all_text(explanation):
    return " ".join(
        (
            explanation.headline,
            explanation.summary,
            *explanation.supporting_points,
            *explanation.caution_points,
            explanation.review_guidance,
        )
    ).lower()


def test_t1_same_persisted_input_has_deterministic_explanation():
    group = _group()
    assert asdict(explain_identity_group(group)) == asdict(explain_identity_group(group))


def test_t2_likely_and_review_have_distinct_status_specific_language():
    likely = explain_identity_group(_group("LIKELY_DUPLICATE_GROUP", strong=1, review=0))
    review = explain_identity_group(_group())
    assert likely.headline == "Stronger system-generated duplicate hypothesis"
    assert review.headline == "Possible duplicate identity - human review required"
    assert likely.headline != review.headline


def test_t3_t4_machine_hypotheses_never_claim_human_confirmation():
    for status in ("LIKELY_DUPLICATE_GROUP", "POSSIBLE_DUPLICATE_GROUP_REVIEW"):
        text = _all_text(explain_identity_group(_group(status, strong=1, review=0)))
        assert "confirmed duplicate" not in text
        assert "confirmed as" not in text
        assert "same physical item" not in text


def test_t5_generic_or_copied_evidence_is_a_caution_not_identity_proof():
    explanation = explain_identity_group(_group(generic=True))
    assert any("generic or copied" in point for point in explanation.caution_points)
    assert "GROUP_WIDE_NORMALIZED_DESCRIPTION" not in explanation.evidence_basis


def test_t6_persisted_protected_conflict_gets_non_group_language():
    explanation = explain_identity_conflict(SimpleNamespace(
        conflict_type="PROTECTED_CANNOT_LINK",
        involved_record_references=("a", "b"),
        summary="Opposite persisted side variants",
    ))
    text = _all_text(explanation)
    assert "not grouped automatically" in text
    assert "protected contradictory evidence" in text
    assert "opposite persisted side variants" in text


def test_t7_historical_group_without_specific_evidence_uses_honest_fallback():
    group = SimpleNamespace(
        status="POSSIBLE_DUPLICATE_GROUP_REVIEW",
        members=(_member(1, category=""), _member(2, category="")),
        validation_coverage=None,
        group_evidence_summary=None,
        genericity_risk_summary=None,
        bridge_risk_summary=None,
        missing_evidence_summary=None,
    )
    explanation = explain_identity_group(group)
    assert "does not establish a clear identity-specific reason" in explanation.summary
    assert "HONEST_GROUP_FALLBACK" in explanation.evidence_basis


def test_t8_three_member_mixed_evidence_does_not_turn_pair_facts_into_group_facts():
    explanation = explain_identity_group(_group(
        members=(_member(1), _member(2), _member(3)),
        strong=1,
        review=1,
        neutral=1,
    ))
    text = _all_text(explanation)
    assert "1 evaluated record relationship" in text
    assert "2 of 3 evaluated relationships support review" in text
    assert "all relationships" not in text
    assert any("neutral" in point for point in explanation.caution_points)


def test_t10_historical_explanation_is_stable_for_dict_shaped_persistence():
    group = {
        "status": "POSSIBLE_DUPLICATE_GROUP_REVIEW",
        "members": (
            {"normalized_part_no": "x", "normalized_description": "pump"},
            {"normalized_part_no": "x", "normalized_description": "pump"},
        ),
        "validation_coverage": {
            "evaluated_internal_pair_count": 1,
            "possible_internal_pair_count": 1,
            "strong_support_count": 0,
            "review_support_count": 1,
            "non_groupable_count": 0,
            "missing_nonrequired_pair_count": 0,
        },
        "genericity_risk_summary": {"review_only_support": True},
    }
    first = explain_identity_group(group)
    second = explain_identity_group(group)
    assert first == second
    assert "GROUP_WIDE_NORMALIZED_PART_NUMBER" in first.evidence_basis


def test_t12_no_score_is_rendered_as_probability_or_confidence():
    explanation = explain_identity_group(_group())
    text = _all_text(explanation)
    assert "%" not in text
    assert "confidence" not in text
    assert "probability" not in text


def test_t13_t14_explanation_is_provider_free_and_does_not_mutate_input():
    group = _group()
    before = dict(vars(group))
    explain_identity_group(group)
    assert vars(group) == before
    source = __import__(
        "inspect"
    ).getsource(__import__("app.identity_read.explanations", fromlist=["*"]))
    assert "app.llm" not in source
    assert "provider" not in source.lower()


def test_r12_style_copied_description_does_not_overclaim_identity_or_model():
    group = _group(
        "LIKELY_DUPLICATE_GROUP",
        members=(
            _member(1, part_no="BRUSH-01", description="copied condition text", category=""),
            _member(2, part_no="PAINT-02", description="copied condition text", category=""),
        ),
        strong=1,
        review=0,
        generic=True,
    )
    text = _all_text(explain_identity_group(group))
    assert "same physical item" not in text
    assert "same model" not in text
    assert "confirmed duplicate" not in text
    assert "generic or copied" in text


def test_deferred_reason_and_unfinished_summary_are_preserved_without_a_decision():
    explanation = explain_deferred_identity_work(SimpleNamespace(
        reason="TARGETED_EVIDENCE_BUDGET_EXHAUSTED",
        record_references=("a", "b", "c"),
        unfinished_evidence_summary="Two checks remain",
    ))
    text = _all_text(explanation)
    assert "no duplicate conclusion" in text
    assert "targeted-evidence budget was exhausted" in text
    assert "two checks remain" in text
