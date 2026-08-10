from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import User
from open_alm_api.domains.dm import (
    participants,
    realtime_event_types,
    realtime_payloads,
    serialization,
)
from open_alm_api.domains.dm.models import DmConversation, DmMessage
from open_alm_api.domains.dm.schemas import DmConversationItem
from open_alm_api.domains.notifications import (
    realtime_event_types as notification_realtime_event_types,
)
from open_alm_api.domains.notifications import realtime_events as notification_realtime_events


class UserRealtimePublisher(Protocol):
    def publish_user(self, user_id: str, event: dict[str, Any]) -> None: ...


def _user_event(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "data": data}


def _conversation_snapshot_for_user(
    db: Session,
    conversation: DmConversation,
    user: User,
    *,
    message: DmMessage | None,
) -> dict[str, Any]:
    conversation_item = serialization.serialize_conversation(
        db,
        conversation,
        current_user=user,
    )
    participant = participants.active_participant(conversation, user.id)
    message_item = (
        serialization.serialize_message(
            message,
            conversation=conversation,
            viewer_participant=participant,
        )
        if message is not None
        else None
    )
    return realtime_payloads.conversation_snapshot_payload(
        conversation_id=conversation.id,
        conversation=conversation_item,
        message=message_item,
    )


@dataclass(frozen=True)
class DmEventPublisher:
    db: Session
    realtime: UserRealtimePublisher

    def publish_conversation_snapshot(
        self,
        conversation: DmConversation,
        event_type: str,
        *,
        message: DmMessage | None = None,
    ) -> None:
        for user in participants.active_participant_users(conversation):
            self.publish_conversation_for_user(
                conversation,
                user.id,
                event_type,
                message=message,
            )

    def publish_conversation_for_user(
        self,
        conversation: DmConversation,
        user_id: str,
        event_type: str,
        *,
        message: DmMessage | None = None,
    ) -> None:
        user = self.db.get(User, user_id)
        if user is None:
            return
        self._publish_user_event(
            user_id,
            event_type,
            _conversation_snapshot_for_user(
                self.db,
                conversation,
                user,
                message=message,
            ),
        )

    def _publish_user_event(self, user_id: str, event_type: str, data: dict[str, Any]) -> None:
        self.realtime.publish_user(user_id, _user_event(event_type, data))

    def publish_conversation_removed(self, user_id: str, *, conversation_id: str) -> None:
        self._publish_user_event(
            user_id,
            realtime_event_types.DM_CONVERSATION_REMOVED,
            realtime_payloads.conversation_removed_payload(
                conversation_id=conversation_id,
            ),
        )

    def publish_conversation_read(
        self,
        reader_user_id: str,
        *,
        conversation_id: str,
        conversation: DmConversation,
    ) -> None:
        for user in participants.active_participant_users(conversation):
            conversation_item = serialization.serialize_conversation(
                self.db,
                conversation,
                current_user=user,
            )
            self._publish_user_event(
                user.id,
                realtime_event_types.DM_CONVERSATION_READ,
                realtime_payloads.conversation_read_payload(
                    user_id=reader_user_id,
                    conversation_id=conversation_id,
                    conversation=conversation_item,
                ),
            )

    def publish_conversation_read_for_user(
        self,
        recipient_user_id: str,
        *,
        reader_user_id: str,
        conversation_id: str,
        conversation: DmConversationItem,
    ) -> None:
        self._publish_user_event(
            recipient_user_id,
            realtime_event_types.DM_CONVERSATION_READ,
            realtime_payloads.conversation_read_payload(
                user_id=reader_user_id,
                conversation_id=conversation_id,
                conversation=conversation,
            ),
        )

    def publish_notification(
        self,
        user_id: str,
        *,
        notification: dict[str, Any] | None,
        unread_count: int,
        event_type: str = notification_realtime_event_types.NOTIFICATION_CREATED,
    ) -> None:
        notification_realtime_events.publish_notification_event(
            self.realtime,
            user_id,
            event_type,
            notification=notification,
            unread_count=unread_count,
        )
