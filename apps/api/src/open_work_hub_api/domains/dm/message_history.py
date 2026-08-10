from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.dm import (
    conversation_queries,
    participants as participant_rules,
    serialization,
)
from open_work_hub_api.domains.dm.schemas import DmMessageItem


class DmMessageHistory:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_messages(
        self,
        *,
        current_user: User,
        conversation_id: str,
        limit: int,
        before: datetime | None,
    ) -> list[DmMessageItem]:
        conversation = conversation_queries.require_user_conversation(
            self._db,
            current_user=current_user,
            conversation_id=conversation_id,
        )
        participant = participant_rules.active_participant(conversation, current_user.id)
        if participant is None:
            raise localized_http_exception(status_code=404, code="dm.thread_not_found")
        rows = conversation_queries.visible_messages(
            self._db,
            conversation_id=conversation_id,
            participant=participant,
            limit=limit,
            before=before,
        )
        return [
            serialization.serialize_message(
                row,
                conversation=conversation,
                viewer_participant=participant,
            )
            for row in rows
        ]


def message_history(db: Session) -> DmMessageHistory:
    return DmMessageHistory(db)


def list_messages(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    limit: int,
    before: datetime | None,
) -> list[DmMessageItem]:
    return message_history(db).list_messages(
        current_user=current_user,
        conversation_id=conversation_id,
        limit=limit,
        before=before,
    )
