"""Route-level tests for ``/api/v1/ai/chat/stream``."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import socket
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
import httpx
from openai import OpenAIError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
import uvicorn

from aidoo_api.core import llm as llm_core
from aidoo_api.core.db import get_engine
from aidoo_api.core.llm_adapters import StreamChunk
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai import agent as ai_agent
from aidoo_api.domains.ai import approvals as ai_approvals
from aidoo_api.domains.ai.models import LlmPolicy
from aidoo_api.domains.ai import router as ai_router
from aidoo_api.domains.ai.runtime.models import AgentInvocation, AgentRun, AgentTraceEvent
from aidoo_api.domains.ai.runtime.graph_scheduler import GraphSchedulerError
from aidoo_api.domains.auth.models import AuditLog, Workspace, WorkspaceAppEntitlement
from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_meeting,
    _create_user_with_workspaces,
    _dev_login,
    _login,
)


@pytest.fixture(autouse=True)
def _reset_sse_starlette_app_status() -> None:
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit = False
    AppStatus.should_exit_event = None
    yield
    AppStatus.should_exit_event = None


def _delta(
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        reasoning=None,
        tool_calls=tool_calls,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)],
        usage=None,
    )


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


def _usage_tail(pt: int, ct: int, tt: int) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
        ),
    )


class _FakeAsyncStream:
    def __init__(self, chunks: list[Any], *, block_after_first: bool = False) -> None:
        self._chunks = list(chunks)
        self._index = 0
        self._block_after_first = block_after_first
        self.closed = False

    def __aiter__(self) -> "_FakeAsyncStream":
        return self

    async def __anext__(self) -> Any:
        if self._block_after_first and self._index == 1:
            await asyncio.sleep(60)
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk

    async def aclose(self) -> None:
        self.closed = True


class _FakeAsyncChatCompletions:
    def __init__(
        self,
        chunks: list[Any] | None = None,
        *,
        non_stream_content: str = "ok",
        error: Exception | None = None,
        block_after_first: bool = False,
    ) -> None:
        self._chunks = chunks or []
        self._non_stream_content = non_stream_content
        self._error = error
        self._block_after_first = block_after_first
        self.calls: list[dict[str, Any]] = []
        self.last_stream: _FakeAsyncStream | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        if kwargs.get("stream"):
            self.last_stream = _FakeAsyncStream(
                list(self._chunks),
                block_after_first=self._block_after_first,
            )
            return self.last_stream
        return SimpleNamespace(
            model=str(kwargs["model"]),
            choices=[SimpleNamespace(message=SimpleNamespace(content=self._non_stream_content))],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        )


class _FakeModels:
    def list(self) -> SimpleNamespace:
        return SimpleNamespace(data=[])


class _FakeAsyncPoolClient:
    def __init__(
        self,
        chunks: list[Any] | None = None,
        *,
        error: Exception | None = None,
        block_after_first: bool = False,
    ) -> None:
        self.chat = SimpleNamespace(
            completions=_FakeAsyncChatCompletions(
                chunks,
                error=error,
                block_after_first=block_after_first,
            )
        )
        self.models = _FakeModels()

    def with_options(self, **_: Any) -> "_FakeAsyncPoolClient":
        return self


class _FakeSyncChatCompletions:
    def __init__(
        self,
        *,
        content: str = "ok",
        finish_reason: str | None = "stop",
        error: Exception | None = None,
    ) -> None:
        self._content = content
        self._finish_reason = finish_reason
        self._error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return SimpleNamespace(
            model=str(kwargs["model"]),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._content),
                    finish_reason=self._finish_reason,
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        )


class _FakeSyncPoolClient:
    def __init__(
        self,
        *,
        content: str = "ok",
        finish_reason: str | None = "stop",
        error: Exception | None = None,
    ) -> None:
        self.chat = SimpleNamespace(
            completions=_FakeSyncChatCompletions(
                content=content,
                finish_reason=finish_reason,
                error=error,
            )
        )
        self.models = _FakeModels()

    def with_options(self, **_: Any) -> "_FakeSyncPoolClient":
        return self


class _SequencedAsyncChatCompletions:
    def __init__(self, chunk_sequences: list[list[Any]]) -> None:
        self._chunk_sequences = [list(chunks) for chunks in chunk_sequences]
        self.calls: list[dict[str, Any]] = []
        self.last_stream: _FakeAsyncStream | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        assert kwargs.get("stream") is True
        chunks = self._chunk_sequences.pop(0)
        self.last_stream = _FakeAsyncStream(chunks)
        return self.last_stream


class _SequencedAsyncPoolClient:
    def __init__(self, chunk_sequences: list[list[Any]]) -> None:
        self.chat = SimpleNamespace(completions=_SequencedAsyncChatCompletions(chunk_sequences))
        self.models = _FakeModels()

    def with_options(self, **_: Any) -> "_SequencedAsyncPoolClient":
        return self


def _workspace_ai_path(slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{slug}/ai{suffix}"


def _legacy_ai_path(suffix: str) -> str:
    return f"/api/v1/ai{suffix}"


def _seeded_dev_login(client: TestClient, account_key: str) -> dict:
    _bootstrap_admin_session(client)
    return _dev_login(client, account_key)


def _set_policy(task_kind: str, mode: str) -> None:
    with Session(get_engine()) as session:
        policy = session.scalar(select(LlmPolicy).where(LlmPolicy.task_kind == task_kind))
        assert policy is not None
        policy.policy_mode = mode
        session.add(policy)
        session.commit()


def _llm_audit_rows() -> list[AuditLog]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
        )


def _tool_audit_rows() -> list[AuditLog]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_tool_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
        )


def _tool_call_delta(
    *,
    index: int,
    tool_id: str,
    name: str | None = None,
    arguments: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        index=index,
        id=tool_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


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


def _stream_post(
    client: TestClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    response = client.post(url, headers=headers or {}, json=json_body or {})
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        return response.status_code, _parse_sse(response.text)
    return response.status_code, []


def _chat_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return events after the leading ``conversation_attached`` prefix.

    Every chat stream now opens with a ``conversation_attached`` envelope
    carrying the persisted conversation id — tests that only care about the
    content/tool/done contract use this helper to keep their assertions
    focused on the streamed response shape.
    """
    return [event for event in events if event.get("type") != "conversation_attached"]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@asynccontextmanager
async def _live_server(app: Any):
    port = _find_free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.05)
        else:  # pragma: no cover - defensive timeout
            raise RuntimeError("Timed out waiting for live test server startup")
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def _close_stream_after_first_event(
    client: TestClient,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any],
) -> None:
    async with _live_server(client.app) as base_url:
        async with httpx.AsyncClient(base_url=base_url) as async_client:
            async with async_client.stream(
                "POST",
                url,
                headers=headers,
                json=json_body,
            ) as response:
                assert response.status_code == 200
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        await response.aclose()
                        return
    raise AssertionError("stream opened but no data event was received")


@pytest.mark.anyio
async def test_chat_stream_disconnect_marks_audit_cancelled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="first"), _delta(content="second", finish_reason="stop")],
        block_after_first=True,
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    before = len(_llm_audit_rows())
    await _close_stream_after_first_event(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={"messages": [{"role": "user", "content": "hi"}]},
    )

    for _ in range(20):
        rows = _llm_audit_rows()
        if len(rows) > before:
            break
        await asyncio.sleep(0.05)
    rows = _llm_audit_rows()
    assert len(rows) == before + 1
    assert rows[-1].payload["status"] == "cancelled"
    assert pool_client.chat.completions.last_stream is not None
    assert pool_client.chat.completions.last_stream.closed is True


def test_chat_stream_rejects_openrouter_backend_mode(client: TestClient) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    before = len(_llm_audit_rows())
    response = client.post(
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "openrouter",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 400
    assert "no longer supported" in response.json()["detail"]
    assert len(_llm_audit_rows()) == before


def test_chat_stream_requires_auth(client: TestClient) -> None:
    response = client.post(
        _legacy_ai_path("/chat/stream"),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code in (401, 403)


def test_chat_stream_requires_workspace_membership(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    outsider = _create_user_with_workspaces(
        client,
        admin["token"],
        email="stream-outsider@aidoo.local",
        full_name="Stream Outsider",
        workspace_keys=[],
    )
    outsider_token = _login(
        client,
        outsider["user"]["email"],
        outsider["temporary_password"],
    )

    response = client.post(
        _workspace_ai_path("hq", "/chat/stream"),
        headers=_auth_headers(outsider_token),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code == 403


def test_chat_stream_includes_meeting_scope_prompt_for_scoped_conversation(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool: False)

    meeting = _create_meeting(client, auth["token"], title="Scoped meeting")

    from aidoo_api.domains.auth.models import User
    from aidoo_api.domains.conversations import service as conversations_service

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, auth["user"]["id"])
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
        conversation_id = conversation.id

    pool_client = _FakeAsyncPoolClient(
        [
            _delta(content="회의 범위를 반영했습니다."),
            _delta(finish_reason="stop"),
            _usage_tail(1, 2, 3),
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "conversation_id": conversation_id,
            "persist": True,
            "messages": [{"role": "user", "content": "회의 기준으로 정리해줘"}],
        },
    )

    assert status_code == 200
    assert _chat_events(events)[-1]["type"] == "done"
    sent_messages = pool_client.chat.completions.calls[0]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert "[회의 컨텍스트]" in sent_messages[0]["content"]
    assert "Scoped meeting" in sent_messages[0]["content"]


def test_chat_stream_emits_content_and_reasoning_in_order(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [
            _delta(reasoning_content="think"),
            _delta(content="Hi"),
            _delta(content=" there"),
            _delta(finish_reason="stop"),
            _usage_tail(1, 2, 3),
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "hi"}],
            "reasoning_effort": "medium",
        },
    )
    assert status_code == 200
    # When persistence is enabled, `conversation_attached` is emitted first
    # so the client learns which persisted conversation the turns are being
    # appended to before any rendering begins.
    assert [event["type"] for event in events] == [
        "conversation_attached",
        "reasoning_delta",
        "content_delta",
        "content_delta",
        "usage",
        "done",
    ]
    assert [event["seq"] for event in events] == list(range(len(events)))
    assert events[0]["data"]["conversation_id"]
    done = events[-1]
    assert done["data"]["finish_reason"] == "stop"
    assert done["data"]["meta"]["chosen_pool"] == "local"
    rows = _llm_audit_rows()
    assert rows[-1].payload["status"] == "ok"
    assert rows[-1].payload["usage"] == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }


def test_chat_stream_suppresses_reasoning_when_stream_reasoning_false(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(
        [
            _delta(reasoning_content="should-not-appear"),
            _delta(content="ok", finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "messages": [{"role": "user", "content": "hi"}],
            "reasoning_effort": "medium",
            "stream_reasoning": False,
        },
    )
    assert [event["type"] for event in _chat_events(events)] == [
        "content_delta",
        "done",
    ]
    assert pool_client.chat.completions.calls[0]["extra_body"] == {"think": False}


def test_chat_stream_tool_command_emits_tool_events_without_llm_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(auth["token"]),
        json={
            "key": "AISTRM",
            "name": "AI Stream Tool List",
            "description": "tool command source",
        },
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(auth["token"]),
        json={"title": "AI stream tool issue", "description": "stream search target"},
    )
    assert issue_response.status_code == 201, issue_response.text

    def _unexpected_pool_call(pool):  # type: ignore[no-untyped-def]
        raise AssertionError(f"LLM pool should not be called for /tool commands: {pool}")

    monkeypatch.setattr(llm_core, "get_async_pool_client", _unexpected_pool_call)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "messages": [
                {
                    "role": "user",
                    "content": '/tool pms.search_issues {"q":"AI stream tool issue","limit":5}',
                }
            ]
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert chat[0]["data"]["name"] == "pms.search_issues"
    assert chat[2]["data"]["status"] == "ok"
    assert "AI stream tool issue" in chat[3]["data"]["text"]
    assert chat[4]["data"]["finish_reason"] == "stop"
    assert chat[4]["data"]["meta"]["provider"] == "tool"


def test_chat_stream_tool_command_scoped_conversation_skips_scope_prompt_lookup(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    meeting = _create_meeting(client, auth["token"], title="Scoped AI stream meeting")

    conversation_response = client.post(
        _workspace_ai_path(slug, "/conversations"),
        headers=_auth_headers(auth["token"]),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )
    assert conversation_response.status_code == 201, conversation_response.text
    conversation_id = conversation_response.json()["id"]

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(auth["token"]),
        json={
            "key": "AISTRMSC",
            "name": "AI Scoped Stream List",
            "description": "tool command source",
        },
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(auth["token"]),
        json={"title": "Scoped AI stream tool issue", "description": "stream search target"},
    )
    assert issue_response.status_code == 201, issue_response.text

    def _unexpected_scope_prompt(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("scope prompt lookup should not run for /tool commands")

    def _unexpected_pool_call(pool):  # type: ignore[no-untyped-def]
        raise AssertionError(f"LLM pool should not be called for /tool commands: {pool}")

    monkeypatch.setattr(
        ai_router.meeting_service,
        "build_meeting_scope_prompt",
        _unexpected_scope_prompt,
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", _unexpected_pool_call)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "conversationId": conversation_id,
            "messages": [
                {
                    "role": "user",
                    "content": '/tool pms.search_issues {"q":"Scoped AI stream tool issue","limit":5}',
                }
            ],
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert chat[0]["data"]["name"] == "pms.search_issues"
    assert chat[2]["data"]["status"] == "ok"
    assert "Scoped AI stream tool issue" in chat[3]["data"]["text"]
    assert chat[4]["data"]["finish_reason"] == "stop"


def test_chat_stream_agent_loop_executes_tool_and_keeps_shared_agent_run_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(auth["token"]),
        json={
            "key": "AIACT",
            "name": "AI Agent Loop List",
            "description": "agent loop source",
        },
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(auth["token"]),
        json={"title": "Agent loop issue", "description": "agent result target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    pool_client = _SequencedAsyncPoolClient(
        [
            [
                _delta(
                    tool_calls=[
                        _tool_call_delta(
                            index=0,
                            tool_id="call-1",
                            name="pms.search_issues",
                            arguments='{"q":"Agent loop issue","limit":5}',
                        )
                    ]
                ),
                _delta(finish_reason="tool_calls"),
            ],
            [
                _delta(content="Agent loop issue를 찾았습니다.", finish_reason="stop"),
                _usage_tail(1, 2, 3),
            ],
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "messages": [{"role": "user", "content": "오늘 내 이슈 보여줘"}],
            "persist": True,
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "usage",
        "done",
    ]
    assert chat[2]["data"]["status"] == "ok"
    assert issue["id"] in _tool_audit_rows()[-1].payload["resource_ids"]

    llm_rows = _llm_audit_rows()[-2:]
    tool_row = _tool_audit_rows()[-1]
    attached = next(event for event in events if event["type"] == "conversation_attached")
    assert len({row.payload["agent_run_id"] for row in llm_rows}) == 1
    assert tool_row.payload["agent_run_id"] == llm_rows[-1].payload["agent_run_id"]
    assert {row.payload["conversation_id"] for row in llm_rows} == {attached["data"]["conversation_id"]}
    assert all(isinstance(row.payload["trace_id"], str) and row.payload["trace_id"] for row in llm_rows)
    assert tool_row.payload["conversation_id"] == attached["data"]["conversation_id"]
    assert isinstance(tool_row.payload["trace_id"], str) and tool_row.payload["trace_id"]


def test_chat_stream_agent_loop_halts_for_approval_required_tool(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")

    async def fake_complete_chat_stream(*args: Any, **kwargs: Any):
        yield (
            StreamChunk(
                kind="tool_call_start",
                tool_call_id="call-1",
                tool_name="pms.create_issue",
            ),
            None,
            None,
        )
        yield (
            StreamChunk(
                kind="tool_call_args",
                tool_call_id="call-1",
                tool_name="pms.create_issue",
                args_delta='{"title":"Approval issue"}',
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

    def blocked_tool_call(*args: Any, **kwargs: Any):
        return ai_router.ToolCallExecution(
            call_id="call-1",
            tool_name="pms.create_issue",
            arguments_json='{"title":"Approval issue"}',
            status="blocked",
            resource_preview="Create PMS issue Approval issue",
        )

    monkeypatch.setattr(ai_agent, "execute_tool_call", blocked_tool_call)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "messages": [{"role": "user", "content": "이슈 만들어줘"}],
            "persist": True,
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == [
        "tool_call_started",
        "tool_call_args_delta",
        "approval_required",
        "done",
    ]
    assert chat[2]["data"]["tool"] == "pms.create_issue"
    assert chat[3]["data"]["finish_reason"] == "awaiting_approval"
    approval_id = chat[2]["data"]["approval_id"]
    agent_run_id = chat[3]["data"]["meta"]["agent_run_id"]
    assert approval_id
    assert agent_run_id

    with Session(get_engine()) as session:
        approval = session.scalar(
            select(ai_approvals.AiToolApproval).where(
                ai_approvals.AiToolApproval.id == approval_id
            )
        )
        snapshot = session.scalar(
            select(ai_approvals.AgentRunSnapshot).where(
                ai_approvals.AgentRunSnapshot.id == agent_run_id
            )
        )
        assert approval is not None
        assert snapshot is not None
        assert approval.status == "pending"
        assert snapshot.status == "awaiting_approval"


def test_chat_stream_agent_loop_halt_preserves_graph_schedule_summary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_runtime_graph_enabled", True)
    monkeypatch.setattr(settings, "ai_tool_calling_enabled", True)

    async def fake_complete_chat_stream(*args: Any, **kwargs: Any):
        yield (
            StreamChunk(
                kind="tool_call_start",
                tool_call_id="call-1",
                tool_name="pms.create_issue",
            ),
            None,
            None,
        )
        yield (
            StreamChunk(
                kind="tool_call_args",
                tool_call_id="call-1",
                tool_name="pms.create_issue",
                args_delta='{"title":"Approval issue"}',
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

    def blocked_tool_call(*args: Any, **kwargs: Any):
        return ai_router.ToolCallExecution(
            call_id="call-1",
            tool_name="pms.create_issue",
            arguments_json='{"title":"Approval issue"}',
            status="blocked",
            resource_preview="Create PMS issue Approval issue",
        )

    monkeypatch.setattr(ai_agent, "execute_tool_call", blocked_tool_call)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "messages": [{"role": "user", "content": "PMS 이슈를 만들어줘"}],
            "persist": True,
            "allowed_app_ids": ["pms"],
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == [
        "tool_call_started",
        "tool_call_args_delta",
        "approval_required",
        "done",
    ]
    done_meta = chat[-1]["data"]["meta"]
    graph_schedule = done_meta["graph_schedule_summary"]
    assert done_meta["runtime_profile"] == "high_risk_action"
    assert done_meta["graph_validation_status"] == "accepted"
    assert done_meta["graph_execution_status"] == "disabled"
    assert done_meta["graph_execution_fallback_reason"] == "graph_execution_disabled"
    assert graph_schedule["state"] == "planned"
    assert graph_schedule["execution_enabled"] is False
    assert graph_schedule["planned_agent_ids"] == [
        "domain.pms",
        "approval.proposal_preview",
    ]
    approval_id = chat[2]["data"]["approval_id"]
    agent_run_id = done_meta["agent_run_id"]
    assert approval_id
    assert agent_run_id

    with Session(get_engine()) as session:
        approval = session.scalar(
            select(ai_approvals.AiToolApproval).where(
                ai_approvals.AiToolApproval.id == approval_id
            )
        )
        snapshot = session.scalar(
            select(ai_approvals.AgentRunSnapshot).where(
                ai_approvals.AgentRunSnapshot.id == agent_run_id
            )
        )
        runtime_run = session.get(AgentRun, agent_run_id)
        invocations = list(
            session.scalars(
                select(AgentInvocation)
                .where(AgentInvocation.agent_run_id == agent_run_id)
                .order_by(AgentInvocation.invocation_seq)
            )
        )
        trace_events = list(
            session.scalars(
                select(AgentTraceEvent)
                .where(AgentTraceEvent.agent_run_id == agent_run_id)
                .order_by(AgentTraceEvent.event_seq)
            )
        )

    assert approval is not None
    assert snapshot is not None
    assert runtime_run is not None
    assert approval.status == "pending"
    assert snapshot.status == "awaiting_approval"
    assert runtime_run.status == "awaiting_approval"
    assert runtime_run.graph_enabled is True
    assert snapshot.model_meta["graph_schedule_summary"] == graph_schedule
    assert snapshot.model_meta["graph_execution_status"] == "disabled"
    assert snapshot.model_meta["graph_execution_fallback_reason"] == "graph_execution_disabled"
    assert [invocation.agent_id for invocation in invocations] == graph_schedule[
        "planned_agent_ids"
    ]
    assert [invocation.status for invocation in invocations] == [
        "pending",
        "awaiting_approval",
    ]
    replay = ai_approvals.rehydrate_model_meta(snapshot)
    assert replay.raw["graph_schedule_summary"] == graph_schedule
    assert replay.raw["graph_execution_status"] == "disabled"
    event_types = [event.event_type for event in trace_events]
    assert event_types[:4] == [
        "run_created",
        "graph_candidate_generated",
        "graph_candidate_validated",
        "graph_schedule_planned",
    ]
    assert event_types.count("graph_node_planned") == graph_schedule["step_count"]
    planned_events = [
        event for event in trace_events if event.event_type == "graph_node_planned"
    ]
    assert all(event.agent_invocation_id for event in planned_events)
    assert "graph_execution_gate_evaluated" in event_types


def test_chat_stream_agent_loop_uses_filtered_tool_specs_from_mcp_manifest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")
    _disable_workspace_app(slug, "planner")

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(auth["token"]),
        json={
            "key": "AIFILTER",
            "name": "AI Filtered Loop List",
            "description": "filtered agent loop source",
        },
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(auth["token"]),
        json={"title": "Filtered loop issue", "description": "visible result"},
    )
    assert issue_response.status_code == 201, issue_response.text

    pool_client = _SequencedAsyncPoolClient(
        [
            [
                _delta(
                    tool_calls=[
                        _tool_call_delta(
                            index=0,
                            tool_id="call-1",
                            name="pms.search_issues",
                            arguments='{"q":"Filtered loop issue","limit":5}',
                        )
                    ]
                ),
                _delta(finish_reason="tool_calls"),
            ],
            [
                _delta(content="Filtered loop issue를 찾았습니다.", finish_reason="stop"),
                _usage_tail(1, 2, 3),
            ],
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={"messages": [{"role": "user", "content": "필터된 도구로 이슈 보여줘"}]},
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "usage",
        "done",
    ]
    tool_names = [
        tool["function"]["name"] for tool in pool_client.chat.completions.calls[0]["tools"]
    ]
    assert "pms.search_issues" in tool_names
    assert "planner.list_events" not in tool_names


def test_chat_stream_falls_back_to_plain_chat_when_tools_are_not_supported(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient([_delta(content="plain response", finish_reason="stop")])
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool: False)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={"messages": [{"role": "user", "content": "hi"}]},
    )

    assert status_code == 200
    assert [event["type"] for event in _chat_events(events)] == [
        "content_delta",
        "done",
    ]
    assert pool_client.chat.completions.calls[0].get("tools") is None


def test_chat_stream_provider_error_emits_error_and_done_and_audits_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(error=OpenAIError("backend down"))
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == ["error", "done"]
    assert chat[0]["data"]["code"] == "provider_error"
    assert chat[1]["data"]["finish_reason"] == "error"
    assert _llm_audit_rows()[-1].payload["status"] == "error"


def test_chat_stream_generic_adapter_error_emits_error_contract(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(error=RuntimeError("adapter boom"))
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == ["error", "done"]
    assert chat[0]["data"]["code"] == "adapter_error"
    assert chat[0]["data"]["message"] == "adapter boom"
    assert _llm_audit_rows()[-1].payload["status"] == "error"


def test_chat_stream_local_only_policy_local_fail_no_external_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    local_pool = _FakeAsyncPoolClient(error=OpenAIError("local down"))
    external_pool = _FakeAsyncPoolClient(
        [_delta(content="should not be used", finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool: local_pool if pool == "local" else external_pool,
    )

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert [event["type"] for event in _chat_events(events)] == ["error", "done"]
    assert external_pool.chat.completions.calls == []
    assert _llm_audit_rows()[-1].payload["status"] == "error"


def test_chat_stream_done_meta_uses_requested_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")
    settings = get_settings()

    pool_client = _FakeAsyncPoolClient([_delta(content="ok", finish_reason="stop")])
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "model": settings.llm_local_canonical_model,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    done_meta = events[-1]["data"]["meta"]
    assert done_meta["policy"] == "external"
    assert done_meta["chosen_pool"] == "local"
    assert done_meta["decision_reason"] == "local_hint"
    assert done_meta["forced_local"] is True
    assert done_meta["pii_hits"] == []
    assert done_meta["model"] == settings.llm_local_canonical_model
    assert done_meta["chosen_model"] == settings.llm_local_canonical_model
    assert done_meta["provider"]
    assert "runtime_profile" in done_meta, done_meta
    assert done_meta["runtime_profile"] == "interactive_read"
    assert done_meta["graph_gate"] == "disabled"
    assert done_meta["graph_fallback_reason"] == "feature_disabled"
    assert done_meta["graph_used"] is False
    assert done_meta["graph_validation_status"] == "not_applicable"
    assert done_meta.get("graph_validation_fallback_reason") is None
    assert done_meta["graph_registry_agent_count"] == 0
    assert done_meta["graph_write_agent_count"] == 0
    assert done_meta["graph_execution_status"] == "not_applicable"
    assert done_meta.get("graph_execution_fallback_reason") is None


def test_chat_stream_graph_gate_falls_back_without_graph_execution(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_runtime_graph_enabled", True)
    monkeypatch.setattr(settings, "ai_tool_calling_enabled", False)

    pool_client = _FakeAsyncPoolClient([_delta(content="ok", finish_reason="stop")])
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [
                {
                    "role": "user",
                    "content": "회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘",
                }
            ],
            "allowed_app_ids": ["meeting", "pms"],
        },
    )

    assert status_code == 200
    done_meta = events[-1]["data"]["meta"]
    assert "runtime_profile" in done_meta, done_meta
    assert done_meta["runtime_profile"] == "grounded_report"
    assert done_meta["runtime_routing_reason_codes"] == ["grounded_report_signal"]
    assert done_meta["graph_gate"] == "eligible"
    assert done_meta["graph_fallback_reason"] == "graph_runtime_not_implemented"
    assert done_meta["graph_used"] is False
    assert done_meta["agent_run_id"]
    assert done_meta["graph_validation_status"] == "accepted"
    assert done_meta["graph_execution_status"] == "disabled"
    assert done_meta["graph_execution_fallback_reason"] == "graph_execution_disabled"
    assert done_meta.get("graph_validation_fallback_reason") is None
    assert done_meta["graph_registry_agent_count"] > 0
    assert done_meta["graph_write_agent_count"] == 1
    graph_summary = done_meta["graph_candidate_summary"]
    assert graph_summary["intent"] == "report"
    assert set(graph_summary["domains"]) >= {"meeting", "pms", "rag"}
    assert graph_summary["risk"] == "medium"
    assert graph_summary["output_kind"] == "artifact"
    assert "writer.template" in graph_summary["invocation_agent_ids"]
    assert graph_summary["requires_verifier"] is True
    assert graph_summary["requires_approval_preview"] is False
    assert set(graph_summary) == {
        "intent",
        "domains",
        "risk",
        "output_kind",
        "invocation_agent_ids",
        "requires_verifier",
        "requires_approval_preview",
    }
    graph_schedule = done_meta["graph_schedule_summary"]
    assert graph_schedule["state"] == "planned"
    assert graph_schedule["execution_enabled"] is False
    assert graph_schedule["step_count"] == len(graph_summary["invocation_agent_ids"])
    assert graph_schedule["planned_agent_ids"] == graph_summary["invocation_agent_ids"]
    attached = next(event for event in events if event["type"] == "conversation_attached")
    agent_run_id = done_meta["agent_run_id"]
    with Session(get_engine()) as session:
        runtime_run = session.get(AgentRun, agent_run_id)
        assert runtime_run is not None
        assert runtime_run.status == "completed"
        assert runtime_run.conversation_id == attached["data"]["conversation_id"]
        assert runtime_run.legacy_snapshot_id is None
        assert runtime_run.runtime_profile == "grounded_report"
        assert runtime_run.graph_enabled is True
        assert runtime_run.fallback_reason == "graph_runtime_not_implemented"
        invocations = list(
            session.scalars(
                select(AgentInvocation)
                .where(AgentInvocation.agent_run_id == agent_run_id)
                .order_by(AgentInvocation.invocation_seq)
            )
        )
        trace_events = list(
            session.scalars(
                select(AgentTraceEvent)
                .where(AgentTraceEvent.agent_run_id == agent_run_id)
                .order_by(AgentTraceEvent.event_seq)
            )
        )
    planned_invocations = [
        invocation
        for invocation in invocations
        if invocation.agent_id != "single_loop.fallback"
    ]
    assert [invocation.agent_id for invocation in planned_invocations] == graph_schedule[
        "planned_agent_ids"
    ]
    assert {invocation.status for invocation in planned_invocations} == {"abandoned"}
    fallback_invocation = next(
        invocation for invocation in invocations if invocation.agent_id == "single_loop.fallback"
    )
    assert fallback_invocation.status == "completed"
    assert fallback_invocation.invocation_seq == graph_schedule["step_count"]
    event_types = [event.event_type for event in trace_events]
    assert event_types[:4] == [
        "run_created",
        "graph_candidate_generated",
        "graph_candidate_validated",
        "graph_schedule_planned",
    ]
    assert event_types.count("graph_node_planned") == graph_schedule["step_count"]
    assert all(
        event.agent_invocation_id
        for event in trace_events
        if event.event_type == "graph_node_planned"
    )
    assert "graph_execution_gate_evaluated" in event_types
    assert event_types[-3:] == ["invocation_started", "invocation_completed", "run_completed"]
    assert trace_events[1].payload_json["graph_candidate_summary"]["output_kind"] == "artifact"
    schedule_event = next(
        event for event in trace_events if event.event_type == "graph_schedule_planned"
    )
    assert schedule_event.payload_json["graph_schedule_summary"]["state"] == "planned"

    inspection = client.get(
        _workspace_ai_path(slug, f"/runtime/runs/{agent_run_id}"),
        headers=_auth_headers(auth["token"]),
    )
    assert inspection.status_code == 200, inspection.text
    inspected = inspection.json()
    assert inspected["status"] == "completed"
    inspected_trace = {
        event["event_type"]: event["payload"] for event in inspected["trace_events"]
    }
    assert (
        inspected_trace["graph_candidate_generated"]["graph_candidate_summary"][
            "output_kind"
        ]
        == "artifact"
    )
    assert inspected_trace["graph_schedule_planned"]["graph_schedule_summary"][
        "execution_enabled"
    ] is False


def test_chat_stream_graph_schedule_failure_remains_fallback_metadata(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_runtime_graph_enabled", True)
    monkeypatch.setattr(settings, "ai_tool_calling_enabled", False)

    def fail_schedule(*args: Any, **kwargs: Any):
        del args, kwargs
        raise GraphSchedulerError("cyclic invocation dependency: ['writer.template']")

    monkeypatch.setattr(ai_router, "build_graph_execution_schedule", fail_schedule)

    pool_client = _FakeAsyncPoolClient([_delta(content="ok", finish_reason="stop")])
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [
                {
                    "role": "user",
                    "content": "회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘",
                }
            ],
            "allowed_app_ids": ["meeting", "pms"],
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == ["content_delta", "done"]
    done_meta = chat[-1]["data"]["meta"]
    assert done_meta["graph_validation_status"] == "accepted"
    assert done_meta["graph_candidate_summary"]["intent"] == "report"
    assert done_meta["graph_execution_status"] == "not_applicable"
    assert done_meta["graph_execution_fallback_reason"] == "graph_schedule_unavailable"
    assert done_meta["graph_schedule_summary"] == {
        "state": "failed",
        "execution_enabled": False,
        "fallback_reason": "graph_schedule_failed",
        "error_type": "GraphSchedulerError",
        "error": "cyclic invocation dependency: ['writer.template']",
        "step_count": 0,
        "planned_agent_ids": [],
        "steps": [],
    }

    inspection = client.get(
        _workspace_ai_path(slug, f"/runtime/runs/{done_meta['agent_run_id']}"),
        headers=_auth_headers(auth["token"]),
    )
    assert inspection.status_code == 200, inspection.text
    event_types = [event["event_type"] for event in inspection.json()["trace_events"]]
    assert "graph_schedule_failed" in event_types
    assert "graph_node_planned" not in event_types


def test_chat_stream_mounts_on_legacy_and_slug_paths(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    def build_pool(_pool: str) -> _FakeAsyncPoolClient:
        return _FakeAsyncPoolClient([_delta(content="ok", finish_reason="stop")])

    monkeypatch.setattr(llm_core, "get_async_pool_client", build_pool)

    for path in (
        _legacy_ai_path("/chat/stream"),
        _workspace_ai_path(slug, "/chat/stream"),
    ):
        status_code, events = _stream_post(
            client,
            path,
            headers=_auth_headers(auth["token"]),
            json_body={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert status_code == 200, path
        assert [event["type"] for event in _chat_events(events)] == [
            "content_delta",
            "done",
        ]


def test_chat_sync_persists_user_and_assistant_turns_and_returns_conversation_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeSyncPoolClient(content="echo: hi")
    monkeypatch.setattr(llm_core, "get_pool_client", lambda pool: pool_client)

    response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    conversation_id = body["conversation_id"]
    assert conversation_id
    assert body["content"] == "echo: hi"

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [turn["role"] for turn in detail["turns"]] == ["user", "assistant"]
    assert detail["turns"][0]["content"] == "hi"
    assert detail["turns"][1]["content"] == "echo: hi"


def test_chat_sync_appends_to_existing_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    monkeypatch.setattr(
        llm_core, "get_pool_client", lambda pool: _FakeSyncPoolClient(content="first")
    )
    first = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "first question"}],
        },
    )
    assert first.status_code == 200, first.text
    conversation_id = first.json()["conversation_id"]

    monkeypatch.setattr(
        llm_core, "get_pool_client", lambda pool: _FakeSyncPoolClient(content="second")
    )
    second = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "follow up"}],
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["conversation_id"] == conversation_id

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [turn["role"] for turn in detail["turns"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert detail["turns"][2]["content"] == "follow up"
    assert detail["turns"][3]["content"] == "second"


def test_chat_sync_persists_artifact_only_response_into_turn_meta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool: _FakeSyncPoolClient(
            content='<artifact type="document" title="Draft">body</artifact>'
        ),
    )

    response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "generate draft"}],
        },
    )
    assert response.status_code == 200, response.text
    conversation_id = response.json()["conversation_id"]

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant = detail["turns"][-1]
    assert assistant["content"] == ""
    assert assistant["artifacts"] == [
        {
            "id": assistant["artifacts"][0]["id"],
            "type": "document",
            "title": "Draft",
            "language": None,
            "content": "body",
            "status": "closed",
        }
    ]


def test_chat_sync_preserves_literal_artifact_syntax_examples_as_plain_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    literal_example = (
        "형식은 다음과 같습니다:\n"
        '    <artifact type="document" title="Draft">\n'
        "    markdown 본문...\n"
        "    </artifact>"
    )
    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool: _FakeSyncPoolClient(content=literal_example),
    )

    response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "artifact 형식을 설명해줘"}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"] == literal_example
    assert body["artifacts"] == []

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{body['conversation_id']}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant = detail["turns"][-1]
    assert assistant["content"] == literal_example
    assert assistant["artifacts"] == []


def test_chat_stream_persists_user_and_assistant_turns(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A full round trip through the stream must land the user message and the
    # finalized assistant message on the attached Conversation so reloading
    # the sidebar later restores the thread exactly as it was.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [
            _delta(content="echo: "),
            _delta(content="hi"),
            _delta(finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert status_code == 200
    attached = [e for e in events if e["type"] == "conversation_attached"]
    assert len(attached) == 1
    conversation_id = attached[0]["data"]["conversation_id"]

    # Detail API should now return the user + assistant turn pair.
    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [t["role"] for t in detail["turns"]] == ["user", "assistant"]
    assert detail["turns"][0]["content"] == "hi"
    assert detail["turns"][1]["content"] == "echo: hi"
    # Auto-title picks up the first user message.
    assert detail["title"].startswith("hi")

    # Listing surfaces the new conversation newest-first.
    listing = client.get(
        f"/api/v1/workspaces/{slug}/conversations",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert listing["items"][0]["id"] == conversation_id


def test_chat_stream_appends_to_existing_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    # Start a conversation with a first exchange.
    pool_client = _FakeAsyncPoolClient([_delta(content="first", finish_reason="stop")])
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)
    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "first question"}],
        },
    )
    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]

    # Resume the same conversation — passing conversation_id must NOT create a
    # new row and the second turn pair must append after seq 0/1.
    pool_client_second = _FakeAsyncPoolClient([_delta(content="second", finish_reason="stop")])
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client_second)
    _, events2 = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "follow up"}],
        },
    )
    attached2 = next(e for e in events2 if e["type"] == "conversation_attached")
    assert attached2["data"]["conversation_id"] == conversation_id

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [t["role"] for t in detail["turns"]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert detail["turns"][2]["content"] == "follow up"
    assert detail["turns"][3]["content"] == "second"


def test_chat_stream_rejects_unknown_conversation_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A bogus conversation_id must NOT silently create a fresh conversation —
    # surface an SSE error envelope so the client can recover deterministically.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    def _should_not_be_called(_pool):
        raise AssertionError("stream should short-circuit before hitting the LLM")

    monkeypatch.setattr(llm_core, "get_async_pool_client", _should_not_be_called)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "conversation_id": "does-not-exist",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert status_code == 200
    # Must emit both error AND done — the client's useChatStream state
    # machine only leaves `streaming` on a terminal `done` envelope, so an
    # error-only response would leave the UI hung forever.
    assert [e["type"] for e in events] == ["error", "done"]
    assert events[0]["data"]["code"] == "conversation_not_found"
    assert events[1]["data"]["finish_reason"] == "error"


def test_chat_stream_persist_false_skips_conversation_creation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Default behavior for legacy callers: no conversation_id and no persist
    # flag means the stream completes without creating a Conversation row —
    # otherwise every request from the current web client would fork a new
    # one-turn conversation until Phase 3.3 threads conversation_id back.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient([_delta(content="ok", finish_reason="stop")])
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert not [e for e in events if e["type"] == "conversation_attached"]
    listing = client.get(
        f"/api/v1/workspaces/{slug}/conversations",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert listing["items"] == []


def test_chat_stream_persists_failure_with_empty_body(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: when the provider errors before emitting any content, the
    # assistant turn still has to land so the reloaded history reflects what
    # the live stream showed (an error bubble). An empty, body-less turn was
    # previously dropped, making the request look unanswered.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(error=RuntimeError("boom"))
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "please fail"}],
        },
    )
    assert status_code == 200
    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    roles = [t["role"] for t in detail["turns"]]
    assert roles == ["user", "assistant"], f"expected user+assistant, got {roles}"
    assistant_turn = detail["turns"][1]
    # The streamed error message becomes the assistant content so reloaded
    # threads show the failure text the live bubble displayed, rather than
    # an empty assistant bubble.
    assert "boom" in assistant_turn["content"]
    assert assistant_turn["responseStatus"] == "error"
    assert assistant_turn["finishReason"] == "error"


def test_chat_stream_persists_length_finish_with_empty_body(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [_delta(finish_reason="length"), _usage_tail(1, 4096, 4097)]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "loop"}],
        },
    )
    assert status_code == 200
    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant_turn = detail["turns"][1]
    assert "토큰 한도" in assistant_turn["content"]
    assert assistant_turn["finishReason"] == "length"
    assert assistant_turn["responseStatus"] == "done"


def test_chat_stream_extracts_artifact_markup_into_dedicated_envelopes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A single content chunk carrying `<artifact>...</artifact>` must surface
    # as content_delta (prefix) → artifact_started/delta/completed →
    # content_delta (suffix). The inline markup never reaches the client as
    # plain content.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool: False)

    pool_client = _FakeAsyncPoolClient(
        [
            _delta(
                content=(
                    "Here you go: "
                    '<artifact type="document" title="Email">**draft** body</artifact>'
                    " — let me know."
                ),
            ),
            _delta(finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "write an email draft"}],
        },
    )
    assert status_code == 200
    chat = _chat_events(events)
    types = [event["type"] for event in chat]
    assert types == [
        "content_delta",
        "artifact_started",
        "artifact_delta",
        "artifact_completed",
        "content_delta",
        "done",
    ]
    # Prefix / suffix text flows as plain content_delta, artifact body is
    # routed exclusively through artifact_delta.
    assert chat[0]["data"]["text"] == "Here you go: "
    start_data = chat[1]["data"]
    assert start_data["artifact_type"] == "document"
    assert start_data["title"] == "Email"
    assert chat[2]["data"]["artifact_id"] == start_data["artifact_id"]
    assert chat[2]["data"]["delta"] == "**draft** body"
    assert chat[3]["data"]["artifact_id"] == start_data["artifact_id"]
    assert chat[4]["data"]["text"] == " — let me know."


def test_chat_stream_persists_artifact_into_turn_meta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The assistant turn row on disk must include the artifact so reload
    # restores the side panel content.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool: False)

    pool_client = _FakeAsyncPoolClient(
        [
            _delta(
                content=(
                    'summary<artifact type="document" title="Report">'
                    "- line one\n- line two</artifact>"
                ),
            ),
            _delta(finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "generate report"}],
        },
    )
    assert status_code == 200
    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]

    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant = detail["turns"][-1]
    assert assistant["role"] == "assistant"
    artifacts = assistant["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "document"
    assert artifacts[0]["title"] == "Report"
    assert artifacts[0]["content"] == "- line one\n- line two"


def test_chat_stream_code_artifact_language_roundtrips_through_stream_and_persistence(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `type="code"` artifacts carry a `language` hint on the open tag. It
    # must surface on the live `artifact_started` envelope AND on the
    # persisted turn so reload picks the right syntax highlighter.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool: False)

    pool_client = _FakeAsyncPoolClient(
        [
            _delta(
                content=(
                    '<artifact type="code" language="python" title="Hello">print("hi")</artifact>'
                ),
            ),
            _delta(finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "python hello"}],
        },
    )
    assert status_code == 200
    chat = _chat_events(events)
    started = next(event for event in chat if event["type"] == "artifact_started")
    assert started["data"]["artifact_type"] == "code"
    assert started["data"]["language"] == "python"

    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant = detail["turns"][-1]
    assert assistant["role"] == "assistant"
    artifacts = assistant["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "code"
    assert artifacts[0]["language"] == "python"
    assert artifacts[0]["content"] == 'print("hi")'


def test_chat_sync_code_artifact_language_roundtrips(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sync `/chat` must also carry the `language` hint on the response's
    # `artifacts` array so clients without SSE see the same metadata.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    def _fake_complete_chat(context, db, *, messages, **kwargs):  # type: ignore[no-untyped-def]
        class _Usage:
            prompt_tokens = completion_tokens = total_tokens = 0

        class _Msg:
            role = "assistant"
            reasoning_content = None
            content = (
                'intro <artifact type="code" language="sql" title="Q">SELECT 1;</artifact> done'
            )

        class _Choice:
            finish_reason = "stop"
            message = _Msg()

        class _Response:
            model = "dev"
            choices = [_Choice()]
            usage = _Usage()

        class _Decision:
            policy = "local_only"
            chosen_pool = "local"
            reason = "policy_local_only"
            forced_local = False
            pii_hits: list[str] = []

        class _Cfg:
            model = "dev"
            canonical_model = "dev"
            provider = "local"
            backend = "primary"
            base_url = ""
            api_key = ""

        return _Response(), _Decision(), _Cfg()

    monkeypatch.setattr(ai_router, "complete_chat", _fake_complete_chat)

    response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "sql hello"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"].strip() == "intro  done"
    assert len(body["artifacts"]) == 1
    assert body["artifacts"][0]["type"] == "code"
    assert body["artifacts"][0]["language"] == "sql"
    assert body["artifacts"][0]["content"] == "SELECT 1;"


def test_chat_stream_synthesizes_completed_for_unclosed_artifact_on_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If the model opens an artifact and then the provider errors before
    # the close tag arrives, the stream must still emit
    # artifact_completed so the client's buffer is released.
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool: False)

    class _ErrorAfterContentStream:
        def __init__(self) -> None:
            self._emitted = False

        def __aiter__(self) -> "_ErrorAfterContentStream":
            return self

        async def __anext__(self):
            if not self._emitted:
                self._emitted = True
                return _delta(content='<artifact type="document">opened but never closed')
            raise OpenAIError("provider died")

        async def aclose(self) -> None:  # pragma: no cover - interface glue
            pass

    class _ErrorChatCompletions:
        def __init__(self) -> None:
            self.calls: list = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            assert kwargs.get("stream") is True
            return _ErrorAfterContentStream()

    class _ErrorPoolClient:
        def __init__(self) -> None:
            self.chat = SimpleNamespace(completions=_ErrorChatCompletions())
            self.models = _FakeModels()

        def with_options(self, **_) -> "_ErrorPoolClient":
            return self

    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: _ErrorPoolClient())

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "crash mid-artifact"}],
        },
    )
    assert status_code == 200
    types = [event["type"] for event in _chat_events(events)]
    # The synthesized artifact_completed lands before the error+done pair.
    assert "artifact_started" in types
    assert "artifact_completed" in types
    started_idx = types.index("artifact_started")
    completed_idx = types.index("artifact_completed")
    error_idx = types.index("error")
    assert started_idx < completed_idx < error_idx


# ---------------------------------------------------------------------------
# allowed_app_ids: per-conversation tool scope picker
# ---------------------------------------------------------------------------


def _tools_in_first_call(pool_client: _FakeAsyncPoolClient) -> list[dict[str, Any]]:
    calls = pool_client.chat.completions.calls
    assert calls, "pool client never received a chat.completions.create call"
    return list(calls[0].get("tools") or [])


def test_chat_stream_allowed_app_ids_narrows_tool_surface_to_one_app(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="ok"), _delta(finish_reason="stop"), _usage_tail(1, 1, 2)]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, _events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "hi"}],
            # Pure user-driven scope narrowing: only meeting tools are exposed
            # to the LLM for this turn even though the workspace also has PMS,
            # planner, and docs entitlements.
            "allowed_app_ids": ["meeting"],
        },
    )

    assert status_code == 200
    tool_names = [item["function"]["name"] for item in _tools_in_first_call(pool_client)]
    assert tool_names, "expected meeting tools to be exposed"
    assert all(name.startswith("meeting.") for name in tool_names), (
        f"non-meeting tool leaked into LLM context: {tool_names}"
    )


def test_chat_stream_allowed_app_ids_empty_list_disables_all_tools(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="ok"), _delta(finish_reason="stop"), _usage_tail(1, 1, 2)]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, _events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "hi"}],
            # Explicit "no tools" — text-only conversation. The agent loop is
            # short-circuited because filtered_tool_specs is empty, so the
            # underlying chat.completions call is made without a tools kwarg.
            "allowed_app_ids": [],
        },
    )

    assert status_code == 200
    assert _tools_in_first_call(pool_client) == []


def test_chat_stream_allowed_app_ids_rejects_unknown_app(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="ok"), _delta(finish_reason="stop"), _usage_tail(1, 1, 2)]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    response = client.post(
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "hi"}],
            # An attacker can't smuggle a tool surface in by inventing an
            # app_id — the validator rejects unknown values up front.
            "allowed_app_ids": ["pms", "shadow-app"],
        },
    )
    assert response.status_code == 422
    assert "shadow-app" in response.text


def test_chat_stream_allowed_app_ids_cannot_widen_beyond_entitlements(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")
    # The user asks for PMS tools, but the workspace entitlement for PMS has
    # been revoked — the resulting tool surface is the *intersection*, so
    # zero tools end up exposed even though the request looks valid.
    _disable_workspace_app(slug, "pms")

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="ok"), _delta(finish_reason="stop"), _usage_tail(1, 1, 2)]
    )
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: pool_client)

    status_code, _events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "hi"}],
            "allowed_app_ids": ["pms"],
        },
    )

    assert status_code == 200
    tool_names = [item["function"]["name"] for item in _tools_in_first_call(pool_client)]
    assert all(not name.startswith("pms.") for name in tool_names), (
        f"PMS tool leaked despite revoked entitlement: {tool_names}"
    )
