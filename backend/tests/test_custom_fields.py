import json

import pandas as pd

from app.engine.business_rules import evaluate_hard_business_rules
from app.engine.scoring import score_candidate
from app.services.validation_service import apply_column_mapping, parse_column_mapping


def test_create_custom_field_derives_key_and_rejects_duplicates(client):
    create = client.post("/api/config/custom-fields", json={"display_label": "Manufacturer Code", "mode": "SUPPORTING"})
    assert create.status_code == 200
    body = create.json()
    assert body["field_key"] == "MANUFACTURER_CODE"
    assert body["mode"] == "SUPPORTING"
    assert body["aliases"] == []

    duplicate = client.post("/api/config/custom-fields", json={"display_label": "manufacturer code", "mode": "STRICT"})
    assert duplicate.status_code == 409

    listed = client.get("/api/config/custom-fields")
    assert listed.status_code == 200
    assert [f["field_key"] for f in listed.json()] == ["MANUFACTURER_CODE"]

    deleted = client.delete(f"/api/config/custom-fields/{body['id']}")
    assert deleted.status_code == 200
    assert client.get("/api/config/custom-fields").json() == []


def test_custom_field_cannot_shadow_a_builtin_field(client):
    response = client.post("/api/config/custom-fields", json={"display_label": "Part No", "mode": "SUPPORTING"})
    assert response.status_code == 409


def test_custom_field_delete_missing_returns_404(client):
    assert client.delete("/api/config/custom-fields/999").status_code == 404


def test_explicit_mapping_resolves_custom_field_and_learns_alias(client):
    create = client.post("/api/config/custom-fields", json={"display_label": "Manufacturer Code", "mode": "SUPPORTING"})
    assert create.status_code == 200

    csv = b"Part No,Part Description,Mfr Code\nA,Motor,ACME\nB,Motor unit,ACME\n"
    response = client.post(
        "/api/scans/validate-only",
        files={"file": ("custom.csv", csv, "text/csv")},
        data={"column_mapping": json.dumps({"MANUFACTURER_CODE": "Mfr Code"})},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["resolved_column_mapping"]["MANUFACTURER_CODE"] == "Mfr Code"
    assert body["custom_fields_used"] == [
        {"field_key": "MANUFACTURER_CODE", "display_label": "Manufacturer Code", "mode": "SUPPORTING"}
    ]

    saved = client.get("/api/config/custom-fields").json()[0]
    assert saved["aliases"] == ["MFR_CODE"]

    # The learned alias now auto-resolves the same header spelling without an explicit mapping.
    second = client.post(
        "/api/scans/validate-only",
        files={"file": ("custom2.csv", csv, "text/csv")},
    )
    assert second.status_code == 200
    assert second.json()["resolved_column_mapping"]["MANUFACTURER_CODE"] == "Mfr Code"


def test_parse_column_mapping_rejects_unknown_target_field():
    try:
        parse_column_mapping(json.dumps({"NOT_A_FIELD": "Some Column"}), custom_field_keys={"MANUFACTURER_CODE"})
        raised = False
    except Exception:
        raised = True
    assert raised


def test_apply_column_mapping_uses_custom_field_aliases_before_falling_back():
    df = pd.DataFrame({"PART_NO": ["A"], "DESCRIPTION": ["Motor"], "Mfr Code": ["ACME"]})
    mapped, metadata = apply_column_mapping(
        df,
        custom_field_aliases={"MFR_CODE": "MANUFACTURER_CODE"},
        custom_field_keys={"MANUFACTURER_CODE"},
    )
    assert metadata["resolved_column_mapping"]["MANUFACTURER_CODE"] == "Mfr Code"
    assert "MANUFACTURER_CODE" in mapped.columns


def test_strict_custom_field_hard_rejects_on_mismatch():
    strict_fields = [{"field_key": "MANUFACTURER_CODE", "display_label": "Manufacturer Code"}]
    record_a = {"PART_NO": "A", "MANUFACTURER_CODE": "ACME"}
    record_b = {"PART_NO": "B", "MANUFACTURER_CODE": "OTHER"}

    result = evaluate_hard_business_rules(record_a, record_b, "SAME_SITE_DUPLICATE", strict_fields)

    assert result["blocked"] is True
    assert result["business_status"] == "REJECTED_BY_BUSINESS_RULE"
    assert result["rule_decision"] == "REJECT"
    assert result["rejection_reason"] == "MANUFACTURER_CODE_MISMATCH"
    assert result["score_cap"] == 45.0
    assert "Manufacturer Code differs" in result["explanation"]


def test_strict_custom_field_allows_when_matching_or_missing():
    strict_fields = [{"field_key": "MANUFACTURER_CODE", "display_label": "Manufacturer Code"}]

    matching = evaluate_hard_business_rules(
        {"PART_NO": "A", "MANUFACTURER_CODE": "ACME"},
        {"PART_NO": "B", "MANUFACTURER_CODE": "acme"},
        "SAME_SITE_DUPLICATE", strict_fields,
    )
    missing = evaluate_hard_business_rules(
        {"PART_NO": "A", "MANUFACTURER_CODE": "ACME"},
        {"PART_NO": "B"},
        "SAME_SITE_DUPLICATE", strict_fields,
    )

    assert matching["blocked"] is False
    assert missing["blocked"] is False


def test_existing_hardcoded_strict_rules_unaffected_by_default():
    result = evaluate_hard_business_rules(
        {"PART_NO": "A", "UNIT_MEAS": "PCS"},
        {"PART_NO": "B", "UNIT_MEAS": "KG"},
        "SAME_SITE_DUPLICATE",
    )
    assert result["rejection_reason"] == "UNIT_MEAS_MISMATCH"


def test_score_candidate_passes_through_strict_custom_fields():
    strict_fields = [{"field_key": "MANUFACTURER_CODE", "display_label": "Manufacturer Code"}]
    record_a = {"PART_NO": "A", "DESCRIPTION": "Motor", "MANUFACTURER_CODE": "ACME"}
    record_b = {"PART_NO": "B", "DESCRIPTION": "Motor unit", "MANUFACTURER_CODE": "OTHER"}

    result = score_candidate(record_a, record_b, [], "SAME_SITE_DUPLICATE", strict_fields)

    assert result["rejection_reason"] == "MANUFACTURER_CODE_MISMATCH"
    assert result["rule_decision"] == "REJECT"


def test_end_to_end_supporting_custom_field_participates_in_matching(client):
    created = client.post("/api/config/custom-fields", json={"display_label": "Manufacturer Code", "mode": "SUPPORTING"})
    assert created.status_code == 200

    csv = (
        b"PART_NO,DESCRIPTION,Manufacturer Code\n"
        b"A,Hydraulic Pump,ACME\n"
        b"B,Hydraulic Pump Assembly,ACME\n"
    )
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("supporting.csv", csv, "text/csv")},
        data={"threshold": "50"},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["custom_fields_used"] == [
        {"field_key": "MANUFACTURER_CODE", "display_label": "Manufacturer Code", "mode": "SUPPORTING"}
    ]
    assert body["total_candidates"] >= 1

    candidates = client.get(f"/api/scans/{body['scan_id']}/candidates").json()
    assert "MANUFACTURER_CODE" in candidates[0]["matched_fields"]


def test_end_to_end_strict_custom_field_hard_rejects(client):
    created = client.post("/api/config/custom-fields", json={"display_label": "Manufacturer Code", "mode": "STRICT"})
    assert created.status_code == 200

    csv = (
        b"PART_NO,DESCRIPTION,Manufacturer Code\n"
        b"A,Hydraulic Pump,ACME\n"
        b"B,Hydraulic Pump Assembly,OTHER\n"
    )
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("strict.csv", csv, "text/csv")},
        data={"threshold": "50"},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["total_candidates"] == 0
    assert body["rejections_count"] == 1

    rejections = client.get(f"/api/scans/{body['scan_id']}/rejections").json()
    assert rejections[0]["rejection_reason"] == "MANUFACTURER_CODE_MISMATCH"
