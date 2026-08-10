from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from open_work_hub_api.core.llm import LlmPoolConfig, LlmTaskContext, PolicyDecision, ResolvedLlmExecution
from open_work_hub_api.core.llm_errors import LlmProviderError
from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.core.llm_adapters import StreamChunk
from open_work_hub_api.domains.ai import agent as agent_module
from open_work_hub_api.domains.ai.events import EnvelopeEncoder
from open_work_hub_api.domains.ai.tool_contracts import AgentToolSpec
from open_work_hub_api.domains.ai.tool_runtime import ToolCallExecution


pytestmark = pytest.mark.anyio


def _ctx() -> LlmTaskContext:
    return LlmTaskContext(
        source="test.agent",
        actor_user_id="user-1",
        principal_kind="user",
        principal_id="user-1",
        workspace_id="ws-1",
        task_kind="chatbot",
        app_id="chatbot",
        workload_id="chatbot",
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
        healthcheck_timeout_seconds=5,
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


def _snapshot_model_meta(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "model": "mlx-community/model",
        "provider": "mlx-lm",
        "policy": "local_only",
        "chosen_pool": "local",
        "max_output_tokens": 1000,
        "reasoning_effort": "none",
    }
    values.update(overrides)
    return values


async def test_execution_from_snapshot_uses_current_registered_workload_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_config = _execution().config
    captured: dict[str, Any] = {}

    def fake_build_request(
        workload_id: str,
        context: Any,
        db: Any,
        **request_values: Any,
    ) -> SimpleNamespace:
        captured.update(
            workload_id=workload_id,
            context=context,
            db=db,
            request_values=request_values,
        )
        return SimpleNamespace(
            workload_route="local",
            workload_config=current_config,
            requested_model="mlx-community/model",
            max_tokens=640,
        )

    monkeypatch.setattr(agent_module, "build_llm_workload_request", fake_build_request)
    db = object()
    execution = agent_module._execution_from_snapshot(
        SimpleNamespace(model_meta=_snapshot_model_meta()),
        context=_ctx(),
        db=db,
    )

    assert not hasattr(agent_module, "get_pool_config")
    assert captured["workload_id"] == "chatbot"
    assert captured["context"].app_id == "chatbot"
    assert captured["db"] is db
    assert captured["request_values"] == {
        "messages": [],
        "max_tokens": 1000,
        "reasoning_effort": "none",
    }
    assert execution.config is current_config
    assert execution.chosen_model == "mlx-community/model"
    assert execution.resolved_max_tokens == 640


@pytest.mark.parametrize(
    ("snapshot_values", "current_values"),
    [
        ({"chosen_pool": "external", "policy": "external"}, {}),
        ({"provider": "different-provider"}, {}),
        ({"model": "different-model"}, {}),
        ({"policy": "external"}, {}),
        ({"provider": None}, {}),
        ({"model": None}, {}),
        ({}, {"workload_route": "external"}),
        ({}, {"workload_config": None}),
    ],
)
async def test_execution_from_snapshot_fails_closed_when_registered_identity_changed(
    monkeypatch: pytest.MonkeyPatch,
    snapshot_values: dict[str, Any],
    current_values: dict[str, Any],
) -> None:
    request_values = {
        "workload_route": "local",
        "workload_config": _execution().config,
        "requested_model": "mlx-community/model",
        "max_tokens": 640,
    }
    request_values.update(current_values)
    monkeypatch.setattr(
        agent_module,
        "build_llm_workload_request",
        lambda *args, **kwargs: SimpleNamespace(**request_values),
    )

    with pytest.raises(
        LlmProviderError,
        match="ai.agent_resume_model_configuration_changed",
    ):
        agent_module._execution_from_snapshot(
            SimpleNamespace(model_meta=_snapshot_model_meta(**snapshot_values)),
            context=_ctx(),
            db=object(),
        )


async def _collect_events(
    monkeypatch: pytest.MonkeyPatch,
    streams: list[list[StreamChunk]],
    *,
    max_turns: int = 4,
    captured_stream_kwargs: list[dict[str, Any]] | None = None,
    messages: list[dict[str, Any]] | None = None,
    tool_specs: list[AgentToolSpec] | None = None,
):
    stream_iter = iter(streams)

    async def fake_complete_gateway_chat_stream(gateway_execution: Any, _db: Any):
        if captured_stream_kwargs is not None:
            request = gateway_execution.request
            captured_stream_kwargs.append(
                {
                    "messages": gateway_execution.messages,
                    "temperature": request.temperature,
                    "stream_reasoning": request.stream_reasoning,
                    "tools": request.tools,
                    "tool_choice": request.tool_choice,
                    "parallel_tool_calls": request.parallel_tool_calls,
                    "agent_run_id": request.agent_run_id,
                    "conversation_id": request.conversation_id,
                }
            )
        for chunk in next(stream_iter):
            yield chunk, gateway_execution.decision, gateway_execution.llm_execution.config

    monkeypatch.setattr(
        agent_module,
        "complete_resolved_gateway_chat_stream",
        fake_complete_gateway_chat_stream,
    )

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
            tool_specs=tool_specs
            or [
                AgentToolSpec(
                    name="pms.search_tasks",
                    description="Search issues",
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                )
            ],
            bound_conversation=SimpleNamespace(id="conversation-1"),
        )
    ]


async def test_run_agent_turn_stream_uses_open_work_hub_identity_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_stream_kwargs: list[dict[str, Any]] = []

    await _collect_events(
        monkeypatch,
        [
            [
                StreamChunk(kind="content", text="안녕하세요."),
                StreamChunk(kind="done", finish_reason="stop"),
            ]
        ],
        captured_stream_kwargs=captured_stream_kwargs,
        messages=[{"role": "user", "content": "너는 누구야?"}],
    )

    messages = captured_stream_kwargs[0]["messages"]
    system_prompt = messages[0]["content"]
    assert messages[0]["role"] == "system"
    assert "Open Work Hub의 업무용 챗봇 AI 어시스턴트(Open Work Hub)" in system_prompt
    assert "저는 Open Work Hub의 업무용 챗봇 AI 어시스턴트(Open Work Hub)입니다." in system_prompt
    assert "기반 모델명이나 개발사를 너의 정체성처럼 말하지 않는다" in system_prompt


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
            AgentToolSpec(
                name="pms.update_task",
                description="Update issue",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            )
        ],
    )

    assert [event.type for event in events] == ["content_delta", "done"]
    assert "write tool 실행 결과가 없습니다" in events[0].data.text
    assert "성공적으로 변경" not in events[0].data.text
    assert events[-1].data.finish_reason == "stop"


async def test_run_agent_turn_stream_halts_on_approval_required_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_execute_tool_call(*args: Any, **kwargs: Any) -> ToolCallExecution:
        return ToolCallExecution(
            call_id="call-1",
            tool_name="pms.create_task",
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
                    tool_name="pms.create_task",
                ),
                StreamChunk(
                    kind="tool_call_args",
                    tool_call_id="call-1",
                    tool_name="pms.create_task",
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
