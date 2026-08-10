from __future__ import annotations

from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.dm import (
    attachment_links,
    participants as participant_rules,
    read_state,
    thread_projection,
)
from ai_do_api.domains.dm.models import (
    DmConversation,
    DmConversationParticipant,
    DmMessage,
    DmMessageAttachment,
)
from ai_do_api.domains.dm.schemas import (
    DmMessageAttachmentItem,
    DmConversationItem,
    DmConversationParticipantItem,
    DmMessageItem,
    DmUserItem,
)


def serialize_user(user: User) -> DmUserItem:
    return thread_projection.build_user_item(user)


def serialize_conversation(
    db: Session,
    conversation: DmConversation,
    *,
    current_user: User,
) -> DmConversationItem:
    current_participant = participant_rules.active_participant(conversation, current_user.id)
    if current_participant is None:
        raise localized_http_exception(status_code=404, code="dm.thread_not_found")
    active_participants = participant_rules.active_participants(conversation)
    other_participant = participant_rules.other_active_participant(conversation, current_user.id)
    other_user = (
        other_participant.user
        if conversation.conversation_type == "direct" and other_participant is not None
        else None
    )
    if conversation.conversation_type == "direct" and other_user is None:
        raise localized_http_exception(status_code=404, code="dm.thread_not_found")
    last_message = read_state.latest_visible_message(db, conversation.id, current_participant)
    return thread_projection.build_conversation_item(
        conversation,
        current_user_id=current_user.id,
        current_participant=current_participant,
        active_participants=active_participants,
        other_user=other_user,
        participants=[serialize_participant(participant) for participant in active_participants],
        last_message=(
            serialize_message(
                last_message,
                conversation=conversation,
                viewer_participant=current_participant,
            )
            if last_message is not None
            else None
        ),
        unread_count=read_state.unread_count(
            db,
            conversation=conversation,
            user_id=current_user.id,
        ),
    )


def serialize_participant(participant: DmConversationParticipant) -> DmConversationParticipantItem:
    if participant.user is None:
        raise localized_http_exception(status_code=404, code="dm.participant_not_found")
    return thread_projection.build_participant_item(participant, user=participant.user)


def serialize_message(
    message: DmMessage,
    *,
    conversation: DmConversation | None = None,
    viewer_participant: DmConversationParticipant | None = None,
) -> DmMessageItem:
    source_conversation = conversation or getattr(message, "conversation", None)
    active_participants = (
        participant_rules.active_participants(source_conversation)
        if source_conversation is not None
        else []
    )
    reply_to = _visible_reply_to(message, viewer_participant=viewer_participant)
    return thread_projection.build_message_item(
        message,
        attachments=[serialize_attachment(attachment) for attachment in message.attachments],
        read_state=(
            read_state.message_read_state(message, participants=active_participants)
            if source_conversation is not None
            else read_state.DmMessageReadState(unread_count=0, read_by_all=True)
        ),
        reply_to=(
            thread_projection.build_message_reply_to_item(reply_to)
            if reply_to is not None
            else None
        ),
    )


def _visible_reply_to(
    message: DmMessage,
    *,
    viewer_participant: DmConversationParticipant | None,
) -> DmMessage | None:
    reply_to = getattr(message, "reply_to", None)
    if reply_to is None:
        return None
    if viewer_participant is not None and reply_to.created_at < viewer_participant.joined_at:
        return None
    return reply_to


def serialize_attachment(attachment: DmMessageAttachment) -> DmMessageAttachmentItem:
    preview_url = attachment_links.build_dm_attachment_preview_url(attachment)
    return thread_projection.build_attachment_item(
        attachment,
        download_url=attachment_links.build_dm_attachment_download_url(attachment),
        preview_url=preview_url,
    )
