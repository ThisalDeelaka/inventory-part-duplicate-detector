import io
import json

import pandas as pd

from app.engine.business_rules import evaluate_hard_business_rules


def test_config_fields_expose_part_type_tags(client):
    response = client.get("/api/config/fields")
    assert response.status_code == 200
    by_field = {item["field"]: item for item in response.json()}

    assert by_field["PART_NO"]["part_types"] == ["INVENTORY", "PURCHASE", "SALES"]
    assert by_field["UNIT_MEAS"]["part_types"] == ["INVENTORY"]
    assert by_field["DEFAULT_UOM"]["part_types"] == ["PURCHASE"]
    assert by_field["BUYER_ID"]["part_types"] == ["PURCHASE"]
    assert by_field["TECH_COORDINATOR"]["part_types"] == ["PURCHASE"]
    assert by_field["PURCHASE_GROUP"]["part_types"] == ["PURCHASE"]
    assert by_field["ORDER_PROC_TYPE"]["part_types"] == ["PURCHASE"]
    assert by_field["SALES_PART_DESCRIPTION"]["part_types"] == ["SALES"]
    assert by_field["SALES_UOM"]["part_types"] == ["SALES"]
    assert by_field["PRICE_UOM"]["part_types"] == ["SALES"]
    assert by_field["SALES_PRICE_GROUP"]["part_types"] == ["SALES"]
    assert by_field["SALES_GROUP"]["part_types"] == ["SALES"]
    assert by_field["HSN_SAC_CODE"]["part_types"] == ["INVENTORY"]
    assert by_field["CONTRACT"]["part_types"] == ["INVENTORY", "PURCHASE"]


def test_built_in_uom_style_fields_hard_reject_unconditionally():
    for field_key, label in (("DEFAULT_UOM", "Default UOM"), ("SALES_UOM", "Sales UOM"), ("PRICE_UOM", "Price UOM")):
        record_a = {"PART_NO": "A", field_key: "EA"}
        record_b = {"PART_NO": "B", field_key: "KG"}
        result = evaluate_hard_business_rules(record_a, record_b, "SAME_SITE_DUPLICATE")
        assert result["blocked"] is True
        assert result["business_status"] == "REJECTED_BY_BUSINESS_RULE"
        assert result["rule_decision"] == "REJECT"
        assert result["rejection_reason"] == f"{field_key}_MISMATCH"
        assert f"{label} differs" in result["explanation"]


def test_built_in_uom_style_fields_allow_when_matching_or_missing():
    matching = evaluate_hard_business_rules(
        {"PART_NO": "A", "SALES_UOM": "EA"}, {"PART_NO": "B", "SALES_UOM": "ea"}, "SAME_SITE_DUPLICATE",
    )
    missing = evaluate_hard_business_rules(
        {"PART_NO": "A", "PRICE_UOM": "EA"}, {"PART_NO": "B"}, "SAME_SITE_DUPLICATE",
    )
    assert matching["blocked"] is False
    assert missing["blocked"] is False


def test_scan_persists_and_defaults_part_type(client):
    csv = b"PART_NO,DESCRIPTION,CONTRACT,UNIT_MEAS\nA,MCB30A,S1,PCS\nB,MCB 30 A,S1,PCS\n"

    default_upload = client.post(
        "/api/scans/upload",
        files={"file": ("parts.csv", csv, "text/csv")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]', "threshold": "60"},
    )
    assert default_upload.status_code == 200
    assert default_upload.json()["part_type"] == "INVENTORY"

    purchase_csv = (
        b"PART_NO,DESCRIPTION,Site,Default UOM,Buyer Id,Tech Coordinator,Purchase Group,Order Proc Type\n"
        b"A,Ball Bearing,S1,EA,B01,TC01,PG01,PUR\n"
        b"B,Ball Bearing Assembly,S1,EA,B01,TC01,PG01,PUR\n"
    )
    purchase_upload = client.post(
        "/api/scans/upload",
        files={"file": ("purchase.csv", purchase_csv, "text/csv")},
        data={"threshold": "50", "part_type": "PURCHASE"},
    )
    assert purchase_upload.status_code == 200
    body = purchase_upload.json()
    assert body["part_type"] == "PURCHASE"

    fetched = client.get(f"/api/scans/{body['scan_id']}")
    assert fetched.json()["part_type"] == "PURCHASE"


def test_invalid_part_type_falls_back_to_inventory(client):
    csv = b"PART_NO,DESCRIPTION\nA,Widget\nB,Widget v2\n"
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("parts.csv", csv, "text/csv")},
        data={"threshold": "50", "part_type": "NOT_A_REAL_TYPE"},
    )
    assert upload.status_code == 200
    assert upload.json()["part_type"] == "INVENTORY"


def test_purchase_uom_mismatch_hard_rejects_end_to_end(client):
    csv = (
        b"PART_NO,DESCRIPTION,Default UOM\n"
        b"A,Hydraulic Pump,EA\n"
        b"B,Hydraulic Pump Assembly,KG\n"
    )
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("purchase-uom.csv", csv, "text/csv")},
        data={"threshold": "50", "part_type": "PURCHASE"},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["total_candidates"] == 0
    assert body["rejections_count"] == 1

    rejections = client.get(f"/api/scans/{body['scan_id']}/rejections").json()
    assert rejections[0]["rejection_reason"] == "DEFAULT_UOM_MISMATCH"


def _xlsx_bytes(rows, columns):
    frame = pd.DataFrame(rows, columns=columns)
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def test_xlsx_upload_is_parsed_like_csv(client):
    content = _xlsx_bytes(
        [["A", "MCB30A", "S1", "PCS"], ["B", "MCB 30 A", "S1", "PCS"]],
        ["PART_NO", "DESCRIPTION", "CONTRACT", "UNIT_MEAS"],
    )
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("parts.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["record_count"] == 2
    assert body["resolved_column_mapping"]["PART_NO"] == "PART_NO"


def test_xlsx_upload_runs_a_full_scan(client):
    content = _xlsx_bytes(
        [["A", "MCB30A", "S1", "PCS"], ["B", "MCB 30 A", "S1", "PCS"]],
        ["PART_NO", "DESCRIPTION", "CONTRACT", "UNIT_MEAS"],
    )
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("parts.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]', "threshold": "60"},
    )
    assert upload.status_code == 200
    assert upload.json()["status"] == "COMPLETED"
    assert upload.json()["total_records"] == 2


def test_xlsx_uses_human_readable_headers_with_automatic_mapping(client):
    content = _xlsx_bytes(
        [["A-1", "Motor 10MM", "S1"], ["A-2", "Motor 10 mm", "S1"]],
        ["Part No", "Part Description", "Site"],
    )
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("ifs-export.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["resolved_column_mapping"]["PART_NO"] == "Part No"
    assert body["resolved_column_mapping"]["CONTRACT"] == "Site"


def test_empty_and_oversized_upload_error_messages_are_generic(client):
    empty = client.post(
        "/api/scans/validate-only",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert empty.status_code == 400
    assert "empty" in empty.json()["detail"].lower()


def test_bad_xlsx_content_fails_safely(client):
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("bad.xlsx", b"not a real xlsx file", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 400
    assert "XLSX" in response.json()["detail"]
