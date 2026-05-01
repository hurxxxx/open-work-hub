from __future__ import annotations

import os
import shlex
import socket
import subprocess
import time
import urllib.request
import uuid

from fastapi.testclient import TestClient
import psycopg
import pytest


POSTGRES_IMAGE = "postgres:18"
REDIS_IMAGE = "redis:7"
MINIO_IMAGE = "minio/minio:latest"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
TEST_POSTGRES_DSN = "postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test"
TEST_LOCAL_LLM_MODEL = "local/current-moe-test-model"


def _clear_cache(func) -> None:
    cache_clear = getattr(func, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _docker_command() -> list[str]:
    configured = os.getenv("AIDOO_TEST_DOCKER_COMMAND")
    if configured:
        return shlex.split(configured)

    if os.getenv("AIDOO_ENV_PROFILE", "local").lower() == "vm":
        direct = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if direct.returncode == 0:
            return ["docker"]

        sudo = subprocess.run(
            ["sudo", "-n", "docker", "version", "--format", "{{.Server.Version}}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if sudo.returncode == 0:
            return ["sudo", "-n", "docker"]

    return ["docker"]


def _docker_uses_host_network() -> bool:
    configured = os.getenv("AIDOO_TEST_DOCKER_NETWORK")
    if configured:
        return configured.lower() == "host"
    return os.getenv("AIDOO_ENV_PROFILE", "local").lower() == "vm"


def _docker_network_args() -> list[str]:
    if _docker_uses_host_network():
        return ["--network", "host"]
    return []


def _docker_publish_args(host_port: int, container_port: int) -> list[str]:
    if _docker_uses_host_network():
        return []
    return ["-p", f"{host_port}:{container_port}"]


def _docker_rm(container_name: str) -> None:
    subprocess.run([*_docker_command(), "rm", "-f", container_name], check=False)


def _ensure_docker_image(image: str) -> None:
    inspected = subprocess.run(
        [*_docker_command(), "image", "inspect", image],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if inspected.returncode == 0:
        return
    subprocess.run([*_docker_command(), "pull", image], check=True)


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


def _wait_for_http_ok(url: str, timeout_seconds: int = 60) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as error:  # pragma: no cover - exercised in retry loop
            last_error = error
            time.sleep(1)
    raise RuntimeError(f"Timed out waiting for HTTP service at {url}: {last_error}")


@pytest.fixture(autouse=True)
def _required_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", TEST_POSTGRES_DSN)


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    _ensure_docker_image(POSTGRES_IMAGE)
    port = _find_free_port()
    container_name = f"aidoo-api-test-{uuid.uuid4().hex[:10]}"
    dsn = f"postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:{port}/aidoo_test"

    subprocess.run(
        [
            *_docker_command(),
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            *_docker_network_args(),
            "-e",
            "POSTGRES_USER=aidoo_test",
            "-e",
            "POSTGRES_PASSWORD=aidoo_test",
            "-e",
            "POSTGRES_DB=aidoo_test",
            *_docker_publish_args(port, 5432),
            POSTGRES_IMAGE,
            *([] if not _docker_uses_host_network() else ["-c", f"port={port}"]),
        ],
        check=True,
    )

    try:
        _wait_for_postgres(dsn)
        yield dsn
    finally:
        _docker_rm(container_name)


@pytest.fixture(scope="session")
def redis_url() -> str:
    _ensure_docker_image(REDIS_IMAGE)
    port = _find_free_port()
    container_name = f"aidoo-api-redis-test-{uuid.uuid4().hex[:10]}"
    url = f"redis://127.0.0.1:{port}/0"

    subprocess.run(
        [
            *_docker_command(),
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            *_docker_network_args(),
            *_docker_publish_args(port, 6379),
            REDIS_IMAGE,
            *([] if not _docker_uses_host_network() else ["redis-server", "--port", str(port)]),
        ],
        check=True,
    )

    try:
        _wait_for_tcp("127.0.0.1", port)
        yield url
    finally:
        _docker_rm(container_name)


@pytest.fixture(scope="session")
def minio_endpoint() -> str:
    _ensure_docker_image(MINIO_IMAGE)
    port = _find_free_port()
    console_port = _find_free_port()
    container_name = f"aidoo-api-minio-test-{uuid.uuid4().hex[:10]}"
    endpoint = f"http://127.0.0.1:{port}"

    subprocess.run(
        [
            *_docker_command(),
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            *_docker_network_args(),
            "-e",
            f"MINIO_ROOT_USER={MINIO_ACCESS_KEY}",
            "-e",
            f"MINIO_ROOT_PASSWORD={MINIO_SECRET_KEY}",
            *_docker_publish_args(port, 9000),
            *_docker_publish_args(console_port, 9001),
            MINIO_IMAGE,
            "server",
            "/data",
            "--address",
            f":{port if _docker_uses_host_network() else 9000}",
            "--console-address",
            f":{console_port if _docker_uses_host_network() else 9001}",
        ],
        check=True,
    )

    try:
        _wait_for_http_ok(f"{endpoint}/minio/health/ready")
        yield endpoint
    finally:
        _docker_rm(container_name)


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    postgres_dsn: str,
    collab_redis_url: str,
    minio_endpoint: str,
) -> TestClient:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("DOOWON_API_SESSION_TTL_HOURS", "1")
    monkeypatch.setenv("DOOWON_API_ALLOW_DEV_ADMIN_LOGIN", "1")
    monkeypatch.setenv("DOOWON_LLM_HEALTHCHECK_ON_STARTUP", "0")
    monkeypatch.setenv("DOOWON_API_AUTO_MIGRATE", "1")
    monkeypatch.setenv("DOOWON_API_COLLAB_REDIS_URL", collab_redis_url)
    monkeypatch.setenv("DOOWON_REDIS_URL", collab_redis_url)
    monkeypatch.setenv("DOOWON_MINIO_ENDPOINT", minio_endpoint)
    monkeypatch.setenv("DOOWON_MINIO_ACCESS_KEY", MINIO_ACCESS_KEY)
    monkeypatch.setenv("DOOWON_MINIO_SECRET_KEY", MINIO_SECRET_KEY)
    monkeypatch.setenv("DOOWON_MINIO_BUCKET", f"aidoo-test-{uuid.uuid4().hex}")
    monkeypatch.setenv("AIDOO_AI_MCP_BRIDGE_ENABLED", "1")
    # Make tests independent of the developer's local `.env`: pin a dummy
    # external pool key so ``LlmPoolConfig.configured`` is True when a test
    # exercises the external pool via monkeypatched ``get_pool_client``.
    monkeypatch.setenv("DOOWON_LLM_EXTERNAL_API_KEY", "test-external-key")
    # Keep tests independent of the developer's local `.env`: fake pool clients
    # are still gated by pool configuration before they are invoked.
    monkeypatch.setenv("DOOWON_LLM_LOCAL_DEFAULT_MODEL", TEST_LOCAL_LLM_MODEL)
    monkeypatch.setenv("DOOWON_LLM_LOCAL_CANONICAL_MODEL", TEST_LOCAL_LLM_MODEL)
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")

    from aidoo_api.core.db import Base, get_engine, get_session_factory
    from aidoo_api.core.llm import (
        get_async_pool_client,
        get_pool_client,
    )
    from aidoo_api.core.settings import get_settings
    from aidoo_api.core.storage import get_minio_client
    from aidoo_api.domains.ai.registry import reset_ai_capability_registry
    from aidoo_api.domains.auth import models as auth_models  # noqa: F401
    from aidoo_api.domains.meeting import models as meeting_models  # noqa: F401
    from aidoo_api.domains.pms import models as pms_models  # noqa: F401
    from aidoo_api.domains.rag.runtime import reset_rag_runtime_caches
    from aidoo_api.domains.whiteboard import models as whiteboard_models  # noqa: F401

    _clear_cache(get_settings)
    _clear_cache(get_async_pool_client)
    _clear_cache(get_pool_client)
    _clear_cache(get_minio_client)
    _clear_cache(get_engine)
    _clear_cache(get_session_factory)
    reset_ai_capability_registry()
    reset_rag_runtime_caches()

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
    from aidoo_api.core.storage import get_minio_client
    from aidoo_api.domains.ai.registry import reset_ai_capability_registry
    from aidoo_api.domains.rag.runtime import reset_rag_runtime_caches

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    engine.dispose()
    _clear_cache(get_settings)
    _clear_cache(get_async_pool_client)
    _clear_cache(get_pool_client)
    _clear_cache(get_minio_client)
    _clear_cache(get_engine)
    _clear_cache(get_session_factory)
    reset_ai_capability_registry()
    reset_rag_runtime_caches()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
    redis_url: str,
    minio_endpoint: str,
) -> TestClient:
    test_client = _build_client(
        monkeypatch,
        postgres_dsn=postgres_dsn,
        collab_redis_url=redis_url,
        minio_endpoint=minio_endpoint,
    )
    with test_client:
        yield test_client
    _teardown_client_state()


@pytest.fixture
def client_without_collab_relay(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
    minio_endpoint: str,
) -> TestClient:
    test_client = _build_client(
        monkeypatch,
        postgres_dsn=postgres_dsn,
        collab_redis_url="redis://127.0.0.1:1/0",
        minio_endpoint=minio_endpoint,
    )
    with test_client:
        yield test_client
    _teardown_client_state()
