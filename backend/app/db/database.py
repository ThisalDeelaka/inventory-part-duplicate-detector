from types import MappingProxyType

from sqlalchemy import MetaData
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

NAMING_CONVENTION = MappingProxyType({
    "pk": "pk_%(table_name)s",
    "fk": (
        "fk_%(table_name)s_%(column_0_N_name)s_"
        "%(referred_table_name)s"
    ),
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
})


class DatabaseEngineConfigurationError(ValueError):
    """Raised when a database URL cannot safely configure a supported engine."""

    def __init__(
        self,
        message: str,
        *,
        drivername: str | None = None,
        safe_url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.drivername = drivername
        self.safe_url = safe_url


def _render_safe_database_url(url: URL) -> str:
    """Render useful URL diagnostics without credentials or query data."""
    return url.set(query={}).render_as_string(hide_password=True)


def create_database_engine(database_url: str) -> Engine:
    """Create a supported synchronous engine without opening a connection."""
    if not isinstance(database_url, str):
        raise TypeError("database_url must be a string")
    if not database_url.strip():
        raise DatabaseEngineConfigurationError("Database URL is empty.")

    try:
        url = make_url(database_url)
    except Exception as error:
        raise DatabaseEngineConfigurationError(
            "Database URL could not be parsed."
        ) from error

    drivername = url.drivername
    safe_url = _render_safe_database_url(url)
    if drivername in {"sqlite", "sqlite+pysqlite"}:
        engine_url: URL = url
        engine_options = {
            "connect_args": {"check_same_thread": False},
            "pool_pre_ping": True,
        }
    elif drivername in {"postgresql", "postgresql+psycopg", "postgres"}:
        engine_url = url.set(drivername="postgresql+psycopg")
        engine_options = {"pool_pre_ping": True}
    else:
        raise DatabaseEngineConfigurationError(
            "Database URL uses an unsupported driver.",
            drivername=drivername,
            safe_url=safe_url,
        )

    try:
        return create_engine(engine_url, **engine_options)
    except Exception as error:
        raise DatabaseEngineConfigurationError(
            "Database engine could not be configured.",
            drivername=drivername,
            safe_url=safe_url,
        ) from error


engine = create_database_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base(metadata=MetaData(naming_convention=dict(NAMING_CONVENTION)))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
