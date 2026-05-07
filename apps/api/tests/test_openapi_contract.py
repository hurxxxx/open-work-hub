from __future__ import annotations

import pytest


def test_openapi_schema_exports_without_runtime_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DOOWON_POSTGRES_DSN",
        "postgresql+psycopg://openapi:openapi@127.0.0.1:1/openapi",
    )

    from ai_do_api.core.settings import get_settings
    from ai_do_api import app as app_module
    from ai_do_api.openapi_contract import assert_openapi_contract

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

    assert_openapi_contract(schema)

    assert "/api/v1/workspaces/{workspace_slug}/pms/lists" in schema["paths"]
    assert "/api/v1/workspaces/{workspace_slug}/docs/hub" in schema["paths"]
    assert "/api/v1/workspaces/{workspace_slug}/meeting/meetings" in schema["paths"]
    assert "/api/v1/workspaces/{workspace_slug}/planner/events" in schema["paths"]
    assert "/api/v1/docs/shared-links/{share_token}" in schema["paths"]
    assert "/api/v1/ai/chat" not in schema["paths"]
    assert "/api/v1/pms/lists" not in schema["paths"]
    assert "/api/v1/docs/hub" not in schema["paths"]
    assert "/api/v1/meeting/meetings" not in schema["paths"]
    assert "/api/v1/planner/events" not in schema["paths"]
    assert "/api/v1/calendar/events" not in schema["paths"]

    assert schema["paths"]["/healthz"]["get"]["operationId"] == "system_healthz_get"
    assert (
        schema["paths"]["/api/v1/workspaces/{workspace_slug}/pms/lists"]["get"][
            "operationId"
        ]
        == "pms_list_task_lists_get"
    )
    assert (
        schema["paths"]["/api/v1/workspaces/{workspace_slug}/meeting/meetings"][
            "post"
        ]["operationId"]
        == "meeting_create_meeting_post"
    )
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert (
        schema["paths"]["/api/v1/workspaces/{workspace_slug}/pms/lists"]["get"]["responses"][
            "401"
        ]["description"]
        == "Authentication required."
    )

    get_settings.cache_clear()
