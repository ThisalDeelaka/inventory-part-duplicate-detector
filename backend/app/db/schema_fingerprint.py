"""Read-only, deterministic classification of supported SQLite schemas.

The canonical fingerprint is the SHA-256 of compact, UTF-8 JSON with sorted
mapping keys. Tables and constraint collections are sorted deterministically;
column order is preserved. A column entry contains its name, normalized
declared SQLite type (which preserves affinity-relevant text and lengths),
nullability, primary-key membership, and strict server default.

Conflict codes are stable identifiers: ``missing_managed_table``,
``missing_managed_column``, ``extra_managed_column``, ``column_order``,
``column_type``, ``column_nullability``, ``column_default``, ``primary_key``,
``foreign_key``, ``index``, ``unique_constraint``, ``check_constraint``,
``alembic_revision``, ``malformed_alembic_version``, and
``unrecognized_profile``.

This module only inspects a caller-supplied bind. It never creates an engine,
opens a path, runs Alembic, or mutates schema, data, or revision state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine


class SQLiteSchemaClassification(str, Enum):
    EMPTY = "EMPTY"
    CURRENT_ALEMBIC = "CURRENT_ALEMBIC"
    CURRENT_UNVERSIONED = "CURRENT_UNVERSIONED"
    RECOGNIZED_LEGACY = "RECOGNIZED_LEGACY"
    INCOMPLETE = "INCOMPLETE"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


class SQLiteSchemaProfileId(str, Enum):
    CURRENT_ALEMBIC_0001 = "current_alembic_0001"
    CURRENT_NAMED_UNVERSIONED = "current_named_unversioned"
    PROTECTED_BASELINE_UNNAMED = "protected_baseline_unnamed"
    HELPER_FROM_07C9A6E = "helper_from_07c9a6e"
    HELPER_FROM_00204E1 = "helper_from_00204e1"
    HELPER_FROM_FEE3F3D_OR_42FA7BA = "helper_from_fee3f3d_or_42fa7ba"


@dataclass(frozen=True, slots=True)
class SQLiteSchemaConflict:
    code: str
    path: str
    expected: str | None
    actual: str | None


@dataclass(frozen=True, slots=True)
class SQLiteSchemaClassificationResult:
    classification: SQLiteSchemaClassification
    profile_id: SQLiteSchemaProfileId | None
    managed_fingerprint_sha256: str
    alembic_revision: str | None
    extra_tables: tuple[str, ...]
    conflicts: tuple[SQLiteSchemaConflict, ...]


class UnsupportedSchemaDialectError(ValueError):
    pass


MANAGED_TABLES = (
    "duplicate_candidate",
    "duplicate_feedback",
    "duplicate_scan",
    "rule_exclusion_audit",
    "scan_warning",
)

CURRENT_REVISION = "0001_current_schema"

CURRENT_NAMED_FINGERPRINT = (
    "d4300dc7f7c1282534978f2bc6b9883dd375585bfe4d24ab54d49e5550303e2b"
)
PROTECTED_BASELINE_FINGERPRINT = (
    "98b2998cfaacbed14a334722729a10d863369f52aed72825fd75e0dc9d05deb3"
)
HELPER_07C9A6E_FINGERPRINT = (
    "f182f4a801bd37d9774a24b038d245d6bdda54aff86da5c4abee85b086588b9c"
)
HELPER_00204E1_FINGERPRINT = (
    "67ebb0814a651343b8b1427c76771a7ec412ca0bbb3ab2360f082a6f4ea6ab90"
)
HELPER_FEE3F3D_FINGERPRINT = (
    "335199b9d4faca6950125c2014743fb817884d55db4994d48de307087a4530db"
)

APPROVED_PROFILE_FINGERPRINTS: Mapping[SQLiteSchemaProfileId, str] = (
    MappingProxyType(
        {
            SQLiteSchemaProfileId.CURRENT_ALEMBIC_0001:
                CURRENT_NAMED_FINGERPRINT,
            SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED:
                CURRENT_NAMED_FINGERPRINT,
            SQLiteSchemaProfileId.PROTECTED_BASELINE_UNNAMED:
                PROTECTED_BASELINE_FINGERPRINT,
            SQLiteSchemaProfileId.HELPER_FROM_07C9A6E:
                HELPER_07C9A6E_FINGERPRINT,
            SQLiteSchemaProfileId.HELPER_FROM_00204E1:
                HELPER_00204E1_FINGERPRINT,
            SQLiteSchemaProfileId.HELPER_FROM_FEE3F3D_OR_42FA7BA:
                HELPER_FEE3F3D_FINGERPRINT,
        }
    )
)

_UNVERSIONED_PROFILE_BY_FINGERPRINT = MappingProxyType(
    {
        CURRENT_NAMED_FINGERPRINT:
            SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED,
        PROTECTED_BASELINE_FINGERPRINT:
            SQLiteSchemaProfileId.PROTECTED_BASELINE_UNNAMED,
        HELPER_07C9A6E_FINGERPRINT:
            SQLiteSchemaProfileId.HELPER_FROM_07C9A6E,
        HELPER_00204E1_FINGERPRINT:
            SQLiteSchemaProfileId.HELPER_FROM_00204E1,
        HELPER_FEE3F3D_FINGERPRINT:
            SQLiteSchemaProfileId.HELPER_FROM_FEE3F3D_OR_42FA7BA,
    }
)

_CURRENT_ORDERS = {
    "duplicate_scan": (
        "id", "scan_name", "source_type", "selected_fields", "threshold",
        "status", "total_records", "total_candidates", "warnings_count",
        "rejections_count", "scan_mode", "started_at", "completed_at",
        "model_version",
    ),
    "duplicate_candidate": (
        "id", "scan_id", "contract_a", "part_no_a", "description_a",
        "contract_b", "part_no_b", "description_b", "similarity_score",
        "confidence_level", "description_similarity", "tfidf_score",
        "fuzzy_score", "part_no_similarity", "technical_token_score",
        "matched_fields", "mismatched_fields", "explanation",
        "recommended_action", "business_status", "rule_decision",
        "rejection_reason", "scan_mode", "critical_mismatches",
        "variant_attributes_a", "variant_attributes_b",
        "generic_description_warning", "application_context_a",
        "application_context_b", "application_context_warning",
        "normalized_description_a", "normalized_description_b",
        "normalized_part_no_a", "normalized_part_no_b", "review_status",
        "reviewed_by", "reviewed_at",
    ),
    "duplicate_feedback": (
        "id", "candidate_id", "user_decision", "user_comment", "created_by",
        "created_at",
    ),
    "scan_warning": (
        "id", "scan_id", "warning_type", "message", "record_reference",
        "created_at",
    ),
    "rule_exclusion_audit": (
        "id", "scan_id", "contract_a", "part_no_a", "description_a",
        "contract_b", "part_no_b", "description_b", "similarity_score",
        "confidence_level", "business_status", "rule_decision",
        "rejection_reason", "critical_mismatches", "explanation",
        "created_at",
    ),
}

_COLUMN_DEFINITIONS = {
    "duplicate_scan": {
        "id": ("INTEGER", False, True),
        "scan_name": ("VARCHAR(200)", False, False),
        "source_type": ("VARCHAR(30)", False, False),
        "selected_fields": ("TEXT", False, False),
        "threshold": ("FLOAT", False, False),
        "status": ("VARCHAR(30)", False, False),
        "total_records": ("INTEGER", True, False),
        "total_candidates": ("INTEGER", True, False),
        "warnings_count": ("INTEGER", True, False),
        "rejections_count": ("INTEGER", True, False),
        "scan_mode": ("VARCHAR(60)", False, False),
        "started_at": ("DATETIME", False, False),
        "completed_at": ("DATETIME", True, False),
        "model_version": ("VARCHAR(50)", False, False),
    },
    "duplicate_candidate": {
        "id": ("INTEGER", False, True),
        "scan_id": ("INTEGER", False, False),
        "contract_a": ("VARCHAR(100)", True, False),
        "part_no_a": ("VARCHAR(200)", False, False),
        "description_a": ("TEXT", False, False),
        "contract_b": ("VARCHAR(100)", True, False),
        "part_no_b": ("VARCHAR(200)", False, False),
        "description_b": ("TEXT", False, False),
        "similarity_score": ("FLOAT", False, False),
        "confidence_level": ("VARCHAR(20)", False, False),
        "description_similarity": ("FLOAT", False, False),
        "tfidf_score": ("FLOAT", False, False),
        "fuzzy_score": ("FLOAT", False, False),
        "part_no_similarity": ("FLOAT", False, False),
        "technical_token_score": ("FLOAT", False, False),
        "matched_fields": ("TEXT", True, False),
        "mismatched_fields": ("TEXT", True, False),
        "explanation": ("TEXT", False, False),
        "recommended_action": ("VARCHAR(200)", False, False),
        "business_status": ("VARCHAR(80)", False, False),
        "rule_decision": ("VARCHAR(50)", False, False),
        "rejection_reason": ("VARCHAR(120)", True, False),
        "scan_mode": ("VARCHAR(60)", False, False),
        "critical_mismatches": ("TEXT", True, False),
        "variant_attributes_a": ("TEXT", True, False),
        "variant_attributes_b": ("TEXT", True, False),
        "generic_description_warning": ("VARCHAR(10)", True, False),
        "application_context_a": ("TEXT", True, False),
        "application_context_b": ("TEXT", True, False),
        "application_context_warning": ("VARCHAR(10)", True, False),
        "normalized_description_a": ("TEXT", True, False),
        "normalized_description_b": ("TEXT", True, False),
        "normalized_part_no_a": ("TEXT", True, False),
        "normalized_part_no_b": ("TEXT", True, False),
        "review_status": ("VARCHAR(30)", False, False),
        "reviewed_by": ("VARCHAR(100)", True, False),
        "reviewed_at": ("DATETIME", True, False),
    },
    "duplicate_feedback": {
        "id": ("INTEGER", False, True),
        "candidate_id": ("INTEGER", False, False),
        "user_decision": ("VARCHAR(30)", False, False),
        "user_comment": ("TEXT", True, False),
        "created_by": ("VARCHAR(100)", False, False),
        "created_at": ("DATETIME", False, False),
    },
    "scan_warning": {
        "id": ("INTEGER", False, True),
        "scan_id": ("INTEGER", False, False),
        "warning_type": ("VARCHAR(80)", False, False),
        "message": ("TEXT", False, False),
        "record_reference": ("VARCHAR(200)", True, False),
        "created_at": ("DATETIME", False, False),
    },
    "rule_exclusion_audit": {
        "id": ("INTEGER", False, True),
        "scan_id": ("INTEGER", False, False),
        "contract_a": ("VARCHAR(100)", True, False),
        "part_no_a": ("VARCHAR(200)", False, False),
        "description_a": ("TEXT", False, False),
        "contract_b": ("VARCHAR(100)", True, False),
        "part_no_b": ("VARCHAR(200)", False, False),
        "description_b": ("TEXT", False, False),
        "similarity_score": ("FLOAT", False, False),
        "confidence_level": ("VARCHAR(20)", False, False),
        "business_status": ("VARCHAR(80)", False, False),
        "rule_decision": ("VARCHAR(50)", False, False),
        "rejection_reason": ("VARCHAR(120)", False, False),
        "critical_mismatches": ("TEXT", True, False),
        "explanation": ("TEXT", False, False),
        "created_at": ("DATETIME", False, False),
    },
}

_FOREIGN_KEYS = {
    "duplicate_candidate": ("scan_id", "duplicate_scan"),
    "duplicate_feedback": ("candidate_id", "duplicate_candidate"),
    "rule_exclusion_audit": ("scan_id", "duplicate_scan"),
    "scan_warning": ("scan_id", "duplicate_scan"),
}

_INDEXED_COLUMNS = {
    "duplicate_candidate": "scan_id",
    "duplicate_feedback": "candidate_id",
    "rule_exclusion_audit": "scan_id",
    "scan_warning": "scan_id",
}

_HELPER_07_SCAN_ORDER = (
    "id", "scan_name", "source_type", "selected_fields", "threshold",
    "status", "total_records", "total_candidates", "warnings_count",
    "started_at", "completed_at", "model_version", "scan_mode",
    "rejections_count",
)
_HELPER_07_CANDIDATE_ORDER = (
    "id", "scan_id", "contract_a", "part_no_a", "description_a",
    "contract_b", "part_no_b", "description_b", "similarity_score",
    "confidence_level", "description_similarity", "tfidf_score",
    "fuzzy_score", "part_no_similarity", "technical_token_score",
    "matched_fields", "mismatched_fields", "explanation",
    "recommended_action", "review_status", "reviewed_by", "reviewed_at",
    "business_status", "rule_decision", "rejection_reason", "scan_mode",
    "critical_mismatches", "variant_attributes_a", "variant_attributes_b",
    "generic_description_warning", "application_context_a",
    "application_context_b", "application_context_warning",
    "normalized_description_a", "normalized_description_b",
    "normalized_part_no_a", "normalized_part_no_b",
)
_HELPER_002_CANDIDATE_ORDER = (
    "id", "scan_id", "contract_a", "part_no_a", "description_a",
    "contract_b", "part_no_b", "description_b", "similarity_score",
    "confidence_level", "description_similarity", "tfidf_score",
    "fuzzy_score", "part_no_similarity", "technical_token_score",
    "matched_fields", "mismatched_fields", "explanation",
    "recommended_action", "business_status", "rule_decision",
    "rejection_reason", "scan_mode", "critical_mismatches",
    "variant_attributes_a", "variant_attributes_b", "review_status",
    "reviewed_by", "reviewed_at", "generic_description_warning",
    "application_context_a", "application_context_b",
    "application_context_warning", "normalized_description_a",
    "normalized_description_b", "normalized_part_no_a",
    "normalized_part_no_b",
)
_HELPER_LATER_SCAN_ORDER = (
    "id", "scan_name", "source_type", "selected_fields", "threshold",
    "status", "total_records", "total_candidates", "warnings_count",
    "scan_mode", "started_at", "completed_at", "model_version",
    "rejections_count",
)

_HELPER_07_DEFAULTS = {
    "duplicate_scan": {
        "scan_mode": "'SAME_SITE_DUPLICATE'",
        "rejections_count": "0",
    },
    "duplicate_candidate": {
        "business_status": "'POSSIBLE_DUPLICATE_REVIEW'",
        "rule_decision": "'ALLOW'",
        "rejection_reason": "''",
        "scan_mode": "'SAME_SITE_DUPLICATE'",
        "critical_mismatches": "'[]'",
        "variant_attributes_a": "'{}'",
        "variant_attributes_b": "'{}'",
        "generic_description_warning": "'false'",
        "application_context_a": "'[]'",
        "application_context_b": "'[]'",
        "application_context_warning": "'false'",
        "normalized_description_a": "''",
        "normalized_description_b": "''",
        "normalized_part_no_a": "''",
        "normalized_part_no_b": "''",
    },
}
_HELPER_002_DEFAULTS = {
    "duplicate_scan": {"rejections_count": "0"},
    "duplicate_candidate": {
        "generic_description_warning": "'false'",
        "application_context_a": "'[]'",
        "application_context_b": "'[]'",
        "application_context_warning": "'false'",
        "normalized_description_a": "''",
        "normalized_description_b": "''",
        "normalized_part_no_a": "''",
        "normalized_part_no_b": "''",
    },
}
_HELPER_LATER_DEFAULTS = {
    "duplicate_scan": {"rejections_count": "0"},
}

_VALID_REVISION = re.compile(r"^[A-Za-z0-9_]+$")


def _normalize_declared_type(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def _sqlite_affinity(declared_type: str) -> str:
    value = declared_type.upper()
    if "INT" in value:
        return "INTEGER"
    if any(token in value for token in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if "BLOB" in value or not value:
        return "BLOB"
    if any(token in value for token in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _normalize_default(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


def _canonical_json_bytes(schema: Mapping[str, Any]) -> bytes:
    return _stable_json(schema).encode("utf-8")


def _fingerprint(schema: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(schema)).hexdigest()


def _sort_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=_stable_json)


def _canonical_schema(connection: Connection) -> dict[str, Any]:
    inspector = inspect(connection)
    present = set(inspector.get_table_names())
    result: dict[str, Any] = {}
    for table in sorted(present.intersection(MANAGED_TABLES)):
        columns = [
            (
                column["name"],
                _normalize_declared_type(column["type"]),
                bool(column["nullable"]),
                bool(column["primary_key"]),
                _normalize_default(column["default"]),
            )
            for column in inspector.get_columns(table)
        ]
        primary_key = inspector.get_pk_constraint(table)
        primary_key = {
            "constrained_columns": list(
                primary_key.get("constrained_columns") or []
            ),
            "name": primary_key.get("name"),
        }
        foreign_keys = _sort_items([
            {
                "name": item.get("name"),
                "constrained_columns": list(
                    item.get("constrained_columns") or []
                ),
                "referred_schema": item.get("referred_schema"),
                "referred_table": item.get("referred_table"),
                "referred_columns": list(item.get("referred_columns") or []),
                "options": dict(item.get("options") or {}),
            }
            for item in inspector.get_foreign_keys(table)
        ])
        indexes = _sort_items([
            {
                "name": item.get("name"),
                "column_names": list(item.get("column_names") or []),
                "unique": item.get("unique"),
                "dialect_options": dict(item.get("dialect_options") or {}),
            }
            for item in inspector.get_indexes(table)
        ])
        unique_constraints = _sort_items([
            {
                key: item[key]
                for key in sorted(item)
            }
            for item in inspector.get_unique_constraints(table)
        ])
        check_constraints = _sort_items([
            {
                key: item[key]
                for key in sorted(item)
            }
            for item in inspector.get_check_constraints(table)
        ])
        result[table] = {
            "c": columns,
            "pk": primary_key,
            "fk": foreign_keys,
            "ix": indexes,
            "uq": unique_constraints,
            "ck": check_constraints,
        }
    return result


def _expected_profile(
    *,
    named: bool,
    scan_order: tuple[str, ...],
    candidate_order: tuple[str, ...],
    defaults: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    orders = dict(_CURRENT_ORDERS)
    orders["duplicate_scan"] = scan_order
    orders["duplicate_candidate"] = candidate_order
    result: dict[str, Any] = {}
    for table in MANAGED_TABLES:
        columns = []
        for column in orders[table]:
            declared_type, nullable, primary_key = _COLUMN_DEFINITIONS[
                table
            ][column]
            columns.append(
                (
                    column,
                    declared_type,
                    nullable,
                    primary_key,
                    defaults.get(table, {}).get(column),
                )
            )
        pk_name = f"pk_{table}" if named else None
        foreign_keys: list[dict[str, Any]] = []
        if table in _FOREIGN_KEYS:
            column, target = _FOREIGN_KEYS[table]
            foreign_keys.append(
                {
                    "name": (
                        f"fk_{table}_{column}_{target}" if named else None
                    ),
                    "constrained_columns": [column],
                    "referred_schema": None,
                    "referred_table": target,
                    "referred_columns": ["id"],
                    "options": {},
                }
            )
        indexes: list[dict[str, Any]] = []
        if table in _INDEXED_COLUMNS:
            column = _INDEXED_COLUMNS[table]
            indexes.append(
                {
                    "name": f"ix_{table}_{column}",
                    "column_names": [column],
                    "unique": 0,
                    "dialect_options": {},
                }
            )
        result[table] = {
            "c": columns,
            "pk": {"constrained_columns": ["id"], "name": pk_name},
            "fk": foreign_keys,
            "ix": indexes,
            "uq": [],
            "ck": [],
        }
    return result


def _profile_catalog() -> tuple[
    tuple[SQLiteSchemaProfileId, dict[str, Any]], ...
]:
    return (
        (
            SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED,
            _expected_profile(
                named=True,
                scan_order=_CURRENT_ORDERS["duplicate_scan"],
                candidate_order=_CURRENT_ORDERS["duplicate_candidate"],
                defaults={},
            ),
        ),
        (
            SQLiteSchemaProfileId.PROTECTED_BASELINE_UNNAMED,
            _expected_profile(
                named=False,
                scan_order=_CURRENT_ORDERS["duplicate_scan"],
                candidate_order=_CURRENT_ORDERS["duplicate_candidate"],
                defaults={},
            ),
        ),
        (
            SQLiteSchemaProfileId.HELPER_FROM_07C9A6E,
            _expected_profile(
                named=False,
                scan_order=_HELPER_07_SCAN_ORDER,
                candidate_order=_HELPER_07_CANDIDATE_ORDER,
                defaults=_HELPER_07_DEFAULTS,
            ),
        ),
        (
            SQLiteSchemaProfileId.HELPER_FROM_00204E1,
            _expected_profile(
                named=False,
                scan_order=_HELPER_LATER_SCAN_ORDER,
                candidate_order=_HELPER_002_CANDIDATE_ORDER,
                defaults=_HELPER_002_DEFAULTS,
            ),
        ),
        (
            SQLiteSchemaProfileId.HELPER_FROM_FEE3F3D_OR_42FA7BA,
            _expected_profile(
                named=False,
                scan_order=_HELPER_LATER_SCAN_ORDER,
                candidate_order=_CURRENT_ORDERS["duplicate_candidate"],
                defaults=_HELPER_LATER_DEFAULTS,
            ),
        ),
    )


def _display(value: Any) -> str:
    return _stable_json(value)


def _profile_conflicts(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> list[SQLiteSchemaConflict]:
    conflicts: list[SQLiteSchemaConflict] = []
    for table in MANAGED_TABLES:
        if table not in actual:
            continue
        actual_table = actual[table]
        expected_table = expected[table]
        actual_columns = {item[0]: item for item in actual_table["c"]}
        expected_columns = {item[0]: item for item in expected_table["c"]}
        actual_order = tuple(item[0] for item in actual_table["c"])
        expected_order = tuple(item[0] for item in expected_table["c"])
        if (
            set(actual_order) == set(expected_order)
            and actual_order != expected_order
        ):
            conflicts.append(
                SQLiteSchemaConflict(
                    "column_order",
                    f"{table}.columns",
                    ",".join(expected_order),
                    ",".join(actual_order),
                )
            )
        for column in expected_order:
            if column not in actual_columns:
                continue
            expected_item = expected_columns[column]
            actual_item = actual_columns[column]
            expected_type = expected_item[1]
            actual_type = actual_item[1]
            if (
                expected_type != actual_type
                or _sqlite_affinity(expected_type)
                != _sqlite_affinity(actual_type)
            ):
                conflicts.append(
                    SQLiteSchemaConflict(
                        "column_type",
                        f"{table}.{column}.type",
                        expected_type,
                        actual_type,
                    )
                )
            if expected_item[2] != actual_item[2]:
                conflicts.append(
                    SQLiteSchemaConflict(
                        "column_nullability",
                        f"{table}.{column}.nullable",
                        str(expected_item[2]).lower(),
                        str(actual_item[2]).lower(),
                    )
                )
            if expected_item[4] != actual_item[4]:
                conflicts.append(
                    SQLiteSchemaConflict(
                        "column_default",
                        f"{table}.{column}.default",
                        expected_item[4],
                        actual_item[4],
                    )
                )
        for key, code, suffix in (
            ("pk", "primary_key", "primary_key"),
            ("fk", "foreign_key", "foreign_keys"),
            ("ix", "index", "indexes"),
            ("uq", "unique_constraint", "unique_constraints"),
            ("ck", "check_constraint", "check_constraints"),
        ):
            if expected_table[key] != actual_table[key]:
                conflicts.append(
                    SQLiteSchemaConflict(
                        code,
                        f"{table}.{suffix}",
                        _display(expected_table[key]),
                        _display(actual_table[key]),
                    )
                )
    return conflicts


def _missing_and_extra_column_conflicts(
    schema: Mapping[str, Any],
    present_tables: set[str],
) -> tuple[list[SQLiteSchemaConflict], list[SQLiteSchemaConflict]]:
    missing: list[SQLiteSchemaConflict] = []
    extra: list[SQLiteSchemaConflict] = []
    for table in MANAGED_TABLES:
        if table not in present_tables:
            missing.append(
                SQLiteSchemaConflict(
                    "missing_managed_table", table, "present", None
                )
            )
            continue
        actual_names = {item[0] for item in schema[table]["c"]}
        expected_names = set(_COLUMN_DEFINITIONS[table])
        for column in sorted(expected_names - actual_names):
            missing.append(
                SQLiteSchemaConflict(
                    "missing_managed_column",
                    f"{table}.{column}",
                    "present",
                    None,
                )
            )
        for column in sorted(actual_names - expected_names):
            extra.append(
                SQLiteSchemaConflict(
                    "extra_managed_column",
                    f"{table}.{column}",
                    None,
                    "present",
                )
            )
    return missing, extra


def _inspect_revision(
    connection: Connection,
    table_names: set[str],
) -> tuple[str | None, SQLiteSchemaConflict | None]:
    if "alembic_version" not in table_names:
        return None, None
    columns = {
        item["name"] for item in inspect(connection).get_columns(
            "alembic_version"
        )
    }
    if "version_num" not in columns:
        return None, SQLiteSchemaConflict(
            "malformed_alembic_version",
            "alembic_version.version_num",
            "exactly one non-empty string row",
            "missing column",
        )
    rows = connection.execute(
        text('SELECT version_num FROM "alembic_version"')
    ).all()
    if len(rows) != 1:
        return None, SQLiteSchemaConflict(
            "malformed_alembic_version",
            "alembic_version.version_num",
            "exactly one non-empty string row",
            f"{len(rows)} rows",
        )
    value = rows[0][0]
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or _VALID_REVISION.fullmatch(value) is None
    ):
        return None, SQLiteSchemaConflict(
            "malformed_alembic_version",
            "alembic_version.version_num",
            "one non-empty revision string",
            None if value is None else str(value),
        )
    if value != CURRENT_REVISION:
        return value, SQLiteSchemaConflict(
            "alembic_revision",
            "alembic_version.version_num",
            CURRENT_REVISION,
            value,
        )
    return value, None


def _classify_connection(
    connection: Connection,
) -> SQLiteSchemaClassificationResult:
    inspector = inspect(connection)
    all_tables = set(inspector.get_table_names())
    present_managed = all_tables.intersection(MANAGED_TABLES)
    extra_tables = tuple(
        sorted(all_tables - set(MANAGED_TABLES) - {"alembic_version"})
    )
    schema = _canonical_schema(connection)
    fingerprint = _fingerprint(schema)
    revision, revision_conflict = _inspect_revision(connection, all_tables)
    missing, extra_columns = _missing_and_extra_column_conflicts(
        schema, present_managed
    )
    is_empty = (
        not present_managed
        and revision is None
        and revision_conflict is None
    )

    profile_id: SQLiteSchemaProfileId | None = None
    managed_conflicts: list[SQLiteSchemaConflict] = []
    matching_profile = (
        _UNVERSIONED_PROFILE_BY_FINGERPRINT.get(fingerprint)
        if not missing and not extra_columns
        else None
    )
    if matching_profile is None and present_managed:
        candidates = [
            (
                _profile_conflicts(schema, expected),
                candidate_profile,
            )
            for candidate_profile, expected in _profile_catalog()
        ]
        managed_conflicts, _nearest = min(
            candidates,
            key=lambda item: (len(item[0]), item[1].value),
        )
        if not managed_conflicts and not missing and not extra_columns:
            managed_conflicts.append(
                SQLiteSchemaConflict(
                    "unrecognized_profile",
                    "managed_schema",
                    "an approved exact fingerprint",
                    fingerprint,
                )
            )

    conflicts = (
        ([] if is_empty else list(missing))
        + list(extra_columns)
        + managed_conflicts
    )
    if revision_conflict is not None:
        conflicts.append(revision_conflict)

    if revision_conflict is not None:
        classification = SQLiteSchemaClassification.UNKNOWN
    elif is_empty:
        classification = SQLiteSchemaClassification.EMPTY
    elif missing:
        classification = SQLiteSchemaClassification.INCOMPLETE
    elif extra_columns:
        classification = SQLiteSchemaClassification.UNKNOWN
    elif (
        revision == CURRENT_REVISION
        and fingerprint == CURRENT_NAMED_FINGERPRINT
        and not managed_conflicts
    ):
        classification = SQLiteSchemaClassification.CURRENT_ALEMBIC
        profile_id = SQLiteSchemaProfileId.CURRENT_ALEMBIC_0001
    elif revision is None and fingerprint in _UNVERSIONED_PROFILE_BY_FINGERPRINT:
        profile_id = _UNVERSIONED_PROFILE_BY_FINGERPRINT[fingerprint]
        classification = (
            SQLiteSchemaClassification.CURRENT_UNVERSIONED
            if profile_id in {
                SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED,
                SQLiteSchemaProfileId.PROTECTED_BASELINE_UNNAMED,
            }
            else SQLiteSchemaClassification.RECOGNIZED_LEGACY
        )
    elif managed_conflicts:
        classification = SQLiteSchemaClassification.INCOMPATIBLE
    else:
        classification = SQLiteSchemaClassification.UNKNOWN
        conflicts.append(
            SQLiteSchemaConflict(
                "unrecognized_profile",
                "managed_schema",
                "an approved exact fingerprint",
                fingerprint,
            )
        )

    return SQLiteSchemaClassificationResult(
        classification=classification,
        profile_id=profile_id,
        managed_fingerprint_sha256=fingerprint,
        alembic_revision=revision,
        extra_tables=extra_tables,
        conflicts=tuple(
            sorted(
                conflicts,
                key=lambda item: (
                    item.code,
                    item.path,
                    item.expected or "",
                    item.actual or "",
                ),
            )
        ),
    )


def classify_sqlite_schema(
    bind: Engine | Connection,
) -> SQLiteSchemaClassificationResult:
    """Classify a caller-owned SQLite bind without mutating or disposing it."""
    if not isinstance(bind, (Engine, Connection)):
        raise TypeError("bind must be a SQLAlchemy Engine or Connection")
    if bind.dialect.name != "sqlite":
        raise UnsupportedSchemaDialectError(
            f"unsupported schema dialect: {bind.dialect.name}"
        )
    if isinstance(bind, Connection):
        return _classify_connection(bind)
    with bind.connect() as connection:
        return _classify_connection(connection)
