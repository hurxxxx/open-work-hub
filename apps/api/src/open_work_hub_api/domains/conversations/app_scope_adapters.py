from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from open_work_hub_api.domains.conversations.scope_registry import ConversationExperience

WEB_SEARCH_SCOPE_REF = "web_search"


@dataclass(frozen=True, slots=True)
class AppConversationScopeDefinition:
    scope_ref: str
    owner_app_id: str
    system_prompt: str


DEFAULT_APP_CONVERSATION_SCOPES: tuple[AppConversationScopeDefinition, ...] = (
    AppConversationScopeDefinition(
        WEB_SEARCH_SCOPE_REF,
        "web-search",
        "Persist web search assistant conversations for this user.",
    ),
)


class AppConversationScopeAdapter:
    def __init__(self, definition: AppConversationScopeDefinition) -> None:
        self.scope_ref = definition.scope_ref
        self.experience = ConversationExperience(owner_app_id=definition.owner_app_id)
        self._system_prompt = definition.system_prompt

    def validate(
        self,
        *,
        db: Any,
        principal: Any,
        user: Any,
        scope_resource_id: str,
    ) -> None:
        if not scope_resource_id.strip():
            raise ValueError("scope_resource_id is required")

    def system_prompt(
        self,
        *,
        db: Any,
        principal: Any,
        user: Any,
        scope_resource_id: str,
    ) -> str:
        return self._system_prompt


def default_app_conversation_scope_adapters() -> tuple[AppConversationScopeAdapter, ...]:
    return tuple(
        AppConversationScopeAdapter(definition) for definition in DEFAULT_APP_CONVERSATION_SCOPES
    )


__all__ = [
    "AppConversationScopeAdapter",
    "AppConversationScopeDefinition",
    "DEFAULT_APP_CONVERSATION_SCOPES",
    "WEB_SEARCH_SCOPE_REF",
    "default_app_conversation_scope_adapters",
]
