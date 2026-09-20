from __future__ import annotations

from contextlib import ExitStack

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from open_work_hub_api.core import db
from open_work_hub_api.core.settings import Settings


def test_api_burst_returns_to_small_idle_pool(tmp_path, monkeypatch) -> None:
    settings = Settings(_env_file=None)
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    options = db._engine_options("postgresql+psycopg://unused/test")
    assert options.pop("connect_args")["application_name"].endswith(":api")
    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}", poolclass=QueuePool, **options)
    try:
        with ExitStack() as stack:
            for _ in range(10):
                connection = stack.enter_context(engine.connect())
                assert connection.scalar(text("SELECT 1")) == 1
            assert engine.pool.checkedout() == 10
        assert engine.pool.checkedout() == 0
        assert engine.pool.checkedin() == 5
    finally:
        engine.dispose()


@pytest.mark.parametrize("fail", [False, True])
def test_request_cleanup_returns_connection_on_success_and_error(
    tmp_path, monkeypatch, fail
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'request.db'}")
    monkeypatch.setattr(db, "_configured_engine", None)
    db.configure_database_engine(engine)
    request = db.get_db_session()
    try:
        session = next(request)
        assert session.scalar(text("SELECT 1")) == 1
        assert engine.pool.checkedout() == 1
        if fail:
            with pytest.raises(ValueError, match="request failed"):
                request.throw(ValueError("request failed"))
        else:
            with pytest.raises(StopIteration):
                next(request)
        assert engine.pool.checkedout() == 0
    finally:
        request.close()
        engine.dispose()
        db.get_engine.cache_clear()
        db.get_session_factory.cache_clear()
