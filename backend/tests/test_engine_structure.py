import importlib

from app.engine.models import DecisionResult, STATUSES
from app.engine.semantic_policy import DEFAULT_COLUMN_POLICY


ENGINE_MODULES = [
    "app.engine.models",
    "app.engine.semantic_policy",
    "app.engine.normalizer",
    "app.engine.attribute_extractor",
    "app.engine.candidate_generator",
    "app.engine.similarity",
    "app.engine.guardrails",
    "app.engine.decision_engine",
    "app.engine.explanations",
    "app.engine.profiler",
]

REQUIRED_STATUSES = {
    "DUPLICATE_CANDIDATE",
    "POSSIBLE_DUPLICATE_REVIEW",
    "RELATED_BUT_NOT_DUPLICATE",
    "DATA_CONFLICT_REVIEW",
    "CROSS_SITE_STANDARDIZATION_CANDIDATE",
    "INSUFFICIENT_DATA",
    "UNIQUE_NO_MATCH",
}

POLICY_COLUMNS = {
    "CONTRACT",
    "PART_NO",
    "DESCRIPTION",
    "MASTER_PART_DESCRIPTION",
    "PART_TYPE",
    "INVENTORY_UOM",
    "COMMODITY_GROUP_1",
    "COMMODITY_GROUP_2",
    "SAFETY_CODE",
    "ACCOUNTING_GROUP",
    "PART_PRODUCT_CODE",
    "PART_PRODUCT_FAMILY",
    "PRODUCT_CATEGORY_ID",
    "HSN_SAC_CODE",
}


def test_engine_modules_import_successfully():
    for module in ENGINE_MODULES:
        assert importlib.import_module(module)


def test_required_statuses_exist():
    assert REQUIRED_STATUSES <= STATUSES


def test_default_semantic_policy_contains_required_columns():
    assert POLICY_COLUMNS == set(DEFAULT_COLUMN_POLICY)
    for column, policy in DEFAULT_COLUMN_POLICY.items():
        assert policy["meaning"]
        assert policy["role"]
        assert policy["importance"]
        assert policy["behavior_if_same"]
        assert policy["behavior_if_different"]
        assert policy["behavior_if_missing"]


def test_decision_result_can_be_created_with_required_fields():
    result = DecisionResult(
        status="POSSIBLE_DUPLICATE_REVIEW",
        confidence_score=72.5,
        confidence_level="LOW",
        explanation="Manual review required.",
        matched_evidence=["DESCRIPTION"],
        differences=[{"field": "UNIT_MEAS"}],
        warnings=["Example warning"],
        rule_decision="DOWNGRADE",
        rejection_reason="GENERIC_DESCRIPTION",
        normalized_part_no_a="dec type 1",
        normalized_part_no_b="dec type 1",
        normalized_description_a="desiccated coconut type 1",
        normalized_description_b="desiccated coconut type 1",
        extracted_attributes_a={"type": ["type 1"]},
        extracted_attributes_b={"type": ["type 1"]},
    )

    assert result.status == "POSSIBLE_DUPLICATE_REVIEW"
    assert result.confidence_score == 72.5
    assert result.normalized_description_a == "desiccated coconut type 1"
