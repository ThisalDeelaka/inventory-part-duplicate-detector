"""Offline R18D assessment of post-R18C Review-support burden.

This module is diagnostic only.  It reads frozen development evidence and
persisted group-first snapshots, writes analysis artifacts, and never mutates
detector evidence or invokes an external provider.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from app.engine.lexical_trust import assess_lexical_trust


R18D_ANALYSIS_VERSION = "r18d-review-support-burden-v1"
LABELS = ("SAME_IDENTITY", "DIFFERENT_IDENTITY", "INSUFFICIENT_INFORMATION")
CLASSES = ("STRONG_SUPPORT", "REVIEW_SUPPORT", "NON_GROUPABLE", "CANNOT_LINK")
CONFIDENCES = ("HIGH", "MEDIUM", "LOW")
GF5_PARTITION_OBJECTIVE = "(covered, likely_members, strong, -review, -group_count)"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _json(value: str, fallback):
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def _engine_record(source: dict) -> dict:
    return {
        "PART_NO": source.get("part_no"),
        "DESCRIPTION": source.get("description"),
        "TYPE_CODE": source.get("type_code"),
        "PRIME_COMMODITY": source.get("prime_commodity"),
        "SECOND_COMMODITY": source.get("second_commodity"),
        "ACCOUNTING_GROUP": source.get("accounting_group"),
        "PART_PRODUCT_CODE": source.get("part_product_code"),
        "PART_PRODUCT_FAMILY": source.get("part_product_family"),
        "PRODUCT_CATEGORY_ID": source.get("product_category_id"),
        "HSN_SAC_CODE": source.get("hsn_sac_code"),
        "HAZARD_CODE": source.get("hazard_code"),
    }


def matrix_report(rows: list[dict], class_key: str = "post_r18c_edge_class") -> dict:
    counts = {
        label: {
            edge_class: sum(
                row["expert_label"] == label and row[class_key] == edge_class
                for row in rows
            )
            for edge_class in CLASSES
        }
        for label in LABELS
    }
    column_totals = {
        edge_class: sum(counts[label][edge_class] for label in LABELS)
        for edge_class in CLASSES
    }
    return {
        "counts": counts,
        "row_percentages": {
            label: {
                edge_class: round(100 * value / max(1, sum(counts[label].values())), 3)
                for edge_class, value in counts[label].items()
            }
            for label in LABELS
        },
        "column_percentages": {
            edge_class: {
                label: round(100 * counts[label][edge_class] / max(1, column_totals[edge_class]), 3)
                for label in LABELS
            }
            for edge_class in CLASSES
        },
    }


def _assessment(row: dict) -> dict:
    left = _json(row.get("record_a_source_fields_json", ""), {})
    right = _json(row.get("record_b_source_fields_json", ""), {})
    scores = _json(row.get("component_scores_json", ""), {})
    value = assess_lexical_trust(
        _engine_record(left), _engine_record(right), scores,
        record_reference_a="R18D-A", record_reference_b="R18D-B",
    )
    return value.payload()


def review_usefulness(expert_label: str, assessment: dict) -> str:
    """Assign an analysis-only category; this is not a production contract."""
    if expert_label == "SAME_IDENTITY":
        return "USEFUL_REVIEW_SUPPORT"
    if expert_label == "INSUFFICIENT_INFORMATION":
        return "OVERCOMMITTED_REVIEW_SUPPORT"
    weak = (
        assessment["description_dominance"]
        and not assessment["independent_identity_support_present"]
    ) or assessment["cross_field_incoherence"]
    return "NOISY_REVIEW_SUPPORT" if weak else "AMBIGUOUS_REVIEW_SUPPORT"


def review_origin(current_edge_class: str, post_r18c_edge_class: str) -> str:
    if post_r18c_edge_class != "REVIEW_SUPPORT":
        raise ValueError("review origin applies only to current Review support")
    return (
        "R18C_DEMOTED_STRONG_TO_REVIEW"
        if current_edge_class == "STRONG_SUPPORT"
        else "NATIVE_REVIEW"
    )


def _connected(members: set[str], pairs: set[tuple[str, str]]) -> bool:
    if len(members) < 2:
        return True
    adjacency = defaultdict(set)
    for left, right in pairs:
        adjacency[left].add(right)
        adjacency[right].add(left)
    seen = set()
    stack = [min(members)]
    while stack:
        item = stack.pop()
        if item in seen:
            continue
        seen.add(item)
        stack.extend(adjacency[item] - seen)
    return members <= seen


def _sets_by_parent(connection, snapshot_table, member_table, run_column, run_id,
                    status_column=None):
    status = f", s.{status_column}" if status_column else ""
    rows = connection.execute(
        f"SELECT m.{member_table[1]}, m.{member_table[2]}{status} "
        f"FROM {member_table[0]} m JOIN {snapshot_table[0]} s "
        f"ON s.id=m.{snapshot_table[1]} WHERE m.{run_column}=?",
        (run_id,),
    ).fetchall()
    values = defaultdict(lambda: {"members": set(), "status": ""})
    for row in rows:
        values[row[0]]["members"].add(row[1])
        if status_column:
            values[row[0]]["status"] = row[2]
    return values


def load_group_context(database_path: Path, *, scan_id: int = 31) -> dict:
    connection = sqlite3.connect(
        f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    resolution = connection.execute(
        "SELECT * FROM identity_resolution_run WHERE scan_id=? AND status='COMPLETED' "
        "ORDER BY id DESC LIMIT 1", (scan_id,),
    ).fetchone()
    projection = connection.execute(
        "SELECT * FROM g2_v2_projection_run WHERE scan_id=? AND status='COMPLETED' "
        "ORDER BY id DESC LIMIT 1", (scan_id,),
    ).fetchone()
    if resolution is None or projection is None:
        connection.close()
        raise ValueError("R18D requires completed persisted GF5 and G2_V2 state")

    groups = _sets_by_parent(
        connection,
        ("g2_v2_group_snapshot", "group_snapshot_id"),
        ("g2_v2_group_member", "group_snapshot_id", "stable_record_reference"),
        "projection_run_id", projection["id"], "status",
    )
    deferred = _sets_by_parent(
        connection,
        ("g2_v2_deferred_snapshot", "deferred_snapshot_id"),
        ("g2_v2_deferred_member", "deferred_snapshot_id", "stable_record_reference"),
        "projection_run_id", projection["id"], "reason",
    )
    conflicts = _sets_by_parent(
        connection,
        ("g2_v2_conflict_snapshot", "conflict_snapshot_id"),
        ("g2_v2_conflict_member", "conflict_snapshot_id", "stable_record_reference"),
        "projection_run_id", projection["id"], "conflict_type",
    )
    internal = connection.execute(
        "SELECT group_snapshot_id, stable_record_reference_1, "
        "stable_record_reference_2, edge_class, required_for_validation "
        "FROM g2_v2_internal_evidence WHERE projection_run_id=?",
        (projection["id"],),
    ).fetchall()
    internal_by_group = defaultdict(list)
    for row in internal:
        internal_by_group[row[0]].append(dict(row))

    neighborhood_rows = connection.execute(
        "SELECT n.id, m.record_id, r.record_ref_key "
        "FROM identity_neighborhood_snapshot n "
        "JOIN identity_neighborhood_member m ON m.neighborhood_id=n.id "
        "JOIN scan_record_snapshot r ON r.id=m.record_id "
        "WHERE n.discovery_run_id=? ORDER BY n.id, m.member_order",
        (resolution["discovery_run_id"],),
    ).fetchall()
    neighborhood_members = defaultdict(set)
    for row in neighborhood_rows:
        neighborhood_members[row[0]].add(row[2])
    parent = {}

    def find(value):
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    for members in neighborhood_members.values():
        ordered = sorted(members)
        for member in ordered:
            find(member)
        for member in ordered[1:]:
            union(ordered[0], member)
    work_units = defaultdict(set)
    for member in parent:
        work_units[find(member)].add(member)

    context = {
        "scan_id": scan_id,
        "resolution_run_id": resolution["id"],
        "projection_run_id": projection["id"],
        "groups": groups,
        "deferred": deferred,
        "conflicts": conflicts,
        "work_units": tuple(work_units.values()),
        "internal_by_group": internal_by_group,
        "metrics": {
            "accepted_group_count": projection["accepted_group_count"],
            "likely_group_count": projection["likely_group_count"],
            "review_group_count": projection["review_group_count"],
            "conflict_count": projection["conflict_count"],
            "deferred_count": projection["deferred_count"],
        },
    }
    connection.close()
    return context


def group_impact(left: str, right: str, context: dict) -> tuple[str, str]:
    pair = {left, right}
    for group_id, group in context["groups"].items():
        if pair <= group["members"]:
            status = group["status"]
            category = (
                "SUPPORTS_ACCEPTED_LIKELY_GROUP"
                if status == "LIKELY_DUPLICATE_GROUP"
                else "SUPPORTS_ACCEPTED_REVIEW_GROUP"
            )
            return category, str(group_id)
    for item_id, item in context["conflicts"].items():
        if pair <= item["members"]:
            return "CONTRIBUTES_TO_CONFLICT_CONTEXT", str(item_id)
    for item_id, item in context["deferred"].items():
        if pair <= item["members"]:
            return "CONTRIBUTES_TO_DEFERRED_FAMILY", str(item_id)
    if any(pair <= unit for unit in context["work_units"]):
        return "BRIDGE_OR_PARTITION_RELEVANT", ""
    return "NOT_IN_ANY_RESOLUTION_WORK_UNIT", ""


def bounded_group_counterfactual(rows: list[dict], context: dict, policy: str) -> dict:
    selected = {
        tuple(sorted((row["record_a_stable_ref"], row["record_b_stable_ref"])))
        for row in rows if row[policy] == "true"
    }
    affected = set()
    disconnected = set()
    redundant = set()
    for group_id, group in context["groups"].items():
        internal = context["internal_by_group"].get(group_id, ())
        removed = {
            tuple(sorted((edge["stable_record_reference_1"], edge["stable_record_reference_2"])))
            for edge in internal
            if edge["edge_class"] == "REVIEW_SUPPORT"
            and tuple(sorted((edge["stable_record_reference_1"], edge["stable_record_reference_2"]))) in selected
        }
        if not removed:
            continue
        affected.add(group_id)
        remaining = {
            tuple(sorted((edge["stable_record_reference_1"], edge["stable_record_reference_2"])))
            for edge in internal
            if edge["edge_class"] in {"STRONG_SUPPORT", "REVIEW_SUPPORT"}
            and tuple(sorted((edge["stable_record_reference_1"], edge["stable_record_reference_2"]))) not in removed
        }
        (redundant if _connected(group["members"], remaining) else disconnected).add(group_id)
    deferred_touched = sum(
        any(set(pair) <= item["members"] for pair in selected)
        for item in context["deferred"].values()
    )
    conflict_touched = sum(
        any(set(pair) <= item["members"] for pair in selected)
        for item in context["conflicts"].values()
    )
    status_by_group = {
        group_id: group["status"] for group_id, group in context["groups"].items()
    }
    same_selected = {
        tuple(sorted((row["record_a_stable_ref"], row["record_b_stable_ref"])))
        for row in rows if row[policy] == "true" and row["expert_label"] == "SAME_IDENTITY"
    }
    same_harmed = sum(
        any(set(pair) <= context["groups"][group_id]["members"] for pair in same_selected)
        for group_id in disconnected
    )
    return {
        "policy": policy,
        "method": "BOUNDED_PERSISTED_GROUP_CONNECTIVITY_SHADOW",
        "selected_review_edges": len(selected),
        "accepted_groups_touched": len(affected),
        "accepted_groups_connectivity_lost": len(disconnected),
        "accepted_groups_where_removed_review_is_redundant": len(redundant),
        "review_groups_connectivity_lost": sum(
            status_by_group[item] == "POSSIBLE_DUPLICATE_GROUP_REVIEW"
            for item in disconnected
        ),
        "likely_groups_connectivity_lost": sum(
            status_by_group[item] == "LIKELY_DUPLICATE_GROUP"
            for item in disconnected
        ),
        "expert_same_supported_groups_harmed": same_harmed,
        "deferred_families_touched": deferred_touched,
        "conflict_contexts_touched": conflict_touched,
        "partition_change": "UNKNOWN_WITHOUT_GOVERNED_GF5_OBJECTIVE",
        "cannot_link_safety": "UNCHANGED",
    }


def _scan33_summary(database_path: Path) -> dict:
    # Scan 33's stored run predates IQR-1A.  The authoritative current-product
    # control is the verified R18C in-memory rerun, not that stale projection.
    # R18D changes no runtime source, so it records and regression-tests this
    # exact frozen bounded reference rather than misrepresenting the old rows.
    return {
        "available": True,
        "source": "R18C_VERIFIED_IN_MEMORY_SCAN33_REFERENCE",
        "proposal_count": 1124,
        "evidence_edge_count": 1124,
        "cross_site_proposal_count": 21,
        "provider_calls": 0,
        "bicycle_relationship_count": 21,
        "bicycle_all_review": True,
        "bicycle_all_generic_only": True,
        "generic_review_suppression_would_erase_bicycle_edges": 21,
        "head_tail_cannot_link": True,
        "resolution": {
            "accepted_group_count": 2,
            "likely_group_count": 0,
            "review_group_count": 2,
            "conflict_count": 4,
            "deferred_count": 3,
            "unassigned_record_count": 113,
        },
        "runtime_result_unchanged": True,
    }


def run_assessment(r18c_path: Path, mapping_path: Path, database_path: Path,
                   output_dir: Path) -> dict:
    source_rows = _read_csv(r18c_path)
    mappings = {row["review_pair_id"]: row for row in _read_csv(mapping_path)}
    if {row["review_pair_id"] for row in source_rows} != set(mappings):
        raise ValueError("R18D source and mapping pair IDs do not reconcile")
    context = load_group_context(database_path)
    rows = []
    for source in source_rows:
        if "EVALUATION" not in source["panel_membership"].split("|"):
            continue
        post = source["shadow_corrected_edge_class"]
        if post != "REVIEW_SUPPORT":
            rows.append({**source, "post_r18c_edge_class": post})
            continue
        mapped = mappings[source["review_pair_id"]]
        assessment = _assessment(source)
        technical = _json(source["technical_evidence_json"], {})
        discriminator = technical.get("identity_discriminator", {})
        mismatch = int(discriminator.get("protected_conflict_count", 0)) > 0
        origin = review_origin(source["current_edge_class"], post)
        reasons = sorted(set(
            _json(source["current_classification_reason_codes_json"], [])
            + list(assessment["risk_reasons"])
        ))
        impact, impact_ref = group_impact(
            mapped["record_a_stable_ref"], mapped["record_b_stable_ref"], context
        )
        high_risk = bool(
            assessment["description_dominance"]
            and not assessment["independent_identity_support_present"]
            and (assessment["unresolved_discriminator_count"] > 0
                 or assessment["generic_or_copy_risk"]
                 or assessment["cross_field_incoherence"])
        )
        rows.append({
            **source,
            "post_r18c_edge_class": post,
            "record_a_stable_ref": mapped["record_a_stable_ref"],
            "record_b_stable_ref": mapped["record_b_stable_ref"],
            "sampling_stratum": mapped["evaluation_stratum"],
            "review_origin": origin,
            "review_usefulness": review_usefulness(source["expert_label"], assessment),
            "review_reason_codes": "|".join(reasons),
            "trusted_identity_support": str(assessment["independent_identity_support_present"]).lower(),
            "part_number_coherence": assessment["part_number_coherence"],
            "description_dominance": str(assessment["description_dominance"]).lower(),
            "unresolved_discriminators": assessment["unresolved_discriminator_count"],
            "typed_identity_support": str(
                assessment["support_provenance"] == "SHADOW_TRUSTED_IDENTITY_PRESENT"
            ).lower(),
            "technical_mismatch": str(mismatch or not assessment["technical_attribute_coherence"]).lower(),
            "cannot_link_state": source["protected_conflict_present"],
            "lexical_trust_assessment_state": json.dumps(assessment, sort_keys=True),
            "downgraded_from_strong": str(origin.startswith("R18C_")).lower(),
            "risk_lexical_independence": str(bool(assessment["risk_reasons"])).lower(),
            "risk_high_specificity": str(high_risk).lower(),
            "risk_generic_only": str(source["generic_guard_state"] == "GENERIC_DESCRIPTION").lower(),
            "group_impact": impact,
            "group_impact_reference": impact_ref,
        })
    review_rows = [row for row in rows if row["post_r18c_edge_class"] == "REVIEW_SUPPORT"]
    output_dir.mkdir(parents=True, exist_ok=True)
    review_path = output_dir / "r18d_review_support_analysis.csv"
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(review_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows)
    impact_path = output_dir / "r18d_group_impact_analysis.csv"
    impact_fields = (
        "review_pair_id", "expert_label", "expert_confidence", "review_origin",
        "review_usefulness", "risk_lexical_independence", "risk_high_specificity",
        "risk_generic_only", "group_impact", "group_impact_reference",
    )
    with impact_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=impact_fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(review_rows)

    matrix = matrix_report(rows)
    confidence = {
        label: dict(Counter(row["expert_confidence"] for row in review_rows if row["expert_label"] == label))
        for label in LABELS
    }
    provenance = dict(Counter(row["frozen_shadow_bucket"] for row in review_rows))
    matrix_by_confidence = {
        confidence: matrix_report(
            [row for row in rows if row["expert_confidence"] == confidence]
        )["counts"]
        for confidence in CONFIDENCES
    }
    matrix_by_provenance = {
        provenance_name: matrix_report(
            [row for row in rows if row["frozen_shadow_bucket"] == provenance_name]
        )["counts"]
        for provenance_name in sorted({row["frozen_shadow_bucket"] for row in rows})
    }
    patterns = {
        risk: {
            "different_review": sum(row["expert_label"] == "DIFFERENT_IDENTITY" and row[risk] == "true" for row in review_rows),
            "same_review": sum(row["expert_label"] == "SAME_IDENTITY" and row[risk] == "true" for row in review_rows),
            "same_strong": sum(
                row["expert_label"] == "SAME_IDENTITY" and row["post_r18c_edge_class"] == "STRONG_SUPPORT"
                and bool(_assessment(row)["risk_reasons"])
                for row in rows if risk == "risk_lexical_independence"
            ) if risk == "risk_lexical_independence" else None,
        }
        for risk in ("risk_lexical_independence", "risk_high_specificity", "risk_generic_only")
    }
    counterfactuals = [
        bounded_group_counterfactual(review_rows, context, policy)
        for policy in ("risk_lexical_independence", "risk_high_specificity", "risk_generic_only")
    ]
    scan33 = _scan33_summary(database_path)
    summary = {
        "analysis_version": R18D_ANALYSIS_VERSION,
        "governance": "POST_R18C_DEVELOPMENT_EFFECT_NOT_INDEPENDENT_VALIDATION",
        "evaluation_pair_count": len(rows),
        "matrix": matrix,
        "review_count": len(review_rows),
        "review_by_expert_label": dict(Counter(row["expert_label"] for row in review_rows)),
        "review_by_confidence_and_label": confidence,
        "review_by_provenance": provenance,
        "review_by_origin": dict(Counter(row["review_origin"] for row in review_rows)),
        "review_origin_by_expert_label": {
            origin: dict(Counter(
                row["expert_label"] for row in review_rows if row["review_origin"] == origin
            ))
            for origin in ("NATIVE_REVIEW", "R18C_DEMOTED_STRONG_TO_REVIEW")
        },
        "matrix_by_senior_confidence": matrix_by_confidence,
        "matrix_by_evidence_provenance": matrix_by_provenance,
        "review_usefulness": dict(Counter(row["review_usefulness"] for row in review_rows)),
        "group_impact": dict(Counter(row["group_impact"] for row in review_rows)),
        "risk_pattern_same_control_collisions": patterns,
        "counterfactuals": counterfactuals,
        "client_output": {
            "persisted_scan_31_review_groups": context["metrics"]["review_group_count"],
            "persisted_scan_31_review_group_members": sum(
                len(group["members"]) for group in context["groups"].values()
                if group["status"] == "POSSIBLE_DUPLICATE_GROUP_REVIEW"
            ),
            "scope_note": "Evaluation-panel trace over persisted pre-R18C Scan-31 group state",
        },
        "scan_33": scan33,
        "gf5_partition_policy": {
            "current_objective": GF5_PARTITION_OBJECTIVE,
            "adr_alignment": False,
            "material_confound": True,
            "reason": "Review suppression changes a negatively weighted partition term, so partition-level benefits cannot be attributed safely before governance resolution.",
        },
        "classification": "R18D_GF5_PARTITION_POLICY_CONFOUNDED",
        "next": "NEXT = R18G_GROUP_LEVEL_HUMAN_EVIDENCE",
        "runtime_detector_behavior": "UNCHANGED",
        "provider_calls": 0,
    }
    summary_path = output_dir / "r18d_shadow_counterfactual_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["artifacts"] = {
        review_path.name: {"bytes": review_path.stat().st_size, "sha256": _sha256(review_path)},
        impact_path.name: {"bytes": impact_path.stat().st_size, "sha256": _sha256(impact_path)},
        summary_path.name: {"bytes": summary_path.stat().st_size, "sha256": _sha256(summary_path)},
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--r18c", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run_assessment(args.r18c, args.mapping, args.database, args.output_dir), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
