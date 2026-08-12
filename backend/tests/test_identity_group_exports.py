import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from app.db.models import (
    DuplicateScan,
    IdentityFamilyDiagnosticMemberSnapshot,
    IdentityFamilyDiagnosticSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.llm.groq_provider import GroqLLMProvider
from app.services import identity_group_projection, identity_group_snapshot_service
from app.services.identity_group_export_service import (
    IDENTITY_DIAGNOSTIC_EXPORT_FIELDS,
    IDENTITY_GROUP_EXPORT_FIELDS,
)


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def add_scan(db, scan_id=1):
    row = DuplicateScan(
        id=scan_id, scan_name=f"scan-{scan_id}", threshold=80, status="COMPLETED",
        model_version="deterministic-v1", selected_fields="[]",
    )
    db.add(row); db.flush()
    return row


def add_run(db, scan_id=1, *, suffix="a", created_at=NOW, status="COMPLETED"):
    row = IdentityGroupProjectionRun(
        scan_id=scan_id, algorithm_version="constrained-group-projection-v1",
        edge_classifier_version="identity-edge-classifier-v1",
        evidence_fingerprint=suffix * 64, max_group_validation_members=20,
        engine_version="deterministic-v1", status=status, created_at=created_at,
        records_seen=0, seed_edges=0, provisional_components=0, accepted_groups=0,
        likely_groups=0, review_groups=0, conflicting_families=0,
        oversized_families=0, ambiguous_families=0, internal_pairs_total=0,
        internal_pairs_reused=0, internal_pairs_rescored=0, cannot_links_found=0,
        max_component_size=0, max_accepted_group_size=0,
    )
    db.add(row); db.flush()
    return row


def add_group(db, run, *, size, status="LIKELY_DUPLICATE_GROUP", key="a",
              member_order=None, dangerous=False, description="Component"):
    pair_count = size * (size - 1) // 2
    group = IdentityGroupSnapshot(
        projection_run_id=run.id, scan_id=run.scan_id, hypothesis_key=key * 64,
        projection_algorithm_version=run.algorithm_version, group_status=status,
        group_size=size, supporting_edge_count=pair_count if status == "LIKELY_DUPLICATE_GROUP" else 0,
        review_edge_count=0 if status == "LIKELY_DUPLICATE_GROUP" else pair_count,
        non_groupable_internal_count=0, internal_pair_count=pair_count,
        internal_pairs_reused=pair_count, internal_pairs_rescored=0,
        evidence_completeness=1.0, distinct_uoms_json='["PCS","l"]',
        same_uom_pair_count=pair_count, convertible_uom_pair_count=0,
        different_basis_pair_count=0, missing_or_wildcard_pair_count=0,
        malformed_or_unknown_pair_count=0, possible_mapping_error_count=0,
        reason_codes_json='["SAFE_SNAPSHOT"]', created_at=run.created_at,
    )
    db.add(group); db.flush()
    indexes = member_order if member_order is not None else range(size)
    for index in indexes:
        ref = f"{run.id}-{key}-{index}".ljust(64, key)
        record = ScanRecordSnapshot(
            scan_id=run.scan_id, record_ref_key=ref, contract="=SITE" if dangerous and index == 0 else "S1",
            part_no="+PART" if dangerous and index == 0 else f"{key.upper()}-{index}",
            description=description if index == 0 else f"{description} {index}",
            normalized_part_no=f"{key} {index}", normalized_description="component",
            uom="PCS", product_category_id="@CATEGORY" if dangerous and index == 0 else "CAT",
            hsn_sac_code="-100" if dangerous and index == 0 else "1000",
        )
        db.add(record); db.flush()
        db.add(IdentityGroupMemberSnapshot(
            group_snapshot_id=group.id, record_snapshot_id=record.id,
            member_index=index, record_ref_key=ref,
        ))
    run.accepted_groups += 1
    run.likely_groups += status == "LIKELY_DUPLICATE_GROUP"
    run.review_groups += status == "POSSIBLE_DUPLICATE_GROUP_REVIEW"
    run.records_seen += size
    run.max_accepted_group_size = max(run.max_accepted_group_size, size)
    db.flush()
    return group


def add_diagnostic(db, run, *, size=3, status="CONFLICTING_FAMILY", key="d"):
    row = IdentityFamilyDiagnosticSnapshot(
        projection_run_id=run.id, scan_id=run.scan_id, diagnostic_key=key * 64,
        diagnostic_status=status, member_count=size, seed_edge_count=size - 1,
        internal_pair_count=size * (size - 1) // 2 if status == "CONFLICTING_FAMILY" else 0,
        internal_pairs_reused=0, internal_pairs_rescored=0,
        cannot_link_count=1 if status == "CONFLICTING_FAMILY" else 0,
        reason_codes_json='["HUMAN_NON_DUPLICATE"]',
        projection_algorithm_version=run.algorithm_version, created_at=run.created_at,
    )
    db.add(row); db.flush()
    for index in reversed(range(size)):
        ref = f"{run.id}-{key}-{index}".ljust(64, key)
        record = ScanRecordSnapshot(
            scan_id=run.scan_id, record_ref_key=ref, contract="S1", part_no=f"D-{index}",
            description=f"Diagnostic {index}", normalized_part_no=f"d {index}",
            normalized_description=f"diagnostic {index}", uom="PCS",
            product_category_id="", hsn_sac_code="",
        )
        db.add(record); db.flush()
        db.add(IdentityFamilyDiagnosticMemberSnapshot(
            diagnostic_snapshot_id=row.id, record_snapshot_id=record.id,
            member_index=index, record_ref_key=ref,
        ))
    run.conflicting_families += status == "CONFLICTING_FAMILY"
    run.oversized_families += status == "DEFERRED_OVERSIZED_FAMILY"
    run.ambiguous_families += status == "DEFERRED_AMBIGUOUS_RECORD_FAMILY"
    run.records_seen += size
    db.flush()
    return row


def rows(response):
    return list(csv.DictReader(io.StringIO(response.text)))


@pytest.mark.parametrize("size", [2, 4, 7, 14])
def test_group_exports_exactly_one_adjacent_row_per_member_not_pair_combinations(client, db, size):
    add_scan(db); run = add_run(db); add_group(db, run, size=size, member_order=reversed(range(size)))
    db.commit()
    exported = rows(client.get("/api/scans/1/identity-groups/export.csv"))
    assert len(exported) == size
    assert [int(row["group_member_index"]) for row in exported] == list(range(size))


def test_multiple_groups_are_contiguous_and_follow_canonical_status_size_key_order(client, db):
    add_scan(db); run = add_run(db)
    review = add_group(db, run, size=7, status="POSSIBLE_DUPLICATE_GROUP_REVIEW", key="a")
    likely_small = add_group(db, run, size=2, key="c")
    likely_large = add_group(db, run, size=4, key="b")
    db.commit()
    exported = rows(client.get("/api/scans/1/identity-groups/export.csv"))
    ordered_ids = [int(row["group_snapshot_id"]) for row in exported]
    assert ordered_ids == [likely_large.id] * 4 + [likely_small.id] * 2 + [review.id] * 7


def test_machine_and_human_status_labels_are_business_safe(client, db):
    add_scan(db); run = add_run(db)
    add_group(db, run, size=2, key="a")
    add_group(db, run, size=2, status="POSSIBLE_DUPLICATE_GROUP_REVIEW", key="b")
    db.commit()
    exported = rows(client.get("/api/scans/1/identity-groups/export.csv"))
    labels = {(row["duplicate_group_status"], row["duplicate_group_status_label"]) for row in exported}
    assert labels == {
        ("LIKELY_DUPLICATE_GROUP", "Likely duplicate group"),
        ("POSSIBLE_DUPLICATE_GROUP_REVIEW", "Possible duplicate group — review"),
    }
    assert all("confirmed" not in label.lower() for _, label in labels)


def test_uom_summary_is_repeated_without_reinterpreting_group_status(client, db):
    add_scan(db); run = add_run(db)
    group = add_group(db, run, size=2, status="POSSIBLE_DUPLICATE_GROUP_REVIEW")
    group.same_uom_pair_count = 0; group.different_basis_pair_count = 1
    db.commit()
    exported = rows(client.get("/api/scans/1/identity-groups/export.csv"))
    assert all(row["duplicate_group_status"] == "POSSIBLE_DUPLICATE_GROUP_REVIEW" for row in exported)
    assert all(row["different_basis_pair_count"] == "1" for row in exported)


def test_latest_and_explicit_completed_projection_selection(client, db):
    add_scan(db)
    older = add_run(db, suffix="a", created_at=NOW); add_group(db, older, size=2, key="a")
    latest = add_run(db, suffix="b", created_at=NOW + timedelta(minutes=1)); add_group(db, latest, size=4, key="b")
    db.commit()
    assert len(rows(client.get("/api/scans/1/identity-groups/export.csv"))) == 4
    explicit = client.get(f"/api/scans/1/identity-groups/export.csv?projection_run_id={older.id}")
    assert len(rows(explicit)) == 2
    assert {row["projection_run_id"] for row in rows(explicit)} == {str(older.id)}


def test_wrong_scan_unknown_and_failed_projection_are_rejected_safely(client, db):
    add_scan(db, 1); add_scan(db, 2)
    other = add_run(db, scan_id=2, suffix="a")
    failed = add_run(db, scan_id=1, suffix="b", status="FAILED")
    db.commit()
    assert client.get(f"/api/scans/1/identity-groups/export.csv?projection_run_id={other.id}").status_code == 404
    assert client.get("/api/scans/1/identity-groups/export.csv?projection_run_id=999").status_code == 404
    assert client.get(f"/api/scans/1/identity-groups/export.csv?projection_run_id={failed.id}").status_code == 409


def test_no_snapshot_returns_404_without_projection_or_scoring(client, db, monkeypatch):
    add_scan(db); db.commit()
    monkeypatch.setattr(identity_group_projection, "project_identity_groups", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("G1 called")))
    monkeypatch.setattr(identity_group_snapshot_service, "project_identity_groups", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("G2 called")))
    response = client.get("/api/scans/1/identity-groups/export.csv")
    assert response.status_code == 404
    assert response.json()["detail"] == "No completed identity projection snapshot exists for scan"


def test_diagnostics_are_absent_from_group_csv_and_complete_in_diagnostic_csv(client, db):
    add_scan(db); run = add_run(db); add_group(db, run, size=2); diagnostic = add_diagnostic(db, run, size=21, status="DEFERRED_OVERSIZED_FAMILY")
    db.commit()
    group_rows = rows(client.get("/api/scans/1/identity-groups/export.csv"))
    diagnostic_rows = rows(client.get("/api/scans/1/identity-group-diagnostics/export.csv"))
    assert len(group_rows) == 2 and all("diagnostic_status" not in row for row in group_rows)
    assert len(diagnostic_rows) == 21
    assert {row["diagnostic_snapshot_id"] for row in diagnostic_rows} == {str(diagnostic.id)}
    assert [int(row["diagnostic_member_index"]) for row in diagnostic_rows] == list(range(21))


def test_formula_injection_is_neutralized_for_every_dangerous_prefix(client, db):
    add_scan(db); run = add_run(db); add_group(db, run, size=2, dangerous=True)
    db.commit()
    first = rows(client.get("/api/scans/1/identity-groups/export.csv"))[0]
    assert first["site_or_contract"] == "'=SITE"
    assert first["part_no"] == "'+PART"
    assert first["product_category"] == "'@CATEGORY"
    assert first["hsn_sac"] == "'-100"


def test_commas_quotes_and_newlines_round_trip_through_csv(client, db):
    add_scan(db); run = add_run(db)
    value = 'Valve, "quoted"\nsecond line'
    add_group(db, run, size=2, description=value)
    db.commit()
    assert rows(client.get("/api/scans/1/identity-groups/export.csv"))[0]["description"] == value


def test_group_and_diagnostic_headers_have_stable_exact_order(client, db):
    add_scan(db); run = add_run(db); add_group(db, run, size=2); add_diagnostic(db, run)
    db.commit()
    group_header = next(csv.reader(io.StringIO(client.get("/api/scans/1/identity-groups/export.csv").text)))
    diagnostic_header = next(csv.reader(io.StringIO(client.get("/api/scans/1/identity-group-diagnostics/export.csv").text)))
    assert group_header == IDENTITY_GROUP_EXPORT_FIELDS
    assert diagnostic_header == IDENTITY_DIAGNOSTIC_EXPORT_FIELDS


def test_db_member_insertion_order_does_not_change_export_order(client, db):
    add_scan(db); run = add_run(db); add_group(db, run, size=7, member_order=[6, 1, 5, 0, 4, 2, 3])
    db.commit()
    exported = rows(client.get("/api/scans/1/identity-groups/export.csv"))
    assert [int(row["group_member_index"]) for row in exported] == list(range(7))


def test_group_exports_make_zero_provider_calls(client, db, monkeypatch):
    add_scan(db); run = add_run(db); add_group(db, run, size=2); add_diagnostic(db, run); db.commit()
    calls = []
    monkeypatch.setattr(GroqLLMProvider, "complete_json", lambda *_args, **_kwargs: calls.append(True))
    assert client.get("/api/scans/1/identity-groups/export.csv").status_code == 200
    assert client.get("/api/scans/1/identity-group-diagnostics/export.csv").status_code == 200
    assert calls == []


def test_existing_pair_export_bytes_are_unchanged_by_group_exports(client, db):
    add_scan(db); run = add_run(db); add_group(db, run, size=2); db.commit()
    before = client.get("/api/scans/1/export").content
    client.get("/api/scans/1/identity-groups/export.csv")
    client.get("/api/scans/1/identity-group-diagnostics/export.csv")
    assert client.get("/api/scans/1/export").content == before


def test_each_export_uses_three_bounded_selects_including_scan_check(client, db):
    add_scan(db); run = add_run(db)
    for index in range(40): add_group(db, run, size=2, key=chr(0x100 + index))
    add_diagnostic(db, run, size=21, status="DEFERRED_OVERSIZED_FAMILY"); db.commit()
    selects = []
    def count(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"): selects.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", count)
    try:
        assert client.get("/api/scans/1/identity-groups/export.csv").status_code == 200
        group_count = len(selects); selects.clear()
        assert client.get("/api/scans/1/identity-group-diagnostics/export.csv").status_code == 200
        diagnostic_count = len(selects)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count)
    assert (group_count, diagnostic_count) == (3, 3)


def test_export_filenames_are_deterministic_and_business_readable(client, db):
    add_scan(db); run = add_run(db); add_group(db, run, size=2); db.commit()
    assert client.get("/api/scans/1/identity-groups/export.csv").headers["content-disposition"] == 'attachment; filename="scan-1-identity-groups.csv"'
    assert client.get("/api/scans/1/identity-group-diagnostics/export.csv").headers["content-disposition"] == 'attachment; filename="scan-1-identity-group-diagnostics.csv"'
