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


def _validate(client, csv, part_type, **data):
    return client.post(
        "/api/scans/validate-only",
        files={"file": ("parts.csv", csv, "text/csv")},
        data={"part_type": part_type, **data},
    )


PURCHASE_FLAG_CSV = (
    b"Part No,Part Description,Inventory Part\n"
    b"A,Ball Bearing,Yes\n"
    b"B,Ball Bearing Assembly,No\n"
    b"C,Ball Bearing Kit, yes \n"
    b"D,Ball Bearing Set,No\n"
)

SALES_TYPE_CSV = (
    b"Sales Part No,Part No,Description,Type of Sales Part\n"
    b"S1,P1,Gasket,Inventory Part\n"
    b"S2,P2,Gasket Kit,Non Inventory Part\n"
    b"S3,P3,Gasket Set,Package Part\n"
    b"S4,P4,Gasket Ring,inventory part\n"
)


def test_purchase_exclude_inventory_parts_skips_yes_rows(client):
    body = _validate(client, PURCHASE_FLAG_CSV, "PURCHASE", include_inventory_parts="false").json()
    assert body["valid"] is True
    assert body["record_count"] == 2
    assert body["inventory_filter"]["excluded_count"] == 2
    assert body["resolved_column_mapping"]["INVENTORY_PART_FLAG"] == "Inventory Part"


def test_purchase_include_inventory_parts_keeps_every_row(client):
    body = _validate(client, PURCHASE_FLAG_CSV, "PURCHASE", include_inventory_parts="true").json()
    assert body["record_count"] == 4
    assert body["inventory_filter"]["requested"] is False


def test_sales_exclude_inventory_parts_keeps_other_types(client):
    body = _validate(client, SALES_TYPE_CSV, "SALES", include_inventory_parts="false").json()
    assert body["record_count"] == 2
    assert body["inventory_filter"]["excluded_count"] == 2


def test_inventory_part_type_ignores_the_exclusion_flag(client):
    body = _validate(client, PURCHASE_FLAG_CSV, "INVENTORY", include_inventory_parts="false").json()
    assert body["record_count"] == 4
    assert body["inventory_filter"]["requested"] is False


def test_exclusion_without_the_filter_column_is_invalid(client):
    csv = b"Part No,Part Description\nA,Widget\nB,Widget v2\n"
    body = _validate(client, csv, "PURCHASE", include_inventory_parts="false").json()
    assert body["valid"] is False
    assert any(w["warning_type"] == "INVENTORY_FILTER_COLUMN_MISSING" for w in body["warnings"])

    upload = client.post(
        "/api/scans/upload",
        files={"file": ("parts.csv", csv, "text/csv")},
        data={"part_type": "PURCHASE", "include_inventory_parts": "false", "threshold": "50"},
    )
    assert upload.status_code == 422


def test_excluding_every_row_fails_safely(client):
    csv = b"Part No,Part Description,Inventory Part\nA,Widget,Yes\nB,Widget v2,Yes\n"
    response = _validate(client, csv, "PURCHASE", include_inventory_parts="false")
    assert response.status_code == 400
    assert "inventory parts" in response.json()["detail"]


def test_sales_scan_keys_on_sales_part_no_and_maps_part_no_as_condition(client):
    body = _validate(client, SALES_TYPE_CSV, "SALES").json()
    mapping = body["resolved_column_mapping"]
    assert mapping["PART_NO"] == "Sales Part No"
    assert mapping["INVENTORY_PART_NO"] == "Part No"
    assert body["valid"] is True


def test_sales_export_without_sales_part_no_keeps_default_part_no(client):
    csv = b"Part No,Description\nP1,Gasket\nP2,Gasket Kit\n"
    mapping = _validate(client, csv, "SALES").json()["resolved_column_mapping"]
    assert mapping["PART_NO"] == "Part No"
    assert "INVENTORY_PART_NO" not in mapping


def test_sales_part_no_is_not_special_for_other_part_types(client):
    mapping = _validate(client, SALES_TYPE_CSV, "PURCHASE").json()["resolved_column_mapping"]
    assert mapping["PART_NO"] == "Part No"


def test_sales_scan_runs_with_part_no_condition_and_exclusion(client):
    csv = (
        b"Sales Part No,Part No,Description,Type of Sales Part\n"
        b"S1,P1,Hydraulic Pump 10 bar,Non Inventory Part\n"
        b"S2,P1,Hydraulic Pump 10bar,Non Inventory Part\n"
        b"S3,P9,Hydraulic Pump 10 bar,Inventory Part\n"
    )
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("sales.csv", csv, "text/csv")},
        data={
            "part_type": "SALES", "include_inventory_parts": "false", "threshold": "50",
            "selected_fields": '["INVENTORY_PART_NO"]',
        },
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["part_type"] == "SALES"
    assert body["total_records"] == 2


def test_config_fields_expose_new_sales_and_filter_fields(client):
    by_field = {item["field"]: item for item in client.get("/api/config/fields").json()}
    assert by_field["INVENTORY_PART_NO"]["part_types"] == ["SALES"]
    assert by_field["INVENTORY_PART_FLAG"]["selectable"] is False
    assert by_field["SALES_PART_TYPE"]["selectable"] is False


PURCHASE_IFS_CLOUD_CSV = (
    b"Part,Part Description In Use,Purchase Part Description,Site,Default Purch UoM,"
    b"Inventory Part,Order Processing Type\n"
    b"P1,Gasket,Gasket,10,pcs,No,1\n"
    b"P2,Gasket Kit,Gasket Kit,10,pcs,Yes,1\n"
)


def test_ifs_cloud_purchase_export_headers_resolve(client):
    body = _validate(client, PURCHASE_IFS_CLOUD_CSV, "PURCHASE", include_inventory_parts="false").json()
    mapping = body["resolved_column_mapping"]
    assert mapping["PART_NO"] == "Part"
    assert mapping["DEFAULT_UOM"] == "Default Purch UoM"
    assert mapping["ORDER_PROC_TYPE"] == "Order Processing Type"
    assert body["valid"] is True
    assert body["record_count"] == 1


def test_bare_part_header_stays_inventory_part_no_beside_sales_part_no(client):
    csv = b"Sales Part No,Part,Description,Type of Sales Part\nS1,P1,Gasket,Non Inventory Part\n"
    body = _validate(client, csv, "SALES").json()
    mapping = body["resolved_column_mapping"]
    assert mapping["PART_NO"] == "Sales Part No"
    assert mapping["INVENTORY_PART_NO"] == "Part"
    assert body["column_mapping_conflicts"] == {}
    assert body["valid"] is True


SALES_IFS_CLOUD_CSV = (
    b"Sales Part No,Part Description in Use,Sales Part Description,Site,Type Of Sales Part,"
    b"Part No,Inventory UoM,Sales UoM,Price UoM,Replacement Part No,Description\n"
    b"S1,Gasket,Gasket,10,InventoryPart,P1,pcs,pcs,pcs,,\n"
    b"S2,Gasket Kit,Gasket Kit,10,NonInventoryPart,,,pcs,pcs,,\n"
    b"S3,Gasket Pack,Gasket Pack,10,PackagePart,,,pcs,pcs,S1,Old gasket\n"
)


def test_ifs_cloud_sales_description_comes_from_part_description_in_use(client):
    body = _validate(client, SALES_IFS_CLOUD_CSV, "SALES").json()
    mapping = body["resolved_column_mapping"]
    assert mapping["DESCRIPTION"] == "Part Description in Use"
    assert mapping["PART_NO"] == "Sales Part No"
    assert mapping["INVENTORY_PART_NO"] == "Part No"
    assert not any(w["warning_type"] == "EMPTY_DESCRIPTION" for w in body["warnings"])


def test_bare_description_still_maps_without_part_description_in_use(client):
    csv = b"Sales Part No,Description,Type Of Sales Part\nS1,Gasket,NonInventoryPart\n"
    assert _validate(client, csv, "SALES").json()["resolved_column_mapping"]["DESCRIPTION"] == "Description"


def test_ifs_cloud_sales_type_values_without_spaces_are_excluded(client):
    body = _validate(client, SALES_IFS_CLOUD_CSV, "SALES", include_inventory_parts="false").json()
    assert body["valid"] is True
    assert body["record_count"] == 2
    assert body["inventory_filter"]["excluded_count"] == 1
    assert any(w["warning_type"] == "INVENTORY_PARTS_EXCLUDED" for w in body["warnings"])


def test_exclusion_that_matches_nothing_warns_instead_of_passing_silently(client):
    csv = b"Part No,Part Description,Inventory Part\nA,Bearing,Maybe\nB,Bolt,Unknown\n"
    body = _validate(client, csv, "PURCHASE", include_inventory_parts="false").json()
    assert body["record_count"] == 2
    warning = next(w for w in body["warnings"] if w["warning_type"] == "INVENTORY_FILTER_NO_MATCH")
    assert "Maybe" in warning["message"] and "Unknown" in warning["message"]
