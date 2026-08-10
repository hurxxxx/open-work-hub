from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_do_api import reset_dev_db


POSTGRES_DSN = "postgresql+psycopg://ai_do_test:ai_do_test@127.0.0.1:5432/ai_do_test"


def test_reset_dev_db_refuses_preview_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["reset_dev_db"])
    monkeypatch.setattr(
        reset_dev_db,
        "get_settings",
        lambda: SimpleNamespace(environment="preview", postgres_dsn=POSTGRES_DSN),
    )

    with pytest.raises(SystemExit, match="preview/production"):
        reset_dev_db.main()
