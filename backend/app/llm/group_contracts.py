"""Provider-independent contracts for bounded whole-group LLM advisory."""

import hashlib
import json
from dataclasses import dataclass, fields
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel, ConfigDict, Field, StrictInt, StringConstraints, ValidationError,
)


GROUP_ADVISORY_REQUEST_VERSION = "group-advisory-request-v1"
GROUP_ADVISORY_RESULT_VERSION = "group-advisory-result-v1"
MAX_GROUP_ADVISORY_MEMBERS = 20

RecordRef = Annotated[str, StringConstraints(min_length=64, max_length=64)]
ShortOptional = Annotated[str, StringConstraints(max_length=200)] | None
BoundedText = Annotated[str, StringConstraints(max_length=2048)]
ReasonCode = Annotated[str, StringConstraints(min_length=1, max_length=120)]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GroupAdvisoryMember(StrictContract):
    record_ref_key: RecordRef
    part_no: Annotated[str, StringConstraints(max_length=200)]
    normalized_part_no: Annotated[str, StringConstraints(max_length=512)]
    description: BoundedText
    normalized_description: BoundedText
    site_or_contract: ShortOptional = None
    uom: ShortOptional = None
    product_category: ShortOptional = None
    hsn_sac: ShortOptional = None


class GroupAdvisoryCriticalMismatch(StrictContract):
    group: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    label: Annotated[str, StringConstraints(max_length=200)] | None = None
    values_left: tuple[Annotated[str, StringConstraints(max_length=200)], ...] = Field(
        default=(), max_length=10
    )
    values_right: tuple[Annotated[str, StringConstraints(max_length=200)], ...] = Field(
        default=(), max_length=10
    )


class GroupAdvisoryEdge(StrictContract):
    left_record_ref_key: RecordRef
    right_record_ref_key: RecordRef
    edge_class: Literal["STRONG_SUPPORT", "REVIEW_SUPPORT", "NON_GROUPABLE", "CANNOT_LINK"]
    reason_codes: tuple[ReasonCode, ...] = Field(max_length=32)
    evidence_source: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    deterministic_status: Annotated[str, StringConstraints(max_length=80)] | None = None
    critical_mismatches: tuple[GroupAdvisoryCriticalMismatch, ...] = Field(
        default=(), max_length=10
    )


class GroupIdentityEvidenceSummary(StrictContract):
    strong_support_count: int = Field(ge=0, le=190)
    review_support_count: int = Field(ge=0, le=190)
    non_groupable_count: int = Field(ge=0, le=190)
    internal_pair_count: int = Field(ge=1, le=190)
    evidence_completeness: float = Field(ge=0, le=1)
    reason_codes: tuple[ReasonCode, ...] = Field(max_length=64)


class GroupUomMappingSummary(StrictContract):
    distinct_uoms: tuple[Annotated[str, StringConstraints(max_length=80)], ...] = Field(
        max_length=20
    )
    same_uom_pair_count: int = Field(ge=0, le=190)
    convertible_uom_pair_count: int = Field(ge=0, le=190)
    different_basis_pair_count: int = Field(ge=0, le=190)
    missing_or_wildcard_pair_count: int = Field(ge=0, le=190)
    malformed_or_unknown_pair_count: int = Field(ge=0, le=190)
    possible_mapping_error_count: int = Field(ge=0, le=190)
    identity_authority: Literal[False] = False


class GroupAdvisoryRequest(StrictContract):
    contract_version: Literal[GROUP_ADVISORY_REQUEST_VERSION]
    scan_id: int = Field(gt=0)
    projection_run_id: int = Field(gt=0)
    group_snapshot_id: int = Field(gt=0)
    group_hypothesis_key: RecordRef
    projection_algorithm_version: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    group_status: Literal["POSSIBLE_DUPLICATE_GROUP_REVIEW"]
    group_size: int = Field(ge=2, le=MAX_GROUP_ADVISORY_MEMBERS)
    members: tuple[GroupAdvisoryMember, ...] = Field(min_length=2, max_length=20)
    internal_edges: tuple[GroupAdvisoryEdge, ...] = Field(min_length=1, max_length=190)
    group_identity_evidence_summary: GroupIdentityEvidenceSummary
    group_uom_mapping_summary: GroupUomMappingSummary
    unresolved_identity_questions: tuple[ReasonCode, ...] = Field(min_length=1, max_length=32)


def canonical_group_advisory_request_json(request: GroupAdvisoryRequest) -> str:
    payload = request.model_dump(mode="json")
    payload["members"] = sorted(
        payload["members"], key=lambda item: item["record_ref_key"]
    )
    payload["internal_edges"] = sorted(
        payload["internal_edges"],
        key=lambda item: (
            item["left_record_ref_key"], item["right_record_ref_key"]
        ),
    )
    for edge in payload["internal_edges"]:
        edge["reason_codes"] = sorted(set(edge["reason_codes"]))
    payload["group_identity_evidence_summary"]["reason_codes"] = sorted(set(
        payload["group_identity_evidence_summary"]["reason_codes"]
    ))
    payload["group_uom_mapping_summary"]["distinct_uoms"] = sorted(set(
        payload["group_uom_mapping_summary"]["distinct_uoms"]
    ))
    payload["unresolved_identity_questions"] = sorted(set(
        payload["unresolved_identity_questions"]
    ))
    return json.dumps(
        payload, ensure_ascii=True,
        sort_keys=True, separators=(",", ":"),
    )


def group_advisory_request_fingerprint(request: GroupAdvisoryRequest) -> str:
    return hashlib.sha256(
        canonical_group_advisory_request_json(request).encode("utf-8")
    ).hexdigest()


class GroupAdvisoryOutcome(str, Enum):
    SUPPORTS_SINGLE_IDENTITY = "SUPPORTS_SINGLE_IDENTITY"
    PROPOSES_PARTITION = "PROPOSES_PARTITION"
    INCONCLUSIVE = "INCONCLUSIVE"


class GroupAdvisoryConfidenceBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class GroupAdvisoryResult(StrictContract):
    contract_version: Literal[GROUP_ADVISORY_RESULT_VERSION]
    request_fingerprint: Annotated[str, StringConstraints(min_length=64, max_length=64)]
    group_snapshot_id: StrictInt = Field(gt=0)
    group_hypothesis_key: RecordRef
    outcome: GroupAdvisoryOutcome
    proposed_partitions: tuple[tuple[RecordRef, ...], ...] = Field(
        max_length=20
    )
    confidence_band: GroupAdvisoryConfidenceBand
    reason_codes: tuple[ReasonCode, ...] = Field(max_length=16)
    rationale: Annotated[str, StringConstraints(max_length=1200)]
    mapping_observations: tuple[
        Annotated[str, StringConstraints(max_length=300)], ...
    ] = Field(max_length=10)
    requires_human_review: Literal[True]
    deterministic_result_authoritative: Literal[True]
    validation_reasons: tuple[ReasonCode, ...] = Field(default=(), max_length=16)


def _inconclusive(request: GroupAdvisoryRequest, reasons: list[str]) -> GroupAdvisoryResult:
    return GroupAdvisoryResult(
        contract_version=GROUP_ADVISORY_RESULT_VERSION,
        request_fingerprint=group_advisory_request_fingerprint(request),
        group_snapshot_id=request.group_snapshot_id,
        group_hypothesis_key=request.group_hypothesis_key,
        outcome=GroupAdvisoryOutcome.INCONCLUSIVE,
        proposed_partitions=(), confidence_band=GroupAdvisoryConfidenceBand.LOW,
        reason_codes=("INVALID_PROVIDER_RESULT",), rationale="",
        mapping_observations=(), requires_human_review=True,
        deterministic_result_authoritative=True,
        validation_reasons=tuple(sorted(set(reasons)))[:16],
    )


MAX_SCHEMA_DIAGNOSTIC_ENTRIES = 16
MAX_SCHEMA_DIAGNOSTIC_PATH_LENGTH = 120


@dataclass(frozen=True)
class GroupResultSchemaDiagnostic:
    """Bounded Pydantic field paths only; never provider values or messages."""

    missing_fields: tuple[str, ...] = ()
    unexpected_fields: tuple[str, ...] = ()
    wrong_type_fields: tuple[str, ...] = ()
    invalid_literal_fields: tuple[str, ...] = ()
    invalid_length_fields: tuple[str, ...] = ()
    invalid_format_fields: tuple[str, ...] = ()
    other_schema_paths: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not any(getattr(self, item.name) for item in fields(self))


def _safe_schema_path(location: Any) -> str:
    parts = []
    for part in location if isinstance(location, (tuple, list)) else ():
        if isinstance(part, str):
            safe = "".join(character for character in part if character.isalnum() or character == "_")
            if safe:
                parts.append(safe)
        elif isinstance(part, int):
            parts.append("[]")
    path = ".".join(parts) or "$"
    return path[:MAX_SCHEMA_DIAGNOSTIC_PATH_LENGTH]


def group_result_schema_diagnostic(
    exc: ValidationError | Exception,
) -> GroupResultSchemaDiagnostic:
    """Map authoritative parser errors to deterministic field-name categories."""
    buckets = {item.name: set() for item in fields(GroupResultSchemaDiagnostic)}
    try:
        errors = exc.errors(
            include_url=False, include_context=False, include_input=False
        ) if isinstance(exc, ValidationError) else ()
    except Exception:
        errors = ()
    if not errors:
        buckets["other_schema_paths"].add("$")
    for error in errors:
        path = _safe_schema_path(error.get("loc", ()))
        error_type = error.get("type", "")
        if error_type == "missing":
            bucket = "missing_fields"
        elif error_type == "extra_forbidden":
            bucket = "unexpected_fields"
        elif error_type in {"literal_error", "enum"}:
            bucket = "invalid_literal_fields"
        elif error_type in {
            "string_too_long", "string_too_short", "too_long", "too_short",
        }:
            bucket = "invalid_length_fields"
        elif error_type in {"string_pattern_mismatch"}:
            bucket = "invalid_format_fields"
        elif error_type.endswith("_type") or error_type in {
            "bool_parsing", "int_parsing", "string_unicode",
        }:
            bucket = "wrong_type_fields"
        else:
            bucket = "other_schema_paths"
        buckets[bucket].add(path)
    return GroupResultSchemaDiagnostic(**{
        name: tuple(sorted(values))[:MAX_SCHEMA_DIAGNOSTIC_ENTRIES]
        for name, values in buckets.items()
    })


def parse_group_advisory_result(
    raw_result: GroupAdvisoryResult | dict[str, Any],
) -> tuple[GroupAdvisoryResult | None, GroupResultSchemaDiagnostic]:
    """Use the authoritative result model and return value-free diagnostics."""
    if isinstance(raw_result, GroupAdvisoryResult):
        return raw_result, GroupResultSchemaDiagnostic()
    try:
        return GroupAdvisoryResult.model_validate(raw_result), GroupResultSchemaDiagnostic()
    except ValidationError as exc:
        return None, group_result_schema_diagnostic(exc)
    except Exception as exc:
        return None, group_result_schema_diagnostic(exc)


def validate_group_advisory_result(
    request: GroupAdvisoryRequest, raw_result: GroupAdvisoryResult | dict[str, Any]
) -> GroupAdvisoryResult:
    """Validate untrusted provider output; every failure becomes safe abstention."""
    result, _diagnostic = parse_group_advisory_result(raw_result)
    if result is None:
        return _inconclusive(request, ["SCHEMA_MISMATCH"])
    reasons = []
    expected_fingerprint = group_advisory_request_fingerprint(request)
    if result.request_fingerprint != expected_fingerprint:
        reasons.append("REQUEST_FINGERPRINT_MISMATCH")
    if result.group_snapshot_id != request.group_snapshot_id:
        reasons.append("GROUP_SNAPSHOT_MISMATCH")
    if result.group_hypothesis_key != request.group_hypothesis_key:
        reasons.append("GROUP_HYPOTHESIS_MISMATCH")
    members = {member.record_ref_key for member in request.members}
    blocks = result.proposed_partitions
    flattened = [ref for block in blocks for ref in block]
    if any(not block for block in blocks):
        reasons.append("EMPTY_PARTITION")
    if len(flattened) != len(set(flattened)):
        reasons.append("DUPLICATE_PARTITION_MEMBER")
    if set(flattened) - members:
        reasons.append("UNKNOWN_PARTITION_MEMBER")
    if result.outcome == GroupAdvisoryOutcome.INCONCLUSIVE:
        if blocks:
            reasons.append("INCONCLUSIVE_MUST_NOT_PARTITION")
    else:
        if set(flattened) != members:
            reasons.append("INCOMPLETE_PARTITION_MEMBERSHIP")
        if result.outcome == GroupAdvisoryOutcome.SUPPORTS_SINGLE_IDENTITY and len(blocks) != 1:
            reasons.append("SINGLE_IDENTITY_REQUIRES_ONE_SET")
        if result.outcome == GroupAdvisoryOutcome.PROPOSES_PARTITION and len(blocks) < 2:
            reasons.append("PARTITION_REQUIRES_MULTIPLE_SETS")
    cannot_pairs = {
        frozenset((edge.left_record_ref_key, edge.right_record_ref_key))
        for edge in request.internal_edges if edge.edge_class == "CANNOT_LINK"
    }
    if any(
        frozenset((left, right)) in cannot_pairs
        for block in blocks for index, left in enumerate(block) for right in block[index + 1:]
    ):
        reasons.append("PROTECTED_CANNOT_LINK_VIOLATION")
    if reasons:
        return _inconclusive(request, reasons)
    return result.model_copy(update={
        "proposed_partitions": tuple(
            sorted((tuple(sorted(block)) for block in blocks), key=lambda block: block[0])
        ),
        "requires_human_review": True,
        "deterministic_result_authoritative": True,
        "validation_reasons": (),
    })
