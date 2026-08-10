from __future__ import annotations

import inspect
from types import SimpleNamespace

import conftest
import integration_infra as infra_module
from integration_infra import IntegrationInfra
import pytest
from sqlalchemy import create_engine, inspect as sqlalchemy_inspect, text


def _infra() -> IntegrationInfra:
    return IntegrationInfra(
        redis_url="redis://127.0.0.1:56380/0",
        minio_endpoint="http://127.0.0.1:59010",
        minio_access_key="test-access",
        minio_secret_key="test-secret",
        opensearch_url="http://127.0.0.1:59210",
        run_token="abc123",
    )


def test_default_client_fixture_has_no_external_infra_dependencies() -> None:
    parameters = inspect.signature(conftest.client).parameters

    assert "redis_url" not in parameters
    assert "integration_infra" not in parameters
    assert "minio_target" not in parameters
    assert "postgres_dsn" not in parameters
    assert "application_postgres_dsn" in parameters


def test_default_client_reuses_worker_scoped_application_composition() -> None:
    assert hasattr(conftest, "application_test_app")
    fixture = conftest.application_test_app._fixture_function_marker
    assert fixture.scope == "session"
    assert "application_test_app" in inspect.signature(conftest.client).parameters


def test_database_reset_drops_unknown_foreign_keys_and_preserves_extensions(
    postgres_dsn: str,
) -> None:
    conftest._ensure_pgvector_extension(postgres_dsn)
    engine = create_engine(postgres_dsn)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE test_harness_parent (id integer PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE test_harness_migration_only_child (
                    id integer PRIMARY KEY,
                    parent_id integer REFERENCES test_harness_parent(id)
                )
                """
            )

        conftest._reset_test_database(engine)

        with engine.connect() as connection:
            assert sqlalchemy_inspect(connection).get_table_names() == []
            assert connection.scalar(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            ) == "vector"
    finally:
        conftest._reset_test_database(engine)
        engine.dispose()


def test_database_reset_refuses_non_test_database() -> None:
    engine = create_engine(
        "postgresql+psycopg://test:test@127.0.0.1:5432/application"
    )
    try:
        with pytest.raises(RuntimeError, match="Refusing to reset non-test database"):
            conftest._reset_test_database(engine)
    finally:
        engine.dispose()


def test_database_data_reset_preserves_schema_and_migration_revision(
    postgres_dsn: str,
) -> None:
    engine = create_engine(postgres_dsn)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "INSERT INTO alembic_version (version_num) VALUES ('test-head')"
            )
            connection.exec_driver_sql(
                "CREATE TABLE test_harness_parent "
                "(id serial PRIMARY KEY, value text NOT NULL)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE test_harness_child "
                "(id serial PRIMARY KEY, parent_id integer REFERENCES test_harness_parent(id))"
            )
            connection.exec_driver_sql(
                "INSERT INTO test_harness_parent (value) VALUES ('before-reset')"
            )
            connection.exec_driver_sql(
                "INSERT INTO test_harness_child (parent_id) VALUES (1)"
            )

        conftest._truncate_test_database(engine)

        with engine.connect() as connection:
            table_names = set(sqlalchemy_inspect(connection).get_table_names())
            assert {
                "alembic_version",
                "test_harness_parent",
                "test_harness_child",
            } <= table_names
            assert connection.scalar(text("SELECT COUNT(*) FROM test_harness_parent")) == 0
            assert connection.scalar(text("SELECT COUNT(*) FROM test_harness_child")) == 0
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "test-head"
            next_id = connection.scalar(
                text("INSERT INTO test_harness_parent (value) VALUES ('after-reset') RETURNING id")
            )
            assert next_id == 1
    finally:
        conftest._reset_test_database(engine)
        engine.dispose()


def test_database_data_reset_refuses_non_test_database() -> None:
    engine = create_engine(
        "postgresql+psycopg://test:test@127.0.0.1:5432/application"
    )
    try:
        with pytest.raises(RuntimeError, match="Refusing to truncate non-test database"):
            conftest._truncate_test_database(engine)
    finally:
        engine.dispose()


def test_application_database_reset_restores_migration_owned_seed(
    application_postgres_state: conftest.ApplicationPostgresState,
) -> None:
    conftest._restore_application_postgres_state(application_postgres_state)
    engine = create_engine(application_postgres_state.dsn)
    try:
        with engine.begin() as connection:
            expected_rows = {
                table_name: connection.scalar(
                    text(
                        f"SELECT COALESCE(jsonb_agg(to_jsonb(row_data) ORDER BY id), "
                        f"'[]'::jsonb)::text FROM {table_name} AS row_data"
                    )
                )
                for table_name in (
                    "release_notes",
                    "lawsearch_items",
                    "ai_model_catalog_entries",
                    "community_channels",
                )
            }
            assert expected_rows["ai_model_catalog_entries"] == "[]"
            assert all(
                rows != "[]"
                for table_name, rows in expected_rows.items()
                if table_name != "ai_model_catalog_entries"
            )
            connection.execute(text("DELETE FROM release_notes"))
            connection.execute(text("DELETE FROM lawsearch_items"))
            connection.execute(
                text("UPDATE community_channels SET name = 'corrupted'")
            )

        conftest._restore_application_postgres_state(application_postgres_state)

        with engine.connect() as connection:
            restored_rows = {
                table_name: connection.scalar(
                    text(
                        f"SELECT COALESCE(jsonb_agg(to_jsonb(row_data) ORDER BY id), "
                        f"'[]'::jsonb)::text FROM {table_name} AS row_data"
                    )
                )
                for table_name in expected_rows
            }
        assert restored_rows == expected_rows
    finally:
        engine.dispose()


def test_test_resource_names_are_scoped_to_the_run() -> None:
    infra = _infra()

    minio_target = infra.new_minio_target()
    index_prefix = infra.new_opensearch_index_prefix()

    assert minio_target.bucket.startswith("open-alm-api-test-abc123-")
    assert index_prefix.startswith("open_alm_api_test_abc123_")
    assert infra.postgres_run_prefix == "open_alm_test_abc123_"


def test_cleanup_refuses_resources_outside_the_current_run() -> None:
    infra = _infra()

    with pytest.raises(RuntimeError, match="outside this test run"):
        infra.cleanup_minio_bucket("open-alm-dev")
    with pytest.raises(RuntimeError, match="outside this test run"):
        infra.cleanup_opensearch_indices("open-alm-dev")


def test_opensearch_cleanup_deletes_and_verifies_run_prefix(monkeypatch) -> None:
    infra = _infra()
    calls: list[tuple[str, str]] = []

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[object]:
            return []

    monkeypatch.setattr(
        infra_module.httpx,
        "delete",
        lambda url, **_kwargs: calls.append(("delete", url)) or Response(),
    )
    monkeypatch.setattr(
        infra_module.httpx,
        "get",
        lambda url, **_kwargs: calls.append(("get", url)) or Response(),
    )

    infra.cleanup_opensearch_indices("open_alm_api_test_abc123_case")

    assert calls == [
        ("delete", "http://127.0.0.1:59210/open_alm_api_test_abc123_case*"),
        (
            "get",
            "http://127.0.0.1:59210/_cat/indices/open_alm_api_test_abc123_case*",
        ),
    ]


def test_load_refuses_production_profile(monkeypatch) -> None:
    values = {
        "OPEN_ALM_TEST_REDIS_URL": "redis://127.0.0.1:56380/0",
        "OPEN_ALM_TEST_MINIO_ENDPOINT": "http://127.0.0.1:59010",
        "OPEN_ALM_TEST_MINIO_ACCESS_KEY": "test-access",
        "OPEN_ALM_TEST_MINIO_SECRET_KEY": "test-secret",
        "OPEN_ALM_TEST_OPENSEARCH_URL": "http://127.0.0.1:59210",
        "OPEN_ALM_ENV_PROFILE": "production",
    }
    monkeypatch.setattr(
        infra_module.os,
        "getenv",
        lambda name, default=None: values.get(name, default),
    )
    monkeypatch.setattr(infra_module, "_file_value", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="production environment"):
        IntegrationInfra.load()


def test_load_refuses_missing_environment_profile(monkeypatch) -> None:
    values = {
        "OPEN_ALM_TEST_REDIS_URL": "redis://127.0.0.1:56380/0",
        "OPEN_ALM_TEST_MINIO_ENDPOINT": "http://127.0.0.1:59010",
        "OPEN_ALM_TEST_MINIO_ACCESS_KEY": "test-access",
        "OPEN_ALM_TEST_MINIO_SECRET_KEY": "test-secret",
        "OPEN_ALM_TEST_OPENSEARCH_URL": "http://127.0.0.1:59210",
    }
    monkeypatch.setattr(
        infra_module.os,
        "getenv",
        lambda name, default=None: values.get(name, default),
    )
    monkeypatch.setattr(infra_module, "_file_value", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="explicit non-production"):
        IntegrationInfra.load()


def test_postgres_refuses_missing_environment_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        infra_module.os,
        "getenv",
        lambda _name, default=None: default,
    )
    monkeypatch.setattr(infra_module, "_file_value", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="explicit non-production"):
        infra_module.assert_non_production_postgres_dsn(
            "postgresql+psycopg://user:password@127.0.0.1/test"
        )


def test_minio_cleanup_verifies_bucket_absence(monkeypatch) -> None:
    infra = _infra()
    states = iter((True, False))
    removed: list[str] = []
    fake_client = SimpleNamespace(
        bucket_exists=lambda _bucket: next(states),
        list_objects=lambda _bucket, recursive: [SimpleNamespace(object_name="item")],
        remove_object=lambda bucket, item: removed.append(f"{bucket}/{item}"),
        remove_bucket=lambda bucket: removed.append(bucket),
    )
    monkeypatch.setattr(
        IntegrationInfra,
        "_minio_client",
        lambda _self: fake_client,
    )

    bucket = "open-alm-api-test-abc123-case"
    infra.cleanup_minio_bucket(bucket)

    assert removed == [f"{bucket}/item", bucket]


def test_unrecognized_test_endpoint_requires_explicit_non_production_ack(
    monkeypatch,
) -> None:
    values = {
        "OPEN_ALM_TEST_REDIS_URL": "redis://production-alias.invalid:6379/0",
        "OPEN_ALM_TEST_MINIO_ENDPOINT": "https://production-alias.invalid:9000",
        "OPEN_ALM_TEST_MINIO_ACCESS_KEY": "test-access",
        "OPEN_ALM_TEST_MINIO_SECRET_KEY": "test-secret",
        "OPEN_ALM_TEST_OPENSEARCH_URL": "https://production-alias.invalid:9200",
        "OPEN_ALM_ENV_PROFILE": "development",
    }
    monkeypatch.setattr(
        infra_module.os,
        "getenv",
        lambda name, default=None: values.get(name, default),
    )
    monkeypatch.setattr(infra_module, "_file_value", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(infra_module, "_approved_dev_values", lambda _name: set())
    monkeypatch.setattr(infra_module, "_env_values", lambda _path: {})

    with pytest.raises(RuntimeError, match="NON_PRODUCTION_ACK"):
        IntegrationInfra.load()


def test_unrecognized_postgres_template_is_rejected_without_ack(monkeypatch) -> None:
    monkeypatch.setattr(
        infra_module.os,
        "getenv",
        lambda name, default=None: (
            "development" if name == "OPEN_ALM_ENV_PROFILE" else default
        ),
    )
    monkeypatch.setattr(infra_module, "_approved_dev_values", lambda _name: set())
    monkeypatch.setattr(infra_module, "_env_values", lambda _path: {})

    with pytest.raises(RuntimeError, match="PostgreSQL test template"):
        infra_module.assert_non_production_postgres_dsn(
            "postgresql+psycopg://user:password@production-alias.invalid/prod"
        )


def test_current_run_cleanup_attempts_every_backend(monkeypatch) -> None:
    infra = _infra()
    calls: list[str] = []

    def fail_minio(_self) -> None:
        calls.append("minio")
        raise RuntimeError("minio unavailable")

    monkeypatch.setattr(IntegrationInfra, "_cleanup_current_minio", fail_minio)
    monkeypatch.setattr(
        IntegrationInfra,
        "cleanup_opensearch_indices",
        lambda _self, _prefix: calls.append("opensearch"),
    )
    monkeypatch.setattr(
        IntegrationInfra,
        "cleanup_current_postgres_databases",
        lambda _self: calls.append("postgres"),
    )

    with pytest.raises(ExceptionGroup, match="resource cleanup failed"):
        infra.cleanup_current_run()

    assert calls == ["minio", "opensearch", "postgres"]
