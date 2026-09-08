from pathlib import Path

import pandas as pd

from app.db.models import DuplicateCandidate
from app.llm.services import candidate_eligibility
from app.services.scan_runner import ScanRunner
from app.services.validation_service import apply_column_mapping, validate_dataframe


def test_demo_csv_completes_deterministically_without_llm_provider_calls(db, monkeypatch):
    provider_calls = 0

    def fail_if_provider_is_created(*_args, **_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("The deterministic demo smoke path must not create an LLM provider")

    monkeypatch.setattr("app.llm.runtime.create_llm_provider", fail_if_provider_is_created)
    path = Path(__file__).resolve().parents[2] / "data" / "llm_assisted_mvp_demo.csv"
    source = pd.read_csv(path, dtype=str)
    mapped, metadata = apply_column_mapping(
        source,
        {"PART_NO": "Stock Ref", "DESCRIPTION": "Item Narrative"},
    )

    assert len(source) == 16
    assert metadata["resolved_column_mapping"]["PART_NO"] == "Stock Ref"
    assert metadata["resolved_column_mapping"]["DESCRIPTION"] == "Item Narrative"
    validation = validate_dataframe(mapped, ["CONTRACT", "UNIT_MEAS"])
    assert validation["valid"] is True
    assert validation["missing_required_columns"] == []

    scan, pair_count = ScanRunner(db).run(
        mapped,
        scan_name="Synthetic LLM-assisted MVP demo",
        selected_fields=["CONTRACT", "UNIT_MEAS"],
        threshold=40,
        sensitive_mode=True,
        scan_mode="SAME_SITE_DUPLICATE",
    )
    candidates = (
        db.query(DuplicateCandidate)
        .filter(DuplicateCandidate.scan_id == scan.id)
        .all()
    )
    eligibility = [candidate_eligibility(candidate) for candidate in candidates]

    assert scan.status == "COMPLETED"
    assert pair_count == 8
    assert scan.total_candidates == len(candidates)
    assert candidates
    assert any(item.eligible for item in eligibility)
    assert any(not item.eligible for item in eligibility)
    assert any(candidate.rejection_reason == "HSN_SAC_CODE_MISMATCH" for candidate in candidates)
    assert provider_calls == 0
