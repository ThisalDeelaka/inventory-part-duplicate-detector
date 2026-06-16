import io

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
