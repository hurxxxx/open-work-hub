from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.notifications.read_service import (
    list_user_notifications,
    mark_all_read_and_publish,
    mark_one_read_and_publish,
    mark_all_read,
    mark_one_read,
)
from open_alm_api.domains.pms.models import Notification


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, Notification.__table__])
    return Session(engine)


def _add_user(session: Session, user_id: str) -> None:
    session.add(
        User(
            id=user_id,
            login_id=user_id,
            email=f"{user_id}@open-alm.local",
            full_name=user_id.title(),
            password_hash="hash",
            status="active",
        )
    )


def _add_notification(
    session: Session,
    *,
    notification_id: str,
    user_id: str,
    created_at: datetime,
    action_url: str = "/dm/conversations/conversation-1",
    is_read: bool = False,
    notification_type: str = "test_notification",
) -> None:
    session.add(
        Notification(
            id=notification_id,
            user_id=user_id,
            type=notification_type,
            title=f"Notification {notification_id}",
            body="Body",
            reference_type="conversation",
            reference_id="conversation-1",
            action_url=action_url,
            is_read=is_read,
            created_at=created_at,
        )
    )


def test_list_user_notifications_paginates_user_rows_in_created_order() -> None:
    session = _session()
    try:
        _add_user(session, "user-1")
        _add_user(session, "user-2")
        start = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        for index in range(3):
            _add_notification(
                session,
                notification_id=f"user-1-notification-{index}",
                user_id="user-1",
                created_at=start + timedelta(minutes=index),
            )
        _add_notification(
            session,
            notification_id="user-2-notification",
            user_id="user-2",
            created_at=start + timedelta(minutes=10),
        )
        session.commit()

        response = list_user_notifications(
            session,
            user_id="user-1",
            page=2,
            page_size=2,
        )

        assert response.total == 3
        assert response.page == 2
        assert response.page_size == 2
        assert [item.id for item in response.items] == ["user-1-notification-0"]
    finally:
        session.close()


def test_list_user_notifications_excludes_legacy_dm_message_rows() -> None:
    session = _session()
    try:
        _add_user(session, "user-1")
        created_at = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        _add_notification(
            session,
            notification_id="dm-notification",
            user_id="user-1",
            created_at=created_at,
            notification_type="dm_message",
        )
        _add_notification(
            session,
            notification_id="community-notification",
            user_id="user-1",
            created_at=created_at + timedelta(minutes=1),
            notification_type="community_comment",
        )
        session.commit()

        response = list_user_notifications(
            session,
            user_id="user-1",
            page=1,
            page_size=10,
        )

        assert response.total == 1
        assert [item.id for item in response.items] == ["community-notification"]
    finally:
        session.close()


def test_list_user_notifications_normalizes_legacy_pms_action_urls() -> None:
    session = _session()
    try:
        _add_user(session, "user-1")
        _add_notification(
            session,
            notification_id="pms-notification",
            user_id="user-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None),
            action_url="/tool/pms-list-list-1?workspace=hq&task=task-1",
        )
        session.commit()

        response = list_user_notifications(session, user_id="user-1", page=1, page_size=20)

        assert response.items[0].action_url == "/w/hq/pms/lists/list-1?task=task-1"
    finally:
        session.close()


def test_list_user_notifications_normalizes_duplicate_workspace_app_action_urls() -> None:
    session = _session()
    try:
        _add_user(session, "user-1")
        _add_notification(
            session,
            notification_id="legacy-issues-notification",
            user_id="user-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None),
            action_url="/w/hq/legacy-issues/legacy-issues/cooling-module",
        )
        session.commit()

        response = list_user_notifications(session, user_id="user-1", page=1, page_size=20)

        assert response.items[0].action_url == "/w/hq/legacy-issues/cooling-module"
    finally:
        session.close()


def test_mark_one_read_scopes_to_owner_and_returns_unread_count() -> None:
    session = _session()
    try:
        _add_user(session, "user-1")
        _add_user(session, "user-2")
        created_at = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        _add_notification(
            session,
            notification_id="notification-1",
            user_id="user-1",
            created_at=created_at,
        )
        _add_notification(
            session,
            notification_id="notification-2",
            user_id="user-1",
            created_at=created_at + timedelta(minutes=1),
        )
        _add_notification(
            session,
            notification_id="notification-3",
            user_id="user-2",
            created_at=created_at + timedelta(minutes=2),
        )
        session.commit()

        result = mark_one_read(
            session,
            user_id="user-1",
            notification_id="notification-1",
        )

        assert result.item.id == "notification-1"
        assert result.item.is_read is True
        assert result.unread_count == 1

        with pytest.raises(HTTPException) as exc_info:
            mark_one_read(
                session,
                user_id="user-2",
                notification_id="notification-2",
            )
        assert exc_info.value.status_code == 404
    finally:
        session.close()


def test_mark_one_read_and_publish_emits_read_event_with_serialized_notification() -> None:
    session = _session()
    events = _FakeNotificationPublisher()
    try:
        _add_user(session, "user-1")
        created_at = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        _add_notification(
            session,
            notification_id="notification-1",
            user_id="user-1",
            created_at=created_at,
        )
        _add_notification(
            session,
            notification_id="notification-2",
            user_id="user-1",
            created_at=created_at + timedelta(minutes=1),
        )
        session.commit()

        item = mark_one_read_and_publish(
            session,
            user_id="user-1",
            notification_id="notification-1",
            events=events,
        )

        assert item.id == "notification-1"
        assert events.published == [
            {
                "user_id": "user-1",
                "event_type": "notification.read",
                "notification": {
                    "id": "notification-1",
                    "type": "test_notification",
                    "title": "Notification notification-1",
                    "body": "Body",
                    "reference_type": "conversation",
                    "reference_id": "conversation-1",
                    "action_url": "/dm/conversations/conversation-1",
                    "is_read": True,
                    "created_at": created_at.isoformat(),
                },
                "unread_count": 1,
            }
        ]
    finally:
        session.close()


def test_mark_all_read_is_idempotent_and_scoped_to_user() -> None:
    session = _session()
    try:
        _add_user(session, "user-1")
        _add_user(session, "user-2")
        created_at = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        _add_notification(
            session,
            notification_id="notification-1",
            user_id="user-1",
            created_at=created_at,
        )
        _add_notification(
            session,
            notification_id="notification-2",
            user_id="user-1",
            created_at=created_at + timedelta(minutes=1),
            is_read=True,
        )
        _add_notification(
            session,
            notification_id="notification-3",
            user_id="user-2",
            created_at=created_at + timedelta(minutes=2),
        )
        session.commit()

        assert mark_all_read(session, user_id="user-1") == 0
        assert mark_all_read(session, user_id="user-1") == 0

        other = session.get(Notification, "notification-3")
        assert other is not None
        assert other.is_read is False
    finally:
        session.close()


def test_mark_all_read_and_publish_emits_read_all_event() -> None:
    session = _session()
    events = _FakeNotificationPublisher()
    try:
        _add_user(session, "user-1")
        _add_user(session, "user-2")
        created_at = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
        _add_notification(
            session,
            notification_id="notification-1",
            user_id="user-1",
            created_at=created_at,
        )
        _add_notification(
            session,
            notification_id="notification-2",
            user_id="user-2",
            created_at=created_at + timedelta(minutes=1),
        )
        session.commit()

        mark_all_read_and_publish(session, user_id="user-1", events=events)

        assert events.published == [
            {
                "user_id": "user-1",
                "event_type": "notifications.read_all",
                "notification": None,
                "unread_count": 0,
            }
        ]
        other = session.get(Notification, "notification-2")
        assert other is not None
        assert other.is_read is False
    finally:
        session.close()


class _FakeNotificationPublisher:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish_notification(
        self,
        user_id: str,
        *,
        event_type: str,
        notification: dict[str, Any] | None,
        unread_count: int,
    ) -> None:
        self.published.append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "notification": notification,
                "unread_count": unread_count,
            }
        )
