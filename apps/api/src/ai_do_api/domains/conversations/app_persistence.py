from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.conversations import service as conversations_service
from ai_do_api.domains.conversations.models import Conversation, ConversationTurn


@dataclass(frozen=True, slots=True)
class ConversationAppendResult:
    conversation: Conversation
    user_turn: ConversationTurn


def get_or_create_app_conversation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str | None,
    scope_ref: str,
    scope_resource_id: str,
) -> Conversation:
    if conversation_id:
        conversation = conversations_service.get_conversation(
            db,
            workspace=workspace,
            user=user,
            conversation_id=conversation_id,
        )
        if (
            conversation.scope_ref != scope_ref
            or conversation.scope_resource_id != scope_resource_id
        ):
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="ai.conversation_scope_mismatch",
            )
        return conversation
    return conversations_service.create_conversation(
        db,
        workspace=workspace,
        user=user,
        title="",
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
    )


def append_user_app_turn(
    db: Session,
    *,
    conversation: Conversation,
    content: str,
    meta: dict[str, Any] | None = None,
) -> ConversationTurn:
    if not conversation.turns:
        conversations_service.autotitle_from_turn(
            db,
            conversation=conversation,
            first_user_content=content,
        )
    return conversations_service.append_turn(
        db,
        conversation=conversation,
        role="user",
        content=content,
        meta=meta,
    )


def append_assistant_app_turn(
    db: Session,
    *,
    conversation: Conversation,
    content: str,
    meta: dict[str, Any] | None = None,
) -> ConversationTurn:
    return conversations_service.append_turn(
        db,
        conversation=conversation,
        role="assistant",
        content=content,
        meta=meta,
    )


def recent_turns_for_prompt(
    conversation: Conversation,
    *,
    limit: int,
) -> list[ConversationTurn]:
    turns = [
        turn
        for turn in conversation.turns
        if turn.role in ("user", "assistant") and turn.content.strip()
    ]
    return turns[-limit:]


def append_user_and_attach(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str | None,
    scope_ref: str,
    scope_resource_id: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> ConversationAppendResult:
    conversation = get_or_create_app_conversation(
        db,
        workspace=workspace,
        user=user,
        conversation_id=conversation_id,
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
    )
    turn = append_user_app_turn(
        db,
        conversation=conversation,
        content=content,
        meta=meta,
    )
    return ConversationAppendResult(conversation=conversation, user_turn=turn)


__all__ = [
    "ConversationAppendResult",
    "append_assistant_app_turn",
    "append_user_and_attach",
    "append_user_app_turn",
    "get_or_create_app_conversation",
    "recent_turns_for_prompt",
]
