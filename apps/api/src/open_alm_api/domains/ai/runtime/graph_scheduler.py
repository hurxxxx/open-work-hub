from __future__ import annotations

from open_alm_api.domains.ai.runtime.contracts import (
    ExecutionGraph,
    GraphExecutionSchedule,
    GraphScheduleStep,
)
from open_alm_api.domains.ai.runtime.graph_invocation_dependencies import (
    GraphInvocationDependencyError,
    plan_invocation_dependencies,
)
from open_alm_api.domains.ai.runtime.graph_schedule_summary import (
    project_graph_execution_schedule,
    project_graph_schedule_failure,
)


class GraphSchedulerError(ValueError):
    pass


def build_graph_execution_schedule(graph: ExecutionGraph) -> GraphExecutionSchedule:
    try:
        planned_invocations = plan_invocation_dependencies(
            graph,
            validate_references=False,
        )
    except GraphInvocationDependencyError as exc:
        raise GraphSchedulerError(str(exc)) from exc

    return GraphExecutionSchedule(
        steps=[
            GraphScheduleStep(
                invocation_seq=invocation_seq,
                agent_id=invocation.agent_id,
                depends_on_agent_ids=list(invocation.must_run_after),
            )
            for invocation_seq, invocation in enumerate(planned_invocations)
        ]
    )


def summarize_graph_execution_schedule(schedule: GraphExecutionSchedule) -> dict[str, object]:
    return project_graph_execution_schedule(schedule)


def summarize_graph_schedule_failure(error: GraphSchedulerError) -> dict[str, object]:
    return project_graph_schedule_failure(error)


__all__ = [
    "GraphSchedulerError",
    "build_graph_execution_schedule",
    "summarize_graph_execution_schedule",
    "summarize_graph_schedule_failure",
]
