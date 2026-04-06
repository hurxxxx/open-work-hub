from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from aidoo_api.core.settings import get_settings


class Base(DeclarativeBase):
    pass


def _engine_options(database_url: str) -> dict[str, object]:
    if database_url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
        }
    return {
        "pool_pre_ping": True,
    }


@lru_cache(maxsize=1)
def get_engine():
    settings = get_settings()
    return create_engine(settings.postgres_dsn, **_engine_options(settings.postgres_dsn))


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    from aidoo_api.domains.auth import models  # noqa: F401
    from aidoo_api.domains.pms import models as pms_models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
