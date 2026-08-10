from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ConversationScopeArtifact:
    id: str
    type: str
    content: str
    title: str | None = None
    language: str | None = None

    def as_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "language": self.language,
            "content": self.content,
            "status": "closed",
        }


@dataclass(frozen=True)
class ConversationScopeTurnContext:
    prompt: str | None = None
    artifacts: tuple[ConversationScopeArtifact, ...] = field(default_factory=tuple)
    direct_response: str | None = None
    server_owned_artifact_types: frozenset[str] = field(default_factory=frozenset)
    background_run_id: str | None = None
    background_artifact_id: str | None = None
    assistant_turn_persisted: bool = False


@dataclass(frozen=True, slots=True)
class ConversationExperience:
    """Server-owned availability and execution binding for a chat surface."""

    owner_app_id: str
    chat_workload_id: str | None = None
    execution_mode: Literal["inline", "durable_background"] = "inline"
    requires_persistence: bool = False
    allowed_tool_app_ids: tuple[str, ...] | None = None


class ConversationScopeAdapter(Protocol):
    scope_ref: str
    experience: ConversationExperience
    server_owned_artifact_types: frozenset[str]

    def validate(
        self,
        *,
        db: Any,
        workspace: Any,
        principal: Any,
        user: Any,
        scope_resource_id: str,
    ) -> None: ...

    def system_prompt(
        self,
        *,
        db: Any,
        workspace: Any,
        principal: Any,
        user: Any,
        scope_resource_id: str,
    ) -> str: ...


_scope_adapters: dict[str, ConversationScopeAdapter] = {}
_server_owned_artifact_type_owners: dict[str, str] = {}


def register_conversation_scope_adapter(adapter: ConversationScopeAdapter) -> None:
    if adapter.scope_ref in _scope_adapters:
        raise ValueError(f"Conversation scope adapter already registered: {adapter.scope_ref}")
    experience = getattr(adapter, "experience", None)
    if not isinstance(experience, ConversationExperience):
        raise ValueError(
            f"Conversation scope adapter {adapter.scope_ref} must declare an experience"
        )
    owner_app_id = experience.owner_app_id.strip()
    if not owner_app_id:
        raise ValueError(
            f"Conversation scope adapter {adapter.scope_ref} must declare an owner app"
        )
    workload_id = experience.chat_workload_id
    if workload_id is not None and not workload_id.strip():
        raise ValueError(
            f"Conversation scope adapter {adapter.scope_ref} has a blank chat workload"
        )
    raw_artifact_types = getattr(adapter, "server_owned_artifact_types", frozenset())
    if not isinstance(raw_artifact_types, (set, frozenset, tuple, list)):
        raise ValueError(
            f"Conversation scope adapter {adapter.scope_ref} has invalid "
            "server-owned artifact types"
        )
    artifact_types: set[str] = set()
    for raw_artifact_type in raw_artifact_types:
        if not isinstance(raw_artifact_type, str) or not raw_artifact_type.strip():
            raise ValueError(
                f"Conversation scope adapter {adapter.scope_ref} has an invalid "
                "server-owned artifact type"
            )
        artifact_type = raw_artifact_type.strip()
        existing_owner = _server_owned_artifact_type_owners.get(artifact_type)
        if existing_owner is not None and existing_owner != adapter.scope_ref:
            raise ValueError(
                f"Server-owned artifact type {artifact_type} is already owned by "
                f"conversation scope {existing_owner}"
            )
        artifact_types.add(artifact_type)
    _scope_adapters[adapter.scope_ref] = adapter
    for artifact_type in artifact_types:
        _server_owned_artifact_type_owners[artifact_type] = adapter.scope_ref


def get_conversation_scope_adapter(scope_ref: str) -> ConversationScopeAdapter | None:
    return _scope_adapters.get(scope_ref)


def supported_conversation_scope_refs() -> frozenset[str]:
    return frozenset(_scope_adapters)


def conversation_scope_adapters() -> tuple[ConversationScopeAdapter, ...]:
    return tuple(_scope_adapters.values())


def server_owned_artifact_types_for_scope(scope_ref: str) -> frozenset[str]:
    adapter = _scope_adapters.get(scope_ref)
    if adapter is None:
        return frozenset()
    raw_artifact_types = getattr(adapter, "server_owned_artifact_types", frozenset())
    return frozenset(
        artifact_type.strip()
        for artifact_type in raw_artifact_types
        if isinstance(artifact_type, str) and artifact_type.strip()
    )


def reset_conversation_scope_adapters() -> None:
    _scope_adapters.clear()
    _server_owned_artifact_type_owners.clear()


__all__ = [
    "ConversationExperience",
    "ConversationScopeAdapter",
    "ConversationScopeArtifact",
    "ConversationScopeTurnContext",
    "conversation_scope_adapters",
    "get_conversation_scope_adapter",
    "register_conversation_scope_adapter",
    "reset_conversation_scope_adapters",
    "server_owned_artifact_types_for_scope",
    "supported_conversation_scope_refs",
]
