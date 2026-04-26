from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import json
from typing import Any

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
import pytest
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.core.principal import user_principal
from aidoo_api.domains.ai import agent as ai_agent
from aidoo_api.domains.ai import approvals as ai_approvals
from aidoo_api.domains.ai import mcp as ai_mcp
from aidoo_api.domains.ai import router as ai_router
from aidoo_api.domains.ai import tool_service as ai_tool_service
from aidoo_api.domains.ai.tool_runtime import ToolCallExecution
from aidoo_api.core.llm_adapters import StreamChunk
from aidoo_api.domains.ai.registry import (
    AiCapabilityRegistry,
    ApprovalPreview,
    PreviewField,
)
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data
from aidoo_api.domains.auth.access import load_user_graph
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.conversations import service as conversations_service
from test_meeting import _auth_headers, _dev_login


@pytest.fixture(autouse=True)
def _reset_sse_starlette_app_status() -> None:
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


def _workspace_ai_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/ai{suffix}"


def _legacy_ai_path(suffix: str) -> str:
    return f"/api/v1/ai{suffix}"


def _parse_sse(body: str) -> list[dict[str, Any]]:
    normalized = body.replace("\r\n", "\n")
    events: list[dict[str, Any]] = []
    for block in normalized.split("\n\n"):
        block = block.strip("\n")
        if not block:
            continue
        data_str: str | None = None
        for line in block.split("\n"):
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_str = line[len("data:") :].strip()
        if data_str is None:
            continue
        events.append(json.loads(data_str))
    return events


_APPROVAL_TOOL_NAME = "test.approval_write"


class _ApprovalToolArgs(BaseModel):
    title: str


def _approval_tool_handler(
    db: Any,
    workspace: Any,
    principal: Any,
    user: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    del db, workspace, principal, user
    title = str(arguments["title"])
    slug = title.lower().replace(" ", "-")
    return {
        "id": f"approval-{slug}",
        "title": title,
    }


def _approval_preview_builder(
    principal: Any,
    workspace_context: Any,
    parsed_args: BaseModel | dict[str, Any],
) -> ApprovalPreview:
    del principal, workspace_context
    if isinstance(parsed_args, BaseModel):
        title = str(getattr(parsed_args, "title"))
    else:
        title = str(parsed_args.get("title") or "Untitled")
    return ApprovalPreview(
        title="Approval Test Write",
        summary="Creates an approval-gated test resource.",
        fields=(PreviewField(label="Title", value=title),),
    )


def _build_test_approval_registry(
    *,
    handler: Any = _approval_tool_handler,
) -> AiCapabilityRegistry:
    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="test.enabled",
        predicate=lambda principal, workspace_context, entitlements: True,
    )
    registry.register_preview_builder(
        preview_builder_id="test.preview",
        builder=_approval_preview_builder,
    )
    registry.register_tool(
        name=_APPROVAL_TOOL_NAME,
        description="Approval-gated test write tool.",
        owner_domain="test",
        approval_required=True,
        handler=handler,
        args_model=_ApprovalToolArgs,
        mode="write",
        discoverability_predicate_id="test.enabled",
        preview_builder_id="test.preview",
        # owner_domain is a synthetic test value; pin the workspace_app_id to
        # a real workspace app so the registry validation passes.
        workspace_app_id="ai",
    )
    registry.compile_capabilities()
    return registry


def _patch_test_approval_registry(
    monkeypatch: pytest.MonkeyPatch,
    registry: AiCapabilityRegistry,
) -> None:
    monkeypatch.setattr(ai_tool_service, "get_ai_capability_registry", lambda: registry)
    monkeypatch.setattr(ai_router, "get_ai_capability_registry", lambda: registry)


def _seed_pending_approval(
    client: TestClient,
    *,
    expires_at: datetime | None = None,
    tool_name: str = "pms.create_issue",
    arguments_json: str = '{"title":"Approval issue"}',
    resource_preview: str = "Create PMS issue Approval issue",
) -> dict[str, str]:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    session = _dev_login(client, "delivery-hub-admin")
    workspace_slug = "delivery-hub"

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert user is not None
        assert workspace is not None

        conversation = conversations_service.create_conversation(
            db,
            workspace=workspace,
            user=user,
            title="approval test",
        )
        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "user", "content": "create an issue"}],
            blocked_call_id="call-1",
            model_meta={
                "model": "qwen/qwen3.6-35b-a3b",
                "policy": "local_only",
                "chosen_pool": "local",
                "parallel_tool_calls": False,
                "temperature": 0.2,
                "max_output_tokens": 4096,
            },
        )
        approval = ai_approvals.create_pending_approval(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            agent_run_id=snapshot.id,
            tool_call_id="call-1",
            tool_name=tool_name,
            arguments_json=arguments_json,
            resource_preview=resource_preview,
            expires_at=expires_at,
        )
        db.commit()

        return {
            "token": session["token"],
            "user_id": user.id,
            "workspace_slug": workspace_slug,
            "conversation_id": conversation.id,
            "approval_id": approval.id,
            "agent_run_id": snapshot.id,
        }


def test_get_and_resolve_approval_routes_work_on_workspace_and_legacy_mounts(
    client: TestClient,
) -> None:
    seed = _seed_pending_approval(client)
    headers = _auth_headers(seed["token"])

    resolve_response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert resolve_response.status_code == 200, resolve_response.text
    resolved = resolve_response.json()
    assert resolved["status"] == "approved"
    assert resolved["tool_call_id"] == "call-1"
    assert resolved["snapshot_status"] == "awaiting_approval"

    workspace_get = client.get(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}"),
        headers=headers,
    )
    assert workspace_get.status_code == 200, workspace_get.text
    assert workspace_get.json()["status"] == "approved"

    legacy_get = client.get(
        _legacy_ai_path(f"/approvals/{seed['approval_id']}"),
        headers=headers,
    )
    assert legacy_get.status_code == 200, legacy_get.text
    assert legacy_get.json()["status"] == "approved"


def test_abandon_approval_route_marks_snapshot_abandoned(client: TestClient) -> None:
    seed = _seed_pending_approval(client)
    headers = _auth_headers(seed["token"])

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/abandon"),
        headers=headers,
        json={"reason": "cancelled in review"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["reject_reason"] == "cancelled in review"
    assert body["snapshot_status"] == "abandoned"


def test_resolve_approval_expired_transition_persists_before_410(client: TestClient) -> None:
    seed = _seed_pending_approval(
        client,
        expires_at=ai_approvals.utcnow_naive() - timedelta(minutes=1),
    )
    headers = _auth_headers(seed["token"])

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )

    assert response.status_code == 410, response.text
    assert response.json()["detail"] == "Approval has expired."

    status_response = client.get(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}"),
        headers=headers,
    )
    assert status_response.status_code == 200, status_response.text
    body = status_response.json()
    assert body["status"] == "expired"
    assert body["snapshot_status"] == "abandoned"


def test_resolve_approval_rejects_second_resolution(client: TestClient) -> None:
    seed = _seed_pending_approval(client)
    headers = _auth_headers(seed["token"])

    first = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "Approval is already approved."


def test_resolve_approval_forbidden_for_different_user(client: TestClient) -> None:
    seed = _seed_pending_approval(client)
    session = _dev_login(client, "delivery-hub-member")
    headers = _auth_headers(session["token"])

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Approval belongs to a different user."


def test_chat_resume_rejects_mismatched_conversation_id(client: TestClient) -> None:
    seed = _seed_pending_approval(client)
    headers = _auth_headers(seed["token"])

    resolve_response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert resolve_response.status_code == 200, resolve_response.text

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": "different-conversation-id",
            "approval_id": seed["approval_id"],
        },
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Approval does not belong to the requested conversation."


def test_chat_resume_rejects_pending_approval(client: TestClient) -> None:
    seed = _seed_pending_approval(client)
    headers = _auth_headers(seed["token"])

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": seed["conversation_id"],
            "approval_id": seed["approval_id"],
        },
    )

    assert response.status_code == 400
    assert "resolved before resume" in response.json()["detail"]


def test_chat_resume_replays_approved_tool_and_completes_snapshot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _build_test_approval_registry()
    _patch_test_approval_registry(monkeypatch, registry)
    seed = _seed_pending_approval(
        client,
        tool_name=_APPROVAL_TOOL_NAME,
        resource_preview="Approval Test Write\nCreates an approval-gated test resource.\nTitle: Approval issue",
    )
    headers = _auth_headers(seed["token"])
    captured: dict[str, Any] = {}

    async def fake_complete_chat_stream(*args: Any, **kwargs: Any):
        messages = kwargs["messages"]
        captured["messages"] = messages
        assistant_calls = [
            message
            for message in messages
            if message.get("role") == "assistant" and message.get("tool_calls")
        ]
        tool_messages = [message for message in messages if message.get("role") == "tool"]
        assert len(assistant_calls) == 1
        assert assistant_calls[0]["tool_calls"][0]["id"] == "call-1"
        assert len(tool_messages) == 1
        assert tool_messages[0]["tool_call_id"] == "call-1"
        yield (
            StreamChunk(kind="content", text="이슈를 생성했습니다."),
            None,
            None,
        )
        yield (
            StreamChunk(kind="done", finish_reason="stop"),
            None,
            None,
        )

    monkeypatch.setattr(ai_agent, "complete_chat_stream", fake_complete_chat_stream)

    resolve_response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert resolve_response.status_code == 200, resolve_response.text

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": seed["conversation_id"],
            "approval_id": seed["approval_id"],
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(response.text)
    assert [event["type"] for event in events] == [
        "approval_resolved",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert events[0]["data"] == {
        "approval_id": seed["approval_id"],
        "call_id": "call-1",
        "decision": "approved",
    }
    assert events[1]["data"]["status"] == "ok"
    assert events[2]["data"]["text"] == "이슈를 생성했습니다."
    assert events[3]["data"]["finish_reason"] == "stop"
    assert len(
        [
            message
            for message in captured["messages"]
            if message.get("role") == "assistant" and message.get("tool_calls")
        ]
    ) == 1

    with get_session_factory()() as db:
        approval = db.scalar(
            select(ai_approvals.AiToolApproval).where(
                ai_approvals.AiToolApproval.id == seed["approval_id"]
            )
        )
        snapshot = ai_approvals.load_snapshot(db, agent_run_id=seed["agent_run_id"])
        assert approval is not None
        assert approval.status == "executed"
        assert json.loads(approval.execution_result_json or "{}") == {
            "id": "approval-approval-issue",
            "title": "Approval issue",
        }
        assert snapshot.status == "completed"


def test_chat_resume_replays_rejected_tool_without_running_handler(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler_calls: list[dict[str, Any]] = []

    def handler(
        db: Any,
        workspace: Any,
        principal: Any,
        user: Any,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        del db, workspace, principal, user
        handler_calls.append(arguments)
        return {"id": "unexpected", "title": arguments["title"]}

    registry = _build_test_approval_registry(handler=handler)
    _patch_test_approval_registry(monkeypatch, registry)
    seed = _seed_pending_approval(
        client,
        tool_name=_APPROVAL_TOOL_NAME,
        resource_preview="Approval Test Write\nCreates an approval-gated test resource.\nTitle: Approval issue",
    )
    headers = _auth_headers(seed["token"])

    async def fake_complete_chat_stream(*args: Any, **kwargs: Any):
        messages = kwargs["messages"]
        assistant_calls = [
            message
            for message in messages
            if message.get("role") == "assistant" and message.get("tool_calls")
        ]
        tool_messages = [message for message in messages if message.get("role") == "tool"]
        assert len(assistant_calls) == 1
        assert len(tool_messages) == 1
        assert '"status": "rejected"' in tool_messages[0]["content"]
        yield (
            StreamChunk(kind="content", text="승인이 거절되어 실행하지 않았습니다."),
            None,
            None,
        )
        yield (
            StreamChunk(kind="done", finish_reason="stop"),
            None,
            None,
        )

    monkeypatch.setattr(ai_agent, "complete_chat_stream", fake_complete_chat_stream)

    resolve_response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "rejected", "reason": "not now"},
    )
    assert resolve_response.status_code == 200, resolve_response.text

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": seed["conversation_id"],
            "approval_id": seed["approval_id"],
        },
    )

    assert response.status_code == 200, response.text
    events = _parse_sse(response.text)
    assert [event["type"] for event in events] == [
        "approval_resolved",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert events[0]["data"] == {
        "approval_id": seed["approval_id"],
        "call_id": "call-1",
        "decision": "rejected",
        "reason": "not now",
    }
    assert events[1]["data"]["status"] == "rejected"
    assert events[2]["data"]["text"] == "승인이 거절되어 실행하지 않았습니다."
    assert not handler_calls

    with get_session_factory()() as db:
        approval = db.scalar(
            select(ai_approvals.AiToolApproval).where(
                ai_approvals.AiToolApproval.id == seed["approval_id"]
            )
        )
        snapshot = ai_approvals.load_snapshot(db, agent_run_id=seed["agent_run_id"])
        assert approval is not None
        assert approval.status == "rejected"
        assert json.loads(approval.execution_result_json or "{}") == {
            "status": "rejected",
            "reason": "not now",
        }
        assert snapshot.status == "completed"


def test_chat_resume_can_rehalt_after_replay(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _build_test_approval_registry()
    _patch_test_approval_registry(monkeypatch, registry)
    seed = _seed_pending_approval(
        client,
        tool_name=_APPROVAL_TOOL_NAME,
        arguments_json='{"title":"First approval issue"}',
        resource_preview="Approval Test Write\nCreates an approval-gated test resource.\nTitle: First approval issue",
    )
    headers = _auth_headers(seed["token"])

    async def fake_complete_chat_stream(*args: Any, **kwargs: Any):
        messages = kwargs["messages"]
        assistant_calls = [
            message
            for message in messages
            if message.get("role") == "assistant" and message.get("tool_calls")
        ]
        tool_messages = [message for message in messages if message.get("role") == "tool"]
        assert len(assistant_calls) == 1
        assert len(tool_messages) == 1
        yield (
            StreamChunk(
                kind="tool_call_start",
                tool_call_id="call-2",
                tool_name=_APPROVAL_TOOL_NAME,
            ),
            None,
            None,
        )
        yield (
            StreamChunk(
                kind="tool_call_args",
                tool_call_id="call-2",
                tool_name=_APPROVAL_TOOL_NAME,
                args_delta='{"title":"Follow up issue"}',
            ),
            None,
            None,
        )
        yield (
            StreamChunk(kind="done", finish_reason="tool_calls"),
            None,
            None,
        )

    monkeypatch.setattr(ai_agent, "complete_chat_stream", fake_complete_chat_stream)

    resolve_response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert resolve_response.status_code == 200, resolve_response.text

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": seed["conversation_id"],
            "approval_id": seed["approval_id"],
        },
    )

    assert response.status_code == 200, response.text
    events = _parse_sse(response.text)
    assert [event["type"] for event in events] == [
        "approval_resolved",
        "tool_result",
        "tool_call_started",
        "tool_call_args_delta",
        "approval_required",
        "done",
    ]
    new_approval_id = events[4]["data"]["approval_id"]
    new_agent_run_id = events[5]["data"]["meta"]["agent_run_id"]
    assert events[1]["data"]["status"] == "ok"
    assert events[4]["data"]["tool"] == _APPROVAL_TOOL_NAME
    assert events[5]["data"]["finish_reason"] == "awaiting_approval"
    assert new_approval_id != seed["approval_id"]
    assert new_agent_run_id != seed["agent_run_id"]

    with get_session_factory()() as db:
        approvals = list(
            db.scalars(
                select(ai_approvals.AiToolApproval).where(
                    ai_approvals.AiToolApproval.conversation_id == seed["conversation_id"]
                )
            )
        )
        snapshots = list(
            db.scalars(
                select(ai_approvals.AgentRunSnapshot).where(
                    ai_approvals.AgentRunSnapshot.conversation_id == seed["conversation_id"]
                )
            )
        )
        original_approval = next(item for item in approvals if item.id == seed["approval_id"])
        followup_approval = next(item for item in approvals if item.id == new_approval_id)
        original_snapshot = next(item for item in snapshots if item.id == seed["agent_run_id"])
        followup_snapshot = next(item for item in snapshots if item.id == new_agent_run_id)
        assert original_approval.status == "executed"
        assert followup_approval.status == "pending"
        assert original_snapshot.status == "completed"
        assert followup_snapshot.status == "awaiting_approval"
        assert sum(1 for item in snapshots if item.status == "awaiting_approval") == 1


def test_chat_resume_cancellation_rewinds_snapshot_for_retry(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _seed_pending_approval(client)
    headers = _auth_headers(seed["token"])

    resolve_response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert resolve_response.status_code == 200, resolve_response.text

    def fake_execute_tool_call(*args: Any, **kwargs: Any):
        del args, kwargs
        raise asyncio.CancelledError

    monkeypatch.setattr(ai_agent, "execute_tool_call", fake_execute_tool_call)

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": seed["conversation_id"],
            "approval_id": seed["approval_id"],
        },
    )

    assert response.status_code == 200, response.text

    with get_session_factory()() as db:
        approval = db.scalar(
            select(ai_approvals.AiToolApproval).where(
                ai_approvals.AiToolApproval.id == seed["approval_id"]
            )
        )
        snapshot = ai_approvals.load_snapshot(db, agent_run_id=seed["agent_run_id"])
        assert approval is not None
        assert approval.status == "approved"
        assert snapshot.status == "awaiting_approval"


def test_chat_resume_cancellation_after_tool_exec_does_not_rewind(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If cancel fires AFTER the approved tool executed, the snapshot must not
    rewind to awaiting_approval — otherwise a second resume would re-run the
    write and double its side effects.
    """
    seed = _seed_pending_approval(client)
    headers = _auth_headers(seed["token"])

    resolve_response = client.post(
        _workspace_ai_path(seed["workspace_slug"], f"/approvals/{seed['approval_id']}/resolve"),
        headers=headers,
        json={"decision": "approved"},
    )
    assert resolve_response.status_code == 200, resolve_response.text

    def fake_execute_tool_call(*args: Any, **kwargs: Any) -> ToolCallExecution:
        del args, kwargs
        return ToolCallExecution(
            call_id="call-1",
            tool_name="pms.create_issue",
            arguments_json='{"title":"ok"}',
            status="ok",
            response={"tool": "pms.create_issue", "result": {"ok": True}},
        )

    def fake_iter_tool_call_events(*args: Any, **kwargs: Any):
        del args, kwargs
        raise asyncio.CancelledError

    monkeypatch.setattr(ai_agent, "execute_tool_call", fake_execute_tool_call)
    monkeypatch.setattr(ai_agent, "iter_tool_call_events", fake_iter_tool_call_events)

    response = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": seed["conversation_id"],
            "approval_id": seed["approval_id"],
        },
    )

    assert response.status_code == 200, response.text

    with get_session_factory()() as db:
        approval = db.scalar(
            select(ai_approvals.AiToolApproval).where(
                ai_approvals.AiToolApproval.id == seed["approval_id"]
            )
        )
        snapshot = ai_approvals.load_snapshot(db, agent_run_id=seed["agent_run_id"])
        assert approval is not None
        # Tool already ran — snapshot must be completed (no re-execute path).
        assert snapshot.status == "completed"

    second_resume = client.post(
        _workspace_ai_path(seed["workspace_slug"], "/chat/resume"),
        headers=headers,
        json={
            "conversation_id": seed["conversation_id"],
            "approval_id": seed["approval_id"],
        },
    )
    assert second_resume.status_code == 410, second_resume.text
    assert "no longer resumable" in second_resume.json()["detail"]


def test_ai_tool_invoke_returns_409_for_approval_required_tool(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _build_test_approval_registry()
    _patch_test_approval_registry(monkeypatch, registry)
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    session = _dev_login(client, "delivery-hub-admin")

    response = client.post(
        _workspace_ai_path("delivery-hub", f"/tools/{_APPROVAL_TOOL_NAME}/invoke"),
        headers=_auth_headers(session["token"]),
        json={"arguments": {"title": "Approval issue"}},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
        f"AI tool requires approval before execution: {_APPROVAL_TOOL_NAME}"
    )


def test_mcp_call_tool_returns_409_for_approval_required_tool(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _build_test_approval_registry()
    _patch_test_approval_registry(monkeypatch, registry)
    seed = _seed_pending_approval(
        client,
        tool_name=_APPROVAL_TOOL_NAME,
    )

    with get_session_factory()() as db:
        user = load_user_graph(db, seed["user_id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == seed["workspace_slug"]))
        assert user is not None
        assert workspace is not None
        principal = user_principal(
            workspace_id=workspace.id,
            user_id=user.id,
            source="test.mcp",
        )

        with pytest.raises(HTTPException) as exc_info:
            ai_mcp.AiMcpClient(registry=registry).call_tool(
                db,
                workspace=workspace,
                principal=principal,
                user=user,
                tool_name=_APPROVAL_TOOL_NAME,
                arguments={"title": "Approval issue"},
                source="test.mcp",
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == (
        f"AI tool requires approval before execution: {_APPROVAL_TOOL_NAME}"
    )
