from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import User, utcnow_naive
from open_alm_api.domains.auth.security import hash_password, new_id
from open_alm_api.domains.dm import (
    conversation_lifecycle,
    conversation_queries,
    message_delivery,
    message_flow,
)
from open_alm_api.domains.dm.models import DmConversation, DmMessage
from open_alm_api.domains.notifications.models import NotificationDmDelivery
from open_alm_api.domains.pms.models import Notification


OPEN_ALM_BOT_USER_ID = "open-alm-notification-bot"
OPEN_ALM_BOT_LOGIN_ID = "open-alm-bot"
OPEN_ALM_BOT_EMAIL = "open-alm-bot@open-alm.local"
OPEN_ALM_BOT_NAME = "Open ALM Bot"


@dataclass(frozen=True)
class NotificationDmDeliveryResult:
    delivery: NotificationDmDelivery
    conversation: DmConversation
    message: DmMessage
    created: bool


def ensure_notification_bot_user(db: Session) -> User:
    bot = db.get(User, OPEN_ALM_BOT_USER_ID)
    if bot is not None:
        _normalize_bot_user(bot)
        return bot

    bot = User(
        id=OPEN_ALM_BOT_USER_ID,
        login_id=OPEN_ALM_BOT_LOGIN_ID,
        email=OPEN_ALM_BOT_EMAIL,
        full_name=OPEN_ALM_BOT_NAME,
        display_name=OPEN_ALM_BOT_NAME,
        password_hash=hash_password(new_id()),
        status="system",
        login_blocked=True,
        must_change_password=False,
    )
    db.add(bot)
    db.flush()
    return bot


def deliver_notification_as_bot_dm(
    db: Session,
    *,
    notification: Notification,
    recipient: User,
    body: str,
    now: datetime | None = None,
) -> NotificationDmDeliveryResult:
    existing = db.get(NotificationDmDelivery, notification.id)
    if existing is not None:
        conversation = conversation_queries.conversation_for_publish(db, existing.conversation_id)
        message = db.get(DmMessage, existing.message_id)
        if conversation is not None and message is not None:
            return NotificationDmDeliveryResult(
                delivery=existing,
                conversation=conversation,
                message=message,
                created=False,
            )

    created_at = now or utcnow_naive()
    bot = ensure_notification_bot_user(db)
    conversation = _get_or_create_bot_direct_conversation(
        db,
        bot=bot,
        recipient=recipient,
        now=created_at,
    )
    draft = message_flow.compose_dm_message(
        db,
        conversation=conversation,
        sender=bot,
        body=body,
        attachment_ids=[],
        reply_to_message_id=None,
        now=created_at,
    )
    sent = message_delivery.persist_message_draft(db, draft=draft, commit=False)
    delivery = NotificationDmDelivery(
        notification_id=notification.id,
        user_id=recipient.id,
        conversation_id=conversation.id,
        message_id=sent.message.id,
        created_at=created_at,
    )
    db.add(delivery)
    db.flush()
    return NotificationDmDeliveryResult(
        delivery=delivery,
        conversation=conversation,
        message=sent.message,
        created=True,
    )


def _normalize_bot_user(bot: User) -> None:
    bot.login_id = OPEN_ALM_BOT_LOGIN_ID
    bot.email = OPEN_ALM_BOT_EMAIL
    bot.full_name = OPEN_ALM_BOT_NAME
    bot.display_name = OPEN_ALM_BOT_NAME
    bot.status = "system"
    bot.login_blocked = True
    bot.must_change_password = False


def _get_or_create_bot_direct_conversation(
    db: Session,
    *,
    bot: User,
    recipient: User,
    now: datetime,
) -> DmConversation:
    direct_key = conversation_lifecycle.direct_conversation_key(bot.id, recipient.id)
    conversation = db.scalar(
        select(DmConversation).where(DmConversation.direct_key == direct_key)
    )
    if conversation is None:
        draft = conversation_lifecycle.new_direct_conversation(
            current_user=bot,
            recipient=recipient,
            now=now,
        )
        draft.conversation.participants = draft.participants
        db.add(draft.conversation)
        db.add_all(draft.participants)
        db.flush()
        conversation = draft.conversation
    _restore_bot_direct_participants(
        db,
        conversation=conversation,
        bot=bot,
        recipient=recipient,
        now=now,
    )
    refreshed = conversation_queries.conversation_for_publish(db, conversation.id)
    return refreshed or conversation


def _restore_bot_direct_participants(
    db: Session,
    *,
    conversation: DmConversation,
    bot: User,
    recipient: User,
    now: datetime,
) -> None:
    latest_message = conversation_queries.latest_message(db, conversation.id)
    restored = [
        participant
        for participant in (
            conversation_lifecycle.restore_direct_participant_if_needed(
                conversation,
                user_id,
                joined_at=now,
                last_read_message_id=latest_message.id if latest_message is not None else None,
            )
            for user_id in (bot.id, recipient.id)
        )
        if participant is not None
    ]
    if restored:
        db.add_all(restored)
        db.flush()
