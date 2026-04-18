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

from aidoo_api.core import llm as llm_core
from aidoo_api.core.db import get_engine
from aidoo_api.core.llm import LlmTaskContext, complete_chat_stream
from aidoo_api.core.llm_adapters import (
    MlxLmStreamAdapter,
    OpenRouterStreamAdapter,
    StreamChunk,
)
from aidoo_api.domains.ai.models import LlmPolicy
from aidoo_api.domains.auth.models import AuditLog


pytestmark = pytest.mark.anyio


def _delta_chunk(
    *,
    content: str | None = None,
    reasoning_content: str | None = None,
    reasoning: Any = None,
    finish_reason: str | None = None,
) -> SimpleNamespace:
    delta = SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        reasoning=reasoning,
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


async def _collect_chunks(generator) -> list[StreamChunk]:
    return [chunk async for chunk in generator]


async def test_mlx_lm_adapter_yields_reasoning_then_content_then_done() -> None:
    chunks = [
        _delta_chunk(reasoning_content="think"),
        _delta_chunk(content="Hi"),
        _delta_chunk(content=" there"),
        _delta_chunk(finish_reason="stop"),
    ]
    client = _FakeAsyncPoolClient(_FakeAsyncChatCompletions(chunks))
    out = await _collect_chunks(
        MlxLmStreamAdapter().open_stream(client, {"model": "m", "messages": []})
    )
    kinds_texts = [(chunk.kind, chunk.text) for chunk in out]
    assert kinds_texts == [
        ("reasoning", "think"),
        ("content", "Hi"),
        ("content", " there"),
        ("done", None),
    ]
    assert out[-1].finish_reason == "stop"
    call = client.chat.completions.calls[0]
    assert call["stream"] is True
    assert call["stream_options"] == {"include_usage": True}


async def test_openrouter_adapter_handles_string_reasoning() -> None:
    chunks = [
        _delta_chunk(reasoning="think"),
        _delta_chunk(content="ok", finish_reason="stop"),
    ]
    client = _FakeAsyncPoolClient(_FakeAsyncChatCompletions(chunks))
    out = await _collect_chunks(
        OpenRouterStreamAdapter().open_stream(
            client, {"model": "m", "messages": []}
        )
    )
    assert [(chunk.kind, chunk.text) for chunk in out if chunk.kind != "done"] == [
        ("reasoning", "think"),
        ("content", "ok"),
    ]


async def test_openrouter_adapter_handles_object_reasoning() -> None:
    chunks = [
        _delta_chunk(reasoning={"content": "think"}),
        _delta_chunk(content="ok", finish_reason="stop"),
    ]
    client = _FakeAsyncPoolClient(_FakeAsyncChatCompletions(chunks))
    out = await _collect_chunks(
        OpenRouterStreamAdapter().open_stream(
            client, {"model": "m", "messages": []}
        )
    )
    assert out[0] == StreamChunk(kind="reasoning", text="think")


async def test_adapter_skips_empty_and_none_deltas() -> None:
    chunks = [
        _delta_chunk(content=""),
        _delta_chunk(reasoning_content=""),
        _delta_chunk(content=None),
        _delta_chunk(content="real", finish_reason="stop"),
    ]
    client = _FakeAsyncPoolClient(_FakeAsyncChatCompletions(chunks))
    out = await _collect_chunks(
        MlxLmStreamAdapter().open_stream(client, {"model": "m", "messages": []})
    )
    assert [chunk.kind for chunk in out] == ["content", "done"]
    assert out[0].text == "real"


async def test_adapter_emits_usage_from_tail_chunk_before_done() -> None:
    chunks = [
        _delta_chunk(content="hi", finish_reason="stop"),
        _usage_tail(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    ]
    client = _FakeAsyncPoolClient(_FakeAsyncChatCompletions(chunks))
    out = await _collect_chunks(
        MlxLmStreamAdapter().open_stream(client, {"model": "m", "messages": []})
    )
    assert [chunk.kind for chunk in out] == ["content", "usage", "done"]
    assert out[1].usage == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
    }


async def test_adapter_close_called_even_when_consumer_breaks_early() -> None:
    chunks = [
        _delta_chunk(content="a"),
        _delta_chunk(content="b"),
        _delta_chunk(content="c", finish_reason="stop"),
    ]
    completions = _FakeAsyncChatCompletions(chunks)
    client = _FakeAsyncPoolClient(completions)
    gen = MlxLmStreamAdapter().open_stream(client, {"model": "m", "messages": []})
    first = await gen.__anext__()
    assert first.kind == "content"
    await gen.aclose()
    assert completions.last_stream is not None
    assert completions.last_stream.closed is True


def _ctx() -> LlmTaskContext:
    return LlmTaskContext(
        source="test.stream",
        actor_user_id=None,
        workspace_id="ws-stream-test",
        task_kind="chatbot",
    )


def _make_db_session() -> Session:
    return Session(get_engine())


def _install_fake_pool(
    monkeypatch: pytest.MonkeyPatch,
    chunks: list[Any],
    *,
    error: Exception | None = None,
) -> _FakeAsyncChatCompletions:
    completions = _FakeAsyncChatCompletions(chunks, error=error)
    client = _FakeAsyncPoolClient(completions)
    monkeypatch.setattr(llm_core, "get_async_pool_client", lambda pool: client)
    return completions


def _set_policy(task_kind: str, mode: str) -> None:
    with _make_db_session() as session:
        policy = session.scalar(
            select(LlmPolicy).where(LlmPolicy.task_kind == task_kind)
        )
        assert policy is not None
        policy.policy_mode = mode
        session.add(policy)
        session.commit()


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
    db = _make_db_session()
    try:
        return [
            chunk
            async for chunk, _, _ in complete_chat_stream(_ctx(), db, **kwargs)
        ]
    finally:
        db.close()


async def test_complete_chat_stream_commits_ok_audit_on_normal_finish(
    monkeypatch: pytest.MonkeyPatch, client_seed_workspace: None
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
    assert payload["source"] == "test.stream"
    assert payload["chosen_pool"] == "local"


async def test_complete_chat_stream_audits_error_and_reraises_on_provider_failure(
    monkeypatch: pytest.MonkeyPatch, client_seed_workspace: None
) -> None:
    _set_policy("chatbot", "local_only")
    _install_fake_pool(monkeypatch, [], error=OpenAIError("provider down"))
    before = len(_audit_rows())
    with pytest.raises(OpenAIError, match="provider down"):
        await _drain(messages=[{"role": "user", "content": "hi"}])
    rows = _audit_rows()
    assert len(rows) == before + 1
    payload = rows[-1].payload
    assert payload["status"] == "error"
    assert "provider down" in payload["error"]


async def test_complete_chat_stream_audits_cancelled_on_generator_close(
    monkeypatch: pytest.MonkeyPatch, client_seed_workspace: None
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
            _ctx(), db, messages=[{"role": "user", "content": "hi"}]
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


async def test_complete_chat_stream_unconfigured_pool_audits_error_and_raises(
    monkeypatch: pytest.MonkeyPatch, client_seed_workspace: None
) -> None:
    _set_policy("chatbot", "local_only")

    def fake_get_pool_config(pool, settings=None):  # type: ignore[override]
        return llm_core.LlmPoolConfig(
            pool=pool,
            provider="mlx-lm",
            base_url="",
            api_key="",
            default_model="",
            canonical_model="x",
            long_generation_timeout_seconds=1.0,
            enabled=True,
        )

    monkeypatch.setattr(llm_core, "get_pool_config", fake_get_pool_config)
    before = len(_audit_rows())
    with pytest.raises(OpenAIError, match="not configured"):
        await _drain(messages=[{"role": "user", "content": "hi"}])
    rows = _audit_rows()
    assert len(rows) == before + 1
    assert rows[-1].payload["status"] == "error"
    assert "not configured" in rows[-1].payload["error"]


async def test_complete_chat_stream_passes_reasoning_effort_extra_body_for_local(
    monkeypatch: pytest.MonkeyPatch, client_seed_workspace: None
) -> None:
    _set_policy("chatbot", "local_only")
    completions = _install_fake_pool(
        monkeypatch,
        [_delta_chunk(content="x", finish_reason="stop")],
    )
    await _drain(
        messages=[{"role": "user", "content": "hi"}],
        reasoning_effort="medium",
    )
    call = completions.calls[0]
    assert call["extra_body"] == {"reasoning_effort": "medium"}
    assert call["stream"] is True


async def test_complete_chat_stream_suppresses_reasoning_payload_when_stream_reasoning_off(
    monkeypatch: pytest.MonkeyPatch, client_seed_workspace: None
) -> None:
    _set_policy("chatbot", "local_only")
    completions = _install_fake_pool(
        monkeypatch,
        [_delta_chunk(content="x", finish_reason="stop")],
    )
    await _drain(
        messages=[{"role": "user", "content": "hi"}],
        reasoning_effort="medium",
        stream_reasoning=False,
    )
    assert completions.calls[0]["extra_body"] == {"think": False}


async def test_complete_chat_stream_uses_external_reasoning_shape(
    monkeypatch: pytest.MonkeyPatch, client_seed_workspace: None
) -> None:
    _set_policy("chatbot", "external")
    completions = _install_fake_pool(
        monkeypatch,
        [_delta_chunk(content="x", finish_reason="stop")],
    )
    await _drain(
        messages=[{"role": "user", "content": "hi"}],
        reasoning_effort="low",
    )
    assert completions.calls[0]["extra_body"] == {"reasoning": {"effort": "low"}}


@pytest.fixture(name="client_seed_workspace")
def _client_seed_workspace(client):
    """Reuse the existing app bootstrap to ensure seed policies exist."""

    return client
