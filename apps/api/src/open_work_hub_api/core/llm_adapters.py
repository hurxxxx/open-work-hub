"""Provider-agnostic streaming adapters.

Both mlx-lm/vLLM (local) and official OpenAI (external) speak the OpenAI chat
completions streaming protocol, but the reasoning-channel shape differs:

- mlx-lm/vLLM: ``choice.delta.reasoning_content: str`` or
               ``choice.delta.reasoning: str`` on newer vLLM/Qwen streams
- OpenAI:      provider-specific reasoning deltas can arrive on
               ``choice.delta.reasoning``

Route and audit code never sees these differences — the adapters normalize
every raw chunk into a flat ``StreamChunk`` enum with one of four ``kind``
values.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


StreamChunkKind = Literal[
    "content",
    "reasoning",
    "usage",
    "tool_call_start",
    "tool_call_args",
    "tool_call_end",
    "done",
]


@dataclass(frozen=True)
class StreamChunk:
    kind: StreamChunkKind
    text: str | None = None
    usage: dict[str, int] | None = None
    finish_reason: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    args_delta: str | None = None


class LlmStreamAdapter(Protocol):
    supports_tools: bool

    def open_stream(
        self, client: Any, payload: dict[str, Any]
    ) -> AsyncIterator[StreamChunk]: ...


class _BaseOpenAICompatAdapter:
    """Shared driver for OpenAI-compatible streaming endpoints.

    Subclasses only override ``_extract_reasoning_text``; everything else is
    provider-independent.
    """

    supports_tools = True

    async def open_stream(
        self, client: Any, payload: dict[str, Any]
    ) -> AsyncIterator[StreamChunk]:
        stream_payload = _build_stream_payload(payload)
        stream = await client.chat.completions.create(**stream_payload)
        normalizer = _OpenAICompatStreamNormalizer(self, stream_payload)
        try:
            async for raw in _iter_raw_stream_chunks(stream):
                for chunk in normalizer.chunks_from_raw(raw):
                    yield chunk
        finally:
            await _close_stream(stream)
        yield normalizer.done_chunk()

    def _extract_reasoning_text(
        self, delta: Any, payload: dict[str, Any]
    ) -> str | None:  # pragma: no cover - abstract
        raise NotImplementedError

    def _extract_content_text(self, delta: Any, payload: dict[str, Any]) -> str | None:
        del payload
        value = getattr(delta, "content", None)
        if isinstance(value, str) and value:
            return value
        return None


class MlxLmStreamAdapter(_BaseOpenAICompatAdapter):
    """mlx-lm / vLLM local stream adapter."""

    def _extract_reasoning_text(self, delta: Any, payload: dict[str, Any]) -> str | None:
        if _vllm_thinking_disabled(payload):
            return None
        value = getattr(delta, "reasoning_content", None)
        if isinstance(value, str) and value:
            return value
        value = getattr(delta, "reasoning", None)
        if isinstance(value, str) and value:
            return value
        return None

    def _extract_content_text(self, delta: Any, payload: dict[str, Any]) -> str | None:
        value = getattr(delta, "content", None)
        if isinstance(value, str) and value:
            return value
        # vLLM with Qwen reasoning parser can stream the non-thinking answer
        # on ``delta.reasoning`` even though the final non-stream response
        # reports the same text as ``message.content``.
        if _vllm_thinking_disabled(payload):
            value = getattr(delta, "reasoning", None)
            if isinstance(value, str) and value:
                return value
            value = getattr(delta, "reasoning_content", None)
            if isinstance(value, str) and value:
                return value
        return None


class OpenAIExternalStreamAdapter(_BaseOpenAICompatAdapter):
    """OpenAI-compatible external stream adapter."""

    def _extract_reasoning_text(self, delta: Any, payload: dict[str, Any]) -> str | None:
        del payload
        value = getattr(delta, "reasoning", None)
        if isinstance(value, str):
            return value or None
        if isinstance(value, dict):
            inner = value.get("content")
            if isinstance(inner, str) and inner:
                return inner
            return None
        inner = getattr(value, "content", None)
        if isinstance(inner, str) and inner:
            return inner
        return None


def _build_stream_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "stream": True,
        # Ask the provider to append a final usage-only chunk. mlx-lm and vLLM
        # ignore unknown keys; OpenAI respects the flag.
        "stream_options": {"include_usage": True},
    }


async def _iter_raw_stream_chunks(stream: Any) -> AsyncIterator[Any]:
    async for raw in stream:
        yield raw


@dataclass
class _ToolCallState:
    id: str
    name: str | None = None
    started: bool = False


@dataclass(frozen=True)
class _ToolCallUpdate:
    id: str
    name: str | None = None
    arguments: str | None = None


@dataclass
class _ToolCallLifecycle:
    states: dict[int, _ToolCallState] = field(default_factory=dict)

    def update_chunks(self, delta: Any) -> list[StreamChunk]:
        chunks: list[StreamChunk] = []
        for _tool_index, tool_call, tool_state in _iter_tool_call_updates(
            delta,
            self.states,
        ):
            if not tool_state.started and tool_call.name:
                tool_state.started = True
                chunks.append(
                    StreamChunk(
                        kind="tool_call_start",
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                    )
                )
            if tool_call.arguments:
                chunks.append(
                    StreamChunk(
                        kind="tool_call_args",
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        args_delta=tool_call.arguments,
                    )
                )
        return chunks

    def finish_chunks(self, finish_reason: str) -> list[StreamChunk]:
        if finish_reason != "tool_calls":
            return []
        chunks: list[StreamChunk] = []
        for tool_index in sorted(self.states):
            state = self.states[tool_index]
            if not state.started:
                continue
            chunks.append(
                StreamChunk(
                    kind="tool_call_end",
                    tool_call_id=state.id,
                    tool_name=state.name,
                )
            )
        return chunks


@dataclass
class _OpenAICompatStreamNormalizer:
    adapter: _BaseOpenAICompatAdapter
    payload: dict[str, Any]
    finish_reason: str | None = None
    tool_calls: _ToolCallLifecycle = field(default_factory=_ToolCallLifecycle)

    def chunks_from_raw(self, raw: Any) -> list[StreamChunk]:
        choices = getattr(raw, "choices", None) or []
        usage_obj = getattr(raw, "usage", None)
        if not choices and usage_obj is not None:
            usage = _extract_usage(usage_obj)
            return [StreamChunk(kind="usage", usage=usage)] if usage else []
        if not choices:
            return []

        choice = choices[0]
        chunks = self._chunks_from_delta(getattr(choice, "delta", None))
        chunk_finish = getattr(choice, "finish_reason", None)
        if chunk_finish:
            self.finish_reason = chunk_finish
            chunks.extend(self.tool_calls.finish_chunks(chunk_finish))
        return chunks

    def done_chunk(self) -> StreamChunk:
        return StreamChunk(kind="done", finish_reason=self.finish_reason or "stop")

    def _chunks_from_delta(self, delta: Any) -> list[StreamChunk]:
        if delta is None:
            return []

        chunks: list[StreamChunk] = []
        reasoning_text = self.adapter._extract_reasoning_text(delta, self.payload)
        if reasoning_text:
            chunks.append(StreamChunk(kind="reasoning", text=reasoning_text))
        chunks.extend(self.tool_calls.update_chunks(delta))
        content_text = self.adapter._extract_content_text(delta, self.payload)
        if content_text:
            chunks.append(StreamChunk(kind="content", text=content_text))
        return chunks


async def _close_stream(stream: Any) -> None:
    aclose = getattr(stream, "aclose", None)
    if callable(aclose):
        try:
            await aclose()
        except Exception:  # pragma: no cover - defensive
            pass
        return

    close = getattr(stream, "close", None)
    if callable(close):
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:  # pragma: no cover - defensive
            pass


def _vllm_thinking_disabled(payload: dict[str, Any]) -> bool:
    extra_body = payload.get("extra_body")
    if not isinstance(extra_body, dict):
        return False
    chat_template_kwargs = extra_body.get("chat_template_kwargs")
    if not isinstance(chat_template_kwargs, dict):
        return False
    return chat_template_kwargs.get("enable_thinking") is False


def _iter_tool_call_updates(
    delta: Any,
    tool_states: dict[int, _ToolCallState],
) -> list[tuple[int, _ToolCallUpdate, _ToolCallState]]:
    updates: list[tuple[int, _ToolCallUpdate, _ToolCallState]] = []
    for item in getattr(delta, "tool_calls", None) or []:
        index = _tool_call_index(item, fallback=len(tool_states))
        state = tool_states.get(index)
        function_data = _tool_call_function(item)
        incoming_id = getattr(item, "id", None)
        if not isinstance(incoming_id, str) or not incoming_id:
            incoming_id = state.id if state is not None else f"tool_call_{index}"
        incoming_name = _tool_call_name(function_data)
        if state is None:
            state = _ToolCallState(id=incoming_id, name=incoming_name)
            tool_states[index] = state
        else:
            state.id = incoming_id
            if incoming_name:
                state.name = incoming_name
        updates.append(
            (
                index,
                _ToolCallUpdate(
                    id=state.id,
                    name=state.name,
                    arguments=_tool_call_arguments(function_data),
                ),
                state,
            )
        )
    return updates


def _tool_call_index(item: Any, *, fallback: int) -> int:
    value = getattr(item, "index", None)
    return value if isinstance(value, int) else fallback


def _tool_call_function(item: Any) -> Any:
    return getattr(item, "function", None)


def _tool_call_name(function_data: Any) -> str | None:
    value = getattr(function_data, "name", None)
    if isinstance(value, str) and value:
        return value
    return None


def _tool_call_arguments(function_data: Any) -> str | None:
    value = getattr(function_data, "arguments", None)
    if isinstance(value, str) and value:
        return value
    return None


_ADAPTERS: dict[str, LlmStreamAdapter] = {
    "local": MlxLmStreamAdapter(),
    "external": OpenAIExternalStreamAdapter(),
}


def get_stream_adapter(pool: str, provider: str | None = None) -> LlmStreamAdapter:
    del provider
    try:
        return _ADAPTERS[pool]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"no stream adapter registered for pool {pool!r}") from exc


def supports_tool_calling(pool: str, provider: str | None = None) -> bool:
    return bool(get_stream_adapter(pool, provider).supports_tools)


def _extract_usage(usage_obj: Any) -> dict[str, int] | None:
    out: dict[str, int] = {}
    for field_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(usage_obj, field_name, None)
        if isinstance(value, int):
            out[field_name] = value
    return out or None


__all__ = [
    "LlmStreamAdapter",
    "MlxLmStreamAdapter",
    "OpenAIExternalStreamAdapter",
    "StreamChunk",
    "StreamChunkKind",
    "get_stream_adapter",
    "supports_tool_calling",
]
