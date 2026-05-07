from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agents import Agent, ModelSettings, RunConfig, RunContextWrapper, Runner, function_tool

from ai_do_api.domains.ai.events import AgentEventEnvelope, make_envelope
from ai_do_api.domains.ai.internal_agent_contracts import LocalAgentTask
from ai_do_api.domains.ai.internal_agents import (
    LocalAgentRunner,
    LocalAgentRuntimeContext,
    run_local_agent_task,
)
from ai_do_api.domains.ai.manager_runtime.manager_stream import (
    AI_MANAGER_RUNTIME_PROFILE,
    AiManagerStreamContext,
    StaticAiManagerClient,
    run_ai_manager_stream,
)
from ai_do_api.domains.ai.manager_runtime.specialist_tool import RUN_LOCAL_SPECIALIST_TOOL_NAME


@dataclass(frozen=True, slots=True)
class OpenAIAiManagerRunContext:
    local_context: LocalAgentRuntimeContext
    local_runner: LocalAgentRunner


async def run_openai_ai_manager_stream(
    *,
    context: AiManagerStreamContext,
) -> AsyncIterator[AgentEventEnvelope]:
    if context.manager_input.prompt.status == "blocked":
        async for event in run_ai_manager_stream(
            context=context,
            manager_client=StaticAiManagerClient(),
        ):
            yield event
        return

    agent = build_openai_ai_manager_agent(context)
    sdk_context = OpenAIAiManagerRunContext(
        local_context=context.local_context,
        local_runner=context.local_runner,
    )
    result_stream = Runner.run_streamed(
        agent,
        input=_manager_input_text(context),
        context=sdk_context,
        max_turns=context.config.max_loops,
        run_config=build_openai_ai_manager_run_config(context),
    )

    emitted_content = False
    try:
        async for sdk_event in result_stream.stream_events():
            for event in _sdk_event_to_envelopes(context=context, sdk_event=sdk_event):
                if event.type == "content_delta":
                    emitted_content = True
                yield event
    except (asyncio.CancelledError, GeneratorExit):
        cancel = getattr(result_stream, "cancel", None)
        if callable(cancel):
            cancel()
        raise

    final_output = getattr(result_stream, "final_output", None)
    if not emitted_content and final_output:
        yield make_envelope(
            "content_delta",
            context.encoder.next_seq(),
            {"text": _final_output_text(final_output)},
        )

    yield _done_event(context, decision="final")


def build_openai_ai_manager_agent(
    context: AiManagerStreamContext,
) -> Agent[OpenAIAiManagerRunContext]:
    return Agent[OpenAIAiManagerRunContext](
        name="Doowon AI Manager",
        instructions=_manager_instructions(),
        model=context.config.model,
        model_settings=build_openai_ai_manager_model_settings(context),
        tools=[build_run_local_specialist_function_tool()],
        handoffs=[],
        mcp_servers=[],
    )


def build_openai_ai_manager_model_settings(
    context: AiManagerStreamContext,
) -> ModelSettings:
    return ModelSettings(
        temperature=context.temperature,
        max_tokens=context.max_tokens,
        parallel_tool_calls=False,
        store=context.config.store_response,
    )


def build_openai_ai_manager_run_config(
    context: AiManagerStreamContext,
) -> RunConfig:
    return RunConfig(
        model=context.config.model,
        model_settings=build_openai_ai_manager_model_settings(context),
        trace_include_sensitive_data=context.config.trace_sensitive_data,
        workflow_name="ai_do_ai_manager",
        trace_metadata={
            "adapter_id": context.config.adapter_id,
            "runtime_profile": AI_MANAGER_RUNTIME_PROFILE,
            "hosted_tools_enabled": str(context.config.hosted_tools_enabled).lower(),
            "response_storage": str(context.config.store_response).lower(),
        },
    )


def build_run_local_specialist_function_tool():
    @function_tool(
        name_override=RUN_LOCAL_SPECIALIST_TOOL_NAME,
        description_override=(
            "Execute one provider-independent internal agent inside the workspace boundary. "
            "Returns only LocalAgentResult redacted summary, artifact refs, "
            "coverage/gap metadata, and sensitivity labels."
        ),
        strict_mode=True,
    )
    def _run_local_specialist_tool(
        ctx: RunContextWrapper[OpenAIAiManagerRunContext],
        agent_id: str,
        objective: str,
        allowed_tool_names: list[str],
        context_boundary: str,
        expected_output: str,
        tool_arguments_json: str | None = None,
        approved_call_id: str | None = None,
    ) -> dict[str, Any]:
        task = LocalAgentTask(
            agent_id=agent_id,
            objective=objective,
            allowed_tool_names=allowed_tool_names,
            tool_arguments=_parse_tool_arguments_json(tool_arguments_json),
            approved_call_id=approved_call_id,
            context_boundary=context_boundary,
            expected_output=expected_output,
        )
        result = run_local_agent_task(
            task=task,
            context=ctx.context.local_context,
            runner=ctx.context.local_runner,
        )
        return result.model_dump(exclude_none=True)

    return _run_local_specialist_tool


def _parse_tool_arguments_json(tool_arguments_json: str | None) -> dict[str, Any]:
    if tool_arguments_json is None or not tool_arguments_json.strip():
        return {}
    parsed = json.loads(tool_arguments_json)
    if not isinstance(parsed, dict):
        raise ValueError("tool_arguments_json must decode to a JSON object")
    return parsed


def _sdk_event_to_envelopes(
    *,
    context: AiManagerStreamContext,
    sdk_event: Any,
) -> list[AgentEventEnvelope]:
    event_type = getattr(sdk_event, "type", "")
    if event_type == "raw_response_event":
        return _raw_response_event_to_envelopes(context=context, raw_event=sdk_event.data)
    if event_type != "run_item_stream_event":
        return []

    name = getattr(sdk_event, "name", "")
    item = getattr(sdk_event, "item", None)
    if name == "tool_called":
        return _tool_called_to_envelopes(context=context, item=item)
    if name == "tool_output":
        return _tool_output_to_envelopes(context=context, item=item)
    return []


def _raw_response_event_to_envelopes(
    *,
    context: AiManagerStreamContext,
    raw_event: Any,
) -> list[AgentEventEnvelope]:
    raw_type = str(getattr(raw_event, "type", ""))
    delta = getattr(raw_event, "delta", None)
    if not isinstance(delta, str) or not delta:
        return []
    if raw_type in {
        "response.output_text.delta",
        "response.refusal.delta",
    }:
        return [
            make_envelope(
                "content_delta",
                context.encoder.next_seq(),
                {"text": delta},
            )
        ]
    if "reasoning" in raw_type and context.stream_reasoning:
        return [
            make_envelope(
                "reasoning_delta",
                context.encoder.next_seq(),
                {"text": delta},
            )
        ]
    return []


def _tool_called_to_envelopes(
    *,
    context: AiManagerStreamContext,
    item: Any,
) -> list[AgentEventEnvelope]:
    raw_item = getattr(item, "raw_item", item)
    call_id = _tool_call_id(raw_item)
    tool_name = _tool_name(raw_item)
    arguments = _tool_arguments(raw_item)
    events = [
        make_envelope(
            "tool_call_started",
            context.encoder.next_seq(),
            {
                "call_id": call_id,
                "name": tool_name,
                "args_preview": _preview_text(arguments, limit=240),
            },
        )
    ]
    if arguments:
        events.append(
            make_envelope(
                "tool_call_args_delta",
                context.encoder.next_seq(),
                {
                    "call_id": call_id,
                    "delta": arguments,
                },
            )
        )
    return events


def _tool_output_to_envelopes(
    *,
    context: AiManagerStreamContext,
    item: Any,
) -> list[AgentEventEnvelope]:
    raw_item = getattr(item, "raw_item", item)
    output = getattr(item, "output", None)
    status, error = _tool_output_status(output)
    return [
        make_envelope(
            "tool_result",
            context.encoder.next_seq(),
            {
                "call_id": _tool_call_id(raw_item),
                "status": status,
                "result_preview": _preview_text(_dump_json(output), limit=1200)
                if status == "ok"
                else None,
                "error": error,
            },
        )
    ]


def _done_event(
    context: AiManagerStreamContext,
    *,
    decision: str,
) -> AgentEventEnvelope:
    return make_envelope(
        "done",
        context.encoder.next_seq(),
        {
            "finish_reason": "stop" if decision != "failed" else "error",
            "audit_id": None,
            "meta": {
                "policy": "ai_manager",
                "chosen_pool": "external",
                "decision_reason": decision,
                "forced_local": False,
                "pii_hits": _pii_hits(context.manager_input.prompt.removed_entity_types),
                "provider": context.config.provider,
                "model": context.config.model,
                "chosen_model": context.config.model,
                "runtime_profile": AI_MANAGER_RUNTIME_PROFILE,
                "runtime_routing_reason_codes": [
                    "ai_manager_openai_agents",
                    f"max_loops:{context.config.max_loops}",
                ],
                "external_egress_summary": {
                    "manager": "ai_manager",
                    "sdk": "openai_agents",
                    "prompt_status": context.manager_input.prompt.status,
                    "removed_entity_types": (
                        context.manager_input.prompt.removed_entity_types
                    ),
                    "response_storage": context.config.store_response,
                    "trace_sensitive_data": context.config.trace_sensitive_data,
                    "hosted_tools_enabled": context.config.hosted_tools_enabled,
                },
            },
        },
    )


def _manager_input_text(context: AiManagerStreamContext) -> str:
    return (
        "AiManagerInput JSON follows. Treat it as the only external "
        "planning input. Never infer or request raw internal data.\n\n"
        f"{context.manager_input.model_dump_json(exclude_none=True)}"
    )


def _manager_instructions() -> str:
    return """You are the Doowon AI manager.

Use the run_local_specialist function tool for any internal evidence, document,
RAG, task, meeting, calendar, or workspace data need. That tool delegates to
provider-independent internal agents running on the configured local model
profile; PMS, Planner, and Docs are not OpenAI handoff agents. You must not ask
for raw internal data, raw document text, product/order/customer identifiers,
prices, contracts, credentials, internal URLs, or raw tool results.

You may plan, select internal agents, review LocalAgentResult summaries,
identify gaps, ask the user for clarification, and produce the final answer.
LocalAgentResult is already redacted; do not try to expand it into raw data.

Prefer one focused internal agent task first. Stop when the answer is useful.
If evidence is incomplete or permission is needed, say that clearly instead of
inventing facts."""


def _tool_call_id(raw_item: Any) -> str:
    value = (
        getattr(raw_item, "call_id", None)
        or getattr(raw_item, "id", None)
        or getattr(raw_item, "tool_call_id", None)
    )
    return str(value or "openai-tool-call")


def _tool_name(raw_item: Any) -> str:
    value = getattr(raw_item, "name", None)
    if isinstance(value, str) and value:
        return value
    function = getattr(raw_item, "function", None)
    function_name = getattr(function, "name", None)
    if isinstance(function_name, str) and function_name:
        return function_name
    return RUN_LOCAL_SPECIALIST_TOOL_NAME


def _tool_arguments(raw_item: Any) -> str:
    value = getattr(raw_item, "arguments", None)
    if isinstance(value, str):
        return value
    if value is None:
        function = getattr(raw_item, "function", None)
        value = getattr(function, "arguments", None)
    if isinstance(value, str):
        return value
    return ""


def _tool_output_status(output: Any) -> tuple[str, str | None]:
    if isinstance(output, dict):
        status = output.get("status")
        if status == "completed":
            return ("ok", None)
        if status == "blocked":
            reason = output.get("blocked_reason")
            return ("rejected", str(reason or "blocked"))
        if status == "failed":
            reason = output.get("blocked_reason")
            return ("error", str(reason or "failed"))
    return ("ok", None)


def _final_output_text(final_output: Any) -> str:
    if isinstance(final_output, str):
        return final_output
    return _dump_json(final_output)


def _dump_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _pii_hits(removed_entity_types: list[str]) -> list[str]:
    return [
        entity_type.removeprefix("pii:")
        for entity_type in removed_entity_types
        if entity_type.startswith("pii:")
    ]


def _preview_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."
