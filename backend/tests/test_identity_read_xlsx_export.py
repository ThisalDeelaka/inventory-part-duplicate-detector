import csv
import dataclasses
import io

import pytest
from openpyxl import load_workbook
from sqlalchemy import text

from app.db.models import DuplicateScan
from app.identity_read.adapters import adapt_g2_v2_to_identity_read_snapshot
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.llm.groq_provider import GroqLLMProvider
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    VersionedIdentityGroupReviewService,
)
from app.services.identity_read_service import (
    IdentityReadAuthorityInconsistent,
    IdentityReadService,
)
from app.services.identity_read_xlsx_export_service import (
    ALL_COLUMNS,
    GROUP_COLUMNS,
    WORKBOOK_NOTICE,
    authority_selected_system_groups_to_xlsx,
    reason_for_group_status,
)
from test_group_first_backend_inversion import authoritative_group, review_scan
from test_identity_read_contracts import all_records, v2_source


def _workbook(content):
    return load_workbook(io.BytesIO(content), data_only=False)


def _rows(sheet):
    return list(sheet.iter_rows(min_row=2, values_only=True))


def _add_scan(db, scan_id=21):
    db.add(DuplicateScan(
        id=scan_id,
        scan_name="XLSX synthetic",
        threshold=60,
        status="COMPLETED",
        model_version="deterministic-v1",
        selected_fields="[]",
    ))
    db.commit()


def test_xlsx1_to_xlsx15_workbook_contract_membership_merges_and_review(db, client):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    refs = tuple(member.stable_record_reference for member in group.members)
    VersionedIdentityGroupReviewService(db).create_review(
        scan_id=scan.id,
        key=group.versioned_group_key,
        decision_type=GroupReviewDecision.UNSURE,
        reviewer="xlsx-reviewer",
        submitted_members=refs,
    )

    csv_response = client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.csv"
    )
    response = client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"] == (
        f'attachment; filename="scan-{scan.id}-system-groups.xlsx"'
    )
    workbook = _workbook(response.content)
    assert workbook.sheetnames == ["Summary", "Duplicate Groups", "Group Data"]

    summary = {
        row[0].value: row[1].value
        for row in workbook["Summary"].iter_rows(min_row=2, max_col=2)
    }
    assert summary["Notice"] == WORKBOOK_NOTICE
    assert summary["Authority"] == "System-generated / analytical"
    assert summary["Human confirmation"] == "Not implied"
    assert summary["Input record count"] == snapshot.canonical_record_count
    assert summary["Group count"] == snapshot.group_count

    grouped = workbook["Duplicate Groups"]
    flat = workbook["Group Data"]
    assert tuple(cell.value for cell in grouped[1]) == ALL_COLUMNS
    assert tuple(cell.value for cell in flat[1]) == ALL_COLUMNS
    assert grouped.freeze_panes == "A2" and flat.freeze_panes == "A2"
    assert flat.auto_filter.ref == f"A1:T{flat.max_row}"

    csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    flat_rows = _rows(flat)
    assert len(flat_rows) == len(csv_rows) == group.member_count
    assert {row[1] for row in flat_rows} == {row["group_key"] for row in csv_rows}
    assert {
        str(row[-1]).split(" / ")[-1] for row in flat_rows
    } == {row["stable_record_reference"] for row in csv_rows}
    assert {row[0] for row in flat_rows} == {"DG-000001"}
    assert {row[4] for row in flat_rows} == {group.member_count}
    assert {row[5] for row in flat_rows} == {"Reviewed - unsure"}
    assert "human review is required" in flat_rows[0][3]
    assert "human-confirmed" not in flat_rows[0][3]

    expected_end = 1 + group.member_count
    for column in "ABCDEF":
        assert f"{column}2:{column}{expected_end}" in {
            str(item) for item in grouped.merged_cells.ranges
        }
    assert all(item.min_col <= len(GROUP_COLUMNS) for item in grouped.merged_cells.ranges)


def test_xlsx9_xlsx13_repeated_generation_is_semantically_deterministic(db):
    scan = review_scan(db)
    generated = [
        _workbook(authority_selected_system_groups_to_xlsx(db, scan.id))
        for _ in range(3)
    ]
    semantic_rows = [
        list(book["Group Data"].iter_rows(values_only=True)) for book in generated
    ]
    assert semantic_rows[0] == semantic_rows[1] == semantic_rows[2]
    assert generated[0].sheetnames == generated[1].sheetnames == generated[2].sheetnames
    merged_ranges = [
        tuple(sorted(str(item) for item in book["Duplicate Groups"].merged_cells.ranges))
        for book in generated
    ]
    assert merged_ranges[0] == merged_ranges[1] == merged_ranges[2]
    assert semantic_rows[0][1][0] == "DG-000001"
    assert semantic_rows[0][1][3] == reason_for_group_status(
        "POSSIBLE_DUPLICATE_GROUP_REVIEW"
    )


def test_xlsx7_three_member_group_merges_full_group_range_only(db, monkeypatch):
    _add_scan(db)
    snapshot = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    monkeypatch.setattr(
        IdentityReadService,
        "load_identity_read_snapshot",
        lambda _self, _scan_id: snapshot,
    )
    sheet = _workbook(
        authority_selected_system_groups_to_xlsx(db, 21)
    )["Duplicate Groups"]
    ranges = {str(item) for item in sheet.merged_cells.ranges}
    assert {f"{column}2:{column}4" for column in "ABCDEF"} == ranges


def test_xlsx21_formula_like_inventory_values_remain_literal_and_source_immutable(
    db, client, monkeypatch
):
    _add_scan(db)
    original = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    original_member = original.groups[0].members[0]
    changed_member = dataclasses.replace(
        original_member,
        part_no="=1+1",
        description="+ABC",
        contract="-XYZ",
        uom="@PART",
    )
    changed_group = dataclasses.replace(
        original.groups[0],
        members=(changed_member,) + original.groups[0].members[1:],
    )
    snapshot = dataclasses.replace(original, groups=(changed_group,))
    monkeypatch.setattr(
        IdentityReadService,
        "load_identity_read_snapshot",
        lambda _self, _scan_id: snapshot,
    )

    response = client.get("/api/scans/21/identity-read/system-groups/export.xlsx")
    assert response.status_code == 200
    row = _workbook(response.content)["Group Data"][2]
    for index, expected in ((6, "=1+1"), (7, "+ABC"), (8, "-XYZ"), (9, "@PART")):
        assert row[index].value == expected
        assert row[index].data_type == "s"
    assert original_member.part_no != changed_member.part_no


def test_xlsx16_failed_and_xlsx17_incomplete_orchestration_fail_closed(
    db, client
):
    for status in ("FAILED", "RUNNING"):
        scan = review_scan(db)
        db.execute(text(
            "UPDATE scan_orchestration_run SET status = :status "
            "WHERE scan_id = :scan_id"
        ), {"status": status, "scan_id": scan.id})
        db.commit()
        response = client.get(
            f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
        )
        assert response.status_code == 409


def test_xlsx18_corrupt_authority_fails_closed(db, client, monkeypatch):
    scan = review_scan(db)
    monkeypatch.setattr(
        IdentityReadService,
        "load_identity_read_snapshot",
        lambda _self, _scan_id: (_ for _ in ()).throw(
            IdentityReadAuthorityInconsistent("corrupt persisted authority")
        ),
    )
    response = client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    )
    assert response.status_code == 422


def test_authority_missing_projection_is_not_ready(db, client):
    scan = review_scan(db)
    db.execute(text(
        "UPDATE scan_orchestration_stage_result SET source_run_reference = NULL "
        "WHERE orchestration_run_id = (SELECT id FROM scan_orchestration_run "
        "WHERE scan_id = :scan_id) AND stage_id = 'G2_V2_PROJECTION'"
    ), {"scan_id": scan.id})
    db.commit()
    response = client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    )
    assert response.status_code == 409
    assert "G2_V2_PROJECTION_MISSING" in response.json()["detail"]


def test_xlsx19_cross_scan_membership_is_not_combined(db, client):
    first = review_scan(db)
    second = review_scan(db)
    _, first_group = authoritative_group(db, first)
    _, second_group = authoritative_group(db, second)
    workbook = _workbook(client.get(
        f"/api/scans/{second.id}/identity-read/system-groups/export.xlsx"
    ).content)
    canonical_ids = {row[1] for row in _rows(workbook["Group Data"])}
    assert canonical_ids == {
        serialize_versioned_identity_group_key(second_group.versioned_group_key)
    }
    assert serialize_versioned_identity_group_key(
        first_group.versioned_group_key
    ) not in canonical_ids


def test_xlsx20_provider_calls_are_zero(db, client, monkeypatch):
    scan = review_scan(db)

    async def forbidden_provider_call(*_args, **_kwargs):
        raise AssertionError("XLSX export must not call an LLM provider")

    monkeypatch.setattr(GroqLLMProvider, "complete_json", forbidden_provider_call)
    assert client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    ).status_code == 200


def test_xlsx22_xlsx23_xlsx26_has_no_truth_secrets_formulas_or_writeback(db, client):
    scan = review_scan(db)
    workbook = _workbook(client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    ).content)
    forbidden = ("truth", "ground truth", "api key", "credential", "password", "merge target")
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                assert cell.data_type != "f"
                if isinstance(cell.value, str):
                    assert not any(term in cell.value.lower() for term in forbidden)
