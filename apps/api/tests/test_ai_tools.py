from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from test_pms_issues import _create_task_list
from dev_accounts import dev_login
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.domains.ai.registry import reset_ai_capability_registry
from open_work_hub_api.domains.ai.tool_service import _extract_resource_ids, execute_tool
from open_work_hub_api.core.db import get_engine
from open_work_hub_api.domains.auth.models import AuditLog, CompanyAppControl, User


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _tool_path(tool_name: str) -> str:
    return f"/api/v1/chatbot/tools/{tool_name}/invoke"


def _disable_platform_app(app_id: str) -> None:
    with Session(get_engine()) as session:
        control = session.scalar(
            select(CompanyAppControl).where(CompanyAppControl.app_id == app_id)
        )
        assert control is not None
        control.enabled = False
        session.add(control)
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


def test_ai_tool_invoke_search_issues_returns_accessible_space_results(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list = _create_task_list(client, token)

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/tasks",
        headers=_auth_headers(token),
        json={"title": "AI tool issue", "description": "search target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    response = client.post(
        _tool_path("pms.search_tasks"),
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


def test_ai_tool_lists_acl_scoped_pms_task_options(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    task_list = _create_task_list(client, token)

    response = client.post(
        _tool_path("pms.get_task_list_options"),
        headers=_auth_headers(token),
        json={"arguments": {"list_id": task_list["id"]}},
    )

    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert result["task_list"] == {
        "id": task_list["id"],
        "name": task_list["name"],
        "space_id": task_list["team_id"],
        "role": "owner",
        "can_edit": True,
        "archived": False,
    }
    assert {item["slug"] for item in result["statuses"]} >= {
        "todo",
        "in_progress",
        "done",
    }
    assert {item["name"] for item in result["labels"]} >= {
        "blocked",
        "priority",
        "review",
    }
    assert session["user"]["id"] in {item["id"] for item in result["assignees"]}

    platform_reader = _dev_login(client, "knowledge-base-admin")
    reader_response = client.post(
        _tool_path("pms.get_task_list_options"),
        headers=_auth_headers(platform_reader["token"]),
        json={"arguments": {"list_id": task_list["id"]}},
    )
    assert reader_response.status_code == 403, reader_response.text

    add_viewer_response = client.post(
        f"/api/v1/pms/spaces/{task_list['team_id']}/members",
        headers=_auth_headers(token),
        json={"user_id": platform_reader["user"]["id"], "role": "viewer"},
    )
    assert add_viewer_response.status_code == 201, add_viewer_response.text

    reader_response = client.post(
        _tool_path("pms.get_task_list_options"),
        headers=_auth_headers(platform_reader["token"]),
        json={"arguments": {"list_id": task_list["id"]}},
    )
    assert reader_response.status_code == 200, reader_response.text
    assert reader_response.json()["result"]["task_list"]["role"] == "viewer"
    assert reader_response.json()["result"]["task_list"]["can_edit"] is False


def test_pms_ai_write_rechecks_viewer_acl_after_external_approval(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        owner = _dev_login(client, "delivery-hub-admin")
        viewer = _dev_login(client, "knowledge-base-admin")
        task_list = _create_task_list(client, owner["token"])
        add_viewer_response = client.post(
            f"/api/v1/pms/spaces/{task_list['team_id']}/members",
            headers=_auth_headers(owner["token"]),
            json={"user_id": viewer["user"]["id"], "role": "viewer"},
        )
        assert add_viewer_response.status_code == 201, add_viewer_response.text
        task_response = client.post(
            f"/api/v1/pms/lists/{task_list['id']}/tasks",
            headers=_auth_headers(owner["token"]),
            json={"title": "Viewer cannot archive"},
        )
        assert task_response.status_code == 201, task_response.text
        task = task_response.json()

        with Session(get_engine()) as db:
            viewer_user = db.get(User, viewer["user"]["id"])
            assert viewer_user is not None
            with pytest.raises(HTTPException) as denied:
                execute_tool(
                    db,
                    principal=user_principal(
                        user_id=viewer_user.id,
                        source="test.pms.ai.viewer",
                    ),
                    user=viewer_user,
                    tool_name="pms.update_task",
                    arguments={"task_id": task["id"], "archived": True},
                    source="hermes-mcp",
                    externally_approved_call_id="approved-pms-viewer-archive",
                )
            assert denied.value.status_code == 403

        detail_response = client.get(
            f"/api/v1/pms/tasks/{task['id']}",
            headers=_auth_headers(owner["token"]),
        )
        assert detail_response.status_code == 200, detail_response.text
        assert detail_response.json()["task"]["archived"] is False
    finally:
        monkeypatch.delenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()


def test_pms_ai_write_tools_apply_daily_fields_archive_restore_and_delete(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        session = _dev_login(client, "delivery-hub-admin")
        token = session["token"]
        user_id = session["user"]["id"]
        task_list = _create_task_list(client, token)
        parent_response = client.post(
            f"/api/v1/pms/lists/{task_list['id']}/tasks",
            headers=_auth_headers(token),
            json={"title": "Parent task"},
        )
        assert parent_response.status_code == 201, parent_response.text
        parent = parent_response.json()

        options_response = client.post(
            _tool_path("pms.get_task_list_options"),
            headers=_auth_headers(token),
            json={"arguments": {"list_id": task_list["id"]}},
        )
        assert options_response.status_code == 200, options_response.text
        label_id = options_response.json()["result"]["labels"][0]["id"]

        with Session(get_engine()) as db:
            user = db.get(User, user_id)
            assert user is not None
            principal = user_principal(user_id=user.id, source="test.pms.ai.write")

            with pytest.raises(HTTPException) as invalid_status:
                execute_tool(
                    db,
                    principal=principal,
                    user=user,
                    tool_name="pms.create_task",
                    arguments={
                        "list_id": task_list["id"],
                        "title": "Invalid status task",
                        "status": "not-a-real-status",
                    },
                    source="hermes-mcp",
                    externally_approved_call_id="approved-pms-invalid-status",
                )
            assert invalid_status.value.status_code == 400

            created = execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name="pms.create_task",
                arguments={
                    "list_id": task_list["id"],
                    "title": "AI managed task",
                    "body": "Implementation details",
                    "status": "in_progress",
                    "priority": "high",
                    "assignee_ids": [user.id],
                    "labels": [label_id],
                    "parent_id": parent["id"],
                    "start_date": "2026-09-21",
                    "due_date": "2026-09-30",
                },
                source="hermes-mcp",
                externally_approved_call_id="approved-pms-create",
            )["result"]

            assert created["id"] == "approved-pms-create"
            assert created["resource_ids"] == [created["id"]]
            assert created["status"] == "in_progress"
            assert created["priority"] == "high"
            assert created["assignee_ids"] == [user.id]
            assert [item["id"] for item in created["labels"]] == [label_id]
            assert created["parent_id"] == parent["id"]
            assert str(created["start_date"]) == "2026-09-21"
            assert str(created["due_date"]) == "2026-09-30"

            strict_update = execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name="pms.update_task",
                arguments={
                    "task_id": created["id"],
                    "title": "AI managed task updated",
                    "parent_id": None,
                    "start_date": None,
                    "due_date": None,
                },
                source="hermes-mcp",
                externally_approved_call_id="approved-pms-strict-update",
                strict_tool_arguments=True,
            )["result"]
            assert strict_update["title"] == "AI managed task updated"
            assert strict_update["parent_id"] == parent["id"]
            assert str(strict_update["start_date"]) == "2026-09-21"
            assert str(strict_update["due_date"]) == "2026-09-30"

            comment = execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name="pms.add_comment",
                arguments={"task_id": created["id"], "body": "AI progress update"},
                source="hermes-mcp",
                externally_approved_call_id="approved-pms-comment",
            )["result"]
            assert comment["body"] == "AI progress update"
            assert comment["resource_ids"] == [created["id"], comment["id"]]

            archived = execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name="pms.update_task",
                arguments={
                    "task_id": created["id"],
                    "body": "",
                    "priority": "low",
                    "assignee_ids": [],
                    "labels": [],
                    "archived": True,
                    "parent_id": None,
                    "start_date": None,
                    "due_date": None,
                },
                source="hermes-mcp",
                externally_approved_call_id="approved-pms-archive",
            )["result"]

            assert archived["description"] == ""
            assert archived["resource_ids"] == [created["id"]]
            assert archived["priority"] == "low"
            assert archived["assignee_ids"] == []
            assert archived["labels"] == []
            assert archived["parent_id"] is None
            assert archived["start_date"] is None
            assert archived["due_date"] is None
            assert archived["archived"] is True

            restored = execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name="pms.update_task",
                arguments={"task_id": created["id"], "archived": False},
                source="hermes-mcp",
                externally_approved_call_id="approved-pms-restore",
            )["result"]
            assert restored["archived"] is False

            deleted = execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name="pms.delete_task",
                arguments={"task_id": created["id"]},
                source="hermes-mcp",
                externally_approved_call_id="approved-pms-delete",
            )["result"]
            assert deleted == {
                "id": created["id"],
                "deleted": True,
                "resource_ids": [created["id"]],
            }
            retried_delete = execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name="pms.delete_task",
                arguments={"task_id": created["id"]},
                source="hermes-mcp",
                externally_approved_call_id="approved-pms-delete",
            )["result"]
            assert retried_delete == deleted

        missing_response = client.get(
            f"/api/v1/pms/tasks/{created['id']}",
            headers=_auth_headers(token),
        )
        assert missing_response.status_code == 404
        delete_audit = _tool_audit_rows()[-1].payload
        assert delete_audit["tool_name"] == "pms.delete_task"
        assert delete_audit["resource_ids"] == [created["id"]]
    finally:
        monkeypatch.delenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()


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
        _tool_path("unknown.tool"),
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
        _tool_path("planner.list_events"),
        headers=_auth_headers(token),
        json={"arguments": {}},
    )

    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "ai.tool_unavailable_for_user"
    assert body["params"]["tool_name"] == "planner.list_events"
    audit_payload = _tool_audit_rows()[-1].payload
    assert audit_payload["tool_name"] == "planner.list_events"
    assert audit_payload["status"] == "blocked"


def test_ai_tool_invoke_pms_write_tool_requires_approval_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        session = _dev_login(client, "delivery-hub-admin")
        token = session["token"]

        task_list = _create_task_list(client, token)

        response = client.post(
            _tool_path("pms.create_task"),
            headers=_auth_headers(token),
            json={
                "arguments": {
                    "list_id": task_list["id"],
                    "title": "AI gated issue",
                    "status": "todo",
                }
            },
        )

        assert response.status_code == 409, response.text
        body = response.json()
        assert body["code"] == "ai.tool_requires_approval"
        assert body["params"]["tool_name"] == "pms.create_task"
        audit_payload = _tool_audit_rows()[-1].payload
        assert audit_payload["tool_name"] == "pms.create_task"
        assert audit_payload["status"] == "blocked"

        tasks_response = client.get(
            f"/api/v1/pms/lists/{task_list['id']}/tasks",
            headers=_auth_headers(token),
            params={"q": "AI gated issue"},
        )
        assert tasks_response.status_code == 200, tasks_response.text
        assert tasks_response.json()["items"] == []

        delete_response = client.post(
            _tool_path("pms.delete_task"),
            headers=_auth_headers(token),
            json={"arguments": {"task_id": "issue-approval-target"}},
        )
        assert delete_response.status_code == 409, delete_response.text
        delete_audit_payload = _tool_audit_rows()[-1].payload
        assert delete_audit_payload["tool_name"] == "pms.delete_task"
        assert delete_audit_payload["status"] == "blocked"
    finally:
        monkeypatch.delenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()


def test_ai_tool_invoke_meeting_and_planner_write_tools_require_approval_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        session = _dev_login(client, "delivery-hub-admin")
        token = session["token"]

        meeting_response = client.post(
            _tool_path("meeting.create_meeting"),
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
            _tool_path("planner.create_event"),
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
            _tool_path("planner.update_event"),
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
            _tool_path("planner.delete_event"),
            headers=_auth_headers(token),
            json={"arguments": {"event_id": "event-approval-target"}},
        )
        assert planner_delete_response.status_code == 409, planner_delete_response.text
    finally:
        monkeypatch.delenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()
