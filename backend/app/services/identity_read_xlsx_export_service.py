"""Client-friendly XLSX representation of authority-selected System Groups."""

from __future__ import annotations

import json
from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.core.constants import FIELD_DEFINITIONS
from app.db.models import DuplicateScan
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.identity_read.deterministic_explanations import (
    business_match_facts,
    project_group_explanation,
    review_consideration_for_group,
    sources_for_group,
)
from app.services.deterministic_explanation_service import (
    load_pair_explanation_sources,
)
from app.match_strength.service import MatchStrengthProjectionService
from app.services.identity_group_review_service import VersionedIdentityGroupReviewService
from app.services.identity_group_presentation import (
    human_review_presentation,
    system_evidence_tier,
)
from app.services.identity_read_export_service import (
    authority_selected_system_group_rows,
)


WORKBOOK_NOTICE = (
    "Human review required. System-generated candidate groups are advisory "
    "and do not automatically merge or modify inventory records."
)
REPORT_CARRIED_OUT_BY = "IFS APP Test"
REVIEWED_WORKBOOK_NOTICE = (
    "This workbook contains only current human-confirmed same-identity sets from "
    "the exact authority-selected review chain. Rejected, deferred, and superseded "
    "decisions are excluded. Human decisions are operationally authoritative."
)
SHEET_ORDER = (
    "Overview",
    "Review Groups",
    "Group Index",
    "Detailed Data",
    "Technical Reference",
)
GROUP_INDEX_COLUMNS = (
    "Group", "Evidence Tier", "Match Strength", "Match Band", "Members", "Sites",
    "Review Consideration", "Human Decision", "Human Comment",
)
_REVIEW_GROUP_PREFIX_COLUMNS = (
    "Group", "Evidence Tier", "Match Strength", "Match Band", "Group Sites",
    "Review Consideration", "Why This Group Exists", "Relationship Evidence",
    "Human Decision", "Human Comment", "Member Position",
)
_DETAILED_DATA_PREFIX_COLUMNS = (
    "Group", "Members", "Group Sites", "Human Decision", "Human Comment",
)
TECHNICAL_REFERENCE_COLUMNS = (
    "Group", "Canonical Group ID", "Member Position", "Part Number", "Source Row",
    "Stable Record Reference", "Projection Contract", "Source Projection Run",
    "Original System Reason",
    "Match Strength Version", "Match Strength Status", "Unscored Reason",
    "Support Density", "Lower Quartile Score", "Weakest Member Anchor",
    "Pair Score Minimum", "Pair Score Median", "Pair Score Maximum",
    "Safety Status Crossover", "Safety Status Message",
)
MATCH_STRENGTH_OVERVIEW_NOTE = (
    "Match Strength summarizes deterministic comparison evidence. It is not a "
    "probability of duplication and does not replace human review."
)
MATCH_STRENGTH_TECHNICAL_CONTRACT = (
    ("Version", "DETERMINISTIC_MATCH_STRENGTH_V2"),
    (
        "Two-member rule",
        "Match Strength = exact persisted deterministic supporting-edge score",
    ),
    (
        "P25",
        "position = (number_of_supporting_scores - 1) × 0.25; P25 uses "
        "deterministic linear interpolation at that position.",
    ),
    (
        "Weakest-member anchor",
        "member_best_support(member) = maximum incident supporting-edge score; "
        "weakest_member_anchor = minimum member_best_support across members.",
    ),
    (
        "Three-or-more-member formula",
        "base_strength = min(P25, weakest_member_anchor); support_density = "
        "supporting_internal_pairs / possible_internal_pairs; Match Strength = "
        "round_half_even(base_strength × support_density, 2).",
    ),
    (
        "Bands",
        "High Match 90–100; Moderate Match 60–<90; Borderline Match 0–<60.",
    ),
    (
        "Threshold origin",
        "The 90 and 60 numeric boundaries come from the existing deterministic "
        "evaluator's numeric thresholds.",
    ),
    (
        "Evidence Tier authority",
        "The numeric band does not replace the authoritative signed Evidence Tier. "
        "A numerically High Match may remain Review Evidence when deterministic "
        "safety rules require review.",
    ),
    ("Created Date", "Created Date is not included in Match Strength."),
    (
        "Non-authority boundary",
        "Match Strength is not duplicate probability, AI confidence, a human "
        "review decision, or a GF4/GF5 authority input.",
    ),
    ("Group explanation version", "deterministic-group-explanation-v1"),
    ("Pair read-model version", "deterministic-pair-explanation-read-model-v1"),
    ("Structured evidence source", "deterministic-pair-explanation-v1"),
    (
        "Evidence availability",
        "COMPLETE renders persisted structured facts; PARTIAL_LEGACY shows only facts actually retained and a limited-history notice.",
    ),
    (
        "Safe causal language",
        "Relationships support the final group; no relationship is described as decisive or as causing the group.",
    ),
    (
        "Reason-code rendering",
        "Known codes use deterministic centralized wording; unknown codes remain visible verbatim without invented semantics.",
    ),
    (
        "Execution boundary",
        "No evaluator rerun and no LLM/provider call. Human review remains authoritative.",
    ),
    (
        "Business-facing labels",
        "Evidence Tier and Match Band wording in Review Groups and Group Index is presentation-only; internal values and contracts are unchanged.",
    ),
)
TECHNICAL_REFERENCE_HEADER_ROW = len(MATCH_STRENGTH_TECHNICAL_CONTRACT) + 5

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
# Duplicate-checking condition field codes are optional and user-selectable;
# columns without an entry here (Part Number, Description, Part Type) are
# always shown and are never reordered by selection.
_SOURCE_COLUMN_FIELD_CODE = {
    "Site": "CONTRACT",
    "Inventory UOM": "UNIT_MEAS",
    "Commodity Group 01": "PRIME_COMMODITY",
    "Commodity Group 02": "SECOND_COMMODITY",
    "Safety Code": "HAZARD_CODE",
    "Accounting Group": "ACCOUNTING_GROUP",
    "Product Code": "PART_PRODUCT_CODE",
    "Product Family": "PART_PRODUCT_FAMILY",
    "Product Category": "PRODUCT_CATEGORY_ID",
    "HSN/SAC Code": "HSN_SAC_CODE",
}
_SOURCE_COLUMN_WIDTHS = {
    "Part Number": 18, "Description": 38, "Site": 13, "Inventory UOM": 13,
    "Part Type": 13, "Commodity Group 01": 17, "Commodity Group 02": 17,
    "Safety Code": 13, "Accounting Group": 16, "Product Code": 15,
    "Product Family": 16, "Product Category": 16, "HSN/SAC Code": 15,
}
_SOURCE_COLUMN_FIXED_PREFIX = ("Part Number", "Description")


def _decode_selected_field_codes(selected_fields_json) -> set[str]:
    try:
        decoded = json.loads(selected_fields_json or "[]")
    except (TypeError, json.JSONDecodeError):
        decoded = []
    if not isinstance(decoded, list):
        decoded = []
    return {str(value).strip().upper() for value in decoded if str(value).strip()}


def _ordered_source_columns(selected_fields_json) -> tuple[str, ...]:
    """Selected duplicate-checking condition columns first, then the rest."""
    selected = _decode_selected_field_codes(selected_fields_json)
    reorderable = [
        column for column in _SOURCE_COLUMNS
        if column not in _SOURCE_COLUMN_FIXED_PREFIX
    ]
    chosen = [
        column for column in reorderable
        if _SOURCE_COLUMN_FIELD_CODE.get(column) in selected
    ]
    remaining = [column for column in reorderable if column not in chosen]
    return _SOURCE_COLUMN_FIXED_PREFIX + tuple(chosen) + tuple(remaining)


def _review_group_columns(source_columns) -> tuple:
    return _REVIEW_GROUP_PREFIX_COLUMNS + tuple(source_columns)


def _detailed_data_columns(source_columns) -> tuple:
    return _DETAILED_DATA_PREFIX_COLUMNS + tuple(source_columns)


# Canonical layouts (no duplicate-checking columns selected beyond the base
# order) — kept as plain tuples for callers that want the default shape.
REVIEW_GROUP_COLUMNS = _review_group_columns(_SOURCE_COLUMNS)
DETAILED_DATA_COLUMNS = _detailed_data_columns(_SOURCE_COLUMNS)
_REASONS = {
    "LIKELY_DUPLICATE_GROUP": (
        "Stronger deterministic evidence supports this system-suggested group "
        "for human review."
    ),
    "POSSIBLE_DUPLICATE_GROUP_REVIEW": (
        "Deterministic review evidence supports surfacing this group; "
        "human review is required."
    ),
    "CONFLICT": (
        "Conflicting identity evidence prevents safe grouping; human review is required."
    ),
    "DEFERRED": (
        "Identity evaluation is incomplete or deferred; no same-identity conclusion is implied."
    ),
}
_NAVY = "1F4E78"
_PALE_BLUE = "EAF3F8"
_PALE_GRAY = "F3F5F7"
_PALE_GOLD = "FFF2CC"
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
_MATCH_BAND_STYLES = {
    "High Match": (PatternFill("solid", fgColor="C6EFCE"), "1E7145"),
    "Moderate Match": (PatternFill("solid", fgColor="FFEB9C"), "9C6500"),
    "Borderline Match": (PatternFill("solid", fgColor="FFC7CE"), "9C0006"),
}
_DISABLED_HEADER_FILL = PatternFill("solid", fgColor="7F8B96")
_DISABLED_CELL_FILL = PatternFill("solid", fgColor="ECEEF1")
_DISABLED_FONT = Font(color="8A94A0")
_HUMAN_DECISION_OPTIONS = (
    "Not yet reviewed",
    "Confirmed all records as one identity",
    "Confirmed selected records as one identity",
    "Split into separate identity sets",
    "Rejected and kept separate",
    "Deferred for later review",
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


def _sites(member_rows) -> str:
    values = sorted({
        str(row.get("site_or_contract") or "").strip()
        for row in member_rows
        if str(row.get("site_or_contract") or "").strip()
    })
    return ", ".join(values) or "Not provided"


def _group_presentation(label: str, group, state: dict | None, member_rows) -> dict:
    _review_state, human_decision = human_review_presentation(state)
    raw_match_band = member_rows[0].get("match_band") if member_rows else None
    display_match_band = {
        "HIGH_MATCH": "High Match",
        "MODERATE_MATCH": "Moderate Match",
        "BORDERLINE_MATCH": "Borderline Match",
    }.get(raw_match_band, raw_match_band)
    return {
        "label": label,
        "canonical_id": serialize_versioned_identity_group_key(group.versioned_group_key),
        "evidence": system_evidence_tier(group.status.value),
        "members": group.member_count,
        "sites": _sites(member_rows),
        "original_reason": reason_for_group_status(group.status.value),
        "human_decision": human_decision,
        "human_comment": (state or {}).get("comment") or "",
        "match_strength": member_rows[0].get("match_strength") if member_rows else None,
        "match_band": display_match_band,
        "match_band_code": raw_match_band,
        "match_strength_version": member_rows[0].get("match_strength_version") if member_rows else None,
        "match_strength_status": member_rows[0].get("match_strength_status") if member_rows else None,
        "match_strength_unscored_reason": member_rows[0].get("match_strength_unscored_reason") if member_rows else None,
        "support_density": member_rows[0].get("support_density") if member_rows else None,
        "lower_quartile_score": member_rows[0].get("lower_quartile_score") if member_rows else None,
        "weakest_member_anchor": member_rows[0].get("weakest_member_anchor") if member_rows else None,
        "pair_score_min": member_rows[0].get("pair_score_min") if member_rows else None,
        "pair_score_median": member_rows[0].get("pair_score_median") if member_rows else None,
        "pair_score_max": member_rows[0].get("pair_score_max") if member_rows else None,
        "safety_status_crossover": member_rows[0].get("safety_status_crossover") if member_rows else False,
        "safety_status_message": member_rows[0].get("safety_status_message") if member_rows else None,
    }


def _relationship_lines(explanation) -> str:
    blocks = []
    details = {item.relationship_id: item for item in explanation.pair_explanations}
    for relationship in explanation.relationships:
        detail = details[relationship.relationship_id]
        score = (
            "score not recorded" if relationship.deterministic_score is None
            else f"{relationship.deterministic_score:.2f}/100"
        )
        support_label = {
            "STRONG_SUPPORT": "Strong Support",
            "REVIEW_SUPPORT": "Review Support",
        }.get(
            relationship.signed_relationship,
            relationship.signed_relationship.replace("_", " ").title(),
        )
        facts = business_match_facts(detail)
        sections = [
            f"{relationship.left_display_identity} ↔ {relationship.right_display_identity}",
            f"Pair match: {score} · {support_label}",
            "What matched: " + (
                "; ".join(facts)
                if facts else "Supporting matching information is recorded."
            ),
        ]
        if detail.availability_message:
            sections.append(detail.availability_message)
        blocks.append("\n".join(sections))
    return "\n\n".join(blocks)


def _source_values(row: dict, source_columns=_SOURCE_COLUMNS) -> tuple:
    return tuple(row.get(_MEMBER_FIELD_BY_COLUMN[column]) for column in source_columns)


def _write_row(sheet, row_number: int, values, *, wrap_columns=()) -> None:
    for column_number, value in enumerate(values, start=1):
        cell = sheet.cell(row=row_number, column=column_number)
        write_spreadsheet_safe_cell(cell, value)
        cell.border = _BORDER
        cell.alignment = Alignment(
            vertical="top", wrap_text=column_number in wrap_columns
        )


def _write_header(sheet, columns, *, row_number: int = 1) -> None:
    _write_row(
        sheet, row_number, columns, wrap_columns=range(1, len(columns) + 1)
    )
    for cell in sheet[row_number]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
    sheet.freeze_panes = f"A{row_number + 1}"
    sheet.row_dimensions[row_number].height = 30
    sheet.sheet_view.showGridLines = False


def _set_widths(sheet, widths) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _unselected_source_columns(selected_fields_json) -> frozenset[str]:
    """Condition columns the scan did not use for matching (shown greyed out)."""
    selected = _decode_selected_field_codes(selected_fields_json)
    return frozenset(
        column for column, code in _SOURCE_COLUMN_FIELD_CODE.items()
        if code not in selected
    )


def _apply_disabled_column_styles(
    sheet, source_columns, disabled_columns, *, prefix_length: int, last_row: int,
) -> None:
    for offset, column in enumerate(source_columns, start=1):
        if column not in disabled_columns:
            continue
        column_number = prefix_length + offset
        header = sheet.cell(1, column_number)
        header.fill = _DISABLED_HEADER_FILL
        for row_number in range(2, last_row + 1):
            cell = sheet.cell(row_number, column_number)
            cell.fill = _DISABLED_CELL_FILL
            cell.font = _DISABLED_FONT


def _apply_match_band_style(cell, match_band: str | None) -> None:
    style = _MATCH_BAND_STYLES.get(match_band)
    if not style:
        return
    fill, font_color = style
    cell.fill = fill
    cell.font = Font(color=font_color, bold=True)


def _add_human_decision_dropdown(sheet, column_letter: str, first_row: int, last_row: int) -> None:
    if last_row < first_row:
        return
    validation = DataValidation(
        type="list",
        formula1='"' + ",".join(_HUMAN_DECISION_OPTIONS) + '"',
        allow_blank=True,
    )
    validation.promptTitle = "Human Decision"
    validation.prompt = "Select the recorded human decision for this group."
    validation.errorTitle = "Not a listed decision"
    validation.error = "Choose one of the listed human decisions."
    sheet.add_data_validation(validation)
    validation.add(f"{column_letter}{first_row}:{column_letter}{last_row}")


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


def selected_condition_label_list(selected_fields_json: str) -> list[str]:
    """Return persisted selected fields in stable UI order with safe fallbacks."""
    selected = _decode_selected_field_codes(selected_fields_json)
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
    return ordered


def selected_condition_labels(selected_fields_json: str) -> str:
    """One condition per line, for neatly stacked display in a wrapped cell."""
    return "\n".join(selected_condition_label_list(selected_fields_json)) or "None selected"


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


def _write_footer_metadata(sheet, metadata, *, start_row: int) -> None:
    """Report Details / Technical Footer rows, sized for easy reading."""
    for row_number, (label, value) in enumerate(metadata, start=start_row):
        _merge_and_write(
            sheet, f"A{row_number}:B{row_number}", label,
            fill=PatternFill("solid", fgColor=_PALE_GRAY),
            font=Font(color=_NAVY, bold=True, size=11),
            alignment=Alignment(vertical="center"),
        )
        _merge_and_write(
            sheet, f"C{row_number}:H{row_number}", value,
            fill=PatternFill("solid", fgColor=_WHITE),
            font=Font(color=_TEXT, bold=True, size=11),
            alignment=Alignment(vertical="center", wrap_text=True),
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


def _write_conditions_card(sheet, columns: str, selected_fields_json, *, start_row: int) -> None:
    """Duplicate-checking conditions info card: one condition per line, sized to fit."""
    labels = selected_condition_label_list(selected_fields_json)
    text = "\n".join(labels) or "None selected"
    _write_info_card(
        sheet, columns, "Duplicate-checking Conditions", text, start_row=start_row,
    )
    line_count = max(1, len(labels))
    row_height = max(16, 15 * ((line_count + 1) // 2) + 6)
    sheet.row_dimensions[start_row + 1].height = row_height
    sheet.row_dimensions[start_row + 2].height = row_height


def _write_overview(workbook, scan, snapshot, review_states, strength_distribution) -> None:
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
    _write_conditions_card(sheet, "A:D", scan.selected_fields, start_row=10)
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
        ("Part Type", scan.part_type),
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
    _write_footer_metadata(sheet, metadata, start_row=45)
    _merge_and_write(
        sheet, "A51:H51", "DETERMINISTIC MATCH STRENGTH",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    for row_number, (label, value) in enumerate((
        ("High Match (90–100)", strength_distribution["HIGH_MATCH"]),
        ("Moderate Match (60–<90)", strength_distribution["MODERATE_MATCH"]),
        ("Borderline Match (0–<60)", strength_distribution["BORDERLINE_MATCH"]),
        ("Unscored", strength_distribution["UNSCORED"]),
    ), start=52):
        _write_progress_row(sheet, row_number, label, value)
    _merge_and_write(
        sheet, "A57:H59", MATCH_STRENGTH_OVERVIEW_NOTE,
        fill=PatternFill("solid", fgColor=_PALE_GRAY),
        font=Font(color="5B7894", italic=True, size=9),
        alignment=Alignment(horizontal="left", vertical="center", wrap_text=True),
    )
    sheet.freeze_panes = "A6"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    for row_number in (1, 2, 3, 7, 8, 16, 17, 20, 21, 25, 26, 35, 36):
        sheet.row_dimensions[row_number].height = 24


def _write_group_index(sheet, groups) -> None:
    _write_header(sheet, GROUP_INDEX_COLUMNS)
    for row_number, item in enumerate(groups, start=2):
        p = item["presentation"]
        _write_row(
            sheet, row_number,
            (p["label"], p["evidence"], p["match_strength"], p["match_band"],
             p["members"], p["sites"], p["review_consideration"],
             p["human_decision"], p["human_comment"]),
            wrap_columns=(2, 4, 6, 7, 8, 9),
        )
        _apply_match_band_style(sheet.cell(row_number, 4), p["match_band"])
        sheet.row_dimensions[row_number].height = 26
    _set_widths(sheet, (14, 16, 13, 15, 10, 18, 40, 26, 32))
    sheet.freeze_panes = "E2"
    if groups:
        sheet.auto_filter.ref = (
            f"A1:{get_column_letter(len(GROUP_INDEX_COLUMNS))}{sheet.max_row}"
        )
        _add_human_decision_dropdown(sheet, "H", 2, sheet.max_row)


def _write_review_groups(
    sheet, groups, source_columns=_SOURCE_COLUMNS, disabled_columns=frozenset(),
) -> None:
    columns = _review_group_columns(source_columns)
    _write_header(sheet, columns)
    group_level_columns = tuple(range(1, 11))
    current_row = 2
    if not groups:
        _merge_and_write(
            sheet,
            f"A2:{get_column_letter(len(columns))}3",
            "No candidate groups were generated for this scan.",
            fill=PatternFill("solid", fgColor=_PALE_GRAY),
            font=Font(color=_TEXT, italic=True),
            alignment=Alignment(horizontal="center", vertical="center"),
        )
    for group_index, item in enumerate(groups):
        p = item["presentation"]
        member_rows = item["member_rows"]
        start_row = current_row
        for member_number, member_row in enumerate(member_rows, start=1):
            source = _source_values(member_row, source_columns)
            _write_row(
                sheet, current_row,
                (p["label"], p["evidence"], p["match_strength"], p["match_band"],
                 p["sites"], p["review_consideration"],
                 p["deterministic_group_summary"], p["relationship_evidence"],
                 p["human_decision"], p["human_comment"], member_number, *source),
                wrap_columns=(2, 4, 5, 6, 7, 8, 9, 10, 13),
            )
            sheet.row_dimensions[current_row].height = max(
                40, min(160, 24 + 15 * max(1, p["relationship_evidence"].count("\n") + 1))
            )
            current_row += 1
        end_row = current_row - 1
        fill = _GROUP_FILLS[group_index % len(_GROUP_FILLS)]
        for row_number in range(start_row, end_row + 1):
            for column_number in range(1, len(columns) + 1):
                cell = sheet.cell(row_number, column_number)
                cell.fill = fill
                cell.border = Border(
                    left=_THIN_GRAY, right=_THIN_GRAY,
                    top=_MEDIUM_BLUE if row_number == start_row else _THIN_GRAY,
                    bottom=_MEDIUM_BLUE if row_number == end_row else _THIN_GRAY,
                )
        for column_number in group_level_columns:
            if end_row > start_row:
                sheet.merge_cells(
                    start_row=start_row, start_column=column_number,
                    end_row=end_row, end_column=column_number,
                )
            sheet.cell(start_row, column_number).alignment = Alignment(
                vertical="center", wrap_text=True
            )
        _apply_match_band_style(sheet.cell(start_row, 4), p["match_band"])
    prefix_widths = (14, 16, 13, 15, 18, 42, 42, 40, 28, 32, 12)
    _set_widths(
        sheet,
        prefix_widths + tuple(_SOURCE_COLUMN_WIDTHS[column] for column in source_columns),
    )
    sheet.freeze_panes = "F2"
    _apply_disabled_column_styles(
        sheet, source_columns, disabled_columns,
        prefix_length=len(_REVIEW_GROUP_PREFIX_COLUMNS),
        last_row=sheet.max_row if groups else 1,
    )
    if groups:
        _add_human_decision_dropdown(sheet, "I", 2, sheet.max_row)


def _write_detailed_data(
    sheet, groups, source_columns=_SOURCE_COLUMNS, disabled_columns=frozenset(),
) -> None:
    columns = _detailed_data_columns(source_columns)
    _write_header(sheet, columns)
    row_number = 2
    for item in groups:
        p = item["presentation"]
        for member_row in item["member_rows"]:
            _write_row(
                sheet, row_number,
                (p["label"], p["members"], p["sites"],
                 p["human_decision"], p["human_comment"],
                 *_source_values(member_row, source_columns)),
                wrap_columns=(3, 4, 5, 7),
            )
            sheet.row_dimensions[row_number].height = 26
            row_number += 1
    prefix_widths = (14, 10, 18, 28, 32)
    _set_widths(
        sheet,
        prefix_widths + tuple(_SOURCE_COLUMN_WIDTHS[column] for column in source_columns),
    )
    _apply_disabled_column_styles(
        sheet, source_columns, disabled_columns,
        prefix_length=len(_DETAILED_DATA_PREFIX_COLUMNS), last_row=sheet.max_row,
    )
    if sheet.max_row >= 2:
        table = Table(
            displayName="SystemGroupData",
            ref=f"A1:{get_column_letter(len(columns))}{sheet.max_row}",
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        sheet.add_table(table)
        _add_human_decision_dropdown(sheet, "D", 2, sheet.max_row)


def _write_technical_reference(sheet, groups, snapshot) -> None:
    sheet.sheet_view.showGridLines = False
    _merge_and_write(
        sheet, "A1:H1", "MATCH STRENGTH V2 CONTRACT",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True, size=14),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    for row_number, (label, definition) in enumerate(
        MATCH_STRENGTH_TECHNICAL_CONTRACT, start=2
    ):
        _merge_and_write(
            sheet, f"A{row_number}:B{row_number}", label,
            fill=PatternFill("solid", fgColor=_PALE_GRAY),
            font=Font(color=_NAVY, bold=True, size=9),
            alignment=Alignment(vertical="center", wrap_text=True),
        )
        _merge_and_write(
            sheet, f"C{row_number}:H{row_number}", definition,
            fill=PatternFill("solid", fgColor=_WHITE),
            font=Font(color=_TEXT, size=9),
            alignment=Alignment(vertical="center", wrap_text=True),
        )
        sheet.row_dimensions[row_number].height = 34
    _merge_and_write(
        sheet,
        f"A{TECHNICAL_REFERENCE_HEADER_ROW - 1}:H{TECHNICAL_REFERENCE_HEADER_ROW - 1}",
        "GROUP AUDIT DATA",
        fill=PatternFill("solid", fgColor="5B7894"),
        font=Font(color=_WHITE, bold=True, size=10),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    _write_header(
        sheet, TECHNICAL_REFERENCE_COLUMNS,
        row_number=TECHNICAL_REFERENCE_HEADER_ROW,
    )
    row_number = TECHNICAL_REFERENCE_HEADER_ROW + 1
    for item in groups:
        p = item["presentation"]
        for member_number, member_row in enumerate(item["member_rows"], start=1):
            _write_row(
                sheet, row_number,
                (p["label"], p["canonical_id"], member_number,
                 member_row.get("part_no"), member_row.get("source_row_reference"),
                 member_row.get("stable_record_reference"),
                 snapshot.projection_contract.value,
                 snapshot.source_projection_run_id, p["original_reason"],
                 p["match_strength_version"], p["match_strength_status"],
                 p["match_strength_unscored_reason"], p["support_density"],
                 p["lower_quartile_score"], p["weakest_member_anchor"],
                 p["pair_score_min"], p["pair_score_median"], p["pair_score_max"],
                 p["safety_status_crossover"], p["safety_status_message"]),
                wrap_columns=(2, 6, 9, 20),
            )
            row_number += 1
    _set_widths(
        sheet,
        (16, 38, 10, 20, 14, 42, 22, 22, 58, 34, 22, 28, 16, 20, 22,
         18, 18, 18, 22, 58),
    )
    if groups:
        sheet.auto_filter.ref = (
            f"A{TECHNICAL_REFERENCE_HEADER_ROW}:"
            f"{get_column_letter(len(TECHNICAL_REFERENCE_COLUMNS))}{sheet.max_row}"
        )


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
    strengths = MatchStrengthProjectionService(db).project_groups(snapshot.groups)
    loaded_explanations = load_pair_explanation_sources(db, snapshot)
    for group_index, group in enumerate(snapshot.groups, start=1):
        canonical_id = serialize_versioned_identity_group_key(group.versioned_group_key)
        member_rows = tuple(rows_by_group.get(canonical_id, ()))
        explanation = project_group_explanation(
            group, strengths[group.versioned_group_key],
            sources_for_group(group, loaded_explanations), include_details=True,
        )
        presentation = _group_presentation(
                f"CG-{group_index:06d}", group,
                review_states.get(canonical_id), member_rows,
        )
        presentation["deterministic_group_summary"] = explanation.group_summary
        presentation["review_consideration"] = review_consideration_for_group(
            explanation
        )
        presentation["relationship_evidence"] = _relationship_lines(explanation)
        groups.append({
            "presentation": presentation,
            "member_rows": member_rows,
        })

    strength_distribution = {
        "HIGH_MATCH": 0,
        "MODERATE_MATCH": 0,
        "BORDERLINE_MATCH": 0,
        "UNSCORED": 0,
    }
    for item in groups:
        presentation = item["presentation"]
        key = (
            presentation["match_band_code"]
            if presentation["match_strength_status"] == "SCORED"
            else "UNSCORED"
        )
        strength_distribution[key] += 1

    source_columns = _ordered_source_columns(scan.selected_fields)
    disabled_columns = _unselected_source_columns(scan.selected_fields)
    workbook = Workbook()
    _write_overview(
        workbook, scan, snapshot, review_states, strength_distribution
    )
    review_groups = workbook.create_sheet("Review Groups")
    group_index = workbook.create_sheet("Group Index")
    detailed_data = workbook.create_sheet("Detailed Data")
    technical = workbook.create_sheet("Technical Reference")
    _write_review_groups(review_groups, groups, source_columns, disabled_columns)
    _write_group_index(group_index, groups)
    _write_detailed_data(detailed_data, groups, source_columns, disabled_columns)
    _write_technical_reference(technical, groups, snapshot)
    workbook.active = 0

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


_CONFIRMED_DECISION_TYPES = {
    "CONFIRM_ALL_AS_ONE", "CONFIRM_SELECTED", "SPLIT_PARTITIONS",
}


def _write_reviewed_overview(
    workbook, scan, snapshot, groups, strength_distribution,
    confirmed_same_count, split_count,
) -> None:
    sheet = workbook.active
    sheet.title = "Overview"
    sheet.sheet_view.showGridLines = False
    _set_widths(sheet, (14,) * 8)
    _merge_and_write(
        sheet, "A1:H2", "Reviewed Identity Export",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True, size=20),
        alignment=Alignment(horizontal="center", vertical="center"),
    )
    _merge_and_write(
        sheet, "A3:H3", "Human-confirmed same-identity groups, operationally authoritative",
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
    _write_conditions_card(sheet, "A:D", scan.selected_fields, start_row=10)
    _write_info_card(
        sheet, "E:H", "Carried Out By", REPORT_CARRIED_OUT_BY, start_row=10,
    )

    _merge_and_write(
        sheet, "A14:H14", "FINDINGS AT A GLANCE",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    stronger_evidence = sum(
        1 for item in groups if item["presentation"]["evidence"] == "Stronger Evidence"
    )
    review_evidence = sum(
        1 for item in groups if item["presentation"]["evidence"] == "Review Evidence"
    )
    members_in_groups = sum(item["presentation"]["members"] for item in groups)
    outside_export = max(0, (snapshot.canonical_record_count or 0) - members_in_groups)
    for columns, label, value in (
        ("A:B", "Reviewed Identity Groups", len(groups)),
        ("C:E", "Stronger Evidence", stronger_evidence),
        ("F:H", "Review Evidence", review_evidence),
    ):
        _write_kpi(sheet, columns, label, value, start_row=15)
    for columns, label, value in (
        ("A:D", "Records in Reviewed Groups", members_in_groups),
        ("E:H", "Records Outside This Export", outside_export),
    ):
        _write_kpi(sheet, columns, label, value, start_row=19)

    _merge_and_write(
        sheet, "A23:H23", "REVIEW DECISION BREAKDOWN",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    _write_kpi(
        sheet, "A:D", "Confirmed as Same Identity", confirmed_same_count, start_row=24,
    )
    _write_kpi(
        sheet, "E:H", "Split into Identity Sets", split_count, start_row=24,
    )

    _merge_and_write(
        sheet, "A28:H29",
        REVIEWED_WORKBOOK_NOTICE,
        fill=PatternFill("solid", fgColor=_PALE_GOLD),
        font=Font(color=_TEXT, bold=True),
        alignment=Alignment(horizontal="left", vertical="center", wrap_text=True),
    )
    _merge_and_write(
        sheet, "A31:H31", "HOW TO USE THIS WORKBOOK",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    _merge_and_write(
        sheet, "A32:H34",
        "1. Open Review Groups and inspect each human-confirmed group.\n"
        "2. The Human Decision column shows the recorded reviewer decision for "
        "each group.\n"
        "3. Use Detailed Data when additional record-level information is required.",
        fill=PatternFill("solid", fgColor=_WHITE),
        font=Font(color=_TEXT),
        alignment=Alignment(horizontal="left", vertical="top", wrap_text=True),
    )
    metadata = (
        ("Scan ID", snapshot.scan_id),
        ("Scan Name", scan.scan_name),
        ("Part Type", scan.part_type),
        ("Scan Status", scan.status),
        ("Projection Contract", snapshot.projection_contract.value),
        ("Source Projection Run", snapshot.source_projection_run_id),
    )
    _merge_and_write(
        sheet, "A36:H36", "REPORT DETAILS / TECHNICAL FOOTER",
        fill=PatternFill("solid", fgColor="5B7894"),
        font=Font(color=_WHITE, bold=True, size=10),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    _write_footer_metadata(sheet, metadata, start_row=37)
    _merge_and_write(
        sheet, "A43:H43", "DETERMINISTIC MATCH STRENGTH",
        fill=PatternFill("solid", fgColor=_NAVY),
        font=Font(color=_WHITE, bold=True),
        alignment=Alignment(horizontal="left", vertical="center"),
    )
    for row_number, (label, value) in enumerate((
        ("High Match (90–100)", strength_distribution["HIGH_MATCH"]),
        ("Moderate Match (60–<90)", strength_distribution["MODERATE_MATCH"]),
        ("Borderline Match (0–<60)", strength_distribution["BORDERLINE_MATCH"]),
        ("Unscored", strength_distribution["UNSCORED"]),
    ), start=44):
        _write_progress_row(sheet, row_number, label, value)
    _merge_and_write(
        sheet, "A49:H51", MATCH_STRENGTH_OVERVIEW_NOTE,
        fill=PatternFill("solid", fgColor=_PALE_GRAY),
        font=Font(color="5B7894", italic=True, size=9),
        alignment=Alignment(horizontal="left", vertical="center", wrap_text=True),
    )
    sheet.freeze_panes = "A6"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    for row_number in (1, 2, 3, 7, 8, 16, 17, 20, 21, 25, 26, 28, 29):
        sheet.row_dimensions[row_number].height = 24


def authority_selected_reviewed_identities_to_xlsx(db, scan_id: int) -> bytes:
    """Create a client workbook, in the same layout as the System Group export,
    scoped to only human-confirmed same-identity groups."""
    snapshot, export_rows = authority_selected_system_group_rows(db, scan_id)
    scan = db.get(DuplicateScan, scan_id)
    review_states = VersionedIdentityGroupReviewService(db).current_states_for_snapshot(
        snapshot
    )
    rows_by_group = {}
    for row in export_rows:
        rows_by_group.setdefault(row["group_key"], []).append(row)

    def _state_for(group):
        canonical_id = serialize_versioned_identity_group_key(group.versioned_group_key)
        return review_states.get(canonical_id) or {}

    confirmed_groups = [
        group for group in snapshot.groups
        if _state_for(group).get("current_decision_type") in _CONFIRMED_DECISION_TYPES
    ]
    confirmed_same_count = sum(
        1 for group in confirmed_groups
        if _state_for(group).get("current_decision_type")
        in ("CONFIRM_ALL_AS_ONE", "CONFIRM_SELECTED")
    )
    split_count = sum(
        1 for group in confirmed_groups
        if _state_for(group).get("current_decision_type") == "SPLIT_PARTITIONS"
    )

    groups = []
    strengths = MatchStrengthProjectionService(db).project_groups(confirmed_groups)
    loaded_explanations = load_pair_explanation_sources(db, snapshot)
    for group_index, group in enumerate(confirmed_groups, start=1):
        canonical_id = serialize_versioned_identity_group_key(group.versioned_group_key)
        member_rows = tuple(rows_by_group.get(canonical_id, ()))
        explanation = project_group_explanation(
            group, strengths[group.versioned_group_key],
            sources_for_group(group, loaded_explanations), include_details=True,
        )
        presentation = _group_presentation(
                f"RS-{group_index:06d}", group,
                review_states.get(canonical_id), member_rows,
        )
        presentation["deterministic_group_summary"] = explanation.group_summary
        presentation["review_consideration"] = review_consideration_for_group(
            explanation
        )
        presentation["relationship_evidence"] = _relationship_lines(explanation)
        groups.append({
            "presentation": presentation,
            "member_rows": member_rows,
        })

    strength_distribution = {
        "HIGH_MATCH": 0,
        "MODERATE_MATCH": 0,
        "BORDERLINE_MATCH": 0,
        "UNSCORED": 0,
    }
    for item in groups:
        presentation = item["presentation"]
        key = (
            presentation["match_band_code"]
            if presentation["match_strength_status"] == "SCORED"
            else "UNSCORED"
        )
        strength_distribution[key] += 1

    source_columns = _ordered_source_columns(scan.selected_fields)
    disabled_columns = _unselected_source_columns(scan.selected_fields)
    workbook = Workbook()
    _write_reviewed_overview(
        workbook, scan, snapshot, groups, strength_distribution,
        confirmed_same_count, split_count,
    )
    review_groups = workbook.create_sheet("Review Groups")
    group_index_sheet = workbook.create_sheet("Group Index")
    detailed_data = workbook.create_sheet("Detailed Data")
    technical = workbook.create_sheet("Technical Reference")
    _write_review_groups(review_groups, groups, source_columns, disabled_columns)
    _write_group_index(group_index_sheet, groups)
    _write_detailed_data(detailed_data, groups, source_columns, disabled_columns)
    _write_technical_reference(technical, groups, snapshot)
    workbook.active = 0

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
