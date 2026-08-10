"""Conversation binding primitives for AI chat routes."""

from __future__ import annotations

from collections.abc import Sequence
import logging
from typing import Protocol

from sqlalchemy.orm import Session

from open_work_hub_api.domains.ai import approvals as ai_approvals
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.conversations import service as conversations_service
from open_work_hub_api.domains.conversations.models import Conversation


logger = logging.getLogger(__name__)


class ConversationTurnMessage(Protocol):
    role: str
    content: str


def start_live_conversation_run(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    conversation: Conversation | None,
) -> ai_approvals.ConversationRunLock | None:
    if conversation is None:
        return None
    return ai_approvals.acquire_conversation_run_lock(
        db,
        workspace=workspace,
        conversation=conversation,
        requested_by_user=user,
    )


def complete_live_conversation_run(
    db: Session,
    lock: ai_approvals.ConversationRunLock | None,
) -> None:
    if lock is None:
        return
    try:
        db.rollback()
        ai_approvals.release_conversation_run_lock(db, lock)
    except Exception as exc:  # noqa: BLE001 - cleanup must not alter chat contract
        logger.exception(
            "live conversation run cleanup failed lock_id=%s: %s",
            lock.id,
            exc,
        )
        db.rollback()


def resolve_requested_conversation(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    conversation_id: str | None,
) -> Conversation | None:
    if not conversation_id:
        return None
    return conversations_service.get_conversation(
        db,
        workspace=workspace,
        user=user,
        conversation_id=conversation_id,
    )


def record_user_turn(
    *,
    db: Session,
    conversation: Conversation,
    messages: Sequence[ConversationTurnMessage],
) -> None:
    """Persist the caller-supplied history onto the attached conversation.

    If the conversation is empty, persist every non-system turn in ``messages``
    so the saved thread matches the exact context the model is about to see.
    If the conversation already has turns, store only the new trailing user
    message; the earlier history is already on disk from prior requests.
    """

    non_system = [message for message in messages if message.role in ("user", "assistant")]
    if not non_system:
        return
    conversation_is_empty = len(conversation.turns) == 0
    if conversation_is_empty:
        first_user = next((message for message in non_system if message.role == "user"), None)
        if first_user is not None:
            conversations_service.autotitle_from_turn(
                db,
                conversation=conversation,
                first_user_content=first_user.content,
            )
        for message in non_system:
            conversations_service.append_turn(
                db,
                conversation=conversation,
                role=message.role,
                content=message.content,
            )
        return

    last_user_content: str | None = None
    for message in reversed(messages):
        if message.role == "user":
            last_user_content = message.content
            break
    if not last_user_content:
        return
    conversations_service.append_turn(
        db,
        conversation=conversation,
        role="user",
        content=last_user_content,
    )
