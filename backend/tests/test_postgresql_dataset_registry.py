import os
from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.db.database import (
    DatabaseEngineConfigurationError,
    create_database_engine,
)
from test_postgresql_migrations import (
    _EXPECTED_COLUMNS as _LEGACY_EXPECTED_COLUMNS,
    _EXPECTED_FOREIGN_KEYS as _LEGACY_EXPECTED_FOREIGN_KEYS,
    _EXPECTED_INDEXES as _LEGACY_EXPECTED_INDEXES,
    _EXPECTED_PRIMARY_KEYS as _LEGACY_EXPECTED_PRIMARY_KEYS,
    _EXPECTED_SEQUENCES as _LEGACY_EXPECTED_SEQUENCES,
    _columns,
    _configuration_failure,
    _constraints,
    _create_target_engine,
    _custom_types,
    _database_exists,
    _database_oid,
    _execute,
    _fingerprint as _assert_exact_legacy_contract,
    _indexes,
    _non_system_relations,
    _relations,
    _require,
    _require_equal,
    _safe_url,
    _sequences,
    _schemas,
    _triggers,
    _validate_base,
    _validate_target_identity,
)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATABASE_NAME = "inventory_dataset_registry_test"
LEGACY_REVISION = "0001_current_schema"
REGISTRY_REVISION = "0002_dataset_registry"
LEGACY_TABLES = {
    "duplicate_scan",
    "duplicate_candidate",
    "duplicate_feedback",
    "scan_warning",
    "rule_exclusion_audit",
}
REGISTRY_TABLES = {"datasets", "dataset_versions", "dataset_artifacts"}
ASCII_WHITESPACE = (" ", "\t", "\n", "\r", "\f", "\v")
SCHEMA_CHANGING_KEYWORDS = {
    "CREATE", "ALTER", "DROP", "COMMENT", "GRANT", "REVOKE", "TRUNCATE",
}
EXPECTED_COLUMN_NAMES = {
    "datasets": (
        "id", "name", "description", "status", "created_at", "updated_at",
    ),
    "dataset_versions": (
        "id", "dataset_id", "version_number", "status", "source_filename",
        "source_media_type", "source_sha256", "source_size_bytes",
        "source_record_count", "created_at", "updated_at",
    ),
    "dataset_artifacts": (
        "id", "dataset_version_id", "artifact_kind", "artifact_ordinal",
        "object_uri", "content_sha256", "size_bytes", "media_type",
        "created_at",
    ),
}
EXPECTED_COLUMN_CONTRACT = {
    "datasets": (
        ("id", "UUID", None, False, None),
        ("name", "VARCHAR", 255, False, None),
        ("description", "TEXT", None, True, None),
        ("status", "VARCHAR", 20, False, None),
        ("created_at", "TIMESTAMP", None, False, True),
        ("updated_at", "TIMESTAMP", None, False, True),
    ),
    "dataset_versions": (
        ("id", "UUID", None, False, None),
        ("dataset_id", "UUID", None, False, None),
        ("version_number", "INTEGER", None, False, None),
        ("status", "VARCHAR", 20, False, None),
        ("source_filename", "VARCHAR", 512, False, None),
        ("source_media_type", "VARCHAR", 255, False, None),
        ("source_sha256", "VARCHAR", 64, False, None),
        ("source_size_bytes", "BIGINT", None, False, None),
        ("source_record_count", "BIGINT", None, True, None),
        ("created_at", "TIMESTAMP", None, False, True),
        ("updated_at", "TIMESTAMP", None, False, True),
    ),
    "dataset_artifacts": (
        ("id", "UUID", None, False, None),
        ("dataset_version_id", "UUID", None, False, None),
        ("artifact_kind", "VARCHAR", 40, False, None),
        ("artifact_ordinal", "INTEGER", None, False, None),
        ("object_uri", "VARCHAR", 2048, False, None),
        ("content_sha256", "VARCHAR", 64, False, None),
        ("size_bytes", "BIGINT", None, False, None),
        ("media_type", "VARCHAR", 255, False, None),
        ("created_at", "TIMESTAMP", None, False, True),
    ),
}
EXPECTED_UNIQUES = {
    "datasets": set(),
    "dataset_versions": {
        (
            "uq_dataset_versions_dataset_id_version_number",
            ("dataset_id", "version_number"),
        ),
        (
            "uq_dataset_versions_dataset_id_source_sha256_source_size_bytes",
            ("dataset_id", "source_sha256", "source_size_bytes"),
        ),
    },
    "dataset_artifacts": {
        (
            # PostgreSQL's 63-byte identifier limit deterministically renders
            # the approved 70-character logical name with this hash suffix.
            "uq_dataset_artifacts_dataset_version_id_artifact_kind_a_9ec4",
            ("dataset_version_id", "artifact_kind", "artifact_ordinal"),
        ),
        ("uq_dataset_artifacts_object_uri", ("object_uri",)),
    },
}
EXPECTED_INDEXES = {
    "datasets": {("ix_datasets_status", ("status",), False)},
    "dataset_versions": {
        ("ix_dataset_versions_dataset_id", ("dataset_id",), False),
        ("ix_dataset_versions_status", ("status",), False),
    },
    "dataset_artifacts": {
        (
            "ix_dataset_artifacts_dataset_version_id",
            ("dataset_version_id",),
            False,
        ),
        (
            "ix_dataset_artifacts_dataset_version_id_artifact_kind",
            ("dataset_version_id", "artifact_kind"),
            False,
        ),
    },
}
EXPECTED_CHECKS = {
    "datasets": {"ck_datasets_name_nonempty", "ck_datasets_status"},
    "dataset_versions": {
        "ck_dataset_versions_version_number_positive",
        "ck_dataset_versions_status",
        "ck_dataset_versions_source_filename_nonempty",
        "ck_dataset_versions_source_media_type_nonempty",
        "ck_dataset_versions_source_sha256_format",
        "ck_dataset_versions_source_size_bytes_nonnegative",
        "ck_dataset_versions_source_record_count_nonnegative",
    },
    "dataset_artifacts": {
        "ck_dataset_artifacts_artifact_kind",
        "ck_dataset_artifacts_artifact_ordinal_nonnegative",
        "ck_dataset_artifacts_object_uri_nonempty",
        "ck_dataset_artifacts_content_sha256_format",
        "ck_dataset_artifacts_size_bytes_nonnegative",
        "ck_dataset_artifacts_media_type_nonempty",
    },
}


def _expected_nonempty(column: str) -> str:
    expression = column
    for character in ASCII_WHITESPACE:
        expression = f"replace({expression}, '{character}', '')"
    return f"length({expression}) > 0"


def _expected_sha256(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression}, '{character}', '')"
    return (
        f"length({column}) = 64 AND lower({column}) = {column} AND "
        f"{expression} = ''"
    )


EXPECTED_CHECK_SQL = {
    "datasets": {
        "ck_datasets_name_nonempty": _expected_nonempty("name"),
        "ck_datasets_status": "status IN ('ACTIVE', 'ARCHIVED')",
    },
    "dataset_versions": {
        "ck_dataset_versions_version_number_positive": "version_number > 0",
        "ck_dataset_versions_status": (
            "status IN ('REGISTERED', 'STAGED', 'PROFILED', 'READY', 'REJECTED')"
        ),
        "ck_dataset_versions_source_filename_nonempty": _expected_nonempty(
            "source_filename"
        ),
        "ck_dataset_versions_source_media_type_nonempty": _expected_nonempty(
            "source_media_type"
        ),
        "ck_dataset_versions_source_sha256_format": _expected_sha256(
            "source_sha256"
        ),
        "ck_dataset_versions_source_size_bytes_nonnegative": (
            "source_size_bytes >= 0"
        ),
        "ck_dataset_versions_source_record_count_nonnegative": (
            "source_record_count IS NULL OR source_record_count >= 0"
        ),
    },
    "dataset_artifacts": {
        "ck_dataset_artifacts_artifact_kind": (
            "artifact_kind IN ('SOURCE_CSV', 'SCHEMA_PROFILE_JSON', "
            "'CANONICAL_PARQUET')"
        ),
        "ck_dataset_artifacts_artifact_ordinal_nonnegative": (
            "artifact_ordinal >= 0"
        ),
        "ck_dataset_artifacts_object_uri_nonempty": _expected_nonempty(
            "object_uri"
        ),
        "ck_dataset_artifacts_content_sha256_format": _expected_sha256(
            "content_sha256"
        ),
        "ck_dataset_artifacts_size_bytes_nonnegative": "size_bytes >= 0",
        "ck_dataset_artifacts_media_type_nonempty": _expected_nonempty(
            "media_type"
        ),
    },
}


def _normalized_check(value: str) -> str:
    value = re.sub(
        r"::\s*(?:character\s+varying|text)(?:\[\])?",
        "",
        value,
        flags=re.IGNORECASE,
    )
    result: list[str] = []
    index = 0
    quoted = False
    while index < len(value):
        character = value[index]
        if character == "'":
            result.append(character)
            if quoted and index + 1 < len(value) and value[index + 1] == "'":
                result.append("'")
                index += 2
                continue
            quoted = not quoted
        elif quoted:
            result.append(f"\\x{ord(character):02x}")
        elif character == '"':
            pass
        elif not character.isspace():
            result.append(character.lower())
        index += 1
    normalized = "".join(result)
    while normalized.startswith("(") and normalized.endswith(")"):
        depth = 0
        encloses = True
        in_string = False
        for position, character in enumerate(normalized):
            if character == "'":
                in_string = not in_string
            elif not in_string:
                if character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
                    if depth == 0 and position != len(normalized) - 1:
                        encloses = False
                        break
        if not encloses or depth != 0:
            break
        normalized = normalized[1:-1]
    normalized = re.sub(
        r"(?P<column>[a-z_][a-z0-9_]*)=any\(array\[(?P<values>.*)\]\)",
        r"\g<column>in(\g<values>)",
        normalized,
    )
    return normalized


def _config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    _require_equal("Alembic bases", tuple(script.get_bases()), (LEGACY_REVISION,))
    _require_equal("Alembic heads", tuple(script.get_heads()), (REGISTRY_REVISION,))
    return config


def _upgrade(config: Config, connection, target: str) -> None:
    config.attributes["connection"] = connection
    try:
        command.upgrade(config, target)
    finally:
        config.attributes.pop("connection", None)


def _downgrade(config: Config, connection, target: str) -> None:
    config.attributes["connection"] = connection
    try:
        command.downgrade(config, target)
    finally:
        config.attributes.pop("connection", None)


def _revision(connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _legacy_fingerprint(connection):
    primary_keys, foreign_keys, unsupported = _constraints(connection)
    columns = tuple(
        item for item in _columns(connection) if item[0] in LEGACY_TABLES
    )
    primary_keys = tuple(
        item for item in primary_keys if item[1] in LEGACY_TABLES
    )
    foreign_keys = tuple(
        item for item in foreign_keys if item[1] in LEGACY_TABLES
    )
    unsupported = tuple(
        item for item in unsupported if item[2] in LEGACY_TABLES
    )
    indexes = tuple(
        item for item in _indexes(connection) if item[1] in LEGACY_TABLES
    )
    relations = tuple(
        item
        for item in _relations(connection)
        if item[0] in LEGACY_TABLES
        or item[0] in {sequence[0] for sequence in _LEGACY_EXPECTED_SEQUENCES}
    )
    rows = tuple(
        (
            table,
            tuple(
                connection.execute(
                    text(f'SELECT * FROM "{table}" ORDER BY id')
                ).all()
            ),
        )
        for table in sorted(LEGACY_TABLES)
    )
    fingerprint = (
        ("schemas", _schemas(connection)),
        ("relations", relations),
        ("columns", columns),
        ("primary_keys", primary_keys),
        ("foreign_keys", foreign_keys),
        ("unsupported_constraints", unsupported),
        ("indexes", indexes),
        ("sequences", _sequences(connection)),
        ("triggers", _triggers(connection)),
        ("custom_types", _custom_types(connection)),
        ("rows", rows),
    )
    _require_equal(
        "legacy columns",
        columns,
        tuple(
            (table, values)
            for table, values in sorted(_LEGACY_EXPECTED_COLUMNS.items())
            if table in LEGACY_TABLES
        ),
    )
    _require_equal(
        "legacy primary keys",
        primary_keys,
        tuple(item for item in _LEGACY_EXPECTED_PRIMARY_KEYS if item[1] in LEGACY_TABLES),
    )
    _require_equal("legacy foreign keys", foreign_keys, _LEGACY_EXPECTED_FOREIGN_KEYS)
    _require_equal("legacy unsupported constraints", unsupported, ())
    _require_equal(
        "legacy indexes",
        indexes,
        tuple(item for item in _LEGACY_EXPECTED_INDEXES if item[1] in LEGACY_TABLES),
    )
    _require_equal("legacy sequences and ownership", _sequences(connection), _LEGACY_EXPECTED_SEQUENCES)
    _require_equal("legacy triggers", _triggers(connection), ())
    _require_equal("legacy custom types", _custom_types(connection), ())
    _require_equal("public schema", _schemas(connection), ("public",))
    return fingerprint


def _check_definitions(connection, table: str) -> dict[str, str]:
    rows = connection.execute(
        text(
            "SELECT con.conname, pg_get_expr(con.conbin, con.conrelid, true) "
            "FROM pg_constraint AS con "
            "JOIN pg_class AS cls ON cls.oid = con.conrelid "
            "JOIN pg_namespace AS ns ON ns.oid = cls.relnamespace "
            "WHERE ns.nspname = 'public' AND cls.relname = :table "
            "AND con.contype = 'c' ORDER BY con.conname"
        ),
        {"table": table},
    ).all()
    return {name: expression for name, expression in rows}


def _full_fingerprint(connection):
    primary_keys, foreign_keys, unsupported = _constraints(connection)
    tables = tuple(sorted(LEGACY_TABLES | REGISTRY_TABLES))
    return (
        ("schemas", _schemas(connection)),
        ("relations", _relations(connection)),
        ("columns", _columns(connection)),
        ("primary_keys", primary_keys),
        ("foreign_keys", foreign_keys),
        ("other_constraints", unsupported),
        ("checks", tuple((table, _check_definitions(connection, table)) for table in sorted(REGISTRY_TABLES))),
        ("indexes", _indexes(connection)),
        ("sequences", _sequences(connection)),
        ("triggers", _triggers(connection)),
        ("custom_types", _custom_types(connection)),
        (
            "row_counts",
            tuple(
                (
                    table,
                    connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one(),
                )
                for table in tables
            ),
        ),
        ("revision", _revision(connection)),
        (
            "version_rows",
            tuple(
                connection.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                ).scalars()
            ),
        ),
    )


def _statement_keyword(statement: str) -> str:
    value = statement
    while True:
        value = value.lstrip()
        if value.startswith("/*"):
            end = value.find("*/", 2)
            if end < 0:
                return ""
            value = value[end + 2:]
            continue
        if value.startswith("--"):
            end = re.search(r"\r?\n", value)
            if end is None:
                return ""
            value = value[end.end():]
            continue
        break
    keyword = re.match(r"[A-Za-z]+", value)
    return keyword.group(0).upper() if keyword is not None else ""


def _finish_cleanup(
    primary_error: BaseException | None,
    cleanup_error: BaseException | None,
) -> None:
    if cleanup_error is None:
        return
    if primary_error is None:
        raise cleanup_error
    primary_error.add_note(
        "Registry cleanup also failed "
        f"({type(cleanup_error).__name__})"
    )


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        (" \n/* one */ /* two */ -- three\r\n CREATE TABLE x (id int)", "CREATE"),
        ("-- one\n-- two\n\tSELECT 1", "SELECT"),
        ("/* comment only */ -- final", ""),
        ("/* unclosed", ""),
        ("-- no line ending", ""),
        ("123 malformed", ""),
    ],
)
def test_registry_statement_keyword_parser_is_comment_safe(statement, expected):
    assert _statement_keyword(statement) == expected


def test_registry_cleanup_preserves_primary_error_and_safe_note():
    primary = AssertionError("primary migration proof failure")
    cleanup = RuntimeError(
        "postgresql+psycopg://user:secret@example.invalid/database"
    )
    _finish_cleanup(primary, cleanup)
    assert primary.__notes__ == ["Registry cleanup also failed (RuntimeError)"]
    assert "secret" not in primary.__notes__[0]
    with pytest.raises(RuntimeError) as captured:
        _finish_cleanup(None, cleanup)
    assert captured.value is cleanup


def _sentinels(connection):
    return tuple(
        (
            table,
            tuple(
                connection.execute(
                    text(f'SELECT id FROM "{table}" ORDER BY id')
                ).scalars()
            ),
        )
        for table in sorted(LEGACY_TABLES)
    )


def _insert_sentinels(connection) -> None:
    connection.execute(text("""
        INSERT INTO duplicate_scan (
            id, scan_name, source_type, selected_fields, threshold, status,
            total_records, total_candidates, warnings_count,
            rejections_count, scan_mode, started_at, model_version
        ) VALUES (
            101, 'registry sentinel', 'CSV', '[]', 75, 'COMPLETED',
            2, 1, 1, 1, 'SAME_SITE_DUPLICATE',
            '2026-08-06 01:00:00+00', 'hybrid-nlp-v1'
        )
    """))
    connection.execute(text("""
        INSERT INTO duplicate_candidate (
            id, scan_id, part_no_a, description_a, part_no_b, description_b,
            similarity_score, confidence_level, description_similarity,
            tfidf_score, fuzzy_score, part_no_similarity,
            technical_token_score, explanation, recommended_action,
            business_status, rule_decision, scan_mode, review_status
        ) VALUES (
            102, 101, 'A', 'left', 'B', 'right', 88, 'MEDIUM', 88,
            88, 88, 0, 0, 'sentinel', 'review',
            'POSSIBLE_DUPLICATE_REVIEW', 'ALLOW',
            'SAME_SITE_DUPLICATE', 'UNREVIEWED'
        )
    """))
    connection.execute(text("""
        INSERT INTO duplicate_feedback (
            id, candidate_id, user_decision, created_by, created_at
        ) VALUES (103, 102, 'UNSURE', 'tester', '2026-08-06 01:01:00+00')
    """))
    connection.execute(text("""
        INSERT INTO scan_warning (
            id, scan_id, warning_type, message, created_at
        ) VALUES (104, 101, 'SENTINEL', 'keep', '2026-08-06 01:02:00+00')
    """))
    connection.execute(text("""
        INSERT INTO rule_exclusion_audit (
            id, scan_id, part_no_a, description_a, part_no_b, description_b,
            similarity_score, confidence_level, business_status,
            rule_decision, rejection_reason, explanation, created_at
        ) VALUES (
            105, 101, 'C', 'left', 'D', 'right', 0, 'IGNORE',
            'REJECTED_BY_BUSINESS_RULE', 'REJECT', 'SENTINEL',
            'keep', '2026-08-06 01:03:00+00'
        )
    """))


def _assert_registry_contract(connection) -> None:
    inspector = inspect(connection)
    _require_equal(
        "registry table set",
        set(inspector.get_table_names()).intersection(REGISTRY_TABLES),
        REGISTRY_TABLES,
    )
    for table in sorted(REGISTRY_TABLES):
        columns = inspector.get_columns(table)
        _require_equal(
            f"{table} column order",
            tuple(item["name"] for item in columns),
            EXPECTED_COLUMN_NAMES[table],
        )
        actual_column_contract = tuple(
            (
                item["name"],
                type(item["type"]).__name__,
                getattr(item["type"], "length", None),
                bool(item["nullable"]),
                getattr(item["type"], "timezone", None),
            )
            for item in columns
        )
        _require_equal(
            f"{table} column contract",
            actual_column_contract,
            EXPECTED_COLUMN_CONTRACT[table],
        )
        _require(
            all(item["default"] is None for item in columns),
            f"{table} has an unexpected server default",
        )
        primary_key = inspector.get_pk_constraint(table)
        _require_equal(f"{table} primary-key name", primary_key["name"], f"pk_{table}")
        _require_equal(
            f"{table} primary-key columns",
            primary_key["constrained_columns"],
            ["id"],
        )
        _require_equal(
            f"{table} checks",
            {item["name"] for item in inspector.get_check_constraints(table)},
            EXPECTED_CHECKS[table],
        )
        _require_equal(
            f"{table} normalized check definitions",
            {
                name: _normalized_check(expression)
                for name, expression in _check_definitions(connection, table).items()
            },
            {
                name: _normalized_check(expression)
                for name, expression in EXPECTED_CHECK_SQL[table].items()
            },
        )
        _require_equal(
            f"{table} unique constraints",
            {
                (item["name"], tuple(item["column_names"]))
                for item in inspector.get_unique_constraints(table)
            },
            EXPECTED_UNIQUES[table],
        )
        _require_equal(
            f"{table} explicit indexes",
            {
                (
                    item["name"],
                    tuple(item["column_names"]),
                    bool(item["unique"]),
                )
                for item in inspector.get_indexes(table)
                if item["name"].startswith("ix_")
            },
            EXPECTED_INDEXES[table],
        )
        _require_equal(
            f"{table} row count",
            connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one(),
            0,
        )
        id_type = inspector.get_columns(table)[0]["type"]
        _require_equal(f"{table}.id native UUID", str(id_type), "UUID")

    version_fk = inspector.get_foreign_keys("dataset_versions")
    artifact_fk = inspector.get_foreign_keys("dataset_artifacts")
    _require_equal(
        "version FK delete",
        version_fk[0]["options"].get("ondelete"),
        "RESTRICT",
    )
    _require_equal(
        "version FK identity",
        (
            version_fk[0]["name"],
            tuple(version_fk[0]["constrained_columns"]),
            version_fk[0]["referred_table"],
            tuple(version_fk[0]["referred_columns"]),
        ),
        (
            "fk_dataset_versions_dataset_id_datasets",
            ("dataset_id",),
            "datasets",
            ("id",),
        ),
    )
    _require_equal(
        "artifact FK delete",
        artifact_fk[0]["options"].get("ondelete"),
        "RESTRICT",
    )
    _require_equal(
        "artifact FK identity",
        (
            artifact_fk[0]["name"],
            tuple(artifact_fk[0]["constrained_columns"]),
            artifact_fk[0]["referred_table"],
            tuple(artifact_fk[0]["referred_columns"]),
        ),
        (
            "fk_dataset_artifacts_dataset_version_id_dataset_versions",
            ("dataset_version_id",),
            "dataset_versions",
            ("id",),
        ),
    )
    _require_equal("registry custom types", _custom_types(connection), ())
    _require_equal("registry triggers", _triggers(connection), ())
    _require_equal(
        "owned sequences remain legacy-only with exact ownership",
        _sequences(connection),
        _LEGACY_EXPECTED_SEQUENCES,
    )


def _assert_postgresql_sha_and_whitespace_checks(connection) -> None:
    transaction = connection.begin()
    try:
        connection.execute(text("""
            INSERT INTO datasets VALUES (
                '11111111111111111111111111111111', 'valid', NULL,
                'ACTIVE', '2026-08-06 01:00:00+00',
                '2026-08-06 01:00:00+00'
            )
        """))
        savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text("""
                    INSERT INTO dataset_versions VALUES (
                        '22222222222222222222222222222222',
                        '11111111111111111111111111111111', 1,
                        'REGISTERED', 'source.csv', 'text/csv', :sha,
                        1, NULL, '2026-08-06 01:00:00+00',
                        '2026-08-06 01:00:00+00'
                    )
                """),
                {"sha": "A" * 64},
            )
        savepoint.rollback()
        connection.execute(
            text("""
                INSERT INTO dataset_versions VALUES (
                    '22222222222222222222222222222222',
                    '11111111111111111111111111111111', 1,
                    'REGISTERED', 'source.csv', 'text/csv', :sha,
                    1, NULL, '2026-08-06 01:00:00+00',
                    '2026-08-06 01:00:00+00'
                )
            """),
            {"sha": "a" * 64},
        )
        savepoint = connection.begin_nested()
        with pytest.raises(IntegrityError):
            connection.execute(
                text("""
                    INSERT INTO dataset_artifacts VALUES (
                        '33333333333333333333333333333333',
                        '22222222222222222222222222222222',
                        'SOURCE_CSV', 0, 'opaque://one', :sha,
                        1, 'text/csv', '2026-08-06 01:00:00+00'
                    )
                """),
                {"sha": "z" * 64},
            )
        savepoint.rollback()
        connection.execute(
            text("""
                INSERT INTO dataset_artifacts VALUES (
                    '33333333333333333333333333333333',
                    '22222222222222222222222222222222',
                    'SOURCE_CSV', 0, 'opaque://one', :sha,
                    1, 'text/csv', '2026-08-06 01:00:00+00'
                )
            """),
            {"sha": "b" * 64},
        )
        checks = (
            ("datasets", "name", "11111111111111111111111111111111"),
            (
                "dataset_versions",
                "source_filename",
                "22222222222222222222222222222222",
            ),
            (
                "dataset_versions",
                "source_media_type",
                "22222222222222222222222222222222",
            ),
            (
                "dataset_artifacts",
                "object_uri",
                "33333333333333333333333333333333",
            ),
            (
                "dataset_artifacts",
                "media_type",
                "33333333333333333333333333333333",
            ),
        )
        rejected = ("", " ", "\t", "\n", "\r", "\f", "\v", " \t\r\n\f\v ")
        for table, column, row_id in checks:
            for invalid in rejected:
                savepoint = connection.begin_nested()
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text(
                            f'UPDATE "{table}" SET "{column}" = :value '
                            "WHERE id = :id"
                        ),
                        {"value": invalid, "id": row_id},
                    )
                savepoint.rollback()
            connection.execute(
                text(
                    f'UPDATE "{table}" SET "{column}" = :value '
                    "WHERE id = :id"
                ),
                {"value": " \tΔ-valid\n ", "id": row_id},
            )
    finally:
        transaction.rollback()


@pytest.mark.postgres_integration
def test_postgresql_dataset_registry_migration_contract() -> None:
    configured_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if configured_url is None:
        pytest.skip(
            "POSTGRES_TEST_DATABASE_URL is not set; opt-in PostgreSQL "
            "dataset registry migration test skipped"
        )

    base_engine: Engine | None = None
    target_engine: Engine | None = None
    created = False
    primary_error: BaseException | None = None
    try:
        try:
            base_engine = create_database_engine(configured_url)
        except DatabaseEngineConfigurationError as error:
            raise _configuration_failure(error) from None

        with base_engine.connect() as base_connection:
            _validate_base(base_connection, base_engine)
            _require(
                not _database_exists(base_connection, DATABASE_NAME),
                f"{DATABASE_NAME} already exists; refusing ownership",
            )
        with base_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as admin:
            _execute(
                admin,
                "create registry database",
                'CREATE DATABASE "inventory_dataset_registry_test"',
            )
            created = True
            database_oid = _database_oid(admin, DATABASE_NAME)

        target_engine = _create_target_engine(base_engine, DATABASE_NAME)
        config = _config()
        with target_engine.connect() as connection:
            _validate_target_identity(connection, DATABASE_NAME, database_oid)
            _upgrade(config, connection, LEGACY_REVISION)
            _require_equal("legacy revision", _revision(connection), LEGACY_REVISION)
            _assert_exact_legacy_contract(connection)
            _insert_sentinels(connection)
            connection.commit()
            legacy = _legacy_fingerprint(connection)
            sentinel_values = _sentinels(connection)
            connection.commit()
            _upgrade(config, connection, REGISTRY_REVISION)
            _require_equal(
                "registry revision", _revision(connection), REGISTRY_REVISION
            )
            _require_equal(
                "legacy fingerprint after registry upgrade",
                _legacy_fingerprint(connection),
                legacy,
            )
            _require_equal("legacy sentinels", _sentinels(connection), sentinel_values)
            _assert_registry_contract(connection)
            connection.commit()
            _assert_postgresql_sha_and_whitespace_checks(connection)

        with target_engine.connect() as connection:
            pre_noop = _full_fingerprint(connection)

        statements: list[str] = []
        with target_engine.connect() as connection:
            def capture(_conn, _cursor, statement, _params, _context, _many):
                statements.append(statement)

            event.listen(connection, "before_cursor_execute", capture)
            try:
                _upgrade(config, connection, "head")
            finally:
                event.remove(connection, "before_cursor_execute", capture)

        observable = tuple(statement for statement in statements if statement.strip())
        keywords = tuple(_statement_keyword(statement) for statement in observable)
        _require_equal(
            "second registry upgrade unclassified statements",
            tuple(index for index, keyword in enumerate(keywords) if not keyword),
            (),
        )
        _require_equal(
            "second registry upgrade schema-changing statements",
            tuple(keyword for keyword in keywords if keyword in SCHEMA_CHANGING_KEYWORDS),
            (),
        )
        with target_engine.connect() as connection:
            _require_equal("second registry revision", _revision(connection), REGISTRY_REVISION)
            _require_equal(
                "second registry full-schema fingerprint",
                _full_fingerprint(connection),
                pre_noop,
            )

        with target_engine.connect() as connection:
            _downgrade(config, connection, LEGACY_REVISION)
            _require_equal("downgraded revision", _revision(connection), LEGACY_REVISION)
            _require_equal(
                "registry tables after downgrade",
                REGISTRY_TABLES.intersection(inspect(connection).get_table_names()),
                set(),
            )
            _require_equal("legacy downgrade fingerprint", _legacy_fingerprint(connection), legacy)
            _require_equal("legacy downgrade sentinels", _sentinels(connection), sentinel_values)
            connection.commit()
            _upgrade(config, connection, REGISTRY_REVISION)
            _require_equal("re-upgraded revision", _revision(connection), REGISTRY_REVISION)
            _require_equal("legacy re-upgrade fingerprint", _legacy_fingerprint(connection), legacy)
            _require_equal("legacy re-upgrade sentinels", _sentinels(connection), sentinel_values)
            _assert_registry_contract(connection)
    except AssertionError as error:
        primary_error = error
        raise
    except Exception as error:
        safe = _safe_url(base_engine) if base_engine is not None else "unavailable"
        detail = f"; key={error.args[0]!r}" if isinstance(error, KeyError) else ""
        primary_error = AssertionError(
            "PostgreSQL dataset registry verification failed "
            f"({type(error).__name__}){detail}; url={safe}"
        )
        raise primary_error from None
    finally:
        cleanup_error: BaseException | None = None
        if target_engine is not None:
            try:
                target_engine.dispose()
            except BaseException as error:
                cleanup_error = error
        if base_engine is not None:
            if created:
                try:
                    checked_out = getattr(base_engine.pool, "checkedout", lambda: 0)()
                    _require_equal(
                        "base checked-out connections before registry cleanup",
                        checked_out,
                        0,
                    )
                    with base_engine.connect().execution_options(
                        isolation_level="AUTOCOMMIT"
                    ) as admin:
                        _execute(
                            admin,
                            "drop registry database",
                            'DROP DATABASE "inventory_dataset_registry_test"',
                        )
                        _require(
                            not _database_exists(admin, DATABASE_NAME),
                            "registry database still exists after cleanup",
                        )
                        _require_equal(
                            "base relations after registry cleanup",
                            _non_system_relations(admin),
                            (),
                        )
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
            try:
                base_engine.dispose()
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = AssertionError(
                        f"dispose base engine failed ({type(error).__name__})"
                    )
        _finish_cleanup(primary_error, cleanup_error)
