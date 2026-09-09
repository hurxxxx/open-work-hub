from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.ai.tool_contracts import AgentToolSpec

WRITE_TOOL_REQUIRED_MESSAGE = (
    "요청은 생성/수정/삭제 같은 쓰기 작업으로 보이지만 실제 write tool 실행 결과가 없습니다. "
    "데이터가 변경됐다고 확인할 수 없으므로 완료됐다고 답할 수 없습니다. "
    "대상과 변경 내용을 확인한 뒤 다시 요청해 주세요."
)


def write_tool_names_from_specs(tool_specs: Sequence[AgentToolSpec]) -> frozenset[str]:
    registry = get_ai_capability_registry()
    names: set[str] = set()
    for spec in tool_specs:
        raw_name = spec.name
        descriptor = registry.get_descriptor(raw_name)
        descriptor_is_write = descriptor is not None and descriptor.mode == "write"
        if descriptor_is_write or _tool_name_looks_write(raw_name):
            names.add(raw_name)
    return frozenset(names)


def latest_user_message_has_write_intent(messages: list[dict[str, Any]]) -> bool:
    latest_text = ""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        latest_text = _message_content_text(message.get("content"))
        break
    if not latest_text:
        return False
    normalized = latest_text.lower()
    if any(
        marker in normalized
        for marker in (
            "방법",
            "어떻게",
            "가이드",
            "절차",
            "설명해",
            "알려줘",
            "can i",
            "how to",
            "how do",
        )
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "생성",
            "만들",
            "추가",
            "등록",
            "수정",
            "변경",
            "바꿔",
            "업데이트",
            "삭제",
            "지워",
            "제거",
            "댓글",
            "comment",
            "create",
            "add ",
            "update",
            "change",
            "delete",
            "remove",
        )
    )


def _tool_name_looks_write(tool_name: str) -> bool:
    return any(
        marker in tool_name
        for marker in (
            ".create_",
            ".update_",
            ".delete_",
            ".add_",
            ".remove_",
            ".archive_",
            ".restore_",
        )
    )


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                raw_text = item.get("text")
                if isinstance(raw_text, str):
                    parts.append(raw_text)
        return "\n".join(parts)
    return ""


__all__ = [
    "WRITE_TOOL_REQUIRED_MESSAGE",
    "latest_user_message_has_write_intent",
    "write_tool_names_from_specs",
]
