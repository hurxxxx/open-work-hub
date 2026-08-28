from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import dev_login
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import reset_ai_capability_registry
from open_work_hub_api.core.db import get_engine
from open_work_hub_api.domains.auth.models import CompanyAppControl


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_ai_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/chatbot{suffix}"


def _disable_platform_app(app_id: str) -> None:
    with Session(get_engine()) as session:
        control = session.scalar(
            select(CompanyAppControl).where(CompanyAppControl.app_id == app_id)
        )
        assert control is not None
        control.enabled = False
        session.add(control)
        session.commit()


def _reset_settings_and_registry() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    reset_ai_capability_registry()


def test_capability_manifest_returns_filtered_tool_inventory(client: TestClient) -> None:
    auth = _dev_login(client, "delivery-hub-admin")
    response = client.get(
        _workspace_ai_path("delivery-hub", "/capabilities/manifest"),
        headers=_auth_headers(auth["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()

    tool_names = [item["name"] for item in payload["tools"]]
    assert tool_names == sorted(tool_names)
    assert {
        "docs.get_item",
        "meeting.list_meetings",
        "planner.list_events",
        "pms.get_task",
        "pms.list_spaces",
        "pms.list_task_lists",
        "pms.search_tasks",
        "rag.query",
    } <= set(tool_names)
    assert "pms.get_issue" not in tool_names
    assert payload["server"]["transport"] == "inproc"
    assert all("annotations" in item for item in payload["tools"])
    assert all("_meta" in item for item in payload["tools"])


def test_app_manifest_and_openapi_are_scoped_to_one_app(client: TestClient) -> None:
    auth = _dev_login(client, "delivery-hub-admin")

    manifest_response = client.get(
        _workspace_ai_path("delivery-hub", "/apps/planner/manifest"),
        headers=_auth_headers(auth["token"]),
    )
    assert manifest_response.status_code == 200, manifest_response.text
    manifest_payload = manifest_response.json()
    assert [item["name"] for item in manifest_payload["tools"]] == ["planner.list_events"]

    openapi_response = client.get(
        _workspace_ai_path("delivery-hub", "/apps/planner/openapi.json"),
        headers=_auth_headers(auth["token"]),
    )
    assert openapi_response.status_code == 200, openapi_response.text
    openapi_payload = openapi_response.json()
    assert set(openapi_payload["paths"].keys()) == {"/mcp/tools/planner.list_events"}


def test_manifest_and_openapi_reflect_platform_visibility_changes_on_next_request(
    client: TestClient,
) -> None:
    auth = _dev_login(client, "delivery-hub-admin")
    _disable_platform_app("planner")

    manifest_response = client.get(
        _workspace_ai_path("delivery-hub", "/capabilities/manifest"),
        headers=_auth_headers(auth["token"]),
    )
    assert manifest_response.status_code == 200, manifest_response.text
    manifest_payload = manifest_response.json()
    assert "planner.list_events" not in {item["name"] for item in manifest_payload["tools"]}

    openapi_response = client.get(
        _workspace_ai_path("delivery-hub", "/capabilities/openapi.json"),
        headers=_auth_headers(auth["token"]),
    )
    assert openapi_response.status_code == 200, openapi_response.text
    openapi_payload = openapi_response.json()
    assert "/mcp/tools/planner.list_events" not in openapi_payload["paths"]


def test_manifest_and_openapi_include_pms_write_tools_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        auth = _dev_login(client, "delivery-hub-admin")

        manifest_response = client.get(
            _workspace_ai_path("delivery-hub", "/capabilities/manifest"),
            headers=_auth_headers(auth["token"]),
        )
        assert manifest_response.status_code == 200, manifest_response.text
        manifest_payload = manifest_response.json()
        tool_names = {item["name"] for item in manifest_payload["tools"]}
        assert {
            "pms.create_task",
            "pms.update_task",
            "pms.add_comment",
            "pms.delete_task",
            "meeting.create_meeting",
            "planner.create_event",
            "planner.update_event",
            "planner.delete_event",
        } <= tool_names
        assert "docs.create_page" not in tool_names

        openapi_response = client.get(
            _workspace_ai_path("delivery-hub", "/capabilities/openapi.json"),
            headers=_auth_headers(auth["token"]),
        )
        assert openapi_response.status_code == 200, openapi_response.text
        openapi_payload = openapi_response.json()
        assert "/mcp/tools/pms.create_task" in openapi_payload["paths"]
        assert "/mcp/tools/pms.update_task" in openapi_payload["paths"]
        assert "/mcp/tools/pms.add_comment" in openapi_payload["paths"]
        assert "/mcp/tools/pms.delete_task" in openapi_payload["paths"]
        assert "/mcp/tools/meeting.create_meeting" in openapi_payload["paths"]
        assert "/mcp/tools/planner.create_event" in openapi_payload["paths"]
        assert "/mcp/tools/planner.update_event" in openapi_payload["paths"]
        assert "/mcp/tools/planner.delete_event" in openapi_payload["paths"]
        assert "/mcp/tools/docs.create_page" not in openapi_payload["paths"]
    finally:
        monkeypatch.delenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()


def test_planner_app_manifest_and_openapi_include_write_tool_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        auth = _dev_login(client, "delivery-hub-admin")

        manifest_response = client.get(
            _workspace_ai_path("delivery-hub", "/apps/planner/manifest"),
            headers=_auth_headers(auth["token"]),
        )
        assert manifest_response.status_code == 200, manifest_response.text
        manifest_payload = manifest_response.json()
        assert {item["name"] for item in manifest_payload["tools"]} == {
            "planner.list_events",
            "planner.create_event",
            "planner.update_event",
            "planner.delete_event",
        }

        openapi_response = client.get(
            _workspace_ai_path("delivery-hub", "/apps/planner/openapi.json"),
            headers=_auth_headers(auth["token"]),
        )
        assert openapi_response.status_code == 200, openapi_response.text
        openapi_payload = openapi_response.json()
        assert set(openapi_payload["paths"].keys()) == {
            "/mcp/tools/planner.list_events",
            "/mcp/tools/planner.create_event",
            "/mcp/tools/planner.update_event",
            "/mcp/tools/planner.delete_event",
        }
    finally:
        monkeypatch.delenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()
