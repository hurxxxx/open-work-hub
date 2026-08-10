from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai_do_api.domains.dm.schemas import (
    DmConversationItem,
    DmConversationParticipantItem,
    DmMessageAttachmentItem,
    DmMessageItem,
    DmMessageReadStateItem,
    DmMessageReplyToItem,
    DmUserItem,
)


DM_REPLY_BODY_PREVIEW_LENGTH = 120


def user_display_name(user: Any) -> str:
    return user.display_name or user.full_name or user.email


def other_active_participant(
    active_participants: Sequence[Any],
    current_user_id: str,
) -> Any | None:
    return next(
        (
            participant
            for participant in active_participants
            if participant.user_id != current_user_id
        ),
        None,
    )


def direct_other_user(
    conversation: Any,
    *,
    current_user_id: str,
    active_participants: Sequence[Any],
) -> Any | None:
    if conversation.conversation_type != "direct":
        return None
    participant = other_active_participant(active_participants, current_user_id)
    return participant.user if participant is not None else None


def conversation_display_name(
    conversation: Any,
    *,
    current_user_id: str,
    active_participants: Sequence[Any],
) -> str:
    if conversation.conversation_type == "direct":
        other_user = direct_other_user(
            conversation,
            current_user_id=current_user_id,
            active_participants=active_participants,
        )
        return user_display_name(other_user) if other_user is not None else "DM"
    if conversation.title:
        return conversation.title
    names = [
        user_display_name(participant.user)
        for participant in active_participants
        if participant.user is not None and participant.user_id != current_user_id
    ]
    return ", ".join(names[:3]) or "DM"


def message_sender_name(message: Any) -> str:
    if message.sender is None:
        return message.sender_id
    return user_display_name(message.sender) or message.sender_id


def build_user_item(user: Any) -> DmUserItem:
    return DmUserItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        display_name=user.display_name,
        job_title=user.job_title,
        primary_org_unit_name=(
            user.primary_org_unit.name if getattr(user, "primary_org_unit", None) else None
        ),
    )


def build_participant_item(
    participant: Any,
    *,
    user: Any,
) -> DmConversationParticipantItem:
    return DmConversationParticipantItem(
        user=build_user_item(user),
        role=participant.role,
        joined_at=participant.joined_at,
        left_at=participant.left_at,
        muted_at=participant.muted_at,
        last_read_message_id=participant.last_read_message_id,
    )


def build_attachment_item(
    attachment: Any,
    *,
    download_url: str,
    preview_url: str | None,
) -> DmMessageAttachmentItem:
    return DmMessageAttachmentItem(
        id=attachment.id,
        conversation_id=attachment.conversation_id,
        message_id=attachment.message_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        is_image=preview_url is not None,
        download_url=download_url,
        preview_url=preview_url,
        created_at=attachment.created_at,
    )


def build_message_read_state_item(read_state: Any) -> DmMessageReadStateItem:
    return DmMessageReadStateItem(
        unread_count=read_state.unread_count,
        read_by_all=read_state.read_by_all,
    )


def build_message_reply_to_item(message: Any) -> DmMessageReplyToItem:
    body_preview = message.body.strip()
    if len(body_preview) > DM_REPLY_BODY_PREVIEW_LENGTH:
        body_preview = f"{body_preview[: DM_REPLY_BODY_PREVIEW_LENGTH - 1]}..."
    return DmMessageReplyToItem(
        id=message.id,
        sender_id=message.sender_id,
        sender_name=message_sender_name(message),
        body_preview=body_preview,
        attachment_count=len(message.attachments or []),
        created_at=message.created_at,
    )


def build_message_item(
    message: Any,
    *,
    attachments: Sequence[DmMessageAttachmentItem],
    read_state: Any,
    reply_to: DmMessageReplyToItem | None,
) -> DmMessageItem:
    return DmMessageItem(
        id=message.id,
        conversation_id=message.conversation_id,
        thread_id=message.conversation_id,
        sequence=message.sequence,
        sender_id=message.sender_id,
        sender_name=message_sender_name(message),
        read_state=build_message_read_state_item(read_state),
        reply_to=reply_to,
        body=message.body,
        attachments=list(attachments),
        created_at=message.created_at,
    )


def build_conversation_item(
    conversation: Any,
    *,
    current_user_id: str,
    current_participant: Any,
    active_participants: Sequence[Any],
    other_user: Any | None,
    participants: Sequence[DmConversationParticipantItem],
    last_message: DmMessageItem | None,
    unread_count: int,
) -> DmConversationItem:
    return DmConversationItem(
        id=conversation.id,
        conversation_type=conversation.conversation_type,
        thread_type=conversation.conversation_type,
        title=conversation.title,
        display_name=conversation_display_name(
            conversation,
            current_user_id=current_user_id,
            active_participants=active_participants,
        ),
        other_user=build_user_item(other_user) if other_user is not None else None,
        participants=list(participants),
        participant_count=len(active_participants),
        last_message=last_message,
        unread_count=unread_count,
        last_read_message_id=current_participant.last_read_message_id,
        muted_at=current_participant.muted_at,
        created_by_id=conversation.created_by_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def conversation_snapshot_payload(
    *,
    conversation_id: str,
    conversation: Any,
    message: Any | None = None,
) -> dict[str, Any]:
    conversation_payload = dump_realtime_payload(conversation)
    data: dict[str, Any] = {
        "conversation": conversation_payload,
        "thread": conversation_payload,
        "conversation_id": conversation_id,
        "thread_id": conversation_id,
    }
    if message is not None:
        data["message"] = dump_realtime_payload(message)
    return data


def conversation_removed_payload(*, conversation_id: str) -> dict[str, Any]:
    return {"conversation_id": conversation_id}


def conversation_read_payload(
    *,
    user_id: str,
    conversation_id: str,
    conversation: Any,
) -> dict[str, Any]:
    conversation_payload = dump_realtime_payload(conversation)
    return {
        "conversation_id": conversation_id,
        "thread_id": conversation_id,
        "user_id": user_id,
        "conversation": conversation_payload,
        "thread": conversation_payload,
    }


def dump_realtime_payload(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return payload
