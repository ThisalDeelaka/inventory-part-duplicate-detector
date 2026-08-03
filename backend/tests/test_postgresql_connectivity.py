import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import (
    DatabaseEngineConfigurationError,
    create_database_engine,
)


@pytest.mark.postgres_integration
def test_disposable_postgresql_connectivity_baseline() -> None:
    configured_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if configured_url is None:
        pytest.skip(
            "POSTGRES_TEST_DATABASE_URL is not set; "
            "opt-in PostgreSQL connectivity test skipped"
        )

    try:
        engine = create_database_engine(configured_url)
    except DatabaseEngineConfigurationError as error:
        details = [
            "PostgreSQL test engine configuration failed",
            f"driver={error.drivername or 'unknown'}",
        ]
        if error.safe_url is not None:
            details.append(f"url={error.safe_url}")
        raise AssertionError("; ".join(details)) from None

    safe_url = engine.url.set(query={}).render_as_string(hide_password=True)
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"

        try:
            with engine.connect() as connection:
                assert connection.execute(text("SELECT 1")).scalar_one() == 1
                assert connection.execute(
                    text("SELECT current_database()")
                ).scalar_one() == "inventory_test"
                assert connection.execute(
                    text("SELECT current_user")
                ).scalar_one() == "inventory_test"
                assert connection.execute(
                    text("SELECT current_setting('server_version_num')")
                ).scalar_one() == "180004"
                assert connection.execute(
                    text("SELECT current_setting('server_version')")
                ).scalar_one().startswith("18.4")

                relations = connection.execute(
                    text(
                        "SELECT namespace.nspname, relation.relname "
                        "FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid = relation.relnamespace "
                        "WHERE namespace.nspname NOT IN "
                        "('pg_catalog', 'information_schema') "
                        "AND namespace.nspname NOT LIKE 'pg_toast%' "
                        "AND namespace.nspname NOT LIKE 'pg_temp_%' "
                        "AND relation.relkind IN ('r', 'p', 'v', 'm', 'S', 'f') "
                        "ORDER BY namespace.nspname, relation.relname"
                    )
                ).all()
                assert relations == [], "unexpected non-system relations found"
        except SQLAlchemyError as error:
            raise AssertionError(
                "PostgreSQL connectivity check failed "
                f"({type(error).__name__}); url={safe_url}"
            ) from None
    finally:
        engine.dispose()
