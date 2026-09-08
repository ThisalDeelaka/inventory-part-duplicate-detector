import csv
import io
from datetime import datetime, timezone

from app.llm.service_contracts import LLMCapability
from app.services.export_service import sanitize_csv_cell
from app.services.llm_triage_service import (
    candidate_is_triage_eligible,
    effective_recommended_action,
    effective_status,
)


CANDIDATE_FIELDS = [
    "part_no_a", "description_a", "contract_a", "part_no_b", "description_b", "contract_b",
    "similarity_score", "confidence_level", "business_status", "rule_decision", "rejection_reason",
    "scan_mode", "critical_mismatches", "generic_description_warning",
    "application_context_a", "application_context_b", "application_context_warning",
    "normalized_description_a", "normalized_description_b", "normalized_part_no_a", "normalized_part_no_b",
    "variant_attributes_a", "variant_attributes_b", "description_similarity", "tfidf_score", "fuzzy_score",
    "part_no_similarity", "technical_token_score", "matched_fields", "mismatched_fields", "explanation",
    "recommended_action", "review_status",
]

REJECTION_FIELDS = [
    "part_no_a", "description_a", "contract_a", "part_no_b", "description_b", "contract_b",
    "similarity_score", "confidence_level", "business_status", "rule_decision", "rejection_reason",
    "critical_mismatches", "explanation",
]

LLM_FIELDS = [
    "llm_state", "llm_used", "llm_cache_hit", "llm_provider", "llm_model",
    "llm_prompt_version", "llm_assessment", "llm_confidence", "llm_recommended_action",
    "llm_supporting_evidence", "llm_conflicting_evidence", "llm_bypass_reason",
    "llm_safe_error_category", "llm_generated_at", "deterministic_result_authoritative",
]

ASSISTED_FIELDS = [
    "effective_status", "effective_recommended_action", "llm_triage_run_state",
]

TERMINAL_RULE_DECISIONS = frozenset({"REJECT"})


def format_utc_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def sanitize_llm_csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value)
    stripped = text.lstrip(" \t\r\n")
    if text.lstrip(" ").startswith(("\t", "\r", "\n")) or stripped.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _blank_llm_row(state="NOT_REQUESTED", bypass_reason=None):
    row = {field: "" for field in LLM_FIELDS}
    row.update(
        llm_state=state,
        llm_used="false",
        llm_bypass_reason=bypass_reason or "",
        deterministic_result_authoritative="true",
    )
    return row


def snapshot_export_columns(snapshot):
    if snapshot is None:
        return _blank_llm_row()
    return {
        "llm_state": snapshot.state,
        "llm_used": snapshot.llm_used,
        "llm_cache_hit": snapshot.cache_hit,
        "llm_provider": snapshot.provider,
        "llm_model": snapshot.model,
        "llm_prompt_version": snapshot.prompt_version,
        "llm_assessment": snapshot.assessment,
        "llm_confidence": snapshot.confidence,
        "llm_recommended_action": snapshot.recommended_action,
        "llm_supporting_evidence": snapshot.supporting_evidence,
        "llm_conflicting_evidence": snapshot.conflicting_evidence,
        "llm_bypass_reason": snapshot.bypass_reason,
        "llm_safe_error_category": snapshot.safe_error_category,
        "llm_generated_at": format_utc_timestamp(snapshot.generated_at),
        "deterministic_result_authoritative": True,
    }


def exclusion_export_columns(exclusion):
    if exclusion.rule_decision in TERMINAL_RULE_DECISIONS:
        return _blank_llm_row("NOT_APPLICABLE_HARD_RULE", exclusion.rejection_reason)
    return _blank_llm_row()


def _write_rows(records, deterministic_fields, llm_rows, extra_fields=None):
    extra_fields = list(extra_fields or [])
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=deterministic_fields + LLM_FIELDS + extra_fields
    )
    writer.writeheader()
    for record, llm_row in zip(records, llm_rows):
        row = {field: sanitize_csv_cell(getattr(record, field)) for field in deterministic_fields}
        row.update({
            field: sanitize_llm_csv_cell(llm_row.get(field))
            for field in LLM_FIELDS + extra_fields
        })
        writer.writerow(row)
    return output.getvalue()


def candidates_with_llm_to_csv(
    candidates,
    snapshots_by_candidate,
    triage_snapshots_by_candidate=None,
    triage_run_state="NOT_STARTED",
):
    triage_snapshots_by_candidate = triage_snapshots_by_candidate or {}
    rows = []
    for item in candidates:
        triage_snapshot = triage_snapshots_by_candidate.get(item.id)
        fallback_snapshot = snapshots_by_candidate.get(item.id)
        selected_snapshot = triage_snapshot or fallback_snapshot
        row = snapshot_export_columns(selected_snapshot)
        status = effective_status(
            triage_snapshot or fallback_snapshot,
            eligible=candidate_is_triage_eligible(item),
            queued=triage_run_state != "NOT_STARTED",
        )
        row.update(
            effective_status=status,
            effective_recommended_action=effective_recommended_action(status),
            llm_triage_run_state=triage_run_state,
        )
        rows.append(row)
    return _write_rows(candidates, CANDIDATE_FIELDS, rows, ASSISTED_FIELDS)


def rejections_with_llm_to_csv(rejections):
    rows = [exclusion_export_columns(item) for item in rejections]
    return _write_rows(rejections, REJECTION_FIELDS, rows)


def candidate_snapshot_capability():
    return LLMCapability.CANDIDATE_ADVISORY.value
