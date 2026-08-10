"""Unit tests for streaming adapters + ``complete_chat_stream``.

These stay provider-free by handing the adapters fake async SDK objects. No
HTTP or FastAPI client here — route wiring lives in ``test_ai_stream.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from openai import OpenAIError
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core import llm as llm_core
from open_work_hub_api.core import llm_execution_adapters
from open_work_hub_api.core.db import get_engine
from open_work_hub_api.core.llm import (
    LlmProviderError,
    LlmTaskContext,
    ResolvedLlmExecution,
    complete_chat_stream,
    resolve_registered_chat_execution,
)
from open_work_hub_api.core.llm_adapters import StreamChunk, _close_stream
from open_work_hub_api.domains.ai.gateway import (
    LlmWorkloadContext,
    build_llm_workload_request,
    resolve_gateway_execution,
)
from open_work_hub_api.domains.auth.models import AuditLog


pytestmark = pytest.mark.anyio


def _delta_chunk(
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    reasoning: Any = None,
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


def _usage_tail(
    *, prompt_tokens: int, completion_tokens: int, total_tokens: int
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )


class _FakeAsyncStream:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = iter(chunks)
        self.closed = False

    def __aiter__(self) -> "_FakeAsyncStream":
        return self

    async def __anext__(self) -> Any:
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def aclose(self) -> None:
        self.closed = True


class _FakeAsyncChatCompletions:
    def __init__(
        self,
        chunks: list[Any] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._chunks = chunks or []
        self._error = error
        self.calls: list[dict[str, Any]] = []
        self.last_stream: _FakeAsyncStream | None = None

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        self.last_stream = _FakeAsyncStream(self._chunks)
        return self.last_stream


class _FakeAsyncPoolClient:
    def __init__(self, completions: _FakeAsyncChatCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)

    def with_options(self, **_: Any) -> "_FakeAsyncPoolClient":
        return self


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


class _CloseReturnsCoroutineStream:
    def __init__(self) -> None:
        self.closed = False

    def close(self):
        async def mark_closed() -> None:
            self.closed = True

        return mark_closed()


def _ctx() -> LlmTaskContext:
    return LlmTaskContext(
        source="test.stream",
        actor_user_id=None,
        workspace_id="ws-stream-test",
        task_kind="chatbot",
        app_id="chatbot",
        workload_id="chatbot",
    )


async def test_close_stream_awaits_close_coroutine_result() -> None:
    stream = _CloseReturnsCoroutineStream()

    await _close_stream(stream)

    assert stream.closed is True


def _make_db_session() -> Session:
    return Session(get_engine())


def _resolve_database_execution(
    db: Session,
    *,
    messages: list[dict[str, Any]],
    max_tokens: int,
) -> ResolvedLlmExecution:
    request = build_llm_workload_request(
        "chatbot",
        LlmWorkloadContext.from_task_context(_ctx()),
        db,
        messages=messages,
        max_tokens=max_tokens,
    )
    return resolve_gateway_execution(request, db).llm_execution


def _install_fake_pool(
    monkeypatch: pytest.MonkeyPatch,
    chunks: list[Any],
    *,
    error: Exception | None = None,
) -> _FakeAsyncChatCompletions:
    completions = _FakeAsyncChatCompletions(chunks, error=error)
    client = _FakeAsyncPoolClient(completions)
    monkeypatch.setattr(
        llm_core,
        "_new_async_pool_client",
        lambda _config: client,
    )
    return completions


def _set_policy(task_kind: str, mode: str) -> None:
    # Legacy test shim: registered workload routing is no longer DB task-policy driven.
    _ = (task_kind, mode)


def _audit_rows() -> list[AuditLog]:
    with _make_db_session() as session:
        return list(
            session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "llm_call")
                .order_by(AuditLog.created_at.asc())
            ).all()
        )


async def _drain(**kwargs: Any) -> list[StreamChunk]:
    kwargs.setdefault("max_tokens", 32_768)
    db = _make_db_session()
    try:
        if "resolved_execution" not in kwargs:
            kwargs["resolved_execution"] = _resolve_database_execution(
                db,
                messages=kwargs["messages"],
                max_tokens=kwargs["max_tokens"],
            )
        return [chunk async for chunk, _, _ in complete_chat_stream(_ctx(), db, **kwargs)]
    finally:
        db.close()


@pytest.mark.usefixtures("client_seed_workspace")
async def test_complete_chat_stream_commits_ok_audit_on_normal_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_policy("chatbot", "local_only")
    _install_fake_pool(
        monkeypatch,
        [
            _delta_chunk(content="hello", finish_reason="stop"),
            _usage_tail(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        ],
    )
    before = len(_audit_rows())
    chunks = await _drain(messages=[{"role": "user", "content": "hi"}])
    assert [chunk.kind for chunk in chunks] == ["content", "usage", "done"]
    rows = _audit_rows()
    assert len(rows) == before + 1
    payload = rows[-1].payload
    assert payload["status"] == "ok"
    assert payload["usage"] == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }
    assert payload["max_tokens"] == 32_768
    assert payload["finish_reason"] == "stop"
    assert payload["source"] == "test.stream"
    assert payload["chosen_pool"] == "local"


@pytest.mark.usefixtures("client_seed_workspace")
async def test_complete_chat_stream_audits_error_and_reraises_on_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_policy("chatbot", "local_only")
    _install_fake_pool(monkeypatch, [], error=OpenAIError("provider down"))
    before = len(_audit_rows())
    with pytest.raises(LlmProviderError, match="provider down"):
        await _drain(messages=[{"role": "user", "content": "hi"}])
    rows = _audit_rows()
    assert len(rows) == before + 1
    payload = rows[-1].payload
    assert payload["status"] == "error"
    assert "provider down" in payload["error"]


@pytest.mark.usefixtures("client_seed_workspace")
async def test_complete_chat_stream_audits_cancelled_on_generator_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_policy("chatbot", "local_only")
    _install_fake_pool(
        monkeypatch,
        [
            _delta_chunk(content="a"),
            _delta_chunk(content="b"),
            _delta_chunk(content="c", finish_reason="stop"),
        ],
    )
    db = _make_db_session()
    before = len(_audit_rows())
    try:
        gen = complete_chat_stream(
            _ctx(),
            db,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=32_768,
            resolved_execution=_resolve_database_execution(
                db,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=32_768,
            ),
        )
        first = await gen.__anext__()
        second = await gen.__anext__()
        assert first[0].kind == "content"
        assert second[0].kind == "content"
        await gen.aclose()
    finally:
        db.close()
    rows = _audit_rows()
    assert len(rows) == before + 1
    assert rows[-1].payload["status"] == "cancelled"


@pytest.mark.usefixtures("client_seed_workspace")
async def test_complete_chat_stream_treats_tool_calls_finish_as_ok_for_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_policy("chatbot", "local_only")
    _install_fake_pool(
        monkeypatch,
        [
            _delta_chunk(
                tool_calls=[
                    _tool_call_delta(
                        index=0,
                        tool_id="call-1",
                        name="docs.read_page",
                        arguments='{"page_id":"p1"}',
                    )
                ]
            ),
            _delta_chunk(finish_reason="tool_calls"),
        ],
    )
    before = len(_audit_rows())
    chunks = await _drain(messages=[{"role": "user", "content": "hi"}], tools=[])
    assert [chunk.kind for chunk in chunks][-1] == "done"
    rows = _audit_rows()
    assert len(rows) == before + 1
    assert rows[-1].payload["status"] == "ok"
    assert rows[-1].payload["finish_reason"] == "tool_calls"


@pytest.mark.usefixtures("client_seed_workspace")
async def test_complete_chat_stream_unconfigured_pool_audits_error_and_raises() -> None:
    _set_policy("chatbot", "local_only")
    unconfigured_execution = resolve_registered_chat_execution(
        _ctx(),
        config=llm_core.LlmPoolConfig(
            pool="local",
            provider="mlx-lm",
            base_url="",
            api_key="",
            default_model="",
            canonical_model="x",
            healthcheck_timeout_seconds=1.0,
            long_generation_timeout_seconds=1.0,
            enabled=True,
        ),
        max_tokens=32_768,
    )
    before = len(_audit_rows())
    with pytest.raises(LlmProviderError, match="not configured"):
        await _drain(
            messages=[{"role": "user", "content": "hi"}],
            resolved_execution=unconfigured_execution,
        )
    rows = _audit_rows()
    assert len(rows) == before + 1
    assert rows[-1].payload["status"] == "error"
    assert "not configured" in rows[-1].payload["error"]


async def test_official_provider_execution_adapter_streams_provider_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_provider_stream(config, payload, *, timeout_seconds):  # type: ignore[no-untyped-def]
        captured["provider"] = config.provider
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        yield StreamChunk(kind="content", text="hel")
        yield StreamChunk(kind="content", text="lo")
        yield StreamChunk(
            kind="usage",
            usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        )
        yield StreamChunk(kind="done", finish_reason="stop")

    monkeypatch.setattr(
        llm_execution_adapters,
        "stream_official_provider_chat",
        fake_provider_stream,
    )

    adapter = llm_execution_adapters.OfficialProviderLlmExecutionAdapter()
    chunks = [
        chunk
        async for chunk in adapter.stream(
            SimpleNamespace(
                pool="external",
                provider="anthropic",
                base_url="",
                api_key="test-key",
                default_model="claude-test",
                canonical_model="claude-test",
                healthcheck_timeout_seconds=1.0,
                long_generation_timeout_seconds=7.0,
            ),
            {
                "model": "claude-test",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 11,
            },
            timeout_seconds=7.0,
            sync_client_factory=lambda *_args: pytest.fail(
                "official stream must not use OpenAI client"
            ),
            async_client_factory=lambda *_args: pytest.fail(
                "official stream must not use OpenAI async client"
            ),
        )
    ]

    assert captured == {
        "provider": "anthropic",
        "payload": {
            "model": "claude-test",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 11,
        },
        "timeout_seconds": 7.0,
    }
    assert [chunk.kind for chunk in chunks] == ["content", "content", "usage", "done"]
    assert [chunk.text for chunk in chunks[:2]] == ["hel", "lo"]


async def test_official_provider_execution_adapter_wraps_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_provider_complete(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("anthropic down")

    def fake_provider_stream(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        yield StreamChunk(kind="content", text="partial")
        raise RuntimeError("gemini down")

    monkeypatch.setattr(
        llm_execution_adapters,
        "complete_official_provider_chat",
        fake_provider_complete,
    )
    monkeypatch.setattr(
        llm_execution_adapters,
        "stream_official_provider_chat",
        fake_provider_stream,
    )

    config = SimpleNamespace(
        pool="external",
        provider="anthropic",
        base_url="",
        api_key="test-key",
        default_model="claude-test",
        canonical_model="claude-test",
        healthcheck_timeout_seconds=1.0,
        long_generation_timeout_seconds=7.0,
    )
    adapter = llm_execution_adapters.OfficialProviderLlmExecutionAdapter()

    with pytest.raises(LlmProviderError, match="anthropic down"):
        adapter.complete(
            config,
            {"model": "claude-test", "messages": [], "max_tokens": 11},
            timeout_seconds=7.0,
            sync_client_factory=lambda *_args: pytest.fail(
                "official complete must not use OpenAI client"
            ),
        )

    with pytest.raises(LlmProviderError, match="gemini down"):
        async for _chunk in adapter.stream(
            config,
            {"model": "claude-test", "messages": [], "max_tokens": 11},
            timeout_seconds=7.0,
            sync_client_factory=lambda *_args: pytest.fail(
                "official stream must not use OpenAI client"
            ),
            async_client_factory=lambda *_args: pytest.fail(
                "official stream must not use OpenAI async client"
            ),
        ):
            pass


@pytest.fixture(name="client_seed_workspace")
def _client_seed_workspace(configured_local_llm_control_plane: None) -> None:
    """Use the explicit DB-managed local model for LLM execution tests."""

    return configured_local_llm_control_plane
