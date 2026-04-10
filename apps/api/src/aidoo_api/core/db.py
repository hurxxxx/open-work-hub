from __future__ import annotations

import logging
import os
from collections.abc import Generator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from aidoo_api.core.settings import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _engine_options(database_url: str) -> dict[str, object]:
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


def _alembic_config():
    from alembic.config import Config

    ini_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", get_settings().postgres_dsn)
    return cfg


def run_migrations() -> None:
    """Apply all pending Alembic migrations against the configured database."""
    from alembic import command

    command.upgrade(_alembic_config(), "head")


def init_db() -> None:
    """Application startup database hook.

    Schema is owned by Alembic. Setting ``DOOWON_API_AUTO_MIGRATE=1`` runs
    ``alembic upgrade head`` at boot — convenient for local dev and test
    fixtures, but production deploys must run migrations explicitly from a
    release script and leave this flag unset.
    """
    from aidoo_api.domains.auth import models  # noqa: F401
    from aidoo_api.domains.auth.access import ensure_seed_data
    from aidoo_api.domains.docs import models as docs_models  # noqa: F401
    from aidoo_api.domains.media import models as media_models  # noqa: F401
    from aidoo_api.domains.meeting import models as meeting_models  # noqa: F401
    from aidoo_api.domains.pms import models as pms_models  # noqa: F401

    if os.environ.get("DOOWON_API_AUTO_MIGRATE", "").lower() in {"1", "true", "yes"}:
        run_migrations()

    engine = get_engine()
    with Session(engine) as session:
        ensure_seed_data(session)
