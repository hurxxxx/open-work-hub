from __future__ import annotations

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User, utcnow_naive
from open_work_hub_api.domains.dm import (
    conversation_lifecycle,
    conversation_queries,
    participants as participant_rules,
    serialization,
)
from open_work_hub_api.domains.dm.schemas import DmConversationItem


def update_conversation(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    title: str | None,
) -> DmConversationItem:
    conversation = conversation_queries.require_user_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    participant_rules.ensure_group_conversation_manager(conversation, current_user.id)
    conversation.title = conversation_lifecycle.clean_conversation_title(title)
    conversation.updated_at = utcnow_naive()
    db.add(conversation)
    db.commit()
    return serialization.serialize_conversation(db, conversation, current_user=current_user)
