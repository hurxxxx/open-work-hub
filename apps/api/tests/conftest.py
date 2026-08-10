from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time
import uuid
from typing import Literal

from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
from psycopg import errors
from psycopg import sql
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from dotenv import dotenv_values

from integration_infra import (
    IntegrationInfra,
    MinioTestTarget,
    TEST_RUN_TOKEN,
    assert_non_production_postgres_dsn,
    cleanup_stale_postgres_databases,
    stale_resource_cutoff,
)

TEST_POSTGRES_DSN = "postgresql+psycopg://open_alm_test:open_alm_test@127.0.0.1:5432/open_alm_test"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "fresh_api_app: tests that require function-scoped FastAPI route composition "
        "or startup settings",
    )


@pytest.fixture(autouse=True)
def _reset_sse_starlette_app_status() -> Iterator[None]:
    """Keep process-global SSE shutdown state scoped to each test event loop."""

    from sse_starlette.sse import AppStatus

    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    try:
        yield
    finally:
        AppStatus.should_exit = False
        AppStatus.should_exit_event = None


@dataclass(frozen=True)
class ApplicationPostgresState:
    dsn: str
    baseline_path: Path
    table_names: frozenset[str]
    head_revision: str


def _clear_cache(func) -> None:
    cache_clear = getattr(func, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def _dispose_cached_engine(engine_factory) -> None:
    cache_info = getattr(engine_factory, "cache_info", None)
    try:
        if cache_info is not None and cache_info().currsize:
            engine_factory().dispose()
    finally:
        _clear_cache(engine_factory)


def _reset_test_database(engine) -> None:
    configured_database = engine.url.database or ""
    if not configured_database.startswith("open_alm_test_"):
        raise RuntimeError(
            f"Refusing to reset non-test database {configured_database!r}."
        )

    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
        database = connection.exec_driver_sql("SELECT current_database()").scalar_one()
        if database != configured_database or not database.startswith("open_alm_test_"):
            raise RuntimeError(f"Refusing to reset non-test database {database!r}.")

        preparer = connection.dialect.identifier_preparer
        schema = preparer.quote_schema("public")
        for table_name in inspect(connection).get_table_names(schema="public"):
            connection.exec_driver_sql(
                f"DROP TABLE IF EXISTS {schema}.{preparer.quote(table_name)} CASCADE"
            )


def _truncate_test_database(engine) -> None:
    """Clear application data while preserving the migrated schema."""
    configured_database = engine.url.database or ""
    if not configured_database.startswith("open_alm_test_"):
        raise RuntimeError(
            f"Refusing to truncate non-test database {configured_database!r}."
        )

    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '30s'")
        database = connection.exec_driver_sql("SELECT current_database()").scalar_one()
        if database != configured_database or not database.startswith("open_alm_test_"):
            raise RuntimeError(f"Refusing to truncate non-test database {database!r}.")

        preparer = connection.dialect.identifier_preparer
        schema = preparer.quote_schema("public")
        table_names = [
            table_name
            for table_name in inspect(connection).get_table_names(schema="public")
            if table_name != "alembic_version"
        ]
        if not table_names:
            return
        tables = ", ".join(
            f"{schema}.{preparer.quote(table_name)}" for table_name in table_names
        )
        connection.exec_driver_sql(
            f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"
        )


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


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[3]


def _env_file_value(name: str) -> str | None:
    if os.getenv(name):
        return os.getenv(name)
    root = _workspace_root()
    for env_file in (root / ".env.local", root / ".env"):
        if not env_file.exists():
            continue
        value = dotenv_values(env_file).get(name)
        if value:
            return str(value)
    return None


def _env_file_value_in_order(name: str, env_files: tuple[Path, ...]) -> str | None:
    for env_file in env_files:
        if not env_file.exists():
            continue
        value = dotenv_values(env_file).get(name)
        if value:
            return str(value)
    return None


def _native_postgres_template_dsn() -> str:
    root = _workspace_root()
    configured = _env_file_value("OPEN_ALM_TEST_POSTGRES_TEMPLATE_DSN")
    if not configured:
        # Nx loads .env.local into the process. That file intentionally points
        # developer apps at published dev infrastructure, while server-side tests
        # must prefer the checkout's native PostgreSQL from .env.
        configured = _env_file_value_in_order(
            "OPEN_ALM_POSTGRES_DSN",
            (root / ".env", root / ".env.local"),
        )
    if not configured:
        raise RuntimeError(
            "Native PostgreSQL tests require OPEN_ALM_POSTGRES_DSN or "
            "OPEN_ALM_TEST_POSTGRES_TEMPLATE_DSN."
        )
    assert_non_production_postgres_dsn(configured)
    return configured


def _dsn_for_database(dsn: str, database: str) -> str:
    return make_url(dsn).set(database=database).render_as_string(hide_password=False)


def _database_from_dsn(dsn: str) -> str:
    database = make_url(dsn).database
    if not database:
        raise RuntimeError("PostgreSQL DSN must include a database name.")
    return database


def _create_native_test_database(template_dsn: str, database: str) -> str:
    admin_dsn = _dsn_for_database(template_dsn, "postgres")
    test_dsn = _dsn_for_database(template_dsn, database)
    with psycopg.connect(admin_dsn.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
            marker = f"open-alm-test-created-at={datetime.now(timezone.utc).isoformat()}"
            cursor.execute(
                sql.SQL("COMMENT ON DATABASE {} IS {}").format(
                    sql.Identifier(database),
                    sql.Literal(marker),
                )
            )
            cursor.execute(
                sql.SQL("ALTER DATABASE {} SET timezone TO 'UTC'").format(
                    sql.Identifier(database)
                )
            )
    _wait_for_postgres(test_dsn)
    _ensure_pgvector_extension(test_dsn)
    _ensure_ai_analysis_reader_role(test_dsn)
    return test_dsn


def _drop_native_test_database(template_dsn: str, database: str) -> None:
    admin_dsn = _dsn_for_database(template_dsn, "postgres")
    with psycopg.connect(admin_dsn.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            deadline = time.monotonic() + 10
            while True:
                cursor.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s
                      AND pid <> pg_backend_pid()
                      AND backend_type = 'client backend'
                    """,
                    (database,),
                )
                try:
                    cursor.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database))
                    )
                    return
                except errors.ObjectInUse:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)


@contextmanager
def _native_test_database(template_dsn: str, *, role: str) -> Iterator[str]:
    database = f"open_alm_test_{TEST_RUN_TOKEN}_{role}_{uuid.uuid4().hex[:8]}"
    dsn = _create_native_test_database(template_dsn, database)
    try:
        yield dsn
    finally:
        _drop_native_test_database(template_dsn, database)


def _migrate_application_test_database(dsn: str) -> None:
    from alembic import command

    from open_alm_api.core.db import _alembic_config
    from open_alm_api.core.settings import get_settings

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", dsn)
        monkeypatch.setenv("OPEN_ALM_API_AUTO_MIGRATE", "0")
        monkeypatch.setenv("OPEN_ALM_LLM_HEALTHCHECK_ON_STARTUP", "0")
        get_settings.cache_clear()
        try:
            command.upgrade(_alembic_config(), "head")
        finally:
            get_settings.cache_clear()


def _initialize_application_test_database(dsn: str) -> None:
    """Add canonical runtime seed data before the worker baseline is captured."""
    from open_alm_api.core.db import get_engine, get_session_factory, init_db
    from open_alm_api.core.settings import get_settings

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", dsn)
        monkeypatch.setenv("OPEN_ALM_API_AUTO_MIGRATE", "0")
        monkeypatch.setenv("OPEN_ALM_MAIL_CREDENTIAL_ENCRYPTION_KEY", "test-mail-credential-key")
        monkeypatch.setenv(
            "OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY",
            "test-ai-model-credential-key",
        )
        _clear_cache(get_session_factory)
        _dispose_cached_engine(get_engine)
        _clear_cache(get_settings)
        try:
            init_db()
        finally:
            _clear_cache(get_session_factory)
            _dispose_cached_engine(get_engine)
            _clear_cache(get_settings)


def _postgres_cli_args(dsn: str) -> list[str]:
    url = make_url(dsn)
    args: list[str] = []
    if url.host:
        args.extend(("--host", url.host))
    if url.port:
        args.extend(("--port", str(url.port)))
    if url.username:
        args.extend(("--username", url.username))
    if url.database:
        args.extend(("--dbname", url.database))
    return args


def _postgres_cli_env(dsn: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PGPASSWORD", None)
    password = make_url(dsn).password
    if password:
        env["PGPASSWORD"] = password
    return env


def _run_postgres_cli(command: list[str], *, dsn: str) -> None:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=_postgres_cli_env(dsn),
            timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"PostgreSQL test baseline command {command[0]!r} timed out after 60 seconds."
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip()[:1000]
        password = make_url(dsn).password
        if password:
            detail = detail.replace(password, "[REDACTED]")
        raise RuntimeError(
            f"PostgreSQL test baseline command {command[0]!r} failed with "
            f"exit code {result.returncode}: {detail}"
        )


def _capture_application_postgres_state(dsn: str, baseline_path: Path) -> ApplicationPostgresState:
    engine = create_engine(dsn)
    try:
        with engine.connect() as connection:
            table_names = frozenset(inspect(connection).get_table_names(schema="public"))
            head_revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
    finally:
        engine.dispose()

    _run_postgres_cli(
        [
            "pg_dump",
            *_postgres_cli_args(dsn),
            "--format=custom",
            "--data-only",
            "--exclude-table-data=public.alembic_version",
            "--file",
            str(baseline_path),
        ],
        dsn=dsn,
    )
    baseline_path.chmod(0o600)
    return ApplicationPostgresState(
        dsn=dsn,
        baseline_path=baseline_path,
        table_names=table_names,
        head_revision=head_revision,
    )


def _restore_application_postgres_state(state: ApplicationPostgresState) -> None:
    engine = create_engine(state.dsn)
    try:
        _truncate_test_database(engine)
    finally:
        engine.dispose()

    _run_postgres_cli(
        [
            "pg_restore",
            *_postgres_cli_args(state.dsn),
            "--data-only",
            "--single-transaction",
            "--exit-on-error",
            str(state.baseline_path),
        ],
        dsn=state.dsn,
    )

    engine = create_engine(state.dsn)
    try:
        with engine.connect() as connection:
            table_names = frozenset(inspect(connection).get_table_names(schema="public"))
            head_revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one()
    finally:
        engine.dispose()
    if table_names != state.table_names:
        raise RuntimeError("Application test database schema changed outside Alembic.")
    if head_revision != state.head_revision:
        raise RuntimeError(
            "Application test database Alembic revision changed during a client test."
        )


def _ensure_pgvector_extension(dsn: str) -> None:
    plain_dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with psycopg.connect(plain_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            connection.commit()
    except errors.InsufficientPrivilege:
        _ensure_pgvector_extension_with_native_superuser(dsn)


def _ensure_pgvector_extension_with_native_superuser(dsn: str) -> None:
    database = _database_from_dsn(dsn)
    url = make_url(dsn)
    host = url.host or ""
    if host not in {"", "localhost", "127.0.0.1", "::1"}:
        raise RuntimeError(
            "The configured PostgreSQL user cannot create the pgvector extension, "
            "and native postgres fallback only supports local PostgreSQL."
        )

    result = subprocess.run(
        [
            "sudo",
            "-n",
            "-u",
            "postgres",
            "psql",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
            "-c",
            "CREATE EXTENSION IF NOT EXISTS vector",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip()
        raise RuntimeError(
            "Failed to enable pgvector in the native PostgreSQL test database. "
            "Install/enable the native vector extension for this database; "
            f"psql exited with {result.returncode}: {detail}"
        )


def _ensure_ai_analysis_reader_role(dsn: str) -> None:
    url = make_url(dsn)
    app_role = url.username
    database = url.database
    if not app_role or not database:
        raise RuntimeError("Native PostgreSQL test DSN requires user and database.")
    plain_dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    try:
        with psycopg.connect(plain_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_has_role(current_user, 'open_alm_analysis_reader', 'MEMBER')"
                )
                if cursor.fetchone() == (True,):
                    return
    except errors.UndefinedObject:
        pass

    result = subprocess.run(
        [
            "sudo",
            "-n",
            "-u",
            "postgres",
            "psql",
            "-d",
            database,
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            f"app_role={app_role}",
            "-q",
            "-f",
            str(_workspace_root() / "scripts" / "provision-ai-analysis-reader.sql"),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to provision the native AI analysis reader role; "
            f"psql exited with {result.returncode}: {result.stderr.strip()}"
        )


@pytest.fixture(autouse=True)
def _required_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from open_alm_api.core.settings import get_settings

    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", TEST_POSTGRES_DSN)
    monkeypatch.setenv("OPEN_ALM_MAIL_CREDENTIAL_ENCRYPTION_KEY", "test-mail-credential-key")
    monkeypatch.setenv(
        "OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY",
        "test-ai-model-credential-key",
    )
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture(scope="session")
def postgres_template_dsn() -> str:
    template_dsn = _native_postgres_template_dsn()
    cleanup_stale_postgres_databases(template_dsn, stale_resource_cutoff())
    return template_dsn


@pytest.fixture
def postgres_dsn(postgres_template_dsn: str) -> Iterator[str]:
    """Test-local raw database for migration and direct PostgreSQL tests."""
    with _native_test_database(postgres_template_dsn, role="raw") as dsn:
        yield dsn


@pytest.fixture(scope="session")
def application_postgres_state(
    postgres_template_dsn: str,
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[ApplicationPostgresState]:
    """Worker-local migrated database plus its application-ready seed baseline."""
    with _native_test_database(postgres_template_dsn, role="app") as dsn:
        _migrate_application_test_database(dsn)
        _initialize_application_test_database(dsn)
        baseline_path = tmp_path_factory.mktemp("postgres-baseline") / "application.dump"
        yield _capture_application_postgres_state(dsn, baseline_path)


@pytest.fixture
def application_postgres_dsn(
    application_postgres_state: ApplicationPostgresState,
) -> str:
    """Clean application data without replaying the Alembic revision chain."""
    _restore_application_postgres_state(application_postgres_state)
    return application_postgres_state.dsn


@pytest.fixture(scope="session")
def integration_infra() -> IntegrationInfra:
    infra = IntegrationInfra.load()
    infra.verify_available()
    infra.cleanup_stale_resources()
    try:
        yield infra
    finally:
        infra.cleanup_current_run()


@pytest.fixture(scope="session")
def redis_url(integration_infra: IntegrationInfra) -> str:
    return integration_infra.redis_url


@pytest.fixture
def minio_target(
    integration_infra: IntegrationInfra,
) -> MinioTestTarget:
    target = integration_infra.new_minio_target()
    try:
        yield target
    finally:
        integration_infra.cleanup_minio_bucket(target.bucket)


class _InMemoryStorageObject:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def stream(self, chunk_size: int):
        for offset in range(0, len(self._data), chunk_size):
            yield self._data[offset : offset + chunk_size]

    def close(self) -> None:
        return None

    def release_conn(self) -> None:
        return None


class _InMemoryObjectStorageClient:
    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data,
        *,
        length: int,
        content_type: str,
    ) -> None:
        del content_type
        self._objects[(bucket_name, object_name)] = data.read(length)

    def get_object(self, bucket_name: str, object_name: str) -> _InMemoryStorageObject:
        return _InMemoryStorageObject(self._objects[(bucket_name, object_name)])

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self._objects.pop((bucket_name, object_name), None)


@pytest.fixture
def in_memory_object_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    from open_alm_api.domains.diagrams import storage as diagram_storage
    from open_alm_api.domains.dm import attachment_storage
    from open_alm_api.domains.files import storage_adapter

    client = _InMemoryObjectStorageClient()
    monkeypatch.setattr(storage_adapter, "get_minio_client", lambda: client)
    monkeypatch.setattr(attachment_storage, "get_minio_client", lambda: client)
    monkeypatch.setattr(diagram_storage, "get_minio_client", lambda: client)
    monkeypatch.setattr(diagram_storage, "ensure_bucket", lambda: None)


def _configure_test_application_environment(
    monkeypatch: pytest.MonkeyPatch,
    *,
    postgres_dsn: str,
    minio_endpoint: str = "http://127.0.0.1:1",
    minio_access_key: str = "unused",
    minio_secret_key: str = "unused",
    minio_bucket: str = "open-alm-test-unused",
) -> None:
    monkeypatch.setenv("OPEN_ALM_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("OPEN_ALM_API_SESSION_TTL_HOURS", "1")
    monkeypatch.setenv("OPEN_ALM_API_ALLOW_DEV_ADMIN_LOGIN", "1")
    monkeypatch.setenv("OPEN_ALM_LLM_HEALTHCHECK_ON_STARTUP", "0")
    monkeypatch.setenv("OPEN_ALM_OPF_HEALTHCHECK_ON_STARTUP", "0")
    monkeypatch.setenv("OPEN_ALM_OPF_REQUIRED", "0")
    monkeypatch.setenv("OPEN_ALM_OPF_SERVICE_BASE_URL", "")
    monkeypatch.setenv("OPEN_ALM_API_AUTO_MIGRATE", "0")
    monkeypatch.setenv("OPEN_ALM_API_COLLAB_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("OPEN_ALM_API_REALTIME_REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("OPEN_ALM_MINIO_ENDPOINT", minio_endpoint)
    monkeypatch.setenv("OPEN_ALM_MINIO_ACCESS_KEY", minio_access_key)
    monkeypatch.setenv("OPEN_ALM_MINIO_SECRET_KEY", minio_secret_key)
    monkeypatch.setenv("OPEN_ALM_MINIO_BUCKET", minio_bucket)
    monkeypatch.setenv("OPEN_ALM_MAIL_CREDENTIAL_ENCRYPTION_KEY", "test-mail-credential-key")
    monkeypatch.setenv(
        "OPEN_ALM_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY",
        "test-ai-model-credential-key",
    )
    monkeypatch.setenv("OPEN_ALM_AI_MCP_BRIDGE_ENABLED", "1")
    # Keep tests independent of the developer's local `.env`: fake pool clients
    # are still gated by pool configuration before they are invoked.
    monkeypatch.setenv("OPEN_ALM_LLM_LOCAL_PROVIDER", "mlx-lm")
    monkeypatch.setenv("OPEN_ALM_RAG_ENABLED", "1")
    monkeypatch.setenv("OPEN_ALM_RAG_VECTOR_INDEX_PROVIDER", "fake")
    monkeypatch.setenv("OPEN_ALM_RAG_EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("OPEN_ALM_RAG_RERANK_PROVIDER", "fake")
    monkeypatch.setenv("OPEN_ALM_RAG_OCR_PROVIDER", "fake")
    monkeypatch.setenv("OPEN_ALM_IMAGE_ENABLED", "0")


def _prepare_client_process_state() -> None:
    from open_alm_api.core.db import get_engine, get_session_factory
    from open_alm_api.core.llm import (
        get_async_pool_client,
        get_pool_client,
    )
    from open_alm_api.core.model_registry import import_all_models
    from open_alm_api.core.settings import get_settings
    from open_alm_api.core.storage import get_minio_client
    from open_alm_api.domains.ai.registry import reset_ai_capability_registry
    from open_alm_api.domains.rag.runtime import reset_rag_runtime_caches

    import_all_models()

    _clear_cache(get_session_factory)
    _dispose_cached_engine(get_engine)
    _clear_cache(get_settings)
    _clear_cache(get_async_pool_client)
    _clear_cache(get_pool_client)
    _clear_cache(get_minio_client)
    reset_ai_capability_registry()
    reset_rag_runtime_caches()


def _build_test_application(
    monkeypatch: pytest.MonkeyPatch,
    *,
    postgres_dsn: str,
    runtime_mode: Literal["in_process", "minio", "unavailable"] = "in_process",
    minio_endpoint: str = "http://127.0.0.1:1",
    minio_access_key: str = "unused",
    minio_secret_key: str = "unused",
    minio_bucket: str = "open-alm-test-unused",
) -> FastAPI:
    _configure_test_application_environment(
        monkeypatch,
        postgres_dsn=postgres_dsn,
        minio_endpoint=minio_endpoint,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
        minio_bucket=minio_bucket,
    )
    _prepare_client_process_state()

    from open_alm_api.app import create_app
    from open_alm_api.core.storage import ensure_bucket
    from open_alm_api.external_runtime import (
        InProcessApiExternalRuntime,
        UnavailableCollaborationApiExternalRuntime,
    )

    if runtime_mode == "minio":
        external_runtime = InProcessApiExternalRuntime(storage_prepare=ensure_bucket)
    elif runtime_mode == "unavailable":
        external_runtime = UnavailableCollaborationApiExternalRuntime()
    else:
        external_runtime = InProcessApiExternalRuntime()

    return create_app(external_runtime=external_runtime)


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    postgres_dsn: str,
    runtime_mode: Literal["in_process", "minio", "unavailable"] = "in_process",
    minio_endpoint: str = "http://127.0.0.1:1",
    minio_access_key: str = "unused",
    minio_secret_key: str = "unused",
    minio_bucket: str = "open-alm-test-unused",
) -> TestClient:
    return TestClient(
        _build_test_application(
            monkeypatch,
            postgres_dsn=postgres_dsn,
            runtime_mode=runtime_mode,
            minio_endpoint=minio_endpoint,
            minio_access_key=minio_access_key,
            minio_secret_key=minio_secret_key,
            minio_bucket=minio_bucket,
        )
    )


def _teardown_client_state() -> None:
    from open_alm_api.core.db import get_engine, get_session_factory
    from open_alm_api.core.llm import (
        get_async_pool_client,
        get_pool_client,
    )
    from open_alm_api.core.settings import get_settings
    from open_alm_api.core.storage import get_minio_client
    from open_alm_api.domains.ai.registry import reset_ai_capability_registry
    from open_alm_api.domains.rag.runtime import reset_rag_runtime_caches

    try:
        _dispose_cached_engine(get_engine)
    finally:
        _clear_cache(get_settings)
        _clear_cache(get_async_pool_client)
        _clear_cache(get_pool_client)
        _clear_cache(get_minio_client)
        _clear_cache(get_session_factory)
        reset_ai_capability_registry()
        reset_rag_runtime_caches()


def _assert_reused_application_idle(app: FastAPI) -> None:
    active_state_names = [
        state_name
        for state_name in (
            "app_realtime",
            "docs_collab",
            "whiteboard_collab",
            "loop_lag_watchdog",
        )
        if getattr(app.state, state_name, None) is not None
    ]
    if active_state_names:
        raise RuntimeError(
            "Reusable application retained active lifespan state: "
            + ", ".join(active_state_names)
        )


@pytest.fixture(scope="session")
def application_test_app(
    application_postgres_state: ApplicationPostgresState,
) -> Iterator[FastAPI]:
    """Worker-local route composition reused with a fresh lifespan per test."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        try:
            app = _build_test_application(
                monkeypatch,
                postgres_dsn=application_postgres_state.dsn,
            )
            _assert_reused_application_idle(app)
            yield app
        finally:
            if "app" in locals():
                app.dependency_overrides.clear()
                _assert_reused_application_idle(app)
            _teardown_client_state()


@pytest.fixture
def client(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
    application_postgres_dsn: str,
    application_test_app: FastAPI,
) -> TestClient:
    integration = request.node.get_closest_marker("external_integration")
    uses_minio = integration is not None and "minio" in integration.args
    uses_fresh_app = request.node.get_closest_marker("fresh_api_app") is not None
    minio = request.getfixturevalue("minio_target") if uses_minio else None
    reused_app = not uses_minio and not uses_fresh_app
    try:
        if reused_app:
            _configure_test_application_environment(
                monkeypatch,
                postgres_dsn=application_postgres_dsn,
            )
            _prepare_client_process_state()
            from open_alm_api.core.settings import get_settings
            from open_alm_api.platform_extensions import initialize_platform_extensions

            initialize_platform_extensions(get_settings())
            application_test_app.dependency_overrides.clear()
            _assert_reused_application_idle(application_test_app)
            test_client = TestClient(application_test_app)
        else:
            test_client = _build_client(
                monkeypatch,
                postgres_dsn=application_postgres_dsn,
                runtime_mode="minio" if uses_minio else "in_process",
                minio_endpoint=minio.endpoint if minio else "http://127.0.0.1:1",
                minio_access_key=minio.access_key if minio else "unused",
                minio_secret_key=minio.secret_key if minio else "unused",
                minio_bucket=minio.bucket if minio else "open-alm-test-unused",
            )
        with test_client:
            yield test_client
    finally:
        try:
            if reused_app:
                application_test_app.dependency_overrides.clear()
                _assert_reused_application_idle(application_test_app)
        finally:
            _teardown_client_state()


@pytest.fixture
def configured_local_llm_control_plane(client: TestClient) -> None:
    """Select the explicit local test model for suites that exercise LLM execution."""

    del client
    from open_alm_api.core.db import get_session_factory
    from open_alm_api.core.settings import get_settings
    from open_alm_api.domains.ai.model_settings_models import (
        AiModelCatalogEntry,
        AiModelProviderConfig,
    )

    model_id = "local-current-moe-test-model"
    model_key = "local/current-moe-test-model"
    with get_session_factory()() as db:
        provider = db.get(AiModelProviderConfig, "local")
        assert provider is not None
        model = db.get(AiModelCatalogEntry, model_id)
        if model is None:
            model = AiModelCatalogEntry(
                id=model_id,
                provider_id="local",
                model_key=model_key,
                display_name=model_key,
                capabilities_json=["chat", "tool_calling", "vision"],
                source="manual",
                discovery_status="active",
                enabled=True,
                version=1,
            )
            db.add(model)
        provider.enabled = True
        provider.endpoint_url = get_settings().llm_local_base_url
        provider.default_model_id = model.id
        db.commit()


@pytest.fixture
def client_without_collab_relay(
    monkeypatch: pytest.MonkeyPatch,
    application_postgres_dsn: str,
) -> TestClient:
    try:
        test_client = _build_client(
            monkeypatch,
            postgres_dsn=application_postgres_dsn,
            runtime_mode="unavailable",
        )
        with test_client:
            yield test_client
    finally:
        _teardown_client_state()
