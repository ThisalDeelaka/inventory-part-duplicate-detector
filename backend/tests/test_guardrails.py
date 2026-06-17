from app.engine.guardrails import apply_guardrails
from app.engine.models import CandidatePair, PartRecord
from app.engine.similarity import score_candidate_pair


def candidate(part_a, desc_a, part_b, desc_b, extra_a=None, extra_b=None):
    raw_a = {"PART_NO": part_a, "DESCRIPTION": desc_a, "CONTRACT": "S1", "UNIT_MEAS": "PCS"}
    raw_b = {"PART_NO": part_b, "DESCRIPTION": desc_b, "CONTRACT": "S1", "UNIT_MEAS": "PCS"}
    raw_a.update(extra_a or {})
    raw_b.update(extra_b or {})
    return CandidatePair(
        record_a=PartRecord(part_no=part_a, description=desc_a, contract=raw_a.get("CONTRACT"), raw=raw_a),
        record_b=PartRecord(part_no=part_b, description=desc_b, contract=raw_b.get("CONTRACT"), raw=raw_b),
        matched_fields=["UNIT_MEAS"],
    )


def guard(part_a, desc_a, part_b, desc_b, extra_a=None, extra_b=None, cross_site=False):
    pair = candidate(part_a, desc_a, part_b, desc_b, extra_a, extra_b)
    return apply_guardrails(pair, score_candidate_pair(pair), cross_site=cross_site)


def test_mcb_rating_mismatch_is_hard_conflict():
    result = guard("MCB-20", "MCB 20A", "MCB-30", "MCB30A")

    assert result.hard_conflict is True
    assert "rating_mismatch" in result.conflict_types


def test_paint_color_mismatch_is_hard_conflict():
    result = guard("PAINT-RED", "RED PAINT 1L CAN", "PAINT-BLUE", "BLUE PAINT 1L CAN")

    assert result.hard_conflict is True
    assert "color_mismatch" in result.conflict_types


def test_coconut_type_code_mismatch_is_hard_conflict():
    result = guard("COCO-1", "Decicated Coconut type 1", "COCO-2", "Decicated Coconut type 2")

    assert result.hard_conflict is True
    assert "type_code_mismatch" in result.conflict_types


def test_filter_function_media_mismatch_is_hard_conflict():
    result = guard("GEN-FUEL-FLT", "Generator Fuel Filter", "GEN-AIR-FLT", "Generator Air Filter")

    assert result.hard_conflict is True
    assert "function_or_media_mismatch" in result.conflict_types


def test_application_context_mismatch_is_warning_only():
    result = guard("SP-GEN-AIR-FLT", "Generator Air Filter", "HVAC-FILTER-01", "HVAC Air Filter")

    assert result.hard_conflict is False
    assert result.review_warning is True
    assert "application_context_mismatch" in result.warning_types


def test_generic_sparse_description_is_warning():
    result = guard("TR LABELS", "Labels", "TR WARNING LABELS", "Warning labels")

    assert result.review_warning is True
    assert "generic_or_sparse_description" in result.warning_types


def test_hsn_sac_mismatch_is_data_conflict():
    result = guard(
        "A",
        "Stainless Steel Pipe",
        "B",
        "Stainless Steel Pipe",
        {"HSN_SAC_CODE": "7306"},
        {"HSN_SAC_CODE": "3917"},
    )

    assert result.data_conflict is True
    assert "hsn_sac_mismatch" in result.conflict_types


def test_safety_code_mismatch_is_data_conflict():
    result = guard(
        "A",
        "Hydraulic Oil",
        "B",
        "Hydraulic Oil",
        {"SAFETY_CODE": "HZ1"},
        {"SAFETY_CODE": "HZ2"},
    )

    assert result.data_conflict is True
    assert "safety_code_mismatch" in result.conflict_types


def test_contract_mismatch_without_cross_site_is_scope_conflict():
    result = guard(
        "A",
        "SS Pipe",
        "B",
        "Stainless Steel Pipe",
        {"CONTRACT": "S1"},
        {"CONTRACT": "S2"},
        cross_site=False,
    )

    assert result.hard_conflict is True
    assert result.scope_warning is True
    assert "contract_scope_mismatch" in result.conflict_types


def test_contract_mismatch_with_cross_site_is_warning_not_hard_conflict():
    result = guard(
        "A",
        "SS Pipe",
        "B",
        "Stainless Steel Pipe",
        {"CONTRACT": "S1"},
        {"CONTRACT": "S2"},
        cross_site=True,
    )

    assert result.hard_conflict is False
    assert result.scope_warning is True
    assert "cross_site_candidate" in result.warning_types
