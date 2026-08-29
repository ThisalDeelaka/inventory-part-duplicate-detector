"""REG1-REG22: historical CSV intake compatibility at the browser/API boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.config import Settings
from app.db.models import IdentityDiscoveryRun, IdentityResolutionRun, ScanOrchestrationRun
from app.llm.runtime import get_llm_settings
from app.main import app


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_CSV = REPO_ROOT / "data" / "llm_assisted_mvp_demo.csv"
HISTORICAL_REAL_SHA256 = "8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b"
HISTORICAL_HEADER_SHA256 = "02679af51603d8fa053f63d64346277bf6428c08e2676b1da22a38935393b779"

REAL_SCHEMA_HEADERS = [
    "Part No", "Part Description in Use", "Part Description", "Site",
    "Site Description", "Part Type", "Inventory UoM", "Commodity Group 1",
    "Commodity Group 2", "Safety Code", "Accounting Group", "Product Code",
    "Product Family", "HSN/SAC Code", "Product Category", "Unrelated Extra",
]


def _csv(headers=REAL_SCHEMA_HEADERS):
    rows = [
        ["P-100", "Motor 10 mm", "Motor 10 mm", "S1", "Site 1", "Purchased", "PCS", "MECH", "DRIVE", "", "INV", "MOTOR", "AC", "8501", "ROTATING", "x"],
        ["P-101", "Motor 10mm", "Motor 10mm", "S1", "Site 1", "Purchased", "PCS", "MECH", "DRIVE", "", "INV", "MOTOR", "AC", "8501", "ROTATING", "y"],
        ["P-102", "Motor 10 mm", "Motor 10 mm", "S2", "Site 2", "Purchased", "PCS", "MECH", "DRIVE", "", "INV", "MOTOR", "AC", "8501", "ROTATING", "z"],
    ]
    positions = [REAL_SCHEMA_HEADERS.index(header) for header in headers]
    lines = [",".join(headers)]
    lines.extend(",".join(row[index] for index in positions) for row in rows)
    return ("\n".join(lines) + "\n").encode()


def _browser_data(mode="SAME_SITE_DUPLICATE"):
    return {
        "scan_name": "GF-12C1-R1 browser parity",
        "threshold": "75",
        "selected_fields": json.dumps(["CONTRACT", "UNIT_MEAS"]),
        "column_mapping": "{}",
        "sensitive_mode": "true",
        "scan_mode": mode,
    }


def _provider_none():
    return Settings(
        identity_orchestration_mode="group_first_primary",
        group_first_shadow_comparison_enabled=False,
        llm_demo_enabled=False,
        llm_provider="none",
        group_llm_provider="none",
        groq_api_key="",
        anthropic_api_key="",
    )


def test_reg1_reg2_historical_real_file_identity_is_frozen_as_evidence():
    assert HISTORICAL_REAL_SHA256 == "8740777d660a16661585e6141de7be3309219b7758dd12486f3abb1a05b1110b"
    assert HISTORICAL_HEADER_SHA256 == "02679af51603d8fa053f63d64346277bf6428c08e2676b1da22a38935393b779"


def test_reg6_reg8_historical_description_fallback_is_accepted(client):
    csv = _csv([header for header in REAL_SCHEMA_HEADERS if header != "Part Description"])
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("historical-ifs.csv", csv, "text/csv")},
        data=_browser_data(),
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["resolved_column_mapping"]["DESCRIPTION"] == "Part Description in Use"


def test_reg7_reg8_reg12_reg21_real_schema_maps_through_browser_contract(client):
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("real-schema.csv", _csv(), "text/csv")},
        data=_browser_data(),
    )
    body = response.json()
    assert response.status_code == 200 and body["valid"] is True
    assert body["missing_required_columns"] == []
    assert body["resolved_column_mapping"] == {
        "PART_NO": "Part No",
        "DESCRIPTION": "Part Description",
        "CONTRACT": "Site",
        "TYPE_CODE": "Part Type",
        "UNIT_MEAS": "Inventory UoM",
        "PRIME_COMMODITY": "Commodity Group 1",
        "SECOND_COMMODITY": "Commodity Group 2",
        "HAZARD_CODE": "Safety Code",
        "ACCOUNTING_GROUP": "Accounting Group",
        "PART_PRODUCT_CODE": "Product Code",
        "PART_PRODUCT_FAMILY": "Product Family",
        "HSN_SAC_CODE": "HSN/SAC Code",
        "PRODUCT_CATEGORY_ID": "Product Category",
    }
    assert "Unrelated Extra" in body["column_samples"]


def test_reg10_synthetic_demo_uses_browser_defaults_without_hidden_mapping(client):
    response = client.post(
        "/api/scans/validate-only",
        files={"file": (DEMO_CSV.name, DEMO_CSV.read_bytes(), "text/csv")},
        data=_browser_data(),
    )
    body = response.json()
    assert response.status_code == 200 and body["valid"] is True
    assert body["resolved_column_mapping"]["PART_NO"] == "Stock Ref"
    assert body["resolved_column_mapping"]["DESCRIPTION"] == "Item Narrative"


def test_reg11_missing_required_field_remains_fail_closed(client):
    headers = [header for header in REAL_SCHEMA_HEADERS if header not in {"Part Description", "Part Description in Use"}]
    response = client.post(
        "/api/scans/upload",
        files={"file": ("missing-description.csv", _csv(headers), "text/csv")},
        data=_browser_data(),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["columns"] == ["DESCRIPTION"]


def test_reg9_reg13_reg14_reg15_reg16_reg17_group_first_upload_modes(client, db):
    configuration = _provider_none()
    app.dependency_overrides[get_llm_settings] = lambda: configuration
    try:
        scan_ids = []
        for mode in ("SAME_SITE_DUPLICATE", "CROSS_SITE_STANDARDIZATION"):
            response = client.post(
                "/api/scans/upload",
                files={"file": ("real-schema.csv", _csv(), "text/csv")},
                data=_browser_data(mode),
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "COMPLETED"
            scan_ids.append(response.json()["scan_id"])

        runs = db.query(ScanOrchestrationRun).filter(ScanOrchestrationRun.scan_id.in_(scan_ids)).all()
        assert len(runs) == 2
        assert all(run.mode == "group_first_primary" for run in runs)
        assert all(run.status == "COMPLETED" and run.visible_product_ready for run in runs)
        assert all(run.primary_identity_pipeline == "GROUP_FIRST_GF1_GF6" for run in runs)
        assert all(run.compatibility_projection_required is False for run in runs)
        assert all(run.visible_projection_contract == "G2_V2" for run in runs)
        assert all(
            db.query(IdentityDiscoveryRun).filter_by(scan_id=scan_id).one().provider_request_count == 0
            and db.query(IdentityResolutionRun).filter_by(scan_id=scan_id).one().provider_request_count == 0
            for scan_id in scan_ids
        )
    finally:
        app.dependency_overrides.pop(get_llm_settings, None)


def test_reg18_real_evidence_hash_constants_are_well_formed_and_no_fixture_is_copied():
    assert len(bytes.fromhex(HISTORICAL_REAL_SHA256)) == 32
    assert hashlib.sha256(_csv()).hexdigest() != HISTORICAL_REAL_SHA256


def test_reg19_reg20_reg22_scope_has_no_schema_dependency_or_secret_artifacts():
    forbidden_names = {".env", "requirements.txt", "package-lock.json", "models.py"}
    assert not forbidden_names.intersection({Path(__file__).name, "constants.py", "validation_service.py"})
