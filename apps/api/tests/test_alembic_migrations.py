from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from open_work_hub_api.core import db as db_module


def test_runtime_alembic_config_uses_workspace_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_root = tmp_path / "apps" / "api"
    api_root.mkdir(parents=True)
    ini_path = api_root / "alembic.ini"
    ini_path.write_text(
        "[alembic]\nscript_location = %(here)s/alembic\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(db_module, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(
        db_module,
        "get_settings",
        lambda: SimpleNamespace(postgres_dsn="sqlite:///runtime-test.db"),
    )

    config = db_module._alembic_config()

    assert Path(config.config_file_name or "") == ini_path
    assert config.get_main_option("script_location") == str(api_root / "alembic")
    assert config.get_main_option("sqlalchemy.url") == "sqlite:///runtime-test.db"


def _migration_config(dsn: str | None = None) -> Config:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    if dsn:
        config.set_main_option("sqlalchemy.url", dsn.replace("%", "%%"))
    return config


@pytest.mark.migration
def test_repository_starts_at_company_deployment_baseline() -> None:
    revisions = list(ScriptDirectory.from_config(_migration_config()).walk_revisions())
    assert [revision.revision for revision in revisions] == [
        "hermes_runtime_20260912",
        "group_sources_20260912",
        "company_20260908",
    ]
    assert revisions[0].down_revision == "group_sources_20260912"
    assert revisions[1].down_revision == "company_20260908"
    assert revisions[-1].down_revision is None
    assert "clean deployment baseline" in revisions[-1].doc


@pytest.mark.migration
def test_fresh_baseline_owns_company_identity_and_app_local_resources(postgres_dsn: str) -> None:
    config = _migration_config(postgres_dsn)
    command.upgrade(config, "group_sources_20260912")
    engine = sa.create_engine(postgres_dsn)
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "users",
            "groups",
            "group_members",
            "app_access_policies",
            "app_user_grants",
            "app_group_grants",
            "company_app_controls",
            "pms_spaces",
            "pms_space_members",
            "pms_space_group_bindings",
            "docs_native_docs",
            "hermes_session_bindings",
        } <= tables
        assert "organization_units" not in tables
        assert not any("workspace" in table for table in tables)
        for table in tables:
            assert not any(
                column["name"] in {"workspace_id", "execution_workspace_id", "origin_workspace_id"}
                for column in inspector.get_columns(table)
            )
        assert any(
            foreign_key["referred_table"] == "pms_spaces"
            for foreign_key in inspector.get_foreign_keys("pms_space_members")
        )
        checks = {
            row["name"] for row in inspector.get_check_constraints("pms_space_group_bindings")
        }
        assert "ck_pms_space_group_role" in checks
        with engine.connect() as connection:
            assert (
                connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
                == "group_sources_20260912"
            )
        command.downgrade(config, "base")
        assert sa.inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()


def test_runtime_metadata_has_no_duplicate_index_declarations() -> None:
    from collections import Counter
    from open_work_hub_api.core.db import Base
    from open_work_hub_api.core.model_registry import import_all_models

    import_all_models()
    duplicated = {
        table.name: sorted(
            name
            for name, count in Counter(index.name for index in table.indexes).items()
            if count > 1
        )
        for table in Base.metadata.tables.values()
    }
    assert {table: names for table, names in duplicated.items() if names} == {}


@pytest.mark.migration
def test_group_unification_preserves_ids_assignments_grants_and_rollback(postgres_dsn: str) -> None:
    config = _migration_config(postgres_dsn)
    command.upgrade(config, "company_20260908")
    engine = sa.create_engine(postgres_dsn)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                INSERT INTO users (id, login_id, email, full_name, password_hash, status,
                    login_blocked, must_change_password, theme_preference, locale,
                    time_zone, date_format, created_at, updated_at)
                VALUES ('migration-user', 'migration-user', 'migration@example.test',
                    'Migration User', 'fixture', 'active', false, false, 'system', 'ko-KR',
                    'Asia/Seoul', 'korean', now(), now())
            """)
            )
            conn.execute(
                sa.text("""
                INSERT INTO organization_units
                    (id, name, slug, unit_type, parent_id, active, head_user_id, created_at, updated_at)
                VALUES ('old-root', 'Root', 'root', 'division', NULL, true, 'migration-user', now(), now()),
                       ('old-child', 'Child', 'child', 'department', 'old-root', false, NULL, now(), now()),
                       ('old-orphan', 'Orphan', 'orphan', 'department', NULL, true, NULL, now(), now())
            """)
            )
            conn.execute(
                sa.text("""
                INSERT INTO groups (id, kind, organization_unit_id, name, description, active, created_at, updated_at)
                VALUES ('stable-root', 'organization', 'old-root', '', 'Retain description', true, now(), now()),
                       ('stable-child', 'organization', 'old-child', '', '', true, now(), now()),
                       ('stable-manual', 'manual', NULL, 'TF', 'TF description', true, now(), now())
            """)
            )
            conn.execute(
                sa.text(
                    "UPDATE users SET primary_organization_unit_id='old-child' WHERE id='migration-user'"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO group_members VALUES ('stable-manual', 'migration-user', now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO company_app_controls (app_id, enabled, created_at, updated_at) VALUES ('community', true, now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO app_access_policies (app_id, audience) VALUES ('community', 'selected')"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO app_group_grants (app_id, group_id) VALUES ('community', 'stable-root')"
                )
            )
        command.upgrade(config, "group_sources_20260912")
        with engine.connect() as conn:
            groups = {
                row["id"]: row for row in conn.execute(sa.text("SELECT * FROM groups")).mappings()
            }
            assert groups["stable-root"]["source"] == "hr"
            assert groups["stable-root"]["name"] == "Root"
            assert groups["stable-root"]["head_user_id"] == "migration-user"
            assert groups["stable-root"]["description"] == "Retain description"
            assert groups["stable-root"]["source_reference"] == "old-root"
            assert groups["stable-child"]["parent_id"] == "stable-root"
            assert not groups["stable-child"]["active"]
            assert groups["stable-manual"]["source"] == "local"
            assert len(groups) == 4
            assert (
                conn.scalar(
                    sa.text(
                        "SELECT primary_organization_unit_id FROM users WHERE id='migration-user'"
                    )
                )
                == "stable-child"
            )
            assert (
                conn.scalar(
                    sa.text("SELECT group_id FROM app_group_grants WHERE app_id='community'")
                )
                == "stable-root"
            )
            assert (
                conn.scalar(
                    sa.text("SELECT group_id FROM group_members WHERE user_id='migration-user'")
                )
                == "stable-manual"
            )
            assert "organization_units" not in sa.inspect(conn).get_table_names()
        command.downgrade(config, "company_20260908")
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    sa.text(
                        "SELECT primary_organization_unit_id FROM users WHERE id='migration-user'"
                    )
                )
                == "old-child"
            )
            assert (
                conn.scalar(
                    sa.text("SELECT parent_id FROM organization_units WHERE id='old-child'")
                )
                == "old-root"
            )
            assert (
                conn.scalar(
                    sa.text("SELECT group_id FROM app_group_grants WHERE app_id='community'")
                )
                == "stable-root"
            )
        command.upgrade(config, "group_sources_20260912")
        with engine.connect() as conn:
            assert (
                conn.scalar(
                    sa.text(
                        "SELECT primary_organization_unit_id FROM users WHERE id='migration-user'"
                    )
                )
                == "stable-child"
            )
    finally:
        engine.dispose()
