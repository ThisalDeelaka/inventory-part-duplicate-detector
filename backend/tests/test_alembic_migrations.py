from importlib.metadata import version
from pathlib import Path
from types import MappingProxyType

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)

from app.db import models as _models  # noqa: F401 - register metadata
from app.db.database import Base, NAMING_CONVENTION


BACKEND_ROOT = Path(__file__).resolve().parents[1]
INI_PATH = BACKEND_ROOT / "alembic.ini"
VERSIONS_PATH = BACKEND_ROOT / "migrations" / "versions"
APPLICATION_TABLES = {
    "duplicate_scan",
    "duplicate_candidate",
    "duplicate_feedback",
    "scan_warning",
    "rule_exclusion_audit",
}
EXPECTED_INDEXES = {
    "ix_duplicate_candidate_scan_id",
    "ix_duplicate_feedback_candidate_id",
    "ix_scan_warning_scan_id",
    "ix_rule_exclusion_audit_scan_id",
}
EXPECTED_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}
EXPECTED_FOREIGN_KEYS = {
    "fk_duplicate_candidate_scan_id_duplicate_scan",
    "fk_duplicate_feedback_candidate_id_duplicate_candidate",
    "fk_scan_warning_scan_id_duplicate_scan",
    "fk_rule_exclusion_audit_scan_id_duplicate_scan",
}


def _config(database_path: Path) -> Config:
    config = Config(str(INI_PATH))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    return config


def _fingerprint(engine):
    inspector = inspect(engine)
    result = {}
    for table in sorted(set(inspector.get_table_names()) - {"alembic_version"}):
        result[table] = {
            "columns": [
                (
                    column["name"], str(column["type"]), bool(column["nullable"]),
                    bool(column["primary_key"]), column["default"],
                )
                for column in inspector.get_columns(table)
            ],
            "pk": inspector.get_pk_constraint(table),
            "foreign_keys": inspector.get_foreign_keys(table),
            "indexes": inspector.get_indexes(table),
            "unique": inspector.get_unique_constraints(table),
            "checks": inspector.get_check_constraints(table),
        }
    return result


def _current_revision(engine):
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def test_dependency_configuration_and_revision_graph(tmp_path):
    assert version("alembic") == "1.18.5"
    config = _config(tmp_path / "explicit.sqlite")
    assert Path(config.get_main_option("script_location")).resolve() == (
        BACKEND_ROOT / "migrations"
    ).resolve()
    assert Config(str(INI_PATH)).get_main_option("sqlalchemy.url") == (
        "driver://user:pass@host/dbname"
    )
    assert sorted(path.name for path in VERSIONS_PATH.glob("*.py")) == [
        "0001_current_schema.py"
    ]
    script = ScriptDirectory.from_config(config)
    assert script.get_bases() == ["0001_current_schema"]
    assert script.get_heads() == ["0001_current_schema"]


def test_naming_convention_is_exact_immutable_and_applied():
    assert isinstance(NAMING_CONVENTION, MappingProxyType)
    assert dict(NAMING_CONVENTION) == EXPECTED_CONVENTION
    with pytest.raises(TypeError):
        NAMING_CONVENTION["pk"] = "changed"
    assert Base.metadata.naming_convention == EXPECTED_CONVENTION
    assert {index.name for table in Base.metadata.tables.values() for index in table.indexes} == (
        EXPECTED_INDEXES
    )
    assert {
        table.primary_key.name for table in Base.metadata.tables.values()
    } == {f"pk_{table}" for table in APPLICATION_TABLES}
    constraints = {
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
    }
    assert {
        constraint.name
        for constraint in constraints
        if isinstance(constraint, ForeignKeyConstraint)
    } == EXPECTED_FOREIGN_KEYS
    assert not any(isinstance(item, UniqueConstraint) for item in constraints)
    assert not any(isinstance(item, CheckConstraint) for item in constraints)


def test_empty_database_upgrade_matches_model_and_has_no_drift(tmp_path):
    migrated_path = tmp_path / "migrated.sqlite"
    model_path = tmp_path / "model.sqlite"
    config = _config(migrated_path)
    command.upgrade(config, "head")
    migrated = create_engine(f"sqlite:///{migrated_path.as_posix()}")
    model = create_engine(f"sqlite:///{model_path.as_posix()}")
    try:
        Base.metadata.create_all(model)
        assert set(inspect(migrated).get_table_names()) == APPLICATION_TABLES | {
            "alembic_version"
        }
        assert _current_revision(migrated) == "0001_current_schema"
        assert _fingerprint(migrated) == _fingerprint(model)
        assert {
            index["name"]
            for table in APPLICATION_TABLES
            for index in inspect(migrated).get_indexes(table)
        } == EXPECTED_INDEXES
        assert all(
            column["default"] is None
            for table in APPLICATION_TABLES
            for column in inspect(migrated).get_columns(table)
        )
        with migrated.connect() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 0
            context = MigrationContext.configure(
                connection,
                opts={
                    "compare_type": True,
                    "compare_server_default": True,
                    "target_metadata": Base.metadata,
                },
            )
            assert compare_metadata(context, Base.metadata) == []
    finally:
        migrated.dispose()
        model.dispose()


def test_downgrade_preserves_unknown_table(tmp_path):
    database = tmp_path / "downgrade.sqlite"
    config = _config(database)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unknown_extension (id INTEGER PRIMARY KEY)"))
    engine.dispose()
    command.downgrade(config, "base")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
        assert not tables.intersection(APPLICATION_TABLES)
        assert "unknown_extension" in tables
        assert _current_revision(engine) is None
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_is_repeatable(tmp_path):
    database = tmp_path / "repeat.sqlite"
    config = _config(database)
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    first = _fingerprint(engine)
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        assert _fingerprint(engine) == first
        assert _current_revision(engine) == "0001_current_schema"
    finally:
        engine.dispose()


def test_startup_and_alembic_paths_remain_separate():
    main_source = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    env_source = (BACKEND_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    revision_source = (
        VERSIONS_PATH / "0001_current_schema.py"
    ).read_text(encoding="utf-8")
    ini_source = INI_PATH.read_text(encoding="utf-8")
    requirements = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "Base.metadata.create_all(bind=engine)" in main_source
    assert "ensure_sqlite_demo_columns(engine)" in main_source
    assert "create_all" not in env_source
    assert "ensure_sqlite_demo_columns" not in env_source
    assert "DATABASE_URL" not in env_source
    assert "settings" not in env_source
    assert "stamp" not in env_source + revision_source
    assert "inventory_detector.db" not in env_source + ini_source
