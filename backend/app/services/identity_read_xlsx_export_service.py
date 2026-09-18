"""Client-friendly XLSX representation of authority-selected System Groups."""

from __future__ import annotations

import json
from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.core.constants import FIELD_DEFINITIONS
from app.db.models import DuplicateScan
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.services.identity_group_review_service import VersionedIdentityGroupReviewService
from app.services.identity_group_presentation import (
    human_review_presentation,
    system_evidence_tier,
)
from app.services.identity_read_export_service import authority_selected_system_group_rows


WORKBOOK_NOTICE = (
    "Human review required. System-generated candidate groups are advisory "
    "and do not automatically merge or modify inventory records."
)
REPORT_CARRIED_OUT_BY = "IFS APP Test"
SHEET_ORDER = (
    "Overview",
    "Review Groups",
    "Group Index",
    "Detailed Data",
    "Technical Reference",
)
GROUP_INDEX_COLUMNS = (
    "Group", "Review Status", "Evidence", "Members", "Sites",
    "Why Suggested", "Human Decision", "Human Comment",
)
REVIEW_GROUP_COLUMNS = (
    "Group", "Review Status", "Evidence", "Group Sites", "Why Suggested",
    "Human Decision", "Human Comment", "Member #", "Part Number",
    "Description", "Site", "UOM", "Part Type", "Commodity Group 01",
    "Commodity Group 02", "Safety Code", "Accounting Group", "Product Code",
    "Product Family", "Product Category", "HSN/SAC Code",
)
DETAILED_DATA_COLUMNS = (
    "Group", "Review Status", "Evidence", "Members", "Group Sites",
    "Human Decision", "Human Comment", "Part Number", "Description", "Site",
    "Inventory UOM", "Part Type", "Commodity Group 01", "Commodity Group 02",
    "Safety Code", "Accounting Group", "Product Code", "Product Family",
    "Product Category", "HSN/SAC Code",
)
TECHNICAL_REFERENCE_COLUMNS = (
    "Group", "Canonical Group ID", "Member #", "Part Number", "Source Row",
    "Stable Record Reference", "Projection Contract", "Source Projection Run",
    "Original System Reason",
)

# Backward-compatible imports now describe the corresponding client sheets.
GROUP_COLUMNS = GROUP_INDEX_COLUMNS
ALL_COLUMNS = DETAILED_DATA_COLUMNS

_SOURCE_COLUMNS = (
    "Part Number", "Description", "Site", "Inventory UOM", "Part Type",
    "Commodity Group 01", "Commodity Group 02", "Safety Code",
    "Accounting Group", "Product Code", "Product Family", "Product Category",
    "HSN/SAC Code",
)
_MEMBER_FIELD_BY_COLUMN = {
    "Part Number": "part_no",
    "Description": "description",
    "Site": "site_or_contract",
    "Inventory UOM": "uom",
    "Part Type": "part_type",
    "Commodity Group 01": "commodity_group_01",
    "Commodity Group 02": "commodity_group_02",
    "Safety Code": "safety_code",
    "Accounting Group": "accounting_group",
    "Product Code": "product_code",
    "Product Family": "product_family",
    "Product Category": "product_category",
    "HSN/SAC Code": "hsn_sac",
}
_REASONS = {
    "LIKELY_DUPLICATE_GROUP": (
        "Stronger deterministic evidence caused the system to suggest this group "
        "for human review."
    ),
    "POSSIBLE_DUPLICATE_GROUP_REVIEW": (
        "Deterministic review evidence caused the system to suggest this group; "
        "human review is required."
    ),
    "CONFLICT": (
        "Conflicting identity evidence prevents safe grouping; human review is required."
    ),
    "DEFERRED": (
        "Identity evaluation is incomplete or deferred; no same-identity conclusion is implied."
    ),
}
_SHORT_REASONS = {
    "LIKELY_DUPLICATE_GROUP": "Multiple deterministic identity signals support review.",
    "POSSIBLE_DUPLICATE_GROUP_REVIEW": (
        "Some identity signals match; manual assessment is needed."
    ),
    "CONFLICT": "Identity signals conflict; manual assessment is needed.",
    "DEFERRED": "Identity evaluation is incomplete; manual assessment is needed.",
}

_NAVY = "1F4E78"
_PALE_BLUE = "EAF3F8"
_PALE_GRAY = "F3F5F7"
_PALE_GOLD = "FFF2CC"
_PALE_GREEN = "E2F0D9"
_PALE_RED = "FCE4D6"
_PALE_PURPLE = "E4DFEC"
_WHITE = "FFFFFF"
_TEXT = "243746"
_HEADER_FILL = PatternFill("solid", fgColor=_NAVY)
_HEADER_FONT = Font(color=_WHITE, bold=True)
_GROUP_FILLS = (
    PatternFill("solid", fgColor=_PALE_BLUE),
    PatternFill("solid", fgColor=_PALE_GRAY),
)
_THIN_GRAY = Side(style="thin", color="B7C9D6")
_MEDIUM_BLUE = Side(style="medium", color="6C8FA5")
_BORDER = Border(
    left=_THIN_GRAY, right=_THIN_GRAY, top=_THIN_GRAY, bottom=_THIN_GRAY
)


def write_spreadsheet_safe_cell(cell, value) -> None:
    """Write business-controlled text literally, never as an Excel formula."""
    if value is None:
        cell.value = ""
        return
    if isinstance(value, (datetime, date)):
        value = value.isoformat()
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"


def reason_for_group_status(status: str) -> str:
    return _REASONS.get(
        status, "System-generated same-identity candidate requiring human review."
    )


def concise_reason_for_group_status(status: str) -> str:
    return _SHORT_REASONS.get(
        status, "System suggestion requires manual identity assessment."
    )


def _sites(member_rows) -> str:
    values = sorted({
        str(row.get("site_or_contract") or "").strip()
        for row in member_rows
        if str(row.get("site_or_contract") or "").strip()
    })
    return ", ".join(values) or "Not provided"


def _group_presentation(label: str, group, state: dict | None, member_rows) -> dict:
    review_state, human_decision = human_review_presentation(state)
    return {
        "label": label,
        "canonical_id": serialize_versioned_identity_group_key(group.versioned_group_key),
        "review_status": review_state,
        "evidence": system_evidence_tier(group.status.value),
        "members": group.member_count,
        "sites": _sites(member_rows),
        "why": concise_reason_for_group_status(group.status.value),
        "original_reason": reason_for_group_status(group.status.value),
        "human_decision": human_decision,
        "human_comment": (state or {}).get("comment") or "",
    }


def _source_values(row: dict) -> tuple:
    return tuple(row.get(_MEMBER_FIELD_BY_COLUMN[column]) for column in _SOURCE_COLUMNS)


def _write_row(sheet, row_number: int, values, *, wrap_columns=()) -> None:
    for column_number, value in enumerate(values, start=1):
        cell = sheet.cell(row=row_number, column=column_number)
        write_spreadsheet_safe_cell(cell, value)
        cell.border = _BORDER
        cell.alignment = Alignment(
            vertical="top", wrap_text=column_number in wrap_columns
        )


def _write_header(sheet, columns) -> None:
    _write_row(sheet, 1, columns, wrap_columns=range(1, len(columns) + 1))
    for cell in sheet[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 34
    sheet.sheet_view.showGridLines = False


def _set_widths(sheet, widths) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _style_state(cell, review_status: str) -> None:
    color = {
        "Human Confirmed Same-Identity Group": _PALE_GREEN,
        "Human Rejected Candidate": _PALE_RED,
        "Review Deferred": _PALE_PURPLE,
    }.get(review_status, _PALE_GOLD)
    cell.fill = PatternFill("solid", fgColor=color)
    cell.font = Font(bold=True, color=_TEXT)


def _merge_and_write(sheet, cell_range: str, value, *, fill, font, alignment) -> None:
    sheet.merge_cells(cell_range)
    cell = sheet[cell_range.split(":", 1)[0]]
    write_spreadsheet_safe_cell(cell, value)
    cell.fill = fill
    cell.font = font
    cell.alignment = alignment
    for row in sheet[cell_range]:
        for item in row:
            item.fill = fill
            item.border = _BORDER


def _write_kpi(sheet, columns: str, label: str, value, *, start_row: int) -> None:
    start_col, end_col = columns.split(":")
    label_range = f"{start_col}{start_row}:{end_col}{start_row}"
    value_range = f"{start_col}{start_row + 1}:{end_col}{start_row + 2}"
    _merge_and_write(
        sheet, label_range, label,
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="center", vertical="center", wrap_text=True),
    )
    _merge_and_write(
        sheet, value_range, value,
        fill=PatternFill("solid", fgColor=_PALE_BLUE),
        font=Font(color=_NAVY, bold=True, size=18),
        alignment=Alignment(horizontal="center", vertical="center"),
    )


def selected_condition_labels(selected_fields_json: str) -> str:
    """Return persisted selected fields in stable UI order with safe fallbacks."""
    try:
        decoded = json.loads(selected_fields_json or "[]")
    except (TypeError, json.JSONDecodeError):
        decoded = []
    if not isinstance(decoded, list):
        decoded = []
    selected = {
        str(value).strip().upper() for value in decoded if str(value).strip()
    }
    labels_by_field = {
        item["field"]: item["display"]
        for item in FIELD_DEFINITIONS
        if not item["required"]
    }
    ordered = [
        labels_by_field[field]
        for field in labels_by_field
        if field in selected
    ]
    ordered.extend(
        field.replace("_", " ").title()
        for field in sorted(selected - labels_by_field.keys())
    )
    return " • ".join(ordered) or "None selected"


def format_scan_datetime(value) -> str:
    """Format a persisted scan timestamp without timezone conversion/invention."""
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return str(value or "Not available")


def _write_info_card(
    sheet, columns: str, label: str, value, *, start_row: int,
) -> None:
    start_col, end_col = columns.split(":")
    _merge_and_write(
        sheet, f"{start_col}{start_row}:{end_col}{start_row}", label,
        fill=PatternFill("solid", fgColor="5B7894"),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center", wrap_text=True),
    )
    _merge_and_write(
        sheet, f"{start_col}{start_row + 1}:{end_col}{start_row + 2}", value,
        fill=PatternFill("solid", fgColor=_WHITE),
        font=Font(color=_TEXT, bold=True, size=12),
        alignment=Alignment(horizontal="left", vertical="center", wrap_text=True),
    )


def _write_progress_row(sheet, row_number: int, label: str, value) -> None:
    _merge_and_write(
        sheet, f"A{row_number}:F{row_number}", label,
        fill=PatternFill("solid", fgColor=_WHITE),
        font=Font(color=_TEXT, bold=True),
        alignment=Alignment(vertical="center", wrap_text=True),
    )
    _merge_and_write(
        sheet, f"G{row_number}:H{row_number}", value,
        fill=PatternFill("solid", fgColor=_WHITE),
        font=Font(color=_NAVY, bold=True, size=12),
        alignment=Alignment(horizontal="right", vertical="center"),
    )


def _write_overview(workbook, scan, snapshot, review_states) -> None:
    sheet = workbook.active
    sheet.title = "Overview"
    sheet.sheet_view.showGridLines = False
    _set_widths(sheet, (14,) * 8)
    _merge_and_write(
        sheet, "A1:H2", "Inventory Duplicate Review Report",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True, size=20),
        alignment=Alignment(horizontal="center", vertical="center"),
    )
    _merge_and_write(
        sheet, "A3:H3", "Candidate groups generated for human review",
        fill=PatternFill("solid", fgColor="5B7894"),
        font=Font(color=_WHITE, italic=True, size=11),
        alignment=Alignment(horizontal="center", vertical="center"),
    )
    _merge_and_write(
        sheet, "A5:H5", "SCAN INFORMATION",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    executed_at = scan.completed_at or scan.started_at
    record_count = (
        scan.total_records
        if scan.total_records is not None
        else snapshot.canonical_record_count
    )
    _write_info_card(
        sheet, "A:D", "Scan Date", format_scan_datetime(executed_at), start_row=6,
    )
    _write_info_card(
        sheet, "E:H", "Records Analysed", record_count, start_row=6,
    )
    _write_info_card(
        sheet, "A:D", "Duplicate-checking Conditions",
        selected_condition_labels(scan.selected_fields), start_row=10,
    )
    _write_info_card(
        sheet, "E:H", "Carried Out By", REPORT_CARRIED_OUT_BY, start_row=10,
    )

    _merge_and_write(
        sheet, "A14:H14", "FINDINGS AT A GLANCE",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    records_in_groups = sum(group.member_count for group in snapshot.groups)
    for columns, label, value in (
        ("A:B", "Total Candidate Groups", snapshot.group_count),
        ("C:E", "Stronger Evidence", snapshot.likely_group_count),
        ("F:H", "Review Evidence", snapshot.review_group_count),
    ):
        _write_kpi(sheet, columns, label, value, start_row=15)
    for columns, label, value in (
        ("A:D", "Records in Candidate Groups", records_in_groups),
        ("E:H", "Unassigned Records", snapshot.unassigned_count),
    ):
        _write_kpi(sheet, columns, label, value, start_row=19)

    _merge_and_write(
        sheet, "A23:H23", "ADDITIONAL FINDINGS REQUIRING ATTENTION",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    _write_kpi(
        sheet, "A:D", "Conflicting Families", snapshot.conflict_count, start_row=24,
    )
    _write_kpi(
        sheet, "E:H", "Deferred Families", snapshot.deferred_count, start_row=24,
    )

    reviewed = sum(bool(state.get("reviewed")) for state in review_states.values())
    confirmed = sum(
        state.get("current_decision_type")
        in {"CONFIRM_ALL_AS_ONE", "CONFIRM_SELECTED", "SPLIT_PARTITIONS"}
        for state in review_states.values()
    )
    rejected = sum(
        state.get("current_decision_type") == "KEEP_ALL_SEPARATE"
        for state in review_states.values()
    )
    reviewer_deferred = sum(
        state.get("current_decision_type") == "UNSURE"
        for state in review_states.values()
    )
    awaiting_review = snapshot.group_count - reviewed
    _merge_and_write(
        sheet, "A28:H28", "HUMAN REVIEW PROGRESS",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    for row_number, (label, value) in enumerate((
        ("Reviewed", f"{reviewed} of {snapshot.group_count}"),
        ("Awaiting Review", awaiting_review),
        ("Confirmed", confirmed),
        ("Rejected", rejected),
        ("Deferred by Reviewer", reviewer_deferred),
    ), start=29):
        _write_progress_row(sheet, row_number, label, value)

    _merge_and_write(
        sheet, "A35:H36",
        WORKBOOK_NOTICE,
        fill=PatternFill("solid", fgColor=_PALE_GOLD),
        font=Font(color=_TEXT, bold=True),
        alignment=Alignment(horizontal="left", vertical="center", wrap_text=True),
    )
    _merge_and_write(
        sheet, "A38:H38", "HOW TO USE THIS WORKBOOK",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    _merge_and_write(
        sheet, "A39:H42",
        "1. Open Review Groups and inspect each suggested group.\n"
        "2. Record Confirm, Reject, or Defer decisions in the application using "
        "the source records and evidence.\n"
        "3. Use Detailed Data when additional record-level information is required.",
        fill=PatternFill("solid", fgColor=_WHITE),
        font=Font(color=_TEXT),
        alignment=Alignment(horizontal="left", vertical="top", wrap_text=True),
    )
    metadata = (
        ("Scan ID", snapshot.scan_id),
        ("Scan Name", scan.scan_name),
        ("Scan Status", scan.status),
        ("Projection Contract", snapshot.projection_contract.value),
        ("Source Projection Run", snapshot.source_projection_run_id),
    )
    _merge_and_write(
        sheet, "A44:H44", "REPORT DETAILS / TECHNICAL FOOTER",
        fill=PatternFill("solid", fgColor="5B7894"),
        font=Font(color=_WHITE, bold=True, size=10),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    for row_number, (label, value) in enumerate(metadata, start=45):
        _merge_and_write(
            sheet, f"A{row_number}:B{row_number}", label,
            fill=PatternFill("solid", fgColor=_PALE_GRAY),
            font=Font(color="5B7894", bold=True, size=9),
            alignment=Alignment(vertical="center"),
        )
        _merge_and_write(
            sheet, f"C{row_number}:H{row_number}", value,
            fill=PatternFill("solid", fgColor=_WHITE),
            font=Font(color="5B7894", size=9),
            alignment=Alignment(vertical="center", wrap_text=True),
        )
    sheet.freeze_panes = "A6"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    for row_number in (1, 2, 3, 7, 8, 11, 12, 16, 17, 20, 21, 25, 26, 35, 36):
        sheet.row_dimensions[row_number].height = 24
    sheet.row_dimensions[11].height = 32


def _write_group_index(sheet, groups) -> None:
    _write_header(sheet, GROUP_INDEX_COLUMNS)
    for row_number, item in enumerate(groups, start=2):
        p = item["presentation"]
        _write_row(
            sheet, row_number,
            (p["label"], p["review_status"], p["evidence"], p["members"],
             p["sites"], p["why"], p["human_decision"], p["human_comment"]),
            wrap_columns=(2, 5, 6, 7, 8),
        )
        _style_state(sheet.cell(row_number, 2), p["review_status"])
        sheet.row_dimensions[row_number].height = 36
    _set_widths(sheet, (16, 34, 20, 11, 22, 45, 32, 45))
    if groups:
        sheet.auto_filter.ref = f"A1:H{sheet.max_row}"


def _write_review_groups(sheet, groups) -> None:
    _write_header(sheet, REVIEW_GROUP_COLUMNS)
    current_row = 2
    if not groups:
        _merge_and_write(
            sheet, "A2:U3", "No candidate groups were generated for this scan.",
            fill=PatternFill("solid", fgColor=_PALE_GRAY),
            font=Font(color=_TEXT, italic=True),
            alignment=Alignment(horizontal="center", vertical="center"),
        )
    for group_index, item in enumerate(groups):
        p = item["presentation"]
        member_rows = item["member_rows"]
        start_row = current_row
        for member_number, member_row in enumerate(member_rows, start=1):
            source = _source_values(member_row)
            _write_row(
                sheet, current_row,
                (p["label"], p["review_status"], p["evidence"], p["sites"],
                 p["why"], p["human_decision"], p["human_comment"],
                 member_number, *source),
                wrap_columns=(2, 4, 5, 6, 7, 10),
            )
            sheet.row_dimensions[current_row].height = 42
            current_row += 1
        end_row = current_row - 1
        fill = _GROUP_FILLS[group_index % len(_GROUP_FILLS)]
        for row_number in range(start_row, end_row + 1):
            for column_number in range(1, len(REVIEW_GROUP_COLUMNS) + 1):
                cell = sheet.cell(row_number, column_number)
                cell.fill = fill
                cell.border = Border(
                    left=_THIN_GRAY, right=_THIN_GRAY,
                    top=_MEDIUM_BLUE if row_number == start_row else _THIN_GRAY,
                    bottom=_MEDIUM_BLUE if row_number == end_row else _THIN_GRAY,
                )
        for column_number in range(1, 8):
            if end_row > start_row:
                sheet.merge_cells(
                    start_row=start_row, start_column=column_number,
                    end_row=end_row, end_column=column_number,
                )
            sheet.cell(start_row, column_number).alignment = Alignment(
                vertical="center", wrap_text=True
            )
        _style_state(sheet.cell(start_row, 2), p["review_status"])
    _set_widths(
        sheet,
        (16, 34, 20, 22, 42, 32, 42, 10, 20, 48, 18, 14, 18, 22, 22,
         16, 20, 18, 20, 20, 18),
    )


def _write_detailed_data(sheet, groups) -> None:
    _write_header(sheet, DETAILED_DATA_COLUMNS)
    row_number = 2
    for item in groups:
        p = item["presentation"]
        for member_row in item["member_rows"]:
            _write_row(
                sheet, row_number,
                (p["label"], p["review_status"], p["evidence"], p["members"],
                 p["sites"], p["human_decision"], p["human_comment"],
                 *_source_values(member_row)),
                wrap_columns=(2, 5, 6, 7, 9),
            )
            _style_state(sheet.cell(row_number, 2), p["review_status"])
            sheet.row_dimensions[row_number].height = 36
            row_number += 1
    _set_widths(
        sheet,
        (16, 34, 20, 11, 22, 32, 42, 20, 48, 18, 16, 18, 22, 22, 16,
         20, 18, 20, 20, 18),
    )
    if sheet.max_row >= 2:
        table = Table(
            displayName="SystemGroupData",
            ref=f"A1:{get_column_letter(len(DETAILED_DATA_COLUMNS))}{sheet.max_row}",
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        sheet.add_table(table)


def _write_technical_reference(sheet, groups, snapshot) -> None:
    _write_header(sheet, TECHNICAL_REFERENCE_COLUMNS)
    row_number = 2
    for item in groups:
        p = item["presentation"]
        for member_number, member_row in enumerate(item["member_rows"], start=1):
            _write_row(
                sheet, row_number,
                (p["label"], p["canonical_id"], member_number,
                 member_row.get("part_no"), member_row.get("source_row_reference"),
                 member_row.get("stable_record_reference"),
                 snapshot.projection_contract.value,
                 snapshot.source_projection_run_id, p["original_reason"]),
                wrap_columns=(2, 6, 9),
            )
            row_number += 1
    _set_widths(sheet, (16, 38, 10, 20, 14, 42, 22, 22, 58))
    if groups:
        sheet.auto_filter.ref = f"A1:I{sheet.max_row}"


def authority_selected_system_groups_to_xlsx(db, scan_id: int) -> bytes:
    """Create a client workbook from the unchanged System Group projection."""
    snapshot, export_rows = authority_selected_system_group_rows(db, scan_id)
    scan = db.get(DuplicateScan, scan_id)
    review_states = VersionedIdentityGroupReviewService(db).current_states_for_snapshot(
        snapshot
    )
    rows_by_group = {}
    for row in export_rows:
        rows_by_group.setdefault(row["group_key"], []).append(row)

    groups = []
    for group_index, group in enumerate(snapshot.groups, start=1):
        canonical_id = serialize_versioned_identity_group_key(group.versioned_group_key)
        member_rows = tuple(rows_by_group.get(canonical_id, ()))
        groups.append({
            "presentation": _group_presentation(
                f"CG-{group_index:06d}", group,
                review_states.get(canonical_id), member_rows,
            ),
            "member_rows": member_rows,
        })

    workbook = Workbook()
    _write_overview(workbook, scan, snapshot, review_states)
    review_groups = workbook.create_sheet("Review Groups")
    group_index = workbook.create_sheet("Group Index")
    detailed_data = workbook.create_sheet("Detailed Data")
    technical = workbook.create_sheet("Technical Reference")
    _write_review_groups(review_groups, groups)
    _write_group_index(group_index, groups)
    _write_detailed_data(detailed_data, groups)
    _write_technical_reference(technical, groups, snapshot)
    workbook.active = 0

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
