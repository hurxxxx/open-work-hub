from __future__ import annotations

import socket
import subprocess
import time
import uuid

from fastapi.testclient import TestClient
import psycopg
import pytest


POSTGRES_IMAGE = "postgres:18"
REDIS_IMAGE = "redis:7"


def _clear_cache(func) -> None:
    cache_clear = getattr(func, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_postgres(dsn: str, timeout_seconds: int = 45) -> None:
    deadline = time.time() + timeout_seconds
    plain_dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with psycopg.connect(plain_dsn) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("select 1")
                    cursor.fetchone()
            return
        except Exception as error:  # pragma: no cover - exercised in retry loop
            last_error = error
            time.sleep(1)

    raise RuntimeError(f"Timed out waiting for PostgreSQL: {last_error}")


def _wait_for_tcp(host: str, port: int, timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except Exception as error:  # pragma: no cover - exercised in retry loop
            last_error = error
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for TCP service at {host}:{port}: {last_error}")


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    subprocess.run(["docker", "pull", POSTGRES_IMAGE], check=True)
    port = _find_free_port()
    container_name = f"aidoo-api-test-{uuid.uuid4().hex[:10]}"
    dsn = f"postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:{port}/aidoo_test"

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            "-e",
            "POSTGRES_USER=aidoo_test",
            "-e",
            "POSTGRES_PASSWORD=aidoo_test",
            "-e",
            "POSTGRES_DB=aidoo_test",
            "-p",
            f"{port}:5432",
            POSTGRES_IMAGE,
        ],
        check=True,
    )

    try:
        _wait_for_postgres(dsn)
        yield dsn
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], check=False)


@pytest.fixture(scope="session")
def redis_url() -> str:
    subprocess.run(["docker", "pull", REDIS_IMAGE], check=True)
    port = _find_free_port()
    container_name = f"aidoo-api-redis-test-{uuid.uuid4().hex[:10]}"
    url = f"redis://127.0.0.1:{port}/0"

    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{port}:6379",
            REDIS_IMAGE,
        ],
        check=True,
    )

    try:
        _wait_for_tcp("127.0.0.1", port)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], check=False)


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    postgres_dsn: str,
    collab_redis_url: str,
) -> TestClient:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("DOOWON_API_SESSION_TTL_HOURS", "1")
    monkeypatch.setenv("DOOWON_API_ALLOW_DEV_ADMIN_LOGIN", "1")
    monkeypatch.setenv("DOOWON_LLM_HEALTHCHECK_ON_STARTUP", "0")
    monkeypatch.setenv("DOOWON_API_AUTO_MIGRATE", "1")
    monkeypatch.setenv("DOOWON_API_COLLAB_REDIS_URL", collab_redis_url)
    monkeypatch.setenv("DOOWON_REDIS_URL", collab_redis_url)
    # Make tests independent of the developer's local `.env`: pin a dummy
    # external pool key so ``LlmPoolConfig.configured`` is True when a test
    # exercises the external pool via monkeypatched ``get_pool_client``.
    monkeypatch.setenv("DOOWON_LLM_EXTERNAL_API_KEY", "test-external-key")

    from aidoo_api.core.db import Base, get_engine, get_session_factory
    from aidoo_api.core.llm import (
        get_async_pool_client,
        get_pool_client,
    )
    from aidoo_api.core.settings import get_settings
    from aidoo_api.domains.auth import models as auth_models  # noqa: F401
    from aidoo_api.domains.meeting import models as meeting_models  # noqa: F401
    from aidoo_api.domains.pms import models as pms_models  # noqa: F401

    _clear_cache(get_settings)
    _clear_cache(get_async_pool_client)
    _clear_cache(get_pool_client)
    _clear_cache(get_engine)
    _clear_cache(get_session_factory)

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

    from aidoo_api.app import create_app

    app = create_app()
    return TestClient(app)


def _teardown_client_state() -> None:
    from aidoo_api.core.db import Base, get_engine, get_session_factory
    from aidoo_api.core.llm import (
        get_async_pool_client,
        get_pool_client,
    )
    from aidoo_api.core.settings import get_settings

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    engine.dispose()
    _clear_cache(get_settings)
    _clear_cache(get_async_pool_client)
    _clear_cache(get_pool_client)
    _clear_cache(get_engine)
    _clear_cache(get_session_factory)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, postgres_dsn: str, redis_url: str) -> TestClient:
    test_client = _build_client(
        monkeypatch,
        postgres_dsn=postgres_dsn,
        collab_redis_url=redis_url,
    )
    with test_client:
        yield test_client
    _teardown_client_state()


@pytest.fixture
def client_without_collab_relay(monkeypatch: pytest.MonkeyPatch, postgres_dsn: str) -> TestClient:
    test_client = _build_client(
        monkeypatch,
        postgres_dsn=postgres_dsn,
        collab_redis_url="redis://127.0.0.1:1/0",
    )
    with test_client:
        yield test_client
    _teardown_client_state()
