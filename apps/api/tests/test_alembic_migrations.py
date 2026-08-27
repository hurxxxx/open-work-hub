from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.mark.migration
def test_repository_has_one_linear_migration_chain() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))

    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert [revision.revision for revision in revisions] == [
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
