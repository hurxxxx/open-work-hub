from __future__ import annotations

from fastapi import HTTPException

from ai_do_api.core.i18n import LocalizedApiMessage


def tool_http_exception_message(
    error: HTTPException,
    *,
    default: str = "AI tool execution failed.",
) -> str:
    detail = error.detail
    if isinstance(detail, str):
        return detail
    if isinstance(detail, LocalizedApiMessage):
        return detail.code
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return default


__all__ = ["tool_http_exception_message"]
