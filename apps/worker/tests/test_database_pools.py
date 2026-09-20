from __future__ import annotations

import importlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import TimeoutError
from sqlalchemy.pool import QueuePool


def test_task_sessions_reuse_one_engine(tmp_path, monkeypatch) -> None:
    """Periodic tasks must not accumulate independent pools in one child."""
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", f"sqlite:///{tmp_path / 'tasks.db'}")
    monkeypatch.setenv("OPEN_WORK_HUB_WORKER_QUEUE_GROUP", "default")
    settings = importlib.import_module("open_work_hub_worker.settings")
    settings.get_settings.cache_clear()
    runtime = importlib.import_module("open_work_hub_worker.runtime")
    mail = importlib.import_module("open_work_hub_worker.tasks.mail")
    search = importlib.import_module("open_work_hub_worker.tasks.search_index")
    media = importlib.import_module("open_work_hub_worker.tasks.media")
    core_db = importlib.import_module("open_work_hub_api.core.db")
    monkeypatch.setattr(core_db, "_configured_engine", None)
    runtime.configure_database()
    factories = (
        runtime.db_session,
        lambda: mail._session_factory()(),
        search._db_session,
        media._get_db_session,
        lambda: core_db.get_session_factory()(),
    )
    engines = set()
    try:
        for _ in range(10):
            for factory in factories:
                with factory() as session:
                    engines.add(session.get_bind())
                    assert session.scalar(text("SELECT 1")) == 1
        assert len(engines) == 1
        assert all(engine.pool.checkedout() == 0 for engine in engines)
    finally:
        for engine in engines:
            engine.dispose()
        runtime.postgres_engine.cache_clear()
        runtime.db_session_factory.cache_clear()
        mail._session_factory.cache_clear()
        settings.get_settings.cache_clear()
        core_db.get_engine.cache_clear()
        core_db.get_session_factory.cache_clear()


def test_worker_pool_returns_overflow_connections(tmp_path, monkeypatch) -> None:
    """Exercise the configured pool with real connections, including rollback."""
    runtime = importlib.import_module("open_work_hub_worker.runtime")
    settings_module = importlib.import_module("open_work_hub_worker.settings")
    settings = settings_module.Settings(
        _env_file=None,
        OPEN_WORK_HUB_POSTGRES_DSN="postgresql+psycopg://unused/test",
        OPEN_WORK_HUB_WORKER_DB_POOL_TIMEOUT=1,
    )
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    engines = []

    def local_engine(_dsn, **options):
        options.pop("connect_args", None)
        engine = create_engine(f"sqlite:///{tmp_path / 'pool.db'}", poolclass=QueuePool, **options)
        engines.append(engine)
        return engine

    monkeypatch.setattr(runtime, "create_engine", local_engine)
    runtime.postgres_engine.cache_clear()
    runtime.db_session_factory.cache_clear()
    sessions = []
    try:
        for _ in range(3):
            session = runtime.db_session()
            sessions.append(session)
            assert session.scalar(text("SELECT 1")) == 1
        engine = runtime.postgres_engine()
        with pytest.raises(TimeoutError):
            with engine.connect():
                pass
    finally:
        for session in sessions:
            session.close()
        try:
            if engines:
                assert engines[0].pool.checkedout() == 0
                assert engines[0].pool.checkedin() == 1
        finally:
            for engine in engines:
                engine.dispose()
            runtime.postgres_engine.cache_clear()
            runtime.db_session_factory.cache_clear()


def test_worker_bootstrap_and_fork_share_the_domain_engine(tmp_path, monkeypatch) -> None:
    runtime = importlib.import_module("open_work_hub_worker.runtime")
    celery_module = importlib.import_module("open_work_hub_worker.celery_app")
    core_db = importlib.import_module("open_work_hub_api.core.db")
    engine = create_engine(f"sqlite:///{tmp_path / 'fork.db'}")
    monkeypatch.setattr(runtime, "postgres_engine", lambda: engine)
    monkeypatch.setattr(core_db, "_configured_engine", None)
    inherited_connection = None
    try:
        celery_module._configure_database_pools()
        inherited_connection = engine.connect()
        inherited_pool = engine.pool
        inherited_factory = core_db.get_session_factory()
        celery_module._reset_database_pool_after_fork()
        assert engine.pool is not inherited_pool
        assert core_db.get_engine() is engine
        assert core_db.get_session_factory() is inherited_factory
        assert inherited_connection.scalar(text("SELECT 1")) == 1
        with inherited_factory() as session:
            assert session.get_bind() is engine
            assert session.scalar(text("SELECT 1")) == 1
    finally:
        if inherited_connection is not None:
            inherited_connection.close()
            inherited_pool.dispose()
        engine.dispose()
        core_db.get_engine.cache_clear()
        core_db.get_session_factory.cache_clear()


@pytest.mark.parametrize("task_name", ["mail", "search_index", "media"])
@pytest.mark.parametrize("fail", [False, True])
def test_empty_periodic_tasks_return_connections(tmp_path, monkeypatch, task_name, fail) -> None:
    """Real task finally blocks must release connections even after a failed poll."""
    from sqlalchemy.orm import sessionmaker

    module = importlib.import_module(f"open_work_hub_worker.tasks.{task_name}")
    engine = create_engine(f"sqlite:///{tmp_path / 'maintenance.db'}", pool_size=1)
    factory = sessionmaker(bind=engine)

    def poll(session, **_kwargs):
        assert session.scalar(text("SELECT 1")) == 1
        if fail:
            raise ValueError("poll failed")
        return [] if task_name == "search_index" else 0

    if task_name == "mail":
        monkeypatch.setattr(module, "_session_factory", lambda: factory)
        monkeypatch.setattr(module, "publish_due_mail_sync_jobs", poll)
        task = module.dispatch_due_sync_jobs
    elif task_name == "search_index":
        monkeypatch.setattr(module, "_db_session", factory)
        monkeypatch.setattr(module, "_due_pending_search_job_ids", poll)
        task = module.republish_pending_index_jobs
    else:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE media_files (id TEXT, storage_key TEXT, "
                "resource_type TEXT, created_at TIMESTAMP)"
            )
        monkeypatch.setattr(module, "_get_db_session", factory)

        def storage_client():
            if fail:
                raise ValueError("poll failed")
            return object()

        monkeypatch.setattr(module, "_get_minio_client", storage_client)
        task = module.cleanup_orphan_media

    try:
        for _ in range(5):
            if fail:
                with pytest.raises(ValueError, match="poll failed"):
                    task.run()
            else:
                task.run()
            assert engine.pool.checkedout() == 0
            assert engine.pool.checkedin() == 1
    finally:
        engine.dispose()
