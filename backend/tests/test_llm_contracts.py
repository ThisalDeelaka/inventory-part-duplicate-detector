import pytest
from pydantic import ValidationError

from app.llm.contracts import (
    CandidateAdvisoryRequest,
    CandidateAdvisoryResponse,
    CandidateEvidence,
    ColumnSuggestionRequest,
    ColumnSuggestionResponse,
    CriticalMismatchEvidence,
    DifficultValueRequest,
    DifficultValueResponse,
)


def _column_response(**overrides):
    values = {
        "source_column": "Stock Identifier",
        "suggested_canonical_field": "PART_NO",
        "confidence": 0.8,
        "reason": "Values resemble part identifiers.",
        "requires_confirmation": True,
    }
    values.update(overrides)
    return values


def _advisory_request(**overrides):
    values = {
        "left": {"part_number": "A-1", "description": "Motor 10 kW", "uom": "PCS"},
        "right": {"part_number": "A-2", "description": "10kW motor", "uom": "PCS"},
        "deterministic_score": 82.5,
        "deterministic_confidence": "MEDIUM",
        "deterministic_status": "POSSIBLE_DUPLICATE_REVIEW",
        "deterministic_rule_decision": "ALLOW",
        "rejection_reason": None,
        "critical_mismatches": [],
    }
    values.update(overrides)
    return values


def _advisory_response(**overrides):
    values = {
        "assessment": "INCONCLUSIVE",
        "confidence": 0.5,
        "supporting_evidence": ["Descriptions share motor capacity."],
        "conflicting_evidence": [],
        "recommended_action": "HUMAN_REVIEW",
        "deterministic_result_authoritative": True,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_contract_confidence_is_bounded(confidence):
    with pytest.raises(ValidationError):
        ColumnSuggestionResponse(**_column_response(confidence=confidence))
    with pytest.raises(ValidationError):
        CandidateAdvisoryResponse(**_advisory_response(confidence=confidence))


def test_contracts_reject_unexpected_fields():
    with pytest.raises(ValidationError):
        ColumnSuggestionRequest(
            source_column="Stock ID",
            sample_values=["A-1"],
            allowed_canonical_fields=["PART_NO"],
            complete_dataset=[{"secret": "row"}],
        )


def test_column_samples_are_small_bounded_and_useful():
    with pytest.raises(ValidationError):
        ColumnSuggestionRequest(
            source_column="Stock ID",
            sample_values=["1", "2", "3", "4", "5", "6"],
            allowed_canonical_fields=["PART_NO"],
        )
    with pytest.raises(ValidationError):
        ColumnSuggestionRequest(
            source_column="Stock ID",
            sample_values=["", "   "],
            allowed_canonical_fields=["PART_NO"],
        )
    with pytest.raises(ValidationError):
        ColumnSuggestionRequest(
            source_column="Stock ID",
            sample_values=["x" * 513],
            allowed_canonical_fields=["PART_NO"],
        )


def test_column_suggestion_requires_confirmation_and_can_abstain():
    with pytest.raises(ValidationError):
        ColumnSuggestionResponse(**_column_response(requires_confirmation=False))

    response = ColumnSuggestionResponse(
        **_column_response(suggested_canonical_field=None, confidence=0)
    )
    assert response.suggested_canonical_field is None


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"item_family_context": None},
        {"item_family_context": "Electric motor"},
    ],
)
def test_difficult_value_item_family_context_is_genuinely_optional(context):
    request = DifficultValueRequest(
        raw_value="MTR 10KW", field_context="DESCRIPTION", **context
    )
    assert request.raw_value == "MTR 10KW"

    with pytest.raises(ValidationError):
        DifficultValueRequest(
            raw_value="MTR 10KW",
            field_context="DESCRIPTION",
            unexpected="not allowed",
        )


def test_difficult_value_response_preserves_raw_value_and_bounds_collections():
    response = DifficultValueResponse(
        raw_value="MTR 10KW",
        normalized_interpretation="10 kilowatt motor",
        attributes={"power": "10 kW"},
        confidence=0.75,
        warnings=["Confirm voltage separately."],
        requires_confirmation=True,
    )
    assert response.raw_value == "MTR 10KW"

    base = response.model_dump()
    with pytest.raises(ValidationError):
        DifficultValueResponse(**{**base, "attributes": {f"key-{i}": "v" for i in range(21)}})
    with pytest.raises(ValidationError):
        DifficultValueResponse(**{**base, "warnings": ["warning"] * 11})
    with pytest.raises(ValidationError):
        DifficultValueResponse(**{**base, "attributes": {"key": {"nested": "forbidden"}}})


def test_candidate_evidence_is_allowlisted_and_rejects_full_rows():
    evidence = CandidateEvidence(
        part_number="A-1",
        description="Motor",
        master_description=None,
        uom="PCS",
        site_or_contract="S1",
    )
    assert evidence.part_number == "A-1"
    with pytest.raises(ValidationError):
        CandidateEvidence(part_number="A-1", unit_price="100.00", supplier="private")


@pytest.mark.parametrize(
    "evidence",
    [
        {},
        {"uom": "PCS"},
        {"site_or_contract": "S1"},
        {"description": "   ", "uom": "PCS"},
    ],
)
def test_candidate_evidence_rejects_missing_identity(evidence):
    with pytest.raises(ValidationError):
        CandidateEvidence(**evidence)


@pytest.mark.parametrize(
    "evidence",
    [
        {"description": "Motor 10 kW"},
        {"part_number": "A-100"},
    ],
)
def test_candidate_evidence_accepts_identity_fields(evidence):
    assert CandidateEvidence(**evidence)


def test_candidate_request_reuses_deterministic_scales_and_values():
    request = CandidateAdvisoryRequest(**_advisory_request())
    assert request.deterministic_score == 82.5
    assert request.deterministic_confidence.value == "MEDIUM"

    with pytest.raises(ValidationError):
        CandidateAdvisoryRequest(**_advisory_request(deterministic_score=101))
    with pytest.raises(ValidationError):
        CandidateAdvisoryRequest(**_advisory_request(deterministic_confidence="CERTAIN"))
    with pytest.raises(ValidationError):
        CandidateAdvisoryRequest(**_advisory_request(deterministic_status="LLM_DUPLICATE"))
    with pytest.raises(ValidationError):
        CandidateAdvisoryRequest(**_advisory_request(deterministic_rule_decision="OVERRIDE"))


def test_candidate_advisory_values_and_authority_are_constrained():
    response = CandidateAdvisoryResponse(**_advisory_response())
    assert response.deterministic_result_authoritative is True

    with pytest.raises(ValidationError):
        CandidateAdvisoryResponse(
            **_advisory_response(deterministic_result_authoritative=False)
        )
    with pytest.raises(ValidationError):
        CandidateAdvisoryResponse(**_advisory_response(assessment="FINAL_DUPLICATE"))
    with pytest.raises(ValidationError):
        CandidateAdvisoryResponse(**_advisory_response(recommended_action="AUTO_MERGE"))


def test_candidate_critical_mismatch_evidence_is_bounded():
    mismatch = {
        "group": "UNIT_MEAS",
        "label": "Inventory UOM",
        "values_a": ["PCS"],
        "values_b": ["KG"],
    }
    request = CandidateAdvisoryRequest(
        **_advisory_request(critical_mismatches=[mismatch])
    )
    assert request.critical_mismatches[0].group == "UNIT_MEAS"

    with pytest.raises(ValidationError):
        CriticalMismatchEvidence(**{**mismatch, "values_a": []})
    with pytest.raises(ValidationError):
        CriticalMismatchEvidence(**{**mismatch, "values_b": []})
    assert CriticalMismatchEvidence(**mismatch)

    with pytest.raises(ValidationError):
        CandidateAdvisoryRequest(
            **_advisory_request(critical_mismatches=[mismatch] * 11)
        )
