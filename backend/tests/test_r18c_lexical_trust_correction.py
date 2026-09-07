import csv
import json
import sqlite3
from pathlib import Path

from app.benchmarks.r18c_lexical_trust_correction import run_shadow


def test_shadow_is_monotonic_and_records_auditable_reasons(tmp_path: Path):
    evaluation = tmp_path / "evaluation.csv"
    mapping = tmp_path / "mapping.csv"
    database = tmp_path / "evidence.db"
    output = tmp_path / "shadow.csv"
    pair_id = "R18-TEST"
    with evaluation.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "review_pair_id", "panel_membership", "diagnostic_family",
            "expert_label", "expert_confidence", "expert_reason",
            "system_edge_class", "shadow_bucket", "generic_guard_reason",
            "cannot_link_present",
        ))
        writer.writeheader()
        writer.writerow({
            "review_pair_id": pair_id, "panel_membership": "DIAGNOSTIC",
            "diagnostic_family": "", "expert_label": "DIFFERENT_IDENTITY",
            "expert_confidence": "HIGH", "expert_reason": "DESCRIPTION_EVIDENCE",
            "system_edge_class": "STRONG_SUPPORT",
            "shadow_bucket": "SHADOW_LEXICAL_ONLY_OR_UNRESOLVED",
            "generic_guard_reason": "", "cannot_link_present": "false",
        })
    with mapping.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=(
            "review_pair_id", "record_a_stable_ref", "record_b_stable_ref",
            "evidence_fingerprint",
        ))
        writer.writeheader()
        writer.writerow({
            "review_pair_id": pair_id, "record_a_stable_ref": "a",
            "record_b_stable_ref": "b", "evidence_fingerprint": "edge",
        })
    connection = sqlite3.connect(database)
    source_columns = ", ".join(f"{name} TEXT" for name in (
        "contract", "uom", "type_code", "prime_commodity", "second_commodity",
        "accounting_group", "part_product_code", "part_product_family",
        "product_category_id", "hsn_sac_code", "hazard_code",
        "normalized_part_no", "normalized_description",
    ))
    connection.execute(
        f"CREATE TABLE scan_record_snapshot (scan_id INTEGER, record_ref_key TEXT, "
        f"source_row_index INTEGER, part_no TEXT, description TEXT, {source_columns})"
    )
    connection.execute(
        "CREATE TABLE identity_evidence_edge_snapshot ("
        "evidence_run_id INTEGER, evidence_fingerprint TEXT, "
        "component_scores_json TEXT, technical_evidence_json TEXT, "
        "classification_reason_codes_json TEXT)"
    )
    connection.executemany(
        "INSERT INTO scan_record_snapshot "
        "(scan_id, record_ref_key, source_row_index, part_no, description, type_code) "
        "VALUES (31, ?, ?, ?, ?, 'Purchased')",
        (("a", 1, "AA-ONE", "Copied phrase"),
         ("b", 2, "ZZ-TWO", "Copied phrase")),
    )
    connection.execute(
        "INSERT INTO identity_evidence_edge_snapshot VALUES (7, 'edge', ?, '{}', '[]')",
        (json.dumps({"description_similarity": 100, "part_no_similarity": 20}),),
    )
    connection.commit()
    connection.close()

    summary = run_shadow(evaluation, mapping, database, output)
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["current_edge_class"] == "STRONG_SUPPORT"
    assert rows[0]["shadow_corrected_edge_class"] == "REVIEW_SUPPORT"
    assert rows[0]["shadow_risk_reasons"] == "LEXICAL_SUPPORT_NOT_INDEPENDENT"
    assert summary["provider_calls"] == 0
