from __future__ import annotations

from collections.abc import Iterator

from alembic import command
import pytest
from sqlalchemy import create_engine, inspect


pytestmark = pytest.mark.migration

BASE_REVISION = "a6b8c0d2e4f7"
ATTACHMENT_REVISION = "c7d9e1f3a5b8"
ATTACHMENT_TABLE = "legacy_issue_vehicle_module_checklist_attachments"
CLEANUP_TABLE = "legacy_issue_vehicle_module_checklist_attachment_cleanups"


@pytest.fixture
def checklist_attachment_migration_config(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
) -> Iterator[object]:
    monkeypatch.setenv("AI_DO_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("AI_DO_LLM_HEALTHCHECK_ON_STARTUP", "0")

    from ai_do_api.core.db import _alembic_config
    from ai_do_api.core.settings import get_settings

    get_settings.cache_clear()
    engine = create_engine(postgres_dsn)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    engine.dispose()

    try:
        yield _alembic_config()
    finally:
        get_settings.cache_clear()


def test_vehicle_module_checklist_attachment_migration_upgrade_and_downgrade(
    checklist_attachment_migration_config,
    postgres_dsn: str,
) -> None:
    command.upgrade(checklist_attachment_migration_config, BASE_REVISION)
    engine = create_engine(postgres_dsn)
    try:
        assert {ATTACHMENT_TABLE, CLEANUP_TABLE}.isdisjoint(inspect(engine).get_table_names())

        command.upgrade(checklist_attachment_migration_config, ATTACHMENT_REVISION)
        inspector = inspect(engine)
        assert ATTACHMENT_TABLE in inspector.get_table_names()
        assert {column["name"] for column in inspector.get_columns(ATTACHMENT_TABLE)} == {
            "id",
            "workspace_id",
            "checklist_id",
            "record_id",
            "filename",
            "content_type",
            "size_bytes",
            "storage_key",
            "uploaded_by_id",
            "created_at",
        }
        assert {
            tuple(foreign_key["constrained_columns"])
            for foreign_key in inspector.get_foreign_keys(ATTACHMENT_TABLE)
        } == {
            ("workspace_id",),
            ("checklist_id",),
            ("record_id",),
            ("uploaded_by_id",),
        }
        assert CLEANUP_TABLE in inspector.get_table_names()
        assert {column["name"] for column in inspector.get_columns(CLEANUP_TABLE)} == {
            "id",
            "workspace_id",
            "storage_key",
            "attempt_count",
            "last_error",
            "last_attempted_at",
            "created_at",
        }
        assert {
            tuple(foreign_key["constrained_columns"])
            for foreign_key in inspector.get_foreign_keys(CLEANUP_TABLE)
        } == {("workspace_id",)}
        assert {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(CLEANUP_TABLE)
        } == {("storage_key",)}

        command.downgrade(checklist_attachment_migration_config, BASE_REVISION)
        assert {ATTACHMENT_TABLE, CLEANUP_TABLE}.isdisjoint(inspect(engine).get_table_names())
    finally:
        engine.dispose()
