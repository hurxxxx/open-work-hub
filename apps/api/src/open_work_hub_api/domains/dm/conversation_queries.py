from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.dm import participants as participant_rules
from open_work_hub_api.domains.dm.models import DmConversation, DmConversationParticipant, DmMessage


class DmConversationReader:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_user_conversations(self, *, current_user: User) -> list[DmConversation]:
        conversation_ids = select(DmConversationParticipant.conversation_id).where(
            DmConversationParticipant.user_id == current_user.id,
            DmConversationParticipant.left_at.is_(None),
        )
        return list(
            self._db.scalars(
                hydrated_conversation_query()
                .where(DmConversation.id.in_(conversation_ids))
                .order_by(DmConversation.updated_at.desc())
            )
        )

    def require_user_conversation(
        self,
        *,
        current_user: User,
        conversation_id: str,
    ) -> DmConversation:
        conversation = self.conversation_for_publish(conversation_id)
        if (
            conversation is None
            or participant_rules.active_participant(conversation, current_user.id) is None
        ):
            raise localized_http_exception(status_code=404, code="dm.thread_not_found")
        return conversation

    def conversation_for_publish(self, conversation_id: str) -> DmConversation | None:
        return self._db.scalar(
            hydrated_conversation_query().where(DmConversation.id == conversation_id)
        )

    def visible_messages(
        self,
        *,
        conversation_id: str,
        participant: DmConversationParticipant,
        limit: int,
        before: datetime | None,
    ) -> list[DmMessage]:
        query = (
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
            .limit(limit)
        )
        if before is not None:
            query = query.where(DmMessage.created_at < before)
        rows = list(self._db.scalars(query))
        rows.reverse()
        return rows

    def latest_message(self, conversation_id: str) -> DmMessage | None:
        return self._db.scalar(
            select(DmMessage)
            .where(DmMessage.conversation_id == conversation_id)
            .options(selectinload(DmMessage.sender))
            .options(selectinload(DmMessage.attachments))
            .options(selectinload(DmMessage.reply_to).selectinload(DmMessage.sender))
            .options(selectinload(DmMessage.reply_to).selectinload(DmMessage.attachments))
            .order_by(DmMessage.sequence.desc())
            .limit(1)
        )


def conversation_reader(db: Session) -> DmConversationReader:
    return DmConversationReader(db)


def list_user_conversations(db: Session, *, current_user: User) -> list[DmConversation]:
    return conversation_reader(db).list_user_conversations(current_user=current_user)


def require_user_conversation(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
) -> DmConversation:
    return conversation_reader(db).require_user_conversation(
        current_user=current_user,
        conversation_id=conversation_id,
    )


def conversation_for_publish(db: Session, conversation_id: str) -> DmConversation | None:
    return conversation_reader(db).conversation_for_publish(conversation_id)


def visible_messages(
    db: Session,
    *,
    conversation_id: str,
    participant: DmConversationParticipant,
    limit: int,
    before: datetime | None,
) -> list[DmMessage]:
    return conversation_reader(db).visible_messages(
        conversation_id=conversation_id,
        participant=participant,
        limit=limit,
        before=before,
    )


def latest_message(db: Session, conversation_id: str) -> DmMessage | None:
    return conversation_reader(db).latest_message(conversation_id)


def hydrated_conversation_query():
    return select(DmConversation).options(
        selectinload(DmConversation.participants).selectinload(DmConversationParticipant.user),
        selectinload(DmConversation.participants).selectinload(
            DmConversationParticipant.last_read_message
        ),
        selectinload(DmConversation.messages).selectinload(DmMessage.sender),
        selectinload(DmConversation.messages).selectinload(DmMessage.attachments),
        selectinload(DmConversation.messages)
        .selectinload(DmMessage.reply_to)
        .selectinload(DmMessage.sender),
        selectinload(DmConversation.messages)
        .selectinload(DmMessage.reply_to)
        .selectinload(DmMessage.attachments),
    )
