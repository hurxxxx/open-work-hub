from __future__ import annotations

from fastapi.testclient import TestClient

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.pms.models import Notification
from dev_accounts import auth_headers, dev_login


def test_notification_read_routes_update_unread_count(client: TestClient) -> None:
    recipient = dev_login(client, "delivery-hub-member")

    notification_id = _create_notification(
        user_id=recipient["user"]["id"],
        title="First notification",
    )

    read_response = client.patch(
        f"/api/v1/notifications/{notification_id}/read",
        headers=auth_headers(recipient["token"]),
    )
    assert read_response.status_code == 200, read_response.text
    assert read_response.json()["is_read"] is True

    _assert_unread_count(client, recipient_token=recipient["token"], count=0)

    _create_notification(
        user_id=recipient["user"]["id"],
        title="Second notification",
    )

    _read_all_notifications(client, recipient_token=recipient["token"])
    _assert_unread_count(client, recipient_token=recipient["token"], count=0)


def _create_notification(
    *,
    user_id: str,
    title: str,
) -> str:
    notification_id = new_id()
    with get_session_factory()() as db:
        db.add(
            Notification(
                id=notification_id,
                user_id=user_id,
                type="test_notification",
                title=title,
                body=title,
                reference_type="test",
                reference_id=None,
            )
        )
        db.commit()
    return notification_id


def _assert_unread_count(client: TestClient, *, recipient_token: str, count: int) -> None:
    unread_response = client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(recipient_token),
    )
    assert unread_response.status_code == 200, unread_response.text
    assert unread_response.json() == {"count": count}


def _read_all_notifications(client: TestClient, *, recipient_token: str) -> None:
    read_all_response = client.patch(
        "/api/v1/notifications/read-all",
        headers=auth_headers(recipient_token),
    )
    assert read_all_response.status_code == 204, read_all_response.text
