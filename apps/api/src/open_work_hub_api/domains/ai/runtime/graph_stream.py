from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.llm import LlmTaskContext, ResolvedLlmExecution
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.ai.agent import run_agent_turn_stream
from open_work_hub_api.domains.ai.events import EnvelopeEncoder
from open_work_hub_api.domains.ai.runtime.graph_execution_fallback_policy import (
    GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID,
    GRAPH_NODE_RUNNER_ADAPTER_ID,
)
from open_work_hub_api.domains.ai.runtime.graph_node_runner_stream import (
    attach_graph_execution_adapter_error_summary,
    run_graph_node_runner_stream,
)
from open_work_hub_api.domains.ai.runtime.graph_prompting import (
    graph_execution_scope_prompt,
)
from open_work_hub_api.domains.ai.runtime.graph_tool_policy import (
    read_only_tool_specs,
)
from open_work_hub_api.domains.ai.runtime.routing import RuntimeRoutingDecision
from open_work_hub_api.domains.ai.runtime.routing_metadata import runtime_routing_stream_kwargs
from open_work_hub_api.domains.ai.runtime.tool_calling import stream_tool_calling_enabled
from open_work_hub_api.domains.ai.tool_contracts import AgentToolSpec
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.conversations.models import Conversation


def should_use_graph_execution_adapter(runtime_routing: RuntimeRoutingDecision) -> bool:
    return (
        runtime_routing.graph_used
        and runtime_routing.graph_execution_status == "adapter_selected"
        and runtime_routing.graph_execution_adapter
        in {
            GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID,
            GRAPH_NODE_RUNNER_ADAPTER_ID,
        }
    )


async def run_graph_execution_adapter_stream(
    *,
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    messages: list[dict[str, Any]],
    temperature: float | None,
    stream_reasoning: bool,
    encoder: EnvelopeEncoder,
    settings: Any,
    agent_run_id: str,
    filtered_tool_specs: Sequence[AgentToolSpec],
    bound_conversation: Conversation | None,
    scope_system_prompt: str | None,
    allowed_app_ids: list[str] | None,
    runtime_routing: RuntimeRoutingDecision,
) -> AsyncIterator[Any]:
    if runtime_routing.graph_execution_adapter == GRAPH_NODE_RUNNER_ADAPTER_ID:
        async for event in run_graph_node_runner_stream(
            context=context,
            execution=execution,
            db=db,
            workspace=workspace,
            principal=principal,
            user=user,
            messages=messages,
            temperature=temperature,
            stream_reasoning=stream_reasoning,
            encoder=encoder,
            settings=settings,
            agent_run_id=agent_run_id,
            filtered_tool_specs=filtered_tool_specs,
            bound_conversation=bound_conversation,
            scope_system_prompt=scope_system_prompt,
            allowed_app_ids=allowed_app_ids,
            runtime_routing=runtime_routing,
        ):
            yield event
        return

    async for event in _run_graph_instructed_single_loop_stream(
        context=context,
        execution=execution,
        db=db,
        workspace=workspace,
        principal=principal,
        user=user,
        messages=messages,
        temperature=temperature,
        stream_reasoning=stream_reasoning,
        encoder=encoder,
        settings=settings,
        agent_run_id=agent_run_id,
        filtered_tool_specs=filtered_tool_specs,
        bound_conversation=bound_conversation,
        scope_system_prompt=scope_system_prompt,
        allowed_app_ids=allowed_app_ids,
        runtime_routing=runtime_routing,
    ):
        yield event


async def _run_graph_instructed_single_loop_stream(
    *,
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    messages: list[dict[str, Any]],
    temperature: float | None,
    stream_reasoning: bool,
    encoder: EnvelopeEncoder,
    settings: Any,
    agent_run_id: str,
    filtered_tool_specs: Sequence[AgentToolSpec],
    bound_conversation: Conversation | None,
    scope_system_prompt: str | None,
    allowed_app_ids: list[str] | None,
    runtime_routing: RuntimeRoutingDecision,
) -> AsyncIterator[Any]:
    graph_tool_specs = (
        read_only_tool_specs(filtered_tool_specs)
        if stream_tool_calling_enabled(settings, execution.pool, execution.config.provider)
        else []
    )
    graph_scope_system_prompt = graph_execution_scope_prompt(
        scope_system_prompt=scope_system_prompt,
        runtime_routing=runtime_routing,
    )
    async for event in run_agent_turn_stream(
        context=context,
        execution=execution,
        db=db,
        workspace=workspace,
        principal=principal,
        user=user,
        messages=messages,
        temperature=temperature,
        stream_reasoning=stream_reasoning,
        encoder=encoder,
        max_turns=settings.ai_agent_max_turns,
        max_tool_calls=settings.ai_agent_max_tool_calls,
        max_consecutive_tool_errors=settings.ai_agent_max_consecutive_tool_errors,
        agent_run_id=agent_run_id,
        tool_specs=graph_tool_specs,
        bound_conversation=bound_conversation,
        scope_system_prompt=graph_scope_system_prompt,
        allowed_app_ids=allowed_app_ids,
        **runtime_routing_stream_kwargs(runtime_routing),
        parallel_tool_calls=None,
        include_agent_run_id_in_done=True,
    ):
        yield event


__all__ = [
    "attach_graph_execution_adapter_error_summary",
    "run_graph_execution_adapter_stream",
    "should_use_graph_execution_adapter",
]
