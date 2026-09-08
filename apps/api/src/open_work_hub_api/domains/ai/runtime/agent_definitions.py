from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from open_work_hub_api.domains.ai.runtime.agent_catalog import (
    DEFAULT_AGENT_DEFINITIONS,
    RUNTIME_INTENTS,
    RUNTIME_OUTPUT_KINDS,
    AgentDefinition,
    default_agent_definitions,
)
from open_work_hub_api.domains.ai.runtime.registry_validation import RuntimeRegistry
from open_work_hub_api.domains.conversations.app_catalog import CHATBOT_APP


@dataclass(frozen=True)
class ResolvedAgentDefinitions:
    definitions: tuple[AgentDefinition, ...]
    runtime_registry: RuntimeRegistry
    write_agent_ids: frozenset[str]

    @property
    def agent_ids(self) -> frozenset[str]:
        return self.runtime_registry.agent_ids


@dataclass(frozen=True)
class _AgentResolutionScope:
    enabled_app_ids: frozenset[str]
    effective_app_ids: frozenset[str]

    @classmethod
    def from_app_ids(
        cls,
        *,
        enabled_app_ids: Iterable[str],
        allowed_app_ids: Iterable[str] | None,
    ) -> _AgentResolutionScope:
        enabled_scope = cls._normalize_app_scope(enabled_app_ids)
        effective_scope = enabled_scope
        if allowed_app_ids is not None:
            effective_scope = enabled_scope & cls._normalize_app_scope(allowed_app_ids)
        return cls(enabled_app_ids=enabled_scope, effective_app_ids=effective_scope)

    @property
    def can_resolve(self) -> bool:
        return CHATBOT_APP.app_id in self.enabled_app_ids

    def is_definition_available(self, definition: AgentDefinition) -> bool:
        if definition.requires_non_empty_scope and not self.effective_app_ids:
            return False
        if not definition.owner_app_ids:
            return True
        return (
            definition.owner_app_ids <= self.enabled_app_ids
            and definition.owner_app_ids <= self.effective_app_ids
        )

    @staticmethod
    def _normalize_app_scope(values: Iterable[str]) -> frozenset[str]:
        return frozenset(str(value) for value in values if str(value).strip())


class AgentDefinitionResolver:
    def __init__(
        self,
        definitions: Iterable[AgentDefinition] | None = None,
    ) -> None:
        definitions_tuple = (
            tuple(definitions) if definitions is not None else default_agent_definitions()
        )
        self._definitions = MappingProxyType(
            {definition.agent_id: definition for definition in definitions_tuple}
        )

    def resolve(
        self,
        *,
        enabled_app_ids: Iterable[str],
        allowed_app_ids: Iterable[str] | None = None,
    ) -> ResolvedAgentDefinitions:
        scope = _AgentResolutionScope.from_app_ids(
            enabled_app_ids=enabled_app_ids,
            allowed_app_ids=allowed_app_ids,
        )
        if not scope.can_resolve:
            return _empty_resolution()

        available_definitions = tuple(
            definition
            for definition in self._definitions.values()
            if scope.is_definition_available(definition)
        )
        return _build_resolution(available_definitions)

    def by_id(self) -> Mapping[str, AgentDefinition]:
        return self._definitions


def resolve_agent_definitions(
    *,
    enabled_app_ids: Iterable[str],
    allowed_app_ids: Iterable[str] | None = None,
) -> ResolvedAgentDefinitions:
    return AgentDefinitionResolver().resolve(
        enabled_app_ids=enabled_app_ids,
        allowed_app_ids=allowed_app_ids,
    )


def _build_resolution(definitions: tuple[AgentDefinition, ...]) -> ResolvedAgentDefinitions:
    return ResolvedAgentDefinitions(
        definitions=definitions,
        runtime_registry=RuntimeRegistry(
            agent_ids=frozenset(definition.agent_id for definition in definitions),
            intents=frozenset().union(*(definition.intents for definition in definitions)),
            domains=frozenset().union(*(definition.domains for definition in definitions)),
            output_kinds=frozenset().union(
                *(definition.output_kinds for definition in definitions)
            ),
            blocked_direct_invocation_agent_ids=frozenset(
                definition.agent_id
                for definition in definitions
                if not definition.direct_invocation_allowed
            ),
        ),
        write_agent_ids=frozenset(
            definition.agent_id for definition in definitions if definition.write_capable
        ),
    )


def _empty_resolution() -> ResolvedAgentDefinitions:
    return _build_resolution(())


__all__ = [
    "DEFAULT_AGENT_DEFINITIONS",
    "AgentDefinition",
    "AgentDefinitionResolver",
    "RUNTIME_INTENTS",
    "RUNTIME_OUTPUT_KINDS",
    "ResolvedAgentDefinitions",
    "resolve_agent_definitions",
]
