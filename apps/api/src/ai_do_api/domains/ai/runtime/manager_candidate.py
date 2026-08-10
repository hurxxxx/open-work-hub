from __future__ import annotations

from typing import Any

from ai_do_api.domains.ai.runtime.agent_definitions import (
    AgentDefinition,
    ResolvedAgentDefinitions,
)
from ai_do_api.domains.ai.runtime.contracts import (
    AgentInvocationSpec,
    ExecutionGraph,
    RuntimeProfile,
)
from ai_do_api.domains.ai.runtime.manager_candidate_profiles import (
    DETERMINISTIC_MANAGER_CANDIDATE_PROFILES,
    DETERMINISTIC_MANAGER_CANDIDATE_RUNTIME_PROFILES,
    DeterministicManagerCandidateProfile,
    GroundedEvidencePolicy,
    TerminalAgentPolicy,
)


def supports_deterministic_manager_candidate(runtime_profile: RuntimeProfile) -> bool:
    return runtime_profile in DETERMINISTIC_MANAGER_CANDIDATE_RUNTIME_PROFILES


def build_deterministic_manager_candidate(
    *,
    runtime_profile: RuntimeProfile,
    resolved_agents: ResolvedAgentDefinitions,
) -> ExecutionGraph | None:
    definitions = {definition.agent_id: definition for definition in resolved_agents.definitions}
    profile = DETERMINISTIC_MANAGER_CANDIDATE_PROFILES.get(runtime_profile)
    if profile is None:
        return None
    return _build_profile_graph(profile, definitions)


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


def _build_profile_graph(
    profile: DeterministicManagerCandidateProfile,
    definitions: dict[str, AgentDefinition],
) -> ExecutionGraph | None:
    domain_agent_ids = _available_agent_ids(
        definitions,
        profile.domain_agent_ids,
    )
    if profile.requires_domain_agent and not domain_agent_ids:
        return None

    invocations: list[AgentInvocationSpec] = []
    for agent_id in domain_agent_ids:
        invocations.append(
            _invocation(
                agent_id=agent_id,
                purpose=profile.domain_purpose_template.format(agent_id=agent_id),
            )
        )

    if profile.grounded_evidence is not None:
        _append_grounded_evidence_invocations(
            profile.grounded_evidence,
            definitions,
            invocations,
            domain_agent_ids,
        )

    if profile.terminal_agent.agent_id not in definitions or not invocations:
        return None

    invocation_agent_ids = _invocation_agent_id_set(invocations)
    verifier_agent_id = (
        profile.grounded_evidence.verifier_agent_id
        if profile.grounded_evidence is not None
        else None
    )
    has_verifier = verifier_agent_id in invocation_agent_ids if verifier_agent_id else False
    invocations.append(
        _invocation(
            agent_id=profile.terminal_agent.agent_id,
            must_run_after=_terminal_dependencies(
                profile.terminal_agent,
                invocations,
                domain_agent_ids,
                verifier_agent_id,
            ),
            purpose=profile.terminal_agent.purpose,
        )
    )
    return ExecutionGraph(
        intent=profile.intent,
        domains=_graph_domains(invocations, definitions),
        risk=profile.risk,
        output_kind=profile.output_kind,
        invocations=invocations,
        requires_verifier=has_verifier,
        requires_approval_preview=profile.requires_approval_preview,
    )


def _append_grounded_evidence_invocations(
    policy: GroundedEvidencePolicy,
    definitions: dict[str, AgentDefinition],
    invocations: list[AgentInvocationSpec],
    domain_agent_ids: list[str],
) -> None:
    if policy.planner_agent_id in definitions:
        invocations.append(
            _invocation(
                agent_id=policy.planner_agent_id,
                must_run_after=domain_agent_ids,
                purpose=policy.planner_purpose,
            )
        )
    if policy.executor_agent_id in definitions:
        search_dependencies = (
            [policy.planner_agent_id]
            if _has_invocation(invocations, policy.planner_agent_id)
            else domain_agent_ids
        )
        invocations.append(
            _invocation(
                agent_id=policy.executor_agent_id,
                must_run_after=search_dependencies,
                purpose=policy.executor_purpose,
            )
        )

    evidence_agent_ids = [
        invocation.agent_id
        for invocation in invocations
        if invocation.agent_id in domain_agent_ids
        or invocation.agent_id == policy.executor_agent_id
    ]
    if policy.verifier_agent_id in definitions and evidence_agent_ids:
        invocations.append(
            _invocation(
                agent_id=policy.verifier_agent_id,
                must_run_after=evidence_agent_ids,
                purpose=policy.verifier_purpose,
            )
        )


def _terminal_dependencies(
    policy: TerminalAgentPolicy,
    invocations: list[AgentInvocationSpec],
    domain_agent_ids: list[str],
    verifier_agent_id: str | None,
) -> list[str]:
    if policy.dependency_policy == "domain_agents":
        return list(domain_agent_ids)
    if (
        policy.dependency_policy == "verifier_or_all_prior"
        and verifier_agent_id is not None
        and _has_invocation(invocations, verifier_agent_id)
    ):
        return [verifier_agent_id]
    return [invocation.agent_id for invocation in invocations]


def _has_invocation(invocations: list[AgentInvocationSpec], agent_id: str) -> bool:
    return any(invocation.agent_id == agent_id for invocation in invocations)


def _available_agent_ids(
    definitions: dict[str, AgentDefinition],
    agent_ids: tuple[str, ...],
) -> list[str]:
    return [agent_id for agent_id in agent_ids if agent_id in definitions]


def _invocation(
    *,
    agent_id: str,
    purpose: str,
    must_run_after: list[str] | None = None,
) -> AgentInvocationSpec:
    return AgentInvocationSpec(
        agent_id=agent_id,
        must_run_after=list(must_run_after) if must_run_after is not None else [],
        purpose=purpose,
    )


def _invocation_agent_id_set(invocations: list[AgentInvocationSpec]) -> set[str]:
    return {invocation.agent_id for invocation in invocations}


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
