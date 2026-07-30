from types import MappingProxyType

from sqlalchemy import MetaData
from sqlalchemy import create_engine
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

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base(metadata=MetaData(naming_convention=dict(NAMING_CONVENTION)))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
