import csv
import io
import json
from types import SimpleNamespace

from app.core.config import settings
from app.services.export_service import candidates_to_csv, serialize_csv_value
from app.services.scan_service import get_scan_candidates


CSV = b"""PART_NO,DESCRIPTION,CONTRACT,UNIT_MEAS
DEC CO1,Decicated Coconut type 1,SMBE,PCS
DEC C01,Dec Coco 1,SMBE,PCS
"""


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def candidate(**overrides):
    base = {
        "part_no_a": "DEC CO1",
        "description_a": "Decicated Coconut type 1",
        "contract_a": "SMBE",
        "part_no_b": "DEC C01",
        "description_b": "Dec Coco 1",
        "contract_b": "SMBE",
        "similarity_score": 96.5,
        "confidence_score": 96.5,
        "confidence_level": "HIGH",
        "business_status": "DUPLICATE_CANDIDATE",
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "scan_mode": "SAME_SITE_DUPLICATE",
        "critical_mismatches": "[]",
        "generic_description_warning": "false",
        "application_context_a": "[]",
        "application_context_b": "[]",
        "application_context_warning": "false",
        "normalized_description_a": "desiccated coconut type 1",
        "normalized_description_b": "desiccated coconut type 1",
        "normalized_part_no_a": "desiccated type 1",
        "normalized_part_no_b": "desiccated type 1",
        "extracted_attributes_a": json.dumps({"product_class": ["coconut"]}),
        "extracted_attributes_b": json.dumps({"product_class": ["coconut"]}),
        "variant_attributes_a": "{}",
        "variant_attributes_b": "{}",
        "description_similarity": 98,
        "tfidf_score": 97,
        "fuzzy_score": 99,
        "part_no_similarity": 95,
        "technical_token_score": 90,
        "matched_fields": '["CONTRACT"]',
        "mismatched_fields": "[]",
        "matched_evidence": json.dumps(["product_class", "type_code"]),
        "differences": json.dumps([{"feature": "rating", "values_a": ["20a"], "values_b": ["30a"]}]),
        "warnings": json.dumps(["example warning"]),
        "explanation": "Descriptions and part numbers match.",
        "recommended_action": "Review as likely duplicate candidate",
        "review_status": "UNREVIEWED",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_export_includes_old_and_new_columns():
    exported = candidates_to_csv([candidate()])
    header = exported.splitlines()[0].split(",")

    for field in ("similarity_score", "recommended_action", "review_status"):
        assert field in header
    for field in (
        "business_status",
        "confidence_score",
        "matched_evidence",
        "differences",
        "warnings",
        "extracted_attributes_a",
        "extracted_attributes_b",
    ):
        assert field in header


def test_lists_and_dicts_are_serialized_safely():
    assert serialize_csv_value(["a", "b"]) == "a; b"
    assert serialize_csv_value({"a": ["b"]}) == '{"a":["b"]}'

    exported = candidates_to_csv([candidate()])
    row = rows(exported)[0]

    assert row["matched_evidence"] == "product_class; type_code"
    assert '"feature":"rating"' in row["differences"]
    assert row["warnings"] == "example warning"
    assert row["extracted_attributes_a"] == '{"product_class":["coconut"]}'


def test_blank_missing_optional_fields_do_not_crash_export():
    exported = candidates_to_csv([SimpleNamespace(part_no_a="A")])
    row = rows(exported)[0]

    assert row["part_no_a"] == "A"
    assert row["confidence_score"] == ""
    assert row["matched_evidence"] == ""
    assert row["extracted_attributes_a"] == ""


def test_redesigned_scan_result_exports_successfully(client, db, monkeypatch):
    monkeypatch.setattr(settings, "use_redesigned_engine", True)
    upload = client.post(
        "/api/scans/upload",
        files={"file": ("parts.csv", CSV, "text/csv")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]', "threshold": "0", "scan_name": "Export redesigned"},
    )
    assert upload.status_code == 200
    scan_id = upload.json()["id"]

    exported = candidates_to_csv(get_scan_candidates(db, scan_id))
    row = rows(exported)[0]

    assert row["business_status"] == "DUPLICATE_CANDIDATE"
    assert row["confidence_score"]
    assert row["matched_evidence"]
    assert row["extracted_attributes_a"]
