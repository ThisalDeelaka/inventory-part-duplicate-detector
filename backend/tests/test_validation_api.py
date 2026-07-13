import io
import json

from app.db.models import DuplicateCandidate
from app.services.export_service import sanitize_csv_cell


CSV = b"PART_NO,DESCRIPTION,CONTRACT,UNIT_MEAS\nA,MCB30A,S1,PCS\nB,MCB 30 A,S1,PCS\n"


def test_validation_service_reports_missing_required(client):
    response = client.post("/api/scans/validate-only", files={"file": ("bad.csv", b"PART_NO\nA\n", "text/csv")}, data={"selected_fields":"[]"})
    assert response.status_code == 200
    assert "DESCRIPTION" in response.json()["missing_required_columns"]


def test_health_and_scan_upload(client):
    assert client.get("/health").json()["status"] == "healthy"
    response = client.post("/api/scans/upload", files={"file": ("parts.csv", CSV, "text/csv")}, data={"selected_fields":'["CONTRACT","UNIT_MEAS"]',"threshold":"60","scan_name":"Test"})
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"


def test_feedback_endpoint(client, db):
    upload = client.post("/api/scans/upload", files={"file": ("parts.csv", CSV, "text/csv")}, data={"selected_fields":'["CONTRACT","UNIT_MEAS"]',"threshold":"50","scan_name":"Feedback"})
    candidate = db.query(DuplicateCandidate).first()
    assert candidate is not None
    response = client.post(f"/api/candidates/{candidate.id}/feedback", json={"user_decision":"DUPLICATE","user_comment":"Reviewed","created_by":"tester"})
    assert response.status_code == 200
    assert response.json()["user_decision"] == "DUPLICATE"


def test_load_test_endpoint(client):
    response = client.post("/api/load-test/run", json={"record_count": 30, "duplicate_rate": 0.2, "variation_rate": 0.3, "threshold": 70})
    assert response.status_code == 200
    body = response.json()
    assert body["record_count"] == 30
    assert body["candidate_pair_count"] >= body["candidates_found"]
    assert body["processing_time_seconds"] >= 0


def test_bad_csv_and_empty_file_fail_safely(client):
    empty = client.post("/api/scans/validate-only", files={"file": ("empty.csv", b"", "text/csv")}, data={"selected_fields": "[]"})
    bad = client.post("/api/scans/validate-only", files={"file": ("bad.csv", b"\x00\x00\x00", "text/csv")}, data={"selected_fields": "[]"})
    assert empty.status_code == 400
    assert bad.status_code in {400, 422}


def test_export_sanitizes_spreadsheet_formula_values():
    assert sanitize_csv_cell("=cmd|' /C calc'!A0").startswith("'=")
    assert sanitize_csv_cell("+SUM(A1:A2)").startswith("'+")
    assert sanitize_csv_cell("normal part") == "normal part"


def test_sensitive_data_mode_returns_transparency_and_pattern_warnings(client):
    csv = b"PART_NO,DESCRIPTION,CONTRACT\nA,Motor for PROJECT-ABC123 contact test@example.com,S1\nB,Motor for project abc123,S1\n"
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("sensitive.csv", csv, "text/csv")},
        data={"selected_fields": "CONTRACT", "sensitive_mode": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["privacy"]["raw_csv_stored"] is False
    assert body["privacy"]["external_ai_used"] is False
    assert len(body["privacy"]["file_sha256"]) == 64
    warning_types = {warning["warning_type"] for warning in body["warnings"]}
    assert "POSSIBLE_EMAIL" in warning_types
    assert "POSSIBLE_PROJECT_REFERENCE" in warning_types


def test_human_readable_ifs_headers_are_mapped_automatically(client):
    csv = (
        b"Part No,Part Description,Site,Part Type,Inventory UoM,Commodity Group 1,"
        b"Product Code,Product Family,Product Category,HSN/SAC Code\n"
        b"A-1,Motor 10MM,S1,Purchased,PCS,MECH,P01,F01,C01,1000\n"
        b"A-2,Motor 10 mm,S1,Purchased,PCS,MECH,P01,F01,C01,1000\n"
    )
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("ifs-export.csv", csv, "text/csv")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]'},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["missing_optional_selected_columns"] == []
    assert body["resolved_column_mapping"]["PART_NO"] == "Part No"
    assert body["resolved_column_mapping"]["DESCRIPTION"] == "Part Description"
    assert body["resolved_column_mapping"]["CONTRACT"] == "Site"
    assert body["resolved_column_mapping"]["HSN_SAC_CODE"] == "HSN/SAC Code"


def test_arbitrary_headers_can_be_mapped_explicitly(client):
    csv = b"Stock Identifier,Long Text,Facility,Stock Unit\nA,Motor,S1,PCS\nB,Motor assembly,S1,PCS\n"
    mapping = {
        "PART_NO": "Stock Identifier",
        "DESCRIPTION": "Long Text",
        "CONTRACT": "Facility",
        "UNIT_MEAS": "Stock Unit",
    }
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("custom.csv", csv, "text/csv")},
        data={
            "selected_fields": '["CONTRACT","UNIT_MEAS"]',
            "column_mapping": json.dumps(mapping),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["resolved_column_mapping"] == mapping


def test_explicit_mapping_can_override_an_automatic_description_column(client):
    csv = b"Part No,Part Description,Master Part Description\nA,Short text,Preferred detailed text\n"
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("override.csv", csv, "text/csv")},
        data={"column_mapping": json.dumps({"DESCRIPTION": "Master Part Description"})},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["resolved_column_mapping"]["DESCRIPTION"] == "Master Part Description"


def test_ambiguous_automatic_aliases_require_an_explicit_choice(client):
    csv = b"Part No,Part Number,Part Description\nA,A-ALT,Motor\n"
    initial = client.post(
        "/api/scans/validate-only",
        files={"file": ("ambiguous.csv", csv, "text/csv")},
    )
    assert initial.status_code == 200
    assert initial.json()["valid"] is False
    assert initial.json()["column_mapping_conflicts"]["PART_NO"] == ["Part No", "Part Number"]
    assert any(w["warning_type"] == "AMBIGUOUS_COLUMN_MAPPING" for w in initial.json()["warnings"])

    resolved = client.post(
        "/api/scans/validate-only",
        files={"file": ("ambiguous.csv", csv, "text/csv")},
        data={"column_mapping": json.dumps({"PART_NO": "Part No"})},
    )
    assert resolved.status_code == 200
    assert resolved.json()["valid"] is True


def test_below_threshold_business_rule_exclusions_are_auditable(client):
    csv = (
        b"PART_NO,DESCRIPTION,CONTRACT,UNIT_MEAS\n"
        b"SN-P1,Serial Part 1,S1,PCS\n"
        b"SN-P2,Serial Part 2,S1,PCS\n"
        b"UNRELATED,Coffee Mug,S1,PCS\n"
    )
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("rule-exclusion.csv", csv, "text/csv")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]', "threshold": "75"},
    )

    assert upload.status_code == 200
    body = upload.json()
    assert body["total_candidates"] == 0
    assert body["rejections_count"] == 1

    exclusions = client.get(f"/api/scans/{body['scan_id']}/rejections")
    assert exclusions.status_code == 200
    assert len(exclusions.json()) == 1
    item = exclusions.json()[0]
    assert item["rejection_reason"] == "TRAILING_VARIANT_SUFFIX_MISMATCH"
    assert item["critical_mismatches"][0]["group"] == "TRAILING_VARIANT_SUFFIX"
    assert "trailing variant suffix differs" in item["explanation"]

    export = client.get(f"/api/scans/{body['scan_id']}/rejections/export")
    assert export.status_code == 200
    assert "TRAILING_VARIANT_SUFFIX_MISMATCH" in export.text
    assert "trailing variant suffix differs" in export.text


def test_structural_role_candidate_keeps_mismatch_evidence(client):
    csv = (
        b"PART_NO,DESCRIPTION,CONTRACT,UNIT_MEAS\n"
        b"SJ COMP PART1,SJ COMP PART1,S1,PCS\n"
        b"SJ TOP PART1,SJ TOP PART1,S1,PCS\n"
    )
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("structural-role.csv", csv, "text/csv")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]', "threshold": "75"},
    )

    assert upload.status_code == 200
    body = upload.json()
    assert body["total_candidates"] == 1
    assert body["rejections_count"] == 0

    candidates = client.get(f"/api/scans/{body['scan_id']}/candidates").json()
    assert candidates[0]["business_status"] == "POSSIBLE_DUPLICATE_REVIEW"
    assert candidates[0]["rule_decision"] == "DOWNGRADE"
    assert candidates[0]["rejection_reason"] == "STRUCTURAL_ROLE_MISMATCH"
    assert candidates[0]["critical_mismatches"][0]["group"] == "STRUCTURAL_ROLE"
    assert "Different structural role detected" in candidates[0]["explanation"]
