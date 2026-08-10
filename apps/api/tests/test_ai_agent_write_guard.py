from __future__ import annotations

from ai_do_api.domains.ai.agent_write_guard import (
    latest_user_message_has_write_intent,
    write_tool_names_from_specs,
)
from ai_do_api.domains.ai.tool_contracts import AgentToolSpec


def _tool_spec(name: str) -> AgentToolSpec:
    return AgentToolSpec(
        name=name,
        description="test tool",
        input_schema={"type": "object", "properties": {}},
    )


def test_write_tool_names_from_specs_detects_registry_and_name_fallbacks() -> None:
    names = write_tool_names_from_specs(
        [
            _tool_spec("pms.update_task"),
            _tool_spec("custom.archive_record"),
            _tool_spec("pms.search_tasks"),
        ]
    )

    assert names == frozenset({"pms.update_task", "custom.archive_record"})


def test_latest_user_message_has_write_intent_detects_korean_and_english() -> None:
    assert latest_user_message_has_write_intent(
        [{"role": "user", "content": "PMS 이슈 상태를 in progress로 변경해줘"}]
    )
    assert latest_user_message_has_write_intent(
        [{"role": "user", "content": "Please update the task status"}]
    )


def test_latest_user_message_has_write_intent_ignores_how_to_requests() -> None:
    assert not latest_user_message_has_write_intent(
        [{"role": "user", "content": "PMS 이슈 상태 변경 방법 알려줘"}]
    )
    assert not latest_user_message_has_write_intent(
        [{"role": "user", "content": "How do I update a task?"}]
    )


def test_latest_user_message_has_write_intent_reads_list_text_parts() -> None:
    assert latest_user_message_has_write_intent(
        [
            {"role": "assistant", "content": "previous"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "PMS 이슈에 댓글 추가해줘"},
                    {"type": "image_url", "image_url": {"url": "mock://image"}},
                    {"type": "text", "text": 7},
                ],
            },
        ]
    )
