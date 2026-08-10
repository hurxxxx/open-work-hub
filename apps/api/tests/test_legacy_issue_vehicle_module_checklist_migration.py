from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text


pytestmark = pytest.mark.migration

BASE_REVISION = "4a9c1e6f2b3d"
NEW_TABLES = {
    "legacy_issue_vehicle_module_checklists",
    "legacy_issue_vehicle_module_checklist_records",
}


@pytest.fixture
def module_checklist_migration_config(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
) -> Iterator[object]:
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("OPEN_ALM_LLM_HEALTHCHECK_ON_STARTUP", "0")

    from open_alm_api.core.db import _alembic_config
    from open_alm_api.core.settings import get_settings

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


def _seed_legacy_checklist(connection) -> None:
    connection.execute(
        text(
            """
            INSERT INTO workspaces (
                id, key, name, description, active, created_at, updated_at
            ) VALUES (
                'module-checklist-workspace',
                'module-checklist-workspace',
                'Module Checklist Workspace',
                '',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO legacy_issue_data_revisions (
                id, workspace_id, dataset_key, revision_no, status,
                created_at, updated_at, published_at
            ) VALUES (
                'module-master-revision',
                'module-checklist-workspace',
                'legacy_issue.module.electrical-control-sw',
                17,
                'published',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO legacy_issue_vehicle_models (
                id, workspace_id, vehicle_code, vehicle_code_normalized,
                vehicle_name, active, created_at, updated_at
            ) VALUES (
                'module-vehicle',
                'module-checklist-workspace',
                'TEST',
                'test',
                'Test Vehicle',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO legacy_issue_records (
                id, workspace_id, dataset_key, module_key, revision_id,
                stable_record_id, field_values, created_at, updated_at
            ) VALUES (
                'module-master-record',
                'module-checklist-workspace',
                'legacy_issue.module.electrical-control-sw',
                'electrical-control-sw',
                'module-master-revision',
                'module-master-stable-record',
                CAST('{"problem": "preserve me"}' AS jsonb),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO legacy_issue_vehicle_checklist_revisions (
                id, workspace_id, vehicle_model_id, revision_no, status,
                source_dataset_key, source_master_revision_id,
                source_master_revision_no, definition_snapshot, row_count,
                created_at, updated_at
            ) VALUES (
                'legacy-aggregate-checklist',
                'module-checklist-workspace',
                'module-vehicle',
                1,
                'draft',
                'legacy_issue.module.electrical-control-sw',
                'module-master-revision',
                17,
                CAST('{}' AS jsonb),
                1,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO legacy_issue_vehicle_checklist_records (
                id, workspace_id, checklist_revision_id, source_record_id,
                source_stable_record_id, source_module_key, sort_order,
                field_values, created_at, updated_at
            ) VALUES (
                'legacy-aggregate-checklist-record',
                'module-checklist-workspace',
                'legacy-aggregate-checklist',
                'module-master-record',
                'module-master-stable-record',
                'electrical-control-sw',
                0,
                CAST('{}' AS jsonb),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """
        )
    )


def test_upgrade_stops_before_dropping_legacy_checklist_rows(
    module_checklist_migration_config,
    postgres_dsn: str,
) -> None:
    command.upgrade(module_checklist_migration_config, BASE_REVISION)
    engine = create_engine(postgres_dsn)
    try:
        with engine.begin() as connection:
            _seed_legacy_checklist(connection)

        with pytest.raises(
            RuntimeError,
            match=(
                "legacy_issue_vehicle_checklist_revisions=1, "
                "legacy_issue_vehicle_checklist_records=1"
            ),
        ):
            command.upgrade(module_checklist_migration_config, "head")

        assert not (NEW_TABLES & set(inspect(engine).get_table_names()))
        with engine.connect() as connection:
            revision_count = connection.scalar(
                text("SELECT COUNT(*) FROM legacy_issue_vehicle_checklist_revisions")
            )
            record_count = connection.scalar(
                text("SELECT COUNT(*) FROM legacy_issue_vehicle_checklist_records")
            )
            version = connection.scalar(text("SELECT version_num FROM alembic_version"))

        assert (revision_count, record_count) == (1, 1)
        assert version == BASE_REVISION
    finally:
        engine.dispose()
