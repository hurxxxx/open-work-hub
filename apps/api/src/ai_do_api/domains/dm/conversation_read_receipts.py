from __future__ import annotations

from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import User
from ai_do_api.domains.dm import conversation_queries, read_state, serialization
from ai_do_api.domains.dm.schemas import DmConversationItem


def mark_conversation_read(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
) -> DmConversationItem:
    conversation = conversation_queries.require_user_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
    )
    receipt = read_state.mark_conversation_read(
        db,
        conversation=conversation,
        user_id=current_user.id,
    )
    db.add(receipt.participant)
    db.add_all(receipt.notifications)
    db.commit()
    return serialization.serialize_conversation(db, conversation, current_user=current_user)
