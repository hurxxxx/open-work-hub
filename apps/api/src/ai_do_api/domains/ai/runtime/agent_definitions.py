from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ai_do_api.domains.ai.runtime.registry_validation import RuntimeRegistry
from ai_do_api.domains.auth.workspace_apps import WORKSPACE_APP_IDS


RUNTIME_INTENTS = frozenset({"read", "report", "draft", "write"})
RUNTIME_OUTPUT_KINDS = frozenset({"answer", "artifact", "approval_preview"})
KNOWN_WORKSPACE_APP_IDS = frozenset(WORKSPACE_APP_IDS)


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    purpose: str
    workspace_app_ids: frozenset[str] = frozenset()
    domains: frozenset[str] = frozenset()
    output_kinds: frozenset[str] = RUNTIME_OUTPUT_KINDS
    intents: frozenset[str] = RUNTIME_INTENTS
    write_capable: bool = False
    requires_non_empty_scope: bool = False


@dataclass(frozen=True)
class ResolvedAgentDefinitions:
    definitions: tuple[AgentDefinition, ...]
    runtime_registry: RuntimeRegistry
    write_agent_ids: frozenset[str]

    @property
    def agent_ids(self) -> frozenset[str]:
        return self.runtime_registry.agent_ids


class AgentDefinitionResolver:
    def __init__(
        self,
        definitions: Iterable[AgentDefinition] | None = None,
    ) -> None:
        definitions_tuple = tuple(definitions) if definitions is not None else DEFAULT_AGENT_DEFINITIONS
        self._definitions = MappingProxyType(
            {definition.agent_id: definition for definition in definitions_tuple}
        )

    def resolve(
        self,
        *,
        enabled_app_ids: Iterable[str],
        allowed_app_ids: Iterable[str] | None = None,
    ) -> ResolvedAgentDefinitions:
        enabled_scope = _normalize_app_scope(enabled_app_ids)
        if "ai" not in enabled_scope:
            return _empty_resolution()

        effective_scope = enabled_scope
        if allowed_app_ids is not None:
            effective_scope = enabled_scope & _normalize_app_scope(allowed_app_ids)

        visible_definitions = tuple(
            definition
            for definition in self._definitions.values()
            if _is_definition_visible(
                definition,
                enabled_scope=enabled_scope,
                effective_scope=effective_scope,
            )
        )
        return _build_resolution(visible_definitions)

    def by_id(self) -> Mapping[str, AgentDefinition]:
        return self._definitions


DEFAULT_AGENT_DEFINITIONS = (
    AgentDefinition(
        agent_id="manager.orchestrator",
        purpose="Decompose graph-path requests and select the execution graph.",
    ),
    AgentDefinition(
        agent_id="domain.pms",
        purpose="Read PMS issue, list, status, and issue-draft context.",
        workspace_app_ids=frozenset({"pms"}),
        domains=frozenset({"pms"}),
    ),
    AgentDefinition(
        agent_id="domain.meeting",
        purpose="Read meeting transcript, insight, action, and decision context.",
        workspace_app_ids=frozenset({"meeting"}),
        domains=frozenset({"meeting"}),
    ),
    AgentDefinition(
        agent_id="domain.docs",
        purpose="Read document hub and page context.",
        workspace_app_ids=frozenset({"docs"}),
        domains=frozenset({"docs"}),
    ),
    AgentDefinition(
        agent_id="domain.planner",
        purpose="Read calendar and availability context.",
        workspace_app_ids=frozenset({"planner"}),
        domains=frozenset({"planner"}),
    ),
    AgentDefinition(
        agent_id="domain.rag",
        purpose="Read cross-domain grounded-search context.",
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
    ),
    AgentDefinition(
        agent_id="search.planner",
        purpose="Build deterministic search plans for evidence collection.",
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
    ),
    AgentDefinition(
        agent_id="search.executor",
        purpose="Execute internal search and domain-service adapters.",
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
    ),
    AgentDefinition(
        agent_id="verifier.grounding",
        purpose="Check evidence coverage, unsupported claims, and policy risk.",
        domains=frozenset({"rag"}),
        requires_non_empty_scope=True,
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


def resolve_agent_definitions(
    *,
    enabled_app_ids: Iterable[str],
    allowed_app_ids: Iterable[str] | None = None,
) -> ResolvedAgentDefinitions:
    return AgentDefinitionResolver().resolve(
        enabled_app_ids=enabled_app_ids,
        allowed_app_ids=allowed_app_ids,
    )


def _normalize_app_scope(values: Iterable[str]) -> frozenset[str]:
    return frozenset(str(value) for value in values if str(value) in KNOWN_WORKSPACE_APP_IDS)


def _is_definition_visible(
    definition: AgentDefinition,
    *,
    enabled_scope: frozenset[str],
    effective_scope: frozenset[str],
) -> bool:
    if definition.requires_non_empty_scope and not effective_scope:
        return False
    if not definition.workspace_app_ids:
        return True
    return (
        definition.workspace_app_ids <= enabled_scope
        and definition.workspace_app_ids <= effective_scope
    )


def _build_resolution(definitions: tuple[AgentDefinition, ...]) -> ResolvedAgentDefinitions:
    return ResolvedAgentDefinitions(
        definitions=definitions,
        runtime_registry=RuntimeRegistry(
            agent_ids=frozenset(definition.agent_id for definition in definitions),
            intents=frozenset().union(*(definition.intents for definition in definitions)),
            domains=frozenset().union(*(definition.domains for definition in definitions)),
            output_kinds=frozenset().union(*(definition.output_kinds for definition in definitions)),
        ),
        write_agent_ids=frozenset(
            definition.agent_id for definition in definitions if definition.write_capable
        ),
    )


def _empty_resolution() -> ResolvedAgentDefinitions:
    return _build_resolution(())
