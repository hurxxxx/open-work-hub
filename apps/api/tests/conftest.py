from __future__ import annotations

import socket
import subprocess
import time
import uuid

from fastapi.testclient import TestClient
import psycopg
import pytest


POSTGRES_IMAGE = "postgres:18"


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


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, postgres_dsn: str) -> TestClient:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("DOOWON_API_SESSION_TTL_HOURS", "1")

    from aidoo_api.core.db import Base, get_engine, get_session_factory
    from aidoo_api.core.settings import get_settings
    from aidoo_api.domains.auth import models as auth_models  # noqa: F401
    from aidoo_api.domains.pms import models as pms_models  # noqa: F401

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)

    from aidoo_api.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
