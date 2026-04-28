from __future__ import annotations

from typing import Any

from aidoo_api.domains.ai.runtime.agent_definitions import (
    AgentDefinition,
    ResolvedAgentDefinitions,
)
from aidoo_api.domains.ai.runtime.contracts import (
    AgentInvocationSpec,
    ExecutionGraph,
    RuntimeProfile,
)


def build_deterministic_manager_candidate(
    *,
    runtime_profile: RuntimeProfile,
    resolved_agents: ResolvedAgentDefinitions,
) -> ExecutionGraph | None:
    definitions = {definition.agent_id: definition for definition in resolved_agents.definitions}
    if runtime_profile == "grounded_report":
        return _grounded_report_graph(definitions)
    if runtime_profile == "high_risk_action":
        return _high_risk_action_graph(definitions)
    return None


def summarize_execution_graph(graph: ExecutionGraph) -> dict[str, Any]:
    return {
        "intent": graph.intent,
        "domains": list(graph.domains),
        "risk": graph.risk,
        "output_kind": graph.output_kind,
        "invocation_agent_ids": [invocation.agent_id for invocation in graph.invocations],
        "requires_verifier": graph.requires_verifier,
        "requires_approval_preview": graph.requires_approval_preview,
    }


def _grounded_report_graph(definitions: dict[str, AgentDefinition]) -> ExecutionGraph | None:
    invocations: list[AgentInvocationSpec] = []
    domain_agent_ids = [
        agent_id
        for agent_id in ("domain.pms", "domain.meeting", "domain.docs", "domain.planner", "domain.rag")
        if agent_id in definitions
    ]
    for agent_id in domain_agent_ids:
        invocations.append(
            AgentInvocationSpec(
                agent_id=agent_id,
                purpose=f"Collect evidence with {agent_id}.",
            )
        )

    if "search.planner" in definitions:
        invocations.append(
            AgentInvocationSpec(
                agent_id="search.planner",
                must_run_after=domain_agent_ids,
                purpose="Build the evidence search plan.",
            )
        )
    if "search.executor" in definitions:
        search_dependencies = ["search.planner"] if "search.planner" in definitions else domain_agent_ids
        invocations.append(
            AgentInvocationSpec(
                agent_id="search.executor",
                must_run_after=search_dependencies,
                purpose="Execute scoped evidence search.",
            )
        )

    evidence_agent_ids = [
        invocation.agent_id
        for invocation in invocations
        if invocation.agent_id.startswith("domain.") or invocation.agent_id == "search.executor"
    ]
    if "verifier.grounding" in definitions and evidence_agent_ids:
        invocations.append(
            AgentInvocationSpec(
                agent_id="verifier.grounding",
                must_run_after=evidence_agent_ids,
                purpose="Verify evidence coverage and unsupported claims.",
            )
        )
    if "writer.template" not in definitions or not invocations:
        return None

    writer_dependencies = (
        ["verifier.grounding"]
        if "verifier.grounding" in {invocation.agent_id for invocation in invocations}
        else [invocation.agent_id for invocation in invocations]
    )
    invocations.append(
        AgentInvocationSpec(
            agent_id="writer.template",
            must_run_after=writer_dependencies,
            purpose="Write the grounded report artifact.",
        )
    )
    return ExecutionGraph(
        intent="report",
        domains=_graph_domains(invocations, definitions),
        risk="medium",
        output_kind="artifact",
        invocations=invocations,
        requires_verifier="verifier.grounding" in {invocation.agent_id for invocation in invocations},
    )


def _high_risk_action_graph(definitions: dict[str, AgentDefinition]) -> ExecutionGraph | None:
    domain_agent_ids = [
        agent_id
        for agent_id in ("domain.pms", "domain.meeting", "domain.docs", "domain.planner")
        if agent_id in definitions
    ]
    if "approval.proposal_preview" not in definitions or not domain_agent_ids:
        return None

    invocations = [
        AgentInvocationSpec(
            agent_id=agent_id,
            purpose=f"Collect write-context evidence with {agent_id}.",
        )
        for agent_id in domain_agent_ids
    ]
    invocations.append(
        AgentInvocationSpec(
            agent_id="approval.proposal_preview",
            must_run_after=domain_agent_ids,
            purpose="Build a user-reviewable write proposal preview.",
        )
    )
    return ExecutionGraph(
        intent="write",
        domains=_graph_domains(invocations, definitions),
        risk="high",
        output_kind="approval_preview",
        invocations=invocations,
        requires_approval_preview=True,
    )


def _graph_domains(
    invocations: list[AgentInvocationSpec],
    definitions: dict[str, AgentDefinition],
) -> list[str]:
    domains: set[str] = set()
    for invocation in invocations:
        definition = definitions.get(invocation.agent_id)
        if definition is None:
            continue
        domains.update(definition.domains)
    return sorted(domains)
