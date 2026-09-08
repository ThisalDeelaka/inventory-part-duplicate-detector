import random

from app.engine.scoring import score_candidate
from app.services.identity_group_projection import (
    FamilyDiagnosticStatus,
    IdentityGroupStatus,
    project_identity_groups,
)


def record(name, description=None, uom="PCS"):
    return {
        "CONTRACT": "S1",
        "PART_NO": name,
        "DESCRIPTION": description or f"Precision component {name}",
        "UNIT_MEAS": uom,
        "PRODUCT_CATEGORY_ID": "",
        "HSN_SAC_CODE": "",
    }


def pair(left, right, edge="review", candidate_id=None, **extra):
    status, decision = {
        "strong": ("LIKELY_DUPLICATE", "ALLOW"),
        "review": ("POSSIBLE_DUPLICATE_REVIEW", "ALLOW"),
        "neutral": ("INSUFFICIENT_DATA", "ALLOW"),
    }[edge]
    return {
        "id": candidate_id,
        "contract_a": left["CONTRACT"],
        "part_no_a": left["PART_NO"],
        "description_a": left["DESCRIPTION"],
        "contract_b": right["CONTRACT"],
        "part_no_b": right["PART_NO"],
        "description_b": right["DESCRIPTION"],
        "business_status": status,
        "rule_decision": decision,
        "rejection_reason": "",
        "critical_mismatches": [],
        **extra,
    }


def scored_pair(left, right, candidate_id=None, **extra):
    result = score_candidate(
        left, right, ["CONTRACT", "UNIT_MEAS"],
        allow_uom_mapping_review=True,
    )
    return {
        **pair(left, right, candidate_id=candidate_id),
        **result,
        **extra,
    }


def project(records, candidates, exclusions=(), **kwargs):
    return project_identity_groups(
        scan_id=7,
        records=records,
        candidates=candidates,
        exclusions=exclusions,
        selected_fields=["CONTRACT", "UNIT_MEAS"],
        **kwargs,
    )


def test_size_two_strong_creates_likely_group():
    a, b = record("A"), record("B")
    result = project([a, b], [pair(a, b, "strong")])
    assert len(result.groups) == 1
    assert result.groups[0].group_size == 2
    assert result.groups[0].group_status == IdentityGroupStatus.LIKELY_DUPLICATE_GROUP


def test_size_two_review_creates_review_group():
    a, b = record("A"), record("B")
    result = project([a, b], [pair(a, b)])
    assert result.groups[0].group_status == IdentityGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW


def test_size_three_all_strong_requires_all_three_internal_edges():
    items = [record(name) for name in "ABC"]
    edges = [pair(items[i], items[j], "strong") for i in range(3) for j in range(i + 1, 3)]
    result = project(items, edges)
    group = result.groups[0]
    assert group.group_size == 3
    assert group.group_status == IdentityGroupStatus.LIKELY_DUPLICATE_GROUP
    assert group.internal_pair_count == group.internal_pairs_reused == 3


def test_size_four_connected_review_validates_neutral_cross_pairs():
    items = [record(name, "Precision hydraulic valve") for name in "ABCD"]
    seeds = [pair(items[index], items[index + 1]) for index in range(3)]
    result = project(items, seeds)
    group = result.groups[0]
    assert group.group_size == 4
    assert group.group_status == IdentityGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
    assert group.internal_pair_count == 6
    assert group.internal_pairs_reused == 3
    assert group.internal_pairs_rescored == 3


def test_size_seven_has_no_pair_only_assumption():
    items = [record(str(index)) for index in range(7)]
    edges = [pair(items[i], items[j], "strong") for i in range(7) for j in range(i + 1, 7)]
    result = project(items, edges)
    assert result.groups[0].group_size == 7
    assert result.groups[0].internal_pair_count == 21
    assert result.metrics.internal_pairs_total == 21


def assert_bridge_conflict(left, bridge, right):
    result = project(
        [left, bridge, right],
        [pair(left, bridge), pair(bridge, right)],
        [scored_pair(left, right)],
    )
    assert result.groups == ()
    assert len(result.conflicting_families) == 1
    assert result.conflicting_families[0].cannot_link_count == 1
    return result.conflicting_families[0]


def test_mlr_bridge_is_conflicting():
    family = assert_bridge_conflict(
        record("TOP", "MLR TOP PART"),
        record("PUR", "MLR PURCHASED PART"),
        record("COMP", "MLR COMPONENT PART"),
    )
    assert "CRITICAL_MISMATCH_STRUCTURAL_ROLE" in family.reason_codes


def test_rotor_generic_stator_bridge_is_conflicting():
    family = assert_bridge_conflict(
        record("ROT", "F30 Compressor Rotor"),
        record("GEN", "F30 Compressor"),
        record("STAT", "F30 Compressor Stator"),
    )
    assert "CRITICAL_MISMATCH_STRUCTURAL_ROLE" in family.reason_codes


def test_circuit_board_bridge_is_conflicting():
    family = assert_bridge_conflict(
        record("CB01", "Circuit Board 01"),
        record("CB", "Circuit Board"),
        record("CB02", "Circuit Board 02"),
    )
    assert "CRITICAL_MISMATCH_TRAILING_VARIANT_SUFFIX" in family.reason_codes


def test_missing_cross_pair_is_rescored_without_mutating_inputs():
    a = record("A", "Precision pump")
    b = record("B", "Precision pump")
    c = record("C", "Precision pump")
    candidates = [pair(a, b), pair(b, c)]
    before = [dict(item) for item in candidates]
    result = project([a, b, c], candidates)
    assert result.metrics.internal_pairs_rescored == 1
    assert candidates == before
    assert result.groups[0].internal_pair_count == 3


def test_uom_summary_never_controls_identity_class():
    items = [
        record("A", "Turbine Lubricating Oil", "l"),
        record("B", "Turbine Lubricating Oil", "liq qt"),
        record("C", "Turbine Lubricating Oil", "PCS"),
        record("D", "Turbine Lubricating Oil", "*"),
    ]
    edges = [pair(items[i], items[j], "strong") for i in range(4) for j in range(i + 1, 4)]
    group = project(items, edges).groups[0]
    assert group.group_status == IdentityGroupStatus.LIKELY_DUPLICATE_GROUP
    assert group.uom_summary.convertible_uom_pair_count == 1
    assert group.uom_summary.different_basis_pair_count == 2
    assert group.uom_summary.missing_or_wildcard_pair_count == 3
    assert group.uom_summary.possible_mapping_error_count == 2


def test_human_non_duplicate_vetoes_connected_family():
    a, b, c = [record(name) for name in "ABC"]
    candidates = [
        pair(a, b, candidate_id=1),
        pair(b, c, candidate_id=2),
        pair(a, c, "strong", candidate_id=3),
    ]
    result = project(
        [a, b, c], candidates,
        feedback_by_candidate_id={3: {"user_decision": "NOT_DUPLICATE"}},
    )
    assert result.groups == ()
    assert result.conflicting_families[0].reason_codes == ("HUMAN_NON_DUPLICATE",)


def test_supportive_llm_metadata_cannot_override_conflict():
    rotor = record("ROT", "Compressor Rotor")
    generic = record("GEN", "Compressor")
    stator = record("STAT", "Compressor Stator")
    conflict = scored_pair(rotor, stator, llm_assessment="SUPPORTS_DUPLICATE")
    result = project(
        [rotor, generic, stator],
        [pair(rotor, generic), pair(generic, stator)],
        [conflict],
    )
    assert result.groups == ()
    assert "CRITICAL_MISMATCH_STRUCTURAL_ROLE" in result.conflicting_families[0].reason_codes


def test_input_order_does_not_change_projection():
    items = [record(name, "Precision control valve") for name in "ABCD"]
    edges = [pair(items[0], items[1]), pair(items[1], items[2]), pair(items[2], items[3])]
    first = project(items, edges)
    shuffled_items, shuffled_edges = list(items), list(edges)
    random.Random(19).shuffle(shuffled_items)
    random.Random(23).shuffle(shuffled_edges)
    second = project(shuffled_items, shuffled_edges)
    assert first == second


def test_oversized_family_is_deferred_without_validation_or_truncation():
    items = [record(f"P{index}") for index in range(21)]
    edges = [pair(items[index], items[index + 1]) for index in range(20)]
    result = project(items, edges)
    assert result.groups == ()
    assert len(result.deferred_families) == 1
    family = result.deferred_families[0]
    assert family.status == FamilyDiagnosticStatus.DEFERRED_OVERSIZED_FAMILY
    assert len(family.members) == 21
    assert result.metrics.internal_pairs_total == 0
    assert result.metrics.internal_pairs_rescored == 0


def test_conflicting_scan_local_record_evidence_defers_family():
    a_first = record("A", "Precision valve", "PCS")
    a_conflict = record("A", "Precision valve", "l")
    b = record("B", "Precision valve", "PCS")
    result = project([a_first, a_conflict, b], [pair(a_first, b)])
    assert result.groups == ()
    assert len(result.deferred_families) == 1
    assert result.deferred_families[0].status == (
        FamilyDiagnosticStatus.DEFERRED_AMBIGUOUS_RECORD_FAMILY
    )
    assert result.deferred_families[0].reason_codes == (
        "AMBIGUOUS_SCAN_LOCAL_RECORD_REF",
    )


def test_isolated_records_do_not_trigger_full_dataset_all_pairs():
    isolated = [record(f"ISO{index}") for index in range(200)]
    a, b, c, d = [record(name) for name in "ABCD"]
    result = project(isolated + [a, b, c, d], [pair(a, b), pair(c, d)])
    assert result.metrics.records_seen == 204
    assert result.metrics.provisional_components == 2
    assert result.metrics.internal_pairs_total == 2
    assert result.metrics.internal_pairs_rescored == 0
