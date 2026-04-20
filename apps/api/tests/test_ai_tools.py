from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_engine
from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data
from aidoo_api.domains.auth.models import AuditLog, Workspace, WorkspaceAppEntitlement


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_tool_path(workspace_slug: str, tool_name: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/ai/tools/{tool_name}/invoke"


def _disable_workspace_app(workspace_slug: str, app_id: str) -> None:
    with Session(get_engine()) as session:
        workspace = session.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert workspace is not None
        entitlement = session.scalar(
            select(WorkspaceAppEntitlement).where(
                WorkspaceAppEntitlement.workspace_id == workspace.id,
                WorkspaceAppEntitlement.app_id == app_id,
            )
        )
        assert entitlement is not None
        entitlement.enabled = False
        session.add(entitlement)
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


def test_ai_tool_invoke_search_issues_returns_workspace_results(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    workspace_slug = "delivery-hub"

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(token),
        json={"key": "AITOOL", "name": "AI Tool Search List", "description": "tool source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        json={"title": "AI tool issue", "description": "search target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    response = client.post(
        _workspace_tool_path(workspace_slug, "pms.search_issues"),
        headers=_auth_headers(token),
        json={"arguments": {"q": "AI tool issue", "limit": 10}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "pms.search_issues"
    assert any(item["id"] == issue["id"] for item in payload["result"]["items"])
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "pms.search_issues"
    assert audit_payload["status"] == "ok"
    assert audit_payload["source"] == "api.tool_invoke"
    assert issue["id"] in audit_payload["resource_ids"]


def test_ai_tool_invoke_docs_read_page_returns_page_content(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    workspace_slug = "delivery-hub"

    doc_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items",
        headers=_auth_headers(token),
        json={"title": "AI Tool Doc"},
    )
    assert doc_response.status_code == 201, doc_response.text
    doc = doc_response.json()

    page_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(token),
        json={
            "title": "AI Tool Page",
            "content_blocks": [{"type": "paragraph", "content": "hello from ai tool"}],
        },
    )
    assert page_response.status_code == 201, page_response.text
    page = page_response.json()

    response = client.post(
        _workspace_tool_path(workspace_slug, "docs.read_page"),
        headers=_auth_headers(token),
        json={"arguments": {"page_id": page["id"]}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "docs.read_page"
    assert payload["result"]["id"] == page["id"]
    assert payload["result"]["content_blocks"] == [
        {"type": "paragraph", "content": "hello from ai tool"}
    ]


def test_ai_tool_invoke_planner_list_events_returns_owner_events(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    workspace_slug = "delivery-hub"

    created = client.post(
        f"/api/v1/workspaces/{workspace_slug}/planner/events",
        headers=_auth_headers(token),
        json={
            "title": "AI Tool Planner Event",
            "description": "planner tool",
            "location": "HQ",
            "visibility": "private",
            "allDay": False,
            "start": "2026-05-04T01:00:00+00:00",
            "end": "2026-05-04T02:00:00+00:00",
        },
    )
    assert created.status_code == 201, created.text
    event = created.json()

    response = client.post(
        _workspace_tool_path(workspace_slug, "planner.list_events"),
        headers=_auth_headers(token),
        json={
            "arguments": {
                "from": "2026-05-01T00:00:00+00:00",
                "to": "2026-06-01T00:00:00+00:00",
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "planner.list_events"
    assert any(item["id"] == event["id"] for item in payload["result"]["items"])


def test_ai_tool_invoke_meeting_find_availability_returns_blocks(client: TestClient) -> None:
    admin = _dev_login(client, "delivery-hub-admin")
    member = _dev_login(client, "delivery-hub-member")
    token = admin["token"]
    workspace_slug = "delivery-hub"

    start_at = datetime(2026, 5, 7, 10, 0, 0)
    end_at = start_at + timedelta(hours=1)
    meeting_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "AI Tool Availability Meeting",
            "agenda": "Check availability",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "attendees": [{"user_id": member["user"]["id"], "role": "required"}],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert meeting_response.status_code == 201, meeting_response.text
    meeting = meeting_response.json()

    response = client.post(
        _workspace_tool_path(workspace_slug, "meeting.find_availability"),
        headers=_auth_headers(token),
        json={
            "arguments": {
                "user_ids": [admin["user"]["id"], member["user"]["id"]],
                "from": "2026-05-07T00:00:00+00:00",
                "to": "2026-05-08T00:00:00+00:00",
            }
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "meeting.find_availability"
    assert len(payload["result"]["items"]) == 2
    assert any(
        block["id"] == f"meeting-{meeting['id']}"
        for item in payload["result"]["items"]
        for block in item["blocks"]
    )


def test_ai_tool_invoke_rejects_unknown_tool(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    response = client.post(
        _workspace_tool_path("delivery-hub", "unknown.tool"),
        headers=_auth_headers(token),
        json={"arguments": {}},
    )
    assert response.status_code == 404
    assert "Unknown AI tool" in response.json()["detail"]
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "unknown.tool"
    assert audit_payload["status"] == "error"


def test_ai_tool_invoke_blocks_hidden_tool_and_audits_blocked(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    _disable_workspace_app("delivery-hub", "planner")

    response = client.post(
        _workspace_tool_path("delivery-hub", "planner.list_events"),
        headers=_auth_headers(token),
        json={"arguments": {}},
    )

    assert response.status_code == 403, response.text
    assert "not available in this workspace" in response.json()["detail"]
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "planner.list_events"
    assert audit_payload["status"] == "blocked"
