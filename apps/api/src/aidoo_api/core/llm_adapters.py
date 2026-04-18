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


StreamChunkKind = Literal["content", "reasoning", "usage", "done"]


@dataclass(frozen=True)
class StreamChunk:
    kind: StreamChunkKind
    text: str | None = None
    usage: dict[str, int] | None = None
    finish_reason: str | None = None


class LlmStreamAdapter(Protocol):
    def open_stream(
        self, client: Any, payload: dict[str, Any]
    ) -> AsyncIterator[StreamChunk]: ...


class _BaseOpenAICompatAdapter:
    """Shared driver for OpenAI-compatible streaming endpoints.

    Subclasses only override ``_extract_reasoning_text``; everything else is
    provider-independent.
    """

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
                    content_text = getattr(delta, "content", None)
                    if isinstance(content_text, str) and content_text:
                        yield StreamChunk(kind="content", text=content_text)
                chunk_finish = getattr(choice, "finish_reason", None)
                if chunk_finish:
                    finish_reason = chunk_finish
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


_ADAPTERS: dict[str, LlmStreamAdapter] = {
    "local": MlxLmStreamAdapter(),
    "external": OpenRouterStreamAdapter(),
}


def get_stream_adapter(pool: str) -> LlmStreamAdapter:
    try:
        return _ADAPTERS[pool]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"no stream adapter registered for pool {pool!r}") from exc


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
]
