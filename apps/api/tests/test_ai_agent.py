from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from aidoo_api.core.llm import LlmPoolConfig, LlmTaskContext, PolicyDecision, ResolvedLlmExecution
from aidoo_api.core.principal import user_principal
from aidoo_api.core.llm_adapters import StreamChunk
from aidoo_api.domains.ai import agent as agent_module
from aidoo_api.domains.ai.events import EnvelopeEncoder
from aidoo_api.domains.ai.tool_runtime import ToolCallExecution


pytestmark = pytest.mark.anyio


def _ctx() -> LlmTaskContext:
    return LlmTaskContext(
        source="test.agent",
        actor_user_id="user-1",
        principal_kind="user",
        principal_id="user-1",
        workspace_id="ws-1",
        task_kind="chatbot",
    )


def _execution() -> ResolvedLlmExecution:
    decision = PolicyDecision(
        policy="local_only",
        chosen_pool="local",
        reason="policy_local_only",
    )
    config = LlmPoolConfig(
        pool="local",
        provider="mlx-lm",
        base_url="http://127.0.0.1:8080/v1",
        api_key="mlx",
        default_model="mlx-community/model",
        canonical_model="local/current-moe-test-profile",
        long_generation_timeout_seconds=30,
        enabled=True,
    )
    return ResolvedLlmExecution(
        pool="local",
        decision=decision,
        config=config,
        chosen_model="mlx-community/model",
        resolved_max_tokens=1000,
        resolved_reasoning_effort="none",
    )


async def _collect_events(
    monkeypatch: pytest.MonkeyPatch,
    streams: list[list[StreamChunk]],
    *,
    max_turns: int = 4,
    captured_stream_kwargs: list[dict[str, Any]] | None = None,
    messages: list[dict[str, Any]] | None = None,
    tool_specs: list[dict[str, Any]] | None = None,
):
    stream_iter = iter(streams)

    async def fake_complete_chat_stream(*args: Any, **kwargs: Any):
        if captured_stream_kwargs is not None:
            captured_stream_kwargs.append(dict(kwargs))
        for chunk in next(stream_iter):
            yield chunk, _execution().decision, _execution().config

    monkeypatch.setattr(agent_module, "complete_chat_stream", fake_complete_chat_stream)

    return [
        event
        async for event in agent_module.run_agent_turn_stream(
            context=_ctx(),
            execution=_execution(),
            db=SimpleNamespace(commit=lambda: None),
            workspace=SimpleNamespace(id="ws-1"),
            principal=user_principal(
                workspace_id="ws-1",
                user_id="user-1",
                source="test.agent",
            ),
            user=SimpleNamespace(id="user-1"),
            messages=messages or [{"role": "user", "content": "hi"}],
            temperature=0.2,
            stream_reasoning=True,
            encoder=EnvelopeEncoder(),
            max_turns=max_turns,
            max_tool_calls=8,
            max_consecutive_tool_errors=3,
            agent_run_id="agent-run-1",
            tool_specs=tool_specs or [
                {
                    "type": "function",
                    "function": {
                        "name": "pms.search_issues",
                        "description": "Search issues",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            bound_conversation=SimpleNamespace(id="conversation-1"),
        )
    ]


async def test_run_agent_turn_stream_passes_plain_response_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(kind="content", text="hello"),
                StreamChunk(
                    kind="usage",
                    usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                ),
                StreamChunk(kind="done", finish_reason="stop"),
            ]
        ],
    )

    assert [event.type for event in events] == ["content_delta", "usage", "done"]
    assert events[-1].data.finish_reason == "stop"


async def test_run_agent_turn_stream_blocks_write_success_without_write_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(kind="content", text="PMS 이슈가 성공적으로 변경되었습니다."),
                StreamChunk(kind="done", finish_reason="stop"),
            ]
        ],
        messages=[{"role": "user", "content": "PMS 이슈 상태를 in progress로 변경해줘"}],
        tool_specs=[
            {
                "type": "function",
                "function": {
                    "name": "pms.update_issue",
                    "description": "Update issue",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ],
    )

    assert [event.type for event in events] == ["content_delta", "done"]
    assert "write tool 실행 결과가 없습니다" in events[0].data.text
    assert "성공적으로 변경" not in events[0].data.text
    assert events[-1].data.finish_reason == "stop"


async def test_run_agent_turn_stream_executes_tool_then_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool_call(*args: Any, **kwargs: Any) -> ToolCallExecution:
        return ToolCallExecution(
            call_id="call-1",
            tool_name="pms.search_issues",
            arguments_json='{"q":"bug"}',
            status="ok",
            response={
                "tool": "pms.search_issues",
                "owner_domain": "pms",
                "approval_required": False,
                "result": {"items": [{"id": "issue-1", "title": "Bug"}]},
            },
        )

    monkeypatch.setattr(agent_module, "execute_tool_call", fake_execute_tool_call)

    events = await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(
                    kind="tool_call_start",
                    tool_call_id="call-1",
                    tool_name="pms.search_issues",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-1",
                    tool_name="pms.search_issues",
                    args_delta='{"q":"bug"}',
                ),
                StreamChunk(kind="done", finish_reason="tool_calls"),
            ],
            [
                StreamChunk(kind="content", text="Bug 한 건을 찾았습니다."),
                StreamChunk(kind="done", finish_reason="stop"),
            ],
        ],
    )

    assert [event.type for event in events] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert events[2].data.status == "ok"
    assert events[-1].data.finish_reason == "stop"


async def test_run_agent_turn_stream_forces_final_answer_after_tool_turn_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool_call(*args: Any, **kwargs: Any) -> ToolCallExecution:
        return ToolCallExecution(
            call_id=str(kwargs["call_id"]),
            tool_name=str(kwargs["tool_name"]),
            arguments_json=kwargs["arguments_json"]
            if "arguments_json" in kwargs
            else '{"q":"런칭 체크리스트"}',
            status="ok",
            response={
                "tool": kwargs["tool_name"],
                "owner_domain": "docs",
                "approval_required": False,
                "result": {"items": [{"id": "doc-1", "title": "런칭 체크리스트"}]},
            },
        )

    captured_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(agent_module, "execute_tool_call", fake_execute_tool_call)

    events = await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(
                    kind="tool_call_start",
                    tool_call_id="call-1",
                    tool_name="docs.list_hub",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-1",
                    tool_name="docs.list_hub",
                    args_delta='{"q":"런칭 체크리스트"}',
                ),
                StreamChunk(kind="done", finish_reason="tool_calls"),
            ],
            [
                StreamChunk(
                    kind="tool_call_start",
                    tool_call_id="call-2",
                    tool_name="docs.get_item",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-2",
                    tool_name="docs.get_item",
                    args_delta='{"item_id":"doc-1"}',
                ),
                StreamChunk(kind="done", finish_reason="tool_calls"),
            ],
            [
                StreamChunk(kind="content", text="런칭 체크리스트의 남은 리스크는 보안 승인입니다."),
                StreamChunk(kind="done", finish_reason="stop"),
            ],
        ],
        max_turns=2,
        captured_stream_kwargs=captured_calls,
    )

    assert [event.type for event in events] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert events[-2].data.text.startswith("런칭 체크리스트")
    assert events[-1].data.finish_reason == "stop"
    assert captured_calls[-1]["tools"] is None
    assert captured_calls[-1]["tool_choice"] is None


async def test_run_agent_turn_stream_finalizes_after_duplicate_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool_call(*args: Any, **kwargs: Any) -> ToolCallExecution:
        return ToolCallExecution(
            call_id=str(kwargs["call_id"]),
            tool_name="docs.read_page",
            arguments_json='{"page_id":"p1"}',
            status="ok",
            response={
                "tool": "docs.read_page",
                "owner_domain": "docs",
                "approval_required": False,
                "result": {"id": "p1"},
            },
        )

    monkeypatch.setattr(agent_module, "execute_tool_call", fake_execute_tool_call)

    events = await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(
                    kind="tool_call_start",
                    tool_call_id="call-1",
                    tool_name="docs.read_page",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-1",
                    tool_name="docs.read_page",
                    args_delta='{"page_id":"p1"}',
                ),
                StreamChunk(kind="done", finish_reason="tool_calls"),
            ],
            [
                StreamChunk(
                    kind="tool_call_start",
                    tool_call_id="call-2",
                    tool_name="docs.read_page",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-2",
                    tool_name="docs.read_page",
                    args_delta='{"page_id":"p1"}',
                ),
                StreamChunk(kind="done", finish_reason="tool_calls"),
            ],
            [
                StreamChunk(kind="content", text="기존 조회 결과로 답변합니다."),
                StreamChunk(kind="done", finish_reason="stop"),
            ],
        ],
    )

    assert [event.type for event in events] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert events[5].data.status == "error"
    assert "중복 도구 호출" in events[5].data.error
    assert events[-1].data.finish_reason == "stop"


async def test_run_agent_turn_stream_allows_model_recovery_after_tool_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool_call(*args: Any, **kwargs: Any) -> ToolCallExecution:
        return ToolCallExecution(
            call_id="call-1",
            tool_name="meeting.find_availability",
            arguments_json='{"from":"2026-05-01"}',
            status="error",
            error_message="calendar unavailable",
        )

    monkeypatch.setattr(agent_module, "execute_tool_call", fake_execute_tool_call)

    events = await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(
                    kind="tool_call_start",
                    tool_call_id="call-1",
                    tool_name="meeting.find_availability",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-1",
                    tool_name="meeting.find_availability",
                    args_delta='{"from":"2026-05-01"}',
                ),
                StreamChunk(kind="done", finish_reason="tool_calls"),
            ],
            [
                StreamChunk(kind="content", text="현재 일정 시스템 응답이 없습니다."),
                StreamChunk(kind="done", finish_reason="stop"),
            ],
        ],
    )

    assert any(event.type == "tool_result" and event.data.status == "error" for event in events)
    assert events[-1].data.finish_reason == "stop"


async def test_run_agent_turn_stream_halts_on_approval_required_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_tool_call(*args: Any, **kwargs: Any) -> ToolCallExecution:
        return ToolCallExecution(
            call_id="call-1",
            tool_name="pms.create_issue",
            arguments_json='{"title":"Approval issue"}',
            status="blocked",
            resource_preview="Create PMS issue Approval issue",
        )

    def fake_persist_snapshot_on_halt(*args: Any, **kwargs: Any) -> SimpleNamespace:
        captured["messages_json"] = kwargs["messages_json"]
        return SimpleNamespace(id=kwargs["snapshot_id"])

    def fake_create_pending_approval(*args: Any, **kwargs: Any) -> SimpleNamespace:
        captured["resource_preview"] = kwargs["resource_preview"]
        return SimpleNamespace(
            id="approval-1",
            expires_at=datetime(2026, 5, 1, 10, 0, 0),
            resource_preview=kwargs["resource_preview"],
        )

    monkeypatch.setattr(agent_module, "execute_tool_call", fake_execute_tool_call)
    monkeypatch.setattr(
        agent_module.ai_approvals,
        "persist_snapshot_on_halt",
        fake_persist_snapshot_on_halt,
    )
    monkeypatch.setattr(
        agent_module.ai_approvals,
        "create_pending_approval",
        fake_create_pending_approval,
    )

    events = await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(
                    kind="tool_call_start",
                    tool_call_id="call-1",
                    tool_name="pms.create_issue",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-1",
                    tool_name="pms.create_issue",
                    args_delta='{"title":"Approval issue"}',
                ),
                StreamChunk(kind="done", finish_reason="tool_calls"),
            ]
        ],
    )

    assert [event.type for event in events] == [
        "tool_call_started",
        "tool_call_args_delta",
        "approval_required",
        "done",
    ]
    assert events[2].data.approval_id == "approval-1"
    assert events[2].data.call_id == "call-1"
    assert events[3].data.finish_reason == "awaiting_approval"
    assert events[3].data.meta.pending_approval_id == "approval-1"
    assert events[3].data.meta.pending_call_id == "call-1"
    assert events[3].data.meta.agent_run_id == "agent-run-1"
    assert captured["resource_preview"] == "Create PMS issue Approval issue"
    assert not any("tool_calls" in message for message in captured["messages_json"])
