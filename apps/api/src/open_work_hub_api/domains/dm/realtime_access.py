from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from open_work_hub_api.core.realtime import RealtimeEvent
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.dm import (
    conversation_queries,
    participants,
    realtime_event_types as event_types,
    realtime_payloads,
    serialization,
)
from open_work_hub_api.domains.dm.models import DmMessage


def authorize_dm_realtime_event(
    db: Session, *, user: User, event: RealtimeEvent
) -> RealtimeEvent | None:
    """Project queued events from current participation and join-history boundaries."""
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    conversation_id = data.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        return None
    removed = {
        "type": event_types.DM_CONVERSATION_REMOVED,
        "data": realtime_payloads.conversation_removed_payload(conversation_id=conversation_id),
    }
    event_type = event.get("type")
    if event_type == event_types.DM_CONVERSATION_REMOVED:
        return removed
    if event_type not in {
        event_types.DM_MESSAGE_CREATED,
        event_types.DM_CONVERSATION_CREATED,
        event_types.DM_CONVERSATION_UPDATED,
        event_types.DM_CONVERSATION_READ,
    }:
        return None
    try:
        conversation = conversation_queries.require_user_conversation(
            db, current_user=user, conversation_id=conversation_id
        )
        current = serialization.serialize_conversation(db, conversation, current_user=user)
    except HTTPException:
        return removed
    participant = participants.active_participant(conversation, user.id)
    assert participant is not None
    message = None
    if event_type == event_types.DM_MESSAGE_CREATED:
        queued_message = data.get("message")
        message_id = queued_message.get("id") if isinstance(queued_message, dict) else None
        stored = db.get(DmMessage, message_id) if isinstance(message_id, str) else None
        if (
            stored is not None
            and stored.conversation_id == conversation_id
            and stored.created_at >= participant.joined_at
        ):
            message = serialization.serialize_message(
                stored, conversation=conversation, viewer_participant=participant
            )
        else:
            # Rejoining grants only the new history window. Refresh the current
            # conversation without resurrecting the queued pre-join message.
            event_type = event_types.DM_CONVERSATION_UPDATED
    reader_id = data.get("user_id")
    if event_type == event_types.DM_CONVERSATION_READ:
        if isinstance(reader_id, str) and participants.active_participant(conversation, reader_id):
            projected = realtime_payloads.conversation_read_payload(
                user_id=reader_id, conversation_id=conversation_id, conversation=current
            )
        else:
            event_type = event_types.DM_CONVERSATION_UPDATED
            projected = realtime_payloads.conversation_snapshot_payload(
                conversation_id=conversation_id, conversation=current
            )
    else:
        projected = realtime_payloads.conversation_snapshot_payload(
            conversation_id=conversation_id, conversation=current, message=message
        )
    return {**event, "type": event_type, "data": projected}
