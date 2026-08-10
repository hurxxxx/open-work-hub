"""Route-level tests for workspace-scoped AI chat stream endpoints."""

from __future__ import annotations

from dataclasses import replace
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
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

from open_alm_api.core import llm as llm_core
from open_alm_api.core.db import get_engine
from open_alm_api.core.llm_adapters import StreamChunk
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.ai.model_credentials import encrypt_api_key
from open_alm_api.domains.ai.model_settings_models import (
    AiModelCatalogEntry,
    AiModelProviderConfig,
)
from open_alm_api.domains.ai.registry import get_ai_capability_registry
from open_alm_api.domains.ai import agent as ai_agent
from open_alm_api.domains.ai import approvals as ai_approvals
from open_alm_api.domains.ai import router as ai_router
from open_alm_api.domains.auth.models import AuditLog, User, Workspace
from open_alm_api.domains.conversations.scope_registry import (
    ConversationScopeArtifact,
    ConversationScopeTurnContext,
)
from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_user_with_workspaces,
    _dev_login,
    _login,
)


@pytest.fixture(autouse=True)
def _bridge_registered_client_factories(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep route tests' fake clients while registered workloads pass exact config."""

    original_sync_getter = llm_core.get_pool_client
    original_sync_factory = llm_core._new_pool_client
    original_getter = llm_core.get_async_pool_client
    original_factory = llm_core._new_async_pool_client

    def sync_factory(config):  # type: ignore[no-untyped-def]
        current_getter = llm_core.get_pool_client
        if current_getter is original_sync_getter:
            return original_sync_factory(config)
        return current_getter(
            config.pool,
            external_provider=(config.provider if config.pool == "external" else None),
        )

    def factory(config):  # type: ignore[no-untyped-def]
        current_getter = llm_core.get_async_pool_client
        if current_getter is original_getter:
            return original_factory(config)
        return current_getter(
            config.pool,
            external_provider=(config.provider if config.pool == "external" else None),
        )

    monkeypatch.setattr(llm_core, "_new_pool_client", sync_factory)
    monkeypatch.setattr(llm_core, "_new_async_pool_client", factory)


def _enable_local_tool_calling(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_tool_calling_enabled", True)
    monkeypatch.setattr(settings, "ai_local_tool_calling_enabled", True)


def _delta(
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    reasoning: str | None = None,
    tool_calls: list[Any] | None = None,
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        reasoning=reasoning,
        tool_calls=tool_calls,
    )
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)],
        usage=None,
    )


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
    return f"/api/v1/workspaces/{slug}/chatbot{suffix}"


def _legacy_ai_path(suffix: str) -> str:
    return f"/api/v1/chatbot{suffix}"


def _seeded_dev_login(client: TestClient, account_key: str) -> dict:
    _bootstrap_admin_session(client)
    return _dev_login(client, account_key)


def _set_policy(task_kind: str, mode: str) -> None:
    registry = get_ai_capability_registry()
    workload = registry.resolve_llm_workload("chatbot")
    assert workload.task_kind == task_kind
    registry.llm_workloads[workload.workload_id] = replace(
        workload,
        default_route="external" if mode == "external" else "local",
    )
    if mode != "external":
        _configure_database_local_provider()


def _configure_database_local_provider() -> None:
    model_id = "local-current-moe-test-model"
    model_key = "local/current-moe-test-model"
    with Session(get_engine()) as db:
        provider = db.get(AiModelProviderConfig, "local")
        assert provider is not None
        model = db.get(AiModelCatalogEntry, model_id)
        if model is None:
            model = AiModelCatalogEntry(
                id=model_id,
                provider_id="local",
                model_key=model_key,
                display_name=model_key,
                capabilities_json=["chat", "tool_calling", "vision"],
                source="manual",
                discovery_status="active",
                enabled=True,
                version=1,
            )
            db.add(model)
        provider.enabled = True
        provider.endpoint_url = get_settings().llm_local_base_url
        provider.default_model_id = model.id
        db.commit()


def _configure_database_external_provider(
    *,
    provider_id: str,
    model_id: str,
    model_key: str,
    endpoint_url: str,
) -> None:
    with Session(get_engine()) as db:
        for external_provider_id in ("openai", "anthropic", "gemini"):
            row = db.get(AiModelProviderConfig, external_provider_id)
            assert row is not None
            row.enabled = external_provider_id == provider_id
        provider = db.get(AiModelProviderConfig, provider_id)
        assert provider is not None
        model = db.get(AiModelCatalogEntry, model_id)
        if model is None:
            model = AiModelCatalogEntry(
                id=model_id,
                provider_id=provider_id,
                model_key=model_key,
                display_name=model_key,
                capabilities_json=["chat", "tool_calling", "vision"],
                source="manual",
                discovery_status="active",
                enabled=True,
                version=1,
            )
            db.add(model)
        provider.endpoint_url = endpoint_url
        provider.api_key_ciphertext = encrypt_api_key(f"test-{provider_id}-key")
        provider.default_model_id = model.id
        db.commit()


def _llm_audit_rows() -> list[AuditLog]:
    with Session(get_engine()) as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
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


def _assert_open_alm_identity_system_message(messages: list[dict[str, Any]]) -> None:
    assert messages[0]["role"] == "system"
    system_prompt = messages[0]["content"]
    assert "Open ALM의 업무용 챗봇 아이두(AI-Do)" in system_prompt
    assert "Qwen, Tongyi, OpenAI" in system_prompt


def test_chat_sync_injects_open_alm_identity_prompt_for_plain_business_chat(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    captured_messages: list[dict[str, Any]] = []

    def _fake_complete_gateway_chat(request, _db):  # type: ignore[no-untyped-def]
        captured_messages.extend(request.messages)

        class _Usage:
            prompt_tokens = completion_tokens = total_tokens = 0

        class _Msg:
            role = "assistant"
            reasoning_content = None
            content = "저는 Open ALM의 업무용 챗봇 아이두(AI-Do)입니다."

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
            reason_codes = ("policy_local_only",)
            forced_local = False
            pii_hits: list[str] = []

        class _Cfg:
            model = "dev"
            canonical_model = "dev"
            provider = "local"
            backend = "primary"
            base_url = ""
            api_key = ""

        return SimpleNamespace(response=_Response(), decision=_Decision(), config=_Cfg())

    monkeypatch.setattr(ai_router, "complete_gateway_chat", _fake_complete_gateway_chat)

    response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "넌 누구냐"}],
        },
    )

    assert response.status_code == 200
    _assert_open_alm_identity_system_message(captured_messages)


def test_chat_stream_injects_open_alm_identity_prompt_for_plain_business_chat(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    captured_messages: list[dict[str, Any]] = []

    async def fake_complete_gateway_chat_stream(gateway_execution, _db):  # type: ignore[no-untyped-def]
        captured_messages.extend(gateway_execution.request.messages)
        yield StreamChunk(kind="content", text="stream ok"), None, None
        yield StreamChunk(kind="done", finish_reason="stop"), None, None

    monkeypatch.setattr(
        ai_router,
        "complete_resolved_gateway_chat_stream",
        fake_complete_gateway_chat_stream,
    )

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "넌 누구냐"}],
        },
    )

    assert status_code == 200
    assert any(event["type"] == "done" for event in _chat_events(events))
    _assert_open_alm_identity_system_message(captured_messages)


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


async def _close_stream_after_event_type(
    client: TestClient,
    url: str,
    *,
    event_type: str,
    headers: dict[str, str],
    json_body: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
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
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line.removeprefix("data:").strip())
                    events.append(event)
                    if event.get("type") == event_type:
                        await response.aclose()
                        return events
    raise AssertionError(f"stream opened but no {event_type!r} event was received")


@pytest.mark.anyio
async def test_chat_stream_disconnect_marks_audit_cancelled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="first"), _delta(content="second", finish_reason="stop")],
        block_after_first=True,
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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


@pytest.mark.anyio
async def test_chat_stream_disconnect_after_done_keeps_persisted_turn_completed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    async def fake_complete_gateway_chat_stream(*args: Any, **kwargs: Any):
        yield StreamChunk(kind="content", text="hello"), None, None
        yield StreamChunk(kind="done", finish_reason="stop"), None, None
        await asyncio.sleep(60)

    monkeypatch.setattr(
        ai_router,
        "complete_resolved_gateway_chat_stream",
        fake_complete_gateway_chat_stream,
    )

    events = await _close_stream_after_event_type(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        event_type="done",
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]

    detail: dict[str, Any] | None = None
    for _ in range(20):
        response = client.get(
            f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
            headers=_auth_headers(auth["token"]),
        )
        detail = response.json()
        if len(detail["turns"]) >= 2:
            break
        await asyncio.sleep(0.05)

    assert detail is not None
    assistant_turn = detail["turns"][1]
    assert assistant_turn["content"] == "hello"
    assert assistant_turn["responseStatus"] == "done"
    assert assistant_turn["finishReason"] == "stop"


def test_chat_stream_caller_provider_does_not_override_local_workload_route(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(
        [_delta(content="local response"), _delta(finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool, external_provider=None: pool_client,
    )
    before = len(_llm_audit_rows())
    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "external_provider": "anthropic",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert status_code == 200
    done = next(event for event in _chat_events(events) if event["type"] == "done")
    assert done["data"]["meta"]["chosen_pool"] == "local"
    assert len(_llm_audit_rows()) == before + 1


def test_chat_stream_caller_model_does_not_override_local_workload_model(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(
        [_delta(content="local response"), _delta(finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool, external_provider=None: pool_client,
    )
    before = len(_llm_audit_rows())

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "model": "gpt-5.4-mini",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert status_code == 200
    assert any(event["type"] == "done" for event in _chat_events(events))
    assert pool_client.chat.completions.calls[0]["model"] == "local/current-moe-test-model"
    assert len(_llm_audit_rows()) == before + 1


def test_chat_stream_caller_provider_does_not_override_external_workload_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")
    _configure_database_external_provider(
        provider_id="openai",
        model_id="openai-gpt-5-4-mini",
        model_key="gpt-5.4-mini",
        endpoint_url="https://api.openai.com/v1",
    )
    pool_client = _FakeAsyncPoolClient(
        [_delta(content="external response"), _delta(finish_reason="stop")]
    )
    selected_providers: list[str | None] = []

    def get_client(config):  # type: ignore[no-untyped-def]
        selected_providers.append(config.provider)
        return pool_client

    monkeypatch.setattr(llm_core, "_new_async_pool_client", get_client)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "auto",
            "external_provider": "anthropic",
            "messages": [{"role": "user", "content": "find my issues"}],
        },
    )

    assert status_code == 200
    done = next(event for event in _chat_events(events) if event["type"] == "done")
    assert done["data"]["meta"]["chosen_pool"] == "external"
    assert selected_providers == ["openai"]


def test_chat_stream_external_tool_incompatibility_blocks_without_local_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")
    _configure_database_external_provider(
        provider_id="anthropic",
        model_id="anthropic-claude-sonnet-4-6",
        model_key="claude-sonnet-4-6",
        endpoint_url="https://api.anthropic.com",
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_tool_calling_enabled", True)
    monkeypatch.setattr(settings, "ai_local_tool_calling_enabled", False)

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="business answer"), _delta(finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool, external_provider=None: pool_client,
    )

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "auto",
            "messages": [{"role": "user", "content": "find my issues"}],
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == ["error", "done"]
    assert chat[0]["data"]["code"] == "request_error"
    assert chat[1]["data"]["finish_reason"] == "error"
    assert pool_client.chat.completions.calls == []


def test_chat_stream_requires_auth(client: TestClient) -> None:
    response = client.post(
        _workspace_ai_path("administrator", "/chat/stream"),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code in (401, 403)


def test_chat_stream_requires_workspace_membership(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    outsider = _create_user_with_workspaces(
        client,
        admin["token"],
        email="stream-outsider@open-alm.local",
        full_name="Stream Outsider",
        workspace_keys=[],
    )
    outsider_token = _login(
        client,
        outsider["user"]["email"],
        outsider["temporary_password"],
    )

    response = client.post(
        _workspace_ai_path("administrator", "/chat/stream"),
        headers=_auth_headers(outsider_token),
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert response.status_code in (403, 404)


def test_chat_stream_emits_content_and_reasoning_in_order(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
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
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(
        [
            _delta(reasoning_content="should-not-appear"),
            _delta(content="ok", finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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


def test_chat_stream_tool_command_uses_registered_business_tool(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"

    def _unexpected_pool_call(pool, external_provider=None):  # type: ignore[no-untyped-def]
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
                    "content": '/tool pms.search_tasks {"q":"AI stream tool issue","limit":5}',
                }
            ]
        },
    )

    assert status_code == 200
    chat = _chat_events(events)
    event_types = [event["type"] for event in chat]
    assert event_types[0] == "tool_call_started"
    assert "tool_result" in event_types
    assert "error" not in event_types
    assert event_types[-1] == "done"
    assert chat[-1]["data"]["finish_reason"] == "stop"


def test_chat_stream_agent_loop_uses_registered_business_tools(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")
    _enable_local_tool_calling(monkeypatch)
    pool_client = _FakeAsyncPoolClient(
        [_delta(content="local business answer"), _delta(finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool, external_provider=None: pool_client,
    )

    async def fake_complete_gateway_chat_stream(*args: Any, **kwargs: Any):
        yield (
            StreamChunk(
                kind="tool_call_start",
                tool_call_id="call-1",
                tool_name="pms.create_task",
            ),
            None,
            None,
        )
        yield (
            StreamChunk(
                kind="tool_call_args",
                tool_call_id="call-1",
                tool_name="pms.create_task",
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

    monkeypatch.setattr(
        ai_agent,
        "complete_resolved_gateway_chat_stream",
        fake_complete_gateway_chat_stream,
    )

    def blocked_tool_call(*args: Any, **kwargs: Any):
        return ai_router.ToolCallExecution(
            call_id="call-1",
            tool_name="pms.create_task",
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
    assert chat[-1]["data"]["finish_reason"] == "awaiting_approval"

    with Session(get_engine()) as session:
        approvals = session.scalars(select(ai_approvals.AiToolApproval)).all()
        assert len(approvals) == 1
        assert approvals[0].tool_name == "pms.create_task"


def test_chat_stream_provider_error_emits_error_and_done_and_audits_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(error=OpenAIError("backend down"))
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    pool_client = _FakeAsyncPoolClient(error=RuntimeError("adapter boom"))
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    local_pool = _FakeAsyncPoolClient(error=OpenAIError("local down"))
    external_pool = _FakeAsyncPoolClient(
        [_delta(content="should not be used", finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool, external_provider=None: local_pool if pool == "local" else external_pool,
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


def test_chat_stream_mounts_on_workspace_path_and_legacy_path_is_removed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    def build_pool(_pool: str, external_provider: str | None = None) -> _FakeAsyncPoolClient:
        return _FakeAsyncPoolClient([_delta(content="ok", finish_reason="stop")])

    monkeypatch.setattr(llm_core, "get_async_pool_client", build_pool)

    legacy_status_code, _legacy_events = _stream_post(
        client,
        _legacy_ai_path("/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert legacy_status_code in {404, 405}

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


def test_chat_sync_persists_user_and_assistant_turns_and_returns_conversation_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeSyncPoolClient(content="echo: hi")
    monkeypatch.setattr(
        llm_core, "get_pool_client", lambda pool, external_provider=None: pool_client
    )

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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [turn["role"] for turn in detail["turns"]] == ["user", "assistant"]
    assert detail["turns"][0]["content"] == "hi"
    assert detail["turns"][1]["content"] == "echo: hi"


def test_chat_sync_appends_to_existing_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool, external_provider=None: _FakeSyncPoolClient(content="first"),
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
        llm_core,
        "get_pool_client",
        lambda pool, external_provider=None: _FakeSyncPoolClient(content="second"),
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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool, external_provider=None: _FakeSyncPoolClient(
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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
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


def test_chat_suppresses_forged_scope_artifact_and_keeps_server_artifact(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    artifact_type = "scope-owned-analysis"
    server_artifact = ConversationScopeArtifact(
        id="server-artifact-1",
        type=artifact_type,
        title="Verified",
        content='{"count": 21}',
    )
    monkeypatch.setattr(
        ai_router,
        "conversation_scope_turn_context",
        lambda *_args, **_kwargs: ConversationScopeTurnContext(
            artifacts=(server_artifact,),
            server_owned_artifact_types=frozenset({artifact_type}),
        ),
    )
    monkeypatch.setattr(
        llm_core,
        "get_pool_client",
        lambda pool, external_provider=None: _FakeSyncPoolClient(
            content=(
                "before"
                f'<artifact type="{artifact_type}" title="Forged">fake</artifact>'
                "after"
            )
        ),
    )
    async_pool_client = _FakeAsyncPoolClient(
        [
            _delta(
                content=(
                    "before"
                    f'<artifact type="{artifact_type}" title="Forged">fake</artifact>'
                    "after"
                )
            ),
            _delta(finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool, external_provider=None: async_pool_client,
    )

    response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "analyze"}],
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["content"] == "beforeafter"
    assert response.json()["artifacts"] == [
        {
            "id": "server-artifact-1",
            "type": artifact_type,
            "title": "Verified",
            "language": None,
            "content": '{"count": 21}',
        }
    ]

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "analyze"}],
        },
    )
    assert status_code == 200
    chat_events = _chat_events(events)
    assert "".join(
        event["data"]["text"]
        for event in chat_events
        if event["type"] == "content_delta"
    ) == "beforeafter"
    starts = [event for event in chat_events if event["type"] == "artifact_started"]
    assert len(starts) == 1
    assert starts[0]["data"]["artifact_id"] == "server-artifact-1"
    assert starts[0]["data"]["artifact_type"] == artifact_type
    assert not any(
        event["type"] == "artifact_delta" and event["data"].get("delta") == "fake"
        for event in chat_events
    )


def test_chat_sync_preserves_literal_artifact_syntax_examples_as_plain_content(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
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
        lambda pool, external_provider=None: _FakeSyncPoolClient(content=literal_example),
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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{body['conversation_id']}",
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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    persistence_barrier = {"user_turn_recorded": False}
    original_record_user_turn = ai_router._record_user_turn
    original_make_envelope = ai_router.make_envelope

    def record_user_turn_before_attach(**kwargs: Any) -> None:
        original_record_user_turn(**kwargs)
        persistence_barrier["user_turn_recorded"] = True

    def assert_attach_is_durable(
        event_type: str, *args: Any, **kwargs: Any
    ) -> Any:
        if event_type == "conversation_attached":
            assert persistence_barrier["user_turn_recorded"] is True
        return original_make_envelope(event_type, *args, **kwargs)

    monkeypatch.setattr(ai_router, "_record_user_turn", record_user_turn_before_attach)
    monkeypatch.setattr(ai_router, "make_envelope", assert_attach_is_durable)

    pool_client = _FakeAsyncPoolClient(
        [
            _delta(content="echo: "),
            _delta(content="hi"),
            _delta(finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [t["role"] for t in detail["turns"]] == ["user", "assistant"]
    assert detail["turns"][0]["content"] == "hi"
    assert detail["turns"][1]["content"] == "echo: hi"
    # Auto-title picks up the first user message.
    assert detail["title"].startswith("hi")

    # Listing surfaces the new conversation newest-first.
    listing = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert listing["items"][0]["id"] == conversation_id


def test_chat_stream_appends_to_existing_conversation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    # Start a conversation with a first exchange.
    pool_client = _FakeAsyncPoolClient([_delta(content="first", finish_reason="stop")])
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )
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
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client_second
    )
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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    def _should_not_be_called(_pool, external_provider=None):
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
    # one-turn conversation until conversation_id is threaded back.
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient([_delta(content="ok", finish_reason="stop")])
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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
        f"/api/v1/workspaces/{slug}/chatbot/conversations",
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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient(error=RuntimeError("boom"))
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
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


def test_chat_stream_extracts_artifact_markup_into_dedicated_envelopes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A single content chunk carrying `<artifact>...</artifact>` must surface
    # as content_delta (prefix) → artifact_started/delta/completed →
    # content_delta (suffix). The inline markup never reaches the client as
    # plain content.
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)

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
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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


def test_chat_stream_promotes_html_document_fence_to_html_artifact(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Models often answer "make a simple HTML page" with a markdown
    # ```html fenced document despite the artifact prompt. Complete HTML
    # documents should still route to the side panel instead of flooding
    # the chat bubble with source.
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)

    html_head = '<!doctype html>\n<html lang="ko">\n<head><title>간단한 카드</title></head>\n'
    html_tail = "<body><main>hello</main></body>\n</html>"
    html = f"{html_head}{html_tail}"
    pool_client = _FakeAsyncPoolClient(
        [
            _delta(content=f"네, 만들었습니다.\n```html\n{html_head}"),
            _delta(content=f"{html_tail}\n```\n확인해 주세요."),
            _delta(finish_reason="stop"),
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "간단한 html 예제 만들어줘"}],
        },
    )
    assert status_code == 200
    chat = _chat_events(events)
    assert [event["type"] for event in chat] == [
        "content_delta",
        "artifact_started",
        "artifact_delta",
        "artifact_delta",
        "artifact_completed",
        "content_delta",
        "done",
    ]
    assert chat[0]["data"]["text"] == "네, 만들었습니다.\n"
    start_data = chat[1]["data"]
    assert start_data["artifact_type"] == "html"
    assert start_data["title"] == "간단한 카드"
    assert chat[2]["data"]["delta"] == html_head
    assert chat[2]["data"]["artifact_id"] == start_data["artifact_id"]
    assert chat[3]["data"]["delta"] == html_tail
    assert chat[3]["data"]["artifact_id"] == start_data["artifact_id"]
    assert chat[4]["data"]["artifact_id"] == start_data["artifact_id"]
    assert chat[5]["data"]["text"] == "확인해 주세요."

    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant = detail["turns"][-1]
    assert assistant["content"] == "네, 만들었습니다.\n확인해 주세요."
    assert len(assistant["artifacts"]) == 1
    assert assistant["artifacts"][0]["type"] == "html"
    assert assistant["artifacts"][0]["title"] == "간단한 카드"
    assert assistant["artifacts"][0]["content"] == html


def test_chat_stream_persists_artifact_into_turn_meta(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The assistant turn row on disk must include the artifact so reload
    # restores the side panel content.
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)

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
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "generate artifact"}],
        },
    )
    assert status_code == 200
    conversation_id = next(e for e in events if e["type"] == "conversation_attached")["data"][
        "conversation_id"
    ]

    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
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
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)

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
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

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
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant = detail["turns"][-1]
    assert assistant["role"] == "assistant"
    artifacts = assistant["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["type"] == "code"
    assert artifacts[0]["language"] == "python"
    assert artifacts[0]["content"] == 'print("hi")'


def test_chat_stream_edit_replaces_turns_from_requested_seq(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _SequencedAsyncPoolClient(
        [
            [_delta(content="first answer"), _delta(finish_reason="stop")],
            [_delta(content="edited answer"), _delta(finish_reason="stop")],
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "original"}],
        },
    )
    assert status_code == 200
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    user_turn_id = detail["turns"][0]["id"]
    tail_turn = detail["turns"][-1]

    status_code, _ = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "replace_from_seq": 0,
            "replace_from_turn_id": user_turn_id,
            "replace_tail_seq": tail_turn["seq"],
            "replace_tail_turn_id": tail_turn["id"],
            "messages": [{"role": "user", "content": "edited"}],
        },
    )
    assert status_code == 200

    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert detail["title"] == "edited"
    assert [(turn["seq"], turn["role"], turn["content"]) for turn in detail["turns"]] == [
        (0, "user", "edited"),
        (1, "assistant", "edited answer"),
    ]


def test_chat_stream_rewrite_rejects_optimistic_synthetic_turn_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _SequencedAsyncPoolClient(
        [
            [_delta(content="first answer"), _delta(finish_reason="stop")],
            [_delta(content="should not run"), _delta(finish_reason="stop")],
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "original"}],
        },
    )
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    tail_turn = detail["turns"][-1]

    _, blocked_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "replace_from_seq": 0,
            "replace_from_turn_id": "user-optimistic",
            "replace_tail_seq": tail_turn["seq"],
            "replace_tail_turn_id": tail_turn["id"],
            "messages": [{"role": "user", "content": "edited"}],
        },
    )

    chat_events = _chat_events(blocked_events)
    assert chat_events[0]["type"] == "error"
    assert chat_events[0]["data"]["code"] == "ai.conversation_rewrite_seq_missing"
    assert len(pool_client.chat.completions.calls) == 1


def test_chat_stream_retry_reuses_trailing_user_turn_without_duplication(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _SequencedAsyncPoolClient(
        [
            [_delta(content="bad answer"), _delta(finish_reason="stop")],
            [_delta(content="better answer"), _delta(finish_reason="stop")],
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert status_code == 200
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant_turn_id = detail["turns"][1]["id"]
    tail_turn = detail["turns"][-1]

    status_code, _ = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "replace_from_seq": 1,
            "replace_from_turn_id": assistant_turn_id,
            "replace_tail_seq": tail_turn["seq"],
            "replace_tail_turn_id": tail_turn["id"],
            "persist_user_turn": False,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert status_code == 200

    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [(turn["seq"], turn["role"], turn["content"]) for turn in detail["turns"]] == [
        (0, "user", "hello"),
        (1, "assistant", "better answer"),
    ]


def test_chat_stream_append_rejects_active_conversation_run_lock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _SequencedAsyncPoolClient(
        [
            [_delta(content="first answer"), _delta(finish_reason="stop")],
            [_delta(content="should not run"), _delta(finish_reason="stop")],
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "original"}],
        },
    )
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, auth["user"]["id"])
        assert workspace is not None
        assert user is not None
        conversation = ai_router.conversations_service.get_conversation(
            db,
            workspace=workspace,
            user=user,
            conversation_id=conversation_id,
        )
        ai_approvals.acquire_conversation_run_lock(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
        )

    _, blocked_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers={
            **_auth_headers(auth["token"]),
            "Accept-Language": "en-US",
        },
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "follow-up"}],
        },
    )

    chat_events = _chat_events(blocked_events)
    assert chat_events[0]["type"] == "error"
    assert chat_events[0]["data"] == {
        "code": "ai.conversation_run_active",
        "message": "Another response is already running for this conversation. Try again after it finishes.",
        "retryable": False,
    }
    assert chat_events[-1]["type"] == "done"
    assert len(pool_client.chat.completions.calls) == 1

    with Session(get_engine()) as db:
        lock = db.scalar(
            select(ai_approvals.ConversationRunLock).where(
                ai_approvals.ConversationRunLock.conversation_id == conversation_id
            )
        )
        assert lock is not None
        lock.expires_at = ai_approvals.utcnow_naive() - timedelta(seconds=1)
        db.commit()

    _, retry_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "after expiry"}],
        },
    )
    retry_chat_events = _chat_events(retry_events)
    assert retry_chat_events[0]["type"] != "error"
    assert len(pool_client.chat.completions.calls) == 2


def test_chat_stream_scope_context_error_releases_conversation_run_lock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    original_scope_context = ai_router.conversation_scope_turn_context

    def fail_scope_context(*_: Any, **__: Any) -> Any:
        raise RuntimeError("scope context exploded")

    monkeypatch.setattr(ai_router, "conversation_scope_turn_context", fail_scope_context)

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "original"}],
        },
    )

    assert status_code == 200
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]
    chat_events = _chat_events(events)
    assert chat_events[0]["type"] == "error"
    assert chat_events[0]["data"] == {
        "code": "adapter_error",
        "message": "scope context exploded",
        "retryable": False,
    }
    assert chat_events[-1]["type"] == "done"
    assert chat_events[-1]["data"]["finish_reason"] == "error"

    with Session(get_engine()) as db:
        lock = db.scalar(
            select(ai_approvals.ConversationRunLock).where(
                ai_approvals.ConversationRunLock.conversation_id == conversation_id
            )
        )
        assert lock is None

    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "conversation_scope_turn_context", original_scope_context)
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _FakeAsyncPoolClient([_delta(content="retry ok"), _delta(finish_reason="stop")])
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    _, retry_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "messages": [{"role": "user", "content": "retry"}],
        },
    )

    retry_chat_events = _chat_events(retry_events)
    assert retry_chat_events[0]["type"] != "error"
    assert len(pool_client.chat.completions.calls) == 1


def test_scope_direct_response_bypasses_model_for_sync_and_stream(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    direct_text = "정확 집계를 완료하지 못했습니다."
    monkeypatch.setattr(
        ai_router,
        "conversation_scope_turn_context",
        lambda *_args, **_kwargs: ConversationScopeTurnContext(
            direct_response=direct_text
        ),
    )
    pool_client = _FakeAsyncPoolClient(
        [_delta(content="model must not run"), _delta(finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core,
        "get_async_pool_client",
        lambda pool, external_provider=None: pool_client,
    )

    sync_response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "전체 건수"}],
        },
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["content"] == direct_text
    assert sync_response.json()["policy"] == "scope_direct_response"
    assert sync_response.json()["chosen_pool"] is None
    sync_conversation_id = sync_response.json()["conversation_id"]
    sync_detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{sync_conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    sync_assistant = sync_detail["turns"][-1]
    assert sync_assistant["policy"] == "scope_direct_response"
    assert sync_assistant["chosenPool"] is None
    assert sync_assistant["provider"] == "server"

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "전체 건수"}],
        },
    )
    assert status_code == 200
    chat_events = _chat_events(events)
    assert chat_events[0]["type"] == "content_delta"
    assert chat_events[0]["data"] == {"text": direct_text}
    assert chat_events[-1]["type"] == "done"
    assert chat_events[-1]["data"]["finish_reason"] == "stop"
    done_meta = chat_events[-1]["data"]["meta"]
    assert done_meta["policy"] == "scope_direct_response"
    assert done_meta.get("chosen_pool") is None
    assert done_meta["decision_reason"] == "scope_direct_response"
    assert done_meta["model"] == "scope-direct"
    assert done_meta["chosen_model"] == "scope-direct"
    assert done_meta["canonical_model"] == "scope-direct"
    assert done_meta["provider"] == "server"
    stream_conversation_id = next(
        event
        for event in events
        if event["type"] == "conversation_attached"
    )["data"]["conversation_id"]
    stream_detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{stream_conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    stream_assistant = stream_detail["turns"][-1]
    assert stream_assistant["policy"] == "scope_direct_response"
    assert stream_assistant["chosenPool"] is None
    assert stream_assistant["provider"] == "server"
    assert pool_client.chat.completions.calls == []


def test_chat_stream_rewrite_rejects_live_pending_approval(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _FakeAsyncPoolClient(
        [_delta(content="needs approval"), _delta(finish_reason="stop")]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    status_code, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "make a task"}],
        },
    )
    assert status_code == 200
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    user_turn_id = detail["turns"][0]["id"]
    tail_turn = detail["turns"][-1]

    with Session(get_engine()) as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == slug))
        user = db.get(User, auth["user"]["id"])
        assert workspace is not None
        assert user is not None
        conversation = ai_router.conversations_service.get_conversation(
            db,
            workspace=workspace,
            user=user,
            conversation_id=conversation_id,
        )
        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "user", "content": "make a task"}],
            blocked_call_id="call-rewrite",
            model_meta={"model": "test-model"},
        )
        ai_approvals.create_pending_approval(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            agent_run_id=snapshot.id,
            tool_call_id="call-rewrite",
            tool_name="pms.create_task",
            arguments_json='{"title":"Task"}',
            resource_preview="Task",
        )
        db.commit()

    status_code, blocked_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "replace_from_seq": 0,
            "replace_from_turn_id": user_turn_id,
            "replace_tail_seq": tail_turn["seq"],
            "replace_tail_turn_id": tail_turn["id"],
            "messages": [{"role": "user", "content": "edit task"}],
        },
    )
    assert status_code == 200
    chat_events = _chat_events(blocked_events)
    assert chat_events[0]["type"] == "error"
    assert chat_events[0]["data"]["code"] == "ai.conversation_rewrite_approval_pending"
    assert chat_events[-1]["type"] == "done"


def test_chat_stream_rewrite_requires_target_turn_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _SequencedAsyncPoolClient(
        [
            [_delta(content="first answer"), _delta(finish_reason="stop")],
            [_delta(content="should not run"), _delta(finish_reason="stop")],
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "original"}],
        },
    )
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]

    status_code, blocked_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers={
            **_auth_headers(auth["token"]),
            "Accept-Language": "en-US",
        },
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "replace_from_seq": 0,
            "messages": [{"role": "user", "content": "edited"}],
        },
    )
    assert status_code == 200
    chat_events = _chat_events(blocked_events)
    assert chat_events[0]["type"] == "error"
    assert chat_events[0]["data"] == {
        "code": "ai.conversation_rewrite_turn_id_required",
        "message": "Conversation rewrites require the target turn id.",
        "retryable": False,
    }
    assert chat_events[-1]["type"] == "done"
    assert len(pool_client.chat.completions.calls) == 1


def test_chat_stream_rewrite_rejects_target_role_mismatch(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _SequencedAsyncPoolClient(
        [
            [_delta(content="first answer"), _delta(finish_reason="stop")],
            [_delta(content="should not run"), _delta(finish_reason="stop")],
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "original"}],
        },
    )
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant_turn_id = detail["turns"][1]["id"]
    tail_turn = detail["turns"][-1]

    _, blocked_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "replace_from_seq": 1,
            "replace_from_turn_id": assistant_turn_id,
            "replace_tail_seq": tail_turn["seq"],
            "replace_tail_turn_id": tail_turn["id"],
            "messages": [{"role": "user", "content": "edited"}],
        },
    )
    chat_events = _chat_events(blocked_events)
    assert chat_events[0]["type"] == "error"
    assert chat_events[0]["data"]["code"] == "ai.conversation_rewrite_role_mismatch"
    assert len(pool_client.chat.completions.calls) == 1


def test_chat_stream_rewrite_rejects_stale_tail(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)
    pool_client = _SequencedAsyncPoolClient(
        [
            [_delta(content="first answer"), _delta(finish_reason="stop")],
            [_delta(content="second answer"), _delta(finish_reason="stop")],
            [_delta(content="should not run"), _delta(finish_reason="stop")],
        ]
    )
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    _, events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "original"}],
        },
    )
    conversation_id = next(event for event in events if event["type"] == "conversation_attached")[
        "data"
    ]["conversation_id"]
    stale_detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    stale_user_turn_id = stale_detail["turns"][0]["id"]
    stale_tail = stale_detail["turns"][-1]

    _, _ = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "messages": [
                {"role": "user", "content": "original"},
                {"role": "assistant", "content": "first answer"},
                {"role": "user", "content": "newer question"},
            ],
        },
    )

    _, blocked_events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "persist": True,
            "conversation_id": conversation_id,
            "replace_from_seq": 0,
            "replace_from_turn_id": stale_user_turn_id,
            "replace_tail_seq": stale_tail["seq"],
            "replace_tail_turn_id": stale_tail["id"],
            "messages": [{"role": "user", "content": "stale edit"}],
        },
    )
    chat_events = _chat_events(blocked_events)
    assert chat_events[0]["type"] == "error"
    assert chat_events[0]["data"]["code"] == "ai.conversation_rewrite_tail_mismatch"
    assert len(pool_client.chat.completions.calls) == 2


def test_chat_sync_code_artifact_language_roundtrips(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sync `/chat` must also carry the `language` hint on the response's
    # `artifacts` array so clients without SSE see the same metadata.
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    def _fake_complete_gateway_chat(_request, _db):  # type: ignore[no-untyped-def]
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
            reason_codes = ("policy_local_only",)
            forced_local = False
            pii_hits: list[str] = []

        class _Cfg:
            model = "dev"
            canonical_model = "dev"
            provider = "local"
            backend = "primary"
            base_url = ""
            api_key = ""

        return SimpleNamespace(response=_Response(), decision=_Decision(), config=_Cfg())

    monkeypatch.setattr(ai_router, "complete_gateway_chat", _fake_complete_gateway_chat)

    response = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "code hello"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["content"].strip() == "intro  done"
    assert len(body["artifacts"]) == 1
    assert body["artifacts"][0]["type"] == "code"
    assert body["artifacts"][0]["language"] == "sql"
    assert body["artifacts"][0]["content"] == "SELECT 1;"


def test_chat_sync_retry_reuses_trailing_user_turn_without_duplication(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    completions = iter(["bad sync answer", "better sync answer"])

    def _fake_complete_gateway_chat(_request, _db):  # type: ignore[no-untyped-def]
        class _Usage:
            prompt_tokens = completion_tokens = total_tokens = 0

        class _Msg:
            role = "assistant"
            reasoning_content = None
            content = next(completions)

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
            reason_codes = ("policy_local_only",)
            forced_local = False
            pii_hits: list[str] = []

        class _Cfg:
            model = "dev"
            canonical_model = "dev"
            provider = "local"
            backend = "primary"
            base_url = ""
            api_key = ""

        return SimpleNamespace(response=_Response(), decision=_Decision(), config=_Cfg())

    monkeypatch.setattr(ai_router, "complete_gateway_chat", _fake_complete_gateway_chat)

    first = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": True,
            "messages": [{"role": "user", "content": "sync hello"}],
        },
    )
    assert first.status_code == 200, first.text
    conversation_id = first.json()["conversation_id"]
    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assistant_turn_id = detail["turns"][1]["id"]
    tail_turn = detail["turns"][-1]

    second = client.post(
        _workspace_ai_path(slug, "/chat"),
        headers=_auth_headers(auth["token"]),
        json={
            "backend_mode": "local",
            "persist": False,
            "conversation_id": conversation_id,
            "replace_from_seq": 1,
            "replace_from_turn_id": assistant_turn_id,
            "replace_tail_seq": tail_turn["seq"],
            "replace_tail_turn_id": tail_turn["id"],
            "persist_user_turn": False,
            "messages": [{"role": "user", "content": "sync hello"}],
        },
    )
    assert second.status_code == 200, second.text

    detail = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{conversation_id}",
        headers=_auth_headers(auth["token"]),
    ).json()
    assert [(turn["seq"], turn["role"], turn["content"]) for turn in detail["turns"]] == [
        (0, "user", "sync hello"),
        (1, "assistant", "better sync answer"),
    ]


def test_chat_stream_synthesizes_completed_for_unclosed_artifact_on_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If the model opens an artifact and then the provider errors before
    # the close tag arrives, the stream must still emit
    # artifact_completed so the client's buffer is released.
    auth = _seeded_dev_login(client, "administrator")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")
    monkeypatch.setattr(ai_router, "supports_tool_calling", lambda pool, provider=None: False)

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

    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: _ErrorPoolClient()
    )

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
# Business chat follows its registered workload route and app tool surface.
# ---------------------------------------------------------------------------


def _tools_in_first_call(pool_client: _FakeAsyncPoolClient) -> list[dict[str, Any]]:
    calls = pool_client.chat.completions.calls
    assert calls, "pool client never received a chat.completions.create call"
    return list(calls[0].get("tools") or [])


def _messages_in_first_call(pool_client: _FakeAsyncPoolClient) -> list[dict[str, Any]]:
    calls = pool_client.chat.completions.calls
    assert calls, "pool client never received a chat.completions.create call"
    return list(calls[0].get("messages") or [])


def test_chat_stream_business_chat_exposes_registered_context_tool_surface(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")
    _enable_local_tool_calling(monkeypatch)

    pool_client = _FakeAsyncPoolClient([_delta(content="ok"), _delta(finish_reason="stop")])
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    status_code, _events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "hi"}],
            # Older clients may still send context app ids. The server filters
            # them against the registry before exposing tools.
            "allowed_app_ids": ["pms", "docs"],
        },
    )

    assert status_code == 200
    tool_names = {tool["function"]["name"] for tool in _tools_in_first_call(pool_client)}
    assert {"docs.get_item", "pms.search_tasks"} <= tool_names


def test_chat_stream_business_context_question_reaches_llm_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "delivery-hub-admin")
    slug = "delivery-hub"
    _set_policy("chatbot", "local_only")

    pool_client = _FakeAsyncPoolClient([_delta(content="ok"), _delta(finish_reason="stop")])
    monkeypatch.setattr(
        llm_core, "get_async_pool_client", lambda pool, external_provider=None: pool_client
    )

    status_code, _events = _stream_post(
        client,
        _workspace_ai_path(slug, "/chat/stream"),
        headers=_auth_headers(auth["token"]),
        json_body={
            "backend_mode": "local",
            "messages": [{"role": "user", "content": "PMS 업무 자료를 찾아줘"}],
        },
    )

    assert status_code == 200
    chat_events = _chat_events(_events)
    assert [event["type"] for event in chat_events] == ["content_delta", "done"]
    assert chat_events[0]["data"]["text"] == "ok"
    assert chat_events[1]["data"]["meta"]["chosen_pool"] == "local"
    assert chat_events[1]["data"]["meta"]["decision_reason"] == "workload_route"
    assert pool_client.chat.completions.calls
    messages = _messages_in_first_call(pool_client)
    assert [message["role"] for message in messages] == ["system", "user"]
    _assert_open_alm_identity_system_message(messages)
