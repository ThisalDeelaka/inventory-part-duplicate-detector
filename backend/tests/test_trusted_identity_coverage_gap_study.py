import pytest

from app.benchmarks.trusted_identity_coverage_gap_study import (
    R17_COUNTERFACTUAL_VERSION,
    STRATEGIES,
    evaluate_strategy,
)
from app.engine.identity_signature_derivation import derive_identity_signature
from app.engine.signed_identity_evidence import derive_signed_identity_evidence
from app.engine.identity_signature import SignedEvidenceChannel


def record(ref, part_no, description, **values):
    return {
        "record_ref_key": ref,
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "MASTER_DESCRIPTION": values.pop("master", description),
        "TYPE_DESIGNATION": values.pop("type_designation", ""),
        "DIMENSION_QUALITY": values.pop("dimension_quality", ""),
        "CONTRACT": values.pop("contract", "10"),
        "UNIT_MEAS": values.pop("uom", "PCS"),
        "TYPE_CODE": values.pop("part_type", "Purchased"),
        **values,
    }


# Exact allowlisted values from the protected CSV and R12 control rationale.
REAL_POSITIVE_CONTROLS = (
    ("Contact Cleaner", record("csv-row-5194", "CB-CC", "Contact Cleaner (can)"), record("csv-row-5195", "AP-CONTACT-CLEANER", "Contact Cleaner (Can)")),
    ("Turbine Lubricating Oil", record("csv-row-5246", "AP-LUBE-OIL-ISO068", "TURBINE LUBRICATING OIL", uom="l"), record("csv-row-5263", "SP-LUBE-OIL-ISO068", "TURBINE LUBRICATING OIL", uom="l")),
    ("Francis Turbine Lower Bearing", record("csv-row-5262", "AP-BRG-FR-22", "FRANCIS TURBINE LOWER BEARING"), record("csv-row-5283", "CB-BRG-FR-22", "Francis Turbine Lower Bearing")),
    ("Pump X500", record("csv-row-5294", "X500", "Pump Model X500", contract="10"), record("csv-row-5295", "X500", "Pump Model X500", contract="AG-10")),
    ("Fan Blade", record("csv-row-2306", "KM-FB", "Fan Blade", contract="K-MRO", part_type="Manufactured"), record("csv-row-2385", "KM/FANBLADE", "Fan Blade", contract="K-MRO", part_type="Manufactured")),
    ("F30", record("csv-row-2526", "AS-COM-ROT", "F30 Engine Compressor Rotor", contract="MRO", part_type="Manufactured"), record("csv-row-3045", "KA/ASCOMROT1", "F30 Engine Compressor Rotor", contract="MRO", part_type="Manufactured")),
    ("B38", record("csv-row-5126", "AS-B38-H", "B38 Engine Head", contract="MRO", part_type="Manufactured"), record("csv-row-5131", "ES/AS-B38-H", "B38 Engine Head", contract="MRO", part_type="Manufactured")),
)

R12_FALSE_PAIRS = (
    (record("csv-row-1434", "XX-BRUSH", "Exercise 3"), record("csv-row-1433", "XX-PAINT", "exercise 3")),
    (record("csv-row-4991", "NE01-MODEL-S", "Model S"), record("csv-row-4925", "NE01-MODEL-X", "Model S")),
    (record("csv-row-5135", "NS-WOOD", "NSUDLK TEST"), record("csv-row-5012", "NS-STEELFRAME", "NSUDLK TEST", part_type="Manufactured")),
    (record("csv-row-3983", "AUTO01 COILSPRING", "Coil Spring"), record("csv-row-3941", "AUTO01 STAPLERS", "Coil Spring")),
)


def _outcome(strategy, pair):
    return evaluate_strategy(strategy, pair[0], pair[1])


def test_r17_f_combined_general_rule_covers_all_exact_real_controls():
    assert [name for name, left, right in REAL_POSITIVE_CONTROLS if _outcome("F", (left, right)).promoted] == [item[0] for item in REAL_POSITIVE_CONTROLS]


@pytest.mark.parametrize("left,right", R12_FALSE_PAIRS)
def test_r17_f_combined_rule_does_not_promote_r12_false_pairs(left, right):
    assert not _outcome("F", (left, right)).promoted


def test_r17_strategy_matrix_exposes_isolated_strategy_risk_and_coverage():
    gains = {
        strategy: sum(_outcome(strategy, (left, right)).promoted for _name, left, right in REAL_POSITIVE_CONTROLS)
        for strategy in STRATEGIES
    }
    assert gains == {"A": 7, "B": 7, "C": 3, "D": 6, "E": 4, "F": 7}
    for strategy in ("A", "B", "D"):
        assert any(_outcome(strategy, pair).promoted for pair in R12_FALSE_PAIRS)
    for strategy in ("C", "E", "F"):
        assert not any(_outcome(strategy, pair).promoted for pair in R12_FALSE_PAIRS)


def test_r17_existing_shadow_comparator_remains_unchanged_and_lexical_for_controls():
    for _name, left, right in REAL_POSITIVE_CONTROLS:
        evidence = derive_signed_identity_evidence(
            derive_identity_signature(left), derive_identity_signature(right)
        )
        assert SignedEvidenceChannel.IDENTITY_SUPPORT not in {fact.channel for fact in evidence.facts}


def test_r17_strategy_is_deterministic_site_independent_and_non_authoritative():
    name, left, right = REAL_POSITIVE_CONTROLS[3]
    assert name == "Pump X500"
    first = evaluate_strategy("F", left, right)
    second = evaluate_strategy("F", right, left)
    changed_site = evaluate_strategy("F", {**left, "CONTRACT": "OTHER"}, right)
    assert first == second == changed_site
    assert not hasattr(first, "edge_class")
    assert R17_COUNTERFACTUAL_VERSION == "trusted-identity-gap-study-v1"
