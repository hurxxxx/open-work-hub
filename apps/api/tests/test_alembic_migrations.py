from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory


@pytest.mark.migration
def test_repository_has_one_initial_schema_revision() -> None:
    api_root = Path(__file__).resolve().parents[1]
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))

    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    assert len(revisions) == 1
    assert revisions[0].down_revision is None
    assert revisions[0].description == "initial Open Work Hub schema"
