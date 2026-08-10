from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.llm import LlmTaskContext, ResolvedLlmExecution
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.ai.agent import run_agent_turn_stream
from open_work_hub_api.domains.ai.events import EnvelopeEncoder
from open_work_hub_api.domains.ai.runtime.graph_events import make_done_envelope_with_meta
from open_work_hub_api.domains.ai.runtime.graph_execution_fallback_policy import (
    GRAPH_NODE_RUNNER_ADAPTER_ID,
)
from open_work_hub_api.domains.ai.runtime.graph_evidence_packet import GRAPH_WRITER_AGENT_ID
from open_work_hub_api.domains.ai.runtime.graph_node_execution_projection import (
    graph_execution_adapter_error_summary,
    graph_node_execution_summary,
)
from open_work_hub_api.domains.ai.runtime.graph_node_output import (
    GraphNodeOutput,
    GraphNodeOutputCollector,
)
from open_work_hub_api.domains.ai.runtime.graph_prompting import (
    build_graph_node_messages,
    graph_node_scope_prompt,
    graph_writer_scope_prompt,
)
from open_work_hub_api.domains.ai.runtime.graph_schedule_summary import (
    ordered_graph_schedule_steps,
)
from open_work_hub_api.domains.ai.runtime.graph_tool_policy import graph_node_tool_specs
from open_work_hub_api.domains.ai.runtime.routing import RuntimeRoutingDecision
from open_work_hub_api.domains.ai.runtime.routing_metadata import runtime_routing_stream_kwargs
from open_work_hub_api.domains.ai.runtime.tool_calling import stream_tool_calling_enabled
from open_work_hub_api.domains.ai.tool_contracts import AgentToolSpec
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.conversations.models import Conversation


async def run_graph_node_runner_stream(
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
    steps = ordered_graph_schedule_steps(runtime_routing.graph_schedule_summary)
    node_outputs: list[GraphNodeOutput] = []
    graph_tools_enabled = stream_tool_calling_enabled(
        settings,
        execution.pool,
        execution.config.provider,
    )

    for step in steps:
        agent_id = step.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id or agent_id == GRAPH_WRITER_AGENT_ID:
            continue
        node_output = await _run_hidden_graph_node(
            context=context,
            execution=execution,
            db=db,
            workspace=workspace,
            principal=principal,
            user=user,
            agent_id=agent_id,
            messages=messages,
            temperature=temperature,
            settings=settings,
            agent_run_id=agent_run_id,
            tool_specs=graph_node_tool_specs(
                agent_id,
                filtered_tool_specs,
                tools_enabled=graph_tools_enabled,
            ),
            bound_conversation=bound_conversation,
            scope_system_prompt=graph_node_scope_prompt(
                scope_system_prompt=scope_system_prompt,
                runtime_routing=runtime_routing,
                agent_id=agent_id,
            ),
            allowed_app_ids=allowed_app_ids,
            runtime_routing=runtime_routing,
            prior_outputs=node_outputs,
            step=step,
        )
        node_outputs.append(node_output)

    writer_scope_prompt = graph_writer_scope_prompt(
        scope_system_prompt=scope_system_prompt,
        runtime_routing=runtime_routing,
        messages=messages,
        node_outputs=node_outputs,
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
        tool_specs=[],
        bound_conversation=bound_conversation,
        scope_system_prompt=writer_scope_prompt,
        allowed_app_ids=allowed_app_ids,
        **runtime_routing_stream_kwargs(runtime_routing),
        parallel_tool_calls=None,
        include_agent_run_id_in_done=True,
    ):
        if event.type == "done":
            writer_status = "failed" if event.data.finish_reason == "error" else "completed"
            node_summary = graph_node_execution_summary(
                adapter=GRAPH_NODE_RUNNER_ADAPTER_ID,
                node_outputs=node_outputs,
                planned_steps=steps,
                writer_status=writer_status,
                messages=messages,
                candidate_summary=runtime_routing.graph_candidate_summary,
                external_planner_execution_summary=(
                    runtime_routing.external_planner_execution_summary
                ),
                external_search_execution_summary=(
                    runtime_routing.external_search_execution_summary
                ),
            )
            yield make_done_envelope_with_meta(
                event,
                {"graph_node_execution_summary": node_summary},
            )
            continue
        yield event


async def _run_hidden_graph_node(
    *,
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    agent_id: str,
    messages: list[dict[str, Any]],
    temperature: float | None,
    settings: Any,
    agent_run_id: str,
    tool_specs: Sequence[AgentToolSpec],
    bound_conversation: Conversation | None,
    scope_system_prompt: str | None,
    allowed_app_ids: list[str] | None,
    runtime_routing: RuntimeRoutingDecision,
    prior_outputs: list[GraphNodeOutput],
    step: dict[str, Any],
) -> GraphNodeOutput:
    hidden_messages = build_graph_node_messages(
        messages,
        agent_id=agent_id,
        step=step,
        prior_outputs=prior_outputs,
        candidate_summary=runtime_routing.graph_candidate_summary,
        external_planner_execution_summary=(runtime_routing.external_planner_execution_summary),
        external_search_execution_summary=runtime_routing.external_search_execution_summary,
    )
    hidden_encoder = EnvelopeEncoder()
    output_collector = GraphNodeOutputCollector.for_agent(agent_id)
    async for event in run_agent_turn_stream(
        context=context,
        execution=execution,
        db=db,
        workspace=workspace,
        principal=principal,
        user=user,
        messages=hidden_messages,
        temperature=temperature,
        stream_reasoning=False,
        encoder=hidden_encoder,
        max_turns=settings.ai_agent_max_turns,
        max_tool_calls=settings.ai_agent_max_tool_calls,
        max_consecutive_tool_errors=settings.ai_agent_max_consecutive_tool_errors,
        agent_run_id=agent_run_id,
        tool_specs=tool_specs,
        bound_conversation=bound_conversation,
        scope_system_prompt=scope_system_prompt,
        allowed_app_ids=allowed_app_ids,
        **runtime_routing_stream_kwargs(runtime_routing),
        parallel_tool_calls=None,
        include_agent_run_id_in_done=False,
    ):
        output_collector.collect_event(event)

    return output_collector.build()


def attach_graph_execution_adapter_error_summary(
    meta: dict[str, Any],
    *,
    runtime_routing: RuntimeRoutingDecision,
    messages: list[dict[str, Any]],
    error_class: str,
) -> dict[str, Any]:
    if runtime_routing.graph_execution_adapter != GRAPH_NODE_RUNNER_ADAPTER_ID:
        return meta
    if meta.get("graph_node_execution_summary") is not None:
        return meta
    updated = dict(meta)
    steps = ordered_graph_schedule_steps(runtime_routing.graph_schedule_summary)
    updated["graph_node_execution_summary"] = graph_execution_adapter_error_summary(
        adapter=GRAPH_NODE_RUNNER_ADAPTER_ID,
        planned_steps=steps,
        messages=messages,
        error_class=error_class,
        candidate_summary=runtime_routing.graph_candidate_summary,
        external_planner_execution_summary=(
            runtime_routing.external_planner_execution_summary
        ),
        external_search_execution_summary=(
            runtime_routing.external_search_execution_summary
        ),
    )
    return updated


__all__ = [
    "attach_graph_execution_adapter_error_summary",
    "run_graph_node_runner_stream",
]
