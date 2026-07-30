from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, FrozenInstanceError
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.pool import QueuePool

from app.db.alembic_bootstrap import (
    SQLiteAlembicBootstrapConfigurationError,
    SQLiteAlembicBootstrapError,
    SQLiteAlembicBootstrapMigrationError,
    SQLiteAlembicBootstrapOutcome,
    SQLiteAlembicBootstrapPostconditionError,
    SQLiteAlembicBootstrapRefusedError,
    SQLiteAlembicBootstrapResult,
    bootstrap_pristine_sqlite,
)
from app.db.schema_fingerprint import (
    CURRENT_NAMED_FINGERPRINT,
    SQLiteSchemaClassification,
    SQLiteSchemaClassificationResult,
    SQLiteSchemaProfileId,
    UnsupportedSchemaDialectError,
    classify_sqlite_schema,
)
from test_schema_fingerprint import _create_historical_profile


MANAGED_TABLES = {
    "duplicate_candidate",
    "duplicate_feedback",
    "duplicate_scan",
    "rule_exclusion_audit",
    "scan_warning",
}


def _engine(tmp_path: Path, name: str = "database.sqlite"):
    return create_engine(
        f"sqlite:///{(tmp_path / name).as_posix()}",
        poolclass=QueuePool,
    )


def _catalog(engine) -> tuple[tuple[object, ...], ...]:
    with engine.connect() as connection:
        return tuple(
            connection.execute(
                text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_schema "
                    "ORDER BY type, name, tbl_name"
                )
            )
        )


def _bytes(path: Path) -> tuple[str, int]:
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest(), len(content)


@dataclass(frozen=True)
class _PersistenceSnapshot:
    catalog: tuple[tuple[object, ...], ...]
    schema_version: int
    sha256: str
    size: int
    modification_time_ns: int
    sidecar_artifacts: tuple[bool, bool, bool]


def _persistence_snapshot(engine, path: Path) -> _PersistenceSnapshot:
    with engine.connect() as connection:
        catalog = tuple(
            connection.execute(
                text(
                    "SELECT type, name, tbl_name, sql FROM sqlite_schema "
                    "ORDER BY type, name, tbl_name"
                )
            )
        )
        schema_version = connection.execute(
            text("PRAGMA schema_version")
        ).scalar_one()
    sha256, size = _bytes(path)
    return _PersistenceSnapshot(
        catalog=catalog,
        schema_version=schema_version,
        sha256=sha256,
        size=size,
        modification_time_ns=path.stat().st_mtime_ns,
        sidecar_artifacts=tuple(
            Path(f"{path}{suffix}").exists()
            for suffix in ("-journal", "-wal", "-shm")
        ),
    )


@contextmanager
def _assert_service_connection_makes_no_dbapi_changes(engine):
    checkout_changes = []
    checkin_changes = []

    def record_checkout(dbapi_connection, *_args):
        checkout_changes.append(dbapi_connection.total_changes)

    def record_checkin(dbapi_connection, *_args):
        checkin_changes.append(dbapi_connection.total_changes)

    event.listen(engine.pool, "checkout", record_checkout)
    event.listen(engine.pool, "checkin", record_checkin)
    try:
        yield
    finally:
        event.remove(engine.pool, "checkout", record_checkout)
        event.remove(engine.pool, "checkin", record_checkin)
    assert len(checkout_changes) == 1
    assert len(checkin_changes) == 1
    assert checkin_changes == checkout_changes


def _assert_no_checkout(engine) -> None:
    assert engine.pool.checkedout() == 0


def test_public_contract_is_exact_frozen_and_slotted():
    assert [item.value for item in SQLiteAlembicBootstrapOutcome] == [
        "ALREADY_CURRENT",
        "BOOTSTRAPPED",
    ]
    assert issubclass(
        SQLiteAlembicBootstrapRefusedError,
        SQLiteAlembicBootstrapError,
    )
    assert issubclass(
        SQLiteAlembicBootstrapConfigurationError,
        SQLiteAlembicBootstrapError,
    )
    assert issubclass(
        SQLiteAlembicBootstrapMigrationError,
        SQLiteAlembicBootstrapError,
    )
    assert issubclass(
        SQLiteAlembicBootstrapPostconditionError,
        SQLiteAlembicBootstrapError,
    )
    empty = SQLiteSchemaClassificationResult(
        SQLiteSchemaClassification.EMPTY,
        None,
        hashlib.sha256(b"[]").hexdigest(),
        None,
        (),
        (),
    )
    result = SQLiteAlembicBootstrapResult(
        SQLiteAlembicBootstrapOutcome.BOOTSTRAPPED,
        empty,
        empty,
    )
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.outcome = SQLiteAlembicBootstrapOutcome.ALREADY_CURRENT
    assert isinstance(result.pre_classification.extra_tables, tuple)
    assert isinstance(result.pre_classification.conflicts, tuple)


def test_invalid_input_and_connection_are_rejected(tmp_path):
    engine = _engine(tmp_path)
    with engine.connect() as connection:
        with pytest.raises(TypeError):
            bootstrap_pristine_sqlite(connection)
    with pytest.raises(TypeError):
        bootstrap_pristine_sqlite(object())
    engine.dispose()


def test_non_sqlite_is_rejected_before_connect(monkeypatch, tmp_path):
    engine = _engine(tmp_path)
    monkeypatch.setattr(engine.dialect, "name", "postgresql")
    opened = False

    def record_open(*_args, **_kwargs):
        nonlocal opened
        opened = True

    event.listen(engine, "engine_connect", record_open)
    with pytest.raises(UnsupportedSchemaDialectError):
        bootstrap_pristine_sqlite(engine)
    assert opened is False
    engine.dispose()


def test_pristine_bootstrap_uses_supplied_connection_and_commits(
    monkeypatch,
    tmp_path,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)
    path = tmp_path / "database.sqlite"
    assert classify_sqlite_schema(engine).classification is (
        SQLiteSchemaClassification.EMPTY
    )
    real_upgrade = alembic_bootstrap.command.upgrade
    calls = []

    def upgrade(config, target):
        supplied = config.attributes["connection"]
        assert isinstance(supplied, Connection)
        assert supplied.engine is engine
        assert config.get_main_option("sqlalchemy.url") == (
            "driver://user:pass@host/dbname"
        )
        calls.append((supplied, target))
        return real_upgrade(config, target)

    monkeypatch.setattr(alembic_bootstrap.command, "upgrade", upgrade)
    result = bootstrap_pristine_sqlite(engine)
    assert result.outcome is SQLiteAlembicBootstrapOutcome.BOOTSTRAPPED
    assert result.pre_classification.classification is (
        SQLiteSchemaClassification.EMPTY
    )
    assert result.post_classification.classification is (
        SQLiteSchemaClassification.CURRENT_ALEMBIC
    )
    assert result.post_classification.profile_id is (
        SQLiteSchemaProfileId.CURRENT_ALEMBIC_0001
    )
    assert result.post_classification.managed_fingerprint_sha256 == (
        CURRENT_NAMED_FINGERPRINT
    )
    assert result.post_classification.alembic_revision == "0001_current_schema"
    assert result.post_classification.conflicts == ()
    assert result.post_classification.extra_tables == ()
    assert len(calls) == 1
    assert calls[0][1] == "head"
    assert set(inspect(engine).get_table_names()) == MANAGED_TABLES | {
        "alembic_version"
    }
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "0001_current_schema"
        for table in MANAGED_TABLES:
            assert connection.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')
            ).scalar_one() == 0
    assert path.exists()
    _assert_no_checkout(engine)
    engine.dispose()


def test_sequential_repeatability_and_engine_ownership(tmp_path):
    engine = _engine(tmp_path)
    first = bootstrap_pristine_sqlite(engine)
    second = bootstrap_pristine_sqlite(engine)
    assert first.outcome is SQLiteAlembicBootstrapOutcome.BOOTSTRAPPED
    assert second.outcome is SQLiteAlembicBootstrapOutcome.ALREADY_CURRENT
    assert second.pre_classification is second.post_classification
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM alembic_version")
        ).scalar_one() == 1
    assert classify_sqlite_schema(engine).classification is (
        SQLiteSchemaClassification.CURRENT_ALEMBIC
    )
    _assert_no_checkout(engine)
    engine.dispose()


def test_already_current_is_exact_noop_without_config_or_upgrade(
    monkeypatch,
    tmp_path,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)
    bootstrap_pristine_sqlite(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE extension (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO extension VALUES (7)"))
        connection.execute(
            text(
                "CREATE VIEW extension_view AS "
                "SELECT id FROM extension"
            )
        )
    path = tmp_path / "database.sqlite"
    before = _persistence_snapshot(engine, path)
    assert before.sidecar_artifacts == (False, False, False)
    statements = []
    event.listen(
        engine,
        "before_cursor_execute",
        lambda _conn, _cursor, statement, _params, _context, _many:
            statements.append(statement),
    )
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    monkeypatch.setattr(
        alembic_bootstrap.command,
        "upgrade",
        lambda *_args, **_kwargs: pytest.fail("upgrade must not run"),
    )
    with _assert_service_connection_makes_no_dbapi_changes(engine):
        result = bootstrap_pristine_sqlite(engine)
    assert result.outcome is SQLiteAlembicBootstrapOutcome.ALREADY_CURRENT
    assert result.pre_classification is result.post_classification
    assert result.pre_classification.extra_tables == ("extension",)
    assert _persistence_snapshot(engine, path) == before
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM extension")).scalar_one() == 7
    assert all(
        statement.lstrip().upper().startswith(("SELECT", "PRAGMA"))
        for statement in statements
    )
    _assert_no_checkout(engine)
    engine.dispose()


@pytest.mark.parametrize("view_name", ["sqliteXview", "SQLiteXview"])
def test_near_internal_prefix_view_is_refused_and_preserved(
    monkeypatch,
    tmp_path,
    view_name,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path, f"{view_name}.sqlite")
    path = tmp_path / f"{view_name}.sqlite"
    with engine.begin() as connection:
        connection.execute(
            text(f'CREATE VIEW "{view_name}" AS SELECT 1 AS id')
        )
    pre = classify_sqlite_schema(engine)
    assert pre.classification is SQLiteSchemaClassification.EMPTY
    assert pre.profile_id is None
    assert pre.extra_tables == ()
    assert pre.conflicts == ()
    before = _persistence_snapshot(engine, path)
    assert before.sidecar_artifacts == (False, False, False)
    with engine.connect() as connection:
        assert connection.execute(
            text(f'SELECT id FROM "{view_name}"')
        ).scalar_one() == 1
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    monkeypatch.setattr(
        alembic_bootstrap.command,
        "upgrade",
        lambda *_args, **_kwargs: pytest.fail("upgrade must not run"),
    )
    with _assert_service_connection_makes_no_dbapi_changes(engine):
        with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
            bootstrap_pristine_sqlite(engine)
    assert captured.value.reason == "database_not_pristine"
    assert captured.value.classification_result == pre
    assert captured.value.user_schema_objects == (
        f"view:{view_name}:{view_name}",
    )
    assert _persistence_snapshot(engine, path) == before
    assert "alembic_version" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(
            text(f'SELECT id FROM "{view_name}"')
        ).scalar_one() == 1
    _assert_no_checkout(engine)
    engine.dispose()


@pytest.mark.parametrize(
    ("ddl", "expected"),
    [
        (
            ["CREATE TABLE other (id INTEGER PRIMARY KEY)"],
            ("table:other:other",),
        ),
        (
            [
                "CREATE TABLE other (id INTEGER PRIMARY KEY, value TEXT)",
                "INSERT INTO other VALUES (1, 'preserve me')",
            ],
            ("table:other:other",),
        ),
        (
            ["CREATE VIEW other_view AS SELECT 1 AS id"],
            ("view:other_view:other_view",),
        ),
        (
            [
                "CREATE TABLE other (id INTEGER PRIMARY KEY)",
                "CREATE TRIGGER other_trigger AFTER INSERT ON other "
                "BEGIN UPDATE other SET id = NEW.id WHERE id = NEW.id; END",
            ],
            ("table:other:other", "trigger:other_trigger:other"),
        ),
        (
            [
                "CREATE TABLE other (id INTEGER, value TEXT)",
                "CREATE INDEX other_index ON other(value)",
            ],
            ("index:other_index:other", "table:other:other"),
        ),
        (
            [
                "CREATE TABLE other (id INTEGER, value TEXT)",
                "CREATE INDEX other_index ON other(value)",
                "CREATE VIEW other_view AS SELECT id FROM other",
                "CREATE TRIGGER other_trigger AFTER INSERT ON other "
                "BEGIN UPDATE other SET value = value WHERE id = NEW.id; END",
            ],
            (
                "index:other_index:other",
                "table:other:other",
                "trigger:other_trigger:other",
                "view:other_view:other_view",
            ),
        ),
    ],
)
def test_non_pristine_schema_objects_are_reported_and_preserved(
    monkeypatch,
    tmp_path,
    ddl,
    expected,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)
    with engine.begin() as connection:
        for statement in ddl:
            connection.execute(text(statement))
    path = tmp_path / "database.sqlite"
    before_catalog = _catalog(engine)
    before_bytes = _bytes(path)
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    monkeypatch.setattr(
        alembic_bootstrap.command,
        "upgrade",
        lambda *_args, **_kwargs: pytest.fail("upgrade must not run"),
    )
    with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.classification_result == classify_sqlite_schema(engine)
    assert captured.value.user_schema_objects == expected
    assert _catalog(engine) == before_catalog
    assert _bytes(path) == before_bytes
    assert "alembic_version" not in inspect(engine).get_table_names()
    _assert_no_checkout(engine)
    engine.dispose()


@pytest.mark.parametrize(
    ("ddl", "classification"),
    [
        (
            "CREATE TABLE duplicate_scan (id INTEGER PRIMARY KEY)",
            SQLiteSchemaClassification.INCOMPLETE,
        ),
        (
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL); "
            "INSERT INTO alembic_version VALUES ('unknown_revision')",
            SQLiteSchemaClassification.UNKNOWN,
        ),
        (
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL); "
            "INSERT INTO alembic_version VALUES ('one'); "
            "INSERT INTO alembic_version VALUES ('two')",
            SQLiteSchemaClassification.UNKNOWN,
        ),
    ],
)
def test_representative_classifier_states_are_refused_before_config(
    monkeypatch,
    tmp_path,
    ddl,
    classification,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)
    with engine.begin() as connection:
        for statement in ddl.split("; "):
            connection.execute(text(statement))
    pre = classify_sqlite_schema(engine)
    assert pre.classification is classification
    before = _catalog(engine)
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.classification_result is not None
    assert captured.value.classification_result == pre
    assert captured.value.user_schema_objects == ()
    assert _catalog(engine) == before
    _assert_no_checkout(engine)
    engine.dispose()


def test_extra_managed_column_is_unknown_and_refused(
    monkeypatch,
    tmp_path,
):
    from app.db import alembic_bootstrap
    from app.db.database import Base
    from app.db import models as _models  # noqa: F401

    engine = _engine(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE duplicate_scan ADD COLUMN unexpected TEXT")
        )
    pre = classify_sqlite_schema(engine)
    assert pre.classification is SQLiteSchemaClassification.UNKNOWN
    assert any(
        conflict.code == "extra_managed_column"
        for conflict in pre.conflicts
    )
    before = _catalog(engine)
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.classification_result == pre
    assert _catalog(engine) == before
    _assert_no_checkout(engine)
    engine.dispose()


def test_managed_type_conflict_is_incompatible_and_refused(
    monkeypatch,
    tmp_path,
):
    from app.db import alembic_bootstrap
    from app.db.database import Base
    from app.db import models as _models  # noqa: F401

    engine = _engine(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE duplicate_scan RENAME TO original_duplicate_scan")
        )
        connection.execute(
            text(
                "CREATE TABLE duplicate_scan ("
                "id INTEGER NOT NULL, "
                "scan_name INTEGER NOT NULL, "
                "source_type VARCHAR(30) NOT NULL, "
                "selected_fields TEXT NOT NULL, "
                "threshold FLOAT NOT NULL, "
                "status VARCHAR(30) NOT NULL, "
                "total_records INTEGER, "
                "total_candidates INTEGER, "
                "warnings_count INTEGER, "
                "rejections_count INTEGER, "
                "scan_mode VARCHAR(60) NOT NULL, "
                "started_at DATETIME NOT NULL, "
                "completed_at DATETIME, "
                "model_version VARCHAR(50) NOT NULL, "
                "CONSTRAINT pk_duplicate_scan PRIMARY KEY (id)"
                ")"
            )
        )
    pre = classify_sqlite_schema(engine)
    assert pre.classification is SQLiteSchemaClassification.INCOMPATIBLE
    assert any(conflict.code == "column_type" for conflict in pre.conflicts)
    before = _catalog(engine)
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.classification_result == pre
    assert _catalog(engine) == before
    _assert_no_checkout(engine)
    engine.dispose()


def test_current_unversioned_is_refused_without_mutation(monkeypatch, tmp_path):
    from app.db import alembic_bootstrap
    from app.db.database import Base
    from app.db import models as _models  # noqa: F401

    engine = _engine(tmp_path)
    Base.metadata.create_all(engine)
    pre = classify_sqlite_schema(engine)
    assert pre.classification is SQLiteSchemaClassification.CURRENT_UNVERSIONED
    assert pre.profile_id is SQLiteSchemaProfileId.CURRENT_NAMED_UNVERSIONED
    before = _catalog(engine)
    monkeypatch.setattr(
        alembic_bootstrap.command,
        "upgrade",
        lambda *_args, **_kwargs: pytest.fail("upgrade must not run"),
    )
    with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.classification_result == pre
    assert _catalog(engine) == before
    _assert_no_checkout(engine)
    engine.dispose()


@pytest.mark.parametrize(
    ("fixture_profile", "classification", "profile_id"),
    [
        (
            "protected",
            SQLiteSchemaClassification.CURRENT_UNVERSIONED,
            SQLiteSchemaProfileId.PROTECTED_BASELINE_UNNAMED,
        ),
        (
            "07",
            SQLiteSchemaClassification.RECOGNIZED_LEGACY,
            SQLiteSchemaProfileId.HELPER_FROM_07C9A6E,
        ),
        (
            "002",
            SQLiteSchemaClassification.RECOGNIZED_LEGACY,
            SQLiteSchemaProfileId.HELPER_FROM_00204E1,
        ),
        (
            "later",
            SQLiteSchemaClassification.RECOGNIZED_LEGACY,
            SQLiteSchemaProfileId.HELPER_FROM_FEE3F3D_OR_42FA7BA,
        ),
    ],
)
def test_historical_profiles_are_refused_without_mutation(
    monkeypatch,
    tmp_path,
    fixture_profile,
    classification,
    profile_id,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)
    _create_historical_profile(engine, fixture_profile)
    pre = classify_sqlite_schema(engine)
    assert pre.classification is classification
    assert pre.profile_id is profile_id
    before = _catalog(engine)
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    monkeypatch.setattr(
        alembic_bootstrap.command,
        "upgrade",
        lambda *_args, **_kwargs: pytest.fail("upgrade must not run"),
    )
    with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.classification_result == pre
    assert captured.value.user_schema_objects == ()
    assert _catalog(engine) == before
    _assert_no_checkout(engine)
    engine.dispose()


def test_defensive_malformed_current_result_is_refused(monkeypatch, tmp_path):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)
    malformed = SQLiteSchemaClassificationResult(
        SQLiteSchemaClassification.CURRENT_ALEMBIC,
        SQLiteSchemaProfileId.CURRENT_ALEMBIC_0001,
        CURRENT_NAMED_FINGERPRINT,
        "wrong_revision",
        (),
        (),
    )
    monkeypatch.setattr(
        alembic_bootstrap,
        "classify_sqlite_schema",
        lambda _connection: malformed,
    )
    monkeypatch.setattr(
        alembic_bootstrap,
        "_verified_config",
        lambda _pre: pytest.fail("configuration must not be resolved"),
    )
    with pytest.raises(SQLiteAlembicBootstrapRefusedError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.classification_result is malformed
    engine.dispose()


@pytest.mark.parametrize(
    ("heads", "reason"),
    [
        ((), "alembic_head_count_invalid"),
        (("one", "two"), "alembic_head_count_invalid"),
        (("wrong",), "alembic_head_mismatch"),
    ],
)
def test_invalid_head_configuration_is_fail_closed(
    monkeypatch,
    tmp_path,
    heads,
    reason,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)

    class Script:
        def get_heads(self):
            return list(heads)

    monkeypatch.setattr(
        alembic_bootstrap.ScriptDirectory,
        "from_config",
        lambda _config: Script(),
    )
    monkeypatch.setattr(
        alembic_bootstrap.command,
        "upgrade",
        lambda *_args, **_kwargs: pytest.fail("upgrade must not run"),
    )
    with pytest.raises(SQLiteAlembicBootstrapConfigurationError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.reason == reason
    assert captured.value.classification_result.classification is (
        SQLiteSchemaClassification.EMPTY
    )
    assert inspect(engine).get_table_names() == []
    _assert_no_checkout(engine)
    engine.dispose()


def test_missing_and_malformed_configuration_preserve_cause(
    monkeypatch,
    tmp_path,
):
    from app.db import alembic_bootstrap

    for case in ("missing", "malformed"):
        engine = _engine(tmp_path, f"{case}.sqlite")
        if case == "missing":
            monkeypatch.setattr(
                alembic_bootstrap,
                "_alembic_ini_path",
                lambda: tmp_path / "absent.ini",
            )
        else:
            monkeypatch.setattr(
                alembic_bootstrap.ScriptDirectory,
                "from_config",
                lambda _config: (_ for _ in ()).throw(ValueError("bad script")),
            )
        with pytest.raises(
            SQLiteAlembicBootstrapConfigurationError
        ) as captured:
            bootstrap_pristine_sqlite(engine)
        assert captured.value.__cause__ is not None
        assert inspect(engine).get_table_names() == []
        _assert_no_checkout(engine)
        engine.dispose()
        monkeypatch.undo()


def test_migration_failure_preserves_cause_and_partial_state(
    monkeypatch,
    tmp_path,
):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)
    original = RuntimeError("migration failed")

    def fail(config, target):
        assert target == "head"
        connection = config.attributes["connection"]
        connection.execute(text("CREATE TABLE partial_object (id INTEGER)"))
        connection.commit()
        raise original

    monkeypatch.setattr(alembic_bootstrap.command, "upgrade", fail)
    with pytest.raises(SQLiteAlembicBootstrapMigrationError) as captured:
        bootstrap_pristine_sqlite(engine)
    assert captured.value.__cause__ is original
    assert captured.value.pre_classification.classification is (
        SQLiteSchemaClassification.EMPTY
    )
    assert captured.value.post_failure_classification is not None
    assert "partial_object" in inspect(engine).get_table_names()
    _assert_no_checkout(engine)
    engine.dispose()


def test_postcondition_failures_preserve_observed_state(
    monkeypatch,
    tmp_path,
):
    from app.db import alembic_bootstrap

    for name, create_extra in (("no_change", False), ("extra", True)):
        engine = _engine(tmp_path, f"{name}.sqlite")

        def incomplete(config, _target):
            if create_extra:
                connection = config.attributes["connection"]
                connection.execute(text("CREATE TABLE unexpected (id INTEGER)"))
                connection.commit()

        monkeypatch.setattr(alembic_bootstrap.command, "upgrade", incomplete)
        with pytest.raises(
            SQLiteAlembicBootstrapPostconditionError
        ) as captured:
            bootstrap_pristine_sqlite(engine)
        assert captured.value.pre_classification.classification is (
            SQLiteSchemaClassification.EMPTY
        )
        if create_extra:
            assert "unexpected" in inspect(engine).get_table_names()
        _assert_no_checkout(engine)
        engine.dispose()


def test_preflight_transaction_is_closed_before_upgrade(monkeypatch, tmp_path):
    from app.db import alembic_bootstrap

    engine = _engine(tmp_path)

    def inspect_transaction(config, _target):
        connection = config.attributes["connection"]
        assert connection.in_transaction() is False
        raise RuntimeError("stop after transaction assertion")

    monkeypatch.setattr(
        alembic_bootstrap.command,
        "upgrade",
        inspect_transaction,
    )
    with pytest.raises(SQLiteAlembicBootstrapMigrationError):
        bootstrap_pristine_sqlite(engine)
    _assert_no_checkout(engine)
    engine.dispose()


def test_prohibited_boundaries_and_exact_file_scope():
    backend = Path(__file__).resolve().parents[1]
    source = (
        backend / "app" / "db" / "alembic_bootstrap.py"
    ).read_text(encoding="utf-8")
    main_source = (backend / "app" / "main.py").read_text(encoding="utf-8")
    prohibited = (
        "command.stamp",
        "command.downgrade",
        "create_all",
        "ensure_sqlite_demo_columns",
        "SessionLocal",
        "app.main",
        "DATABASE_URL",
        "getenv",
        "environ",
        "psycopg",
    )
    assert not any(item in source for item in prohibited)
    assert "alembic_bootstrap" not in main_source
    assert 'config.attributes["connection"] = connection' in source
    assert 'command.upgrade(config, "head")' in source
