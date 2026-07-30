"""Explicit, fail-closed Alembic bootstrap for pristine SQLite databases.

The service is sequentially repeatable but intentionally provides no
concurrency, locking, retry, repair, or startup-integration guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.db.schema_fingerprint import (
    SQLiteSchemaClassification,
    SQLiteSchemaClassificationResult,
    SQLiteSchemaProfileId,
    UnsupportedSchemaDialectError,
    classify_sqlite_schema,
)


_EXPECTED_REVISION = "0001_current_schema"


class SQLiteAlembicBootstrapOutcome(str, Enum):
    ALREADY_CURRENT = "ALREADY_CURRENT"
    BOOTSTRAPPED = "BOOTSTRAPPED"


@dataclass(frozen=True, slots=True)
class SQLiteAlembicBootstrapResult:
    outcome: SQLiteAlembicBootstrapOutcome
    pre_classification: SQLiteSchemaClassificationResult
    post_classification: SQLiteSchemaClassificationResult


class SQLiteAlembicBootstrapError(RuntimeError):
    pass


class SQLiteAlembicBootstrapRefusedError(SQLiteAlembicBootstrapError):
    reason: str
    classification_result: SQLiteSchemaClassificationResult
    user_schema_objects: tuple[str, ...]

    def __init__(
        self,
        reason: str,
        classification_result: SQLiteSchemaClassificationResult,
        user_schema_objects: tuple[str, ...] = (),
    ) -> None:
        super().__init__(f"SQLite Alembic bootstrap refused: {reason}")
        self.reason = reason
        self.classification_result = classification_result
        self.user_schema_objects = user_schema_objects


class SQLiteAlembicBootstrapConfigurationError(SQLiteAlembicBootstrapError):
    reason: str
    classification_result: SQLiteSchemaClassificationResult | None

    def __init__(
        self,
        reason: str,
        classification_result: SQLiteSchemaClassificationResult | None,
    ) -> None:
        super().__init__(f"SQLite Alembic bootstrap configuration error: {reason}")
        self.reason = reason
        self.classification_result = classification_result


class SQLiteAlembicBootstrapMigrationError(SQLiteAlembicBootstrapError):
    pre_classification: SQLiteSchemaClassificationResult
    post_failure_classification: SQLiteSchemaClassificationResult | None

    def __init__(
        self,
        pre_classification: SQLiteSchemaClassificationResult,
        post_failure_classification: SQLiteSchemaClassificationResult | None,
    ) -> None:
        super().__init__("SQLite Alembic bootstrap migration execution failed")
        self.pre_classification = pre_classification
        self.post_failure_classification = post_failure_classification


class SQLiteAlembicBootstrapPostconditionError(SQLiteAlembicBootstrapError):
    pre_classification: SQLiteSchemaClassificationResult
    post_classification: SQLiteSchemaClassificationResult

    def __init__(
        self,
        pre_classification: SQLiteSchemaClassificationResult,
        post_classification: SQLiteSchemaClassificationResult,
    ) -> None:
        super().__init__("SQLite Alembic bootstrap postcondition failed")
        self.pre_classification = pre_classification
        self.post_classification = post_classification


def _is_exact_current(result: SQLiteSchemaClassificationResult) -> bool:
    return (
        result.classification is SQLiteSchemaClassification.CURRENT_ALEMBIC
        and result.profile_id is SQLiteSchemaProfileId.CURRENT_ALEMBIC_0001
        and result.alembic_revision == _EXPECTED_REVISION
        and result.conflicts == ()
    )


def _is_exact_empty(result: SQLiteSchemaClassificationResult) -> bool:
    return (
        result.classification is SQLiteSchemaClassification.EMPTY
        and result.profile_id is None
        and result.alembic_revision is None
        and result.extra_tables == ()
        and result.conflicts == ()
    )


def _user_schema_objects(connection: Connection) -> tuple[str, ...]:
    rows = connection.execute(
        text(
            "SELECT type, name, tbl_name FROM sqlite_schema "
            "WHERE lower(substr(name, 1, 7)) <> 'sqlite_' "
            "ORDER BY type, name, tbl_name"
        )
    )
    return tuple(
        sorted(
            f"{object_type}:{name}:{table_name}"
            for object_type, name, table_name in rows
        )
    )


def _alembic_ini_path() -> Path:
    return Path(__file__).resolve().parents[2] / "alembic.ini"


def _verified_config(
    pre: SQLiteSchemaClassificationResult,
) -> Config:
    ini_path = _alembic_ini_path()
    if not ini_path.is_file():
        error = SQLiteAlembicBootstrapConfigurationError(
            "alembic_config_unavailable",
            pre,
        )
        raise error from FileNotFoundError("Alembic configuration is unavailable")

    try:
        config = Config(str(ini_path))
        script = ScriptDirectory.from_config(config)
        heads = tuple(script.get_heads())
    except Exception as original_error:
        raise SQLiteAlembicBootstrapConfigurationError(
            "alembic_configuration_invalid",
            pre,
        ) from original_error

    if len(heads) != 1:
        raise SQLiteAlembicBootstrapConfigurationError(
            "alembic_head_count_invalid",
            pre,
        )
    if heads[0] != _EXPECTED_REVISION:
        raise SQLiteAlembicBootstrapConfigurationError(
            "alembic_head_mismatch",
            pre,
        )
    return config


def _is_exact_postcondition(result: SQLiteSchemaClassificationResult) -> bool:
    return _is_exact_current(result) and result.extra_tables == ()


def bootstrap_pristine_sqlite(
    engine: Engine,
) -> SQLiteAlembicBootstrapResult:
    """Migrate an exact pristine SQLite database to the one committed head."""
    if not isinstance(engine, Engine):
        raise TypeError("engine must be a SQLAlchemy Engine")
    if engine.dialect.name != "sqlite":
        raise UnsupportedSchemaDialectError(
            f"unsupported schema dialect: {engine.dialect.name}"
        )

    with engine.connect() as connection:
        pre = classify_sqlite_schema(connection)

        if _is_exact_current(pre):
            return SQLiteAlembicBootstrapResult(
                SQLiteAlembicBootstrapOutcome.ALREADY_CURRENT,
                pre,
                pre,
            )

        if pre.classification is not SQLiteSchemaClassification.EMPTY:
            raise SQLiteAlembicBootstrapRefusedError(
                "schema_classification_not_bootstrap_eligible",
                pre,
            )

        user_schema_objects = _user_schema_objects(connection)
        if not _is_exact_empty(pre) or user_schema_objects:
            raise SQLiteAlembicBootstrapRefusedError(
                "database_not_pristine",
                pre,
                user_schema_objects,
            )

        config = _verified_config(pre)
        if connection.in_transaction():
            connection.commit()

        config.attributes["connection"] = connection
        try:
            command.upgrade(config, "head")
        except Exception as original_error:
            try:
                post_failure = classify_sqlite_schema(connection)
            except Exception:
                post_failure = None
            raise SQLiteAlembicBootstrapMigrationError(
                pre,
                post_failure,
            ) from original_error

        post = classify_sqlite_schema(connection)
        if not _is_exact_postcondition(post):
            raise SQLiteAlembicBootstrapPostconditionError(pre, post)

        return SQLiteAlembicBootstrapResult(
            SQLiteAlembicBootstrapOutcome.BOOTSTRAPPED,
            pre,
            post,
        )
