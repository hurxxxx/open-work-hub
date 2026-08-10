from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.dm import participants as participant_state
from open_work_hub_api.domains.dm.models import DmConversation, DmConversationParticipant


@dataclass(frozen=True)
class DmConversationDraft:
    conversation: DmConversation
    participants: list[DmConversationParticipant]


@dataclass(frozen=True)
class DmRecipientRules:
    minimum_group_recipient_count: int = 2

    def require_direct_recipient(
        self,
        db: Session,
        *,
        current_user: User,
        recipient_user_id: str,
    ) -> User:
        recipient = db.scalar(
            select(User).where(User.id == recipient_user_id, User.status == "active")
        )
        if recipient is None or recipient.id == current_user.id:
            raise localized_http_exception(status_code=404, code="dm.recipient_not_found")
        return recipient

    def active_users_by_id(self, db: Session, user_ids: list[str]) -> dict[str, User]:
        users = db.scalars(
            select(User).where(User.id.in_(user_ids), User.status == "active")
        )
        return {user.id: user for user in users}

    def direct_conversation_key(self, left_user_id: str, right_user_id: str) -> str:
        return ":".join(sorted((left_user_id, right_user_id)))

    def group_recipient_ids(
        self,
        *,
        current_user_id: str,
        participant_user_ids: Iterable[object],
    ) -> list[str]:
        recipient_ids = self.unique_user_ids(
            user_id for user_id in participant_user_ids if user_id != current_user_id
        )
        if len(recipient_ids) < self.minimum_group_recipient_count:
            raise localized_http_exception(status_code=422, code="dm.group_participants_required")
        return recipient_ids

    def unique_user_ids(self, user_ids: Iterable[object]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for user_id in user_ids:
            if not isinstance(user_id, str):
                continue
            normalized = user_id.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result


@dataclass(frozen=True)
class DmParticipantRules:
    member_role: str = "member"
    owner_role: str = "owner"

    def direct_participants(
        self,
        *,
        conversation_id: str,
        current_user_id: str,
        recipient_user_id: str,
        joined_at: datetime,
    ) -> list[DmConversationParticipant]:
        return [
            self.new_participant(
                conversation_id=conversation_id,
                user_id=current_user_id,
                role=self.member_role,
                joined_at=joined_at,
            ),
            self.new_participant(
                conversation_id=conversation_id,
                user_id=recipient_user_id,
                role=self.member_role,
                joined_at=joined_at,
            ),
        ]

    def group_participants(
        self,
        *,
        conversation_id: str,
        current_user_id: str,
        recipient_user_ids: list[str],
        joined_at: datetime,
    ) -> list[DmConversationParticipant]:
        participants = [
            self.new_participant(
                conversation_id=conversation_id,
                user_id=current_user_id,
                role=self.owner_role,
                joined_at=joined_at,
            )
        ]
        participants.extend(
            self.new_participant(
                conversation_id=conversation_id,
                user_id=user_id,
                role=self.member_role,
                joined_at=joined_at,
            )
            for user_id in recipient_user_ids
        )
        return participants

    def member_participants(
        self,
        *,
        conversation_id: str,
        user_ids: list[str],
        joined_at: datetime,
        last_read_message_id: str | None,
    ) -> list[DmConversationParticipant]:
        return [
            self.new_participant(
                conversation_id=conversation_id,
                user_id=user_id,
                role=self.member_role,
                joined_at=joined_at,
                last_read_message_id=last_read_message_id,
            )
            for user_id in user_ids
        ]

    def restore_direct_participant_if_needed(
        self,
        conversation: DmConversation,
        user_id: str,
        *,
        joined_at: datetime,
        last_read_message_id: str | None,
    ) -> DmConversationParticipant | None:
        if participant_state.active_participant(conversation, user_id) is not None:
            return None
        return self.new_participant(
            conversation_id=conversation.id,
            user_id=user_id,
            role=self.member_role,
            joined_at=joined_at,
            last_read_message_id=last_read_message_id,
        )

    def new_participant(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: str,
        joined_at: datetime,
        last_read_message_id: str | None = None,
    ) -> DmConversationParticipant:
        return DmConversationParticipant(
            id=new_id(),
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            joined_at=joined_at,
            last_read_message_id=last_read_message_id,
        )


@dataclass(frozen=True)
class DmConversationDraftFactory:
    recipient_rules: DmRecipientRules = field(default_factory=DmRecipientRules)
    participant_rules: DmParticipantRules = field(default_factory=DmParticipantRules)

    def new_direct(
        self,
        *,
        current_user: User,
        recipient: User,
        now: datetime,
    ) -> DmConversationDraft:
        conversation = DmConversation(
            id=new_id(),
            conversation_type="direct",
            direct_key=self.recipient_rules.direct_conversation_key(current_user.id, recipient.id),
            title=None,
            created_by_id=current_user.id,
            message_seq=0,
            created_at=now,
            updated_at=now,
        )
        return DmConversationDraft(
            conversation=conversation,
            participants=self.participant_rules.direct_participants(
                conversation_id=conversation.id,
                current_user_id=current_user.id,
                recipient_user_id=recipient.id,
                joined_at=now,
            ),
        )

    def new_group(
        self,
        *,
        current_user: User,
        recipient_user_ids: list[str],
        title: str | None,
        now: datetime,
    ) -> DmConversationDraft:
        conversation = DmConversation(
            id=new_id(),
            conversation_type="group",
            direct_key=None,
            title=self.clean_title(title),
            created_by_id=current_user.id,
            message_seq=0,
            created_at=now,
            updated_at=now,
        )
        return DmConversationDraft(
            conversation=conversation,
            participants=self.participant_rules.group_participants(
                conversation_id=conversation.id,
                current_user_id=current_user.id,
                recipient_user_ids=recipient_user_ids,
                joined_at=now,
            ),
        )

    def clean_title(self, title: str | None) -> str | None:
        return (title or "").strip() or None


_RECIPIENT_RULES = DmRecipientRules()
_PARTICIPANT_RULES = DmParticipantRules()
_DRAFT_FACTORY = DmConversationDraftFactory(
    recipient_rules=_RECIPIENT_RULES,
    participant_rules=_PARTICIPANT_RULES,
)


def require_direct_recipient(
    db: Session,
    *,
    current_user: User,
    recipient_user_id: str,
) -> User:
    return _RECIPIENT_RULES.require_direct_recipient(
        db,
        current_user=current_user,
        recipient_user_id=recipient_user_id,
    )


def active_users_by_id(db: Session, user_ids: list[str]) -> dict[str, User]:
    return _RECIPIENT_RULES.active_users_by_id(db, user_ids)


def direct_conversation_key(left_user_id: str, right_user_id: str) -> str:
    return _RECIPIENT_RULES.direct_conversation_key(left_user_id, right_user_id)


def group_recipient_ids(
    *,
    current_user_id: str,
    participant_user_ids: Iterable[object],
) -> list[str]:
    return _RECIPIENT_RULES.group_recipient_ids(
        current_user_id=current_user_id,
        participant_user_ids=participant_user_ids,
    )


def unique_user_ids(user_ids: Iterable[object]) -> list[str]:
    return _RECIPIENT_RULES.unique_user_ids(user_ids)


def clean_conversation_title(title: str | None) -> str | None:
    return _DRAFT_FACTORY.clean_title(title)


def new_direct_conversation(
    *,
    current_user: User,
    recipient: User,
    now: datetime,
) -> DmConversationDraft:
    return _DRAFT_FACTORY.new_direct(
        current_user=current_user,
        recipient=recipient,
        now=now,
    )


def new_group_conversation(
    *,
    current_user: User,
    recipient_user_ids: list[str],
    title: str | None,
    now: datetime,
) -> DmConversationDraft:
    return _DRAFT_FACTORY.new_group(
        current_user=current_user,
        recipient_user_ids=recipient_user_ids,
        title=title,
        now=now,
    )


def new_member_participants(
    *,
    conversation_id: str,
    user_ids: list[str],
    joined_at: datetime,
    last_read_message_id: str | None,
) -> list[DmConversationParticipant]:
    return _PARTICIPANT_RULES.member_participants(
        conversation_id=conversation_id,
        user_ids=user_ids,
        joined_at=joined_at,
        last_read_message_id=last_read_message_id,
    )


def restore_direct_participant_if_needed(
    conversation: DmConversation,
    user_id: str,
    *,
    joined_at: datetime,
    last_read_message_id: str | None,
) -> DmConversationParticipant | None:
    return _PARTICIPANT_RULES.restore_direct_participant_if_needed(
        conversation,
        user_id=user_id,
        joined_at=joined_at,
        last_read_message_id=last_read_message_id,
    )


def new_conversation_participant(
    *,
    conversation_id: str,
    user_id: str,
    role: str,
    joined_at: datetime,
    last_read_message_id: str | None = None,
) -> DmConversationParticipant:
    return _PARTICIPANT_RULES.new_participant(
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        joined_at=joined_at,
        last_read_message_id=last_read_message_id,
    )
