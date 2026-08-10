from __future__ import annotations

from collections import Counter

from open_work_hub_api.domains.ai.runtime.contracts import AgentInvocationSpec, ExecutionGraph


class GraphInvocationDependencyError(ValueError):
    pass


def validate_invocation_dependencies(graph: ExecutionGraph) -> None:
    plan_invocation_dependencies(graph, validate_references=True)


def plan_invocation_dependencies(
    graph: ExecutionGraph,
    *,
    validate_references: bool,
) -> list[AgentInvocationSpec]:
    duplicate_agent_ids = sorted(
        agent_id
        for agent_id, count in Counter(
            invocation.agent_id for invocation in graph.invocations
        ).items()
        if count > 1
    )
    if duplicate_agent_ids:
        raise GraphInvocationDependencyError(
            f"duplicate invocation agent id(s): {duplicate_agent_ids}"
        )

    indexed_invocations = {
        invocation.agent_id: (index, invocation)
        for index, invocation in enumerate(graph.invocations)
    }
    if validate_references:
        invocation_ids = set(indexed_invocations)
        for invocation in graph.invocations:
            if invocation.agent_id in invocation.must_run_after:
                raise GraphInvocationDependencyError(
                    f"{invocation.agent_id} depends on itself"
                )
            missing_dependencies = sorted(set(invocation.must_run_after) - invocation_ids)
            if missing_dependencies:
                raise GraphInvocationDependencyError(
                    f"{invocation.agent_id} depends on unknown invocation(s): "
                    f"{missing_dependencies}"
                )

    planned_agent_ids: set[str] = set()
    remaining_agent_ids = set(indexed_invocations)
    planned_invocations: list[AgentInvocationSpec] = []

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
            raise GraphInvocationDependencyError(
                f"cyclic invocation dependency: {sorted(remaining_agent_ids)}"
            )

        for agent_id in ready_agent_ids:
            _index, invocation = indexed_invocations[agent_id]
            planned_invocations.append(invocation)
            planned_agent_ids.add(agent_id)
            remaining_agent_ids.remove(agent_id)

    return planned_invocations


__all__ = [
    "GraphInvocationDependencyError",
    "plan_invocation_dependencies",
    "validate_invocation_dependencies",
]
