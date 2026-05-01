from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.security import new_id
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.registry import reset_ai_capability_registry
from aidoo_api.core.db import get_engine
from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data
from aidoo_api.domains.auth.models import AuditLog, Workspace, WorkspaceAppEntitlement
from aidoo_api.domains.meeting.models import MeetingInsight, MeetingRecording


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
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/issues",
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


def test_ai_tool_invoke_meeting_extract_actions_returns_insights(
    client: TestClient,
    monkeypatch,
) -> None:
    from aidoo_api.domains.meeting import insights as meeting_insights

    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    workspace_slug = "delivery-hub"

    meeting_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "AI Tool Insight Meeting",
            "agenda": "Extract actions",
            "start_at": "2026-05-09T01:00:00+00:00",
            "end_at": "2026-05-09T02:00:00+00:00",
            "attendees": [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert meeting_response.status_code == 201, meeting_response.text
    meeting = meeting_response.json()

    with get_session_factory()() as db:
        db.add(
            MeetingRecording(
                id=new_id(),
                meeting_id=meeting["id"],
                storage_key=f"meeting-recordings/{meeting['id']}/ready.webm",
                duration_sec=120,
                file_size=128,
                mime_type="audio/webm",
                idempotency_key="tool-insight-recording",
                uploaded_by_id=session["user"]["id"],
                source="manual_upload",
                transcription_status="done",
                progress_pct=100,
                transcript_text="할 일은 로그인 플로우를 정리하는 것입니다.",
                summary_text="액션 아이템이 한 개 있습니다.",
            )
        )
        db.commit()

    def fake_complete_chat(context, _db, **_kwargs):
        assert context.task_kind == "meeting_insight_actions"
        return (
            type(
                "Response",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type(
                                    "Message",
                                    (),
                                    {
                                        "content": (
                                            '{"items":[{"title":"로그인 플로우 정리",'
                                            '"description":"OAuth 리다이렉트 경로 점검",'
                                            '"confidence":0.91}]}'
                                        )
                                    },
                                )()
                            },
                        )()
                    ]
                },
            )(),
            None,
            None,
        )

    monkeypatch.setattr(meeting_insights, "complete_chat", fake_complete_chat)

    response = client.post(
        _workspace_tool_path(workspace_slug, "meeting.extract_actions"),
        headers=_auth_headers(token),
        json={"arguments": {"meeting_id": meeting["id"], "refresh": True}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "meeting.extract_actions"
    assert payload["result"]["items"][0]["insight_type"] == "action"
    assert payload["result"]["items"][0]["payload"]["title"] == "로그인 플로우 정리"


def test_ai_tool_invoke_meeting_extract_actions_returns_stored_drafts_without_refresh(
    client: TestClient,
    monkeypatch,
) -> None:
    from aidoo_api.domains.meeting import insights as meeting_insights

    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    workspace_slug = "delivery-hub"

    meeting_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "Stored Insight Meeting",
            "agenda": "Use stored actions",
            "start_at": "2026-05-09T01:00:00+00:00",
            "end_at": "2026-05-09T02:00:00+00:00",
            "attendees": [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert meeting_response.status_code == 201, meeting_response.text
    meeting = meeting_response.json()

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert workspace is not None
        db.add(
            MeetingInsight(
                id=new_id(),
                meeting_id=meeting["id"],
                recording_id=None,
                workspace_id=workspace.id,
                insight_type="action",
                payload_json={
                    "title": "이미 저장된 액션",
                    "description": "기존 draft 재사용",
                },
                confidence=0.82,
                source_span=None,
                status="draft",
                accepted_as_kind=None,
                accepted_as_id=None,
                created_by_run_id=None,
            )
        )
        db.commit()

    monkeypatch.setattr(
        meeting_insights,
        "complete_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM should not run")),
    )

    response = client.post(
        _workspace_tool_path(workspace_slug, "meeting.extract_actions"),
        headers=_auth_headers(token),
        json={"arguments": {"meeting_id": meeting["id"]}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "meeting.extract_actions"
    assert payload["result"]["items"][0]["payload"]["title"] == "이미 저장된 액션"


def test_ai_tool_invoke_meeting_extract_decisions_returns_insights(
    client: TestClient,
    monkeypatch,
) -> None:
    from aidoo_api.domains.meeting import insights as meeting_insights

    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]
    workspace_slug = "delivery-hub"

    meeting_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "AI Tool Decision Meeting",
            "agenda": "Extract decisions",
            "start_at": "2026-05-10T01:00:00+00:00",
            "end_at": "2026-05-10T02:00:00+00:00",
            "attendees": [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert meeting_response.status_code == 201, meeting_response.text
    meeting = meeting_response.json()

    with get_session_factory()() as db:
        db.add(
            MeetingRecording(
                id=new_id(),
                meeting_id=meeting["id"],
                storage_key=f"meeting-recordings/{meeting['id']}/decision.webm",
                duration_sec=120,
                file_size=128,
                mime_type="audio/webm",
                idempotency_key="tool-decision-recording",
                uploaded_by_id=session["user"]["id"],
                source="manual_upload",
                transcription_status="done",
                progress_pct=100,
                transcript_text="이번 분기부터 신규 인증 흐름을 기본으로 합니다.",
                summary_text="결정사항이 하나 있습니다.",
            )
        )
        db.commit()

    def fake_complete_chat(context, _db, **_kwargs):
        assert context.task_kind == "meeting_insight_decisions"
        return (
            type(
                "Response",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type(
                                    "Message",
                                    (),
                                    {
                                        "content": (
                                            '{"items":[{"statement":"신규 인증 흐름 채택",'
                                            '"rationale":"리다이렉트 오류를 줄이기 위해",'
                                            '"confidence":0.89}]}'
                                        )
                                    },
                                )()
                            },
                        )()
                    ]
                },
            )(),
            None,
            None,
        )

    monkeypatch.setattr(meeting_insights, "complete_chat", fake_complete_chat)

    response = client.post(
        _workspace_tool_path(workspace_slug, "meeting.extract_decisions"),
        headers=_auth_headers(token),
        json={"arguments": {"meeting_id": meeting["id"], "refresh": True}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "meeting.extract_decisions"
    assert payload["result"]["items"][0]["insight_type"] == "decision"
    assert payload["result"]["items"][0]["payload"]["statement"] == "신규 인증 흐름 채택"


def test_ai_tool_invoke_meeting_draft_followup_schedule_returns_availability(
    client: TestClient,
) -> None:
    admin = _dev_login(client, "delivery-hub-admin")
    member = _dev_login(client, "delivery-hub-member")
    token = admin["token"]
    workspace_slug = "delivery-hub"

    meeting_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "AI Tool Follow-up Meeting",
            "agenda": "Schedule follow-up",
            "start_at": "2026-05-12T01:00:00+00:00",
            "end_at": "2026-05-12T02:00:00+00:00",
            "attendees": [{"user_id": member["user"]["id"], "role": "required"}],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert meeting_response.status_code == 201, meeting_response.text
    meeting = meeting_response.json()

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert workspace is not None
        db.add(
            MeetingInsight(
                id=new_id(),
                meeting_id=meeting["id"],
                recording_id=None,
                workspace_id=workspace.id,
                insight_type="followup_schedule",
                payload_json={
                    "proposed_title": "후속 점검 회의",
                    "duration_minutes": 30,
                    "proposed_slots": [
                        {
                            "start_at": "2026-05-12T00:00:00+00:00",
                            "end_at": "2026-05-13T00:00:00+00:00",
                        }
                    ],
                    "attendee_user_ids": [admin["user"]["id"], member["user"]["id"]],
                },
                confidence=0.77,
                source_span=None,
                status="draft",
                accepted_as_kind=None,
                accepted_as_id=None,
                created_by_run_id=None,
            )
        )
        db.commit()

    response = client.post(
        _workspace_tool_path(workspace_slug, "meeting.draft_followup_schedule"),
        headers=_auth_headers(token),
        json={"arguments": {"meeting_id": meeting["id"]}},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["tool"] == "meeting.draft_followup_schedule"
    assert payload["result"]["items"][0]["payload"]["proposed_title"] == "후속 점검 회의"
    assert payload["result"]["availability"] is not None
    assert len(payload["result"]["availability"]["items"]) == 2


def test_ai_tool_invoke_meeting_draft_followup_schedule_rejects_range_over_31_days(
    client: TestClient,
) -> None:
    admin = _dev_login(client, "delivery-hub-admin")
    member = _dev_login(client, "delivery-hub-member")
    token = admin["token"]
    workspace_slug = "delivery-hub"

    meeting_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "AI Tool Follow-up Limit Meeting",
            "agenda": "Schedule follow-up",
            "start_at": "2026-05-12T01:00:00+00:00",
            "end_at": "2026-05-12T02:00:00+00:00",
            "attendees": [{"user_id": member["user"]["id"], "role": "required"}],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert meeting_response.status_code == 201, meeting_response.text
    meeting = meeting_response.json()

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert workspace is not None
        db.add(
            MeetingInsight(
                id=new_id(),
                meeting_id=meeting["id"],
                recording_id=None,
                workspace_id=workspace.id,
                insight_type="followup_schedule",
                payload_json={
                    "proposed_title": "너무 먼 후속 회의",
                    "duration_minutes": 30,
                    "proposed_slots": [
                        {
                            "start_at": "2026-05-12T00:00:00+00:00",
                            "end_at": "2026-06-20T00:00:00+00:00",
                        }
                    ],
                    "attendee_user_ids": [admin["user"]["id"], member["user"]["id"]],
                },
                confidence=0.6,
                source_span=None,
                status="draft",
                accepted_as_kind=None,
                accepted_as_id=None,
                created_by_run_id=None,
            )
        )
        db.commit()

    response = client.post(
        _workspace_tool_path(workspace_slug, "meeting.draft_followup_schedule"),
        headers=_auth_headers(token),
        json={"arguments": {"meeting_id": meeting["id"]}},
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Availability range exceeds maximum 31 days."


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


def test_ai_tool_invoke_pms_write_tool_requires_approval_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_AI_WRITE_TOOLS_ENABLED", "1")
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
            _workspace_tool_path("delivery-hub", "pms.create_issue"),
            headers=_auth_headers(token),
            json={"arguments": {"list_id": task_list["id"], "title": "AI gated issue"}},
        )

        assert response.status_code == 409, response.text
        assert "requires approval before execution" in response.json()["detail"]
        audit_payload = _tool_audit_rows()[-1].payload
        assert audit_payload["tool_name"] == "pms.create_issue"
        assert audit_payload["status"] == "blocked"

        delete_response = client.post(
            _workspace_tool_path("delivery-hub", "pms.delete_issue"),
            headers=_auth_headers(token),
            json={"arguments": {"issue_id": "issue-approval-target"}},
        )
        assert delete_response.status_code == 409, delete_response.text
        delete_audit_payload = _tool_audit_rows()[-1].payload
        assert delete_audit_payload["tool_name"] == "pms.delete_issue"
        assert delete_audit_payload["status"] == "blocked"
    finally:
        monkeypatch.delenv("AIDOO_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()


def test_ai_tool_invoke_meeting_and_planner_write_tools_require_approval_when_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_AI_WRITE_TOOLS_ENABLED", "1")
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
        monkeypatch.delenv("AIDOO_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()
