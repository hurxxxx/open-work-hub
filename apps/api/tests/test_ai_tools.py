from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import dev_login
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai.registry import reset_ai_capability_registry
from ai_do_api.domains.ai.tool_service import _extract_resource_ids
from ai_do_api.core.db import get_engine
from ai_do_api.domains.auth.models import (
    AuditLog,
    PlatformAppVisibility,
)


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_tool_path(workspace_slug: str, tool_name: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/chatbot/tools/{tool_name}/invoke"


def _disable_platform_app(app_id: str) -> None:
    with Session(get_engine()) as session:
        visibility = session.scalar(
            select(PlatformAppVisibility).where(PlatformAppVisibility.app_id == app_id)
        )
        assert visibility is not None
        visibility.visible = False
        session.add(visibility)
        session.commit()


def _tool_audit_rows() -> list[AuditLog]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_tool_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
        )


def _reset_settings_and_registry() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    reset_ai_capability_registry()


def test_ai_tool_invoke_search_issues_returns_workspace_results(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    workspace_slug = "delivery-hub"

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "AITOOL", "name": "AI Tool Search List", "description": "tool source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        json={"title": "AI tool issue", "description": "search target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    response = client.post(
        _workspace_tool_path(workspace_slug, "pms.search_tasks"),
        headers=_auth_headers(token),
        json={"arguments": {"q": "AI tool issue", "limit": 10}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "pms.search_tasks"
    assert any(item["id"] == issue["id"] for item in payload["result"]["items"])
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "pms.search_tasks"
    assert audit_payload["status"] == "ok"
    assert audit_payload["source"] == "api.tool_invoke"
    assert issue["id"] in audit_payload["resource_ids"]


def test_ai_tool_audit_resource_id_extractor_uses_explicit_resource_ids() -> None:
    assert _extract_resource_ids(
        {
            "result": {
                "aggregate_result": {"resource_ids": ["record-1", "record-2"]},
                "items": [
                    {"resource_ids": ["record-3"]},
                    {"resource_id": "record-2"},
                    {"record_id": "record-3"},
                    {"id": "record-4"},
                ],
            }
        }
    ) == ["record-1", "record-2", "record-3"]


def test_ai_tool_invoke_rejects_unknown_tool(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    response = client.post(
        _workspace_tool_path("delivery-hub", "unknown.tool"),
        headers=_auth_headers(token),
        json={"arguments": {}},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "ai.unknown_tool"
    assert body["params"]["tool_name"] == "unknown.tool"
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "unknown.tool"
    assert audit_payload["status"] == "error"


def test_ai_tool_invoke_blocks_hidden_tool_and_audits_blocked(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    _disable_platform_app("planner")

    response = client.post(
        _workspace_tool_path("delivery-hub", "planner.list_events"),
        headers=_auth_headers(token),
        json={"arguments": {}},
    )

    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "ai.tool_unavailable_in_workspace"
    assert body["params"]["tool_name"] == "planner.list_events"
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "planner.list_events"
    assert audit_payload["status"] == "blocked"


def test_ai_tool_invoke_pms_write_tool_requires_approval_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_DO_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        session = _dev_login(client, "delivery-hub-admin")
        token = session["token"]

        task_list_response = client.post(
            "/api/v1/workspaces/delivery-hub/pms/lists",
            headers=_auth_headers(token),
            json={"key": "AITOOLW", "name": "AI Tool Write List", "description": "write source"},
        )
        assert task_list_response.status_code == 201, task_list_response.text
        task_list = task_list_response.json()

        response = client.post(
            _workspace_tool_path("delivery-hub", "pms.create_task"),
            headers=_auth_headers(token),
            json={"arguments": {"list_id": task_list["id"], "title": "AI gated issue"}},
        )

        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "ai.tool_requires_approval"
        assert body["params"]["tool_name"] == "pms.create_task"
        audit_payload = _tool_audit_rows()[-1].payload
        assert audit_payload["tool_name"] == "pms.create_task"
        assert audit_payload["status"] == "blocked"

        delete_response = client.post(
            _workspace_tool_path("delivery-hub", "pms.delete_task"),
            headers=_auth_headers(token),
            json={"arguments": {"task_id": "issue-approval-target"}},
        )
        assert delete_response.status_code == 409, delete_response.text
        delete_audit_payload = _tool_audit_rows()[-1].payload
        assert delete_audit_payload["tool_name"] == "pms.delete_task"
        assert delete_audit_payload["status"] == "blocked"
    finally:
        monkeypatch.delenv("AI_DO_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()


def test_ai_tool_invoke_meeting_and_planner_write_tools_require_approval_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_DO_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        session = _dev_login(client, "delivery-hub-admin")
        token = session["token"]

        meeting_response = client.post(
            _workspace_tool_path("delivery-hub", "meeting.create_meeting"),
            headers=_auth_headers(token),
            json={
                "arguments": {
                    "title": "AI gated meeting",
                    "start_at": "2026-05-10T01:00:00+00:00",
                    "end_at": "2026-05-10T02:00:00+00:00",
                }
            },
        )
        assert meeting_response.status_code == 409, meeting_response.text

        planner_response = client.post(
            _workspace_tool_path("delivery-hub", "planner.create_event"),
            headers=_auth_headers(token),
            json={
                "arguments": {
                    "title": "AI gated event",
                    "start_at": "2026-05-11T01:00:00+00:00",
                    "end_at": "2026-05-11T02:00:00+00:00",
                    "scope": "personal",
                }
            },
        )
        assert planner_response.status_code == 409, planner_response.text

        planner_update_response = client.post(
            _workspace_tool_path("delivery-hub", "planner.update_event"),
            headers=_auth_headers(token),
            json={
                "arguments": {
                    "event_id": "event-approval-target",
                    "title": "AI gated event update",
                }
            },
        )
        assert planner_update_response.status_code == 409, planner_update_response.text

        planner_delete_response = client.post(
            _workspace_tool_path("delivery-hub", "planner.delete_event"),
            headers=_auth_headers(token),
            json={"arguments": {"event_id": "event-approval-target"}},
        )
        assert planner_delete_response.status_code == 409, planner_delete_response.text
    finally:
        monkeypatch.delenv("AI_DO_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()
