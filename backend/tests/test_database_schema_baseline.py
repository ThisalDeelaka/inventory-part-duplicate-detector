from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401 - registers the committed tables
from app.db.database import Base
from app.db.migrations import ensure_sqlite_demo_columns


EXPECTED_SCHEMA = {
    "duplicate_scan": [
        ("id", "INTEGER", False, True, None),
        ("scan_name", "VARCHAR(200)", False, False, None),
        ("source_type", "VARCHAR(30)", False, False, None),
        ("selected_fields", "TEXT", False, False, None),
        ("threshold", "FLOAT", False, False, None),
        ("status", "VARCHAR(30)", False, False, None),
        ("total_records", "INTEGER", True, False, None),
        ("total_candidates", "INTEGER", True, False, None),
        ("warnings_count", "INTEGER", True, False, None),
        ("rejections_count", "INTEGER", True, False, None),
        ("scan_mode", "VARCHAR(60)", False, False, None),
        ("started_at", "DATETIME", False, False, None),
        ("completed_at", "DATETIME", True, False, None),
        ("model_version", "VARCHAR(50)", False, False, None),
    ],
    "duplicate_candidate": [
        ("id", "INTEGER", False, True, None),
        ("scan_id", "INTEGER", False, False, None),
        ("contract_a", "VARCHAR(100)", True, False, None),
        ("part_no_a", "VARCHAR(200)", False, False, None),
        ("description_a", "TEXT", False, False, None),
        ("contract_b", "VARCHAR(100)", True, False, None),
        ("part_no_b", "VARCHAR(200)", False, False, None),
        ("description_b", "TEXT", False, False, None),
        ("similarity_score", "FLOAT", False, False, None),
        ("confidence_level", "VARCHAR(20)", False, False, None),
        ("description_similarity", "FLOAT", False, False, None),
        ("tfidf_score", "FLOAT", False, False, None),
        ("fuzzy_score", "FLOAT", False, False, None),
        ("part_no_similarity", "FLOAT", False, False, None),
        ("technical_token_score", "FLOAT", False, False, None),
        ("matched_fields", "TEXT", True, False, None),
        ("mismatched_fields", "TEXT", True, False, None),
        ("explanation", "TEXT", False, False, None),
        ("recommended_action", "VARCHAR(200)", False, False, None),
        ("business_status", "VARCHAR(80)", False, False, None),
        ("rule_decision", "VARCHAR(50)", False, False, None),
        ("rejection_reason", "VARCHAR(120)", True, False, None),
        ("scan_mode", "VARCHAR(60)", False, False, None),
        ("critical_mismatches", "TEXT", True, False, None),
        ("variant_attributes_a", "TEXT", True, False, None),
        ("variant_attributes_b", "TEXT", True, False, None),
        ("generic_description_warning", "VARCHAR(10)", True, False, None),
        ("application_context_a", "TEXT", True, False, None),
        ("application_context_b", "TEXT", True, False, None),
        ("application_context_warning", "VARCHAR(10)", True, False, None),
        ("normalized_description_a", "TEXT", True, False, None),
        ("normalized_description_b", "TEXT", True, False, None),
        ("normalized_part_no_a", "TEXT", True, False, None),
        ("normalized_part_no_b", "TEXT", True, False, None),
        ("review_status", "VARCHAR(30)", False, False, None),
        ("reviewed_by", "VARCHAR(100)", True, False, None),
        ("reviewed_at", "DATETIME", True, False, None),
    ],
    "duplicate_feedback": [
        ("id", "INTEGER", False, True, None),
        ("candidate_id", "INTEGER", False, False, None),
        ("user_decision", "VARCHAR(30)", False, False, None),
        ("user_comment", "TEXT", True, False, None),
        ("created_by", "VARCHAR(100)", False, False, None),
        ("created_at", "DATETIME", False, False, None),
    ],
    "scan_warning": [
        ("id", "INTEGER", False, True, None),
        ("scan_id", "INTEGER", False, False, None),
        ("warning_type", "VARCHAR(80)", False, False, None),
        ("message", "TEXT", False, False, None),
        ("record_reference", "VARCHAR(200)", True, False, None),
        ("created_at", "DATETIME", False, False, None),
    ],
    "rule_exclusion_audit": [
        ("id", "INTEGER", False, True, None),
        ("scan_id", "INTEGER", False, False, None),
        ("contract_a", "VARCHAR(100)", True, False, None),
        ("part_no_a", "VARCHAR(200)", False, False, None),
        ("description_a", "TEXT", False, False, None),
        ("contract_b", "VARCHAR(100)", True, False, None),
        ("part_no_b", "VARCHAR(200)", False, False, None),
        ("description_b", "TEXT", False, False, None),
        ("similarity_score", "FLOAT", False, False, None),
        ("confidence_level", "VARCHAR(20)", False, False, None),
        ("business_status", "VARCHAR(80)", False, False, None),
        ("rule_decision", "VARCHAR(50)", False, False, None),
        ("rejection_reason", "VARCHAR(120)", False, False, None),
        ("critical_mismatches", "TEXT", True, False, None),
        ("explanation", "TEXT", False, False, None),
        ("created_at", "DATETIME", False, False, None),
    ],
}

EXPECTED_CLIENT_DEFAULTS = {
    "duplicate_scan": {
        "source_type": "CSV",
        "selected_fields": "[]",
        "status": "RUNNING",
        "total_records": 0,
        "total_candidates": 0,
        "warnings_count": 0,
        "rejections_count": 0,
        "scan_mode": "SAME_SITE_DUPLICATE",
    },
    "duplicate_candidate": {
        "matched_fields": "[]",
        "mismatched_fields": "[]",
        "business_status": "POSSIBLE_DUPLICATE_REVIEW",
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "scan_mode": "SAME_SITE_DUPLICATE",
        "critical_mismatches": "[]",
        "variant_attributes_a": "{}",
        "variant_attributes_b": "{}",
        "generic_description_warning": "false",
        "application_context_a": "[]",
        "application_context_b": "[]",
        "application_context_warning": "false",
        "normalized_description_a": "",
        "normalized_description_b": "",
        "normalized_part_no_a": "",
        "normalized_part_no_b": "",
        "review_status": "UNREVIEWED",
    },
    "duplicate_feedback": {"created_by": "demo-reviewer"},
    "scan_warning": {},
    "rule_exclusion_audit": {"critical_mismatches": "[]"},
}

EXPECTED_CALLABLE_DEFAULTS = {
    ("duplicate_scan", "started_at"),
    ("duplicate_feedback", "created_at"),
    ("scan_warning", "created_at"),
    ("rule_exclusion_audit", "created_at"),
}

HELPER_ADDITIONS = {
    "duplicate_scan": [
        ("scan_mode", "VARCHAR(60)", False, "'SAME_SITE_DUPLICATE'"),
        ("rejections_count", "INTEGER", True, "0"),
    ],
    "duplicate_candidate": [
        ("business_status", "VARCHAR(80)", False, "'POSSIBLE_DUPLICATE_REVIEW'"),
        ("rule_decision", "VARCHAR(50)", False, "'ALLOW'"),
        ("rejection_reason", "VARCHAR(120)", True, "''"),
        ("scan_mode", "VARCHAR(60)", False, "'SAME_SITE_DUPLICATE'"),
        ("critical_mismatches", "TEXT", True, "'[]'"),
        ("variant_attributes_a", "TEXT", True, "'{}'"),
        ("variant_attributes_b", "TEXT", True, "'{}'"),
        ("generic_description_warning", "VARCHAR(10)", True, "'false'"),
        ("application_context_a", "TEXT", True, "'[]'"),
        ("application_context_b", "TEXT", True, "'[]'"),
        ("application_context_warning", "VARCHAR(10)", True, "'false'"),
        ("normalized_description_a", "TEXT", True, "''"),
        ("normalized_description_b", "TEXT", True, "''"),
        ("normalized_part_no_a", "TEXT", True, "''"),
        ("normalized_part_no_b", "TEXT", True, "''"),
    ],
}

EXPECTED_INDEXES = {
    "duplicate_candidate": [("ix_duplicate_candidate_scan_id", ("scan_id",), False)],
    "duplicate_feedback": [("ix_duplicate_feedback_candidate_id", ("candidate_id",), False)],
    "duplicate_scan": [],
    "rule_exclusion_audit": [("ix_rule_exclusion_audit_scan_id", ("scan_id",), False)],
    "scan_warning": [("ix_scan_warning_scan_id", ("scan_id",), False)],
}

EXPECTED_FOREIGN_KEYS = {
    "duplicate_candidate": [(("scan_id",), "duplicate_scan", ("id",), None)],
    "duplicate_feedback": [(("candidate_id",), "duplicate_candidate", ("id",), None)],
    "duplicate_scan": [],
    "rule_exclusion_audit": [(("scan_id",), "duplicate_scan", ("id",), None)],
    "scan_warning": [(("scan_id",), "duplicate_scan", ("id",), None)],
}

LEGACY_SCHEMA_SQL = [
    """
    CREATE TABLE duplicate_scan (
        id INTEGER PRIMARY KEY,
        scan_name VARCHAR(200) NOT NULL,
        source_type VARCHAR(30) NOT NULL,
        selected_fields TEXT NOT NULL,
        threshold FLOAT NOT NULL,
        status VARCHAR(30) NOT NULL,
        total_records INTEGER,
        total_candidates INTEGER,
        warnings_count INTEGER,
        started_at DATETIME NOT NULL,
        completed_at DATETIME,
        model_version VARCHAR(50) NOT NULL
    )
    """,
    """
    CREATE TABLE duplicate_candidate (
        id INTEGER PRIMARY KEY,
        scan_id INTEGER NOT NULL,
        contract_a VARCHAR(100),
        part_no_a VARCHAR(200) NOT NULL,
        description_a TEXT NOT NULL,
        contract_b VARCHAR(100),
        part_no_b VARCHAR(200) NOT NULL,
        description_b TEXT NOT NULL,
        similarity_score FLOAT NOT NULL,
        confidence_level VARCHAR(20) NOT NULL,
        description_similarity FLOAT NOT NULL,
        tfidf_score FLOAT NOT NULL,
        fuzzy_score FLOAT NOT NULL,
        part_no_similarity FLOAT NOT NULL,
        technical_token_score FLOAT NOT NULL,
        matched_fields TEXT,
        mismatched_fields TEXT,
        explanation TEXT NOT NULL,
        recommended_action VARCHAR(200) NOT NULL,
        review_status VARCHAR(30) NOT NULL,
        reviewed_by VARCHAR(100),
        reviewed_at DATETIME,
        FOREIGN KEY(scan_id) REFERENCES duplicate_scan(id)
    )
    """,
]


def _new_memory_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _reflected_schema(engine):
    schema = {}
    inspector = inspect(engine)
    for table in inspector.get_table_names():
        schema[table] = [
            (
                column["name"],
                str(column["type"]),
                bool(column["nullable"]),
                bool(column["primary_key"]),
                column["default"],
            )
            for column in inspector.get_columns(table)
        ]
    return schema


def _schema_fingerprint(engine):
    inspector = inspect(engine)
    return {
        table: {
            "columns": _reflected_schema(engine)[table],
            "indexes": sorted(
                (
                    index["name"],
                    tuple(index["column_names"]),
                    bool(index["unique"]),
                )
                for index in inspector.get_indexes(table)
            ),
            "foreign_keys": sorted(
                (
                    tuple(foreign_key["constrained_columns"]),
                    foreign_key["referred_table"],
                    tuple(foreign_key["referred_columns"]),
                    foreign_key.get("options", {}).get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys(table)
            ),
            "unique_constraints": sorted(
                (
                    constraint["name"] or "",
                    tuple(constraint["column_names"]),
                )
                for constraint in inspector.get_unique_constraints(table)
            ),
        }
        for table in sorted(inspector.get_table_names())
    }


def _create_legacy_schema(engine):
    with engine.begin() as connection:
        for statement in LEGACY_SCHEMA_SQL:
            connection.execute(text(statement))
        connection.execute(
            text(
                """
                INSERT INTO duplicate_scan (
                    id, scan_name, source_type, selected_fields, threshold, status,
                    total_records, total_candidates, warnings_count, started_at,
                    completed_at, model_version
                ) VALUES (
                    7, 'legacy scan', 'CSV', '["CONTRACT"]', 75.0, 'COMPLETED',
                    2, 1, 3, '2026-07-01 01:02:03', NULL, 'hybrid-nlp-v1'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO duplicate_candidate (
                    id, scan_id, contract_a, part_no_a, description_a, contract_b,
                    part_no_b, description_b, similarity_score, confidence_level,
                    description_similarity, tfidf_score, fuzzy_score,
                    part_no_similarity, technical_token_score, matched_fields,
                    mismatched_fields, explanation, recommended_action,
                    review_status, reviewed_by, reviewed_at
                ) VALUES (
                    11, 7, 'SITE-A', 'A-100', 'Legacy left', 'SITE-A',
                    'B-100', 'Legacy right', 88.5, 'MEDIUM', 90.0, 89.0,
                    91.0, 40.0, 75.0, '["CONTRACT"]', '[]',
                    'legacy explanation', 'Review', 'UNREVIEWED', NULL, NULL
                )
                """
            )
        )


@pytest.fixture
def fresh_engine():
    engine = _new_memory_engine()
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def legacy_engine():
    engine = _new_memory_engine()
    _create_legacy_schema(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_fresh_create_all_has_exact_committed_schema(fresh_engine):
    actual = _reflected_schema(fresh_engine)

    assert set(actual) == {
        "duplicate_scan",
        "duplicate_candidate",
        "duplicate_feedback",
        "scan_warning",
        "rule_exclusion_audit",
    }
    assert "alembic_version" not in actual
    assert actual == EXPECTED_SCHEMA


def test_orm_client_defaults_are_not_fresh_server_defaults(fresh_engine):
    actual_scalar_defaults = {}
    actual_callable_defaults = set()
    for table_name, table in Base.metadata.tables.items():
        actual_scalar_defaults[table_name] = {}
        for column in table.columns:
            if column.default is None:
                continue
            if callable(column.default.arg):
                actual_callable_defaults.add((table_name, column.name))
            else:
                actual_scalar_defaults[table_name][column.name] = column.default.arg

    assert actual_scalar_defaults == EXPECTED_CLIENT_DEFAULTS
    assert actual_callable_defaults == EXPECTED_CALLABLE_DEFAULTS

    fresh_schema = _reflected_schema(fresh_engine)
    for table_name, additions in HELPER_ADDITIONS.items():
        columns = {column[0]: column for column in fresh_schema[table_name]}
        for column_name, _type, _nullable, _helper_default in additions:
            assert columns[column_name][4] is None, (
                f"{table_name}.{column_name} unexpectedly gained a server default"
            )


def test_fresh_schema_has_exact_indexes_foreign_keys_and_no_uniques(fresh_engine):
    inspector = inspect(fresh_engine)
    actual_indexes = {}
    actual_foreign_keys = {}

    for table in sorted(EXPECTED_SCHEMA):
        actual_indexes[table] = sorted(
            (
                index["name"],
                tuple(index["column_names"]),
                bool(index["unique"]),
            )
            for index in inspector.get_indexes(table)
        )
        actual_foreign_keys[table] = sorted(
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
                foreign_key.get("options", {}).get("ondelete"),
            )
            for foreign_key in inspector.get_foreign_keys(table)
        )
        assert inspector.get_unique_constraints(table) == []

    assert actual_indexes == EXPECTED_INDEXES
    assert actual_foreign_keys == EXPECTED_FOREIGN_KEYS


def test_sqlite_foreign_key_enforcement_is_currently_disabled(fresh_engine):
    with fresh_engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 0


def test_legacy_schema_upgrade_adds_exact_columns_defaults_and_preserves_rows(
    legacy_engine,
):
    before = _reflected_schema(legacy_engine)
    with legacy_engine.connect() as connection:
        scan_before = connection.execute(
            text("SELECT id, scan_name, total_records, model_version FROM duplicate_scan")
        ).one()
        candidate_before = connection.execute(
            text(
                "SELECT id, scan_id, part_no_a, description_a, part_no_b, "
                "description_b, similarity_score FROM duplicate_candidate"
            )
        ).one()

    ensure_sqlite_demo_columns(legacy_engine)
    after = _reflected_schema(legacy_engine)

    for table_name, expected_additions in HELPER_ADDITIONS.items():
        old_names = {column[0] for column in before[table_name]}
        actual_additions = [
            (name, type_name, nullable, default)
            for name, type_name, nullable, _primary_key, default in after[table_name]
            if name not in old_names
        ]
        assert actual_additions == expected_additions

    with legacy_engine.connect() as connection:
        scan_after = connection.execute(
            text("SELECT id, scan_name, total_records, model_version FROM duplicate_scan")
        ).one()
        candidate_after = connection.execute(
            text(
                "SELECT id, scan_id, part_no_a, description_a, part_no_b, "
                "description_b, similarity_score FROM duplicate_candidate"
            )
        ).one()
        scan_defaults = connection.execute(
            text("SELECT scan_mode, rejections_count FROM duplicate_scan")
        ).one()
        candidate_defaults = connection.execute(
            text(
                "SELECT business_status, rule_decision, rejection_reason, scan_mode, "
                "critical_mismatches, variant_attributes_a, variant_attributes_b, "
                "generic_description_warning, application_context_a, "
                "application_context_b, application_context_warning, "
                "normalized_description_a, normalized_description_b, "
                "normalized_part_no_a, normalized_part_no_b FROM duplicate_candidate"
            )
        ).one()

    assert scan_after == scan_before
    assert candidate_after == candidate_before
    assert scan_defaults == ("SAME_SITE_DUPLICATE", 0)
    assert candidate_defaults == (
        "POSSIBLE_DUPLICATE_REVIEW",
        "ALLOW",
        "",
        "SAME_SITE_DUPLICATE",
        "[]",
        "{}",
        "{}",
        "false",
        "[]",
        "[]",
        "false",
        "",
        "",
        "",
        "",
    )
    assert "alembic_version" not in inspect(legacy_engine).get_table_names()


def test_compatibility_helper_is_idempotent(legacy_engine):
    ensure_sqlite_demo_columns(legacy_engine)
    first_fingerprint = _schema_fingerprint(legacy_engine)
    with legacy_engine.connect() as connection:
        first_rows = (
            connection.execute(text("SELECT * FROM duplicate_scan")).all(),
            connection.execute(text("SELECT * FROM duplicate_candidate")).all(),
        )

    ensure_sqlite_demo_columns(legacy_engine)

    assert _schema_fingerprint(legacy_engine) == first_fingerprint
    with legacy_engine.connect() as connection:
        second_rows = (
            connection.execute(text("SELECT * FROM duplicate_scan")).all(),
            connection.execute(text("SELECT * FROM duplicate_candidate")).all(),
        )
    assert second_rows == first_rows


def test_fresh_and_helper_upgraded_server_defaults_intentionally_differ(
    fresh_engine,
    legacy_engine,
):
    ensure_sqlite_demo_columns(legacy_engine)
    fresh = _reflected_schema(fresh_engine)
    upgraded = _reflected_schema(legacy_engine)

    for table_name, additions in HELPER_ADDITIONS.items():
        fresh_defaults = {column[0]: column[4] for column in fresh[table_name]}
        upgraded_defaults = {column[0]: column[4] for column in upgraded[table_name]}
        for column_name, _type, _nullable, helper_default in additions:
            assert fresh_defaults[column_name] is None
            assert upgraded_defaults[column_name] == helper_default


def test_compatibility_helper_preserves_extra_table_and_managed_table_column(
    legacy_engine,
):
    with legacy_engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE duplicate_scan ADD COLUMN source_marker "
                "TEXT DEFAULT 'legacy-source'"
            )
        )
        connection.execute(
            text("CREATE TABLE unrelated_extension (id INTEGER PRIMARY KEY, payload TEXT)")
        )
        connection.execute(
            text("INSERT INTO unrelated_extension (id, payload) VALUES (3, 'keep me')")
        )

    ensure_sqlite_demo_columns(legacy_engine)

    inspector = inspect(legacy_engine)
    scan_columns = {column["name"]: column for column in inspector.get_columns("duplicate_scan")}
    assert scan_columns["source_marker"]["default"] == "'legacy-source'"
    assert "unrelated_extension" in inspector.get_table_names()
    with legacy_engine.connect() as connection:
        assert connection.execute(
            text("SELECT id, payload FROM unrelated_extension")
        ).one() == (3, "keep me")
        assert connection.execute(
            text("SELECT source_marker FROM duplicate_scan")
        ).scalar_one() == "legacy-source"


def test_non_sqlite_dialect_returns_before_connecting_or_issuing_ddl():
    class NonSQLiteURL:
        @staticmethod
        def get_backend_name():
            return "postgresql"

    class ConnectionForbiddenEngine:
        url = NonSQLiteURL()

        def __getattr__(self, name):
            raise AssertionError(f"non-SQLite helper unexpectedly accessed engine.{name}")

    assert ensure_sqlite_demo_columns(ConnectionForbiddenEngine()) is None


def test_missing_candidate_table_raises_after_partial_managed_upgrade_only():
    engine = _new_memory_engine()
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE duplicate_scan (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text("CREATE TABLE unrelated_extension (payload TEXT NOT NULL)")
            )
            connection.execute(
                text("INSERT INTO unrelated_extension VALUES ('unchanged')")
            )

        with pytest.raises(NoSuchTableError, match="duplicate_candidate"):
            ensure_sqlite_demo_columns(engine)

        inspector = inspect(engine)
        assert [column["name"] for column in inspector.get_columns("duplicate_scan")] == [
            "id",
            "scan_mode",
            "rejections_count",
        ]
        unrelated_columns = inspector.get_columns("unrelated_extension")
        assert [
            (
                column["name"],
                str(column["type"]),
                bool(column["nullable"]),
                column["default"],
                bool(column["primary_key"]),
            )
            for column in unrelated_columns
        ] == [
            ("payload", "TEXT", False, None, False)
        ]
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT payload FROM unrelated_extension")
            ).scalar_one() == "unchanged"
        assert "alembic_version" not in inspector.get_table_names()
    finally:
        engine.dispose()


def test_incompatible_existing_columns_are_preserved_without_repair():
    engine = _new_memory_engine()
    candidate_columns = ", ".join(
        f"{name} INTEGER DEFAULT 99"
        for name, _type, _nullable, _default in HELPER_ADDITIONS[
            "duplicate_candidate"
        ]
    )
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE duplicate_scan ("
                    "id INTEGER PRIMARY KEY, "
                    "scan_mode INTEGER DEFAULT 99, "
                    "rejections_count TEXT NOT NULL DEFAULT 'wrong'"
                    ")"
                )
            )
            connection.execute(
                text(
                    f"CREATE TABLE duplicate_candidate "
                    f"(id INTEGER PRIMARY KEY, {candidate_columns})"
                )
            )

        before = _schema_fingerprint(engine)
        ensure_sqlite_demo_columns(engine)

        assert _schema_fingerprint(engine) == before
        scan_columns = {
            column["name"]: column for column in inspect(engine).get_columns("duplicate_scan")
        }
        assert str(scan_columns["scan_mode"]["type"]) == "INTEGER"
        assert scan_columns["scan_mode"]["nullable"] is True
        assert scan_columns["scan_mode"]["default"] == "99"
        assert str(scan_columns["rejections_count"]["type"]) == "TEXT"
        assert scan_columns["rejections_count"]["nullable"] is False
        assert scan_columns["rejections_count"]["default"] == "'wrong'"
        assert "alembic_version" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_schema_characterization_uses_only_memory_or_pytest_temporary_database(
    tmp_path,
):
    memory_engine = _new_memory_engine()
    temporary_database = tmp_path / "schema-baseline.sqlite"
    file_engine = create_engine(f"sqlite:///{temporary_database.as_posix()}")
    try:
        assert memory_engine.url.database is None
        assert Path(file_engine.url.database).resolve() == temporary_database.resolve()
        Base.metadata.create_all(bind=file_engine)
        assert temporary_database.is_file()
    finally:
        memory_engine.dispose()
        file_engine.dispose()
