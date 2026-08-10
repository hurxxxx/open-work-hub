from __future__ import annotations

from ai_do_api.domains.conversations.scope_registry import (
    ConversationScopeAdapter,
    get_conversation_scope_adapter,
    register_conversation_scope_adapter,
)


def ensure_conversation_scope_adapters_registered() -> None:
    from ai_do_api.domains.conversations.app_scope_adapters import (
        default_app_conversation_scope_adapters,
    )
    from ai_do_api.domains.files.conversation_scope import (
        iter_extension_conversation_scope_adapters as files_scope_adapters,
    )
    from ai_do_api.domains.legacy_issues.conversation_scope import (
        LegacyIssueConversationScopeAdapter,
    )
    from ai_do_api.domains.meeting.conversation_scope import MeetingConversationScopeAdapter

    for adapter in default_app_conversation_scope_adapters():
        _register_default_conversation_scope_adapter(adapter)
    for adapter in files_scope_adapters():
        _register_default_conversation_scope_adapter(adapter)
    _register_default_conversation_scope_adapter(MeetingConversationScopeAdapter())
    _register_default_conversation_scope_adapter(LegacyIssueConversationScopeAdapter())


def is_supported_conversation_scope_ref(scope_ref: str) -> bool:
    ensure_conversation_scope_adapters_registered()
    return get_conversation_scope_adapter(scope_ref) is not None


def _register_default_conversation_scope_adapter(adapter: ConversationScopeAdapter) -> None:
    if get_conversation_scope_adapter(adapter.scope_ref) is not None:
        return
    register_conversation_scope_adapter(adapter)


__all__ = [
    "ensure_conversation_scope_adapters_registered",
    "is_supported_conversation_scope_ref",
]
