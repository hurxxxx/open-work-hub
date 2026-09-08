from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import socket
from urllib.parse import urlparse
import uuid

from dotenv import dotenv_values
import httpx
from minio import Minio
from minio.error import S3Error
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url


TEST_RESOURCE_PREFIX = "open-work-hub-api-test-"
TEST_INDEX_PREFIX = "open_work_hub_api_test_"
TEST_DATABASE_PREFIX = "open_work_hub_test_"
_STALE_RESOURCE_TTL_HOURS = 24
_NON_PRODUCTION_PROFILES = {"dev", "development", "local", "test", "testing"}
_NON_PRODUCTION_ACK = "non-production"


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[3]


def _env_files() -> tuple[Path, ...]:
    root = _workspace_root()
    return root / ".env.local", root / ".env"


def _env_values(env_file: Path) -> dict[str, str | None]:
    return dict(dotenv_values(env_file)) if env_file.exists() else {}


def _file_value(name: str, env_files: tuple[Path, ...] | None = None) -> str | None:
    for env_file in env_files or _env_files():
        if not env_file.exists():
            continue
        value = dotenv_values(env_file).get(name)
        if value:
            return str(value)
    return None


def _value(test_name: str, runtime_name: str) -> str:
    for name in (test_name, runtime_name):
        value = os.getenv(name) or _file_value(name)
        if value:
            return value
    raise RuntimeError(f"Shared integration tests require {test_name} or {runtime_name}.")


def _approved_dev_values(name: str) -> set[str]:
    approved: set[str] = set()
    for env_file in _env_files():
        values = _env_values(env_file)
        profile = str(values.get("OPEN_WORK_HUB_ENV_PROFILE") or "").strip().lower()
        value = values.get(name)
        if profile in _NON_PRODUCTION_PROFILES and value:
            approved.add(str(value).rstrip("/"))
    return approved


def _has_non_production_ack() -> bool:
    return os.getenv("OPEN_WORK_HUB_TEST_NON_PRODUCTION_ACK", "") == _NON_PRODUCTION_ACK


def _run_token() -> str:
    run_id = os.getenv(
        "OPEN_WORK_HUB_API_TEST_RUN_ID",
        f"local-{os.getpid()}-{uuid.uuid4().hex}",
    )
    return hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]


TEST_RUN_TOKEN = _run_token()


def stale_resource_cutoff() -> datetime:
    raw_hours = os.getenv("OPEN_WORK_HUB_TEST_RESOURCE_TTL_HOURS", "")
    try:
        hours = int(raw_hours) if raw_hours else _STALE_RESOURCE_TTL_HOURS
    except ValueError as error:
        raise RuntimeError("OPEN_WORK_HUB_TEST_RESOURCE_TTL_HOURS must be an integer.") from error
    if hours < 1:
        raise RuntimeError("OPEN_WORK_HUB_TEST_RESOURCE_TTL_HOURS must be at least 1.")
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _assert_non_production(selected: dict[str, str]) -> None:
    profile = (
        (os.getenv("OPEN_WORK_HUB_ENV_PROFILE") or _file_value("OPEN_WORK_HUB_ENV_PROFILE") or "")
        .strip()
        .lower()
    )
    if profile not in _NON_PRODUCTION_PROFILES:
        raise RuntimeError(
            "Shared integration tests require an explicit non-production environment profile."
        )

    prod_env = _workspace_root().parent / "prod" / ".env"
    prod_values = _env_values(prod_env)
    for runtime_name, value in selected.items():
        prod_value = prod_values.get(runtime_name)
        normalized = value.rstrip("/")
        if prod_value and str(prod_value).rstrip("/") == normalized:
            raise RuntimeError(
                f"Shared integration tests refuse the production {runtime_name} endpoint."
            )
        if normalized not in _approved_dev_values(runtime_name) and not _has_non_production_ack():
            raise RuntimeError(
                f"Unrecognized {runtime_name} test endpoint requires "
                "OPEN_WORK_HUB_TEST_NON_PRODUCTION_ACK=non-production."
            )


def assert_non_production_postgres_dsn(dsn: str) -> None:
    profile = (
        (os.getenv("OPEN_WORK_HUB_ENV_PROFILE") or _file_value("OPEN_WORK_HUB_ENV_PROFILE") or "")
        .strip()
        .lower()
    )
    if profile not in _NON_PRODUCTION_PROFILES:
        raise RuntimeError(
            "PostgreSQL tests require an explicit non-production environment profile."
        )

    selected = make_url(dsn)
    approved = _approved_dev_values("OPEN_WORK_HUB_POSTGRES_DSN")
    if dsn.rstrip("/") not in approved and not _has_non_production_ack():
        raise RuntimeError(
            "Unrecognized PostgreSQL test template requires "
            "OPEN_WORK_HUB_TEST_NON_PRODUCTION_ACK=non-production."
        )

    prod_env = _workspace_root().parent / "prod" / ".env"
    raw_prod_dsn = _env_values(prod_env).get("OPEN_WORK_HUB_POSTGRES_DSN")
    if raw_prod_dsn:
        production = make_url(str(raw_prod_dsn))
        if selected.database == production.database and selected.username == production.username:
            raise RuntimeError("PostgreSQL tests refuse the production database identity.")


def _validate_http_endpoint(name: str, endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError(f"{name} must be an http(s) endpoint.")
    return endpoint.rstrip("/")


def _postgres_admin_dsn(template_dsn: str) -> str:
    return make_url(template_dsn).set(database="postgres").render_as_string(hide_password=False)


def _drop_test_postgres_database(template_dsn: str, database: str) -> None:
    if not database.startswith(TEST_DATABASE_PREFIX):
        raise RuntimeError("Refusing to clean a non-test PostgreSQL database.")
    plain_dsn = _postgres_admin_dsn(template_dsn).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(plain_dsn) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
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
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))


def cleanup_current_postgres_databases(
    template_dsn: str,
    run_token: str = TEST_RUN_TOKEN,
) -> None:
    assert_non_production_postgres_dsn(template_dsn)
    plain_dsn = _postgres_admin_dsn(template_dsn).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    prefix = f"{TEST_DATABASE_PREFIX}{run_token}_"
    with psycopg.connect(plain_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT datname FROM pg_database WHERE datname LIKE %s",
                (f"{prefix}%",),
            )
            databases = [row[0] for row in cursor.fetchall()]
    for database in databases:
        _drop_test_postgres_database(template_dsn, database)


def cleanup_stale_postgres_databases(
    template_dsn: str,
    cutoff: datetime,
) -> None:
    assert_non_production_postgres_dsn(template_dsn)
    plain_dsn = _postgres_admin_dsn(template_dsn).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )
    with psycopg.connect(plain_dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT d.datname, shobj_description(d.oid, 'pg_database')
                FROM pg_database AS d
                WHERE d.datname LIKE 'open_work_hub_test_%'
                  AND NOT EXISTS (
                    SELECT 1 FROM pg_stat_activity AS a
                    WHERE a.datname = d.datname
                  )
                """
            )
            rows = cursor.fetchall()
    marker = "open-work-hub-test-created-at="
    for database, description in rows:
        if not description or not str(description).startswith(marker):
            continue
        try:
            created_at = datetime.fromisoformat(str(description)[len(marker) :])
        except ValueError:
            continue
        if created_at.astimezone(timezone.utc) < cutoff:
            _drop_test_postgres_database(template_dsn, database)


@dataclass(frozen=True)
class MinioTestTarget:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str


@dataclass(frozen=True)
class IntegrationInfra:
    redis_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    opensearch_url: str
    run_token: str = TEST_RUN_TOKEN

    @classmethod
    def load(cls) -> IntegrationInfra:
        redis_url = _value("OPEN_WORK_HUB_TEST_REDIS_URL", "OPEN_WORK_HUB_API_COLLAB_REDIS_URL")
        minio_endpoint = _validate_http_endpoint(
            "MinIO endpoint",
            _value("OPEN_WORK_HUB_TEST_MINIO_ENDPOINT", "OPEN_WORK_HUB_MINIO_ENDPOINT"),
        )
        opensearch_url = _validate_http_endpoint(
            "OpenSearch endpoint",
            _value("OPEN_WORK_HUB_TEST_OPENSEARCH_URL", "OPEN_WORK_HUB_OPENSEARCH_URL"),
        )
        _assert_non_production(
            {
                "OPEN_WORK_HUB_API_COLLAB_REDIS_URL": redis_url,
                "OPEN_WORK_HUB_MINIO_ENDPOINT": minio_endpoint,
                "OPEN_WORK_HUB_OPENSEARCH_URL": opensearch_url,
            }
        )
        parsed_redis = urlparse(redis_url)
        if parsed_redis.scheme not in {"redis", "rediss"} or not parsed_redis.hostname:
            raise RuntimeError("Redis integration URL must be a redis(s) URL.")
        return cls(
            redis_url=redis_url,
            minio_endpoint=minio_endpoint,
            minio_access_key=_value(
                "OPEN_WORK_HUB_TEST_MINIO_ACCESS_KEY", "OPEN_WORK_HUB_MINIO_ACCESS_KEY"
            ),
            minio_secret_key=_value(
                "OPEN_WORK_HUB_TEST_MINIO_SECRET_KEY", "OPEN_WORK_HUB_MINIO_SECRET_KEY"
            ),
            opensearch_url=opensearch_url,
        )

    @property
    def minio_run_prefix(self) -> str:
        return f"{TEST_RESOURCE_PREFIX}{self.run_token}-"

    @property
    def opensearch_run_prefix(self) -> str:
        return f"{TEST_INDEX_PREFIX}{self.run_token}_"

    @property
    def postgres_run_prefix(self) -> str:
        return f"{TEST_DATABASE_PREFIX}{self.run_token}_"

    def _minio_client(self) -> Minio:
        parsed = urlparse(self.minio_endpoint)
        return Minio(
            parsed.netloc,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            secure=parsed.scheme == "https",
        )

    def verify_available(self) -> None:
        redis = urlparse(self.redis_url)
        with socket.create_connection((redis.hostname or "", redis.port or 6379), timeout=3):
            pass
        self._minio_client().list_buckets()
        response = httpx.get(self.opensearch_url, timeout=5)
        response.raise_for_status()

    def new_minio_target(self) -> MinioTestTarget:
        return MinioTestTarget(
            endpoint=self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            bucket=f"{self.minio_run_prefix}{uuid.uuid4().hex[:16]}",
        )

    def new_opensearch_index_prefix(self) -> str:
        return f"{self.opensearch_run_prefix}{uuid.uuid4().hex[:12]}"

    def cleanup_minio_bucket(self, bucket: str) -> None:
        if not bucket.startswith(self.minio_run_prefix):
            raise RuntimeError("Refusing to clean a MinIO bucket outside this test run.")
        client = self._minio_client()
        try:
            if not client.bucket_exists(bucket):
                return
            for item in client.list_objects(bucket, recursive=True):
                client.remove_object(bucket, item.object_name)
            client.remove_bucket(bucket)
        except S3Error as error:
            if error.code != "NoSuchBucket":
                raise
        if client.bucket_exists(bucket):
            raise RuntimeError(f"Failed to remove integration test bucket {bucket}.")

    def _opensearch_indices(self, pattern: str) -> list[dict[str, str]]:
        response = httpx.get(
            f"{self.opensearch_url}/_cat/indices/{pattern}",
            params={"format": "json", "h": "index,creation.date"},
            timeout=10,
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected OpenSearch index inventory response.")
        return payload

    def cleanup_opensearch_indices(self, prefix: str) -> None:
        if not prefix.startswith(self.opensearch_run_prefix):
            raise RuntimeError("Refusing to clean OpenSearch indices outside this test run.")
        pattern = f"{prefix}*"
        response = httpx.delete(
            f"{self.opensearch_url}/{pattern}",
            params={
                "allow_no_indices": "true",
                "expand_wildcards": "all",
                "ignore_unavailable": "true",
            },
            timeout=15,
        )
        if response.status_code not in {200, 404}:
            response.raise_for_status()
        if self._opensearch_indices(pattern):
            raise RuntimeError(f"Failed to remove integration test indices with prefix {prefix}.")

    def _cleanup_current_minio(self) -> None:
        client = self._minio_client()
        for bucket in client.list_buckets():
            if bucket.name.startswith(self.minio_run_prefix):
                self.cleanup_minio_bucket(bucket.name)

    def cleanup_current_run(self) -> None:
        errors: list[Exception] = []
        steps = (
            self._cleanup_current_minio,
            lambda: self.cleanup_opensearch_indices(self.opensearch_run_prefix),
            self.cleanup_current_postgres_databases,
        )
        for step in steps:
            try:
                step()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Shared integration resource cleanup failed.", errors)

    def cleanup_stale_resources(self) -> None:
        cutoff = stale_resource_cutoff()
        errors: list[Exception] = []
        steps = (
            lambda: self._cleanup_stale_minio(cutoff),
            lambda: self._cleanup_stale_opensearch(cutoff),
            lambda: self.cleanup_stale_postgres_databases(cutoff),
        )
        for step in steps:
            try:
                step()
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Stale integration resource cleanup failed.", errors)

    def _cleanup_stale_minio(self, cutoff: datetime) -> None:
        client = self._minio_client()
        for bucket in client.list_buckets():
            created_at = bucket.creation_date
            if (
                bucket.name.startswith(TEST_RESOURCE_PREFIX)
                and created_at is not None
                and created_at.astimezone(timezone.utc) < cutoff
            ):
                self._cleanup_any_test_bucket(bucket.name)

    def _cleanup_stale_opensearch(self, cutoff: datetime) -> None:
        for item in self._opensearch_indices(f"{TEST_INDEX_PREFIX}*"):
            name = str(item.get("index", ""))
            raw_created_at = item.get("creation.date")
            if not name.startswith(TEST_INDEX_PREFIX) or not raw_created_at:
                continue
            created_at = datetime.fromtimestamp(int(raw_created_at) / 1000, tz=timezone.utc)
            if created_at < cutoff:
                self._cleanup_any_test_index(name)

    def _cleanup_any_test_bucket(self, bucket: str) -> None:
        if not bucket.startswith(TEST_RESOURCE_PREFIX):
            raise RuntimeError("Refusing to clean a non-test MinIO bucket.")
        client = self._minio_client()
        try:
            if not client.bucket_exists(bucket):
                return
            for item in client.list_objects(bucket, recursive=True):
                client.remove_object(bucket, item.object_name)
            client.remove_bucket(bucket)
        except S3Error as error:
            if error.code != "NoSuchBucket":
                raise
        if client.bucket_exists(bucket):
            raise RuntimeError(f"Failed to remove stale integration bucket {bucket}.")

    def _cleanup_any_test_index(self, name: str) -> None:
        if not name.startswith(TEST_INDEX_PREFIX):
            raise RuntimeError("Refusing to clean a non-test OpenSearch index.")
        response = httpx.delete(
            f"{self.opensearch_url}/{name}",
            params={"ignore_unavailable": "true"},
            timeout=15,
        )
        if response.status_code not in {200, 404}:
            response.raise_for_status()

    def _postgres_template_dsn(self) -> str | None:
        configured = os.getenv("OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN")
        if configured:
            assert_non_production_postgres_dsn(configured)
            return configured
        root = _workspace_root()
        template = _file_value("OPEN_WORK_HUB_POSTGRES_DSN", (root / ".env", root / ".env.local"))
        if template:
            assert_non_production_postgres_dsn(template)
        return template

    def cleanup_current_postgres_databases(self) -> None:
        template = self._postgres_template_dsn()
        if not template:
            return
        cleanup_current_postgres_databases(template, self.run_token)

    def cleanup_stale_postgres_databases(self, cutoff: datetime) -> None:
        template = self._postgres_template_dsn()
        if not template:
            return
        cleanup_stale_postgres_databases(template, cutoff)


def cleanup_current_run() -> None:
    IntegrationInfra.load().cleanup_current_run()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("cleanup-current", "cleanup-stale"))
    args = parser.parse_args()
    infra = IntegrationInfra.load()
    if args.command == "cleanup-current":
        infra.cleanup_current_run()
    else:
        infra.cleanup_stale_resources()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
