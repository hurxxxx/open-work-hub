from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from aidoo_api.core.settings import get_settings


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


def init_db() -> None:
    from aidoo_api.domains.auth import models  # noqa: F401
    from aidoo_api.domains.auth.access import ensure_seed_data
    from aidoo_api.domains.media import models as media_models  # noqa: F401
    from aidoo_api.domains.pms import models as pms_models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _apply_postgres_schema_compat(engine)

    with Session(engine) as session:
        ensure_seed_data(session)


def _apply_postgres_schema_compat(engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_code VARCHAR(40)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS job_title VARCHAR(120)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(24) DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS theme_preference VARCHAR(16) DEFAULT 'system'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS primary_org_unit_id VARCHAR(36)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP",
        "ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP",
        "ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS user_agent VARCHAR(255)",
        "ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS ip_address VARCHAR(64)",
        "ALTER TABLE pms_issues ADD COLUMN IF NOT EXISTS parent_id VARCHAR(36) REFERENCES pms_issues(id)",
        "ALTER TABLE pms_issues ADD COLUMN IF NOT EXISTS description_blocks JSON",
        "ALTER TABLE pms_issue_comments ADD COLUMN IF NOT EXISTS body_blocks JSON",
        "ALTER TABLE pms_issues ADD COLUMN IF NOT EXISTS estimate_hours REAL",
        "ALTER TABLE pms_projects ADD COLUMN IF NOT EXISTS team_id VARCHAR(36)",
        "CREATE INDEX IF NOT EXISTS ix_pms_projects_team_id ON pms_projects (team_id)",
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'pms_projects_team_id_fkey'
                  AND conrelid = 'pms_projects'::regclass
            ) THEN
                ALTER TABLE pms_projects
                ADD CONSTRAINT pms_projects_team_id_fkey
                FOREIGN KEY (team_id) REFERENCES teams(id);
            END IF;
        END
        $$;
        """,
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
