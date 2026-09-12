"""Persist adversarial DM history in the migration-owned test database."""

from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_work_hub_api.core.model_registry import import_all_models
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.dm.models import (
    DmConversation,
    DmConversationParticipant,
    DmMessage,
)


JOINED_AT = datetime(2026, 5, 21, 12)


@pytest.fixture
def dm_db(application_postgres_dsn: str) -> Iterator[Session]:
    import_all_models()
    engine = create_engine(application_postgres_dsn)
    try:
        with Session(engine) as db:
            db.add_all(
                User(
                    id=user_id,
                    login_id=user_id,
                    email=f"{user_id}@example.test",
                    full_name=user_id,
                    password_hash="unused-query-fixture",
                )
                for user_id in ("reader", "peer", "outsider")
            )
            db.flush()
            # Insertion order differs from the requested updated_at order.
            for index, conversation_id in enumerate(("active", "empty", "left", "other")):
                db.add(
                    DmConversation(
                        id=conversation_id,
                        conversation_type="group",
                        created_by_id="peer",
                        updated_at=JOINED_AT + timedelta(days=index),
                        participants=[
                            DmConversationParticipant(
                                id=f"{conversation_id}-participant",
                                user_id="outsider" if conversation_id == "other" else "reader",
                                joined_at=JOINED_AT,
                                left_at=JOINED_AT if conversation_id == "left" else None,
                            ),
                        ],
                    )
                )
            db.flush()
            # Pre-join, exact join boundary, own messages, and a different conversation
            # must not be interchangeable with unread, visible messages from the peer.
            for sequence, seconds, sender in (
                (1, -1, "peer"),
                (2, 0, "peer"),
                (3, 2, "peer"),
                (4, 3, "reader"),
                (5, 4, "peer"),
            ):
                db.add(
                    DmMessage(
                        id=f"message-{sequence}",
                        conversation_id="active",
                        sequence=sequence,
                        sender_id=sender,
                        body=f"body-{sequence}",
                        created_at=JOINED_AT + timedelta(seconds=seconds),
                    )
                )
            db.add(
                DmMessage(
                    id="other-message",
                    conversation_id="other",
                    sequence=100,
                    sender_id="peer",
                    body="other conversation",
                    created_at=JOINED_AT + timedelta(seconds=2),
                )
            )
            db.commit()
            yield db
    finally:
        engine.dispose()
