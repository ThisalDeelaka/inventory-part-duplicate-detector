"""Human-readable XLSX representation of authority-selected System Groups."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.db.models import DuplicateScan
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.services.identity_group_review_service import (
    VersionedIdentityGroupReviewService,
)
from app.services.identity_read_export_service import (
    authority_selected_reviewed_identity_rows,
    authority_selected_system_group_rows,
)


WORKBOOK_NOTICE = (
    "This workbook contains system-generated duplicate identity groups. "
    "Groups requiring review are not human-confirmed identities. Use Reviewed "
    "Identity Export for human-confirmed output."
)

GROUP_COLUMNS = (
    "Duplicate Group",
    "Canonical Group ID",
    "Status",
    "Reason",
    "Member Count",
    "Review State",
)

MEMBER_COLUMNS = (
    "Part No",
    "Description",
    "Site",
    "Inventory UOM",
    "Part Type",
    "Commodity Group 01",
    "Commodity Group 02",
    "Safety Code",
    "Accounting Group",
    "Product Code",
    "Product Family",
    "Product Category",
    "HSN/SAC Code",
    "Source Row / Stable Record Reference",
)

ALL_COLUMNS = GROUP_COLUMNS + MEMBER_COLUMNS

REVIEWED_WORKBOOK_NOTICE = (
    "This workbook contains only current human-confirmed identity sets from the "
    "exact authority-selected review chain. Rejected, deferred, and superseded "
    "decisions are excluded. It is the operationally authoritative duplicate-set export."
)

REVIEWED_SET_COLUMNS = (
    "Reviewed Identity Set",
    "Group Reference",
    "Review Decision",
    "Reviewer",
    "Reviewed At",
    "Review Comment",
    "Member Count",
)

ALL_REVIEWED_COLUMNS = REVIEWED_SET_COLUMNS + MEMBER_COLUMNS

_DEFAULT_WIDTHS = (17, 34, 28, 52, 14, 28, 20, 48, 18, 16, 20, 22, 22, 18, 20, 20, 20, 20, 18, 48)
_REVIEWED_WIDTHS = (20, 30, 30, 20, 20, 40, 14, 16, 40, 14, 16, 14, 20, 20, 16, 20, 16, 18, 18, 16, 40)

_MEMBER_FIELD_BY_COLUMN = {
    "Part No": "part_no",
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

_STATUS_LABELS = {
    "LIKELY_DUPLICATE_GROUP": "Likely duplicate group",
    "POSSIBLE_DUPLICATE_GROUP_REVIEW": "Possible duplicate group - review",
    "CONFLICT": "Conflict",
    "DEFERRED": "Deferred",
}

_REASONS = {
    "LIKELY_DUPLICATE_GROUP": (
        "Strong identity evidence supports this potential duplicate group; human "
        "confirmation is not implied."
    ),
    "POSSIBLE_DUPLICATE_GROUP_REVIEW": (
        "Potential duplicate identity group; supporting identity evidence is "
        "present and human review is required."
    ),
    "CONFLICT": (
        "Conflicting identity evidence prevents safe grouping; human review is required."
    ),
    "DEFERRED": (
        "Identity evaluation is incomplete or deferred; no duplicate conclusion is implied."
    ),
}

_REVIEW_LABELS = {
    "CONFIRM_ALL_AS_ONE": "Reviewed - confirmed as one",
    "CONFIRM_SELECTED": "Reviewed - selected members confirmed",
    "SPLIT_PARTITIONS": "Reviewed - split into identity sets",
    "KEEP_ALL_SEPARATE": "Reviewed - keep separate",
    "UNSURE": "Reviewed - unsure",
}

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_GROUP_FILL = PatternFill("solid", fgColor="D9EAF7")
_THIN_GRAY = Side(style="thin", color="B7C9D6")
_BORDER = Border(left=_THIN_GRAY, right=_THIN_GRAY, top=_THIN_GRAY, bottom=_THIN_GRAY)


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
        status,
        "System-generated potential identity group; human confirmation is not implied.",
    )


def _review_label(state: dict | None) -> str:
    if not state or not state.get("reviewed"):
        return "Not reviewed"
    decision = state.get("current_decision_type")
    return _REVIEW_LABELS.get(decision, "Reviewed")


def _source_reference(row: dict) -> str:
    stable = str(row.get("stable_record_reference") or "")
    source = row.get("source_row_reference")
    return stable if source in (None, "") else f"Row {source} / {stable}"


def _group_values(label: str, group, state: dict | None) -> tuple:
    status = group.status.value
    return (
        label,
        serialize_versioned_identity_group_key(group.versioned_group_key),
        _STATUS_LABELS.get(status, status.replace("_", " ").title()),
        reason_for_group_status(status),
        group.member_count,
        _review_label(state),
    )


def _member_values(row: dict) -> tuple:
    values = [row.get(_MEMBER_FIELD_BY_COLUMN[column]) for column in MEMBER_COLUMNS[:-1]]
    values.append(_source_reference(row))
    return tuple(values)


def _write_row(sheet, row_number: int, values) -> None:
    for column_number, value in enumerate(values, start=1):
        cell = sheet.cell(row=row_number, column=column_number)
        write_spreadsheet_safe_cell(cell, value)
        cell.border = _BORDER
        cell.alignment = Alignment(vertical="top", wrap_text=column_number in (4, 8))


def _write_header(sheet, columns=ALL_COLUMNS) -> None:
    _write_row(sheet, 1, columns)
    for cell in sheet[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.row_dimensions[1].height = 32


def _style_dimensions(sheet, widths=_DEFAULT_WIDTHS) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _write_summary(workbook, scan, snapshot) -> None:
    sheet = workbook.active
    sheet.title = "Summary"
    rows = (
        ("System Group Report", ""),
        ("Notice", WORKBOOK_NOTICE),
        ("Report type", "System Group Report"),
        ("Authority", "System-generated / analytical"),
        ("Human confirmation", "Not implied"),
        ("Scan identifier", snapshot.scan_id),
        ("Scan name", scan.scan_name),
        ("Scan status", scan.status),
        ("Input record count", snapshot.canonical_record_count),
        ("Group count", snapshot.group_count),
        ("Likely group count", snapshot.likely_group_count),
        ("Review group count", snapshot.review_group_count),
        ("Conflict count", snapshot.conflict_count),
        ("Deferred count", snapshot.deferred_count),
        ("Unassigned count", snapshot.unassigned_count),
        ("Projection contract", snapshot.projection_contract.value),
        ("Source projection run", snapshot.source_projection_run_id),
    )
    for row_number, values in enumerate(rows, start=1):
        _write_row(sheet, row_number, values)
    sheet["A1"].font = Font(bold=True, size=16, color="1F4E78")
    for row_number in range(2, len(rows) + 1):
        sheet.cell(row_number, 1).font = Font(bold=True)
    sheet["B2"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 100
    sheet.freeze_panes = "A2"


def authority_selected_system_groups_to_xlsx(db, scan_id: int) -> bytes:
    """Create an in-memory workbook from the exact System Group export projection."""
    snapshot, export_rows = authority_selected_system_group_rows(db, scan_id)
    scan = db.get(DuplicateScan, scan_id)
    review_states = VersionedIdentityGroupReviewService(db).current_states_for_snapshot(
        snapshot
    )
    rows_by_group = {}
    for row in export_rows:
        rows_by_group.setdefault(row["group_key"], []).append(row)

    workbook = Workbook()
    _write_summary(workbook, scan, snapshot)
    grouped = workbook.create_sheet("Duplicate Groups")
    flat = workbook.create_sheet("Group Data")
    _write_header(grouped)
    _write_header(flat)

    grouped_row = 2
    flat_row = 2
    for group_index, group in enumerate(snapshot.groups, start=1):
        canonical_id = serialize_versioned_identity_group_key(group.versioned_group_key)
        label = f"DG-{group_index:06d}"
        group_values = _group_values(label, group, review_states.get(canonical_id))
        member_rows = rows_by_group.get(canonical_id, ())
        first_grouped_row = grouped_row
        for member_row in member_rows:
            _write_row(grouped, grouped_row, group_values + _member_values(member_row))
            _write_row(flat, flat_row, group_values + _member_values(member_row))
            grouped_row += 1
            flat_row += 1
        last_grouped_row = grouped_row - 1
        if last_grouped_row > first_grouped_row:
            for column in range(1, len(GROUP_COLUMNS) + 1):
                grouped.merge_cells(
                    start_row=first_grouped_row,
                    start_column=column,
                    end_row=last_grouped_row,
                    end_column=column,
                )
                grouped.cell(first_grouped_row, column).alignment = Alignment(
                    vertical="top", wrap_text=column == 4
                )
        for row_number in range(first_grouped_row, last_grouped_row + 1):
            for column in range(1, len(GROUP_COLUMNS) + 1):
                grouped.cell(row_number, column).fill = _GROUP_FILL

    for sheet in (grouped, flat):
        _style_dimensions(sheet)
    grouped.auto_filter.ref = (
        f"A1:{get_column_letter(len(ALL_COLUMNS))}{max(1, grouped.max_row)}"
    )
    if flat.max_row >= 2:
        table = Table(displayName="SystemGroupData", ref=f"A1:T{flat.max_row}")
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        flat.add_table(table)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _write_reviewed_summary(workbook, scan, snapshot, rows) -> None:
    sheet = workbook.active
    sheet.title = "Summary"
    set_count = len({row["reviewed_identity_set_key"] for row in rows})
    summary_rows = (
        ("Reviewed Identity Export", ""),
        ("Notice", REVIEWED_WORKBOOK_NOTICE),
        ("Report type", "Reviewed Identity Export"),
        ("Authority", "Human-confirmed"),
        ("Human confirmation", "Required and applied"),
        ("Scan identifier", snapshot.scan_id),
        ("Scan name", scan.scan_name),
        ("Scan status", scan.status),
        ("Input record count", snapshot.canonical_record_count),
        ("Reviewed identity set count", set_count),
        ("Reviewed member count", len(rows)),
        ("Projection contract", snapshot.projection_contract.value),
        ("Source projection run", snapshot.source_projection_run_id),
    )
    for row_number, values in enumerate(summary_rows, start=1):
        _write_row(sheet, row_number, values)
    sheet["A1"].font = Font(bold=True, size=16, color="1F4E78")
    for row_number in range(2, len(summary_rows) + 1):
        sheet.cell(row_number, 1).font = Font(bold=True)
    sheet["B2"].alignment = Alignment(wrap_text=True, vertical="top")
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 100
    sheet.freeze_panes = "A2"


def _reviewed_set_values(index: int, set_rows: list[dict]) -> tuple:
    first_row = set_rows[0]
    decision = first_row["review_decision_type"]
    return (
        f"RS-{index:06d}",
        first_row["group_reference"],
        _REVIEW_LABELS.get(decision, decision),
        first_row["reviewer"],
        first_row["reviewed_at"],
        first_row.get("review_comment") or "",
        len(set_rows),
    )


def authority_selected_reviewed_identities_to_xlsx(db, scan_id: int) -> bytes:
    """Create an in-memory workbook from the exact Reviewed Identity export projection."""
    snapshot, rows = authority_selected_reviewed_identity_rows(db, scan_id)
    scan = db.get(DuplicateScan, scan_id)

    rows_by_set: dict[str, list[dict]] = {}
    set_order: list[str] = []
    for row in rows:
        set_key = row["reviewed_identity_set_key"]
        if set_key not in rows_by_set:
            rows_by_set[set_key] = []
            set_order.append(set_key)
        rows_by_set[set_key].append(row)

    workbook = Workbook()
    _write_reviewed_summary(workbook, scan, snapshot, rows)
    sheet = workbook.create_sheet("Reviewed Identity Sets")
    _write_header(sheet, ALL_REVIEWED_COLUMNS)

    row_number = 2
    for set_index, set_key in enumerate(set_order, start=1):
        set_rows = rows_by_set[set_key]
        set_values = _reviewed_set_values(set_index, set_rows)
        first_data_row = row_number
        for member_row in set_rows:
            _write_row(sheet, row_number, set_values + _member_values(member_row))
            row_number += 1
        last_data_row = row_number - 1
        if last_data_row > first_data_row:
            for column in range(1, len(REVIEWED_SET_COLUMNS) + 1):
                sheet.merge_cells(
                    start_row=first_data_row,
                    start_column=column,
                    end_row=last_data_row,
                    end_column=column,
                )
                sheet.cell(first_data_row, column).alignment = Alignment(
                    vertical="top", wrap_text=column in (3, 6)
                )
        for row_index in range(first_data_row, last_data_row + 1):
            for column in range(1, len(REVIEWED_SET_COLUMNS) + 1):
                sheet.cell(row_index, column).fill = _GROUP_FILL

    _style_dimensions(sheet, _REVIEWED_WIDTHS)
    last_column = get_column_letter(len(ALL_REVIEWED_COLUMNS))
    sheet.auto_filter.ref = f"A1:{last_column}{max(1, sheet.max_row)}"
    if sheet.max_row >= 2:
        table = Table(
            displayName="ReviewedIdentitySets", ref=f"A1:{last_column}{sheet.max_row}"
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        sheet.add_table(table)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
