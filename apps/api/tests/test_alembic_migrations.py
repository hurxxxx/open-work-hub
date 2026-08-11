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
        "b7f2d4a9c6e1",
        "a2e6c8f1b3d5",
        "9d4a6f8b2c1e",
        "8b1f3c2d4e5a",
        "3efcf1ed36c3",
    ]
    assert revisions[-1].down_revision is None
    assert revisions[-1].doc == "initial open work hub schema"
