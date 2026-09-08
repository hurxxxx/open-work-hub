from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Protocol, TypeVar

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.dm import (
    conversation_queries,
    message_delivery,
    message_history,
    realtime_event_types,
    serialization,
)
from open_work_hub_api.domains.dm import (
    participants as participant_rules,
)
from open_work_hub_api.domains.dm.models import DmMessage
from open_work_hub_api.domains.dm.schemas import DmMessageItem, DmMessageListResponse


class DmMessageEventPublisher(Protocol):
    def publish_conversation_snapshot(
        self,
        conversation: Any,
        event_type: str,
        *,
        message: DmMessage | None = None,
    ) -> None: ...


_T = TypeVar("_T")
_RealtimePublication = Callable[[DmMessageEventPublisher], None]


@dataclass(frozen=True)
class _MutationResult(Generic[_T]):
    value: Callable[[], _T]
    publications: tuple[_RealtimePublication, ...] = ()


def _publish_mutation_result(
    result: _MutationResult[_T],
    *,
    events: DmMessageEventPublisher,
) -> _T:
    for publish in result.publications:
        publish(events)
    return result.value()


def list_dm_messages(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    limit: int,
    before: datetime | None,
) -> DmMessageListResponse:
    return DmMessageListResponse(
        items=message_history.list_messages(
            db,
            current_user=current_user,
            conversation_id=conversation_id,
            limit=limit,
            before=before,
        )
    )


def send_dm_message(
    db: Session,
    *,
    sender: User,
    conversation_id: str,
    body: str,
    attachment_ids: list[str],
    reply_to_message_id: str | None,
    events: DmMessageEventPublisher,
) -> DmMessageItem:
    result = message_delivery.send_message(
        db,
        sender=sender,
        conversation_id=conversation_id,
        body=body,
        attachment_ids=attachment_ids,
        reply_to_message_id=reply_to_message_id,
    )
    conversation = conversation_queries.require_user_conversation(
        db,
        current_user=sender,
        conversation_id=conversation_id,
    )
    message = next(
        (message for message in conversation.messages if message.id == result.message.id),
        result.message,
    )
    sender_participant = participant_rules.active_participant(conversation, sender.id)
    message_item = serialization.serialize_message(
        message,
        conversation=conversation,
        viewer_participant=sender_participant,
    )
    return _publish_mutation_result(
        _MutationResult(
            lambda: message_item,
            (
                lambda publisher: publisher.publish_conversation_snapshot(
                    conversation,
                    realtime_event_types.DM_MESSAGE_CREATED,
                    message=message,
                ),
            ),
        ),
        events=events,
    )
