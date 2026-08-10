from __future__ import annotations

from dataclasses import dataclass

from open_alm_api.domains.ai.runtime.contracts import ExecutionGraph
from open_alm_api.domains.ai.runtime.graph_invocation_dependencies import (
    GraphInvocationDependencyError,
    validate_invocation_dependencies,
)


class RuntimeRegistryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeRegistry:
    agent_ids: frozenset[str]
    intents: frozenset[str]
    domains: frozenset[str]
    output_kinds: frozenset[str]
    blocked_direct_invocation_agent_ids: frozenset[str] = frozenset()


def validate_execution_graph(
    graph: ExecutionGraph,
    *,
    registry: RuntimeRegistry,
) -> ExecutionGraph:
    if graph.intent not in registry.intents:
        raise RuntimeRegistryValidationError(f"unknown intent: {graph.intent}")
    if graph.output_kind not in registry.output_kinds:
        raise RuntimeRegistryValidationError(f"unknown output kind: {graph.output_kind}")

    unknown_domains = sorted(set(graph.domains) - set(registry.domains))
    if unknown_domains:
        raise RuntimeRegistryValidationError(f"unknown domain(s): {unknown_domains}")

    unknown_agents = sorted(
        {invocation.agent_id for invocation in graph.invocations} - set(registry.agent_ids)
    )
    if unknown_agents:
        raise RuntimeRegistryValidationError(f"unknown agent id(s): {unknown_agents}")

    blocked_direct_invocation_agents = sorted(
        {invocation.agent_id for invocation in graph.invocations}
        & registry.blocked_direct_invocation_agent_ids
    )
    if blocked_direct_invocation_agents:
        if len(blocked_direct_invocation_agents) == 1:
            raise RuntimeRegistryValidationError(
                f"{blocked_direct_invocation_agents[0]} cannot be a direct invocation target"
            )
        raise RuntimeRegistryValidationError(
            "blocked direct invocation agent id(s): "
            f"{blocked_direct_invocation_agents}"
        )

    _validate_invocation_graph_shape(graph)

    return graph


def _validate_invocation_graph_shape(graph: ExecutionGraph) -> None:
    try:
        validate_invocation_dependencies(graph)
    except GraphInvocationDependencyError as exc:
        raise RuntimeRegistryValidationError(str(exc)) from exc
