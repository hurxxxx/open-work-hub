from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User, utcnow_naive
from open_work_hub_api.domains.dm import (
    conversation_lifecycle,
    conversation_queries,
    participants as participant_rules,
)
from open_work_hub_api.domains.dm.models import DmConversation


@dataclass(frozen=True)
class DmDirectConversationRestoration:
    conversation: DmConversation
    user_ids: tuple[str, str]
    joined_at: datetime
    last_read_message_id: str | None

    def participants_to_restore(self):
        return [
            participant
            for participant in (
                conversation_lifecycle.restore_direct_participant_if_needed(
                    self.conversation,
                    user_id,
                    joined_at=self.joined_at,
                    last_read_message_id=self.last_read_message_id,
                )
                for user_id in self.user_ids
            )
            if participant is not None
        ]


@dataclass(frozen=True)
class DmGroupParticipantAddition:
    conversation: DmConversation
    requested_user_ids: list[str]
    joined_at: datetime
    last_read_message_id: str | None

    def next_user_ids(self) -> list[str]:
        active_ids = {
            participant.user_id
            for participant in participant_rules.active_participants(self.conversation)
        }
        return conversation_lifecycle.unique_user_ids(
            user_id for user_id in self.requested_user_ids if user_id not in active_ids
        )

    def new_participants(self, user_ids: list[str]):
        return conversation_lifecycle.new_member_participants(
            conversation_id=self.conversation.id,
            user_ids=user_ids,
            joined_at=self.joined_at,
            last_read_message_id=self.last_read_message_id,
        )


@dataclass(frozen=True)
class DmParticipantDeparture:
    conversation: DmConversation
    participant: object
    departing_user_id: str
    left_at: datetime

    def apply(self) -> None:
        self.participant.left_at = self.left_at
        self.conversation.updated_at = self.left_at
        participant_rules.promote_owner_if_needed(
            self.conversation,
            departing_user_id=self.departing_user_id,
        )


class DmConversationMembership:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_or_create_direct_conversation(
        self,
        *,
        current_user: User,
        recipient_user_id: str,
    ) -> DmConversation:
        recipient = conversation_lifecycle.require_direct_recipient(
            self._db,
            current_user=current_user,
            recipient_user_id=recipient_user_id,
        )
        direct_key = conversation_lifecycle.direct_conversation_key(current_user.id, recipient.id)
        conversation = self._direct_conversation(direct_key)
        if conversation is not None:
            return self._restore_direct_conversation(
                conversation,
                current_user_id=current_user.id,
                recipient_user_id=recipient.id,
            )

        draft = conversation_lifecycle.new_direct_conversation(
            current_user=current_user,
            recipient=recipient,
            now=utcnow_naive(),
        )
        self._db.add(draft.conversation)
        self._db.add_all(draft.participants)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            existing = self._direct_conversation(direct_key)
            if existing is not None:
                return existing
            raise
        return draft.conversation

    def create_group_conversation(
        self,
        *,
        current_user: User,
        participant_user_ids: list[str],
        title: str | None,
    ) -> DmConversation:
        recipient_ids = conversation_lifecycle.group_recipient_ids(
            current_user_id=current_user.id,
            participant_user_ids=participant_user_ids,
        )

        users_by_id = conversation_lifecycle.active_users_by_id(self._db, recipient_ids)
        if len(users_by_id) != len(recipient_ids):
            raise localized_http_exception(status_code=404, code="dm.recipients_not_found")

        draft = conversation_lifecycle.new_group_conversation(
            current_user=current_user,
            recipient_user_ids=recipient_ids,
            title=title,
            now=utcnow_naive(),
        )
        self._db.add(draft.conversation)
        self._db.add_all(draft.participants)
        self._db.commit()
        return draft.conversation

    def add_participants(
        self,
        *,
        current_user: User,
        conversation_id: str,
        user_ids: list[str],
    ) -> DmConversation:
        conversation = self._required_conversation(
            current_user=current_user,
            conversation_id=conversation_id,
        )
        participant_rules.ensure_group_conversation(conversation)

        latest_message = conversation_queries.latest_message(self._db, conversation.id)
        addition = DmGroupParticipantAddition(
            conversation=conversation,
            requested_user_ids=user_ids,
            joined_at=utcnow_naive(),
            last_read_message_id=latest_message.id if latest_message is not None else None,
        )
        next_ids = addition.next_user_ids()
        if not next_ids:
            return conversation
        users_by_id = conversation_lifecycle.active_users_by_id(self._db, next_ids)
        if len(users_by_id) != len(next_ids):
            raise localized_http_exception(status_code=404, code="dm.recipients_not_found")

        self._db.add_all(addition.new_participants(next_ids))
        conversation.updated_at = addition.joined_at
        self._db.add(conversation)
        self._db.commit()
        return self._required_conversation(
            current_user=current_user,
            conversation_id=conversation.id,
        )

    def remove_participant(
        self,
        *,
        current_user: User,
        conversation_id: str,
        user_id: str,
    ) -> DmConversation:
        conversation = self._required_conversation(
            current_user=current_user,
            conversation_id=conversation_id,
        )
        participant_rules.ensure_group_conversation(conversation)
        if user_id == current_user.id:
            self.leave_conversation(current_user=current_user, conversation_id=conversation_id)
            return conversation
        participant_rules.ensure_conversation_manager(conversation, current_user.id)
        participant = participant_rules.active_participant(conversation, user_id)
        if participant is None:
            raise localized_http_exception(status_code=404, code="dm.participant_not_found")

        departure = DmParticipantDeparture(
            conversation=conversation,
            participant=participant,
            departing_user_id=user_id,
            left_at=utcnow_naive(),
        )
        departure.apply()
        self._db.add(participant)
        self._db.add(conversation)
        self._db.commit()
        return self._required_conversation(
            current_user=current_user,
            conversation_id=conversation.id,
        )

    def leave_conversation(
        self,
        *,
        current_user: User,
        conversation_id: str,
    ) -> None:
        conversation = self._required_conversation(
            current_user=current_user,
            conversation_id=conversation_id,
        )
        participant_rules.ensure_group_conversation(conversation)
        participant = participant_rules.active_participant(conversation, current_user.id)
        if participant is None:
            raise localized_http_exception(status_code=404, code="dm.thread_not_found")

        departure = DmParticipantDeparture(
            conversation=conversation,
            participant=participant,
            departing_user_id=current_user.id,
            left_at=utcnow_naive(),
        )
        departure.apply()
        self._db.add(participant)
        self._db.add(conversation)
        self._db.commit()

    def _direct_conversation(self, direct_key: str) -> DmConversation | None:
        return self._db.scalar(select(DmConversation).where(DmConversation.direct_key == direct_key))

    def _restore_direct_conversation(
        self,
        conversation: DmConversation,
        *,
        current_user_id: str,
        recipient_user_id: str,
    ) -> DmConversation:
        latest_message = conversation_queries.latest_message(self._db, conversation.id)
        restoration = DmDirectConversationRestoration(
            conversation=conversation,
            user_ids=(current_user_id, recipient_user_id),
            joined_at=utcnow_naive(),
            last_read_message_id=latest_message.id if latest_message is not None else None,
        )
        self._db.add_all(restoration.participants_to_restore())
        self._db.commit()
        return conversation

    def _required_conversation(
        self,
        *,
        current_user: User,
        conversation_id: str,
    ) -> DmConversation:
        return conversation_queries.require_user_conversation(
            self._db,
            current_user=current_user,
            conversation_id=conversation_id,
        )


def conversation_membership(db: Session) -> DmConversationMembership:
    return DmConversationMembership(db)


def get_or_create_direct_conversation(
    db: Session,
    *,
    current_user: User,
    recipient_user_id: str,
) -> DmConversation:
    return conversation_membership(db).get_or_create_direct_conversation(
        current_user=current_user,
        recipient_user_id=recipient_user_id,
    )


def create_group_conversation(
    db: Session,
    *,
    current_user: User,
    participant_user_ids: list[str],
    title: str | None,
) -> DmConversation:
    return conversation_membership(db).create_group_conversation(
        current_user=current_user,
        participant_user_ids=participant_user_ids,
        title=title,
    )


def add_participants(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    user_ids: list[str],
) -> DmConversation:
    return conversation_membership(db).add_participants(
        current_user=current_user,
        conversation_id=conversation_id,
        user_ids=user_ids,
    )


def remove_participant(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    user_id: str,
) -> DmConversation:
    return conversation_membership(db).remove_participant(
        current_user=current_user,
        conversation_id=conversation_id,
        user_id=user_id,
    )


def leave_conversation(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
) -> None:
    conversation_membership(db).leave_conversation(
        current_user=current_user,
        conversation_id=conversation_id,
    )
