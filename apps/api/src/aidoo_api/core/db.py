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
    from aidoo_api.domains.docs import models as docs_models  # noqa: F401
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
        """
        CREATE TABLE IF NOT EXISTS user_system_roles (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            role VARCHAR(40) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_user_system_role UNIQUE (user_id, role)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_user_system_roles_user_id ON user_system_roles (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_user_system_roles_role ON user_system_roles (role)",
        """
        CREATE TABLE IF NOT EXISTS group_system_roles (
            id VARCHAR(36) PRIMARY KEY,
            group_id VARCHAR(36) NOT NULL REFERENCES access_groups(id),
            role VARCHAR(40) NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_group_system_role UNIQUE (group_id, role)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_group_system_roles_group_id ON group_system_roles (group_id)",
        "CREATE INDEX IF NOT EXISTS ix_group_system_roles_role ON group_system_roles (role)",
        "ALTER TABLE teams ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS ix_teams_trashed_at ON teams (trashed_at)",
        "ALTER TABLE pms_issues ADD COLUMN IF NOT EXISTS parent_id VARCHAR(36) REFERENCES pms_issues(id)",
        "ALTER TABLE pms_issues ADD COLUMN IF NOT EXISTS description_blocks JSON",
        "ALTER TABLE pms_issue_comments ADD COLUMN IF NOT EXISTS body_blocks JSON",
        "ALTER TABLE pms_issues ADD COLUMN IF NOT EXISTS estimate_hours REAL",
        "ALTER TABLE pms_issues ADD COLUMN IF NOT EXISTS recurrence_rule VARCHAR(120)",
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
        # ── pms_project_statuses table ──
        """
        CREATE TABLE IF NOT EXISTS pms_project_statuses (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES pms_projects(id),
            slug VARCHAR(40) NOT NULL,
            name VARCHAR(60) NOT NULL,
            color VARCHAR(24) NOT NULL DEFAULT '#6b7280',
            category VARCHAR(24) NOT NULL DEFAULT 'active',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_pms_project_status_slug UNIQUE (project_id, slug)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_project_statuses_project_id ON pms_project_statuses (project_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_project_statuses_slug ON pms_project_statuses (slug)",
        # ── pms_task_templates table ──
        """
        CREATE TABLE IF NOT EXISTS pms_task_templates (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES pms_projects(id),
            name VARCHAR(140) NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            default_status VARCHAR(40) NOT NULL DEFAULT 'backlog',
            default_priority VARCHAR(24) NOT NULL DEFAULT 'medium',
            checklist_items JSON,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_task_templates_project_id ON pms_task_templates (project_id)",
        # ── pms_custom_fields + pms_custom_field_values tables ──
        """
        CREATE TABLE IF NOT EXISTS pms_custom_fields (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES pms_projects(id),
            name VARCHAR(100) NOT NULL,
            field_type VARCHAR(24) NOT NULL,
            options JSON,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_custom_fields_project_id ON pms_custom_fields (project_id)",
        """
        CREATE TABLE IF NOT EXISTS pms_custom_field_values (
            id VARCHAR(36) PRIMARY KEY,
            issue_id VARCHAR(36) NOT NULL REFERENCES pms_issues(id),
            field_id VARCHAR(36) NOT NULL REFERENCES pms_custom_fields(id),
            value TEXT NOT NULL DEFAULT '',
            CONSTRAINT uq_pms_cf_value UNIQUE (issue_id, field_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_custom_field_values_issue_id ON pms_custom_field_values (issue_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_custom_field_values_field_id ON pms_custom_field_values (field_id)",
        # ── pms_issue_assignees table ──
        """
        CREATE TABLE IF NOT EXISTS pms_issue_assignees (
            id VARCHAR(36) PRIMARY KEY,
            issue_id VARCHAR(36) NOT NULL REFERENCES pms_issues(id),
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            CONSTRAINT uq_pms_issue_assignee UNIQUE (issue_id, user_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_issue_assignees_issue_id ON pms_issue_assignees (issue_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_issue_assignees_user_id ON pms_issue_assignees (user_id)",
        # ── pms_folders table + pms_projects.folder_id ──
        """
        CREATE TABLE IF NOT EXISTS pms_folders (
            id VARCHAR(36) PRIMARY KEY,
            team_id VARCHAR(36) REFERENCES teams(id),
            name VARCHAR(140) NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_folders_team_id ON pms_folders (team_id)",
        "ALTER TABLE pms_projects ADD COLUMN IF NOT EXISTS folder_id VARCHAR(36)",
        "CREATE INDEX IF NOT EXISTS ix_pms_projects_folder_id ON pms_projects (folder_id)",
        # ── drop removed feature tables ──
        "DROP TABLE IF EXISTS pms_goal_links",
        "DROP TABLE IF EXISTS pms_goals",
        "DROP TABLE IF EXISTS pms_automations",
        # ── pms_docs table ──
        """
        CREATE TABLE IF NOT EXISTS pms_docs (
            id VARCHAR(36) PRIMARY KEY,
            project_id VARCHAR(36) NOT NULL REFERENCES pms_projects(id),
            title VARCHAR(200) NOT NULL,
            content_blocks JSON,
            created_by_id VARCHAR(36) NOT NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_docs_project_id ON pms_docs (project_id)",
        # ── pms_space_docs table ──
        """
        CREATE TABLE IF NOT EXISTS pms_space_docs (
            id VARCHAR(36) PRIMARY KEY,
            team_id VARCHAR(36) NOT NULL REFERENCES teams(id),
            title VARCHAR(200) NOT NULL,
            created_by_id VARCHAR(36) NOT NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            trashed_at TIMESTAMP
        )
        """,
        "ALTER TABLE pms_space_docs ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS ix_pms_space_docs_team_id ON pms_space_docs (team_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_space_docs_trashed_at ON pms_space_docs (trashed_at)",
        # ── pms_space_doc_pages table ──
        """
        CREATE TABLE IF NOT EXISTS pms_space_doc_pages (
            id VARCHAR(36) PRIMARY KEY,
            team_id VARCHAR(36) NOT NULL REFERENCES teams(id),
            space_doc_id VARCHAR(36) NOT NULL REFERENCES pms_space_docs(id),
            parent_id VARCHAR(36) REFERENCES pms_space_doc_pages(id),
            title VARCHAR(200) NOT NULL,
            content_blocks JSON,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_by_id VARCHAR(36) NOT NULL REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            trashed_at TIMESTAMP
        )
        """,
        "ALTER TABLE pms_space_doc_pages ADD COLUMN IF NOT EXISTS space_doc_id VARCHAR(36) REFERENCES pms_space_docs(id)",
        "ALTER TABLE pms_space_doc_pages ADD COLUMN IF NOT EXISTS trashed_at TIMESTAMP",
        "CREATE INDEX IF NOT EXISTS ix_pms_space_doc_pages_team_id ON pms_space_doc_pages (team_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_space_doc_pages_space_doc_id ON pms_space_doc_pages (space_doc_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_space_doc_pages_parent_id ON pms_space_doc_pages (parent_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_space_doc_pages_trashed_at ON pms_space_doc_pages (trashed_at)",
        """
        WITH RECURSIVE orphan_pages AS (
            SELECT id
            FROM pms_space_doc_pages
            WHERE space_doc_id IS NULL
            UNION
            SELECT child.id
            FROM pms_space_doc_pages child
            JOIN orphan_pages orphan ON child.parent_id = orphan.id
        )
        DELETE FROM pms_space_doc_pages
        WHERE id IN (SELECT id FROM orphan_pages)
        """,
        "ALTER TABLE pms_space_doc_pages ALTER COLUMN space_doc_id SET NOT NULL",
        # ── pms_user_doc_prefs table ──
        """
        CREATE TABLE IF NOT EXISTS pms_user_doc_prefs (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL REFERENCES users(id),
            space_doc_id VARCHAR(36) NOT NULL REFERENCES pms_space_docs(id),
            is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
            is_private BOOLEAN NOT NULL DEFAULT FALSE,
            last_viewed_at TIMESTAMP,
            CONSTRAINT uq_user_doc_pref UNIQUE (user_id, space_doc_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_pms_user_doc_prefs_user_id ON pms_user_doc_prefs (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_pms_user_doc_prefs_doc_id ON pms_user_doc_prefs (space_doc_id)",
    ]

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
