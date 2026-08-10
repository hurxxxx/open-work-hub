from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def preview_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def render_tool_result_message(tool_name: str, result: Any) -> str:
    return f"도구 {tool_name} 실행 결과입니다.\n{preview_text(dump_json(result), limit=4000)}"


def serialize_tool_result_for_llm(
    *,
    tool_name: str,
    result: Any | None = None,
    error: str | None = None,
    limit: int = 4000,
) -> str:
    if error is not None:
        return dump_json(
            {
                "tool": tool_name,
                "status": "error",
                "error": preview_text(error, limit=max(64, limit - 96)),
            }
        )

    if result is None:
        return dump_json({"tool": tool_name, "status": "ok", "result": None})

    candidate = {
        "tool": tool_name,
        "status": "ok",
        "result": result,
    }
    dumped = dump_json(candidate)
    if len(dumped) <= limit:
        return dumped

    return dump_json(
        {
            "tool": tool_name,
            "status": "ok",
            "result_preview": preview_text(
                dump_json(result),
                limit=max(256, limit - 128),
            ),
            "truncated": True,
        }
    )


def tool_result_preview(result: Any) -> str:
    return preview_text(dump_json(result), limit=1200)


def sanitize_reject_reason_for_llm(reason: str | None, *, limit: int = 280) -> str | None:
    if reason is None:
        return None
    collapsed = " ".join(reason.split())
    if not collapsed:
        return None
    return preview_text(collapsed, limit=limit)


def build_rejected_tool_response_payload(
    *,
    tool_name: str,
    owner_domain: str,
    approval_required: bool,
    reject_reason: str | None,
) -> dict[str, Any]:
    return {
        "tool": tool_name,
        "owner_domain": owner_domain,
        "approval_required": approval_required,
        "result": {
            "status": "rejected",
            "reason": reject_reason,
        },
    }


@dataclass(frozen=True, slots=True)
class RejectedToolResultProjection:
    is_rejected: bool
    reason: str | None
    error_message: str
    result_preview: str | None


def is_rejected_tool_response(response: Mapping[str, Any] | None) -> bool:
    return _rejected_tool_result(response) is not None


def project_rejected_tool_response(
    response: Mapping[str, Any] | None,
    *,
    default_error: str = "Approval request was rejected.",
) -> RejectedToolResultProjection:
    result = _rejected_tool_result(response)
    reason = _reason_from_rejected_result(result) if result is not None else None
    return RejectedToolResultProjection(
        is_rejected=result is not None,
        reason=reason,
        error_message=reason or default_error,
        result_preview=tool_result_preview(result) if result is not None else None,
    )


def rejected_tool_reason_from_response(
    response: Mapping[str, Any] | None,
    *,
    limit: int = 280,
) -> str | None:
    return _reason_from_rejected_result(_rejected_tool_result(response), limit=limit)


def rejected_tool_error_message(
    response: Mapping[str, Any] | None,
    *,
    default: str = "Approval request was rejected.",
) -> str:
    return project_rejected_tool_response(response, default_error=default).error_message


def serialize_rejected_tool_result_for_llm(
    *,
    tool_name: str,
    reason: str | None,
) -> str:
    return dump_json(
        {
            "tool": tool_name,
            "status": "rejected",
            "reason": sanitize_reject_reason_for_llm(reason),
        }
    )


def _rejected_tool_result(response: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if response is None:
        return None
    result = response.get("result")
    if not isinstance(result, Mapping):
        return None
    return result if result.get("status") == "rejected" else None


def _reason_from_rejected_result(
    result: Mapping[str, Any] | None,
    *,
    limit: int = 280,
) -> str | None:
    if result is None:
        return None
    raw_reason = result.get("reason")
    if not isinstance(raw_reason, str):
        return None
    return sanitize_reject_reason_for_llm(raw_reason, limit=limit)


__all__ = [
    "RejectedToolResultProjection",
    "build_rejected_tool_response_payload",
    "dump_json",
    "is_rejected_tool_response",
    "preview_text",
    "project_rejected_tool_response",
    "rejected_tool_error_message",
    "rejected_tool_reason_from_response",
    "render_tool_result_message",
    "sanitize_reject_reason_for_llm",
    "serialize_rejected_tool_result_for_llm",
    "serialize_tool_result_for_llm",
    "tool_result_preview",
]
