from pathlib import Path
import re

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects import sqlite

from app.db.database import Base
from app.db.models import Dataset, DatasetArtifact, DatasetVersion


BACKEND_ROOT = Path(__file__).resolve().parents[1]
INI_PATH = BACKEND_ROOT / "alembic.ini"
LEGACY_TABLES = {
    "duplicate_scan",
    "duplicate_candidate",
    "duplicate_feedback",
    "scan_warning",
    "rule_exclusion_audit",
}
REGISTRY_TABLES = {"datasets", "dataset_versions", "dataset_artifacts"}

EXPECTED_COLUMNS = {
    "datasets": [
        ("id", "CHAR(32)", False, True),
        ("name", "VARCHAR(255)", False, False),
        ("description", "TEXT", True, False),
        ("status", "VARCHAR(20)", False, False),
        ("created_at", "DATETIME", False, False),
        ("updated_at", "DATETIME", False, False),
    ],
    "dataset_versions": [
        ("id", "CHAR(32)", False, True),
        ("dataset_id", "CHAR(32)", False, False),
        ("version_number", "INTEGER", False, False),
        ("status", "VARCHAR(20)", False, False),
        ("source_filename", "VARCHAR(512)", False, False),
        ("source_media_type", "VARCHAR(255)", False, False),
        ("source_sha256", "VARCHAR(64)", False, False),
        ("source_size_bytes", "BIGINT", False, False),
        ("source_record_count", "BIGINT", True, False),
        ("created_at", "DATETIME", False, False),
        ("updated_at", "DATETIME", False, False),
    ],
    "dataset_artifacts": [
        ("id", "CHAR(32)", False, True),
        ("dataset_version_id", "CHAR(32)", False, False),
        ("artifact_kind", "VARCHAR(40)", False, False),
        ("artifact_ordinal", "INTEGER", False, False),
        ("object_uri", "VARCHAR(2048)", False, False),
        ("content_sha256", "VARCHAR(64)", False, False),
        ("size_bytes", "BIGINT", False, False),
        ("media_type", "VARCHAR(255)", False, False),
        ("created_at", "DATETIME", False, False),
    ],
}
ASCII_WHITESPACE = (" ", "\t", "\n", "\r", "\f", "\v")


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


EXPECTED_CHECKS = {
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
EXPECTED_UNIQUES = {
    "datasets": {},
    "dataset_versions": {
        "uq_dataset_versions_dataset_id_version_number": (
            "dataset_id", "version_number",
        ),
        "uq_dataset_versions_dataset_id_source_sha256_source_size_bytes": (
            "dataset_id", "source_sha256", "source_size_bytes",
        ),
    },
    "dataset_artifacts": {
        "uq_dataset_artifacts_dataset_version_id_artifact_kind_artifact_ordinal": (
            "dataset_version_id", "artifact_kind", "artifact_ordinal",
        ),
        "uq_dataset_artifacts_object_uri": ("object_uri",),
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


def _config(path: Path) -> Config:
    config = Config(str(INI_PATH))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    return config


def _revision(engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


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
    return normalized


def _sqlite_checks(engine, table: str) -> list[dict[str, str]]:
    with engine.connect() as connection:
        ddl = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = :table"
            ),
            {"table": table},
        ).scalar_one()
    checks: list[dict[str, str]] = []
    pattern = re.compile(
        r"\bCONSTRAINT\s+[\"`\[]?(?P<name>[A-Za-z0-9_]+)[\"`\]]?\s+CHECK\s*\(",
        flags=re.IGNORECASE,
    )
    for match in pattern.finditer(ddl):
        start = match.end()
        depth = 1
        quoted = False
        index = start
        while index < len(ddl) and depth:
            character = ddl[index]
            if character == "'":
                if quoted and index + 1 < len(ddl) and ddl[index + 1] == "'":
                    index += 2
                    continue
                quoted = not quoted
            elif not quoted:
                if character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
            index += 1
        assert depth == 0, f"unclosed SQLite check constraint: {match.group('name')}"
        checks.append(
            {"name": match.group("name"), "sqltext": ddl[start:index - 1]}
        )
    return checks


def _legacy_fingerprint(engine):
    inspector = inspect(engine)
    with engine.connect() as connection:
        inventory = tuple(
            connection.execute(
                text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' "
                    "AND name <> 'alembic_version' "
                    "AND tbl_name <> 'alembic_version' "
                    "AND name NOT IN ('datasets', 'dataset_versions', "
                    "'dataset_artifacts') "
                    "AND tbl_name NOT IN ('datasets', 'dataset_versions', "
                    "'dataset_artifacts') ORDER BY type, name, tbl_name"
                )
            ).all()
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
    tables = {
        table: {
            "columns": [
                (
                    column["name"],
                    str(column["type"]),
                    bool(column["nullable"]),
                    bool(column["primary_key"]),
                    column["default"],
                )
                for column in inspector.get_columns(table)
            ],
            "pk": inspector.get_pk_constraint(table),
            "fk": inspector.get_foreign_keys(table),
            "unique": inspector.get_unique_constraints(table),
            "checks": _sqlite_checks(engine, table),
            "indexes": inspector.get_indexes(table),
        }
        for table in sorted(LEGACY_TABLES)
    }
    return {
        "table_names": tuple(sorted(LEGACY_TABLES)),
        "tables": tables,
        "views": tuple(sorted(inspector.get_view_names())),
        "inventory": inventory,
        "rows": rows,
    }


def _registry_fingerprint(engine):
    inspector = inspect(engine)
    return {
        table: {
            "columns": [
                (
                    column["name"],
                    str(column["type"]),
                    bool(column["nullable"]),
                    bool(column["primary_key"]),
                    column["default"],
                )
                for column in inspector.get_columns(table)
            ],
            "pk": inspector.get_pk_constraint(table),
            "fk": inspector.get_foreign_keys(table),
            "unique": inspector.get_unique_constraints(table),
            "checks": _sqlite_checks(engine, table),
            "indexes": inspector.get_indexes(table),
        }
        for table in sorted(REGISTRY_TABLES)
    }


def _full_fingerprint(engine):
    inspector = inspect(engine)
    with engine.connect() as connection:
        inventory = tuple(
            connection.execute(
                text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' "
                    "ORDER BY type, name, tbl_name"
                )
            ).all()
        )
        version_rows = tuple(
            connection.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).scalars()
        )
        row_counts = tuple(
            (
                table,
                connection.execute(
                    text(f'SELECT count(*) FROM "{table}"')
                ).scalar_one(),
            )
            for table in sorted(LEGACY_TABLES | REGISTRY_TABLES)
        )
    return {
        "tables": tuple(sorted(inspector.get_table_names())),
        "views": tuple(sorted(inspector.get_view_names())),
        "inventory": inventory,
        "legacy": _legacy_fingerprint(engine),
        "registry": _registry_fingerprint(engine),
        "row_counts": row_counts,
        "revision": _revision(engine),
        "version_rows": version_rows,
    }


def _assert_registry_contract(engine) -> None:
    inspector = inspect(engine)
    for table in sorted(REGISTRY_TABLES):
        columns = [
            (
                item["name"],
                str(item["type"]),
                bool(item["nullable"]),
                bool(item["primary_key"]),
            )
            for item in inspector.get_columns(table)
        ]
        assert columns == EXPECTED_COLUMNS[table]
        assert all(
            item["default"] is None for item in inspector.get_columns(table)
        )
        assert inspector.get_pk_constraint(table) == {
            "constrained_columns": ["id"],
            "name": f"pk_{table}",
        }
        assert {
            item["name"]: _normalized_check(item["sqltext"])
            for item in _sqlite_checks(engine, table)
        } == {
            name: _normalized_check(sql)
            for name, sql in EXPECTED_CHECKS[table].items()
        }
        assert {
            item["name"]: tuple(item["column_names"])
            for item in inspector.get_unique_constraints(table)
        } == EXPECTED_UNIQUES[table]
        assert {
            (item["name"], tuple(item["column_names"]), bool(item["unique"]))
            for item in inspector.get_indexes(table)
        } == EXPECTED_INDEXES[table]

    version_fk = inspect(engine).get_foreign_keys("dataset_versions")
    assert version_fk == [
        {
            "name": "fk_dataset_versions_dataset_id_datasets",
            "constrained_columns": ["dataset_id"],
            "referred_schema": None,
            "referred_table": "datasets",
            "referred_columns": ["id"],
            "options": {"ondelete": "RESTRICT"},
        }
    ]
    artifact_fk = inspect(engine).get_foreign_keys("dataset_artifacts")
    assert artifact_fk == [
        {
            "name": (
                "fk_dataset_artifacts_dataset_version_id_dataset_versions"
            ),
            "constrained_columns": ["dataset_version_id"],
            "referred_schema": None,
            "referred_table": "dataset_versions",
            "referred_columns": ["id"],
            "options": {"ondelete": "RESTRICT"},
        }
    ]
    with engine.connect() as connection:
        assert {
            table: connection.execute(
                text(f'SELECT count(*) FROM "{table}"')
            ).scalar_one()
            for table in REGISTRY_TABLES
        } == {table: 0 for table in REGISTRY_TABLES}


def _assert_model_contract() -> None:
    for table_name in sorted(REGISTRY_TABLES):
        table = Base.metadata.tables[table_name]
        assert [
            (
                column.name,
                str(column.type.compile(dialect=sqlite.dialect())),
                bool(column.nullable),
                bool(column.primary_key),
            )
            for column in table.columns
        ] == EXPECTED_COLUMNS[table_name]
        assert all(column.server_default is None for column in table.columns)
        assert all(column.default is None for column in table.columns)
        assert table.primary_key.name == f"pk_{table_name}"
        assert tuple(column.name for column in table.primary_key.columns) == ("id",)
        assert {
            constraint.name: tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        } == EXPECTED_UNIQUES[table_name]
        assert {
            constraint.name: _normalized_check(str(constraint.sqltext))
            for constraint in table.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        } == {
            name: _normalized_check(sql)
            for name, sql in EXPECTED_CHECKS[table_name].items()
        }
        assert {
            (
                index.name,
                tuple(column.name for column in index.columns),
                bool(index.unique),
            )
            for index in table.indexes
        } == EXPECTED_INDEXES[table_name]

    version_fk = tuple(
        Base.metadata.tables["dataset_versions"].foreign_key_constraints
    )
    artifact_fk = tuple(
        Base.metadata.tables["dataset_artifacts"].foreign_key_constraints
    )
    assert len(version_fk) == len(artifact_fk) == 1
    assert (
        version_fk[0].name,
        tuple(column.name for column in version_fk[0].columns),
        tuple(element.target_fullname for element in version_fk[0].elements),
        version_fk[0].ondelete,
    ) == (
        "fk_dataset_versions_dataset_id_datasets",
        ("dataset_id",),
        ("datasets.id",),
        "RESTRICT",
    )
    assert (
        artifact_fk[0].name,
        tuple(column.name for column in artifact_fk[0].columns),
        tuple(element.target_fullname for element in artifact_fk[0].elements),
        artifact_fk[0].ondelete,
    ) == (
        "fk_dataset_artifacts_dataset_version_id_dataset_versions",
        ("dataset_version_id",),
        ("dataset_versions.id",),
        "RESTRICT",
    )
    assert not inspect(Dataset).relationships
    assert not inspect(DatasetVersion).relationships
    assert not inspect(DatasetArtifact).relationships


def _insert_legacy_sentinels(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO duplicate_scan (
                id, scan_name, source_type, selected_fields, threshold,
                status, total_records, total_candidates, warnings_count,
                rejections_count, scan_mode, started_at, completed_at,
                model_version
            ) VALUES (
                1, 'registry sentinel', 'CSV', '[]', 75, 'COMPLETED',
                2, 1, 1, 1, 'SAME_SITE_DUPLICATE',
                '2026-08-06 01:00:00', NULL, 'hybrid-nlp-v1'
            )
        """))
        connection.execute(text("""
            INSERT INTO duplicate_candidate (
                id, scan_id, part_no_a, description_a, part_no_b,
                description_b, similarity_score, confidence_level,
                description_similarity, tfidf_score, fuzzy_score,
                part_no_similarity, technical_token_score, explanation,
                recommended_action, business_status, rule_decision,
                scan_mode, review_status
            ) VALUES (
                2, 1, 'A', 'left', 'B', 'right', 88, 'MEDIUM',
                88, 88, 88, 0, 0, 'sentinel', 'review',
                'POSSIBLE_DUPLICATE_REVIEW', 'ALLOW',
                'SAME_SITE_DUPLICATE', 'UNREVIEWED'
            )
        """))
        connection.execute(text("""
            INSERT INTO duplicate_feedback (
                id, candidate_id, user_decision, created_by, created_at
            ) VALUES (3, 2, 'UNSURE', 'tester', '2026-08-06 01:01:00')
        """))
        connection.execute(text("""
            INSERT INTO scan_warning (
                id, scan_id, warning_type, message, created_at
            ) VALUES (4, 1, 'SENTINEL', 'keep', '2026-08-06 01:02:00')
        """))
        connection.execute(text("""
            INSERT INTO rule_exclusion_audit (
                id, scan_id, part_no_a, description_a, part_no_b,
                description_b, similarity_score, confidence_level,
                business_status, rule_decision, rejection_reason,
                explanation, created_at
            ) VALUES (
                5, 1, 'C', 'left', 'D', 'right', 0, 'IGNORE',
                'REJECTED_BY_BUSINESS_RULE', 'REJECT', 'SENTINEL',
                'keep', '2026-08-06 01:03:00'
            )
        """))


def _sentinel_values(engine):
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                text(f'SELECT id FROM "{table}" ORDER BY id')
            ).scalars().all()
            for table in sorted(LEGACY_TABLES)
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
def test_statement_keyword_parser_is_comment_safe(statement, expected):
    assert _statement_keyword(statement) == expected


def test_upgrade_0001_to_0002_preserves_legacy_and_adds_exact_registry(
    tmp_path,
):
    path = tmp_path / "upgrade.sqlite"
    config = _config(path)
    command.upgrade(config, "0001_current_schema")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        _insert_legacy_sentinels(engine)
        legacy_before = _legacy_fingerprint(engine)
        rows_before = _sentinel_values(engine)
    finally:
        engine.dispose()

    command.upgrade(config, "0002_dataset_registry")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        assert _revision(engine) == "0002_dataset_registry"
        assert _legacy_fingerprint(engine) == legacy_before
        assert _sentinel_values(engine) == rows_before
        _assert_registry_contract(engine)
    finally:
        engine.dispose()


def test_empty_database_to_head_second_head_noop_and_model_parity(tmp_path):
    path = tmp_path / "head.sqlite"
    config = _config(path)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    statements: list[str] = []
    try:
        assert set(inspect(engine).get_table_names()) == (
            LEGACY_TABLES | REGISTRY_TABLES | {"alembic_version"}
        )
        assert _revision(engine) == "0002_dataset_registry"
        _assert_registry_contract(engine)
        first = _full_fingerprint(engine)

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            with engine.connect() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
        finally:
            event.remove(engine, "before_cursor_execute", capture)
            config.attributes.pop("connection", None)

        observable = tuple(statement for statement in statements if statement.strip())
        keywords = tuple(_statement_keyword(statement) for statement in observable)
        assert all(keywords)
        assert not set(keywords).intersection(
            {"CREATE", "ALTER", "DROP", "COMMENT", "GRANT", "REVOKE", "TRUNCATE"}
        )
        assert _revision(engine) == "0002_dataset_registry"
        assert _full_fingerprint(engine) == first
        _assert_model_contract()
    finally:
        engine.dispose()


def test_disposable_downgrade_and_reupgrade_preserve_only_legacy(tmp_path):
    path = tmp_path / "roundtrip.sqlite"
    config = _config(path)
    command.upgrade(config, "0001_current_schema")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        _insert_legacy_sentinels(engine)
        legacy_before = _legacy_fingerprint(engine)
        rows_before = _sentinel_values(engine)
    finally:
        engine.dispose()
    command.upgrade(config, "0002_dataset_registry")
    command.downgrade(config, "0001_current_schema")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        assert _revision(engine) == "0001_current_schema"
        assert not REGISTRY_TABLES.intersection(inspect(engine).get_table_names())
        assert _legacy_fingerprint(engine) == legacy_before
        assert _sentinel_values(engine) == rows_before
    finally:
        engine.dispose()
    command.upgrade(config, "0002_dataset_registry")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    try:
        assert _revision(engine) == "0002_dataset_registry"
        assert _legacy_fingerprint(engine) == legacy_before
        assert _sentinel_values(engine) == rows_before
        _assert_registry_contract(engine)
    finally:
        engine.dispose()


def test_portable_sha_and_ascii_whitespace_checks_in_sqlite(tmp_path):
    path = tmp_path / "checks.sqlite"
    config = _config(path)
    command.upgrade(config, "0002_dataset_registry")
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    dataset_id = "1" * 32
    version_id = "2" * 32
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO datasets VALUES "
                    "(:id, 'valid', NULL, 'ACTIVE', :now, :now)"
                ),
                {"id": dataset_id, "now": "2026-08-06 01:00:00"},
            )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO dataset_versions VALUES ("
                        ":id, :dataset_id, 1, 'REGISTERED', 'source.csv', "
                        "'text/csv', :sha, 1, NULL, :now, :now)"
                    ),
                    {
                        "id": version_id,
                        "dataset_id": dataset_id,
                        "sha": "A" * 64,
                        "now": "2026-08-06 01:00:00",
                    },
                )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO dataset_versions VALUES ("
                    ":id, :dataset_id, 1, 'REGISTERED', 'source.csv', "
                    "'text/csv', :sha, 1, NULL, :now, :now)"
                ),
                {
                    "id": version_id,
                    "dataset_id": dataset_id,
                    "sha": "a" * 64,
                    "now": "2026-08-06 01:00:00",
                },
            )
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO dataset_artifacts VALUES ("
                        ":id, :version_id, 'SOURCE_CSV', 0, 'opaque://one', "
                        ":sha, 1, 'text/csv', :now)"
                    ),
                    {
                        "id": "3" * 32,
                        "version_id": version_id,
                        "sha": "z" * 64,
                        "now": "2026-08-06 01:00:00",
                    },
                )
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO dataset_artifacts VALUES ("
                    ":id, :version_id, 'SOURCE_CSV', 0, 'opaque://one', "
                    ":sha, 1, 'text/csv', :now)"
                ),
                {
                    "id": "3" * 32,
                    "version_id": version_id,
                    "sha": "b" * 64,
                    "now": "2026-08-06 01:00:00",
                },
            )
        checks = (
            ("datasets", "name", dataset_id),
            ("dataset_versions", "source_filename", version_id),
            ("dataset_versions", "source_media_type", version_id),
            ("dataset_artifacts", "object_uri", "3" * 32),
            ("dataset_artifacts", "media_type", "3" * 32),
        )
        rejected = ("", " ", "\t", "\n", "\r", "\f", "\v", " \t\r\n\f\v ")
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
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
    finally:
        engine.dispose()
