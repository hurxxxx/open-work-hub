from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Protocol

from aidoo_api.domains.ai.events import AgentEventEnvelope, EnvelopeEncoder, make_envelope
from aidoo_api.domains.ai.manager_runtime.config import AiManagerConfig
from aidoo_api.domains.ai.manager_runtime.contracts import (
    AiManagerInput,
    LocalAgentResult,
    LocalAgentTask,
    ManagerPlan,
    ManagerReview,
    build_manager_prompt_payload,
)
from aidoo_api.domains.ai.manager_runtime.specialist_tool import RUN_LOCAL_SPECIALIST_TOOL_NAME
from aidoo_api.domains.ai.internal_agents import (
    LocalAgentRunner,
    LocalAgentRuntimeContext,
    run_local_agent_task,
)


AI_MANAGER_RUNTIME_PROFILE = "ai_manager"


class AiManagerClient(Protocol):
    def create_plan(self, manager_input: AiManagerInput) -> ManagerPlan:
        """Return the manager's first internal-agent plan."""

    def review_results(
        self,
        *,
        manager_input: AiManagerInput,
        plan: ManagerPlan,
        local_results: list[LocalAgentResult],
        loop_index: int,
    ) -> ManagerReview:
        """Review internal agent output and decide whether to finish."""


@dataclass(frozen=True, slots=True)
class AiManagerStreamContext:
    config: AiManagerConfig
    manager_input: AiManagerInput
    local_context: LocalAgentRuntimeContext
    local_runner: LocalAgentRunner
    encoder: EnvelopeEncoder
    stream_reasoning: bool = True
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class StaticAiManagerClient:
    """Deterministic manager used until the OpenAI Agents SDK runner is wired.

    It exercises the same data boundary and SSE contract as the future SDK
    adapter, but never calls an external model.
    """

    def create_plan(self, manager_input: AiManagerInput) -> ManagerPlan:
        if manager_input.prompt.status == "blocked":
            return ManagerPlan(
                objective="Clarify the request before external planning.",
                needs_user_decision=True,
                clarification_question=(
                    "The request cannot be sent to the AI manager safely. "
                    "Please remove sensitive identifiers or narrow the task."
                ),
            )

        agent_id = _select_agent_id(manager_input.available_agent_ids)
        if agent_id is None:
            return ManagerPlan(
                objective="Clarify the request before internal agent execution.",
                needs_user_decision=True,
                clarification_question=(
                    "No internal agent is available for this workspace scope."
                ),
            )

        return ManagerPlan(
            objective="Use internal agent evidence before drafting the answer.",
            tasks=[
                LocalAgentTask(
                    agent_id=agent_id,
                    objective="Collect a concise redacted evidence summary.",
                    allowed_tool_names=[],
                    context_boundary="workspace_current",
                    expected_output="LocalAgentResult with redacted summary and gaps.",
                )
            ],
        )

    def review_results(
        self,
        *,
        manager_input: AiManagerInput,
        plan: ManagerPlan,
        local_results: list[LocalAgentResult],
        loop_index: int,
    ) -> ManagerReview:
        del manager_input, plan, loop_index
        completed = [result for result in local_results if result.status == "completed"]
        if completed:
            summaries = "\n".join(result.redacted_summary for result in completed)
            return ManagerReview(
                decision="final",
                result_summary=(
                    "AI manager reviewed the internal agent result.\n\n"
                    f"{summaries}"
                ),
            )

        approval_blocked = [
            result
            for result in local_results
            if result.status == "blocked" and result.blocked_reason == "approval_required"
        ]
        if approval_blocked:
            return ManagerReview(
                decision="ask_user",
                user_question=(
                    "An internal agent task needs approval before continuing."
                ),
            )

        return ManagerReview(
            decision="partial",
            result_summary="No completed internal agent result is available yet.",
            gap_summary=_summarize_result_gaps(local_results),
        )


def build_ai_manager_input(
    *,
    raw_prompt: str,
    available_agent_ids: Iterable[str],
    available_tool_names: Iterable[str],
    workspace_metadata: dict[str, str] | None = None,
    prior_redacted_summaries: Iterable[str] = (),
) -> AiManagerInput:
    return AiManagerInput(
        prompt=build_manager_prompt_payload(raw_prompt),
        available_agent_ids=list(available_agent_ids),
        available_tool_names=list(available_tool_names),
        workspace_metadata=workspace_metadata or {},
        prior_redacted_summaries=list(prior_redacted_summaries),
    )


async def run_ai_manager_stream(
    *,
    context: AiManagerStreamContext,
    manager_client: AiManagerClient | None = None,
) -> AsyncIterator[AgentEventEnvelope]:
    client = manager_client or StaticAiManagerClient()
    plan = client.create_plan(context.manager_input)

    if context.stream_reasoning:
        yield _reasoning_event(
            context.encoder,
            _plan_reasoning_text(plan, context.manager_input),
        )

    if plan.needs_user_decision:
        yield _content_event(
            context.encoder,
            plan.clarification_question or "The manager needs user input.",
        )
        yield _done_event(context, decision="ask_user", loops_used=0)
        return

    current_plan = plan
    local_results: list[LocalAgentResult] = []

    for loop_index in range(1, context.config.max_loops + 1):
        loop_results: list[LocalAgentResult] = []
        for task_index, task in enumerate(current_plan.tasks):
            task_events, result = _run_task_events(
                context=context,
                task=task,
                loop_index=loop_index,
                task_index=task_index,
            )
            for event in task_events:
                yield event
            loop_results.append(result)

        local_results.extend(loop_results)
        review = client.review_results(
            manager_input=context.manager_input,
            plan=current_plan,
            local_results=list(local_results),
            loop_index=loop_index,
        )

        if context.stream_reasoning:
            yield _reasoning_event(context.encoder, _review_reasoning_text(review))

        if review.decision == "final":
            yield _content_event(context.encoder, review.result_summary)
            yield _done_event(context, decision="final", loops_used=loop_index)
            return

        if review.decision == "ask_user":
            yield _content_event(
                context.encoder,
                review.user_question or "The manager needs user input.",
            )
            yield _done_event(context, decision="ask_user", loops_used=loop_index)
            return

        if review.decision == "partial":
            yield _content_event(
                context.encoder,
                _partial_answer_text(
                    result_summary=review.result_summary,
                    gap_summary=review.gap_summary,
                ),
            )
            yield _done_event(context, decision="partial", loops_used=loop_index)
            return

        if review.decision == "failed":
            yield make_envelope(
                "error",
                context.encoder.next_seq(),
                {
                    "code": "ai_manager_failed",
                    "message": review.gap_summary or "AI manager failed.",
                    "retryable": False,
                },
            )
            yield _done_event(context, decision="failed", loops_used=loop_index)
            return

        if not review.next_tasks:
            yield _content_event(
                context.encoder,
                _partial_answer_text(
                    result_summary=review.result_summary,
                    gap_summary=review.gap_summary
                    or "The manager requested a retry without a next task.",
                ),
            )
            yield _done_event(context, decision="partial", loops_used=loop_index)
            return

        current_plan = ManagerPlan(
            objective=current_plan.objective,
            tasks=review.next_tasks,
        )

    yield _content_event(
        context.encoder,
        _partial_answer_text(
            result_summary="The manager reached the configured review loop limit.",
            gap_summary=_summarize_result_gaps(local_results),
        ),
    )
    yield _done_event(
        context,
        decision="partial",
        loops_used=context.config.max_loops,
    )


def _run_task_events(
    *,
    context: AiManagerStreamContext,
    task: LocalAgentTask,
    loop_index: int,
    task_index: int,
) -> tuple[list[AgentEventEnvelope], LocalAgentResult]:
    call_id = f"internal-agent-{loop_index}-{task_index}"
    arguments_json = _task_arguments_json(task)
    events = [
        make_envelope(
            "tool_call_started",
            context.encoder.next_seq(),
            {
                "call_id": call_id,
                "name": RUN_LOCAL_SPECIALIST_TOOL_NAME,
                "args_preview": _preview_text(arguments_json, limit=240),
            },
        ),
        make_envelope(
            "tool_call_args_delta",
            context.encoder.next_seq(),
            {
                "call_id": call_id,
                "delta": arguments_json,
            },
        ),
    ]
    result = run_local_agent_task(
        task=task,
        context=context.local_context,
        runner=context.local_runner,
    )
    events.append(
        make_envelope(
            "tool_result",
            context.encoder.next_seq(),
            {
                "call_id": call_id,
                "status": _tool_status_for_result(result),
                "result_preview": _result_preview(result)
                if result.status == "completed"
                else None,
                "error": result.blocked_reason if result.status != "completed" else None,
            },
        )
    )
    return events, result


def _reasoning_event(encoder: EnvelopeEncoder, text: str) -> AgentEventEnvelope:
    return make_envelope(
        "reasoning_delta",
        encoder.next_seq(),
        {"text": text},
    )


def _content_event(encoder: EnvelopeEncoder, text: str) -> AgentEventEnvelope:
    return make_envelope(
        "content_delta",
        encoder.next_seq(),
        {"text": text},
    )


def _done_event(
    context: AiManagerStreamContext,
    *,
    decision: str,
    loops_used: int,
) -> AgentEventEnvelope:
    return make_envelope(
        "done",
        context.encoder.next_seq(),
        {
            "finish_reason": "error" if decision == "failed" else "stop",
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
                    "ai_manager_mvp",
                    f"loops_used:{loops_used}",
                ],
                "external_egress_summary": {
                    "manager": "ai_manager",
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


def _plan_reasoning_text(
    plan: ManagerPlan,
    manager_input: AiManagerInput,
) -> str:
    prompt_status = manager_input.prompt.status
    if plan.needs_user_decision:
        return f"ai_manager: user decision required; prompt_status={prompt_status}"
    return (
        "ai_manager: planned internal agent work; "
        f"tasks={len(plan.tasks)}; prompt_status={prompt_status}"
    )


def _review_reasoning_text(review: ManagerReview) -> str:
    return f"ai_manager: review decision={review.decision}"


def _select_agent_id(agent_ids: list[str]) -> str | None:
    preferred_order = (
        "domain.docs",
        "domain.rag",
        "domain.meeting",
        "domain.pms",
        "domain.planner",
        "writer.template",
    )
    available = set(agent_ids)
    for agent_id in preferred_order:
        if agent_id in available:
            return agent_id
    return agent_ids[0] if agent_ids else None


def _task_arguments_json(task: LocalAgentTask) -> str:
    return json.dumps(task.model_dump(), ensure_ascii=False, sort_keys=True)


def _result_preview(result: LocalAgentResult) -> str:
    return _preview_text(
        json.dumps(result.model_dump(exclude_none=True), ensure_ascii=False, sort_keys=True),
        limit=1200,
    )


def _tool_status_for_result(result: LocalAgentResult) -> str:
    if result.status == "completed":
        return "ok"
    if result.status == "blocked":
        return "rejected"
    return "error"


def _partial_answer_text(*, result_summary: str, gap_summary: str) -> str:
    parts = [part for part in [result_summary.strip(), gap_summary.strip()] if part]
    if not parts:
        return "Partial answer: the manager could not complete the request."
    return "Partial answer:\n\n" + "\n\nGap: ".join(parts)


def _summarize_result_gaps(results: list[LocalAgentResult]) -> str:
    if not results:
        return "No internal agent task completed."
    reasons = [
        result.blocked_reason or result.status
        for result in results
        if result.status != "completed"
    ]
    if not reasons:
        return ""
    return "Internal agent gaps: " + ", ".join(sorted(set(reasons)))


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
