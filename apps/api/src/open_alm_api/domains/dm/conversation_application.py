from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.dm import (
    conversation_membership,
    conversation_queries,
    conversation_read_receipts,
    conversation_settings,
    notification_events,
    participants,
    realtime_event_types,
    serialization,
)
from open_alm_api.domains.dm.models import DmConversation
from open_alm_api.domains.dm.schemas import DmConversationItem, DmConversationListResponse


class DmConversationEventPublisher(notification_events.DmNotificationEventPublisher, Protocol):
    def publish_conversation_snapshot(
        self,
        conversation: DmConversation,
        event_type: str,
    ) -> None: ...

    def publish_conversation_for_user(
        self,
        conversation: DmConversation,
        user_id: str,
        event_type: str,
    ) -> None: ...

    def publish_conversation_removed(self, user_id: str, *, conversation_id: str) -> None: ...

    def publish_conversation_read(
        self,
        reader_user_id: str,
        *,
        conversation_id: str,
        conversation: DmConversation,
    ) -> None: ...


_T = TypeVar("_T")
_RealtimePublication = Callable[[DmConversationEventPublisher], None]


@dataclass(frozen=True)
class _MutationResult(Generic[_T]):
    value: Callable[[], _T]
    publications: tuple[_RealtimePublication, ...] = ()


def _publish_mutation_result(
    result: _MutationResult[_T],
    *,
    events: DmConversationEventPublisher,
) -> _T:
    for publish in result.publications:
        publish(events)
    return result.value()


def list_dm_conversations(
    db: Session,
    *,
    current_user: User,
) -> DmConversationListResponse:
    conversations = conversation_queries.list_user_conversations(db, current_user=current_user)
    return DmConversationListResponse(
        items=[
            serialization.serialize_conversation(db, conversation, current_user=current_user)
            for conversation in conversations
        ]
    )


def create_dm_conversation(
    db: Session,
    *,
    current_user: User,
    recipient_user_id: str | None,
    participant_user_ids: list[str],
    title: str | None,
    events: DmConversationEventPublisher,
) -> DmConversationItem:
    if participant_user_ids:
        conversation = conversation_membership.create_group_conversation(
            db,
            current_user=current_user,
            participant_user_ids=participant_user_ids,
            title=title,
        )
    elif recipient_user_id:
        conversation = conversation_membership.get_or_create_direct_conversation(
            db,
            current_user=current_user,
            recipient_user_id=recipient_user_id,
        )
    else:
        raise localized_http_exception(status_code=404, code="dm.recipient_not_found")

    conversation = conversation_queries.require_user_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation.id,
    )
    return _publish_mutation_result(
        _MutationResult(
            lambda: serialization.serialize_conversation(
                db, conversation, current_user=current_user
            ),
            (
                lambda publisher: publisher.publish_conversation_snapshot(
                    conversation,
                    realtime_event_types.DM_CONVERSATION_CREATED,
                ),
            ),
        ),
        events=events,
    )


def update_dm_conversation(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    title: str | None,
    events: DmConversationEventPublisher,
) -> DmConversationItem:
    item = conversation_settings.update_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        title=title,
    )
    conversation = conversation_queries.require_user_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    return _publish_mutation_result(
        _MutationResult(
            lambda: item,
            (
                lambda publisher: publisher.publish_conversation_snapshot(
                    conversation,
                    realtime_event_types.DM_CONVERSATION_UPDATED,
                ),
            ),
        ),
        events=events,
    )


def add_dm_conversation_participants(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    user_ids: list[str],
    events: DmConversationEventPublisher,
) -> DmConversationItem:
    conversation = conversation_membership.add_participants(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        user_ids=user_ids,
    )
    return _publish_mutation_result(
        _MutationResult(
            lambda: serialization.serialize_conversation(
                db, conversation, current_user=current_user
            ),
            (
                lambda publisher: publisher.publish_conversation_snapshot(
                    conversation,
                    realtime_event_types.DM_CONVERSATION_UPDATED,
                ),
            ),
        ),
        events=events,
    )


def leave_dm_conversation(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    events: DmConversationEventPublisher,
) -> None:
    conversation = conversation_queries.require_user_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    remaining_user_ids = [
        user.id
        for user in participants.active_participant_users(conversation)
        if user.id != current_user.id
    ]
    conversation_membership.leave_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    refreshed = conversation_queries.conversation_for_publish(db, conversation_id)
    publications: list[_RealtimePublication] = []
    if refreshed is not None:
        publications.extend(
            (
                lambda publisher, user_id=user_id: publisher.publish_conversation_for_user(
                    refreshed,
                    user_id,
                    realtime_event_types.DM_CONVERSATION_UPDATED,
                )
            )
            for user_id in remaining_user_ids
        )
    publications.append(
        lambda publisher: publisher.publish_conversation_removed(
            current_user.id,
            conversation_id=conversation_id,
        )
    )
    _publish_mutation_result(
        _MutationResult(lambda: None, tuple(publications)),
        events=events,
    )


def remove_dm_conversation_participant(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    user_id: str,
    events: DmConversationEventPublisher,
) -> DmConversationItem:
    conversation = conversation_membership.remove_participant(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    return _publish_mutation_result(
        _MutationResult(
            lambda: serialization.serialize_conversation(
                db, conversation, current_user=current_user
            ),
            (
                lambda publisher: publisher.publish_conversation_snapshot(
                    conversation,
                    realtime_event_types.DM_CONVERSATION_UPDATED,
                ),
                lambda publisher: publisher.publish_conversation_removed(
                    user_id,
                    conversation_id=conversation_id,
                ),
            ),
        ),
        events=events,
    )


def mark_dm_conversation_read(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    events: DmConversationEventPublisher,
) -> DmConversationItem:
    conversation_item = conversation_read_receipts.mark_conversation_read(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    conversation = conversation_queries.conversation_for_publish(db, conversation_id)
    publications: list[_RealtimePublication] = [
        lambda publisher: notification_events.publish_read_notification(
            db,
            user_id=current_user.id,
            events=publisher,
        ),
    ]
    if conversation is not None:
        publications.insert(
            0,
            lambda publisher: publisher.publish_conversation_read(
                current_user.id,
                conversation_id=conversation_id,
                conversation=conversation,
            ),
        )
    return _publish_mutation_result(
        _MutationResult(
            lambda: conversation_item,
            tuple(publications),
        ),
        events=events,
    )
