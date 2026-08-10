from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from open_alm_api.domains.conversations.scope_registry import ConversationExperience


WEB_SEARCH_SCOPE_REF = "web_search"
RESEARCH_TRENDS_SCOPE_REF = "research_trends"
STANDARDS_MONITOR_SCOPE_REF = "standards_monitor"
QNA_ASSISTANT_SCOPE_REF = "qna_assistant"
PATENT_AGENT_SCOPE_REF = "patent_agent"
PATENT_BRAINY_SCOPE_REF = "patent_brainy"
PPT_JOB_SCOPE_REF = "ppt_job"


@dataclass(frozen=True, slots=True)
class AppConversationScopeDefinition:
    scope_ref: str
    owner_app_id: str
    system_prompt: str


DEFAULT_APP_CONVERSATION_SCOPES: tuple[AppConversationScopeDefinition, ...] = (
    AppConversationScopeDefinition(
        WEB_SEARCH_SCOPE_REF,
        "web-search",
        "Persist web search assistant conversations for this workspace.",
    ),
    AppConversationScopeDefinition(
        RESEARCH_TRENDS_SCOPE_REF,
        "research-trends",
        "Persist research trends assistant conversations for this workspace.",
    ),
    AppConversationScopeDefinition(
        STANDARDS_MONITOR_SCOPE_REF,
        "standards-monitor",
        "Persist standards monitor assistant conversations for this workspace.",
    ),
    AppConversationScopeDefinition(
        QNA_ASSISTANT_SCOPE_REF,
        "qa-assistant",
        "Persist company Q&A assistant conversations for this user.",
    ),
    AppConversationScopeDefinition(
        PATENT_AGENT_SCOPE_REF,
        "patent-compose",
        "Persist patent search assistant conversations for this workspace.",
    ),
    AppConversationScopeDefinition(
        PATENT_BRAINY_SCOPE_REF,
        "patent-compose",
        "Persist patent detail assistant conversations for this workspace.",
    ),
    AppConversationScopeDefinition(
        PPT_JOB_SCOPE_REF,
        "ppt-assistant",
        "Persist PPT assistant edit conversations for this job.",
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
        workspace: Any,
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
        workspace: Any,
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
    "PATENT_AGENT_SCOPE_REF",
    "PATENT_BRAINY_SCOPE_REF",
    "PPT_JOB_SCOPE_REF",
    "QNA_ASSISTANT_SCOPE_REF",
    "RESEARCH_TRENDS_SCOPE_REF",
    "STANDARDS_MONITOR_SCOPE_REF",
    "WEB_SEARCH_SCOPE_REF",
    "default_app_conversation_scope_adapters",
]
