from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.conversations.default_scope_adapters import (
    ensure_conversation_scope_adapters_registered,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.conversations.models import Conversation
from open_work_hub_api.domains.conversations.scope_registry import (
    ConversationScopeAdapter,
    ConversationScopeArtifact,
    ConversationScopeTurnContext,
    get_conversation_scope_adapter,
    server_owned_artifact_types_for_scope,
    supported_conversation_scope_refs as registered_conversation_scope_refs,
)


def validate_requested_conversation_scope(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    scope_ref: str | None,
    scope_resource_id: str | None,
) -> None:
    if scope_ref is None or scope_resource_id is None:
        return
    ensure_conversation_scope_adapters_registered()
    adapter = get_conversation_scope_adapter(scope_ref)
    if adapter is None:
        _raise_unsupported_scope(scope_ref)
    try:
        adapter.validate(
            db=db,
            workspace=workspace,
            principal=principal,
            user=user,
            scope_resource_id=scope_resource_id,
        )
        _require_scope_system_prompt(
            adapter.system_prompt(
                db=db,
                workspace=workspace,
                principal=principal,
                user=user,
                scope_resource_id=scope_resource_id,
            ),
            scope_ref=scope_ref,
        )
    except ValueError:
        _raise_unsupported_scope(scope_ref)
    return


def supported_conversation_scope_refs() -> frozenset[str]:
    ensure_conversation_scope_adapters_registered()
    return registered_conversation_scope_refs()


def is_supported_conversation_scope_ref(scope_ref: str) -> bool:
    return scope_ref in supported_conversation_scope_refs()


def _raise_unsupported_scope(scope_ref: str) -> None:
    raise localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="ai.unsupported_conversation_scope",
        scope_ref=scope_ref,
    )


def conversation_scope_system_prompt(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    conversation: Conversation | None,
) -> str | None:
    if (
        conversation is None
        or conversation.scope_ref is None
        or conversation.scope_resource_id is None
    ):
        return None
    ensure_conversation_scope_adapters_registered()
    adapter = get_conversation_scope_adapter(conversation.scope_ref)
    if adapter is None:
        _raise_unsupported_scope(conversation.scope_ref)
    try:
        adapter.validate(
            db=db,
            workspace=workspace,
            principal=principal,
            user=user,
            scope_resource_id=conversation.scope_resource_id,
        )
        return _require_scope_system_prompt(
            adapter.system_prompt(
                db=db,
                workspace=workspace,
                principal=principal,
                user=user,
                scope_resource_id=conversation.scope_resource_id,
            ),
            scope_ref=conversation.scope_ref,
        )
    except ValueError:
        _raise_unsupported_scope(conversation.scope_ref)
    return None


def conversation_scope_turn_system_prompt(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    conversation: Conversation | None,
    messages: list[dict[str, Any]],
) -> str | None:
    return conversation_scope_turn_context(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        conversation=conversation,
        messages=messages,
    ).prompt


def conversation_scope_turn_context(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    conversation: Conversation | None,
    messages: list[dict[str, Any]],
) -> ConversationScopeTurnContext:
    base_prompt = conversation_scope_system_prompt(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        conversation=conversation,
    )
    if (
        conversation is None
        or conversation.scope_ref is None
        or conversation.scope_resource_id is None
    ):
        return ConversationScopeTurnContext(prompt=base_prompt)
    adapter = get_conversation_scope_adapter(conversation.scope_ref)
    if adapter is None:
        _raise_unsupported_scope(conversation.scope_ref)
    server_owned_artifact_types = server_owned_artifact_types_for_scope(
        conversation.scope_ref
    )
    extra_context = _adapter_turn_context(
        adapter,
        db=db,
        workspace=workspace,
        principal=principal,
        user=user,
        conversation=conversation,
        scope_resource_id=conversation.scope_resource_id,
        messages=messages,
    )
    prompts = [prompt for prompt in (base_prompt, extra_context.prompt) if prompt]
    return ConversationScopeTurnContext(
        prompt="\n\n".join(prompts) if prompts else None,
        artifacts=extra_context.artifacts,
        direct_response=extra_context.direct_response,
        server_owned_artifact_types=(
            server_owned_artifact_types
            | extra_context.server_owned_artifact_types
        ),
        background_run_id=extra_context.background_run_id,
        background_artifact_id=extra_context.background_artifact_id,
        assistant_turn_persisted=extra_context.assistant_turn_persisted,
    )


def _adapter_turn_context(
    adapter: ConversationScopeAdapter,
    *,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    conversation: Conversation,
    scope_resource_id: str,
    messages: list[dict[str, Any]],
) -> ConversationScopeTurnContext:
    turn_context = getattr(adapter, "turn_context", None)
    if callable(turn_context):
        context = turn_context(
            db=db,
            workspace=workspace,
            principal=principal,
            user=user,
            conversation=conversation,
            scope_resource_id=scope_resource_id,
            messages=messages,
        )
        return _coerce_turn_context(context)
    return ConversationScopeTurnContext(
        prompt=_adapter_turn_context_prompt(
            adapter,
            db=db,
            workspace=workspace,
            principal=principal,
            user=user,
            scope_resource_id=scope_resource_id,
            messages=messages,
        )
    )


def _adapter_turn_context_prompt(
    adapter: ConversationScopeAdapter,
    *,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    scope_resource_id: str,
    messages: list[dict[str, Any]],
) -> str | None:
    turn_context_prompt = getattr(adapter, "turn_context_prompt", None)
    if not callable(turn_context_prompt):
        return None
    prompt = turn_context_prompt(
        db=db,
        workspace=workspace,
        principal=principal,
        user=user,
        scope_resource_id=scope_resource_id,
        messages=messages,
    )
    return prompt.strip() if isinstance(prompt, str) and prompt.strip() else None


def _coerce_turn_context(value: Any) -> ConversationScopeTurnContext:
    if isinstance(value, ConversationScopeTurnContext):
        return value
    if isinstance(value, str):
        return ConversationScopeTurnContext(prompt=value.strip() or None)
    if not isinstance(value, dict):
        return ConversationScopeTurnContext()
    prompt = value.get("prompt")
    direct_response = value.get("direct_response")
    raw_artifacts = value.get("artifacts") or ()
    raw_server_owned_artifact_types = value.get("server_owned_artifact_types") or ()
    background_run_id = value.get("background_run_id")
    background_artifact_id = value.get("background_artifact_id")
    artifacts: list[ConversationScopeArtifact] = []
    if isinstance(raw_artifacts, (list, tuple)):
        for artifact in raw_artifacts:
            if isinstance(artifact, ConversationScopeArtifact):
                artifacts.append(artifact)
    server_owned_artifact_types = (
        frozenset(
            artifact_type.strip()
            for artifact_type in raw_server_owned_artifact_types
            if isinstance(artifact_type, str) and artifact_type.strip()
        )
        if isinstance(raw_server_owned_artifact_types, (list, tuple, set, frozenset))
        else frozenset()
    )
    return ConversationScopeTurnContext(
        prompt=prompt.strip() if isinstance(prompt, str) and prompt.strip() else None,
        artifacts=tuple(artifacts),
        direct_response=(
            direct_response.strip()
            if isinstance(direct_response, str) and direct_response.strip()
            else None
        ),
        server_owned_artifact_types=server_owned_artifact_types,
        background_run_id=(
            background_run_id.strip()
            if isinstance(background_run_id, str) and background_run_id.strip()
            else None
        ),
        background_artifact_id=(
            background_artifact_id.strip()
            if isinstance(background_artifact_id, str) and background_artifact_id.strip()
            else None
        ),
        assistant_turn_persisted=value.get("assistant_turn_persisted") is True,
    )


def conversation_scope_server_owned_artifact_types(
    conversation: Conversation | None,
) -> frozenset[str]:
    if conversation is None or conversation.scope_ref is None:
        return frozenset()
    ensure_conversation_scope_adapters_registered()
    return server_owned_artifact_types_for_scope(conversation.scope_ref)


def messages_with_scope_prompt(
    messages: list[dict[str, Any]],
    *,
    scope_system_prompt: str | None,
) -> list[dict[str, Any]]:
    cloned_messages = [dict(message) for message in messages]
    if not scope_system_prompt:
        return cloned_messages
    if (
        cloned_messages
        and cloned_messages[0].get("role") == "system"
        and isinstance(cloned_messages[0].get("content"), str)
    ):
        merged = dict(cloned_messages[0])
        existing_content = (merged.get("content") or "").strip()
        merged["content"] = (
            f"{scope_system_prompt}\n\n{existing_content}"
            if existing_content
            else scope_system_prompt
        )
        return [merged, *cloned_messages[1:]]
    return [{"role": "system", "content": scope_system_prompt}, *cloned_messages]


def _require_scope_system_prompt(prompt: str | None, *, scope_ref: str) -> str:
    normalized = (prompt or "").strip()
    if not normalized:
        raise localized_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="ai.conversation_scope_prompt_missing",
            scope_ref=scope_ref,
        )
    return normalized


__all__ = [
    "conversation_scope_server_owned_artifact_types",
    "conversation_scope_system_prompt",
    "conversation_scope_turn_context",
    "conversation_scope_turn_system_prompt",
    "is_supported_conversation_scope_ref",
    "messages_with_scope_prompt",
    "supported_conversation_scope_refs",
    "validate_requested_conversation_scope",
]
