from __future__ import annotations

from collections import Counter

from ai_do_api.domains.ai.runtime.contracts import (
    ExecutionGraph,
    GraphExecutionSchedule,
    GraphScheduleStep,
)


class GraphSchedulerError(ValueError):
    pass


def build_graph_execution_schedule(graph: ExecutionGraph) -> GraphExecutionSchedule:
    duplicate_agent_ids = sorted(
        agent_id
        for agent_id, count in Counter(
            invocation.agent_id for invocation in graph.invocations
        ).items()
        if count > 1
    )
    if duplicate_agent_ids:
        raise GraphSchedulerError(f"duplicate invocation agent id(s): {duplicate_agent_ids}")

    indexed_invocations = {
        invocation.agent_id: (index, invocation)
        for index, invocation in enumerate(graph.invocations)
    }
    planned_agent_ids: set[str] = set()
    remaining_agent_ids = set(indexed_invocations)
    steps: list[GraphScheduleStep] = []

    while remaining_agent_ids:
        ready_agent_ids = sorted(
            (
                agent_id
                for agent_id in remaining_agent_ids
                if set(indexed_invocations[agent_id][1].must_run_after).issubset(
                    planned_agent_ids
                )
            ),
            key=lambda agent_id: indexed_invocations[agent_id][0],
        )
        if not ready_agent_ids:
            raise GraphSchedulerError(
                f"cyclic invocation dependency: {sorted(remaining_agent_ids)}"
            )

        for agent_id in ready_agent_ids:
            _index, invocation = indexed_invocations[agent_id]
            steps.append(
                GraphScheduleStep(
                    invocation_seq=len(steps),
                    agent_id=invocation.agent_id,
                    depends_on_agent_ids=list(invocation.must_run_after),
                )
            )
            planned_agent_ids.add(agent_id)
            remaining_agent_ids.remove(agent_id)

    return GraphExecutionSchedule(steps=steps)


def summarize_graph_execution_schedule(schedule: GraphExecutionSchedule) -> dict[str, object]:
    return {
        "state": schedule.state,
        "execution_enabled": schedule.execution_enabled,
        "step_count": len(schedule.steps),
        "planned_agent_ids": [step.agent_id for step in schedule.steps],
        "steps": [
            {
                "invocation_seq": step.invocation_seq,
                "agent_id": step.agent_id,
                "state": step.state,
                "depends_on_agent_ids": list(step.depends_on_agent_ids),
            }
            for step in schedule.steps
        ],
    }


def summarize_graph_schedule_failure(error: GraphSchedulerError) -> dict[str, object]:
    return {
        "state": "failed",
        "execution_enabled": False,
        "fallback_reason": "graph_schedule_failed",
        "error_type": type(error).__name__,
        "error": str(error),
        "step_count": 0,
        "planned_agent_ids": [],
        "steps": [],
    }


__all__ = [
    "GraphSchedulerError",
    "build_graph_execution_schedule",
    "summarize_graph_execution_schedule",
    "summarize_graph_schedule_failure",
]
