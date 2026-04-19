"""Provider-agnostic streaming adapters.

Both mlx-lm (local) and OpenRouter (external) speak the OpenAI chat
completions streaming protocol, but the reasoning-channel shape differs:

- mlx-lm:     ``choice.delta.reasoning_content: str``
- OpenRouter: ``choice.delta.reasoning`` is either a ``str`` or
              ``{"content": str}`` depending on upstream provider

Route and audit code never sees these differences — the adapters normalize
every raw chunk into a flat ``StreamChunk`` enum with one of four ``kind``
values.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
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
        stream_payload = {
            **payload,
            "stream": True,
            # Ask the provider to append a final usage-only chunk. mlx-lm
            # ignores unknown keys; OpenRouter respects the flag.
            "stream_options": {"include_usage": True},
        }
        stream = await client.chat.completions.create(**stream_payload)
        finish_reason: str | None = None
        tool_states: dict[int, _ToolCallState] = {}
        try:
            async for raw in stream:
                choices = getattr(raw, "choices", None) or []
                usage_obj = getattr(raw, "usage", None)
                if not choices and usage_obj is not None:
                    usage = _extract_usage(usage_obj)
                    if usage:
                        yield StreamChunk(kind="usage", usage=usage)
                    continue
                if not choices:
                    continue
                choice = choices[0]
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    reasoning_text = self._extract_reasoning_text(delta)
                    if reasoning_text:
                        yield StreamChunk(kind="reasoning", text=reasoning_text)
                    for tool_index, tool_call, tool_state in _iter_tool_call_updates(
                        delta,
                        tool_states,
                    ):
                        if not tool_state.started and tool_call.name:
                            tool_state.started = True
                            yield StreamChunk(
                                kind="tool_call_start",
                                tool_call_id=tool_call.id,
                                tool_name=tool_call.name,
                            )
                        if tool_call.arguments:
                            yield StreamChunk(
                                kind="tool_call_args",
                                tool_call_id=tool_call.id,
                                tool_name=tool_call.name,
                                args_delta=tool_call.arguments,
                            )
                    content_text = getattr(delta, "content", None)
                    if isinstance(content_text, str) and content_text:
                        yield StreamChunk(kind="content", text=content_text)
                chunk_finish = getattr(choice, "finish_reason", None)
                if chunk_finish:
                    finish_reason = chunk_finish
                    if chunk_finish == "tool_calls":
                        for tool_index in sorted(tool_states):
                            state = tool_states[tool_index]
                            if not state.started:
                                continue
                            yield StreamChunk(
                                kind="tool_call_end",
                                tool_call_id=state.id,
                                tool_name=state.name,
                            )
        finally:
            aclose = getattr(stream, "aclose", None)
            if callable(aclose):
                try:
                    await aclose()
                except Exception:  # pragma: no cover - defensive
                    pass
            else:
                close = getattr(stream, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:  # pragma: no cover - defensive
                        pass
        yield StreamChunk(kind="done", finish_reason=finish_reason or "stop")

    def _extract_reasoning_text(self, delta: Any) -> str | None:  # pragma: no cover - abstract
        raise NotImplementedError


class MlxLmStreamAdapter(_BaseOpenAICompatAdapter):
    """mlx-lm — reasoning arrives on ``delta.reasoning_content`` as a string."""

    def _extract_reasoning_text(self, delta: Any) -> str | None:
        value = getattr(delta, "reasoning_content", None)
        if isinstance(value, str) and value:
            return value
        return None


class OpenRouterStreamAdapter(_BaseOpenAICompatAdapter):
    """OpenRouter — ``delta.reasoning`` is ``str`` or ``{"content": str}``."""

    def _extract_reasoning_text(self, delta: Any) -> str | None:
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
    "external": OpenRouterStreamAdapter(),
}


def get_stream_adapter(pool: str) -> LlmStreamAdapter:
    try:
        return _ADAPTERS[pool]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"no stream adapter registered for pool {pool!r}") from exc


def supports_tool_calling(pool: str) -> bool:
    return bool(get_stream_adapter(pool).supports_tools)


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
    "OpenRouterStreamAdapter",
    "StreamChunk",
    "StreamChunkKind",
    "get_stream_adapter",
    "supports_tool_calling",
]
