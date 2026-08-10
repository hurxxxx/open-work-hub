from __future__ import annotations

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.dm.models import DmConversation, DmConversationParticipant


def active_participants(conversation: DmConversation) -> list[DmConversationParticipant]:
    return [
        participant
        for participant in conversation.participants
        if participant.left_at is None
    ]


def active_participant(
    conversation: DmConversation,
    user_id: str,
) -> DmConversationParticipant | None:
    return next(
        (
            participant
            for participant in conversation.participants
            if participant.user_id == user_id and participant.left_at is None
        ),
        None,
    )


def other_active_participant(
    conversation: DmConversation,
    user_id: str,
) -> DmConversationParticipant | None:
    return next(
        (
            participant
            for participant in active_participants(conversation)
            if participant.user_id != user_id
        ),
        None,
    )


def active_participant_users(conversation: DmConversation) -> list[User]:
    return [
        participant.user
        for participant in active_participants(conversation)
        if participant.user is not None
    ]


def ensure_group_conversation(conversation: DmConversation) -> None:
    if conversation.conversation_type != "group":
        raise localized_http_exception(status_code=422, code="dm.group_only")


def ensure_conversation_manager(conversation: DmConversation, user_id: str) -> None:
    participant = active_participant(conversation, user_id)
    if participant is None or participant.role not in {"owner", "admin"}:
        raise localized_http_exception(status_code=403, code="dm.manage_forbidden")


def ensure_group_conversation_manager(
    conversation: DmConversation,
    user_id: str,
) -> None:
    ensure_group_conversation(conversation)
    ensure_conversation_manager(conversation, user_id)


def promote_owner_if_needed(conversation: DmConversation, *, departing_user_id: str) -> None:
    departing = next(
        (
            participant
            for participant in conversation.participants
            if participant.user_id == departing_user_id
        ),
        None,
    )
    if departing is None or departing.role != "owner":
        return
    candidates = [
        participant
        for participant in active_participants(conversation)
        if participant.user_id != departing_user_id
    ]
    if not candidates:
        return
    next_owner = sorted(candidates, key=lambda participant: participant.joined_at)[0]
    next_owner.role = "owner"
