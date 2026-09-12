from datetime import timedelta

from fastapi import HTTPException
import pytest
from sqlalchemy.orm import Session

from dm_query_fixture import JOINED_AT, dm_db as dm_db
from open_work_hub_api.domains.dm import read_state
from open_work_hub_api.domains.dm.models import DmConversation, DmConversationParticipant


@pytest.mark.parametrize("marker, expected", [(None, 3), ("message-2", 2), ("message-5", 0)])
def test_unread_count_filters_conversation_sender_join_time_and_read_sequence(
    dm_db: Session, marker: str | None, expected: int
):
    participant = dm_db.get(DmConversationParticipant, "active-participant")
    participant.last_read_message_id = marker
    dm_db.commit()
    assert (
        read_state.unread_count(
            dm_db, conversation=dm_db.get(DmConversation, "active"), user_id="reader"
        )
        == expected
    )


def test_mark_read_persists_latest_visible_message_and_clears_unread_count(dm_db: Session):
    conversation = dm_db.get(DmConversation, "active")
    assert read_state.unread_count(dm_db, conversation=conversation, user_id="reader") == 3
    receipt = read_state.mark_conversation_read(dm_db, conversation=conversation, user_id="reader")
    assert receipt.latest_message.id == "message-5"
    assert receipt.participant.user_id == "reader"
    dm_db.commit()
    dm_db.expunge_all()
    assert (
        dm_db.get(DmConversationParticipant, "active-participant").last_read_message_id
        == "message-5"
    )
    assert (
        read_state.unread_count(
            dm_db, conversation=dm_db.get(DmConversation, "active"), user_id="reader"
        )
        == 0
    )


def test_mark_read_after_rejoining_cannot_restore_prejoin_history(dm_db: Session):
    participant = dm_db.get(DmConversationParticipant, "active-participant")
    participant.last_read_message_id = "message-2"
    participant.joined_at = JOINED_AT + timedelta(days=1)
    dm_db.commit()
    receipt = read_state.mark_conversation_read(
        dm_db, conversation=dm_db.get(DmConversation, "active"), user_id="reader"
    )
    assert receipt.latest_message is None
    dm_db.commit()
    dm_db.expire_all()
    assert participant.last_read_message_id is None


@pytest.mark.parametrize("conversation_id", ["left", "other"])
def test_read_state_requires_current_membership(dm_db: Session, conversation_id: str):
    conversation = dm_db.get(DmConversation, conversation_id)
    with pytest.raises(HTTPException) as exc:
        read_state.mark_conversation_read(dm_db, conversation=conversation, user_id="reader")
    assert exc.value.status_code == 404
    assert exc.value.detail.code == "dm.thread_not_found"
    assert read_state.unread_count(dm_db, conversation=conversation, user_id="reader") == 0
