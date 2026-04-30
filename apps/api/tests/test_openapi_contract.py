from __future__ import annotations

import pytest


def test_openapi_schema_exports_without_runtime_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DOOWON_POSTGRES_DSN",
        "postgresql+psycopg://openapi:openapi@127.0.0.1:1/openapi",
    )

    from aidoo_api.core.settings import get_settings
    from aidoo_api import app as app_module

    get_settings.cache_clear()
    monkeypatch.setattr(
        app_module,
        "init_db",
        lambda: pytest.fail("OpenAPI export must not initialize the database."),
    )
    monkeypatch.setattr(
        app_module,
        "ensure_bucket",
        lambda: pytest.fail("OpenAPI export must not initialize storage."),
    )
    monkeypatch.setattr(
        app_module,
        "initialize_ai_capability_registry",
        lambda: pytest.fail("OpenAPI export must not initialize AI runtime registries."),
    )

    api = app_module.create_app(initialize_runtime=False)
    schema = api.openapi()

    assert "/api/v1/workspaces/{workspace_slug}/pms/lists" in schema["paths"]
    assert "/api/v1/workspaces/{workspace_slug}/docs/hub" in schema["paths"]
    assert "/api/v1/workspaces/{workspace_slug}/meeting/meetings" in schema["paths"]
    assert "/api/v1/workspaces/{workspace_slug}/planner/events" in schema["paths"]
    assert "/api/v1/pms/lists" in schema["paths"]
    assert "/api/v1/docs/hub" in schema["paths"]
    assert "/api/v1/meeting/meetings" in schema["paths"]
    assert "/api/v1/planner/events" in schema["paths"]

    get_settings.cache_clear()
