"""Executable GF-5B acceptance specification; no resolver algorithm lives here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenResolverCase:
    case_id: str
    records: tuple[str, ...]
    neighborhoods: tuple[tuple[str, ...], ...]
    machine_evidence: tuple[str, ...]
    human_constraints: tuple[str, ...]
    required_targeted_checks: tuple[str, ...]
    required_outcomes: tuple[str, ...]
    allowed_outcomes: tuple[str, ...]
    forbidden_outcomes: tuple[str, ...]


GOLDEN_CASES = (
    GoldenResolverCase("G1", ("A", "B", "C"), (("A", "B", "C"),),
        ("A-B STRONG", "A-C STRONG", "B-C STRONG"), (), (),
        ("COMPLETE_PAIRWISE",), ("LIKELY {A,B,C}",), ("CONFLICT", "DEFERRED")),
    GoldenResolverCase("G2", ("A", "B", "C"), (("A", "B", "C"),),
        ("A-B STRONG", "B-C STRONG", "A-C CANNOT_LINK"), (), (),
        ("conflict visible",), ("safe disjoint subgroup salvage",), ("accepted {A,B,C}",)),
    GoldenResolverCase("G3", ("A", "B", "C"), (("A", "B", "C"),),
        ("A-B STRONG", "B-C STRONG"), (), ("A-C BRIDGE_CROSS_CHECK",),
        ("TargetedEvidenceRequest(A,C,BRIDGE_CROSS_CHECK)",), ("deferred",),
        ("LIKELY {A,B,C} before result",)),
    GoldenResolverCase("G4", ("A", "B", "C"), (("A", "B", "C"),),
        ("A-B STRONG", "B-C REVIEW", "A-C NON_GROUPABLE"), (), (),
        ("bridge risk accounted",), ("{A,B} plus unassigned C", "deferred"),
        ("LIKELY {A,B,C}", "automatic review from connectivity")),
    GoldenResolverCase("G5", ("A", "B", "C"), (("A", "B", "C"),),
        ("A-B REVIEW generic-only", "B-C REVIEW generic-only", "A-C NON_GROUPABLE/absent"),
        (), ("cross-branch evidence when allowed by budget",),
        ("generic-hub risk recorded",), ("split", "additional evidence", "deferred"),
        ("LIKELY {A,B,C}", "automatic REVIEW {A,B,C}")),
    GoldenResolverCase("G6", ("A", "B"), (("A", "B"),),
        ("A-B REVIEW generic-only",), (), (),
        (), ("REVIEW {A,B}",), ("LIKELY from generic-only evidence",)),
    GoldenResolverCase("G7", ("A", "B"), (("A", "B"),),
        ("A-B STRONG",), ("A-B CANNOT_LINK",), (),
        ("human constraint blocks co-membership",), (), ("accepted {A,B}",)),
    GoldenResolverCase("G8", ("A", "B"), (("A", "B"),),
        ("A-B CANNOT_LINK",), ("A-B MUST_LINK",), (),
        ("HUMAN_MACHINE_AUTHORITY_CONFLICT",), (), ("accepted {A,B}",)),
    GoldenResolverCase("G9", ("A", "B", "C"), (("A", "B"), ("B", "C")),
        ("A-B STRONG", "B-C STRONG", "A-C NON_GROUPABLE"), (), (),
        ("choose one safe partition or defer",), ("{A,B}", "{B,C}", "deferred"),
        ("both {A,B} and {B,C}",)),
    GoldenResolverCase("G10", ("A", "B", "C", "D"), (("A", "B"), ("C", "D")),
        ("A-B STRONG", "C-D STRONG", "no cross support"), (), (),
        ("disjoint {A,B} and {C,D}",), ("two accepted groups",), ("merged {A,B,C,D}",)),
    GoldenResolverCase("G11", ("A@S1/EA", "B@S2/BOX"), (("A", "B"),),
        ("A-B STRONG physical identity",), (), (),
        ("use GF-4 edge semantics",), ("accepted when physical evidence is strong",),
        ("conflict from site/UOM difference alone",)),
    GoldenResolverCase("G12", ("A", "B"), (("A", "B"),),
        ("A-B CANNOT_LINK protected technical mismatch",), (), (),
        ("protected cannot-link retained",), (), ("same accepted group",)),
    GoldenResolverCase("G13", ("A", "B", "C"), (("A", "B", "C", "TRUNCATED"),),
        ("incomplete membership evidence",), (), (),
        ("truncation affects safety",), ("explicit safe review", "deferred"),
        ("LIKELY from incomplete discovery",)),
    GoldenResolverCase("G14", ("X",), (), (), (), (),
        ("X unassigned",), (), ("X classified not duplicate",)),
    GoldenResolverCase("G15", ("row-1:SAME", "row-2:SAME"), (("row-1", "row-2"),),
        ("row-1-row-2 SUPPORT",), (), (),
        ("distinct GF-1 record IDs preserved",), ("same accepted group",),
        ("collapse by business values",)),
)


def test_all_fifteen_golden_cases_are_frozen_with_allowed_and_forbidden_outcomes():
    assert tuple(item.case_id for item in GOLDEN_CASES) == tuple(
        f"G{index}" for index in range(1, 16)
    )
    assert all(item.records for item in GOLDEN_CASES)
    assert all(isinstance(item.neighborhoods, tuple) for item in GOLDEN_CASES)
    assert all(isinstance(item.machine_evidence, tuple) for item in GOLDEN_CASES)
    assert all(isinstance(item.human_constraints, tuple) for item in GOLDEN_CASES)
    assert all(isinstance(item.required_targeted_checks, tuple) for item in GOLDEN_CASES)
    assert all(item.required_outcomes or item.allowed_outcomes for item in GOLDEN_CASES)
    assert all(item.forbidden_outcomes for item in GOLDEN_CASES)


def test_golden_cases_freeze_bridge_generic_constraint_and_ownership_safety():
    by_id = {item.case_id: item for item in GOLDEN_CASES}
    assert "LIKELY {A,B,C} before result" in by_id["G3"].forbidden_outcomes
    assert "automatic REVIEW {A,B,C}" in by_id["G5"].forbidden_outcomes
    assert "accepted {A,B}" in by_id["G7"].forbidden_outcomes
    assert "accepted {A,B}" in by_id["G8"].forbidden_outcomes
    assert "both {A,B} and {B,C}" in by_id["G9"].forbidden_outcomes


def test_golden_cases_preserve_safe_salvage_unassigned_and_distinct_source_rows():
    by_id = {item.case_id: item for item in GOLDEN_CASES}
    assert "safe disjoint subgroup salvage" in by_id["G2"].allowed_outcomes
    assert by_id["G14"].required_outcomes == ("X unassigned",)
    assert "collapse by business values" in by_id["G15"].forbidden_outcomes
