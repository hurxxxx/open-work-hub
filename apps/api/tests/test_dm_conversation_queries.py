from datetime import timedelta

from fastapi import HTTPException
import pytest
from sqlalchemy.orm import Session

from dm_query_fixture import JOINED_AT, dm_db as dm_db
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.dm import conversation_queries
from open_work_hub_api.domains.dm.models import DmConversationParticipant, DmMessage


def test_require_user_conversation_loads_only_the_requested_active_membership(dm_db: Session):
    conversation = conversation_queries.require_user_conversation(
        dm_db, current_user=dm_db.get(User, "reader"), conversation_id="active"
    )
    assert conversation.id == "active"
    assert [p.user_id for p in conversation.participants] == ["reader"]


@pytest.mark.parametrize("conversation_id", ["missing", "left", "other"])
def test_require_user_conversation_hides_missing_left_and_nonmember_history(
    dm_db: Session, conversation_id: str
):
    with pytest.raises(HTTPException) as exc:
        conversation_queries.require_user_conversation(
            dm_db, current_user=dm_db.get(User, "reader"), conversation_id=conversation_id
        )
    assert exc.value.status_code == 404
    assert exc.value.detail.code == "dm.thread_not_found"


def test_list_user_conversations_filters_membership_orders_and_hydrates(dm_db: Session):
    conversations = conversation_queries.list_user_conversations(
        dm_db, current_user=dm_db.get(User, "reader")
    )
    assert [c.id for c in conversations] == ["empty", "active"]
    # Relationships promised by the reader must be usable after the query session closes.
    dm_db.expunge_all()
    active = conversations[1]
    assert active.participants[0].user.full_name == "reader"
    assert [m.body for m in active.messages] == [f"body-{i}" for i in range(1, 6)]
    assert active.messages[-1].sender.id == "peer"
    assert active.messages[-1].attachments == []


@pytest.mark.parametrize(
    "limit, before_seconds, expected",
    [
        (20, None, [2, 3, 4, 5]),
        (2, None, [4, 5]),
        (2, 4, [3, 4]),
        (20, 0, []),
    ],
)
def test_visible_messages_enforces_history_cursor_limit_and_order(
    dm_db: Session, limit: int, before_seconds: int | None, expected: list[int]
):
    messages = conversation_queries.visible_messages(
        dm_db,
        conversation_id="active",
        participant=dm_db.get(DmConversationParticipant, "active-participant"),
        limit=limit,
        before=JOINED_AT + timedelta(seconds=before_seconds)
        if before_seconds is not None
        else None,
    )
    assert [m.id for m in messages] == [f"message-{i}" for i in expected]


def test_latest_message_uses_conversation_and_sequence_and_handles_empty_history(dm_db: Session):
    # Clock skew must not make an older sequence the latest message.
    dm_db.get(DmMessage, "message-2").created_at = JOINED_AT + timedelta(days=1)
    dm_db.commit()
    latest = conversation_queries.latest_message(dm_db, "active")
    assert latest.id == "message-5"
    assert latest.body == "body-5"
    assert conversation_queries.latest_message(dm_db, "empty") is None
