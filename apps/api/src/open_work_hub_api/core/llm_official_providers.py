from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any, Literal, Protocol

from open_work_hub_api.core.i18n import LocalizedApiMessage
from open_work_hub_api.core.llm_adapters import StreamChunk

OfficialProviderHealthStatus = Literal["ready", "unavailable", "model_missing"]


class OfficialProviderConfig(Protocol):
    pool: str
    provider: str
    base_url: str
    api_key: str
    default_model: str


class OfficialProviderHealthResult(SimpleNamespace):
    status: OfficialProviderHealthStatus
    detail: str | LocalizedApiMessage | None


def complete_official_provider_chat(
    config: OfficialProviderConfig,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Any:
    if config.provider == "anthropic":
        return _complete_anthropic_chat(config, payload, timeout_seconds)
    if config.provider == "gemini":
        return _complete_gemini_chat(config, payload, timeout_seconds)
    raise RuntimeError(f"unsupported official provider: {config.provider}")


def stream_official_provider_chat(
    config: OfficialProviderConfig,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Iterator[StreamChunk]:
    if config.provider == "anthropic":
        yield from _stream_anthropic_chat(config, payload, timeout_seconds)
        return
    if config.provider == "gemini":
        yield from _stream_gemini_chat(config, payload, timeout_seconds)
        return
    raise RuntimeError(f"unsupported official provider: {config.provider}")


def check_official_provider_health(
    config: OfficialProviderConfig,
    timeout_seconds: float,
) -> OfficialProviderHealthResult:
    try:
        if config.provider == "anthropic":
            return _check_anthropic_health(config, timeout_seconds)
        if config.provider == "gemini":
            return _check_gemini_health(config, timeout_seconds)
    except Exception as exc:
        if _is_model_missing_error(exc):
            return OfficialProviderHealthResult(
                status="model_missing",
                detail=LocalizedApiMessage(
                    code="llm.configured_model_missing",
                    params={"models": config.default_model},
                ),
            )
        return OfficialProviderHealthResult(
            status="unavailable",
            detail=LocalizedApiMessage(
                code="llm.provider_unavailable",
                params={"reason": str(exc)},
            ),
        )
    return OfficialProviderHealthResult(
        status="unavailable",
        detail=LocalizedApiMessage(
            code="llm.provider_unavailable",
            params={"reason": f"unsupported official provider: {config.provider}"},
        ),
    )


def _complete_anthropic_chat(
    config: OfficialProviderConfig,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Any:
    client = _anthropic_client(config, timeout_seconds)
    response = client.messages.create(**_anthropic_chat_request(payload))
    return _anthropic_response_to_openai_shape(response, model=str(payload["model"]))


def _stream_anthropic_chat(
    config: OfficialProviderConfig,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Iterator[StreamChunk]:
    client = _anthropic_client(config, timeout_seconds)
    final_message: Any | None = None
    with client.messages.stream(**_anthropic_chat_request(payload)) as stream:
        for text in stream.text_stream:
            if isinstance(text, str) and text:
                yield StreamChunk(kind="content", text=text)
        final_message = stream.get_final_message()
    usage = _anthropic_usage(final_message)
    if usage:
        yield StreamChunk(kind="usage", usage=usage)
    yield StreamChunk(
        kind="done",
        finish_reason=_normalize_finish_reason(
            config.provider,
            getattr(final_message, "stop_reason", None),
        ),
    )


def _complete_gemini_chat(
    config: OfficialProviderConfig,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Any:
    with _gemini_client(config, timeout_seconds) as client:
        response = client.models.generate_content(
            model=str(payload["model"]),
            contents=_gemini_prompt(payload.get("messages", [])),
            config=_gemini_generate_config(payload),
        )
    return _gemini_response_to_openai_shape(response, model=str(payload["model"]))


def _stream_gemini_chat(
    config: OfficialProviderConfig,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> Iterator[StreamChunk]:
    latest_response: Any | None = None
    with _gemini_client(config, timeout_seconds) as client:
        for response in client.models.generate_content_stream(
            model=str(payload["model"]),
            contents=_gemini_prompt(payload.get("messages", [])),
            config=_gemini_generate_config(payload),
        ):
            latest_response = response
            text = getattr(response, "text", None)
            if isinstance(text, str) and text:
                yield StreamChunk(kind="content", text=text)
    usage = _gemini_usage(latest_response)
    if usage:
        yield StreamChunk(kind="usage", usage=usage)
    yield StreamChunk(
        kind="done",
        finish_reason=_gemini_finish_reason(latest_response),
    )


def _check_anthropic_health(
    config: OfficialProviderConfig,
    timeout_seconds: float,
) -> OfficialProviderHealthResult:
    client = _anthropic_client(config, timeout_seconds)
    client.models.retrieve(config.default_model, timeout=timeout_seconds)
    return OfficialProviderHealthResult(status="ready", detail=None)


def _check_gemini_health(
    config: OfficialProviderConfig,
    timeout_seconds: float,
) -> OfficialProviderHealthResult:
    with _gemini_client(config, timeout_seconds) as client:
        client.models.get(model=config.default_model)
    return OfficialProviderHealthResult(status="ready", detail=None)


def _anthropic_client(
    config: OfficialProviderConfig,
    timeout_seconds: float,
) -> Any:
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("anthropic package is required for Anthropic LLM provider") from exc

    client_kwargs: dict[str, Any] = {
        "api_key": config.api_key,
        "timeout": timeout_seconds,
    }
    if config.base_url.strip():
        client_kwargs["base_url"] = config.base_url.rstrip("/")
    return Anthropic(**client_kwargs)


def _gemini_client(
    config: OfficialProviderConfig,
    timeout_seconds: float,
) -> Any:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("google-genai package is required for Gemini LLM provider") from exc

    http_options_kwargs: dict[str, Any] = {
        "timeout": max(1, int(timeout_seconds * 1000)),
    }
    if config.base_url.strip():
        http_options_kwargs["base_url"] = config.base_url.rstrip("/")
    return genai.Client(
        api_key=config.api_key,
        http_options=types.HttpOptions(**http_options_kwargs),
    )


def _anthropic_chat_request(payload: dict[str, Any]) -> dict[str, Any]:
    system, messages = _split_anthropic_messages(payload.get("messages", []))
    request: dict[str, Any] = {
        "model": str(payload["model"]),
        "max_tokens": int(payload["max_tokens"]),
        "messages": messages,
    }
    if system:
        request["system"] = system
    if payload.get("temperature") is not None:
        request["temperature"] = payload["temperature"]
    return request


def _gemini_generate_config(payload: dict[str, Any]) -> Any:
    try:
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("google-genai package is required for Gemini LLM provider") from exc

    generate_config_kwargs: dict[str, Any] = {
        "max_output_tokens": int(payload["max_tokens"]),
    }
    if payload.get("temperature") is not None:
        generate_config_kwargs["temperature"] = payload["temperature"]
    return types.GenerateContentConfig(**generate_config_kwargs)


def _split_anthropic_messages(raw_messages: Any) -> tuple[str | None, list[dict[str, str]]]:
    system_parts: list[str] = []
    messages: list[dict[str, str]] = []
    for message in raw_messages if isinstance(raw_messages, list) else []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        text = _message_content_text(message.get("content"))
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
            continue
        messages.append(
            {
                "role": "assistant" if role == "assistant" else "user",
                "content": text,
            }
        )
    if not messages:
        messages.append({"role": "user", "content": ""})
    return ("\n\n".join(system_parts) or None), messages


def _gemini_prompt(raw_messages: Any) -> str:
    parts: list[str] = []
    for message in raw_messages if isinstance(raw_messages, list) else []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        text = _message_content_text(message.get("content"))
        if text:
            parts.append(f"{role}: {text}")
    return "\n\n".join(parts)


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def _is_model_missing_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code == 404:
        return True
    code = getattr(error, "code", None)
    if code == 404:
        return True
    message = str(error).lower()
    return "404" in message and ("model" in message or "not found" in message)


def _anthropic_response_to_openai_shape(response: Any, *, model: str) -> Any:
    content_parts: list[str] = []
    for block in getattr(response, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            content_parts.append(text)
    usage_obj = getattr(response, "usage", None)
    prompt_tokens = getattr(usage_obj, "input_tokens", None)
    completion_tokens = getattr(usage_obj, "output_tokens", None)
    return _openai_shaped_response(
        model=getattr(response, "model", model),
        content="".join(content_parts),
        finish_reason=_normalize_finish_reason(
            "anthropic",
            getattr(response, "stop_reason", None),
        ),
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
    )


def _anthropic_usage(response: Any) -> dict[str, int] | None:
    usage_obj = getattr(response, "usage", None)
    prompt_tokens = getattr(usage_obj, "input_tokens", None)
    completion_tokens = getattr(usage_obj, "output_tokens", None)
    total_tokens = None
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        total_tokens = prompt_tokens + completion_tokens
    return _usage_dict(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


def _gemini_response_to_openai_shape(response: Any, *, model: str) -> Any:
    text = getattr(response, "text", None)
    usage_obj = getattr(response, "usage_metadata", None)
    prompt_tokens = getattr(usage_obj, "prompt_token_count", None)
    completion_tokens = getattr(usage_obj, "candidates_token_count", None)
    total_tokens = getattr(usage_obj, "total_token_count", None)
    finish_reason = "stop"
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        raw_finish_reason = getattr(candidates[0], "finish_reason", None)
        if raw_finish_reason is not None:
            finish_reason = _normalize_finish_reason("gemini", raw_finish_reason)
    return _openai_shaped_response(
        model=model,
        content=text if isinstance(text, str) else "",
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
        total_tokens=total_tokens if isinstance(total_tokens, int) else None,
    )


def _gemini_usage(response: Any) -> dict[str, int] | None:
    usage_obj = getattr(response, "usage_metadata", None)
    return _usage_dict(
        prompt_tokens=getattr(usage_obj, "prompt_token_count", None),
        completion_tokens=getattr(usage_obj, "candidates_token_count", None),
        total_tokens=getattr(usage_obj, "total_token_count", None),
    )


def _gemini_finish_reason(response: Any) -> str:
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        raw_finish_reason = getattr(candidates[0], "finish_reason", None)
        if raw_finish_reason is not None:
            return _normalize_finish_reason("gemini", raw_finish_reason)
    return "stop"


def _normalize_finish_reason(provider: str, raw_reason: Any) -> str:
    reason = str(raw_reason or "").strip().lower()
    if not reason:
        return "stop"
    if provider == "anthropic":
        return {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }.get(reason, "stop")
    if provider == "gemini":
        normalized = reason.removeprefix("finish_reason_")
        return {
            "stop": "stop",
            "max_tokens": "length",
            "tool_call": "tool_calls",
            "function_call": "tool_calls",
        }.get(normalized, "stop")
    return "stop"


def _usage_dict(
    *,
    prompt_tokens: Any,
    completion_tokens: Any,
    total_tokens: Any,
) -> dict[str, int] | None:
    usage: dict[str, int] = {}
    if isinstance(prompt_tokens, int):
        usage["prompt_tokens"] = prompt_tokens
    if isinstance(completion_tokens, int):
        usage["completion_tokens"] = completion_tokens
    if isinstance(total_tokens, int):
        usage["total_tokens"] = total_tokens
    return usage or None


def _openai_shaped_response(
    *,
    model: str,
    content: str,
    finish_reason: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
) -> Any:
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )
