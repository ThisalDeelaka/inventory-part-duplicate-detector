import csv
import dataclasses
import io
import json
from datetime import datetime

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import text

from app.db.models import DuplicateScan
from app.identity_read.adapters import adapt_g2_v2_to_identity_read_snapshot
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.llm.groq_provider import GroqLLMProvider
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    VersionedIdentityGroupReviewService,
)
from app.services.identity_read_export_service import authority_selected_system_group_rows
from app.services.identity_read_service import (
    IdentityReadAuthorityInconsistent,
    IdentityReadService,
)
from app.services.identity_read_xlsx_export_service import (
    DETAILED_DATA_COLUMNS,
    GROUP_INDEX_COLUMNS,
    REVIEW_GROUP_COLUMNS,
    SHEET_ORDER,
    TECHNICAL_REFERENCE_COLUMNS,
    WORKBOOK_NOTICE,
    authority_selected_system_groups_to_xlsx,
    concise_reason_for_group_status,
    reason_for_group_status,
)
from test_group_first_backend_inversion import authoritative_group, review_scan
from test_identity_read_contracts import all_records, v2_source


def _workbook(content):
    return load_workbook(io.BytesIO(content), data_only=False)


def _rows(sheet):
    return list(sheet.iter_rows(min_row=2, values_only=True))


def _dict_rows(sheet):
    headers = tuple(cell.value for cell in sheet[1])
    return [dict(zip(headers, row, strict=True)) for row in _rows(sheet)]


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


def test_client_workbook_contract_semantics_merges_and_review(db, client):
    scan = review_scan(db)
    snapshot, group = authoritative_group(db, scan)
    refs = tuple(member.stable_record_reference for member in group.members)
    long_comment = "Review deferred while the client validates equipment context. " * 4
    VersionedIdentityGroupReviewService(db).create_review(
        scan_id=scan.id,
        key=group.versioned_group_key,
        decision_type=GroupReviewDecision.UNSURE,
        reviewer="xlsx-reviewer",
        submitted_members=refs,
        comment=long_comment,
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
    assert tuple(workbook.sheetnames) == SHEET_ORDER
    assert workbook.active.title == "Overview"

    overview = workbook["Overview"]
    overview_text = " ".join(
        str(cell.value) for row in overview.iter_rows() for cell in row
        if cell.value is not None
    )
    assert "Inventory Duplicate Review Report" in overview_text
    assert "Candidate groups generated for human review" in overview_text
    assert "SCAN INFORMATION" in overview_text
    assert "FINDINGS AT A GLANCE" in overview_text
    assert "ADDITIONAL FINDINGS REQUIRING ATTENTION" in overview_text
    assert "HUMAN REVIEW PROGRESS" in overview_text
    assert "HOW TO USE THIS WORKBOOK" in overview_text
    assert "REPORT DETAILS / TECHNICAL FOOTER" in overview_text
    assert WORKBOOK_NOTICE in overview_text
    assert overview["E6"].value == "Records Analysed"
    assert overview["E7"].value == snapshot.canonical_record_count
    assert overview["A15"].value == "Total Candidate Groups"
    assert overview["A16"].value == snapshot.group_count
    assert overview["A29"].value == "Reviewed"
    assert overview["G29"].value == "1 of 1"
    assert overview["A33"].value == "Deferred by Reviewer"
    assert overview["G33"].value == 1
    assert "Deferred / Unreviewed" not in overview_text
    assert overview["A45"].value == "Scan ID"
    assert overview["C45"].value == scan.id
    occupied = set()
    for merged in overview.merged_cells.ranges:
        for row_number in range(merged.min_row, merged.max_row + 1):
            for column_number in range(merged.min_col, merged.max_col + 1):
                coordinate = (row_number, column_number)
                assert coordinate not in occupied
                occupied.add(coordinate)

    review = workbook["Review Groups"]
    index = workbook["Group Index"]
    flat = workbook["Detailed Data"]
    technical = workbook["Technical Reference"]
    assert tuple(cell.value for cell in review[1]) == REVIEW_GROUP_COLUMNS
    assert tuple(cell.value for cell in index[1]) == GROUP_INDEX_COLUMNS
    assert tuple(cell.value for cell in flat[1]) == DETAILED_DATA_COLUMNS
    assert tuple(cell.value for cell in technical[1]) == TECHNICAL_REFERENCE_COLUMNS
    assert all(sheet.freeze_panes == "A2" for sheet in (review, index, flat, technical))
    assert not flat.merged_cells.ranges
    assert flat.auto_filter.ref is None
    assert flat.tables["SystemGroupData"].ref == (
        f"A1:{get_column_letter(len(DETAILED_DATA_COLUMNS))}{flat.max_row}"
    )

    csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    detail_rows = _dict_rows(flat)
    tech_rows = _dict_rows(technical)
    assert len(detail_rows) == len(tech_rows) == len(csv_rows) == group.member_count
    assert {row["Group"] for row in detail_rows} == {"CG-000001"}
    assert {row["Review Status"] for row in detail_rows} == {"Review Deferred"}
    assert {row["Evidence"] for row in detail_rows} == {"Review Evidence"}
    assert {row["Human Decision"] for row in detail_rows} == {
        "Deferred for later review"
    }
    assert {row["Human Comment"] for row in detail_rows} == {long_comment}
    assert flat["G"][1].alignment.wrap_text is True
    assert max(flat.row_dimensions[row].height for row in range(2, flat.max_row + 1)) <= 42

    canonical = serialize_versioned_identity_group_key(group.versioned_group_key)
    assert {row["Canonical Group ID"] for row in tech_rows} == {canonical}
    assert {row["Stable Record Reference"] for row in tech_rows} == {
        row["stable_record_reference"] for row in csv_rows
    }
    assert {row["Source Row"] for row in tech_rows} == {
        int(row["source_row_reference"]) for row in csv_rows
    }
    for primary in (review, index, flat):
        assert "Canonical Group ID" not in tuple(cell.value for cell in primary[1])
        assert "Stable Record Reference" not in tuple(cell.value for cell in primary[1])

    expected_merges = {
        f"{letter}2:{letter}{group.member_count + 1}" for letter in "ABCDEFG"
    }
    assert {str(item) for item in review.merged_cells.ranges} == expected_merges
    assert not any(
        merged.min_col >= 8 for merged in review.merged_cells.ranges
    )
    assert [row["Member #"] for row in _dict_rows(review)] == list(
        range(1, group.member_count + 1)
    )


def test_three_member_group_is_one_visual_block_with_distinct_members(db, monkeypatch):
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
    workbook = _workbook(authority_selected_system_groups_to_xlsx(db, 21))
    sheet = workbook["Review Groups"]
    member_count = snapshot.groups[0].member_count
    assert member_count >= 3
    assert {str(item) for item in sheet.merged_cells.ranges} == {
        f"{letter}2:{letter}{member_count + 1}" for letter in "ABCDEFG"
    }
    rows = _dict_rows(sheet)
    assert len(rows) == member_count
    assert [row["Member #"] for row in rows] == list(range(1, member_count + 1))
    assert len({row["Part Number"] for row in rows}) == member_count
    assert not workbook["Detailed Data"].merged_cells.ranges


def test_unreviewed_candidate_requires_human_review_and_reason_is_concise(db, client):
    scan = review_scan(db)
    workbook = _workbook(client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    ).content)
    rows = _dict_rows(workbook["Group Index"])
    assert {row["Review Status"] for row in rows} == {"Requires Human Review"}
    assert {row["Human Decision"] for row in rows} == {"Not yet reviewed"}
    assert {row["Why Suggested"] for row in rows} == {
        concise_reason_for_group_status("POSSIBLE_DUPLICATE_GROUP_REVIEW")
    }
    overview = workbook["Overview"]
    assert overview["A29"].value == "Reviewed"
    assert overview["G29"].value == "0 of 1"
    assert overview["A30"].value == "Awaiting Review"
    assert overview["G30"].value == 1
    assert overview["A33"].value == "Deferred by Reviewer"
    assert overview["G33"].value == 0
    assert overview["E24"].value == "Deferred Families"


def test_repeated_generation_is_semantically_and_visually_deterministic(db):
    scan = review_scan(db)
    generated = [
        _workbook(authority_selected_system_groups_to_xlsx(db, scan.id))
        for _ in range(3)
    ]
    for sheet_name in ("Review Groups", "Group Index", "Detailed Data", "Technical Reference"):
        values = [list(book[sheet_name].iter_rows(values_only=True)) for book in generated]
        assert values[0] == values[1] == values[2]
    merges = [
        tuple(sorted(str(item) for item in book["Review Groups"].merged_cells.ranges))
        for book in generated
    ]
    assert merges[0] == merges[1] == merges[2]
    assert generated[0]["Technical Reference"]["I2"].value == reason_for_group_status(
        "POSSIBLE_DUPLICATE_GROUP_REVIEW"
    )


def test_overview_uses_persisted_scan_metadata_and_ui_ordered_condition_labels(db):
    scan = review_scan(db)
    scan.started_at = datetime(2026, 9, 14, 8, 0, 0)
    scan.completed_at = datetime(2026, 9, 14, 12, 34, 56)
    scan.total_records = 5327
    scan.selected_fields = json.dumps(["UNIT_MEAS", "CONTRACT"])
    db.commit()

    overview = _workbook(
        authority_selected_system_groups_to_xlsx(db, scan.id)
    )["Overview"]
    assert overview["A7"].value == "14 Sep 2026, 12:34"
    assert overview["A11"].value == "Site • Inventory UOM"
    assert overview["E7"].value == 5327
    assert overview["E11"].value == "IFS APP Test"

    scan.completed_at = None
    db.commit()
    overview = _workbook(
        authority_selected_system_groups_to_xlsx(db, scan.id)
    )["Overview"]
    assert overview["A7"].value == "14 Sep 2026, 08:00"

    for selected_fields, expected in (
        (["UNIT_MEAS"], "Inventory UOM"),
        ([], "None selected"),
        (["FUTURE_CLIENT_FIELD"], "Future Client Field"),
    ):
        scan.selected_fields = json.dumps(selected_fields)
        db.commit()
        overview = _workbook(
            authority_selected_system_groups_to_xlsx(db, scan.id)
        )["Overview"]
        assert overview["A11"].value == expected
        assert "Site" not in str(overview["A11"].value)


def test_overview_findings_match_authoritative_projection_counts(db):
    scan = review_scan(db)
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan.id)
    overview = _workbook(
        authority_selected_system_groups_to_xlsx(db, scan.id)
    )["Overview"]
    findings = {
        overview["A15"].value: overview["A16"].value,
        overview["C15"].value: overview["C16"].value,
        overview["F15"].value: overview["F16"].value,
        overview["A19"].value: overview["A20"].value,
        overview["E19"].value: overview["E20"].value,
        overview["A24"].value: overview["A25"].value,
        overview["E24"].value: overview["E25"].value,
    }
    assert findings == {
        "Total Candidate Groups": snapshot.group_count,
        "Stronger Evidence": snapshot.likely_group_count,
        "Review Evidence": snapshot.review_group_count,
        "Conflicting Families": snapshot.conflict_count,
        "Deferred Families": snapshot.deferred_count,
        "Records in Candidate Groups": sum(
            group.member_count for group in snapshot.groups
        ),
        "Unassigned Records": snapshot.unassigned_count,
    }


def test_xlsx_export_does_not_mutate_request_or_group_semantics(db):
    scan = review_scan(db)
    before = IdentityReadService(db).load_identity_read_snapshot(scan.id)
    selected_fields = scan.selected_fields
    authority_selected_system_groups_to_xlsx(db, scan.id)
    db.expire_all()
    after = IdentityReadService(db).load_identity_read_snapshot(scan.id)

    assert db.get(DuplicateScan, scan.id).selected_fields == selected_fields
    assert after.snapshot_fingerprint == before.snapshot_fingerprint
    assert [
        (group.status, tuple(member.stable_record_reference for member in group.members))
        for group in after.groups
    ] == [
        (group.status, tuple(member.stable_record_reference for member in group.members))
        for group in before.groups
    ]
    assert after.conflicts == before.conflicts
    assert after.deferred_work_units == before.deferred_work_units
    assert after.unassigned_records == before.unassigned_records


def test_data_level_projection_is_logically_equivalent(db):
    scan = review_scan(db)
    _, raw_rows = authority_selected_system_group_rows(db, scan.id)
    workbook = _workbook(authority_selected_system_groups_to_xlsx(db, scan.id))
    details = _dict_rows(workbook["Detailed Data"])
    technical = _dict_rows(workbook["Technical Reference"])
    assert len(raw_rows) == len(details) == len(technical)
    labels_by_key = {}
    for raw in raw_rows:
        labels_by_key.setdefault(
            raw["group_key"], f"CG-{len(labels_by_key) + 1:06d}"
        )
    for raw, detail, tech in zip(raw_rows, details, technical, strict=True):
        assert detail["Group"] == labels_by_key[raw["group_key"]]
        assert tech["Group"] == detail["Group"]
        assert tech["Canonical Group ID"] == raw["group_key"]
        assert tech["Stable Record Reference"] == raw["stable_record_reference"]
        assert tech["Source Row"] == raw["source_row_reference"]
        assert tech["Part Number"] == raw["part_no"] == detail["Part Number"]
        assert detail["Description"] == raw["description"]
        assert detail["Site"] == raw["site_or_contract"]
        assert detail["Inventory UOM"] == raw["uom"]
        assert detail["Part Type"] == raw["part_type"]
        assert detail["Commodity Group 01"] == raw["commodity_group_01"]
        assert detail["Commodity Group 02"] == raw["commodity_group_02"]
        assert detail["Safety Code"] == raw["safety_code"]
        assert detail["Accounting Group"] == raw["accounting_group"]
        assert detail["Product Code"] == raw["product_code"]
        assert detail["Product Family"] == raw["product_family"]
        assert detail["Product Category"] == raw["product_category"]
        assert detail["HSN/SAC Code"] == raw["hsn_sac"]


def test_empty_state_is_friendly_and_structurally_valid(db, monkeypatch):
    _add_scan(db)
    snapshot = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    empty = dataclasses.replace(
        snapshot, groups=(), group_count=0, likely_group_count=0,
        review_group_count=0,
    )
    monkeypatch.setattr(
        IdentityReadService,
        "load_identity_read_snapshot",
        lambda _self, _scan_id: empty,
    )
    workbook = _workbook(authority_selected_system_groups_to_xlsx(db, 21))
    assert tuple(workbook.sheetnames) == SHEET_ORDER
    assert workbook["Overview"]["A16"].value == 0
    assert workbook["Review Groups"]["A2"].value == (
        "No candidate groups were generated for this scan."
    )
    assert workbook["Group Index"].max_row == 1
    assert workbook["Detailed Data"].max_row == 1
    assert workbook["Technical Reference"].max_row == 1


def test_formula_like_inventory_values_remain_literal_and_source_immutable(
    db, client, monkeypatch
):
    _add_scan(db)
    original = adapt_g2_v2_to_identity_read_snapshot(
        v2_source(), all_records(), source_projection_run_id=202,
        source_orchestration_run_id=9,
    )
    original_member = original.groups[0].members[0]
    changed_member = dataclasses.replace(
        original_member, part_no="=1+1", description="+ABC", contract="-XYZ", uom="@PART"
    )
    changed_group = dataclasses.replace(
        original.groups[0], members=(changed_member,) + original.groups[0].members[1:]
    )
    snapshot = dataclasses.replace(original, groups=(changed_group,))
    monkeypatch.setattr(
        IdentityReadService,
        "load_identity_read_snapshot",
        lambda _self, _scan_id: snapshot,
    )
    response = client.get("/api/scans/21/identity-read/system-groups/export.xlsx")
    assert response.status_code == 200
    row = _workbook(response.content)["Detailed Data"][2]
    for index, expected in ((7, "=1+1"), (8, "+ABC"), (9, "-XYZ"), (10, "@PART")):
        assert row[index].value == expected
        assert row[index].data_type == "s"
    assert original_member.part_no != changed_member.part_no


def test_failed_and_incomplete_orchestration_fail_closed(db, client):
    for status in ("FAILED", "RUNNING"):
        scan = review_scan(db)
        db.execute(text(
            "UPDATE scan_orchestration_run SET status = :status WHERE scan_id = :scan_id"
        ), {"status": status, "scan_id": scan.id})
        db.commit()
        assert client.get(
            f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
        ).status_code == 409


def test_corrupt_authority_fails_closed(db, client, monkeypatch):
    scan = review_scan(db)
    monkeypatch.setattr(
        IdentityReadService,
        "load_identity_read_snapshot",
        lambda _self, _scan_id: (_ for _ in ()).throw(
            IdentityReadAuthorityInconsistent("corrupt persisted authority")
        ),
    )
    assert client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    ).status_code == 422


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


def test_cross_scan_membership_is_not_combined(db, client):
    first = review_scan(db)
    second = review_scan(db)
    _, first_group = authoritative_group(db, first)
    _, second_group = authoritative_group(db, second)
    workbook = _workbook(client.get(
        f"/api/scans/{second.id}/identity-read/system-groups/export.xlsx"
    ).content)
    canonical_ids = {
        row["Canonical Group ID"]
        for row in _dict_rows(workbook["Technical Reference"])
    }
    assert canonical_ids == {
        serialize_versioned_identity_group_key(second_group.versioned_group_key)
    }
    assert serialize_versioned_identity_group_key(
        first_group.versioned_group_key
    ) not in canonical_ids


def test_provider_calls_are_zero(db, client, monkeypatch):
    scan = review_scan(db)

    async def forbidden_provider_call(*_args, **_kwargs):
        raise AssertionError("XLSX export must not call an LLM provider")

    monkeypatch.setattr(GroqLLMProvider, "complete_json", forbidden_provider_call)
    assert client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    ).status_code == 200


def test_no_unsupported_claims_secrets_formulas_or_writeback(db, client):
    scan = review_scan(db)
    workbook = _workbook(client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.xlsx"
    ).content)
    forbidden = (
        "ground truth", "api key", "credential", "password", "merge target",
        "likely duplicate", "confirmed duplicate", "high-confidence duplicate",
        "accuracy", "probability", "confidence %",
    )
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                assert cell.data_type != "f"
                if isinstance(cell.value, str):
                    assert not any(term in cell.value.lower() for term in forbidden)
