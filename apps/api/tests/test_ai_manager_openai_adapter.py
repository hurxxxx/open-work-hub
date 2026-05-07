from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_do_api.domains.ai import events as ai_events
from ai_do_api.domains.ai.events import EnvelopeEncoder
from ai_do_api.domains.ai.manager_runtime import (
    AiManagerConfig,
    AiManagerStreamContext,
    StaticLocalSpecialistRunner,
    build_ai_manager_input,
    build_local_specialist_tool_context,
)
from ai_do_api.domains.ai.manager_runtime import openai_adapter


class FakeRunStream:
    def __init__(self, sdk_events: list[Any], *, final_output: Any = None) -> None:
        self._sdk_events = list(sdk_events)
        self.final_output = final_output
        self.cancelled = False

    async def stream_events(self):
        for event in self._sdk_events:
            yield event

    def cancel(self) -> None:
        self.cancelled = True


def _config() -> AiManagerConfig:
    return AiManagerConfig(
        adapter_id="openai_agents_ai_manager.v1",
        enabled=True,
        ready=True,
        disabled_reason=None,
        provider="openai",
        model="gpt-test",
        max_loops=3,
        trace_sensitive_data=False,
        store_response=False,
        hosted_tools_enabled=False,
    )


def _context(
    *,
    raw_prompt: str = "문서를 근거로 요약해줘",
    stream_reasoning: bool = True,
) -> AiManagerStreamContext:
    return AiManagerStreamContext(
        config=_config(),
        manager_input=build_ai_manager_input(
            raw_prompt=raw_prompt,
            available_agent_ids=["domain.docs"],
            available_tool_names=["docs.search"],
            workspace_metadata={"scope": "workspace_current"},
        ),
        local_context=build_local_specialist_tool_context(
            enabled_app_ids=["ai", "docs"],
            allowed_app_ids=["ai", "docs"],
            available_tool_names=["docs.search"],
        ),
        local_runner=StaticLocalSpecialistRunner(redacted_summary="safe local summary"),
        encoder=EnvelopeEncoder(),
        stream_reasoning=stream_reasoning,
        temperature=0.2,
        max_tokens=1024,
    )


async def _collect(context: AiManagerStreamContext) -> list[dict[str, Any]]:
    return [
        event.model_dump(exclude_none=True)
        async for event in openai_adapter.run_openai_ai_manager_stream(
            context=context,
        )
    ]


@pytest.mark.anyio
async def test_openai_adapter_builds_sdk_agent_with_safe_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run_streamed(agent, input, context, max_turns, run_config, **kwargs):
        captured.update(
            {
                "agent": agent,
                "input": input,
                "context": context,
                "max_turns": max_turns,
                "run_config": run_config,
                "kwargs": kwargs,
            }
        )
        return FakeRunStream(
            [
                SimpleNamespace(
                    type="raw_response_event",
                    data=SimpleNamespace(
                        type="response.output_text.delta",
                        delta="final answer",
                    ),
                )
            ]
        )

    monkeypatch.setattr(
        openai_adapter.Runner,
        "run_streamed",
        staticmethod(fake_run_streamed),
    )

    events = await _collect(_context())

    assert [event["type"] for event in events] == ["content_delta", "done"]
    agent = captured["agent"]
    assert agent.model == "gpt-test"
    assert [tool.name for tool in agent.tools] == ["run_local_specialist"]
    assert agent.handoffs == []
    assert agent.mcp_servers == []
    assert captured["max_turns"] == 3
    assert "AiManagerInput JSON follows" in captured["input"]
    run_config = captured["run_config"]
    assert run_config.trace_include_sensitive_data is False
    assert run_config.model_settings.store is False
    assert run_config.model_settings.parallel_tool_calls is False
    assert run_config.model_settings.temperature == 0.2
    assert run_config.model_settings.max_tokens == 1024
    assert run_config.trace_metadata["hosted_tools_enabled"] == "false"
    assert run_config.trace_metadata["response_storage"] == "false"


@pytest.mark.anyio
async def test_openai_adapter_streams_tool_events_and_redacted_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_streamed(*args, **kwargs):
        del args, kwargs
        return FakeRunStream(
            [
                SimpleNamespace(
                    type="run_item_stream_event",
                    name="tool_called",
                    item=SimpleNamespace(
                        raw_item=SimpleNamespace(
                            call_id="call-1",
                            name="run_local_specialist",
                            arguments='{"agent_id":"domain.docs"}',
                        )
                    ),
                ),
                SimpleNamespace(
                    type="run_item_stream_event",
                    name="tool_output",
                    item=SimpleNamespace(
                        raw_item=SimpleNamespace(call_id="call-1"),
                        output={
                            "agent_id": "domain.docs",
                            "status": "completed",
                            "redacted_summary": "safe local summary",
                        },
                    ),
                ),
                SimpleNamespace(
                    type="raw_response_event",
                    data=SimpleNamespace(
                        type="response.output_text.delta",
                        delta="reviewed final",
                    ),
                ),
            ]
        )

    monkeypatch.setattr(
        openai_adapter.Runner,
        "run_streamed",
        staticmethod(fake_run_streamed),
    )

    events = await _collect(_context())

    assert [event["type"] for event in events] == [
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "content_delta",
        "done",
    ]
    assert events[0]["data"]["name"] == "run_local_specialist"
    assert events[2]["data"]["status"] == "ok"
    assert "safe local summary" in events[2]["data"]["result_preview"]
    assert events[-1]["data"]["meta"]["external_egress_summary"] == {
        "manager": "ai_manager",
        "sdk": "openai_agents",
        "prompt_status": "raw_allowed",
        "removed_entity_types": [],
        "response_storage": False,
        "trace_sensitive_data": False,
        "hosted_tools_enabled": False,
    }


@pytest.mark.anyio
async def test_openai_adapter_streams_reasoning_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_streamed(*args, **kwargs):
        del args, kwargs
        return FakeRunStream(
            [
                SimpleNamespace(
                    type="raw_response_event",
                    data=SimpleNamespace(
                        type="response.reasoning_summary_text.delta",
                        delta="thinking",
                    ),
                )
            ],
            final_output="final fallback",
        )

    monkeypatch.setattr(
        openai_adapter.Runner,
        "run_streamed",
        staticmethod(fake_run_streamed),
    )

    events = await _collect(_context(stream_reasoning=False))

    assert [event["type"] for event in events] == ["content_delta", "done"]
    assert events[0]["data"]["text"] == "final fallback"


@pytest.mark.anyio
async def test_openai_adapter_does_not_call_sdk_for_blocked_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_run_streamed(*args, **kwargs):
        del args, kwargs
        raise AssertionError("SDK should not be called for blocked prompt")

    monkeypatch.setattr(
        openai_adapter.Runner,
        "run_streamed",
        staticmethod(fail_run_streamed),
    )

    events = await _collect(_context(raw_prompt="  "))

    assert [event["type"] for event in events] == [
        "reasoning_delta",
        "content_delta",
        "done",
    ]
    assert events[-1]["data"]["meta"]["decision_reason"] == "ask_user"


def test_openai_adapter_tool_schema_is_strict() -> None:
    tool = openai_adapter.build_run_local_specialist_function_tool()

    assert tool.name == "run_local_specialist"
    assert tool.strict_json_schema is True
    assert set(tool.params_json_schema["properties"]) == {
        "agent_id",
        "objective",
        "allowed_tool_names",
        "tool_arguments_json",
        "approved_call_id",
        "context_boundary",
        "expected_output",
    }
    assert tool.params_json_schema["additionalProperties"] is False


def test_openai_adapter_events_validate_against_stream_contract() -> None:
    context = _context()
    sdk_event = SimpleNamespace(
        type="raw_response_event",
        data=SimpleNamespace(type="response.output_text.delta", delta="hello"),
    )

    events = openai_adapter._sdk_event_to_envelopes(  # noqa: SLF001
        context=context,
        sdk_event=sdk_event,
    )

    adapter = ai_events._ENVELOPE_ADAPTER  # noqa: SLF001
    assert adapter.validate_python(events[0].model_dump()) == events[0]
