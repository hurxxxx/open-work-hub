from __future__ import annotations

from fastapi.testclient import TestClient

from open_work_hub_api.domains.community.service import DEFAULT_CHANNEL_KEY
from dev_accounts import auth_headers, dev_login


def test_notification_read_routes_update_unread_count(client: TestClient) -> None:
    recipient = dev_login(client, "administrator")
    commenter = dev_login(client, "delivery-hub-member")

    notification_id = _create_notification(
        client,
        author_token=recipient["token"],
        commenter_token=commenter["token"],
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
        client,
        author_token=recipient["token"],
        commenter_token=commenter["token"],
        title="Second notification",
    )

    _read_all_notifications(client, recipient_token=recipient["token"])
    _assert_unread_count(client, recipient_token=recipient["token"], count=0)


def _create_notification(
    client: TestClient,
    *,
    author_token: str,
    commenter_token: str,
    title: str,
) -> str:
    post_response = client.post(
        f"/api/v1/community/channels/{DEFAULT_CHANNEL_KEY}/posts",
        headers=auth_headers(author_token),
        json={
            "title": title,
            "body": title,
            "is_anonymous": False,
            "is_secret": False,
        },
    )
    assert post_response.status_code == 201, post_response.text
    post_id = post_response.json()["id"]

    comment_response = client.post(
        f"/api/v1/community/posts/{post_id}/comments",
        headers=auth_headers(commenter_token),
        json={"body": f"Comment on {title}", "is_anonymous": False},
    )
    assert comment_response.status_code == 201, comment_response.text

    notifications_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(author_token),
    )
    assert notifications_response.status_code == 200, notifications_response.text
    notification = next(
        item for item in notifications_response.json()["items"] if item["source_id"] == post_id
    )
    return notification["id"]


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
