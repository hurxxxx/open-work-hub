from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
import sqlalchemy as sa

from open_work_hub_api.core import db as db_module


def _load_hermes_runtime_migration() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "e8b4c6d2f1a7_harden_hermes_runtime_lifecycle.py"
    )
    spec = importlib.util.spec_from_file_location("hermes_runtime_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _app_bar_test_tables() -> tuple[sa.MetaData, sa.Table, sa.Table]:
    metadata = sa.MetaData()
    categories = sa.Table(
        "platform_app_bar_categories",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(64), unique=True, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("icon_key", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    category_apps = sa.Table(
        "platform_app_bar_category_apps",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category_id", sa.String(36), nullable=False),
        sa.Column("app_id", sa.String(64), unique=True, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    return metadata, categories, category_apps


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


@pytest.mark.migration
def test_repository_has_one_linear_migration_chain() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))

    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert [revision.revision for revision in revisions] == [
        "e8b4c6d2f1a7",
        "d1f4a8c2e6b9",
        "a7e3c1d9f5b2",
        "c2d7e9f1a4b8",
        "f4a8c2d6e1b9",
        "e3b1c7d9a4f2",
        "d6a9f4c2b8e1",
        "c5f8a2d1e7b4",
        "b4e7c1d9a2f6",
        "a7c4e9f2b6d1",
        "a9c3d2e1f4b5",
        "f6d2a4c8e1b3",
        "e5c9a1b7d3f2",
        "d4b7e9a2c6f1",
        "c8a1e4f7b2d9",
        "b7f2d4a9c6e1",
        "a2e6c8f1b3d5",
        "9d4a6f8b2c1e",
        "8b1f3c2d4e5a",
        "3efcf1ed36c3",
    ]
    assert revisions[-1].down_revision is None
    assert revisions[-1].doc == "initial open work hub schema"


@pytest.mark.migration
def test_hermes_runtime_migration_adds_terminal_to_existing_all_apps() -> None:
    migration = _load_hermes_runtime_migration()
    metadata, categories, category_apps = _app_bar_test_tables()
    engine = sa.create_engine("sqlite://")
    metadata.create_all(engine)
    now = datetime(2026, 9, 2)

    with engine.begin() as connection:
        connection.execute(
            categories.insert(),
            [
                {
                    "id": "other-category",
                    "key": "other",
                    "title": "Other",
                    "icon_key": "grid",
                    "position": 0,
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": "all-category",
                    "key": "localized-category",
                    "title": "전체 앱",
                    "icon_key": "layout-grid",
                    "position": 1,
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            category_apps.insert(),
            {
                "id": "existing-app",
                "category_id": "all-category",
                "app_id": "chatbot",
                "position": 12,
                "created_at": now,
                "updated_at": now,
            },
        )

        migration._ensure_hermes_terminal_app_bar_mapping(connection)
        migration._ensure_hermes_terminal_app_bar_mapping(connection)

        rows = connection.execute(
            sa.select(
                category_apps.c.id,
                category_apps.c.category_id,
                category_apps.c.app_id,
                category_apps.c.position,
            ).where(category_apps.c.app_id == "hermes-terminal")
        ).all()

    assert rows == [
        (
            migration.HERMES_TERMINAL_CATEGORY_MAPPING_ID,
            "all-category",
            "hermes-terminal",
            13,
        )
    ]


@pytest.mark.migration
def test_hermes_runtime_migration_creates_fallback_category_when_empty() -> None:
    migration = _load_hermes_runtime_migration()
    metadata, categories, category_apps = _app_bar_test_tables()
    engine = sa.create_engine("sqlite://")
    metadata.create_all(engine)

    with engine.begin() as connection:
        migration._ensure_hermes_terminal_app_bar_mapping(connection)
        category = connection.execute(sa.select(categories)).one()
        mapping = connection.execute(sa.select(category_apps)).one()

    assert category.id == migration.HERMES_TERMINAL_FALLBACK_CATEGORY_ID
    assert category.key == "all-apps"
    assert mapping.category_id == category.id
    assert mapping.app_id == "hermes-terminal"
