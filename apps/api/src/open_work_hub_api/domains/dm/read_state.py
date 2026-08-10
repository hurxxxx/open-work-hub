from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.dm import participants as participant_rules
from open_work_hub_api.domains.dm.models import DmConversation, DmConversationParticipant, DmMessage
from open_work_hub_api.domains.notifications.models import NotificationDmDelivery
from open_work_hub_api.domains.pms.models import Notification


@dataclass(frozen=True)
class DmConversationReadReceipt:
    participant: DmConversationParticipant
    latest_message: DmMessage | None
    notifications: list[Notification]


@dataclass(frozen=True)
class DmMessageReadState:
    unread_count: int
    read_by_all: bool


@dataclass(frozen=True)
class DmConversationReadMark:
    participant: DmConversationParticipant
    latest_message: DmMessage | None
    notifications: list[Notification]

    def apply(self) -> DmConversationReadReceipt:
        self.participant.last_read_message_id = (
            self.latest_message.id if self.latest_message is not None else None
        )
        for notification in self.notifications:
            notification.is_read = True
        return DmConversationReadReceipt(
            participant=self.participant,
            latest_message=self.latest_message,
            notifications=self.notifications,
        )


class DmConversationReadStateStore:
    def __init__(self, db: Session) -> None:
        self._db = db

    def unread_dm_notifications(
        self,
        *,
        user_id: str,
        conversation_id: str,
    ) -> list[Notification]:
        legacy_notifications = list(
            self._db.scalars(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.reference_type == "dm_thread",
                    Notification.reference_id == conversation_id,
                    Notification.is_read == False,  # noqa: E712
                )
            )
        )
        delivered_notifications = list(
            self._db.scalars(
                select(Notification)
                .join(
                    NotificationDmDelivery,
                    NotificationDmDelivery.notification_id == Notification.id,
                )
                .where(
                    NotificationDmDelivery.user_id == user_id,
                    NotificationDmDelivery.conversation_id == conversation_id,
                    Notification.is_read == False,  # noqa: E712
                )
            )
        )
        by_id = {notification.id: notification for notification in legacy_notifications}
        by_id.update({notification.id: notification for notification in delivered_notifications})
        return list(by_id.values())

    def latest_visible_message(
        self,
        conversation_id: str,
        participant: DmConversationParticipant,
    ) -> DmMessage | None:
        return self._db.scalar(
            select(DmMessage)
            .where(
                DmMessage.conversation_id == conversation_id,
                DmMessage.created_at >= participant.joined_at,
            )
            .options(selectinload(DmMessage.sender))
            .options(selectinload(DmMessage.attachments))
            .options(selectinload(DmMessage.reply_to).selectinload(DmMessage.sender))
            .options(selectinload(DmMessage.reply_to).selectinload(DmMessage.attachments))
            .order_by(DmMessage.sequence.desc())
            .limit(1)
        )

    def unread_message_count(
        self,
        *,
        conversation: DmConversation,
        participant: DmConversationParticipant,
        user_id: str,
    ) -> int:
        query = select(func.count(DmMessage.id)).where(
            DmMessage.conversation_id == conversation.id,
            DmMessage.created_at >= participant.joined_at,
            DmMessage.sender_id != user_id,
        )
        if participant.last_read_message_id is not None:
            last_read = self._db.get(DmMessage, participant.last_read_message_id)
            if last_read is not None:
                query = query.where(DmMessage.sequence > last_read.sequence)
        return self._db.scalar(query) or 0


class DmConversationReadState:
    def __init__(self, store: DmConversationReadStateStore) -> None:
        self._store = store

    def mark_conversation_read(
        self,
        *,
        conversation: DmConversation,
        user_id: str,
    ) -> DmConversationReadReceipt:
        participant = self._required_active_participant(conversation, user_id)
        return DmConversationReadMark(
            participant=participant,
            latest_message=self._store.latest_visible_message(conversation.id, participant),
            notifications=self._store.unread_dm_notifications(
                user_id=user_id,
                conversation_id=conversation.id,
            ),
        ).apply()

    def unread_count(self, *, conversation: DmConversation, user_id: str) -> int:
        participant = participant_rules.active_participant(conversation, user_id)
        if participant is None:
            return 0
        return self._store.unread_message_count(
            conversation=conversation,
            participant=participant,
            user_id=user_id,
        )

    def _required_active_participant(
        self,
        conversation: DmConversation,
        user_id: str,
    ) -> DmConversationParticipant:
        participant = participant_rules.active_participant(conversation, user_id)
        if participant is None:
            raise localized_http_exception(status_code=404, code="dm.thread_not_found")
        return participant


def conversation_read_state(db: Session) -> DmConversationReadState:
    return DmConversationReadState(DmConversationReadStateStore(db))


def mark_conversation_read(
    db: Session,
    *,
    conversation: DmConversation,
    user_id: str,
) -> DmConversationReadReceipt:
    return conversation_read_state(db).mark_conversation_read(
        conversation=conversation,
        user_id=user_id,
    )


def unread_dm_notifications(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
) -> list[Notification]:
    return DmConversationReadStateStore(db).unread_dm_notifications(
        user_id=user_id,
        conversation_id=conversation_id,
    )


def latest_visible_message(
    db: Session,
    conversation_id: str,
    participant: DmConversationParticipant,
) -> DmMessage | None:
    return DmConversationReadStateStore(db).latest_visible_message(conversation_id, participant)


def unread_count(db: Session, *, conversation: DmConversation, user_id: str) -> int:
    return conversation_read_state(db).unread_count(conversation=conversation, user_id=user_id)


def message_read_state(
    message: DmMessage,
    *,
    participants: list[DmConversationParticipant],
) -> DmMessageReadState:
    unread_count = 0
    for participant in participants:
        if participant.user_id == message.sender_id:
            continue
        if participant.left_at is not None:
            continue
        if participant.joined_at > message.created_at:
            continue
        last_read_message = getattr(participant, "last_read_message", None)
        if last_read_message is None or last_read_message.sequence < message.sequence:
            unread_count += 1
    return DmMessageReadState(
        unread_count=unread_count,
        read_by_all=unread_count == 0,
    )
