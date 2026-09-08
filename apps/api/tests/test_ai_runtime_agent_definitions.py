from __future__ import annotations

from open_work_hub_api.domains.ai.runtime.agent_definitions import (
    AgentDefinition,
    AgentDefinitionResolver,
    resolve_agent_definitions,
)


def test_plugin_app_entitlements_can_resolve_registered_agent_definitions() -> None:
    resolver = AgentDefinitionResolver(
        definitions=[
            AgentDefinition(agent_id="writer.global", purpose="Visible global writer."),
            AgentDefinition(
                agent_id="domain.plugin",
                purpose="Visible plugin-app domain.",
                owner_app_ids=frozenset({"plugin.app"}),
                domains=frozenset({"plugin"}),
            ),
            AgentDefinition(
                agent_id="domain.pms",
                purpose="Visible known-app domain.",
                owner_app_ids=frozenset({"pms"}),
                domains=frozenset({"pms"}),
            ),
        ]
    )

    resolved = resolver.resolve(
        enabled_app_ids=["chatbot", "pms", "plugin.app"],
        allowed_app_ids=["pms", "plugin.app"],
    )

    assert "writer.global" in resolved.agent_ids
    assert "domain.pms" in resolved.agent_ids
    assert "domain.plugin" in resolved.agent_ids
    assert "plugin" in resolved.runtime_registry.domains


def test_missing_ai_entitlement_returns_empty_registry() -> None:
    resolved = resolve_agent_definitions(enabled_app_ids=["pms", "docs"])

    assert resolved.definitions == ()
    assert resolved.agent_ids == frozenset()
    assert resolved.runtime_registry.domains == frozenset()
    assert resolved.write_agent_ids == frozenset()


def test_allowed_scope_cannot_widen_enabled_entitlements() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["chatbot", "meeting"],
        allowed_app_ids=["meeting", "pms"],
    )

    assert "domain.meeting" in resolved.agent_ids
    assert "domain.pms" not in resolved.agent_ids
    assert "pms" not in resolved.runtime_registry.domains


def test_empty_allowed_scope_hides_domain_and_rag_agents_but_keeps_global_agents() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["chatbot", "meeting", "docs", "pms"],
        allowed_app_ids=[],
    )

    assert "manager.orchestrator" in resolved.agent_ids
    assert "writer.template" in resolved.agent_ids
    assert "approval.proposal_preview" in resolved.agent_ids
    assert "domain.meeting" not in resolved.agent_ids
    assert "domain.docs" not in resolved.agent_ids
    assert "domain.pms" not in resolved.agent_ids
    assert "domain.rag" not in resolved.agent_ids
    assert "search.planner" not in resolved.agent_ids
    assert "search.executor" not in resolved.agent_ids
    assert "verifier.grounding" not in resolved.agent_ids
    assert resolved.runtime_registry.domains == frozenset()


def test_business_chat_scope_hides_ai_rag_agents() -> None:
    resolved = resolve_agent_definitions(
        enabled_app_ids=["chatbot", "docs", "pms", "meeting", "planner"],
        allowed_app_ids=["pms", "docs"],
    )

    assert "domain.pms" in resolved.agent_ids
    assert "domain.docs" in resolved.agent_ids
    assert "domain.meeting" not in resolved.agent_ids
    assert "domain.planner" not in resolved.agent_ids
    assert "domain.rag" not in resolved.agent_ids
    assert "search.planner" not in resolved.agent_ids
    assert "search.executor" not in resolved.agent_ids
    assert "verifier.grounding" not in resolved.agent_ids
    assert "external.search" not in resolved.agent_ids
    assert "rag" not in resolved.runtime_registry.domains


def test_write_agent_ids_derive_only_from_visible_definitions() -> None:
    resolver = AgentDefinitionResolver(
        definitions=[
            AgentDefinition(
                agent_id="writer.global",
                purpose="Visible global writer.",
                write_capable=True,
            ),
            AgentDefinition(
                agent_id="writer.pms",
                purpose="Visible scoped writer.",
                owner_app_ids=frozenset({"pms"}),
                domains=frozenset({"pms"}),
                write_capable=True,
            ),
            AgentDefinition(
                agent_id="writer.docs",
                purpose="Hidden scoped writer.",
                owner_app_ids=frozenset({"docs"}),
                domains=frozenset({"docs"}),
                write_capable=True,
            ),
        ]
    )

    resolved = resolver.resolve(
        enabled_app_ids=["chatbot", "pms", "docs"],
        allowed_app_ids=["pms"],
    )

    assert resolved.agent_ids == frozenset({"writer.global", "writer.pms"})
    assert resolved.write_agent_ids == frozenset({"writer.global", "writer.pms"})
