from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_engine
from aidoo_api.domains.ai import approvals as ai_approvals
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.conversations import service as conversations_service
from aidoo_api.domains.conversations.models import Conversation
from test_meeting import _auth_headers, _bootstrap_admin_session, _create_meeting


def _workspace_slug(client, token: str) -> str:
    response = client.get("/api/v1/admin/workspaces", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    workspace = response.json()[0]
    return workspace.get("slug", workspace["key"])


def _workspace_ai_conversations_path(workspace_slug: str, suffix: str = "") -> str:
    return f"/api/v1/workspaces/{workspace_slug}/ai/conversations{suffix}"


def test_create_ai_conversation_with_meeting_scope(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, title="Scoped kickoff")

    response = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["scopeRef"] == "meeting"
    assert body["scopeResourceId"] == meeting["id"]
    assert body["turns"] == []
    assert body["livePendingApproval"] is None


def test_get_ai_conversation_returns_live_pending_approval(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, title="Approval scoped meeting")

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, session["user"]["id"])
        assert workspace is not None
        assert user is not None
        conversation = conversations_service.create_conversation(
            db,
            workspace=workspace,
            user=user,
            title="",
            scope_ref="meeting",
            scope_resource_id=meeting["id"],
        )
        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "system", "content": "scoped"}],
            blocked_call_id="call-1",
            model_meta={"model": "test-model"},
        )
        approval = ai_approvals.create_pending_approval(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            agent_run_id=snapshot.id,
            tool_call_id="call-1",
            tool_name="pms.create_issue",
            arguments_json='{"title":"Fix scope"}',
            resource_preview="이슈 생성",
        )
        db.commit()
        conversation_id = conversation.id
        approval_id = approval.id
        snapshot_id = snapshot.id

    response = client.get(
        _workspace_ai_conversations_path(slug, f"/{conversation_id}"),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == conversation_id
    assert body["livePendingApproval"] is not None
    assert body["livePendingApproval"]["approvalId"] == approval_id
    assert body["livePendingApproval"]["agentRunId"] == snapshot_id
    assert body["livePendingApproval"]["callId"] == "call-1"
    assert body["livePendingApproval"]["tool"] == "pms.create_issue"
    assert body["livePendingApproval"]["resourcePreview"] == "이슈 생성"
    assert body["livePendingApproval"]["status"] == "pending"
    assert body["livePendingApproval"]["reason"] is None
    assert isinstance(body["livePendingApproval"]["expiresAtMs"], int)


def test_get_ai_conversation_omits_terminal_live_pending_approval(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, title="Expired approval meeting")

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, session["user"]["id"])
        assert workspace is not None
        assert user is not None
        conversation = conversations_service.create_conversation(
            db,
            workspace=workspace,
            user=user,
            title="",
            scope_ref="meeting",
            scope_resource_id=meeting["id"],
        )
        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "system", "content": "scoped"}],
            blocked_call_id="call-expired",
            model_meta={"model": "test-model"},
        )
        approval = ai_approvals.create_pending_approval(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            agent_run_id=snapshot.id,
            tool_call_id="call-expired",
            tool_name="pms.create_issue",
            arguments_json='{"title":"Fix scope"}',
            resource_preview="이슈 생성",
        )
        approval.status = "expired"
        db.add(approval)
        db.commit()
        conversation_id = conversation.id

    response = client.get(
        _workspace_ai_conversations_path(slug, f"/{conversation_id}"),
        headers=_auth_headers(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["livePendingApproval"] is None


def test_create_ai_conversation_reuses_latest_empty_scoped_conversation(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, title="Reuse scoped meeting")

    first = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert first.status_code == 201, first.text

    second = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]


def test_get_ai_conversation_tolerates_legacy_unsupported_scope_row(client) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    meeting = _create_meeting(client, token, title="Legacy scope row")

    response = client.post(
        _workspace_ai_conversations_path(slug),
        headers=_auth_headers(token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert response.status_code == 201, response.text
    conversation_id = response.json()["id"]

    with Session(get_engine()) as db:
        conversation = db.get(Conversation, conversation_id)
        assert conversation is not None
        conversation.scope_ref = "docs_page"
        conversation.scope_resource_id = "doc-1"
        db.add(conversation)
        db.commit()

    detail = client.get(
        _workspace_ai_conversations_path(slug, f"/{conversation_id}"),
        headers=_auth_headers(token),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["scopeRef"] is None
    assert body["scopeResourceId"] is None
