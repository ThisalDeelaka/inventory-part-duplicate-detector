"""Atomic, immutable persistence for G1 scan-time identity hypotheses."""

import hashlib
import json
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Iterable, Mapping

from app.db.models import (
    DuplicateScan,
    IdentityFamilyDiagnosticMemberSnapshot,
    IdentityFamilyDiagnosticSnapshot,
    IdentityGroupEdgeSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.engine.domain_dictionary import normalize_part_no_with_dictionary
from app.engine.identity_edge import (
    IDENTITY_EDGE_CLASSIFIER_VERSION,
    IdentityEdgeClass,
    classify_identity_edge,
)
from app.engine.normalizer import normalize_description
from app.engine.scoring import score_candidate
from app.services.identity_group_projection import (
    GROUP_PROJECTION_VERSION,
    MAX_GROUP_VALIDATION_MEMBERS,
    FamilyDiagnosticStatus,
    GroupProjectionResult,
    IdentityGroupStatus,
    canonical_hypothesis_key,
    project_identity_groups,
    scan_record_ref,
)


@dataclass(frozen=True)
class SnapshotPersistenceResult:
    projection_run_id: int
    evidence_fingerprint: str
    idempotent: bool
    record_snapshots: int
    group_snapshots: int
    member_snapshots: int
    edge_snapshots: int
    diagnostic_snapshots: int
    diagnostic_member_snapshots: int


def _value(item, name: str, default=None):
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _record_payload(item) -> dict:
    return {
        "contract": _clean(_value(item, "CONTRACT", _value(item, "contract", ""))),
        "part_no": _clean(_value(item, "PART_NO", _value(item, "part_no", ""))),
        "description": _clean(_value(item, "DESCRIPTION", _value(item, "description", ""))),
        "uom": _clean(_value(item, "UNIT_MEAS", _value(item, "uom", ""))),
        "product_category_id": _clean(_value(item, "PRODUCT_CATEGORY_ID", "")),
        "hsn_sac_code": _clean(_value(item, "HSN_SAC_CODE", "")),
    }


def _decision(value) -> str:
    return str(_value(value, "user_decision", value) or "").strip().upper()


def _edge_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))


def _diagnostic_key(scan_id: int, status: str, members: tuple[str, ...]) -> str:
    return hashlib.sha256(_json({
        "scan_id": scan_id,
        "version": GROUP_PROJECTION_VERSION,
        "status": status,
        "members": members,
    }).encode("utf-8")).hexdigest()


def _projection_manifest(projection: GroupProjectionResult) -> dict:
    def edge(item):
        return {
            "left": item.left_ref,
            "right": item.right_ref,
            "class": item.edge_class.value,
            "reasons": list(item.reason_codes),
            "reused": item.reused,
        }

    groups = [{
        "key": group.hypothesis_key,
        "status": group.group_status.value,
        "members": [member.key for member in group.members],
        "counts": [
            group.group_size, group.supporting_edge_count, group.review_edge_count,
            group.non_groupable_internal_count, group.internal_pair_count,
            group.internal_pairs_reused, group.internal_pairs_rescored,
        ],
        "completeness": group.evidence_completeness,
        "uom": asdict(group.uom_summary),
        "reasons": list(group.reason_codes),
        "edges": [edge(item) for item in group.internal_edges],
    } for group in projection.groups]
    conflicts = [{
        "status": family.status.value,
        "members": [member.key for member in family.members],
        "counts": [family.seed_edge_count, family.internal_pair_count,
                   family.internal_pairs_reused, family.internal_pairs_rescored,
                   family.cannot_link_count],
        "reasons": list(family.reason_codes),
        "edges": [edge(item) for item in family.conflict_edges],
    } for family in projection.conflicting_families]
    deferred = [{
        "status": family.status.value,
        "members": [member.key for member in family.members],
        "seed_edge_count": family.seed_edge_count,
        "reasons": list(family.reason_codes),
    } for family in projection.deferred_families]
    return {
        "algorithm_version": GROUP_PROJECTION_VERSION,
        "metrics": asdict(projection.metrics),
        "groups": groups,
        "conflicts": conflicts,
        "deferred": deferred,
    }


def _validate_projection(scan_id: int, projection: GroupProjectionResult) -> None:
    groups = projection.groups
    diagnostics = projection.conflicting_families + projection.deferred_families
    all_family_members = []
    for group in groups:
        keys = tuple(member.key for member in group.members)
        if group.scan_id != scan_id or group.group_size != len(keys) or len(set(keys)) != len(keys):
            raise ValueError("accepted group has inconsistent scan, size, or duplicate members")
        if keys != tuple(sorted(keys)):
            raise ValueError("accepted group member order is not canonical")
        if group.hypothesis_key != canonical_hypothesis_key(scan_id, keys):
            raise ValueError("accepted group hypothesis key is not canonical")
        expected_pairs = len(keys) * (len(keys) - 1) // 2
        if group.internal_pair_count != expected_pairs or len(group.internal_edges) != expected_pairs:
            raise ValueError("accepted group does not contain complete internal-pair evidence")
        expected_pair_keys = {_edge_key(left, right) for left, right in combinations(keys, 2)}
        actual_pair_keys = {_edge_key(edge.left_ref, edge.right_ref) for edge in group.internal_edges}
        if expected_pair_keys != actual_pair_keys:
            raise ValueError("accepted group internal-edge set is inconsistent")
        if any(edge.edge_class == IdentityEdgeClass.CANNOT_LINK for edge in group.internal_edges):
            raise ValueError("accepted group contains CANNOT_LINK evidence")
        strong = sum(edge.edge_class == IdentityEdgeClass.STRONG_SUPPORT for edge in group.internal_edges)
        review = sum(edge.edge_class == IdentityEdgeClass.REVIEW_SUPPORT for edge in group.internal_edges)
        other = expected_pairs - strong - review
        reused = sum(edge.reused for edge in group.internal_edges)
        if (strong, review, other) != (
            group.supporting_edge_count, group.review_edge_count,
            group.non_groupable_internal_count,
        ):
            raise ValueError("accepted group edge counts are inconsistent")
        if (reused, expected_pairs - reused) != (
            group.internal_pairs_reused, group.internal_pairs_rescored
        ):
            raise ValueError("accepted group provenance counts are inconsistent")
        adjacency = {key: set() for key in keys}
        for edge in group.internal_edges:
            if edge.edge_class in {IdentityEdgeClass.STRONG_SUPPORT, IdentityEdgeClass.REVIEW_SUPPORT}:
                adjacency[edge.left_ref].add(edge.right_ref)
                adjacency[edge.right_ref].add(edge.left_ref)
        reached = set()
        pending = [keys[0]]
        while pending:
            current = pending.pop()
            if current not in reached:
                reached.add(current)
                pending.extend(adjacency[current] - reached)
        if reached != set(keys):
            raise ValueError("accepted group support graph is disconnected")
        expected_status = (
            IdentityGroupStatus.LIKELY_DUPLICATE_GROUP
            if strong == expected_pairs
            else IdentityGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW
        )
        if group.group_status != expected_status:
            raise ValueError("accepted group status is inconsistent with internal edges")
        summary = group.uom_summary
        if sum((
            summary.same_uom_pair_count, summary.convertible_uom_pair_count,
            summary.different_basis_pair_count, summary.missing_or_wildcard_pair_count,
            summary.malformed_or_unknown_pair_count,
        )) != expected_pairs:
            raise ValueError("accepted group UOM summary is inconsistent with pair count")
        if not 0.0 <= group.evidence_completeness <= 1.0:
            raise ValueError("accepted group evidence completeness is out of bounds")
        all_family_members.extend(keys)
    for family in diagnostics:
        keys = tuple(member.key for member in family.members)
        if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
            raise ValueError("diagnostic member order is inconsistent")
        if family.status == FamilyDiagnosticStatus.CONFLICTING_FAMILY:
            if not family.conflict_edges or any(
                edge.edge_class != IdentityEdgeClass.CANNOT_LINK
                for edge in family.conflict_edges
            ):
                raise ValueError("conflicting diagnostic lacks bounded CANNOT_LINK evidence")
            expected_pairs = len(keys) * (len(keys) - 1) // 2
            if (
                family.internal_pair_count != expected_pairs
                or family.internal_pairs_reused + family.internal_pairs_rescored != expected_pairs
                or family.cannot_link_count != len(family.conflict_edges)
            ):
                raise ValueError("conflicting diagnostic counts are inconsistent")
        all_family_members.extend(keys)
    metrics = projection.metrics
    ambiguous = sum(
        family.status == FamilyDiagnosticStatus.DEFERRED_AMBIGUOUS_RECORD_FAMILY
        for family in projection.deferred_families
    )
    if (
        metrics.accepted_groups != len(groups)
        or metrics.likely_groups != sum(g.group_status == IdentityGroupStatus.LIKELY_DUPLICATE_GROUP for g in groups)
        or metrics.review_groups != sum(g.group_status == IdentityGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW for g in groups)
        or metrics.conflicting_families != len(projection.conflicting_families)
        or metrics.oversized_families != sum(f.status == FamilyDiagnosticStatus.DEFERRED_OVERSIZED_FAMILY for f in projection.deferred_families)
        or metrics.internal_pairs_total != sum(g.internal_pair_count for g in groups) + sum(f.internal_pair_count for f in projection.conflicting_families)
        or metrics.internal_pairs_reused != sum(g.internal_pairs_reused for g in groups) + sum(f.internal_pairs_reused for f in projection.conflicting_families)
        or metrics.internal_pairs_rescored != sum(g.internal_pairs_rescored for g in groups) + sum(f.internal_pairs_rescored for f in projection.conflicting_families)
        or metrics.cannot_links_found != sum(f.cannot_link_count for f in projection.conflicting_families)
        or metrics.max_accepted_group_size != max((g.group_size for g in groups), default=0)
        or ambiguous < 0
    ):
        raise ValueError("projection metrics are inconsistent with snapshot graph")


def _build_evidence_lookup(
    scan_id: int,
    candidates: tuple,
    exclusions: tuple,
    feedback_by_candidate_id: Mapping[int, object],
) -> dict[tuple[str, str], list[tuple]]:
    lookup = {}
    for evidence, kind in [(item, "candidate") for item in candidates] + [
        (item, "exclusion") for item in exclusions
    ]:
        left = scan_record_ref(scan_id, evidence, "a").key
        right = scan_record_ref(scan_id, evidence, "b").key
        candidate_id = _value(evidence, "id") if kind == "candidate" else None
        feedback = feedback_by_candidate_id.get(candidate_id) if candidate_id is not None else None
        classification = classify_identity_edge(evidence, feedback=feedback)
        human = _decision(feedback) in {"DUPLICATE", "NOT_DUPLICATE"} or (
            feedback is None and str(_value(evidence, "review_status", "")).upper()
            in {"DUPLICATE", "NOT_DUPLICATE"}
        )
        source = "HUMAN_FEEDBACK" if human else (
            "PERSISTED_CANDIDATE" if kind == "candidate" else "PERSISTED_EXCLUSION"
        )
        row = (classification.edge_class, source, evidence)
        lookup.setdefault(_edge_key(left, right), []).append(row)
    return lookup


def _evidence_manifest(evidence_lookup: Mapping) -> list[dict]:
    output = []
    for pair, rows in evidence_lookup.items():
        for edge_class, source, evidence in rows:
            output.append({
                "pair": list(pair), "edge_class": edge_class.value, "source": source,
                "id": _value(evidence, "id"),
                "business_status": _value(evidence, "business_status"),
                "rule_decision": _value(evidence, "rule_decision"),
                "rejection_reason": _value(evidence, "rejection_reason"),
                "critical_mismatches": _value(evidence, "critical_mismatches", []),
            })
    return sorted(output, key=lambda row: _json(row))


def _edge_audit(
    edge,
    evidence_lookup: Mapping,
    records_by_key: Mapping[str, dict],
    selected_fields: tuple[str, ...],
    scan_mode: str,
) -> dict:
    pair = _edge_key(edge.left_ref, edge.right_ref)
    if not edge.reused:
        def scoring_record(values):
            return {
                "CONTRACT": values["contract"],
                "PART_NO": values["part_no"],
                "DESCRIPTION": values["description"],
                "UNIT_MEAS": values["uom"],
                "PRODUCT_CATEGORY_ID": values["product_category_id"],
                "HSN_SAC_CODE": values["hsn_sac_code"],
            }

        scored = score_candidate(
            scoring_record(records_by_key[pair[0]]),
            scoring_record(records_by_key[pair[1]]),
            list(selected_fields), scan_mode,
            allow_uom_mapping_review=True,
        )
        if classify_identity_edge(scored).edge_class != edge.edge_class:
            raise ValueError("local rescoring provenance does not reproduce G1 edge class")
        return {
            "source": "G1_LOCAL_RESCORING", "candidate_id": None, "exclusion_id": None,
            "score": _value(scored, "similarity_score"),
            "status": _value(scored, "business_status"),
            "mismatches": _value(scored, "critical_mismatches", []),
        }
    matches = [row for row in evidence_lookup.get(pair, ()) if row[0] == edge.edge_class]
    if not matches:
        raise ValueError("reused edge has no matching persisted evidence provenance")
    source_rank = {"HUMAN_FEEDBACK": 0, "PERSISTED_EXCLUSION": 1, "PERSISTED_CANDIDATE": 2}
    _, source, evidence = sorted(
        matches,
        key=lambda row: (source_rank[row[1]], _value(row[2], "id", 0) or 0),
    )[0]
    candidate_id = _value(evidence, "id") if source != "PERSISTED_EXCLUSION" else None
    exclusion_id = _value(evidence, "id") if source == "PERSISTED_EXCLUSION" else None
    return {
        "source": source, "candidate_id": candidate_id, "exclusion_id": exclusion_id,
        "score": _value(evidence, "similarity_score"),
        "status": _value(evidence, "business_status"),
        "mismatches": _value(evidence, "critical_mismatches", []),
    }


def _result_for_existing(db, run: IdentityGroupProjectionRun) -> SnapshotPersistenceResult:
    group_ids = [row[0] for row in db.query(IdentityGroupSnapshot.id).filter_by(projection_run_id=run.id)]
    diagnostic_ids = [row[0] for row in db.query(IdentityFamilyDiagnosticSnapshot.id).filter_by(projection_run_id=run.id)]
    member_count = db.query(IdentityGroupMemberSnapshot).filter(
        IdentityGroupMemberSnapshot.group_snapshot_id.in_(group_ids)
    ).count() if group_ids else 0
    diagnostic_member_count = db.query(IdentityFamilyDiagnosticMemberSnapshot).filter(
        IdentityFamilyDiagnosticMemberSnapshot.diagnostic_snapshot_id.in_(diagnostic_ids)
    ).count() if diagnostic_ids else 0
    edge_filter = []
    if group_ids:
        edge_filter.append(IdentityGroupEdgeSnapshot.group_snapshot_id.in_(group_ids))
    if diagnostic_ids:
        edge_filter.append(IdentityGroupEdgeSnapshot.diagnostic_snapshot_id.in_(diagnostic_ids))
    from sqlalchemy import or_
    edge_count = db.query(IdentityGroupEdgeSnapshot).filter(or_(*edge_filter)).count() if edge_filter else 0
    return SnapshotPersistenceResult(
        run.id, run.evidence_fingerprint, True, run.records_seen, len(group_ids),
        member_count, edge_count, len(diagnostic_ids), diagnostic_member_count,
    )


def persist_identity_group_projection(
    db,
    *,
    scan: DuplicateScan,
    records: Iterable,
    candidates: Iterable,
    projection: GroupProjectionResult,
    exclusions: Iterable = (),
    feedback_by_candidate_id: Mapping[int, object] | None = None,
    selected_fields: Iterable[str] = (),
    scan_mode: str | None = None,
) -> SnapshotPersistenceResult:
    """Validate and atomically persist one immutable G1 projection graph."""
    records = tuple(records)
    candidates = tuple(candidates)
    exclusions = tuple(exclusions)
    selected_fields = tuple(selected_fields)
    feedback_by_candidate_id = feedback_by_candidate_id or {}
    scan_mode = scan_mode or scan.scan_mode
    _validate_projection(scan.id, projection)
    record_rows = {}
    record_values = {}
    for item in records:
        values = _record_payload(item)
        ref = scan_record_ref(scan.id, item)
        previous = record_values.get(ref.key)
        if previous is not None and previous != values:
            identity_fields = ("contract", "part_no", "description")
            if any(previous[name] != values[name] for name in identity_fields):
                raise ValueError("scan-local record reference maps to inconsistent identity evidence")
            # G1 explicitly diagnoses conflicting non-identity evidence. Keep one
            # deterministic display snapshot while retaining that family diagnosis.
            values = {
                name: previous[name] if name in identity_fields else min(previous[name], values[name])
                for name in previous
            }
        record_values[ref.key] = values
    required_keys = {
        member.key
        for group in projection.groups
        for member in group.members
    } | {
        member.key
        for family in projection.conflicting_families + projection.deferred_families
        for member in family.members
    }
    if not required_keys.issubset(record_values):
        raise ValueError("projection member is missing from immutable scan record input")
    if projection.metrics.records_seen != len(record_values):
        raise ValueError("projection records_seen does not match immutable scan records")
    evidence_lookup = _build_evidence_lookup(
        scan.id, candidates, exclusions, feedback_by_candidate_id
    )
    manifest = {
        "projection": _projection_manifest(projection),
        "records": [{"record_ref_key": key, **record_values[key]} for key in sorted(record_values)],
        "evidence": _evidence_manifest(evidence_lookup),
    }
    fingerprint = hashlib.sha256(_json(manifest).encode("utf-8")).hexdigest()
    existing = db.query(IdentityGroupProjectionRun).filter_by(
        scan_id=scan.id,
        algorithm_version=GROUP_PROJECTION_VERSION,
        evidence_fingerprint=fingerprint,
    ).one_or_none()
    if existing is not None:
        return _result_for_existing(db, existing)
    metrics = projection.metrics
    ambiguous_count = sum(
        family.status == FamilyDiagnosticStatus.DEFERRED_AMBIGUOUS_RECORD_FAMILY
        for family in projection.deferred_families
    )
    try:
        run = IdentityGroupProjectionRun(
            scan_id=scan.id,
            algorithm_version=GROUP_PROJECTION_VERSION,
            edge_classifier_version=IDENTITY_EDGE_CLASSIFIER_VERSION,
            evidence_fingerprint=fingerprint,
            max_group_validation_members=MAX_GROUP_VALIDATION_MEMBERS,
            engine_version=scan.model_version,
            status="COMPLETED",
            records_seen=metrics.records_seen,
            seed_edges=metrics.seed_edges,
            provisional_components=metrics.provisional_components,
            accepted_groups=metrics.accepted_groups,
            likely_groups=metrics.likely_groups,
            review_groups=metrics.review_groups,
            conflicting_families=metrics.conflicting_families,
            oversized_families=metrics.oversized_families,
            ambiguous_families=ambiguous_count,
            internal_pairs_total=metrics.internal_pairs_total,
            internal_pairs_reused=metrics.internal_pairs_reused,
            internal_pairs_rescored=metrics.internal_pairs_rescored,
            cannot_links_found=metrics.cannot_links_found,
            max_component_size=metrics.max_component_size,
            max_accepted_group_size=metrics.max_accepted_group_size,
        )
        db.add(run)
        existing_records = {
            row.record_ref_key: row
            for row in db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).all()
        }
        for key in sorted(record_values):
            values = record_values[key]
            row = existing_records.get(key)
            if row is not None:
                persisted = {name: _clean(getattr(row, name)) for name in values}
                if persisted != values:
                    raise ValueError("existing immutable scan record snapshot differs")
            else:
                row = ScanRecordSnapshot(
                    scan_id=scan.id,
                    record_ref_key=key,
                    normalized_part_no=normalize_part_no_with_dictionary(values["part_no"]),
                    normalized_description=normalize_description(values["description"]),
                    **values,
                )
                db.add(row)
            record_rows[key] = row
        db.flush()

        group_rows = []
        member_rows = []
        edge_rows = []
        for group in projection.groups:
            summary = group.uom_summary
            group_row = IdentityGroupSnapshot(
                projection_run_id=run.id, scan_id=scan.id,
                hypothesis_key=group.hypothesis_key,
                projection_algorithm_version=GROUP_PROJECTION_VERSION,
                group_status=group.group_status.value,
                group_size=group.group_size,
                supporting_edge_count=group.supporting_edge_count,
                review_edge_count=group.review_edge_count,
                non_groupable_internal_count=group.non_groupable_internal_count,
                internal_pair_count=group.internal_pair_count,
                internal_pairs_reused=group.internal_pairs_reused,
                internal_pairs_rescored=group.internal_pairs_rescored,
                evidence_completeness=group.evidence_completeness,
                distinct_uoms_json=_json(list(summary.distinct_uoms)),
                same_uom_pair_count=summary.same_uom_pair_count,
                convertible_uom_pair_count=summary.convertible_uom_pair_count,
                different_basis_pair_count=summary.different_basis_pair_count,
                missing_or_wildcard_pair_count=summary.missing_or_wildcard_pair_count,
                malformed_or_unknown_pair_count=summary.malformed_or_unknown_pair_count,
                possible_mapping_error_count=summary.possible_mapping_error_count,
                reason_codes_json=_json(list(group.reason_codes)),
            )
            db.add(group_row)
            db.flush()
            group_rows.append(group_row)
            for index, member in enumerate(group.members):
                member_rows.append(IdentityGroupMemberSnapshot(
                    group_snapshot_id=group_row.id,
                    record_snapshot_id=record_rows[member.key].id,
                    member_index=index,
                    record_ref_key=member.key,
                ))
            for edge in group.internal_edges:
                audit = _edge_audit(edge, evidence_lookup, record_values, selected_fields, scan_mode)
                left_id, right_id = sorted((record_rows[edge.left_ref].id, record_rows[edge.right_ref].id))
                edge_rows.append(IdentityGroupEdgeSnapshot(
                    group_snapshot_id=group_row.id,
                    left_record_snapshot_id=left_id, right_record_snapshot_id=right_id,
                    edge_class=edge.edge_class.value,
                    reason_codes_json=_json(list(edge.reason_codes)),
                    evidence_source=audit["source"], candidate_id=audit["candidate_id"],
                    exclusion_id=audit["exclusion_id"], deterministic_score=audit["score"],
                    deterministic_status=audit["status"],
                    critical_mismatches_json=_json(audit["mismatches"] or []),
                ))

        diagnostic_rows = []
        diagnostic_member_rows = []
        for family in projection.conflicting_families + projection.deferred_families:
            keys = tuple(member.key for member in family.members)
            is_conflict = family.status == FamilyDiagnosticStatus.CONFLICTING_FAMILY
            row = IdentityFamilyDiagnosticSnapshot(
                projection_run_id=run.id, scan_id=scan.id,
                diagnostic_key=_diagnostic_key(scan.id, family.status.value, keys),
                diagnostic_status=family.status.value,
                member_count=len(keys), seed_edge_count=family.seed_edge_count,
                internal_pair_count=family.internal_pair_count if is_conflict else 0,
                internal_pairs_reused=family.internal_pairs_reused if is_conflict else 0,
                internal_pairs_rescored=family.internal_pairs_rescored if is_conflict else 0,
                cannot_link_count=family.cannot_link_count if is_conflict else 0,
                reason_codes_json=_json(list(family.reason_codes)),
                projection_algorithm_version=GROUP_PROJECTION_VERSION,
            )
            db.add(row)
            db.flush()
            diagnostic_rows.append(row)
            for index, member in enumerate(family.members):
                diagnostic_member_rows.append(IdentityFamilyDiagnosticMemberSnapshot(
                    diagnostic_snapshot_id=row.id,
                    record_snapshot_id=record_rows[member.key].id,
                    member_index=index,
                    record_ref_key=member.key,
                ))
            if is_conflict:
                for edge in family.conflict_edges:
                    audit = _edge_audit(edge, evidence_lookup, record_values, selected_fields, scan_mode)
                    left_id, right_id = sorted((record_rows[edge.left_ref].id, record_rows[edge.right_ref].id))
                    edge_rows.append(IdentityGroupEdgeSnapshot(
                        diagnostic_snapshot_id=row.id,
                        left_record_snapshot_id=left_id, right_record_snapshot_id=right_id,
                        edge_class=edge.edge_class.value,
                        reason_codes_json=_json(list(edge.reason_codes)),
                        evidence_source=audit["source"], candidate_id=audit["candidate_id"],
                        exclusion_id=audit["exclusion_id"], deterministic_score=audit["score"],
                        deterministic_status=audit["status"],
                        critical_mismatches_json=_json(audit["mismatches"] or []),
                    ))
        db.add_all(member_rows + diagnostic_member_rows + edge_rows)
        db.commit()
        return SnapshotPersistenceResult(
            run.id, fingerprint, False, len(record_rows), len(group_rows), len(member_rows),
            len(edge_rows), len(diagnostic_rows), len(diagnostic_member_rows),
        )
    except Exception:
        db.rollback()
        raise


def project_and_persist_identity_groups(
    db,
    *,
    scan: DuplicateScan,
    records: Iterable,
    candidates: Iterable,
    exclusions: Iterable = (),
    feedback_by_candidate_id: Mapping[int, object] | None = None,
    selected_fields: Iterable[str] = (),
) -> SnapshotPersistenceResult:
    """Authoritative G1 projection and atomic, idempotent G2 persistence."""
    records = tuple(records)
    candidates = tuple(candidates)
    exclusions = tuple(exclusions)
    feedback_by_candidate_id = feedback_by_candidate_id or {}
    projection = project_identity_groups(
        scan_id=scan.id,
        records=records,
        candidates=candidates,
        exclusions=exclusions,
        feedback_by_candidate_id=feedback_by_candidate_id,
        selected_fields=selected_fields,
        scan_mode=scan.scan_mode,
    )
    return persist_identity_group_projection(
        db, scan=scan, records=records, candidates=candidates, exclusions=exclusions,
        feedback_by_candidate_id=feedback_by_candidate_id, selected_fields=selected_fields,
        projection=projection,
    )


def load_identity_group_snapshot_manifest(db, projection_run_id: int) -> dict:
    """Reload a complete snapshot graph without invoking G1 or deterministic scoring."""
    run = db.query(IdentityGroupProjectionRun).filter_by(id=projection_run_id).one()
    groups = db.query(IdentityGroupSnapshot).filter_by(
        projection_run_id=projection_run_id
    ).order_by(IdentityGroupSnapshot.hypothesis_key).all()
    diagnostics = db.query(IdentityFamilyDiagnosticSnapshot).filter_by(
        projection_run_id=projection_run_id
    ).order_by(IdentityFamilyDiagnosticSnapshot.diagnostic_key).all()
    group_ids = [row.id for row in groups]
    diagnostic_ids = [row.id for row in diagnostics]
    members = db.query(IdentityGroupMemberSnapshot).filter(
        IdentityGroupMemberSnapshot.group_snapshot_id.in_(group_ids)
    ).order_by(IdentityGroupMemberSnapshot.group_snapshot_id, IdentityGroupMemberSnapshot.member_index).all() if group_ids else []
    diagnostic_members = db.query(IdentityFamilyDiagnosticMemberSnapshot).filter(
        IdentityFamilyDiagnosticMemberSnapshot.diagnostic_snapshot_id.in_(diagnostic_ids)
    ).order_by(
        IdentityFamilyDiagnosticMemberSnapshot.diagnostic_snapshot_id,
        IdentityFamilyDiagnosticMemberSnapshot.member_index,
    ).all() if diagnostic_ids else []
    edges = db.query(IdentityGroupEdgeSnapshot).filter(
        (IdentityGroupEdgeSnapshot.group_snapshot_id.in_(group_ids) if group_ids else False)
        | (IdentityGroupEdgeSnapshot.diagnostic_snapshot_id.in_(diagnostic_ids) if diagnostic_ids else False)
    ).order_by(
        IdentityGroupEdgeSnapshot.group_snapshot_id,
        IdentityGroupEdgeSnapshot.diagnostic_snapshot_id,
        IdentityGroupEdgeSnapshot.left_record_snapshot_id,
        IdentityGroupEdgeSnapshot.right_record_snapshot_id,
    ).all() if group_ids or diagnostic_ids else []
    record_ids = {
        row.id: row.record_ref_key
        for row in db.query(ScanRecordSnapshot).filter_by(scan_id=run.scan_id).all()
    }
    return {
        "run": {
            "id": run.id, "scan_id": run.scan_id, "algorithm_version": run.algorithm_version,
            "edge_classifier_version": run.edge_classifier_version,
            "evidence_fingerprint": run.evidence_fingerprint,
            "max_group_validation_members": run.max_group_validation_members,
            "engine_version": run.engine_version, "status": run.status,
            "metrics": {name: getattr(run, name) for name in (
                "records_seen", "seed_edges", "provisional_components", "accepted_groups",
                "likely_groups", "review_groups", "conflicting_families", "oversized_families",
                "ambiguous_families", "internal_pairs_total", "internal_pairs_reused",
                "internal_pairs_rescored", "cannot_links_found", "max_component_size",
                "max_accepted_group_size",
            )},
        },
        "groups": [{
            "hypothesis_key": group.hypothesis_key, "status": group.group_status,
            "members": [item.record_ref_key for item in members if item.group_snapshot_id == group.id],
            "counts": {
                "group_size": group.group_size,
                "supporting_edge_count": group.supporting_edge_count,
                "review_edge_count": group.review_edge_count,
                "non_groupable_internal_count": group.non_groupable_internal_count,
                "internal_pair_count": group.internal_pair_count,
                "internal_pairs_reused": group.internal_pairs_reused,
                "internal_pairs_rescored": group.internal_pairs_rescored,
            },
            "evidence_completeness": group.evidence_completeness,
            "reason_codes": json.loads(group.reason_codes_json),
            "uom": {
                "distinct_uoms": json.loads(group.distinct_uoms_json),
                "same_uom_pair_count": group.same_uom_pair_count,
                "convertible_uom_pair_count": group.convertible_uom_pair_count,
                "different_basis_pair_count": group.different_basis_pair_count,
                "missing_or_wildcard_pair_count": group.missing_or_wildcard_pair_count,
                "malformed_or_unknown_pair_count": group.malformed_or_unknown_pair_count,
                "possible_mapping_error_count": group.possible_mapping_error_count,
            },
        } for group in groups],
        "diagnostics": [{
            "diagnostic_key": row.diagnostic_key, "status": row.diagnostic_status,
            "members": [item.record_ref_key for item in diagnostic_members if item.diagnostic_snapshot_id == row.id],
            "reason_codes": json.loads(row.reason_codes_json),
            "counts": {
                "member_count": row.member_count, "seed_edge_count": row.seed_edge_count,
                "internal_pair_count": row.internal_pair_count,
                "internal_pairs_reused": row.internal_pairs_reused,
                "internal_pairs_rescored": row.internal_pairs_rescored,
                "cannot_link_count": row.cannot_link_count,
            },
        } for row in diagnostics],
        "edges": [{
            "group_snapshot_id": row.group_snapshot_id,
            "diagnostic_snapshot_id": row.diagnostic_snapshot_id,
            "left_record_snapshot_id": row.left_record_snapshot_id,
            "right_record_snapshot_id": row.right_record_snapshot_id,
            "left_record_ref_key": record_ids[row.left_record_snapshot_id],
            "right_record_ref_key": record_ids[row.right_record_snapshot_id],
            "edge_class": row.edge_class,
            "reason_codes": json.loads(row.reason_codes_json),
            "evidence_source": row.evidence_source,
            "candidate_id": row.candidate_id,
            "exclusion_id": row.exclusion_id,
        } for row in edges],
    }
