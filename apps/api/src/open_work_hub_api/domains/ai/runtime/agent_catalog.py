from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

RUNTIME_INTENTS = frozenset({"read", "report", "draft", "write"})
RUNTIME_OUTPUT_KINDS = frozenset({"answer", "artifact", "approval_preview"})


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    purpose: str
    owner_app_ids: frozenset[str] = frozenset()
    graph_tool_names: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()
    output_kinds: frozenset[str] = RUNTIME_OUTPUT_KINDS
    intents: frozenset[str] = RUNTIME_INTENTS
    write_capable: bool = False
    requires_non_empty_scope: bool = False
    direct_invocation_allowed: bool = True


_BUILTIN_AGENT_DEFINITIONS = (
    AgentDefinition(
        agent_id="manager.orchestrator",
        purpose="Decompose graph-path requests and select the execution graph.",
    ),
    AgentDefinition(
        agent_id="domain.pms",
        purpose="Read PMS task, list, status, and task-draft context.",
        owner_app_ids=frozenset({"pms"}),
        domains=frozenset({"pms"}),
    ),
    AgentDefinition(
        agent_id="domain.meeting",
        purpose="Read meeting transcript, insight, action, and decision context.",
        owner_app_ids=frozenset({"meeting"}),
        domains=frozenset({"meeting"}),
    ),
    AgentDefinition(
        agent_id="domain.docs",
        purpose="Read document hub and page context.",
        owner_app_ids=frozenset({"docs"}),
        domains=frozenset({"docs"}),
    ),
    AgentDefinition(
        agent_id="domain.planner",
        purpose="Read calendar and availability context.",
        owner_app_ids=frozenset({"planner"}),
        domains=frozenset({"planner"}),
    ),
    AgentDefinition(
        agent_id="domain.rag",
        purpose="Read cross-domain grounded-search context.",
        owner_app_ids=frozenset({"chatbot"}),
        graph_tool_names=frozenset(
            {"retrieval.search", "retrieval.list_sources", "rag.query", "rag.list_sources"}
        ),
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
    ),
    AgentDefinition(
        agent_id="search.planner",
        purpose="Build deterministic search plans for evidence collection.",
        owner_app_ids=frozenset({"chatbot"}),
        graph_tool_names=frozenset({"retrieval.list_sources", "rag.list_sources"}),
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
    ),
    AgentDefinition(
        agent_id="search.executor",
        purpose="Execute internal search and domain-service adapters.",
        owner_app_ids=frozenset({"chatbot"}),
        graph_tool_names=frozenset(
            {"retrieval.search", "retrieval.list_sources", "rag.query", "rag.list_sources"}
        ),
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
    ),
    AgentDefinition(
        agent_id="verifier.grounding",
        purpose="Check evidence coverage, unsupported claims, and policy risk.",
        owner_app_ids=frozenset({"chatbot"}),
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
    ),
    AgentDefinition(
        agent_id="external.search",
        purpose="Execute external search through the runtime adapter.",
        owner_app_ids=frozenset({"chatbot"}),
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
        direct_invocation_allowed=False,
    ),
    AgentDefinition(
        agent_id="writer.template",
        purpose="Render final answer or artifact output from verified evidence.",
    ),
    AgentDefinition(
        agent_id="approval.proposal_preview",
        purpose="Build user-reviewable previews before write or batch execution.",
        output_kinds=frozenset({"approval_preview"}),
        intents=frozenset({"write"}),
        write_capable=True,
    ),
)


class AgentDefinitionRegistry:
    def __init__(self) -> None:
        self._definitions_by_id: dict[str, AgentDefinition] = {}

    def register(self, definition: AgentDefinition) -> None:
        if definition.agent_id in self._definitions_by_id:
            raise ValueError(f"Agent definition already registered: {definition.agent_id}")
        self._definitions_by_id[definition.agent_id] = definition

    def definitions(self) -> tuple[AgentDefinition, ...]:
        return tuple(self._definitions_by_id.values())

    def by_id(self, agent_id: str) -> AgentDefinition | None:
        return self._definitions_by_id.get(agent_id)


@lru_cache(maxsize=1)
def get_agent_definition_registry() -> AgentDefinitionRegistry:
    registry = AgentDefinitionRegistry()
    for definition in _BUILTIN_AGENT_DEFINITIONS:
        registry.register(definition)
    return registry


def default_agent_definitions() -> tuple[AgentDefinition, ...]:
    return get_agent_definition_registry().definitions()


DEFAULT_AGENT_DEFINITIONS = default_agent_definitions()


__all__ = [
    "DEFAULT_AGENT_DEFINITIONS",
    "AgentDefinition",
    "AgentDefinitionRegistry",
    "RUNTIME_INTENTS",
    "RUNTIME_OUTPUT_KINDS",
    "default_agent_definitions",
    "get_agent_definition_registry",
]
