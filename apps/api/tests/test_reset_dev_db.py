from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_work_hub_api import reset_dev_db


POSTGRES_DSN = "postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test"


def test_reset_dev_db_refuses_preview_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["reset_dev_db"])
    monkeypatch.setattr(
        reset_dev_db,
        "get_settings",
        lambda: SimpleNamespace(environment="preview", postgres_dsn=POSTGRES_DSN),
    )

    with pytest.raises(SystemExit, match="preview/production"):
        reset_dev_db.main()
