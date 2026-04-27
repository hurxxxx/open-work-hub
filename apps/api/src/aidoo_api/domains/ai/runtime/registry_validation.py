from __future__ import annotations

from dataclasses import dataclass

from aidoo_api.domains.ai.runtime.contracts import ExecutionGraph


class RuntimeRegistryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeRegistry:
    agent_ids: frozenset[str]
    intents: frozenset[str]
    domains: frozenset[str]
    output_kinds: frozenset[str]


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

    if any(invocation.agent_id == "external.search" for invocation in graph.invocations):
        raise RuntimeRegistryValidationError(
            "external.search cannot be a direct invocation target"
        )

    invocation_ids = {invocation.agent_id for invocation in graph.invocations}
    for invocation in graph.invocations:
        missing_dependencies = sorted(set(invocation.must_run_after) - invocation_ids)
        if missing_dependencies:
            raise RuntimeRegistryValidationError(
                f"{invocation.agent_id} depends on unknown invocation(s): "
                f"{missing_dependencies}"
            )

    return graph
