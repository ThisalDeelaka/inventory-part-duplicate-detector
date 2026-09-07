"""Offline R18C shadow evaluation over the frozen R18 development evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path

from app.engine.lexical_trust import assess_lexical_trust


R18C_SHADOW_VERSION = "r18c-lexical-trust-shadow-v1"
_ORDER = {
    "STRONG_SUPPORT": 3,
    "REVIEW_SUPPORT": 2,
    "NON_GROUPABLE": 1,
    "CANNOT_LINK": 0,
    "HISTORICAL_DIAGNOSTIC": 0,
}
_POSITIVE_CONTROLS = {
    "R17_FAN_BLADE", "R17_F30", "R17_B38",
    "R17_TURBINE_LUBRICATING_OIL", "R17_CONTACT_CLEANER",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _engine_record(row) -> dict:
    return {
        "PART_NO": row["part_no"],
        "DESCRIPTION": row["description"],
        "TYPE_CODE": row["type_code"],
        "PRIME_COMMODITY": row["prime_commodity"],
        "SECOND_COMMODITY": row["second_commodity"],
        "ACCOUNTING_GROUP": row["accounting_group"],
        "PART_PRODUCT_CODE": row["part_product_code"],
        "PART_PRODUCT_FAMILY": row["part_product_family"],
        "PRODUCT_CATEGORY_ID": row["product_category_id"],
        "HSN_SAC_CODE": row["hsn_sac_code"],
        "HAZARD_CODE": row["hazard_code"],
    }


def _source_payload(row) -> dict:
    return {
        key: row[key]
        for key in (
            "source_row_index", "part_no", "description", "contract", "uom",
            "type_code", "prime_commodity", "second_commodity",
            "accounting_group", "part_product_code", "part_product_family",
            "product_category_id", "hsn_sac_code", "hazard_code",
            "normalized_part_no", "normalized_description",
        )
    }


def _matrix(rows, key: str) -> dict[str, dict[str, int]]:
    labels = ("SAME_IDENTITY", "DIFFERENT_IDENTITY", "INSUFFICIENT_INFORMATION")
    classes = ("STRONG_SUPPORT", "REVIEW_SUPPORT", "NON_GROUPABLE", "CANNOT_LINK")
    return {
        label: {
            edge_class: sum(
                row["expert_label"] == label and row[key] == edge_class
                for row in rows
            )
            for edge_class in classes
        }
        for label in labels
    }


def run_shadow(
    evaluation_path: Path,
    mapping_path: Path,
    database_path: Path,
    output_csv: Path,
) -> dict[str, object]:
    """Apply the proposed rule without writing to the source database."""
    with evaluation_path.open(encoding="utf-8", newline="") as handle:
        evaluation = {row["review_pair_id"]: row for row in csv.DictReader(handle)}
    with mapping_path.open(encoding="utf-8", newline="") as handle:
        mapping = {row["review_pair_id"]: row for row in csv.DictReader(handle)}
    if set(evaluation) != set(mapping):
        raise ValueError("R18C pair mapping does not reconcile")

    connection = sqlite3.connect(
        f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    rows = []
    for pair_id in sorted(evaluation):
        expert = evaluation[pair_id]
        mapped = mapping[pair_id]
        current = expert["system_edge_class"]
        shadow = current
        assessment_payload = None
        reason_codes = []
        left = connection.execute(
            "SELECT * FROM scan_record_snapshot WHERE scan_id = 31 "
            "AND record_ref_key = ?", (mapped["record_a_stable_ref"],)
        ).fetchone()
        right = connection.execute(
            "SELECT * FROM scan_record_snapshot WHERE scan_id = 31 "
            "AND record_ref_key = ?", (mapped["record_b_stable_ref"],)
        ).fetchone()
        evidence = connection.execute(
            "SELECT * FROM identity_evidence_edge_snapshot "
            "WHERE evidence_run_id = 7 AND evidence_fingerprint = ?",
            (mapped["evidence_fingerprint"],),
        ).fetchone()
        if current == "STRONG_SUPPORT" and left and right and evidence:
            scores = json.loads(evidence["component_scores_json"])
            assessment = assess_lexical_trust(
                _engine_record(left), _engine_record(right), scores,
                record_reference_a=left["record_ref_key"],
                record_reference_b=right["record_ref_key"],
            )
            assessment_payload = assessment.payload()
            reason_codes = list(assessment.risk_reasons)
            if assessment.requires_strong_downgrade:
                shadow = "REVIEW_SUPPORT"
        if _ORDER.get(shadow, 0) > _ORDER.get(current, 0):
            raise AssertionError("R18C shadow rule promoted support")
        rows.append({
            "review_pair_id": pair_id,
            "panel_membership": expert["panel_membership"],
            "diagnostic_family": expert["diagnostic_family"],
            "expert_label": expert["expert_label"],
            "expert_confidence": expert["expert_confidence"],
            "expert_reason": expert["expert_reason"],
            "frozen_shadow_bucket": expert["shadow_bucket"],
            "current_edge_class": current,
            "shadow_corrected_edge_class": shadow,
            "shadow_risk_reasons": "|".join(reason_codes),
            "generic_guard_state": expert["generic_guard_reason"],
            "protected_conflict_present": expert["cannot_link_present"],
            "record_a_source_fields_json": json.dumps(
                _source_payload(left) if left else {}, sort_keys=True
            ),
            "record_b_source_fields_json": json.dumps(
                _source_payload(right) if right else {}, sort_keys=True
            ),
            "lexical_trust_assessment_json": json.dumps(
                assessment_payload, sort_keys=True
            ) if assessment_payload else "",
            "component_scores_json": evidence["component_scores_json"] if evidence else "{}",
            "technical_evidence_json": evidence["technical_evidence_json"] if evidence else "{}",
            "current_classification_reason_codes_json": (
                evidence["classification_reason_codes_json"] if evidence else "[]"
            ),
        })
    connection.close()

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    panel = [row for row in rows if "EVALUATION" in row["panel_membership"].split("|")]
    lexical = [
        row for row in panel
        if row["frozen_shadow_bucket"] == "SHADOW_LEXICAL_ONLY_OR_UNRESOLVED"
    ]
    different_strong = [
        row for row in lexical
        if row["expert_label"] == "DIFFERENT_IDENTITY"
        and row["current_edge_class"] == "STRONG_SUPPORT"
    ]
    same_strong = [
        row for row in lexical
        if row["expert_label"] == "SAME_IDENTITY"
        and row["current_edge_class"] == "STRONG_SUPPORT"
    ]
    high_different = [
        row for row in different_strong if row["expert_confidence"] == "HIGH"
    ]
    changed = [
        row for row in rows
        if row["current_edge_class"] != row["shadow_corrected_edge_class"]
    ]
    positive_controls = [
        row for row in rows if row["diagnostic_family"] in _POSITIVE_CONTROLS
    ]
    criteria = {
        "high_confidence_different_no_longer_strong": all(
            row["shadow_corrected_edge_class"] != "STRONG_SUPPORT"
            for row in high_different
        ) and len(high_different) == 2,
        "at_least_seven_of_nine_different_no_longer_strong": sum(
            row["shadow_corrected_edge_class"] != "STRONG_SUPPORT"
            for row in different_strong
        ) >= 7 and len(different_strong) == 9,
        "same_never_non_groupable_or_cannot_link": all(
            row["shadow_corrected_edge_class"] in {"STRONG_SUPPORT", "REVIEW_SUPPORT"}
            for row in same_strong
        ) and len(same_strong) == 32,
        "high_confidence_same_support_coverage_100_percent": all(
            row["shadow_corrected_edge_class"] in {"STRONG_SUPPORT", "REVIEW_SUPPORT"}
            for row in same_strong if row["expert_confidence"] == "HIGH"
        ),
        "known_positive_controls_remain_supported": all(
            row["shadow_corrected_edge_class"] in {"STRONG_SUPPORT", "REVIEW_SUPPORT"}
            for row in positive_controls
            if row["current_edge_class"] in {"STRONG_SUPPORT", "REVIEW_SUPPORT"}
        ),
        "cannot_link_unchanged": all(
            row["shadow_corrected_edge_class"] == "CANNOT_LINK"
            for row in rows if row["current_edge_class"] == "CANNOT_LINK"
        ),
        "exact_generic_guard_unchanged": all(
            row["shadow_corrected_edge_class"] == row["current_edge_class"]
            for row in rows if row["generic_guard_state"] == "GENERIC_DESCRIPTION"
        ),
        "no_promotions": all(
            _ORDER.get(row["shadow_corrected_edge_class"], 0)
            <= _ORDER.get(row["current_edge_class"], 0)
            for row in rows
        ),
    }
    return {
        "shadow_version": R18C_SHADOW_VERSION,
        "classification": (
            "R18C_SHADOW_PASS" if all(criteria.values()) else "R18C_SHADOW_FAIL"
        ),
        "evaluation_governance": "DEVELOPMENT_DIAGNOSTIC_EVIDENCE",
        "independent_post_change_quality_claim": "NOT_AUTHORIZED",
        "pair_count": len(rows),
        "evaluation_pair_count": len(panel),
        "before_matrix": _matrix(panel, "current_edge_class"),
        "shadow_matrix": _matrix(panel, "shadow_corrected_edge_class"),
        "changed_count": len(changed),
        "changed_by_expert_label": dict(Counter(row["expert_label"] for row in changed)),
        "lexical_different_strong_before": len(different_strong),
        "lexical_different_strong_after": sum(
            row["shadow_corrected_edge_class"] == "STRONG_SUPPORT"
            for row in different_strong
        ),
        "lexical_same_strong_before": len(same_strong),
        "lexical_same_strong_after": sum(
            row["shadow_corrected_edge_class"] == "STRONG_SUPPORT"
            for row in same_strong
        ),
        "criteria": criteria,
        "provider_calls": 0,
        "shadow_csv_sha256": _sha256(output_csv),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--output-summary", required=True, type=Path)
    args = parser.parse_args()
    summary = run_shadow(
        args.evaluation, args.mapping, args.database, args.output_csv
    )
    args.output_summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
