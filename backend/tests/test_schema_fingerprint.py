from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401 - registers current metadata
from app.db.database import Base
from app.db.models import LEGACY_STARTUP_TABLES
from app.db.schema_fingerprint import (
    APPROVED_PROFILE_FINGERPRINTS,
    SQLiteSchemaClassification,
    SQLiteSchemaClassificationResult,
    SQLiteSchemaConflict,
    SQLiteSchemaProfileId,
    UnsupportedSchemaDialectError,
    _canonical_json_bytes,
    _canonical_schema,
    classify_sqlite_schema,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MANAGED_TABLES = {
    "duplicate_scan",
    "duplicate_candidate",
    "duplicate_feedback",
    "scan_warning",
    "rule_exclusion_audit",
}
EXPECTED_HASHES = {
    "current": "d4300dc7f7c1282534978f2bc6b9883dd375585bfe4d24ab54d49e5550303e2b",
    "protected": "98b2998cfaacbed14a334722729a10d863369f52aed72825fd75e0dc9d05deb3",
    "07": "f182f4a801bd37d9774a24b038d245d6bdda54aff86da5c4abee85b086588b9c",
    "002": "67ebb0814a651343b8b1427c76771a7ec412ca0bbb3ab2360f082a6f4ea6ab90",
    "later": "335199b9d4faca6950125c2014743fb817884d55db4994d48de307087a4530db",
}
EXPECTED_CANONICAL_LENGTHS = {
    "current": 5384,
    "protected": 5121,
    "07": 5208,
    "002": 5134,
    "later": 5120,
}

CURRENT_ORDERS = {
    "duplicate_scan": [
        "id", "scan_name", "source_type", "selected_fields", "threshold",
        "status", "total_records", "total_candidates", "warnings_count",
        "rejections_count", "scan_mode", "started_at", "completed_at",
        "model_version",
    ],
    "duplicate_candidate": [
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
    ],
    "duplicate_feedback": [
        "id", "candidate_id", "user_decision", "user_comment", "created_by",
        "created_at",
    ],
    "scan_warning": [
        "id", "scan_id", "warning_type", "message", "record_reference",
        "created_at",
    ],
    "rule_exclusion_audit": [
        "id", "scan_id", "contract_a", "part_no_a", "description_a",
        "contract_b", "part_no_b", "description_b", "similarity_score",
        "confidence_level", "business_status", "rule_decision",
        "rejection_reason", "critical_mismatches", "explanation",
        "created_at",
    ],
}

COLUMN_SQL = {
    "duplicate_scan": {
        "id": "INTEGER NOT NULL",
        "scan_name": "VARCHAR(200) NOT NULL",
        "source_type": "VARCHAR(30) NOT NULL",
        "selected_fields": "TEXT NOT NULL",
        "threshold": "FLOAT NOT NULL",
        "status": "VARCHAR(30) NOT NULL",
        "total_records": "INTEGER",
        "total_candidates": "INTEGER",
        "warnings_count": "INTEGER",
        "rejections_count": "INTEGER",
        "scan_mode": "VARCHAR(60) NOT NULL",
        "started_at": "DATETIME NOT NULL",
        "completed_at": "DATETIME",
        "model_version": "VARCHAR(50) NOT NULL",
    },
    "duplicate_candidate": {
        "id": "INTEGER NOT NULL",
        "scan_id": "INTEGER NOT NULL",
        "contract_a": "VARCHAR(100)",
        "part_no_a": "VARCHAR(200) NOT NULL",
        "description_a": "TEXT NOT NULL",
        "contract_b": "VARCHAR(100)",
        "part_no_b": "VARCHAR(200) NOT NULL",
        "description_b": "TEXT NOT NULL",
        "similarity_score": "FLOAT NOT NULL",
        "confidence_level": "VARCHAR(20) NOT NULL",
        "description_similarity": "FLOAT NOT NULL",
        "tfidf_score": "FLOAT NOT NULL",
        "fuzzy_score": "FLOAT NOT NULL",
        "part_no_similarity": "FLOAT NOT NULL",
        "technical_token_score": "FLOAT NOT NULL",
        "matched_fields": "TEXT",
        "mismatched_fields": "TEXT",
        "explanation": "TEXT NOT NULL",
        "recommended_action": "VARCHAR(200) NOT NULL",
        "business_status": "VARCHAR(80) NOT NULL",
        "rule_decision": "VARCHAR(50) NOT NULL",
        "rejection_reason": "VARCHAR(120)",
        "scan_mode": "VARCHAR(60) NOT NULL",
        "critical_mismatches": "TEXT",
        "variant_attributes_a": "TEXT",
        "variant_attributes_b": "TEXT",
        "generic_description_warning": "VARCHAR(10)",
        "application_context_a": "TEXT",
        "application_context_b": "TEXT",
        "application_context_warning": "VARCHAR(10)",
        "normalized_description_a": "TEXT",
        "normalized_description_b": "TEXT",
        "normalized_part_no_a": "TEXT",
        "normalized_part_no_b": "TEXT",
        "review_status": "VARCHAR(30) NOT NULL",
        "reviewed_by": "VARCHAR(100)",
        "reviewed_at": "DATETIME",
    },
    "duplicate_feedback": {
        "id": "INTEGER NOT NULL",
        "candidate_id": "INTEGER NOT NULL",
        "user_decision": "VARCHAR(30) NOT NULL",
        "user_comment": "TEXT",
        "created_by": "VARCHAR(100) NOT NULL",
        "created_at": "DATETIME NOT NULL",
    },
    "scan_warning": {
        "id": "INTEGER NOT NULL",
        "scan_id": "INTEGER NOT NULL",
        "warning_type": "VARCHAR(80) NOT NULL",
        "message": "TEXT NOT NULL",
        "record_reference": "VARCHAR(200)",
        "created_at": "DATETIME NOT NULL",
    },
    "rule_exclusion_audit": {
        "id": "INTEGER NOT NULL",
        "scan_id": "INTEGER NOT NULL",
        "contract_a": "VARCHAR(100)",
        "part_no_a": "VARCHAR(200) NOT NULL",
        "description_a": "TEXT NOT NULL",
        "contract_b": "VARCHAR(100)",
        "part_no_b": "VARCHAR(200) NOT NULL",
        "description_b": "TEXT NOT NULL",
        "similarity_score": "FLOAT NOT NULL",
        "confidence_level": "VARCHAR(20) NOT NULL",
        "business_status": "VARCHAR(80) NOT NULL",
        "rule_decision": "VARCHAR(50) NOT NULL",
        "rejection_reason": "VARCHAR(120) NOT NULL",
        "critical_mismatches": "TEXT",
        "explanation": "TEXT NOT NULL",
        "created_at": "DATETIME NOT NULL",
    },
}

FOREIGN_KEYS = {
    "duplicate_candidate": ("scan_id", "duplicate_scan"),
    "duplicate_feedback": ("candidate_id", "duplicate_candidate"),
    "scan_warning": ("scan_id", "duplicate_scan"),
    "rule_exclusion_audit": ("scan_id", "duplicate_scan"),
}
INDEXES = {
    "duplicate_candidate": "scan_id",
    "duplicate_feedback": "candidate_id",
    "scan_warning": "scan_id",
    "rule_exclusion_audit": "scan_id",
}

HELPER_07_SCAN_ORDER = [
    "id", "scan_name", "source_type", "selected_fields", "threshold",
    "status", "total_records", "total_candidates", "warnings_count",
    "started_at", "completed_at", "model_version", "scan_mode",
    "rejections_count",
]
HELPER_LATER_SCAN_ORDER = [
    "id", "scan_name", "source_type", "selected_fields", "threshold",
    "status", "total_records", "total_candidates", "warnings_count",
    "scan_mode", "started_at", "completed_at", "model_version",
    "rejections_count",
]
HELPER_07_CANDIDATE_ORDER = [
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
]
HELPER_002_CANDIDATE_ORDER = [
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
]
HELPER_07_DEFAULTS = {
    "duplicate_scan": {
        "scan_mode": "'SAME_SITE_DUPLICATE'", "rejections_count": "0",
    },
    "duplicate_candidate": {
        "business_status": "'POSSIBLE_DUPLICATE_REVIEW'",
        "rule_decision": "'ALLOW'", "rejection_reason": "''",
        "scan_mode": "'SAME_SITE_DUPLICATE'", "critical_mismatches": "'[]'",
        "variant_attributes_a": "'{}'", "variant_attributes_b": "'{}'",
        "generic_description_warning": "'false'",
        "application_context_a": "'[]'", "application_context_b": "'[]'",
        "application_context_warning": "'false'",
        "normalized_description_a": "''", "normalized_description_b": "''",
        "normalized_part_no_a": "''", "normalized_part_no_b": "''",
    },
}
HELPER_002_DEFAULTS = {
    "duplicate_scan": {"rejections_count": "0"},
    "duplicate_candidate": {
        "generic_description_warning": "'false'",
        "application_context_a": "'[]'", "application_context_b": "'[]'",
        "application_context_warning": "'false'",
        "normalized_description_a": "''", "normalized_description_b": "''",
        "normalized_part_no_a": "''", "normalized_part_no_b": "''",
    },
}
HELPER_LATER_DEFAULTS = {
    "duplicate_scan": {"rejections_count": "0"},
}


def _memory_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_literal_profile(
    engine,
    *,
    named=False,
    scan_order=None,
    candidate_order=None,
    defaults=None,
    omit_table=None,
    omit_column=None,
    extra_column=None,
    column_sql_override=None,
    swap_columns=None,
    pk_name_override=None,
    fk_override=None,
    index_override=None,
    extra_unique=False,
    extra_check=False,
):
    orders = {table: list(columns) for table, columns in CURRENT_ORDERS.items()}
    if scan_order is not None:
        orders["duplicate_scan"] = list(scan_order)
    if candidate_order is not None:
        orders["duplicate_candidate"] = list(candidate_order)
    if omit_column:
        table, column = omit_column
        orders[table].remove(column)
    if swap_columns:
        table, left, right = swap_columns
        li, ri = orders[table].index(left), orders[table].index(right)
        orders[table][li], orders[table][ri] = (
            orders[table][ri],
            orders[table][li],
        )
    defaults = defaults or {}
    column_sql_override = column_sql_override or {}
    fk_override = fk_override or {}
    index_override = index_override or {}
    with engine.begin() as connection:
        for table in (
            "duplicate_scan",
            "duplicate_candidate",
            "duplicate_feedback",
            "scan_warning",
            "rule_exclusion_audit",
        ):
            if table == omit_table:
                continue
            definitions = []
            for column in orders[table]:
                definition = column_sql_override.get(
                    (table, column), COLUMN_SQL[table][column]
                )
                default = defaults.get(table, {}).get(column)
                if default is not None:
                    definition += f" DEFAULT {default}"
                definitions.append(f'"{column}" {definition}')
            if extra_column and extra_column[0] == table:
                definitions.append(
                    f'"{extra_column[1]}" {extra_column[2]}'
                )
            pk_name = (
                pk_name_override
                if pk_name_override is not None
                else (f"pk_{table}" if named else None)
            )
            prefix = f"CONSTRAINT {pk_name} " if pk_name else ""
            definitions.append(f"{prefix}PRIMARY KEY (id)")
            if table in FOREIGN_KEYS:
                column, target = FOREIGN_KEYS[table]
                override = fk_override.get(table, {})
                target = override.get("target", target)
                fk_name = override.get(
                    "name",
                    f"fk_{table}_{column}_{target}" if named else None,
                )
                ondelete = override.get("ondelete")
                prefix = f"CONSTRAINT {fk_name} " if fk_name else ""
                clause = (
                    f"{prefix}FOREIGN KEY ({column}) "
                    f"REFERENCES {target} (id)"
                )
                if ondelete:
                    clause += f" ON DELETE {ondelete}"
                definitions.append(clause)
            if extra_unique and table == "duplicate_scan":
                definitions.append(
                    "CONSTRAINT uq_duplicate_scan_scan_name "
                    "UNIQUE (scan_name)"
                )
            if extra_check and table == "duplicate_scan":
                definitions.append(
                    "CONSTRAINT ck_duplicate_scan_threshold "
                    "CHECK (threshold >= 0)"
                )
            connection.execute(
                text(f'CREATE TABLE "{table}" ({", ".join(definitions)})')
            )
        for table, column in INDEXES.items():
            if table == omit_table:
                continue
            override = index_override.get(table, {})
            name = override.get("name", f"ix_{table}_{column}")
            columns = override.get("columns", [column])
            unique = "UNIQUE " if override.get("unique", False) else ""
            connection.execute(
                text(
                    f'CREATE {unique}INDEX "{name}" ON "{table}" '
                    f'({", ".join(columns)})'
                )
            )


def _create_historical_profile(engine, profile):
    if profile == "protected":
        _create_literal_profile(engine)
    elif profile == "07":
        _create_literal_profile(
            engine,
            scan_order=HELPER_07_SCAN_ORDER,
            candidate_order=HELPER_07_CANDIDATE_ORDER,
            defaults=HELPER_07_DEFAULTS,
        )
    elif profile == "002":
        _create_literal_profile(
            engine,
            scan_order=HELPER_LATER_SCAN_ORDER,
            candidate_order=HELPER_002_CANDIDATE_ORDER,
            defaults=HELPER_002_DEFAULTS,
        )
    elif profile == "later":
        _create_literal_profile(
            engine,
            scan_order=HELPER_LATER_SCAN_ORDER,
            defaults=HELPER_LATER_DEFAULTS,
        )
    else:
        raise AssertionError(profile)


def _codes(result):
    return tuple(conflict.code for conflict in result.conflicts)


def _independent_snapshot(connection):
    master = tuple(
        connection.execute(
            text(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            )
        ).all()
    )
    rows = {}
    for table in sorted(set(inspect(connection).get_table_names()) & MANAGED_TABLES):
        rows[table] = tuple(
            connection.execute(text(f'SELECT * FROM "{table}"')).all()
        )
    schema_version = connection.execute(
        text("PRAGMA schema_version")
    ).scalar_one()
    total_changes = connection.connection.driver_connection.total_changes
    return master, rows, schema_version, total_changes


def test_public_enums_and_immutable_contracts_are_exact():
    assert [item.value for item in SQLiteSchemaClassification] == [
        "EMPTY", "CURRENT_ALEMBIC", "CURRENT_UNVERSIONED",
        "RECOGNIZED_LEGACY", "INCOMPLETE", "INCOMPATIBLE", "UNKNOWN",
    ]
    assert [item.value for item in SQLiteSchemaProfileId] == [
        "current_alembic_0001", "current_named_unversioned",
        "protected_baseline_unnamed", "helper_from_07c9a6e",
        "helper_from_00204e1", "helper_from_fee3f3d_or_42fa7ba",
    ]
    conflict = SQLiteSchemaConflict("index", "a", None, "b")
    result = SQLiteSchemaClassificationResult(
        SQLiteSchemaClassification.EMPTY, None, "0" * 64, None, (), (),
    )
    with pytest.raises(FrozenInstanceError):
        conflict.code = "changed"
    with pytest.raises(FrozenInstanceError):
        result.extra_tables = ("changed",)
    assert not hasattr(conflict, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(TypeError):
        APPROVED_PROFILE_FINGERPRINTS[
            SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED
        ] = "changed"


def test_invalid_input_and_non_sqlite_fail_before_connection():
    with pytest.raises(TypeError):
        classify_sqlite_schema(object())
    engine = create_engine("sqlite://")
    connections = []
    event.listen(
        engine,
        "connect",
        lambda *_args: connections.append("connected"),
    )
    original = engine.dialect.name
    engine.dialect.name = "postgresql"
    try:
        with pytest.raises(UnsupportedSchemaDialectError):
            classify_sqlite_schema(engine)
        assert connections == []
    finally:
        engine.dialect.name = original
        engine.dispose()


@pytest.mark.parametrize(
    ("with_extra", "extra_tables"),
    [(False, ()), (True, ("unrelated_extension",))],
)
def test_empty_is_repeatable_and_never_creates_version_table(
    with_extra, extra_tables,
):
    engine = _memory_engine()
    try:
        if with_extra:
            with engine.begin() as connection:
                connection.execute(
                    text("CREATE TABLE unrelated_extension (id INTEGER)")
                )
        first = classify_sqlite_schema(engine)
        second = classify_sqlite_schema(engine)
        assert first == second
        assert first.classification is SQLiteSchemaClassification.EMPTY
        assert first.profile_id is None
        assert first.extra_tables == extra_tables
        assert first.conflicts == ()
        assert re.fullmatch("[0-9a-f]{64}", first.managed_fingerprint_sha256)
        assert "alembic_version" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_current_metadata_profile_and_canonical_length():
    engine = _memory_engine()
    try:
        Base.metadata.create_all(engine, tables=LEGACY_STARTUP_TABLES)
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.CURRENT_UNVERSIONED
        assert result.profile_id is SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED
        assert result.managed_fingerprint_sha256 == EXPECTED_HASHES["current"]
        assert result.conflicts == ()
        with engine.connect() as connection:
            assert len(_canonical_json_bytes(_canonical_schema(connection))) == 5384
    finally:
        engine.dispose()


def test_current_unversioned_profile_survives_extra_unknown_table():
    engine = _memory_engine()
    try:
        Base.metadata.create_all(engine, tables=LEGACY_STARTUP_TABLES)
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE extension_table (payload TEXT)")
            )
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.CURRENT_UNVERSIONED
        assert result.profile_id is SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED
        assert result.extra_tables == ("extension_table",)
        assert result.conflicts == ()
    finally:
        engine.dispose()


def test_current_alembic_profile_and_extra_table(tmp_path):
    database = tmp_path / "alembic-current.sqlite"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "0001_current_schema")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE extension_table (id INTEGER)"))
        before = set(inspect(engine).get_table_names())
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.CURRENT_ALEMBIC
        assert result.profile_id is SQLiteSchemaProfileId.CURRENT_ALEMBIC_0001
        assert result.managed_fingerprint_sha256 == EXPECTED_HASHES["current"]
        assert result.alembic_revision == "0001_current_schema"
        assert result.extra_tables == ("extension_table",)
        assert set(inspect(engine).get_table_names()) == before
    finally:
        engine.dispose()


def test_registry_revision_is_not_legacy_current_alembic_0001(tmp_path):
    database = tmp_path / "alembic-registry.sqlite"
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.upgrade(config, "0002_dataset_registry")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.UNKNOWN
        assert result.profile_id is None
        assert result.alembic_revision == "0002_dataset_registry"
        assert result.extra_tables == (
            "dataset_artifacts",
            "dataset_versions",
            "datasets",
        )
        assert any(
            conflict.code == "alembic_revision"
            and conflict.actual == "0002_dataset_registry"
            for conflict in result.conflicts
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("profile", "classification", "profile_id"),
    [
        (
            "protected", SQLiteSchemaClassification.CURRENT_UNVERSIONED,
            SQLiteSchemaProfileId.PROTECTED_BASELINE_UNNAMED,
        ),
        (
            "07", SQLiteSchemaClassification.RECOGNIZED_LEGACY,
            SQLiteSchemaProfileId.HELPER_FROM_07C9A6E,
        ),
        (
            "002", SQLiteSchemaClassification.RECOGNIZED_LEGACY,
            SQLiteSchemaProfileId.HELPER_FROM_00204E1,
        ),
        (
            "later", SQLiteSchemaClassification.RECOGNIZED_LEGACY,
            SQLiteSchemaProfileId.HELPER_FROM_FEE3F3D_OR_42FA7BA,
        ),
    ],
)
def test_independent_literal_historical_profiles(
    profile, classification, profile_id,
):
    engine = _memory_engine()
    try:
        _create_historical_profile(engine, profile)
        result = classify_sqlite_schema(engine)
        assert result.classification is classification
        assert result.profile_id is profile_id
        assert result.managed_fingerprint_sha256 == EXPECTED_HASHES[profile]
        assert result.conflicts == ()
        with engine.connect() as connection:
            length = len(_canonical_json_bytes(_canonical_schema(connection)))
        assert length == EXPECTED_CANONICAL_LENGTHS[profile]
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("omit_table", "omit_column", "expected_paths"),
    [
        ("scan_warning", None, {"scan_warning"}),
        (None, ("duplicate_scan", "model_version"), {"duplicate_scan.model_version"}),
        (
            "scan_warning", ("duplicate_scan", "model_version"),
            {"scan_warning", "duplicate_scan.model_version"},
        ),
    ],
)
def test_missing_managed_elements_are_incomplete_and_not_repaired(
    omit_table, omit_column, expected_paths,
):
    engine = _memory_engine()
    try:
        _create_literal_profile(
            engine, named=True, omit_table=omit_table, omit_column=omit_column,
        )
        before = set(inspect(engine).get_table_names())
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.INCOMPLETE
        assert result.profile_id is None
        paths = {
            conflict.path
            for conflict in result.conflicts
            if conflict.code.startswith("missing_")
        }
        assert paths == expected_paths
        assert set(inspect(engine).get_table_names()) == before
        assert result.conflicts == tuple(sorted(
            result.conflicts,
            key=lambda item: (
                item.code, item.path, item.expected or "", item.actual or "",
            ),
        ))
    finally:
        engine.dispose()


def test_extra_managed_column_is_unknown_and_preserved():
    engine = _memory_engine()
    try:
        _create_literal_profile(
            engine,
            named=True,
            extra_column=("duplicate_scan", "source_marker", "TEXT"),
        )
        before = [item["name"] for item in inspect(engine).get_columns(
            "duplicate_scan"
        )]
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.UNKNOWN
        assert result.profile_id is None
        assert SQLiteSchemaConflict(
            "extra_managed_column",
            "duplicate_scan.source_marker",
            None,
            "present",
        ) in result.conflicts
        assert [item["name"] for item in inspect(engine).get_columns(
            "duplicate_scan"
        )] == before
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("kwargs", "code", "path"),
    [
        (
            {"column_sql_override": {
                ("duplicate_scan", "scan_name"): "INTEGER NOT NULL"
            }},
            "column_type", "duplicate_scan.scan_name.type",
        ),
        (
            {"column_sql_override": {
                ("duplicate_scan", "scan_name"): "VARCHAR(201) NOT NULL"
            }},
            "column_type", "duplicate_scan.scan_name.type",
        ),
        (
            {"column_sql_override": {
                ("duplicate_scan", "scan_name"): "VARCHAR(200)"
            }},
            "column_nullability", "duplicate_scan.scan_name.nullable",
        ),
        (
            {"defaults": {"duplicate_scan": {"warnings_count": "0"}}},
            "column_default", "duplicate_scan.warnings_count.default",
        ),
        (
            {"swap_columns": (
                "duplicate_scan", "scan_name", "source_type"
            )},
            "column_order", "duplicate_scan.columns",
        ),
        (
            {"pk_name_override": "wrong_primary_key"},
            "primary_key", "duplicate_scan.primary_key",
        ),
        (
            {"fk_override": {
                "duplicate_candidate": {"name": "wrong_foreign_key"}
            }},
            "foreign_key", "duplicate_candidate.foreign_keys",
        ),
        (
            {"fk_override": {
                "duplicate_candidate": {"target": "duplicate_feedback"}
            }},
            "foreign_key", "duplicate_candidate.foreign_keys",
        ),
        (
            {"fk_override": {
                "duplicate_candidate": {"ondelete": "CASCADE"}
            }},
            "foreign_key", "duplicate_candidate.foreign_keys",
        ),
        (
            {"index_override": {
                "duplicate_candidate": {"name": "wrong_index"}
            }},
            "index", "duplicate_candidate.indexes",
        ),
        (
            {"index_override": {
                "duplicate_candidate": {"columns": ["scan_id", "id"]}
            }},
            "index", "duplicate_candidate.indexes",
        ),
        (
            {"index_override": {
                "duplicate_candidate": {"unique": True}
            }},
            "index", "duplicate_candidate.indexes",
        ),
        (
            {"extra_unique": True},
            "unique_constraint", "duplicate_scan.unique_constraints",
        ),
        (
            {"extra_check": True},
            "check_constraint", "duplicate_scan.check_constraints",
        ),
    ],
)
def test_strict_incompatibility_categories(kwargs, code, path):
    engine = _memory_engine()
    try:
        _create_literal_profile(engine, named=True, **kwargs)
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.INCOMPATIBLE
        assert result.profile_id is None
        assert any(
            conflict.code == code and conflict.path == path
            for conflict in result.conflicts
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("version_ddl", "rows", "expected_code", "expected_revision"),
    [
        (
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)",
            [], "malformed_alembic_version", None,
        ),
        (
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)",
            ["one", "two"], "malformed_alembic_version", None,
        ),
        (
            "CREATE TABLE alembic_version (wrong_column VARCHAR(32))",
            [], "malformed_alembic_version", None,
        ),
        (
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)",
            ["future_revision"], "alembic_revision", "future_revision",
        ),
    ],
)
def test_malformed_and_unknown_alembic_revisions(
    version_ddl, rows, expected_code, expected_revision,
):
    engine = _memory_engine()
    try:
        _create_literal_profile(engine, named=True)
        with engine.begin() as connection:
            connection.execute(text(version_ddl))
            for value in rows:
                connection.execute(
                    text("INSERT INTO alembic_version VALUES (:value)"),
                    {"value": value},
                )
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.UNKNOWN
        assert result.profile_id is None
        assert expected_code in _codes(result)
        assert result.alembic_revision == expected_revision
    finally:
        engine.dispose()


def test_current_revision_never_hides_managed_mismatch():
    engine = _memory_engine()
    try:
        _create_literal_profile(
            engine,
            named=True,
            extra_column=("duplicate_scan", "unexpected", "TEXT"),
        )
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            ))
            connection.execute(text(
                "INSERT INTO alembic_version VALUES ('0001_current_schema')"
            ))
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.UNKNOWN
        assert result.profile_id is None
        assert "extra_managed_column" in _codes(result)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "profile",
    [
        "empty", "current", "current_alembic", "protected", "07",
        "incomplete", "incompatible", "extra",
    ],
)
def test_classifier_is_read_only_for_representative_schemas(profile):
    engine = _memory_engine()
    try:
        if profile == "current":
            _create_literal_profile(engine, named=True)
        elif profile == "current_alembic":
            _create_literal_profile(engine, named=True)
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE TABLE alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                ))
                connection.execute(text(
                    "INSERT INTO alembic_version "
                    "VALUES ('0001_current_schema')"
                ))
        elif profile in {"protected", "07"}:
            _create_historical_profile(engine, profile)
        elif profile == "incomplete":
            _create_literal_profile(engine, named=True, omit_table="scan_warning")
        elif profile == "incompatible":
            _create_literal_profile(
                engine,
                named=True,
                defaults={"duplicate_scan": {"warnings_count": "0"}},
            )
        elif profile == "extra":
            _create_literal_profile(
                engine,
                named=True,
                extra_column=("duplicate_scan", "extra_value", "TEXT"),
            )
        statements = []

        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.strip())

        event.listen(engine, "before_cursor_execute", capture)
        with engine.connect() as connection:
            before = _independent_snapshot(connection)
            statements.clear()
            classify_sqlite_schema(connection)
            after = _independent_snapshot(connection)
            assert not connection.closed
        event.remove(engine, "before_cursor_execute", capture)
        assert before == after
        assert statements
        assert all(
            statement.upper().startswith(("SELECT", "PRAGMA"))
            for statement in statements
        )
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_file_database_hash_size_mtime_and_data_are_unchanged(tmp_path):
    database = tmp_path / "read-only-proof.sqlite"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        _create_literal_profile(engine, named=True)
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO duplicate_scan "
                "(id, scan_name, source_type, selected_fields, threshold, "
                "status, scan_mode, started_at, model_version) VALUES "
                "(1, 'proof', 'CSV', '[]', 75, 'DONE', "
                "'SAME_SITE_DUPLICATE', '2026-07-30', 'v1')"
            ))
        engine.dispose()
        before_bytes = database.read_bytes()
        before_stat = database.stat()
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        result = classify_sqlite_schema(engine)
        assert result.classification is SQLiteSchemaClassification.CURRENT_UNVERSIONED
        engine.dispose()
        after_bytes = database.read_bytes()
        after_stat = database.stat()
        assert hashlib.sha256(after_bytes).digest() == hashlib.sha256(
            before_bytes
        ).digest()
        assert after_stat.st_size == before_stat.st_size
        assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
        assert not any(
            Path(str(database) + suffix).exists()
            for suffix in ("-journal", "-wal", "-shm")
        )
        engine = create_engine(f"sqlite:///{database.as_posix()}")
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT scan_name, model_version FROM duplicate_scan"
            )).one() == ("proof", "v1")
    finally:
        engine.dispose()


def test_caller_owned_connection_and_engine_remain_usable():
    engine = _memory_engine()
    try:
        _create_literal_profile(engine, named=True)
        with engine.connect() as connection:
            result = classify_sqlite_schema(connection)
            assert not connection.closed
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
            assert result == classify_sqlite_schema(connection)
        assert classify_sqlite_schema(engine).classification is (
            SQLiteSchemaClassification.CURRENT_UNVERSIONED
        )
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()


def test_source_boundaries_and_startup_separation():
    source = (
        BACKEND_ROOT / "app" / "db" / "schema_fingerprint.py"
    ).read_text(encoding="utf-8")
    main_source = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    forbidden_database_name = "inventory_detector" + ".db"
    assert "app.main" not in source
    assert "app.core.config" not in source
    assert "app.db.database" not in source
    assert "SessionLocal" not in source
    assert "ensure_sqlite_demo_columns" not in source
    assert "alembic" + ".command" not in source
    assert forbidden_database_name not in source
    assert "schema_fingerprint" not in main_source
