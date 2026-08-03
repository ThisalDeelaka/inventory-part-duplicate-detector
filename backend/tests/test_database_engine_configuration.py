import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import psycopg
from psycopg import pq
import sqlalchemy
from sqlalchemy import event, text
from sqlalchemy.engine import Engine, URL

from app.db import database


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = BACKEND_ROOT / "requirements.txt"


def _assert_secret_absent(secret: str, *values: object) -> None:
    for value in values:
        if secret in repr(value) or secret in str(value):
            pytest.fail("database credential leaked through diagnostics")


def test_dependency_versions_and_binary_runtime_are_exact():
    assert psycopg.__version__ == "3.3.4"
    assert version("psycopg-binary") == "3.3.4"
    assert pq.__impl__ == "binary"
    assert sqlalchemy.__version__ == "2.0.41"
    assert version("alembic") == "1.18.5"


def test_requirements_have_only_the_approved_postgresql_driver():
    dependency_lines = [
        line.strip().lower()
        for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert dependency_lines.count("psycopg[binary]==3.3.4") == 1
    assert dependency_lines.count("sqlalchemy==2.0.41") == 1
    assert dependency_lines.count("alembic==1.18.5") == 1
    forbidden = {
        "psycopg2",
        "psycopg2-binary",
        "asyncpg",
        "psycopg-c",
        "psycopg-pool",
    }
    assert not {
        line.partition("==")[0].partition("[")[0]
        for line in dependency_lines
    }.intersection(forbidden)


def test_public_engine_configuration_contract_exists():
    assert callable(database.create_database_engine)
    assert issubclass(database.DatabaseEngineConfigurationError, ValueError)


@pytest.mark.parametrize("value", [None, 1, object()])
def test_non_string_database_url_is_rejected(value):
    with pytest.raises(TypeError, match="must be a string"):
        database.create_database_engine(value)


@pytest.mark.parametrize("value", ["", " ", "\t\r\n"])
def test_empty_database_url_is_rejected_without_engine_construction(monkeypatch, value):
    monkeypatch.setattr(
        database,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("create_engine was called"),
    )
    with pytest.raises(database.DatabaseEngineConfigurationError) as raised:
        database.create_database_engine(value)
    assert raised.value.drivername is None
    assert raised.value.safe_url is None


def test_malformed_url_is_wrapped_without_leaking_input():
    sentinel = "SENTINEL_MALFORMED_PASSWORD"
    malformed_url = f"://{sentinel}"
    with pytest.raises(database.DatabaseEngineConfigurationError) as raised:
        database.create_database_engine(malformed_url)
    error = raised.value
    assert error.__cause__ is not None
    _assert_secret_absent(
        sentinel,
        str(error),
        repr(error),
        error.args,
        vars(error),
        str(error.__cause__),
    )


@pytest.mark.parametrize("drivername", ["sqlite", "sqlite+pysqlite"])
def test_sqlite_engine_options_are_exact(monkeypatch, drivername):
    captured = {}
    sentinel_engine = object()

    def capture(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return sentinel_engine

    monkeypatch.setattr(database, "create_engine", capture)
    result = database.create_database_engine(f"{drivername}:///:memory:")

    assert result is sentinel_engine
    assert isinstance(captured["url"], URL)
    assert captured["url"].drivername == drivername
    assert captured["kwargs"] == {
        "connect_args": {"check_same_thread": False},
        "pool_pre_ping": True,
    }


def test_real_sqlite_engine_is_lazy_synchronous_and_usable():
    engine = database.create_database_engine("sqlite:///:memory:")
    connect_events = []
    event.listen(engine, "connect", lambda *_args: connect_events.append(True))
    try:
        assert isinstance(engine, Engine)
        assert engine.dialect.name == "sqlite"
        assert engine.dialect.driver == "pysqlite"
        assert engine.pool._pre_ping is True
        assert connect_events == []
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
        assert connect_events == [True]
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "input_driver",
    ["postgresql", "postgresql+psycopg", "postgres"],
)
def test_postgresql_inputs_construct_canonical_lazy_engines(monkeypatch, input_driver):
    connection_attempts = []
    monkeypatch.setattr(
        psycopg,
        "connect",
        lambda *_args, **_kwargs: connection_attempts.append(True),
    )
    engine = database.create_database_engine(
        f"{input_driver}://user:password@db.example:5544/inventory"
    )
    try:
        assert isinstance(engine, Engine)
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
        assert engine.pool._pre_ping is True
        assert connection_attempts == []
    finally:
        engine.dispose()
    assert connection_attempts == []


def test_postgresql_canonicalization_preserves_url_semantics():
    engine = database.create_database_engine(
        "postgres://user%2Bname:p%40ss%3Aword@db.example:5544/"
        "inventory%2Fparts?application_name=detector&sslmode=prefer"
    )
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.username == "user+name"
        assert hashlib.sha256(engine.url.password.encode()).digest() == hashlib.sha256(
            b"p@ss:word"
        ).digest()
        assert engine.url.host == "db.example"
        assert engine.url.port == 5544
        assert engine.url.database == "inventory%2Fparts"
        assert dict(engine.url.query) == {
            "application_name": "detector",
            "sslmode": "prefer",
        }
    finally:
        engine.dispose()


def test_postgresql_engine_options_exclude_sqlite_arguments(monkeypatch):
    captured = {}
    sentinel_engine = object()

    def capture(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return sentinel_engine

    monkeypatch.setattr(database, "create_engine", capture)
    result = database.create_database_engine(
        "postgresql://user:password@db.example/inventory"
    )

    assert result is sentinel_engine
    assert isinstance(captured["url"], URL)
    assert captured["url"].drivername == "postgresql+psycopg"
    assert captured["kwargs"] == {"pool_pre_ping": True}
    assert "connect_args" not in captured["kwargs"]


@pytest.mark.parametrize(
    "url,expected_driver",
    [
        ("postgresql+psycopg2://user:password@host/db", "postgresql+psycopg2"),
        ("postgresql+psycopg_async://user:password@host/db", "postgresql+psycopg_async"),
        ("postgresql+asyncpg://user:password@host/db", "postgresql+asyncpg"),
        ("postgresql+pg8000://user:password@host/db", "postgresql+pg8000"),
        ("postgres+psycopg://user:password@host/db", "postgres+psycopg"),
        ("sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite"),
        ("mysql+pymysql://user:password@host/db", "mysql+pymysql"),
        ("oracle+oracledb://user:password@host/db", "oracle+oracledb"),
    ],
)
def test_unsupported_driver_is_rejected_before_engine_construction(
    monkeypatch,
    url,
    expected_driver,
):
    monkeypatch.setattr(
        database,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("create_engine was called"),
    )
    with pytest.raises(database.DatabaseEngineConfigurationError) as raised:
        database.create_database_engine(url)
    assert raised.value.drivername == expected_driver
    assert raised.value.safe_url is not None
    assert "password" not in raised.value.safe_url
    if "@host" in url:
        assert "***" in raised.value.safe_url


def test_unsupported_driver_diagnostics_redact_credentials():
    sentinel = "SENTINEL_UNSUPPORTED_PASSWORD"
    query_sentinel = "SENTINEL_UNSUPPORTED_QUERY_TOKEN"
    url = (
        f"postgresql+psycopg2://user:{sentinel}@host/db"
        f"?token={query_sentinel}"
    )
    with pytest.raises(database.DatabaseEngineConfigurationError) as raised:
        database.create_database_engine(url)
    error = raised.value
    for secret in (sentinel, query_sentinel):
        _assert_secret_absent(
            secret,
            str(error),
            repr(error),
            error.args,
            vars(error),
            error.safe_url,
        )
    assert error.safe_url is not None
    assert "***" in error.safe_url
    assert "?" not in error.safe_url


def test_unsupported_driver_diagnostics_remove_all_query_parameters(monkeypatch):
    sentinels = (
        "SENTINEL_AUTHORITY_SECRET",
        "SENTINEL_PASSWORD_QUERY_SECRET",
        "SENTINEL_SSLPASSWORD_QUERY_SECRET",
        "SENTINEL_TOKEN_QUERY_SECRET",
        "SENTINEL_NEUTRAL_QUERY_VALUE",
    )
    url = (
        f"postgresql+psycopg2://user:{sentinels[0]}@host.example:5544/inventory"
        f"?password={sentinels[1]}&sslpassword={sentinels[2]}"
        f"&token={sentinels[3]}&application_name={sentinels[4]}"
    )
    monkeypatch.setattr(
        database,
        "create_engine",
        lambda *_args, **_kwargs: pytest.fail("create_engine was called"),
    )

    with pytest.raises(database.DatabaseEngineConfigurationError) as raised:
        database.create_database_engine(url)

    error = raised.value
    assert error.drivername == "postgresql+psycopg2"
    assert error.safe_url is not None
    assert "***" in error.safe_url
    assert "?" not in error.safe_url
    for secret in sentinels:
        _assert_secret_absent(
            secret,
            str(error),
            repr(error),
            error.args,
            vars(error),
            error.safe_url,
        )


def test_engine_construction_failures_are_safely_wrapped(monkeypatch):
    failure = RuntimeError("synthetic safe construction failure")
    query_sentinel = "SENTINEL_CONSTRUCTION_QUERY_SECRET"
    monkeypatch.setattr(
        database,
        "create_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )
    with pytest.raises(database.DatabaseEngineConfigurationError) as raised:
        database.create_database_engine(
            f"sqlite:///:memory:?token={query_sentinel}"
        )
    assert raised.value.__cause__ is failure
    assert raised.value.drivername == "sqlite"
    assert raised.value.safe_url == "sqlite:///:memory:"
    _assert_secret_absent(
        query_sentinel,
        str(raised.value),
        repr(raised.value),
        raised.value.args,
        vars(raised.value),
        raised.value.safe_url,
    )


def test_construction_failure_redaction_preserves_internal_query_semantics(monkeypatch):
    sentinels = (
        "SENTINEL_SUPPORTED_AUTHORITY_SECRET",
        "SENTINEL_SUPPORTED_PASSWORD_QUERY",
        "SENTINEL_SUPPORTED_TOKEN_QUERY",
        "SENTINEL_SUPPORTED_NEUTRAL_QUERY",
    )
    captured = {}
    failure = RuntimeError("synthetic safe PostgreSQL construction failure")

    def fail_construction(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        raise failure

    monkeypatch.setattr(database, "create_engine", fail_construction)
    url = (
        f"postgresql://user:{sentinels[0]}@host.example:5544/inventory"
        f"?password={sentinels[1]}&token={sentinels[2]}"
        f"&application_name={sentinels[3]}"
    )

    with pytest.raises(database.DatabaseEngineConfigurationError) as raised:
        database.create_database_engine(url)

    error = raised.value
    assert error.__cause__ is failure
    assert error.drivername == "postgresql"
    assert error.safe_url is not None
    assert "***" in error.safe_url
    assert "?" not in error.safe_url
    for secret in sentinels:
        _assert_secret_absent(
            secret,
            str(error),
            repr(error),
            error.args,
            vars(error),
            error.safe_url,
        )

    engine_url = captured["url"]
    assert isinstance(engine_url, URL)
    assert engine_url.drivername == "postgresql+psycopg"
    assert hashlib.sha256(engine_url.password.encode()).digest() == hashlib.sha256(
        sentinels[0].encode()
    ).digest()
    assert set(engine_url.query) == {"password", "token", "application_name"}
    for key, secret in zip(
        ("password", "token", "application_name"),
        sentinels[1:],
    ):
        assert hashlib.sha256(engine_url.query[key].encode()).digest() == hashlib.sha256(
            secret.encode()
        ).digest()
    assert captured["kwargs"] == {"pool_pre_ping": True}


def test_global_engine_and_session_binding_remain_compatible():
    assert isinstance(database.engine, Engine)
    assert database.engine.url.drivername == "sqlite"
    assert database.engine.url.database == ":memory:"
    assert database.engine.pool._pre_ping is True
    assert database.SessionLocal.kw["bind"] is database.engine


def test_default_global_import_is_lazy_and_preserves_repository_root_path():
    script = r'''
import json
import sqlite3
import sys

connection_attempts = []

def forbidden_connect(*args, **kwargs):
    connection_attempts.append(True)
    raise AssertionError("global import attempted a DBAPI connection")

sqlite3.connect = forbidden_connect
import app.core.config as config
import app.db.database as database

expected = str(config.Path(config.__file__).resolve().parents[3] / "inventory_detector.db")
print(json.dumps({
    "drivername": database.engine.url.drivername,
    "database": database.engine.url.database,
    "expected": expected,
    "pre_ping": database.engine.pool._pre_ping,
    "session_bound": database.SessionLocal.kw["bind"] is database.engine,
    "connection_attempts": len(connection_attempts),
    "main_imported": "app.main" in sys.modules,
    "alembic_imported": any(name.startswith("alembic") for name in sys.modules),
    "helper_imported": "app.db.migrations" in sys.modules,
}))
'''
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    evidence = json.loads(result.stdout)
    assert evidence["drivername"] == "sqlite"
    assert Path(evidence["database"]).resolve() == Path(evidence["expected"]).resolve()
    assert evidence["pre_ping"] is True
    assert evidence["session_bound"] is True
    assert evidence["connection_attempts"] == 0
    assert evidence["main_imported"] is False
    assert evidence["alembic_imported"] is False
    assert evidence["helper_imported"] is False


def test_database_module_has_no_startup_migration_async_or_environment_logic():
    source = (BACKEND_ROOT / "app" / "db" / "database.py").read_text(
        encoding="utf-8"
    )
    assert "app.main" not in source
    assert "alembic" not in source.lower()
    assert "ensure_sqlite_demo_columns" not in source
    assert "create_async_engine" not in source
    assert "psycopg2" not in source
    assert "os.getenv" not in source
    assert "os.environ" not in source
    assert "render_as_string(hide_password=False)" not in source
    assert "engine = create_database_engine(settings.database_url)" in source
