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
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.models import LlmPolicy
from aidoo_api.domains.auth.models import AuditLog
from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
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
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        reasoning=None,
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
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self._non_stream_content)
                )
            ],
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


def _workspace_ai_path(slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{slug}/ai{suffix}"


def _legacy_ai_path(suffix: str) -> str:
    return f"/api/v1/ai{suffix}"


def _seeded_dev_login(client: TestClient, account_key: str) -> dict:
    _bootstrap_admin_session(client)
    return _dev_login(client, account_key)


def _set_policy(task_kind: str, mode: str) -> None:
    with Session(get_engine()) as session:
        policy = session.scalar(
            select(LlmPolicy).where(LlmPolicy.task_kind == task_kind)
        )
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
            "messages": [{"role": "user", "content": "hi"}],
            "reasoning_effort": "medium",
        },
    )
    assert status_code == 200
    assert [event["type"] for event in events] == [
        "reasoning_delta",
        "content_delta",
        "content_delta",
        "usage",
        "done",
    ]
    assert [event["seq"] for event in events] == list(range(len(events)))
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
    assert [event["type"] for event in events] == ["content_delta", "done"]
    assert pool_client.chat.completions.calls[0]["extra_body"] == {"think": False}


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
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["data"]["code"] == "provider_error"
    assert events[1]["data"]["finish_reason"] == "error"
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
    assert [event["type"] for event in events] == ["error", "done"]
    assert events[0]["data"]["code"] == "adapter_error"
    assert events[0]["data"]["message"] == "adapter boom"
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
    assert [event["type"] for event in events] == ["error", "done"]
    assert external_pool.chat.completions.calls == []
    assert _llm_audit_rows()[-1].payload["status"] == "error"


def test_chat_stream_done_meta_uses_requested_model(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "external")
    settings = get_settings()

    pool_client = _FakeAsyncPoolClient(
        [_delta(content="ok", finish_reason="stop")]
    )
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


def test_chat_stream_mounts_on_legacy_and_slug_paths(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth = _seeded_dev_login(client, "hq-admin")
    slug = auth["user"]["workspaces"][0]["slug"]
    _set_policy("chatbot", "local_only")

    def build_pool(_pool: str) -> _FakeAsyncPoolClient:
        return _FakeAsyncPoolClient(
            [_delta(content="ok", finish_reason="stop")]
        )

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
        assert [event["type"] for event in events] == ["content_delta", "done"]
