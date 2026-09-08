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
    assert [revision.revision for revision in revisions] == ["company_20260908"]
    assert revisions[0].down_revision is None
    assert "clean deployment baseline" in revisions[0].doc


@pytest.mark.migration
def test_fresh_baseline_owns_company_identity_and_app_local_resources(postgres_dsn: str) -> None:
    config = _migration_config(postgres_dsn)
    command.upgrade(config, "head")
    engine = sa.create_engine(postgres_dsn)
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names())
        assert {
            "users",
            "groups",
            "group_members",
            "organization_units",
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
                == "company_20260908"
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
