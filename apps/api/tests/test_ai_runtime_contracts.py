from __future__ import annotations

import pytest

from open_work_hub_api.domains.ai.runtime import (
    AgentDefinitionResolver,
    AgentInvocationSpec,
    ExecutionGraph,
    RuntimeRegistry,
    RuntimeRegistryValidationError,
    resolve_agent_definitions,
    validate_execution_graph,
    validate_manager_graph_candidate,
)


def _registry(*, include_external_search: bool = False) -> RuntimeRegistry:
    agent_ids = {
        "manager.orchestrator",
        "domain.meeting",
        "domain.docs",
        "search.executor",
        "verifier.grounding",
        "writer.template",
    }
    if include_external_search:
        agent_ids.add("external.search")
    return RuntimeRegistry(
        agent_ids=frozenset(agent_ids),
        intents=frozenset({"read", "report"}),
        domains=frozenset({"meeting", "docs", "rag"}),
        output_kinds=frozenset({"answer", "artifact"}),
        blocked_direct_invocation_agent_ids=(
            frozenset({"external.search"}) if include_external_search else frozenset()
        ),
    )


def test_execution_graph_blocks_direct_external_search_invocation() -> None:
    graph = ExecutionGraph(
        intent="read",
        domains=["rag"],
        risk="low",
        output_kind="answer",
        invocations=[
            AgentInvocationSpec(
                agent_id="external.search",
                purpose="search public web",
            )
        ],
    )

    with pytest.raises(RuntimeRegistryValidationError, match="external.search"):
        validate_execution_graph(graph, registry=_registry(include_external_search=True))


def test_manager_graph_validator_enforces_write_agent_risk_floor() -> None:
    result = validate_manager_graph_candidate(
        {
            "intent": "report",
            "domains": ["docs"],
            "risk": "medium",
            "output_kind": "artifact",
            "invocations": [
                {
                    "agent_id": "writer.template",
                    "purpose": "write draft",
                }
            ],
        },
        registry=_registry(),
        write_agent_ids=frozenset({"writer.template"}),
    )

    assert result.accepted is False
    assert result.graph is None
    assert result.fallback_reason == "risk_floor_violation"
    assert "writer.template" in (result.error or "")


def test_agent_definition_resolver_never_widens_beyond_workspace_entitlements() -> None:
    resolved = AgentDefinitionResolver().resolve(
        enabled_app_ids=["chatbot", "meeting"],
        allowed_app_ids=["meeting", "pms"],
    )

    assert "domain.meeting" in resolved.agent_ids
    assert "domain.pms" not in resolved.agent_ids
    assert "pms" not in resolved.runtime_registry.domains


def test_agent_definition_resolver_empty_scope_hides_domain_agents() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["chatbot", "meeting", "docs"],
        allowed_app_ids=[],
    )

    assert "manager.orchestrator" in resolved.agent_ids
    assert "domain.meeting" not in resolved.agent_ids
    assert "domain.docs" not in resolved.agent_ids
    assert "search.executor" not in resolved.agent_ids
    assert resolved.runtime_registry.domains == frozenset()


def test_agent_definition_resolver_requires_ai_app_entitlement() -> None:
    resolved = AgentDefinitionResolver().resolve(
        enabled_app_ids=["meeting", "docs"],
    )

    assert resolved.definitions == ()
    assert resolved.agent_ids == frozenset()
    assert resolved.runtime_registry.domains == frozenset()


def test_manager_validator_uses_resolved_write_agent_risk_floor() -> None:
    resolved = resolve_agent_definitions(enabled_app_ids=["chatbot", "pms"])

    result = validate_manager_graph_candidate(
        {
            "intent": "write",
            "domains": [],
            "risk": "medium",
            "output_kind": "approval_preview",
            "invocations": [
                {
                    "agent_id": "approval.proposal_preview",
                    "purpose": "preview PMS write before approval",
                }
            ],
        },
        registry=resolved.runtime_registry,
        write_agent_ids=resolved.write_agent_ids,
    )

    assert result.accepted is False
    assert result.fallback_reason == "risk_floor_violation"
    assert "approval.proposal_preview" in (result.error or "")
