import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import event

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
from app.services import identity_group_projection, identity_group_snapshot_service
from app.engine import scoring
from app.llm.groq_provider import GroqLLMProvider
from app.services.hybrid_retrieval import HybridCandidateRetriever


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def add_scan(db, scan_id=1):
    row = DuplicateScan(
        id=scan_id, scan_name=f"scan-{scan_id}", threshold=80, status="COMPLETED",
        model_version="deterministic-v1", selected_fields="[]",
    )
    db.add(row)
    db.flush()
    return row


def add_run(db, scan_id=1, *, created_at=NOW, status="COMPLETED", suffix="a", **counts):
    values = {
        "records_seen": 0, "seed_edges": 0, "provisional_components": 0,
        "accepted_groups": 0, "likely_groups": 0, "review_groups": 0,
        "conflicting_families": 0, "oversized_families": 0,
        "ambiguous_families": 0, "internal_pairs_total": 0,
        "internal_pairs_reused": 0, "internal_pairs_rescored": 0,
        "cannot_links_found": 0, "max_component_size": 0,
        "max_accepted_group_size": 0,
    }
    values.update(counts)
    row = IdentityGroupProjectionRun(
        scan_id=scan_id, algorithm_version="constrained-group-projection-v1",
        edge_classifier_version="identity-edge-classifier-v1",
        evidence_fingerprint=(suffix * 64)[:64], max_group_validation_members=20,
        engine_version="deterministic-v1", status=status, created_at=created_at, **values,
    )
    db.add(row)
    db.flush()
    return row


def add_group(db, run, *, size, status, key, uoms=("PCS",), local_edge=False):
    pair_count = size * (size - 1) // 2
    strong = pair_count if status == "LIKELY_DUPLICATE_GROUP" else max(0, pair_count - 1)
    review = pair_count - strong
    group = IdentityGroupSnapshot(
        projection_run_id=run.id, scan_id=run.scan_id, hypothesis_key=key * 64,
        projection_algorithm_version=run.algorithm_version, group_status=status,
        group_size=size, supporting_edge_count=strong, review_edge_count=review,
        non_groupable_internal_count=0, internal_pair_count=pair_count,
        internal_pairs_reused=pair_count - int(local_edge),
        internal_pairs_rescored=int(local_edge), evidence_completeness=1.0,
        distinct_uoms_json=json.dumps(list(uoms)), same_uom_pair_count=pair_count,
        convertible_uom_pair_count=0, different_basis_pair_count=0,
        missing_or_wildcard_pair_count=0, malformed_or_unknown_pair_count=0,
        possible_mapping_error_count=0, reason_codes_json='["SAFE_SNAPSHOT"]',
        created_at=run.created_at,
    )
    db.add(group)
    db.flush()
    records = []
    for index in range(size):
        ref = f"{key}{index:02d}".ljust(64, key)
        record = ScanRecordSnapshot(
            scan_id=run.scan_id, record_ref_key=ref, contract="S1",
            part_no=f"{key.upper()}-{index}", description=f"Component {key} {index}",
            normalized_part_no=f"{key} {index}", normalized_description=f"component {key} {index}",
            uom=uoms[index % len(uoms)], product_category_id="CAT", hsn_sac_code="1000",
        )
        db.add(record)
        db.flush()
        db.add(IdentityGroupMemberSnapshot(
            group_snapshot_id=group.id, record_snapshot_id=record.id,
            member_index=index, record_ref_key=ref,
        ))
        records.append(record)
    for left in range(size):
        for right in range(left + 1, size):
            is_local = local_edge and left == 0 and right == size - 1
            db.add(IdentityGroupEdgeSnapshot(
                group_snapshot_id=group.id,
                left_record_snapshot_id=records[left].id,
                right_record_snapshot_id=records[right].id,
                edge_class="STRONG_SUPPORT" if status == "LIKELY_DUPLICATE_GROUP" or right > 1 else "REVIEW_SUPPORT",
                reason_codes_json='["DETERMINISTIC_EVIDENCE"]',
                evidence_source="G1_LOCAL_RESCORING" if is_local else "PERSISTED_CANDIDATE",
                deterministic_score=96.0, deterministic_status="LIKELY_DUPLICATE",
                critical_mismatches_json="[]",
            ))
    db.flush()
    return group


def add_diagnostic(db, run, *, size, status, key):
    conflict = status == "CONFLICTING_FAMILY"
    row = IdentityFamilyDiagnosticSnapshot(
        projection_run_id=run.id, scan_id=run.scan_id, diagnostic_key=key * 64,
        diagnostic_status=status, member_count=size, seed_edge_count=max(1, size - 1),
        internal_pair_count=size * (size - 1) // 2 if conflict else 0,
        internal_pairs_reused=1 if conflict else 0,
        internal_pairs_rescored=(size * (size - 1) // 2 - 1) if conflict else 0,
        cannot_link_count=1 if conflict else 0,
        reason_codes_json=json.dumps([
            "HUMAN_NON_DUPLICATE" if conflict else
            "MAX_VALIDATION_MEMBERS_20" if status == "DEFERRED_OVERSIZED_FAMILY" else
            "AMBIGUOUS_SCAN_LOCAL_RECORD_REF"
        ]), projection_algorithm_version=run.algorithm_version, created_at=run.created_at,
    )
    db.add(row)
    db.flush()
    records = []
    for index in range(size):
        ref = f"d{key}{index:02d}".ljust(64, key)
        record = ScanRecordSnapshot(
            scan_id=run.scan_id, record_ref_key=ref, contract="S1",
            part_no=f"D-{key}-{index}", description=f"Diagnostic {key} {index}",
            normalized_part_no=f"d {key} {index}", normalized_description=f"diagnostic {key} {index}",
            uom="PCS", product_category_id="", hsn_sac_code="",
        )
        db.add(record)
        db.flush()
        db.add(IdentityFamilyDiagnosticMemberSnapshot(
            diagnostic_snapshot_id=row.id, record_snapshot_id=record.id,
            member_index=index, record_ref_key=ref,
        ))
        records.append(record)
    if conflict:
        db.add(IdentityGroupEdgeSnapshot(
            diagnostic_snapshot_id=row.id, left_record_snapshot_id=records[0].id,
            right_record_snapshot_id=records[-1].id, edge_class="CANNOT_LINK",
            reason_codes_json='["HUMAN_NON_DUPLICATE"]', evidence_source="HUMAN_FEEDBACK",
            deterministic_score=91.0, deterministic_status="LIKELY_DUPLICATE",
            critical_mismatches_json="[]",
        ))
    db.flush()
    return row


def test_historical_scan_returns_typed_empty_state_without_recomputation(client, db, monkeypatch):
    add_scan(db)
    db.commit()
    monkeypatch.setattr(identity_group_projection, "project_identity_groups", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("G1 called")))
    monkeypatch.setattr(identity_group_snapshot_service, "project_identity_groups", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("G2 called")))
    monkeypatch.setattr(scoring, "score_candidate", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("scoring called")))
    monkeypatch.setattr(HybridCandidateRetriever, "retrieve", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("retrieval called")))
    monkeypatch.setattr(GroqLLMProvider, "complete_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider called")))
    writes = []

    def before_flush(*_args):
        writes.append(True)

    event.listen(db, "before_flush", before_flush)
    assert client.get("/api/scans/1/identity-group-projections").json() == []
    summary = client.get("/api/scans/1/identity-groups/summary")
    groups = client.get("/api/scans/1/identity-groups")
    diagnostics = client.get("/api/scans/1/identity-group-diagnostics")
    assert summary.status_code == groups.status_code == diagnostics.status_code == 200
    assert summary.json()["snapshot_available"] is False
    assert groups.json()["selected_projection"] is None and groups.json()["total"] == 0
    assert diagnostics.json()["selected_projection"] is None and diagnostics.json()["total"] == 0
    event.remove(db, "before_flush", before_flush)
    assert writes == []


def test_projection_listing_and_latest_completed_selection_ignore_newer_failed_run(client, db):
    add_scan(db)
    older = add_run(db, created_at=NOW, suffix="a", accepted_groups=1)
    latest = add_run(db, created_at=NOW + timedelta(minutes=1), suffix="b", accepted_groups=2)
    failed = add_run(db, created_at=NOW + timedelta(minutes=2), suffix="c", status="FAILED", accepted_groups=99)
    db.commit()
    runs = client.get("/api/scans/1/identity-group-projections").json()
    assert [row["projection_run_id"] for row in runs] == [failed.id, latest.id, older.id]
    summary = client.get("/api/scans/1/identity-groups/summary").json()
    assert summary["selected_projection"]["projection_run_id"] == latest.id
    assert client.get(f"/api/scans/1/identity-groups?projection_run_id={failed.id}").status_code == 409


def test_explicit_older_projection_is_isolated(client, db):
    add_scan(db)
    older = add_run(db, created_at=NOW, suffix="a", accepted_groups=1, likely_groups=1, max_accepted_group_size=2)
    old_group = add_group(db, older, size=2, status="LIKELY_DUPLICATE_GROUP", key="a")
    latest = add_run(db, created_at=NOW + timedelta(minutes=1), suffix="b", accepted_groups=1, review_groups=1, max_accepted_group_size=4)
    new_group = add_group(db, latest, size=4, status="POSSIBLE_DUPLICATE_GROUP_REVIEW", key="b")
    db.commit()
    body = client.get(f"/api/scans/1/identity-groups?projection_run_id={older.id}").json()
    assert body["total"] == 1
    assert body["items"][0]["group_snapshot_id"] == old_group.id
    assert body["items"][0]["group_snapshot_id"] != new_group.id


def test_group_list_order_filters_and_pagination_are_deterministic(client, db):
    add_scan(db)
    run = add_run(db, suffix="a", accepted_groups=3, likely_groups=2, review_groups=1, max_accepted_group_size=7)
    likely_two = add_group(db, run, size=2, status="LIKELY_DUPLICATE_GROUP", key="c")
    review_four = add_group(db, run, size=4, status="POSSIBLE_DUPLICATE_GROUP_REVIEW", key="a")
    likely_seven = add_group(db, run, size=7, status="LIKELY_DUPLICATE_GROUP", key="b")
    db.commit()
    body = client.get("/api/scans/1/identity-groups?limit=2").json()
    assert body["total"] == 3
    assert [item["group_snapshot_id"] for item in body["items"]] == [likely_seven.id, likely_two.id]
    page_two = client.get("/api/scans/1/identity-groups?limit=2&offset=2").json()
    assert [item["group_snapshot_id"] for item in page_two["items"]] == [review_four.id]
    filtered = client.get("/api/scans/1/identity-groups?status=POSSIBLE_DUPLICATE_GROUP_REVIEW&minimum_group_size=4&maximum_group_size=4").json()
    assert filtered["total"] == 1 and filtered["items"][0]["group_size"] == 4


def test_size_seven_detail_has_ordered_members_all_edges_uom_and_local_provenance(client, db):
    add_scan(db)
    run = add_run(db, suffix="a", accepted_groups=1, likely_groups=1, max_accepted_group_size=7,
                  internal_pairs_total=21, internal_pairs_reused=20, internal_pairs_rescored=1)
    group = add_group(db, run, size=7, status="LIKELY_DUPLICATE_GROUP", key="a", uoms=("PCS", "l"), local_edge=True)
    db.commit()
    body = client.get(f"/api/scans/1/identity-groups/{group.id}").json()
    assert body["hypothesis_key"] == "a" * 64
    assert body["projection"]["algorithm_version"] == "constrained-group-projection-v1"
    assert [member["member_index"] for member in body["members"]] == list(range(7))
    assert len(body["internal_edges"]) == 21
    local = [edge for edge in body["internal_edges"] if edge["evidence_source"] == "G1_LOCAL_RESCORING"]
    assert len(local) == 1 and local[0]["candidate_id"] is None
    assert body["uom_summary"]["distinct_uoms"] == ["PCS", "l"]


def test_diagnostics_remain_separate_and_details_are_untruncated(client, db):
    add_scan(db)
    run = add_run(db, suffix="a", conflicting_families=1, oversized_families=1,
                  ambiguous_families=1, cannot_links_found=1)
    conflict = add_diagnostic(db, run, size=3, status="CONFLICTING_FAMILY", key="a")
    oversized = add_diagnostic(db, run, size=21, status="DEFERRED_OVERSIZED_FAMILY", key="b")
    ambiguous = add_diagnostic(db, run, size=2, status="DEFERRED_AMBIGUOUS_RECORD_FAMILY", key="c")
    db.commit()
    assert client.get("/api/scans/1/identity-groups").json()["total"] == 0
    listing = client.get("/api/scans/1/identity-group-diagnostics").json()
    assert listing["total"] == 3
    conflict_body = client.get(f"/api/scans/1/identity-group-diagnostics/{conflict.id}").json()
    assert len(conflict_body["members"]) == 3
    assert conflict_body["conflict_edges"][0]["edge_class"] == "CANNOT_LINK"
    assert conflict_body["conflict_edges"][0]["evidence_source"] == "HUMAN_FEEDBACK"
    oversized_body = client.get(f"/api/scans/1/identity-group-diagnostics/{oversized.id}").json()
    assert len(oversized_body["members"]) == 21
    ambiguous_body = client.get(f"/api/scans/1/identity-group-diagnostics/{ambiguous.id}").json()
    assert ambiguous_body["reason_codes"] == ["AMBIGUOUS_SCAN_LOCAL_RECORD_REF"]


def test_summary_aggregates_counts_sizes_and_uom_without_changing_identity(client, db):
    add_scan(db)
    run = add_run(db, suffix="a", accepted_groups=2, likely_groups=1, review_groups=1,
                  conflicting_families=1, max_accepted_group_size=4)
    add_group(db, run, size=2, status="LIKELY_DUPLICATE_GROUP", key="a", uoms=("PCS",))
    review = add_group(db, run, size=4, status="POSSIBLE_DUPLICATE_GROUP_REVIEW", key="b", uoms=("PCS", "l"))
    review.different_basis_pair_count = 3
    review.same_uom_pair_count = 3
    add_diagnostic(db, run, size=3, status="CONFLICTING_FAMILY", key="c")
    db.commit()
    body = client.get("/api/scans/1/identity-groups/summary").json()
    assert body["accepted_groups"] == 2 and body["diagnostic_families"] == 1
    assert body["group_size_distribution"] == {"2": 1, "4": 1}
    assert body["largest_diagnostic_family"] == 3
    assert body["uom_summary"]["different_basis_pair_count"] == 3
    assert client.get(f"/api/scans/1/identity-groups/{review.id}").json()["group_status"] == "POSSIBLE_DUPLICATE_GROUP_REVIEW"


def test_invalid_selection_filters_pagination_and_unknown_resources_fail_safely(client, db):
    add_scan(db, 1)
    add_scan(db, 2)
    run = add_run(db, scan_id=2, suffix="a")
    db.commit()
    checks = [
        ("/api/scans/999/identity-groups", 404),
        (f"/api/scans/1/identity-groups?projection_run_id={run.id}", 404),
        ("/api/scans/1/identity-groups?status=CONFIRMED_DUPLICATE", 422),
        ("/api/scans/1/identity-groups?limit=101", 422),
        ("/api/scans/1/identity-groups?offset=-1", 422),
        ("/api/scans/1/identity-groups?minimum_group_size=8&maximum_group_size=2", 422),
        ("/api/scans/1/identity-groups/999", 404),
        ("/api/scans/1/identity-group-diagnostics/999", 404),
    ]
    for path, expected in checks:
        response = client.get(path)
        assert response.status_code == expected
        assert "Traceback" not in response.text and "\\" not in response.text


def test_group_and_diagnostic_queries_have_bounded_select_counts(client, db):
    add_scan(db)
    run = add_run(db, suffix="a", accepted_groups=120, likely_groups=120,
                  conflicting_families=1, max_accepted_group_size=2)
    for index in range(120):
        add_group(db, run, size=2, status="LIKELY_DUPLICATE_GROUP", key=chr(0x100 + index))
    diagnostic = add_diagnostic(db, run, size=14, status="CONFLICTING_FAMILY", key="z")
    db.commit()
    selects = []

    def count(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        assert client.get("/api/scans/1/identity-groups?limit=100").status_code == 200
        list_count = len(selects)
        selects.clear()
        group_id = db.query(IdentityGroupSnapshot.id).first()[0]
        selects.clear()
        assert client.get(f"/api/scans/1/identity-groups/{group_id}").status_code == 200
        detail_count = len(selects)
        selects.clear()
        assert client.get("/api/scans/1/identity-group-diagnostics").status_code == 200
        diagnostic_list_count = len(selects)
        selects.clear()
        assert client.get(f"/api/scans/1/identity-group-diagnostics/{diagnostic.id}").status_code == 200
        diagnostic_detail_count = len(selects)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    assert (list_count, detail_count, diagnostic_list_count, diagnostic_detail_count) == (4, 5, 4, 5)


def test_existing_pair_api_is_byte_compatible_across_snapshot_reads(client, db):
    add_scan(db)
    run = add_run(db, suffix="a")
    db.commit()
    before = client.get("/api/scans/1/candidates")
    assert client.get("/api/scans/1/identity-groups").status_code == 200
    assert client.get(f"/api/scans/1/identity-groups?projection_run_id={run.id}").status_code == 200
    after = client.get("/api/scans/1/candidates")
    assert before.status_code == after.status_code == 200
    assert before.content == after.content == b"[]"
