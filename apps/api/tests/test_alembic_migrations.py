from pathlib import Path
from types import SimpleNamespace

import pytest
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


@pytest.mark.migration
def test_repository_has_one_linear_migration_chain() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))

    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert [revision.revision for revision in revisions] == [
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
