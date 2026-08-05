"""Live PostgreSQL proof for the committed initial Alembic revision.

The expected schema below is deliberately literal.  It is not imported from
ORM metadata, the revision module, SQLite characterization, or observed
PostgreSQL reflection.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from types import MappingProxyType

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine

from app.db.database import (
    DatabaseEngineConfigurationError,
    create_database_engine,
)


_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"
_BASE_DATABASE = "inventory_test"
_MIGRATION_DATABASE = "inventory_migration_test"
_RECOVERY_DATABASE = "inventory_migration_recovery_test"
_SYNTHETIC_PROBE_TABLE = "phase3d2b2_failure_probe"
_SYNTHETIC_FAILURE_MESSAGE = "phase3d2b2 synthetic migration failure"
_EXPECTED_USER = "inventory_test"
_EXPECTED_REVISION = "0001_current_schema"
_EXPECTED_SERVER_VERSION_NUM = "180004"
_APPLICATION_TABLES = (
    "duplicate_candidate",
    "duplicate_feedback",
    "duplicate_scan",
    "rule_exclusion_audit",
    "scan_warning",
)


def _column(
    name: str,
    type_name: str,
    nullable: bool,
    default: str | None = None,
) -> tuple[str, str, bool, str | None]:
    return name, type_name, nullable, default


_EXPECTED_COLUMNS = MappingProxyType({
    "duplicate_scan": (
        _column("id", "integer", False, "duplicate_scan_id_seq"),
        _column("scan_name", "character varying(200)", False),
        _column("source_type", "character varying(30)", False),
        _column("selected_fields", "text", False),
        _column("threshold", "double precision", False),
        _column("status", "character varying(30)", False),
        _column("total_records", "integer", True),
        _column("total_candidates", "integer", True),
        _column("warnings_count", "integer", True),
        _column("rejections_count", "integer", True),
        _column("scan_mode", "character varying(60)", False),
        _column("started_at", "timestamp with time zone", False),
        _column("completed_at", "timestamp with time zone", True),
        _column("model_version", "character varying(50)", False),
    ),
    "duplicate_candidate": (
        _column("id", "integer", False, "duplicate_candidate_id_seq"),
        _column("scan_id", "integer", False),
        _column("contract_a", "character varying(100)", True),
        _column("part_no_a", "character varying(200)", False),
        _column("description_a", "text", False),
        _column("contract_b", "character varying(100)", True),
        _column("part_no_b", "character varying(200)", False),
        _column("description_b", "text", False),
        _column("similarity_score", "double precision", False),
        _column("confidence_level", "character varying(20)", False),
        _column("description_similarity", "double precision", False),
        _column("tfidf_score", "double precision", False),
        _column("fuzzy_score", "double precision", False),
        _column("part_no_similarity", "double precision", False),
        _column("technical_token_score", "double precision", False),
        _column("matched_fields", "text", True),
        _column("mismatched_fields", "text", True),
        _column("explanation", "text", False),
        _column("recommended_action", "character varying(200)", False),
        _column("business_status", "character varying(80)", False),
        _column("rule_decision", "character varying(50)", False),
        _column("rejection_reason", "character varying(120)", True),
        _column("scan_mode", "character varying(60)", False),
        _column("critical_mismatches", "text", True),
        _column("variant_attributes_a", "text", True),
        _column("variant_attributes_b", "text", True),
        _column("generic_description_warning", "character varying(10)", True),
        _column("application_context_a", "text", True),
        _column("application_context_b", "text", True),
        _column("application_context_warning", "character varying(10)", True),
        _column("normalized_description_a", "text", True),
        _column("normalized_description_b", "text", True),
        _column("normalized_part_no_a", "text", True),
        _column("normalized_part_no_b", "text", True),
        _column("review_status", "character varying(30)", False),
        _column("reviewed_by", "character varying(100)", True),
        _column("reviewed_at", "timestamp with time zone", True),
    ),
    "duplicate_feedback": (
        _column("id", "integer", False, "duplicate_feedback_id_seq"),
        _column("candidate_id", "integer", False),
        _column("user_decision", "character varying(30)", False),
        _column("user_comment", "text", True),
        _column("created_by", "character varying(100)", False),
        _column("created_at", "timestamp with time zone", False),
    ),
    "scan_warning": (
        _column("id", "integer", False, "scan_warning_id_seq"),
        _column("scan_id", "integer", False),
        _column("warning_type", "character varying(80)", False),
        _column("message", "text", False),
        _column("record_reference", "character varying(200)", True),
        _column("created_at", "timestamp with time zone", False),
    ),
    "rule_exclusion_audit": (
        _column("id", "integer", False, "rule_exclusion_audit_id_seq"),
        _column("scan_id", "integer", False),
        _column("contract_a", "character varying(100)", True),
        _column("part_no_a", "character varying(200)", False),
        _column("description_a", "text", False),
        _column("contract_b", "character varying(100)", True),
        _column("part_no_b", "character varying(200)", False),
        _column("description_b", "text", False),
        _column("similarity_score", "double precision", False),
        _column("confidence_level", "character varying(20)", False),
        _column("business_status", "character varying(80)", False),
        _column("rule_decision", "character varying(50)", False),
        _column("rejection_reason", "character varying(120)", False),
        _column("critical_mismatches", "text", True),
        _column("explanation", "text", False),
        _column("created_at", "timestamp with time zone", False),
    ),
    "alembic_version": (
        _column("version_num", "character varying(32)", False),
    ),
})

_EXPECTED_PRIMARY_KEYS = (
    ("alembic_version_pkc", "alembic_version", ("version_num",)),
    ("pk_duplicate_candidate", "duplicate_candidate", ("id",)),
    ("pk_duplicate_feedback", "duplicate_feedback", ("id",)),
    ("pk_duplicate_scan", "duplicate_scan", ("id",)),
    ("pk_rule_exclusion_audit", "rule_exclusion_audit", ("id",)),
    ("pk_scan_warning", "scan_warning", ("id",)),
)
_EXPECTED_FOREIGN_KEYS = (
    (
        "fk_duplicate_candidate_scan_id_duplicate_scan",
        "duplicate_candidate", ("scan_id",), "duplicate_scan", ("id",),
        "NO ACTION", "NO ACTION", False, False,
    ),
    (
        "fk_duplicate_feedback_candidate_id_duplicate_candidate",
        "duplicate_feedback", ("candidate_id",), "duplicate_candidate", ("id",),
        "NO ACTION", "NO ACTION", False, False,
    ),
    (
        "fk_rule_exclusion_audit_scan_id_duplicate_scan",
        "rule_exclusion_audit", ("scan_id",), "duplicate_scan", ("id",),
        "NO ACTION", "NO ACTION", False, False,
    ),
    (
        "fk_scan_warning_scan_id_duplicate_scan",
        "scan_warning", ("scan_id",), "duplicate_scan", ("id",),
        "NO ACTION", "NO ACTION", False, False,
    ),
)
_EXPECTED_INDEXES = (
    ("alembic_version_pkc", "alembic_version", True, True, ("version_num",)),
    ("ix_duplicate_candidate_scan_id", "duplicate_candidate", False, False, ("scan_id",)),
    ("ix_duplicate_feedback_candidate_id", "duplicate_feedback", False, False, ("candidate_id",)),
    ("ix_rule_exclusion_audit_scan_id", "rule_exclusion_audit", False, False, ("scan_id",)),
    ("ix_scan_warning_scan_id", "scan_warning", False, False, ("scan_id",)),
    ("pk_duplicate_candidate", "duplicate_candidate", True, True, ("id",)),
    ("pk_duplicate_feedback", "duplicate_feedback", True, True, ("id",)),
    ("pk_duplicate_scan", "duplicate_scan", True, True, ("id",)),
    ("pk_rule_exclusion_audit", "rule_exclusion_audit", True, True, ("id",)),
    ("pk_scan_warning", "scan_warning", True, True, ("id",)),
)
_EXPECTED_SEQUENCES = (
    ("duplicate_candidate_id_seq", "duplicate_candidate", "id"),
    ("duplicate_feedback_id_seq", "duplicate_feedback", "id"),
    ("duplicate_scan_id_seq", "duplicate_scan", "id"),
    ("rule_exclusion_audit_id_seq", "rule_exclusion_audit", "id"),
    ("scan_warning_id_seq", "scan_warning", "id"),
)
_EXPECTED_RELATIONS = tuple(sorted(
    [(name, "table") for name in (*_APPLICATION_TABLES, "alembic_version")]
    + [(name, "sequence") for name, _table, _column in _EXPECTED_SEQUENCES]
))
_ACTION = MappingProxyType({"a": "NO ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET NULL", "d": "SET DEFAULT"})


def _safe_url(engine: Engine) -> str:
    return engine.url.set(query={}).render_as_string(hide_password=True)


def _configuration_failure(error: DatabaseEngineConfigurationError) -> AssertionError:
    details = [str(error), f"driver={error.drivername or 'unknown'}"]
    if error.safe_url is not None:
        details.append(f"url={error.safe_url}")
    return AssertionError("; ".join(details))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _require_equal(category: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{category} mismatch: expected={expected!r}; actual={actual!r}")


def _execute(connection: Connection, operation: str, statement: str):
    try:
        return connection.execute(text(statement))
    except Exception as error:
        raise AssertionError(
            f"{operation} failed ({type(error).__name__}); url={_safe_url(connection.engine)}"
        ) from None


def _non_system_relations(connection: Connection) -> tuple[tuple[str, str], ...]:
    rows = _execute(
        connection,
        "inspect base relations",
        "SELECT namespace.nspname, relation.relname "
        "FROM pg_catalog.pg_class AS relation "
        "JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
        "WHERE namespace.nspname NOT IN ('pg_catalog', 'information_schema') "
        "AND namespace.nspname NOT LIKE 'pg_toast%' "
        "AND namespace.nspname NOT LIKE 'pg_temp_%' "
        "AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f') "
        "ORDER BY namespace.nspname, relation.relname",
    ).all()
    return tuple((row[0], row[1]) for row in rows)


def _database_exists(connection: Connection, database_name: str) -> bool:
    try:
        return bool(connection.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = :name)"),
            {"name": database_name},
        ).scalar_one())
    except Exception as error:
        raise AssertionError(
            "inspect migration database ownership failed "
            f"({type(error).__name__}); url={_safe_url(connection.engine)}"
        ) from None


def _database_oid(connection: Connection, database_name: str) -> int:
    try:
        value = connection.execute(
            text("SELECT oid FROM pg_database WHERE datname = :name"),
            {"name": database_name},
        ).scalar_one()
        return int(value)
    except Exception as error:
        raise AssertionError(
            "inspect migration database identity failed "
            f"({type(error).__name__}); url={_safe_url(connection.engine)}"
        ) from None


def _relation_exists(connection: Connection, relation_name: str) -> bool:
    try:
        return bool(connection.execute(
            text("SELECT to_regclass('public.' || :name) IS NOT NULL"),
            {"name": relation_name},
        ).scalar_one())
    except Exception as error:
        raise AssertionError(
            "inspect migration relation failed "
            f"({type(error).__name__}); url={_safe_url(connection.engine)}"
        ) from None


def _database_ddl(action: str, database_name: str) -> str:
    _require(action in {"CREATE", "DROP"}, "unsupported database DDL action")
    _require(
        database_name in {_MIGRATION_DATABASE, _RECOVERY_DATABASE},
        "unsupported test-owned database name",
    )
    return f'{action} DATABASE "{database_name}"'


def _validate_base(connection: Connection, engine: Engine) -> None:
    _require(engine.url.drivername == "postgresql+psycopg", "unsupported PostgreSQL test driver")
    _require(engine.dialect.name == "postgresql", "PostgreSQL dialect required")
    _require(engine.dialect.driver == "psycopg", "Psycopg driver required")
    _require(engine.url.username == _EXPECTED_USER, "wrong PostgreSQL test URL user")
    _require(engine.url.database == _BASE_DATABASE, "wrong PostgreSQL base database")
    _require_equal("SELECT 1", _execute(connection, "base connectivity", "SELECT 1").scalar_one(), 1)
    _require_equal("current database", _execute(connection, "validate base database", "SELECT current_database()").scalar_one(), _BASE_DATABASE)
    _require_equal("current user", _execute(connection, "validate base user", "SELECT current_user").scalar_one(), _EXPECTED_USER)
    _require_equal("server version number", _execute(connection, "validate server version", "SELECT current_setting('server_version_num')").scalar_one(), _EXPECTED_SERVER_VERSION_NUM)
    version = _execute(connection, "validate server version", "SELECT current_setting('server_version')").scalar_one()
    _require(version.startswith("18.4"), "PostgreSQL server version must be 18.4")
    _require_equal("base database relations", _non_system_relations(connection), ())


def _validate_target_identity(
    connection: Connection,
    database_name: str,
    database_oid: int,
) -> int:
    _require_equal(
        "current database",
        _execute(connection, "validate target database", "SELECT current_database()").scalar_one(),
        database_name,
    )
    _require_equal(
        "current user",
        _execute(connection, "validate target user", "SELECT current_user").scalar_one(),
        _EXPECTED_USER,
    )
    _require_equal(
        "server version number",
        _execute(
            connection,
            "validate target server version",
            "SELECT current_setting('server_version_num')",
        ).scalar_one(),
        _EXPECTED_SERVER_VERSION_NUM,
    )
    version = _execute(
        connection,
        "validate target server version",
        "SELECT current_setting('server_version')",
    ).scalar_one()
    _require(version.startswith("18.4"), "PostgreSQL server version must be 18.4")
    current_oid = _execute(
        connection,
        "validate target database identity",
        "SELECT oid FROM pg_database WHERE datname = current_database()",
    ).scalar_one()
    _require_equal("target database identity", int(current_oid), database_oid)
    return int(current_oid)


def _alembic_config() -> Config:
    config = Config(str(_ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)
    _require_equal("Alembic bases", tuple(script.get_bases()), (_EXPECTED_REVISION,))
    _require_equal("Alembic heads", tuple(script.get_heads()), (_EXPECTED_REVISION,))
    return config


def _run_upgrade(config: Config, connection: Connection) -> None:
    config.attributes["connection"] = connection
    try:
        command.upgrade(config, "head")
    except Exception as error:
        raise AssertionError(
            f"Alembic upgrade failed ({type(error).__name__}); url={_safe_url(connection.engine)}"
        ) from None


def _revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _normalize_default(value: str | None) -> str | None:
    if value is None:
        return None
    compact = re.sub(r"\s+", " ", value.strip())
    identifier = r'(?:"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_$]*)'
    nextval = re.fullmatch(
        rf"nextval\s*\(\s*'(?P<identity>{identifier}(?:\s*\.\s*{identifier})?)'"
        rf"\s*::\s*regclass\s*\)",
        compact,
    )
    if nextval is not None:
        identity = re.fullmatch(
            rf"(?:(?P<schema>{identifier})\s*\.\s*)?(?P<sequence>{identifier})",
            nextval.group("identity"),
        )
        if identity is not None:
            def unquote(part: str) -> str:
                if part.startswith('"'):
                    return part[1:-1].replace('""', '"')
                return part.lower()

            schema = identity.group("schema")
            sequence = unquote(identity.group("sequence"))
            expected = {name for name, _table, _column in _EXPECTED_SEQUENCES}
            if (schema is None or unquote(schema) == "public") and sequence in expected:
                return sequence
    return compact


def _columns(connection: Connection) -> tuple[tuple[str, tuple[tuple[str, str, bool, str | None], ...]], ...]:
    rows = _execute(
        connection,
        "inspect columns",
        "SELECT cls.relname, att.attnum, att.attname, "
        "pg_catalog.format_type(att.atttypid, att.atttypmod), "
        "NOT att.attnotnull AS nullable, pg_get_expr(def.adbin, def.adrelid) "
        "FROM pg_catalog.pg_attribute AS att "
        "JOIN pg_catalog.pg_class AS cls ON cls.oid = att.attrelid "
        "JOIN pg_catalog.pg_namespace AS ns ON ns.oid = cls.relnamespace "
        "LEFT JOIN pg_catalog.pg_attrdef AS def ON def.adrelid = att.attrelid AND def.adnum = att.attnum "
        "WHERE ns.nspname = 'public' AND cls.relkind IN ('r', 'p') "
        "AND att.attnum > 0 AND NOT att.attisdropped "
        "ORDER BY cls.relname, att.attnum",
    ).all()
    grouped: dict[str, list[tuple[str, str, bool, str | None]]] = {}
    for table, _ordinal, name, type_name, nullable, default in rows:
        grouped.setdefault(table, []).append((name, type_name, nullable, _normalize_default(default)))
    return tuple((table, tuple(values)) for table, values in sorted(grouped.items()))


def _constraints(connection: Connection):
    rows = _execute(
        connection,
        "inspect constraints",
        "SELECT con.conname, con.contype, src.relname, "
        "ARRAY(SELECT att.attname FROM unnest(con.conkey) WITH ORDINALITY AS key(attnum, ord) "
        "JOIN pg_attribute AS att ON att.attrelid = con.conrelid AND att.attnum = key.attnum ORDER BY key.ord), "
        "target.relname, "
        "ARRAY(SELECT att.attname FROM unnest(con.confkey) WITH ORDINALITY AS key(attnum, ord) "
        "JOIN pg_attribute AS att ON att.attrelid = con.confrelid AND att.attnum = key.attnum ORDER BY key.ord), "
        "con.confupdtype, con.confdeltype, con.condeferrable, con.condeferred "
        "FROM pg_constraint AS con "
        "JOIN pg_class AS src ON src.oid = con.conrelid "
        "JOIN pg_namespace AS ns ON ns.oid = src.relnamespace "
        "LEFT JOIN pg_class AS target ON target.oid = con.confrelid "
        "WHERE ns.nspname = 'public' AND con.contype IN ('p','f','u','c','x') "
        "ORDER BY con.conname",
    ).all()
    pks = []
    fks = []
    unsupported = []
    for name, kind, table, columns, target, target_columns, update, delete, deferrable, deferred in rows:
        if kind == "p":
            pks.append((name, table, tuple(columns)))
        elif kind == "f":
            fks.append((name, table, tuple(columns), target, tuple(target_columns), _ACTION[update], _ACTION[delete], deferrable, deferred))
        else:
            unsupported.append((name, kind, table))
    return tuple(pks), tuple(fks), tuple(unsupported)


def _indexes(connection: Connection):
    rows = _execute(
        connection,
        "inspect indexes",
        "SELECT idx.relname, tbl.relname, ind.indisunique, ind.indisprimary, "
        "ARRAY(SELECT pg_get_indexdef(ind.indexrelid, key, true) FROM generate_series(1, ind.indnkeyatts) AS key ORDER BY key), "
        "ARRAY(SELECT pg_get_indexdef(ind.indexrelid, key, true) FROM generate_series(ind.indnkeyatts + 1, ind.indnatts) AS key ORDER BY key), "
        "pg_get_expr(ind.indexprs, ind.indrelid), pg_get_expr(ind.indpred, ind.indrelid) "
        "FROM pg_index AS ind JOIN pg_class AS idx ON idx.oid = ind.indexrelid "
        "JOIN pg_class AS tbl ON tbl.oid = ind.indrelid "
        "JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace "
        "WHERE ns.nspname = 'public' ORDER BY idx.relname",
    ).all()
    result = []
    for name, table, unique, primary, keys, included, expressions, predicate in rows:
        _require_equal(f"index {name} included columns", tuple(included or ()), ())
        _require_equal(f"index {name} expressions", expressions, None)
        _require_equal(f"index {name} predicate", predicate, None)
        result.append((name, table, unique, primary, tuple(keys)))
    return tuple(result)


def _sequences(connection: Connection):
    rows = _execute(
        connection,
        "inspect sequences",
        "SELECT seq.relname, tbl.relname, att.attname "
        "FROM pg_class AS seq JOIN pg_namespace AS ns ON ns.oid = seq.relnamespace "
        "LEFT JOIN pg_depend AS dep ON dep.classid = 'pg_class'::regclass "
        "AND dep.objid = seq.oid AND dep.deptype = 'a' "
        "LEFT JOIN pg_class AS tbl ON tbl.oid = dep.refobjid "
        "LEFT JOIN pg_attribute AS att ON att.attrelid = dep.refobjid AND att.attnum = dep.refobjsubid "
        "WHERE ns.nspname = 'public' AND seq.relkind = 'S' ORDER BY seq.relname",
    ).all()
    return tuple((row[0], row[1], row[2]) for row in rows)


def _relations(connection: Connection):
    kinds = {"r": "table", "p": "partitioned table", "v": "view", "m": "materialized view", "f": "foreign table", "S": "sequence"}
    rows = _execute(
        connection,
        "inspect relations",
        "SELECT cls.relname, cls.relkind FROM pg_class AS cls "
        "JOIN pg_namespace AS ns ON ns.oid = cls.relnamespace "
        "WHERE ns.nspname = 'public' AND cls.relkind IN ('r','p','v','m','f','S') "
        "ORDER BY cls.relname",
    ).all()
    return tuple((name, kinds[kind]) for name, kind in rows)


def _schemas(connection: Connection):
    rows = _execute(connection, "inspect schemas", "SELECT nspname FROM pg_namespace WHERE nspname <> 'information_schema' AND nspname NOT LIKE 'pg_%' ORDER BY nspname").scalars()
    return tuple(rows)


def _triggers(connection: Connection):
    rows = _execute(
        connection,
        "inspect triggers",
        "SELECT trg.tgname, cls.relname FROM pg_trigger AS trg "
        "JOIN pg_class AS cls ON cls.oid = trg.tgrelid "
        "JOIN pg_namespace AS ns ON ns.oid = cls.relnamespace "
        "WHERE ns.nspname = 'public' AND NOT trg.tgisinternal ORDER BY trg.tgname",
    ).all()
    return tuple((row[0], row[1]) for row in rows)


def _custom_types(connection: Connection):
    rows = _execute(
        connection,
        "inspect custom types",
        "SELECT typ.typname, typ.typtype FROM pg_type AS typ "
        "JOIN pg_namespace AS ns ON ns.oid = typ.typnamespace "
        "LEFT JOIN pg_class AS cls ON cls.oid = typ.typrelid "
        "WHERE ns.nspname = 'public' AND (typ.typtype IN ('e','d','r','m') "
        "OR (typ.typtype = 'c' AND cls.relkind = 'c')) ORDER BY typ.typname",
    ).all()
    return tuple((row[0], row[1]) for row in rows)


def _row_counts(connection: Connection):
    return tuple((table, _execute(connection, f"count rows in {table}", f'SELECT COUNT(*) FROM "{table}"').scalar_one()) for table in _APPLICATION_TABLES)


def _fingerprint(connection: Connection):
    revision = _revision(connection)
    version_rows = tuple(_execute(connection, "inspect Alembic revision", "SELECT version_num FROM alembic_version ORDER BY version_num").scalars())
    pks, fks, unsupported = _constraints(connection)
    fingerprint = (
        ("schemas", _schemas(connection)),
        ("relations", _relations(connection)),
        ("columns", _columns(connection)),
        ("primary_keys", pks),
        ("foreign_keys", fks),
        ("unsupported_constraints", unsupported),
        ("indexes", _indexes(connection)),
        ("sequences", _sequences(connection)),
        ("triggers", _triggers(connection)),
        ("custom_types", _custom_types(connection)),
        ("row_counts", _row_counts(connection)),
        ("revision", revision),
        ("version_rows", version_rows),
    )
    expected = (
        ("schemas", ("public",)),
        ("relations", _EXPECTED_RELATIONS),
        ("columns", tuple((table, columns) for table, columns in sorted(_EXPECTED_COLUMNS.items()))),
        ("primary_keys", _EXPECTED_PRIMARY_KEYS),
        ("foreign_keys", _EXPECTED_FOREIGN_KEYS),
        ("unsupported_constraints", ()),
        ("indexes", _EXPECTED_INDEXES),
        ("sequences", _EXPECTED_SEQUENCES),
        ("triggers", ()),
        ("custom_types", ()),
        ("row_counts", tuple((table, 0) for table in _APPLICATION_TABLES)),
        ("revision", _EXPECTED_REVISION),
        ("version_rows", (_EXPECTED_REVISION,)),
    )
    _require_equal("PostgreSQL schema contract", fingerprint, expected)
    return fingerprint


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


def _create_target_engine(base_engine: Engine, database_name: str) -> Engine:
    target_url = base_engine.url.set(database=database_name)
    raw_url = target_url.render_as_string(hide_password=False)
    try:
        return create_database_engine(raw_url)
    except DatabaseEngineConfigurationError as error:
        raise _configuration_failure(error) from None
    finally:
        del raw_url


def _synthetic_alembic_config(tmp_path: Path) -> Config:
    script_location = tmp_path / "phase3d2b2_alembic"
    versions = script_location / "versions"
    versions.mkdir(parents=True)
    committed_env = _BACKEND_ROOT / "migrations" / "env.py"
    temporary_env = script_location / "env.py"
    shutil.copyfile(committed_env, temporary_env)
    _require_equal(
        "synthetic Alembic environment copy",
        temporary_env.read_bytes(),
        committed_env.read_bytes(),
    )
    revision_source = f'''from alembic import op
import sqlalchemy as sa

revision = {_EXPECTED_REVISION!r}
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        {_SYNTHETIC_PROBE_TABLE!r},
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    raise RuntimeError({_SYNTHETIC_FAILURE_MESSAGE!r})


def downgrade() -> None:
    raise NotImplementedError
'''
    (versions / "0001_synthetic_failure.py").write_text(
        revision_source,
        encoding="utf-8",
        newline="\n",
    )
    _require_equal(
        "synthetic Alembic tree entries",
        tuple(sorted(path.name for path in script_location.iterdir())),
        ("env.py", "versions"),
    )

    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(script_location))
    script = ScriptDirectory.from_config(config)
    _require_equal("synthetic Alembic bases", tuple(script.get_bases()), (_EXPECTED_REVISION,))
    _require_equal("synthetic Alembic heads", tuple(script.get_heads()), (_EXPECTED_REVISION,))
    revision_files = tuple(path.name for path in versions.iterdir() if path.is_file())
    _require_equal("synthetic Alembic revision files", revision_files, ("0001_synthetic_failure.py",))
    return config


def _is_probe_create_table(statement: str) -> bool:
    value = statement
    while True:
        value = value.lstrip()
        if value.startswith("/*"):
            end = value.find("*/", 2)
            if end < 0:
                return False
            value = value[end + 2:]
            continue
        if value.startswith("--"):
            end = re.search(r"\r?\n", value)
            if end is None:
                return False
            value = value[end.end():]
            continue
        break
    identifier = re.escape(_SYNTHETIC_PROBE_TABLE)
    pattern = (
        rf'CREATE\s+TABLE\s+(?:(?:"public"|public)\s*\.\s*)?'
        rf'(?:"{identifier}"|{identifier})\s*\(.+\)\s*;?'
    )
    return re.fullmatch(pattern, value, flags=re.IGNORECASE | re.DOTALL) is not None


def _require_synthetic_failure(error: BaseException) -> None:
    _require_equal("synthetic failure type", type(error), RuntimeError)
    _require_equal("synthetic failure message", str(error), _SYNTHETIC_FAILURE_MESSAGE)


def _require_pristine_recovery_database(
    connection: Connection,
    database_oid: int,
) -> tuple[object, ...]:
    _validate_target_identity(connection, _RECOVERY_DATABASE, database_oid)
    relations = _non_system_relations(connection)
    revision = _revision(connection)
    schemas = _schemas(connection)
    triggers = _triggers(connection)
    custom_types = _custom_types(connection)
    _require_equal("post-failure relations", relations, ())
    _require_equal("post-failure Alembic revision", revision, None)
    _require_equal("post-failure schemas", schemas, ("public",))
    _require_equal("post-failure triggers", triggers, ())
    _require_equal("post-failure custom types", custom_types, ())
    absent_names = (*_APPLICATION_TABLES, "alembic_version", _SYNTHETIC_PROBE_TABLE)
    for name in absent_names:
        _require(
            not _relation_exists(connection, name),
            f"post-failure relation unexpectedly exists: {name}",
        )
    return relations, revision, schemas, triggers, custom_types


@pytest.mark.postgres_integration
def test_empty_postgresql_alembic_upgrade_matches_independent_schema_contract() -> None:
    configured_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if configured_url is None:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not set; opt-in PostgreSQL migration test skipped")

    base_engine: Engine | None = None
    migration_engine: Engine | None = None
    created = False
    try:
        try:
            base_engine = create_database_engine(configured_url)
        except DatabaseEngineConfigurationError as error:
            raise _configuration_failure(error) from None

        try:
            with base_engine.connect() as base_connection:
                _validate_base(base_connection, base_engine)
                _require(
                    not _database_exists(base_connection, _MIGRATION_DATABASE),
                    "inventory_migration_test already exists; refusing ownership",
                )

            with base_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
                _execute(admin, "create migration database", 'CREATE DATABASE "inventory_migration_test"')
                created = True
                _require(
                    _database_exists(admin, _MIGRATION_DATABASE),
                    "created migration database was not found",
                )

            migration_engine = _create_target_engine(base_engine, _MIGRATION_DATABASE)
            config = _alembic_config()
            with migration_engine.connect() as migration_connection:
                _run_upgrade(config, migration_connection)
                _require_equal("migrated revision", _revision(migration_connection), _EXPECTED_REVISION)
                first = _fingerprint(migration_connection)

            statements: list[str] = []
            def capture(_conn, _cursor, statement, _parameters, _context, _many):
                statements.append(statement)

            with migration_engine.connect() as second_connection:
                event.listen(second_connection, "before_cursor_execute", capture)
                try:
                    _run_upgrade(config, second_connection)
                finally:
                    event.remove(second_connection, "before_cursor_execute", capture)

                observable = tuple(item for item in statements if item.strip())
                _require(bool(observable), "second upgrade emitted no observable SQL statements")
                keywords = tuple(_statement_keyword(item) for item in observable)
                unclassified = tuple(index for index, keyword in enumerate(keywords) if not keyword)
                _require_equal("second-upgrade unclassified SQL statements", unclassified, ())
                unexpected = tuple(keyword for keyword in keywords if keyword != "SELECT")
                _require_equal("second-upgrade non-SELECT SQL statements", unexpected, ())

                _require_equal("second-upgrade revision", _revision(second_connection), _EXPECTED_REVISION)
                second = _fingerprint(second_connection)

            _require_equal("second-upgrade schema fingerprint", second, first)
        except AssertionError:
            raise
        except Exception as error:
            raise AssertionError(
                f"PostgreSQL migration verification failed ({type(error).__name__}); url={_safe_url(base_engine)}"
            ) from None
    finally:
        cleanup_error: BaseException | None = None
        if migration_engine is not None:
            try:
                migration_engine.dispose()
            except BaseException as error:
                cleanup_error = AssertionError(
                    f"dispose migration engine failed ({type(error).__name__})"
                )
        if base_engine is not None:
            if created:
                try:
                    checked_out = getattr(base_engine.pool, "checkedout", lambda: 0)()
                    _require_equal("base checked-out connections before cleanup", checked_out, 0)
                    with base_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
                        _execute(admin, "drop migration database", 'DROP DATABASE "inventory_migration_test"')
                        _require(
                            not _database_exists(admin, _MIGRATION_DATABASE),
                            "migration database still exists after cleanup",
                        )
                        _require_equal("base relations after cleanup", _non_system_relations(admin), ())
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
        if cleanup_error is not None:
            raise cleanup_error


@pytest.mark.postgres_integration
def test_failed_initial_postgresql_migration_rolls_back_and_recovers_on_same_database(
    tmp_path: Path,
) -> None:
    configured_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if configured_url is None:
        pytest.skip(
            "POSTGRES_TEST_DATABASE_URL is not set; "
            "opt-in PostgreSQL failure/recovery test skipped"
        )

    base_engine: Engine | None = None
    recovery_engine: Engine | None = None
    created = False
    database_oid: int | None = None
    primary_error: BaseException | None = None
    try:
        try:
            base_engine = create_database_engine(configured_url)
        except DatabaseEngineConfigurationError as error:
            raise _configuration_failure(error) from None

        with base_engine.connect() as base_connection:
            _validate_base(base_connection, base_engine)
            _require(
                not _database_exists(base_connection, _MIGRATION_DATABASE),
                "parity migration database already exists; refusing recovery test",
            )
            _require(
                not _database_exists(base_connection, _RECOVERY_DATABASE),
                "recovery migration database already exists; refusing ownership",
            )

        with base_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
            _execute(
                admin,
                "create recovery migration database",
                _database_ddl("CREATE", _RECOVERY_DATABASE),
            )
            created = True
            _require(
                _database_exists(admin, _RECOVERY_DATABASE),
                "created recovery migration database was not found",
            )
            database_oid = _database_oid(admin, _RECOVERY_DATABASE)

        recovery_engine = _create_target_engine(base_engine, _RECOVERY_DATABASE)
        synthetic_config = _synthetic_alembic_config(tmp_path)
        statements: list[str] = []

        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        with recovery_engine.connect() as failed_connection:
            before_failure_oid = _validate_target_identity(
                failed_connection,
                _RECOVERY_DATABASE,
                database_oid,
            )
            synthetic_config.attributes["connection"] = failed_connection
            event.listen(failed_connection, "before_cursor_execute", capture)
            try:
                try:
                    command.upgrade(synthetic_config, "head")
                except BaseException as error:
                    _require_synthetic_failure(error)
                else:
                    raise AssertionError("synthetic migration unexpectedly completed")
            finally:
                event.remove(failed_connection, "before_cursor_execute", capture)

        observable = tuple(statement for statement in statements if statement.strip())
        _require(bool(observable), "synthetic upgrade emitted no observable SQL statements")
        keywords = tuple(_statement_keyword(statement) for statement in observable)
        unclassified = tuple(index for index, keyword in enumerate(keywords) if not keyword)
        _require_equal("synthetic-upgrade unclassified SQL statements", unclassified, ())
        probe_creates = tuple(
            statement for statement in observable if _is_probe_create_table(statement)
        )
        _require_equal("synthetic probe CREATE TABLE statements", len(probe_creates), 1)

        with recovery_engine.connect() as post_failure_connection:
            pristine = _require_pristine_recovery_database(
                post_failure_connection,
                database_oid,
            )
            post_failure_oid = _database_oid(
                post_failure_connection,
                _RECOVERY_DATABASE,
            )
            _require_equal("post-failure database identity", post_failure_oid, database_oid)

        real_config = _alembic_config()
        with recovery_engine.connect() as recovery_connection:
            _validate_target_identity(recovery_connection, _RECOVERY_DATABASE, database_oid)
            _run_upgrade(real_config, recovery_connection)
            _require_equal(
                "recovered revision",
                _revision(recovery_connection),
                _EXPECTED_REVISION,
            )
            final_fingerprint = _fingerprint(recovery_connection)
            _require(
                not _relation_exists(recovery_connection, _SYNTHETIC_PROBE_TABLE),
                "synthetic probe remained after real forward recovery",
            )
            after_recovery_oid = _validate_target_identity(
                recovery_connection,
                _RECOVERY_DATABASE,
                database_oid,
            )

        print(
            "phase3d2b2 evidence: "
            f"exception=RuntimeError message={_SYNTHETIC_FAILURE_MESSAGE!r} "
            f"captured_statements={len(observable)} probe_creates={len(probe_creates)} "
            f"post_failure_revision={pristine[1]!r} "
            f"post_failure_relations={len(pristine[0])} "
            f"post_failure_triggers={len(pristine[3])} "
            f"post_failure_custom_types={len(pristine[4])} "
            f"oid_before_failure={before_failure_oid} "
            f"oid_after_failure={post_failure_oid} "
            f"oid_after_recovery={after_recovery_oid} "
            f"recovered_revision={_EXPECTED_REVISION} "
            f"fingerprint_categories={len(final_fingerprint)}"
        )
    except AssertionError as error:
        primary_error = error
        raise
    except BaseException as error:
        safe_url = _safe_url(base_engine) if base_engine is not None else "unavailable"
        primary_error = AssertionError(
            "PostgreSQL failure/recovery verification failed "
            f"({type(error).__name__}); url={safe_url}"
        )
        raise primary_error from None
    finally:
        cleanup_error: BaseException | None = None
        if recovery_engine is not None:
            try:
                recovery_engine.dispose()
            except BaseException as error:
                cleanup_error = AssertionError(
                    f"dispose recovery engine failed ({type(error).__name__})"
                )
        if base_engine is not None:
            if created:
                try:
                    checked_out = getattr(base_engine.pool, "checkedout", lambda: 0)()
                    _require_equal(
                        "base checked-out connections before recovery cleanup",
                        checked_out,
                        0,
                    )
                    with base_engine.connect().execution_options(
                        isolation_level="AUTOCOMMIT"
                    ) as admin:
                        _execute(
                            admin,
                            "drop recovery migration database",
                            _database_ddl("DROP", _RECOVERY_DATABASE),
                        )
                        _require(
                            not _database_exists(admin, _RECOVERY_DATABASE),
                            "recovery migration database still exists after cleanup",
                        )
                        _require(
                            not _database_exists(admin, _MIGRATION_DATABASE),
                            "parity migration database exists after recovery cleanup",
                        )
                        _require_equal(
                            "base relations after recovery cleanup",
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
        if cleanup_error is not None:
            if primary_error is None:
                raise cleanup_error
            primary_error.add_note(
                "Recovery cleanup also failed: "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
