from __future__ import annotations

import base64

from fastapi.testclient import TestClient
import pytest

from ai_do_api.domains.dm.request_normalization import DM_MESSAGE_BODY_MAX_LENGTH
from dev_accounts import auth_headers, create_workspace_user_session, dev_login


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_dm_user_search_is_global_and_excludes_self(client: TestClient) -> None:
    sender = dev_login(client, "administrator")
    recipient = dev_login(client, "delivery-hub-member")

    response = client.get(
        "/api/v1/dm/users",
        headers=auth_headers(sender["token"]),
        params={"q": "Delivery Hub Member"},
    )

    assert response.status_code == 200, response.text
    items = response.json()
    assert any(item["id"] == recipient["user"]["id"] for item in items)
    assert all(item["id"] != sender["user"]["id"] for item in items)


def test_dm_user_search_can_be_scoped_to_an_accessible_workspace(
    client: TestClient,
) -> None:
    sender = create_workspace_user_session(
        client,
        workspace_key="dm-scope-alpha",
        login_id="dmscopealpha",
        email="dm-scope-alpha@example.com",
        full_name="DM Scope Alpha Sender",
    )
    peer = create_workspace_user_session(
        client,
        workspace_key="dm-scope-alpha",
        login_id="dmscopepeer",
        email="dm-scope-peer@example.com",
        full_name="DM Scope Alpha Peer",
    )
    outsider = create_workspace_user_session(
        client,
        workspace_key="dm-scope-beta",
        login_id="dmscopebeta",
        email="dm-scope-beta@example.com",
        full_name="DM Scope Beta Outsider",
    )

    response = client.get(
        "/api/v1/dm/users",
        headers=auth_headers(sender["token"]),
        params={
            "include_current": True,
            "q": "DM Scope",
            "workspace_key": "dm-scope-alpha",
        },
    )

    assert response.status_code == 200, response.text
    user_ids = {item["id"] for item in response.json()}
    assert sender["user"]["id"] in user_ids
    assert peer["user"]["id"] in user_ids
    assert outsider["user"]["id"] not in user_ids

    forbidden_response = client.get(
        "/api/v1/dm/users",
        headers=auth_headers(sender["token"]),
        params={"workspace_key": "dm-scope-beta"},
    )
    assert forbidden_response.status_code == 403, forbidden_response.text


def test_legacy_workspace_dm_user_search_is_removed(client: TestClient) -> None:
    sender = dev_login(client, "administrator")

    response = client.get(
        "/api/v1/workspaces/administrator/dm/users",
        headers=auth_headers(sender["token"]),
    )

    assert response.status_code == 404, response.text


def test_dm_request_schema_rejects_invalid_route_ids_and_shapes(client: TestClient) -> None:
    sender = dev_login(client, "administrator")
    first_recipient = dev_login(client, "delivery-hub-member")
    second_recipient = dev_login(client, "delivery-hub-admin")

    invalid_direct_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": "user/one"},
    )
    assert invalid_direct_response.status_code == 422, invalid_direct_response.text

    ambiguous_create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={
            "recipient_user_id": first_recipient["user"]["id"],
            "participant_user_ids": [second_recipient["user"]["id"]],
        },
    )
    assert ambiguous_create_response.status_code == 422, ambiguous_create_response.text

    missing_recipient_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"title": "No recipients"},
    )
    assert missing_recipient_response.status_code == 422, missing_recipient_response.text

    duplicate_group_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={
            "participant_user_ids": [
                first_recipient["user"]["id"],
                first_recipient["user"]["id"],
            ],
        },
    )
    assert duplicate_group_response.status_code == 422, duplicate_group_response.text

    valid_group_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={
            "title": "  Launch Room  ",
            "participant_user_ids": [
                f"  {first_recipient['user']['id']}  ",
                second_recipient["user"]["id"],
            ],
        },
    )
    assert valid_group_response.status_code == 201, valid_group_response.text
    conversation = valid_group_response.json()
    conversation_id = conversation["id"]
    assert conversation["title"] == "Launch Room"
    assert {item["user"]["id"] for item in conversation["participants"]} == {
        sender["user"]["id"],
        first_recipient["user"]["id"],
        second_recipient["user"]["id"],
    }

    invalid_participant_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/participants",
        headers=auth_headers(sender["token"]),
        json={"user_ids": ["user/one"]},
    )
    assert invalid_participant_response.status_code == 422, invalid_participant_response.text

    duplicate_participant_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/participants",
        headers=auth_headers(sender["token"]),
        json={
            "user_ids": [
                second_recipient["user"]["id"],
                second_recipient["user"]["id"],
            ],
        },
    )
    assert duplicate_participant_response.status_code == 422, duplicate_participant_response.text

    empty_message_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "   "},
    )
    assert empty_message_response.status_code == 422, empty_message_response.text

    oversized_message_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "x" * (DM_MESSAGE_BODY_MAX_LENGTH + 1)},
    )
    assert oversized_message_response.status_code == 422, oversized_message_response.text

    duplicate_attachment_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "hello", "attachment_ids": ["attachment_1", "attachment_1"]},
    )
    assert duplicate_attachment_response.status_code == 422, duplicate_attachment_response.text

    invalid_attachment_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "hello", "attachment_ids": ["attachment/1"]},
    )
    assert invalid_attachment_response.status_code == 422, invalid_attachment_response.text

    invalid_messages_path_response = client.get(
        "/api/v1/dm/conversations/bad.id/messages",
        headers=auth_headers(sender["token"]),
    )
    assert invalid_messages_path_response.status_code == 422, invalid_messages_path_response.text

    invalid_participant_path_response = client.delete(
        f"/api/v1/dm/conversations/{conversation_id}/participants/bad.id",
        headers=auth_headers(sender["token"]),
    )
    assert invalid_participant_path_response.status_code == 422, (
        invalid_participant_path_response.text
    )

    invalid_attachment_path_response = client.get(
        "/api/v1/dm/attachments/bad.id/download",
        headers=auth_headers(sender["token"]),
    )
    assert invalid_attachment_path_response.status_code == 422, (
        invalid_attachment_path_response.text
    )

    invalid_content_path_response = client.get(
        "/api/v1/dm/attachments/bad.id/content",
        params={"expires": 1, "signature": "sig", "disposition": "attachment"},
    )
    assert invalid_content_path_response.status_code == 422, invalid_content_path_response.text


def test_dm_conversations_messages_are_global_without_notification_rows(client: TestClient) -> None:
    sender = dev_login(client, "administrator")
    recipient = dev_login(client, "delivery-hub-member")
    outsider = dev_login(client, "delivery-hub-admin")

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert create_response.status_code == 201, create_response.text
    conversation = create_response.json()
    conversation_id = conversation["id"]
    assert conversation["conversation_type"] == "direct"
    assert conversation["other_user"]["id"] == recipient["user"]["id"]
    assert conversation["unread_count"] == 0

    duplicate_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert duplicate_response.status_code == 201, duplicate_response.text
    assert duplicate_response.json()["id"] == conversation_id

    outsider_response = client.get(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(outsider["token"]),
    )
    assert outsider_response.status_code == 404, outsider_response.text

    send_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "  Hello from HQ  "},
    )
    assert send_response.status_code == 200, send_response.text
    message = send_response.json()
    assert message["body"] == "Hello from HQ"
    assert message["conversation_id"] == conversation_id
    assert message["sequence"] == 1
    assert message["sender_id"] == sender["user"]["id"]

    recipient_messages_response = client.get(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(recipient["token"]),
    )
    assert recipient_messages_response.status_code == 200, recipient_messages_response.text
    assert [item["id"] for item in recipient_messages_response.json()["items"]] == [message["id"]]

    recipient_conversations_response = client.get(
        "/api/v1/dm/conversations",
        headers=auth_headers(recipient["token"]),
    )
    assert recipient_conversations_response.status_code == 200, (
        recipient_conversations_response.text
    )
    recipient_conversation = recipient_conversations_response.json()["items"][0]
    assert recipient_conversation["id"] == conversation_id
    assert recipient_conversation["last_message"]["body"] == "Hello from HQ"
    assert recipient_conversation["unread_count"] == 1

    unread_response = client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(recipient["token"]),
    )
    assert unread_response.status_code == 200, unread_response.text
    assert unread_response.json() == {"count": 0}

    notifications_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(recipient["token"]),
    )
    assert notifications_response.status_code == 200, notifications_response.text
    assert notifications_response.json()["items"] == []

    read_response = client.patch(
        f"/api/v1/dm/conversations/{conversation_id}/read",
        headers=auth_headers(recipient["token"]),
    )
    assert read_response.status_code == 200, read_response.text
    assert read_response.json()["unread_count"] == 0
    assert read_response.json()["last_read_message_id"] == message["id"]

    unread_after_read_response = client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(recipient["token"]),
    )
    assert unread_after_read_response.status_code == 200, unread_after_read_response.text
    assert unread_after_read_response.json() == {"count": 0}

    notifications_after_read_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(recipient["token"]),
    )
    assert notifications_after_read_response.status_code == 200, (
        notifications_after_read_response.text
    )
    assert notifications_after_read_response.json()["items"] == []


def test_dm_message_accepts_maximum_body_length(client: TestClient) -> None:
    sender = dev_login(client, "administrator")
    recipient = dev_login(client, "delivery-hub-member")

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert create_response.status_code == 201, create_response.text
    conversation_id = create_response.json()["id"]

    body = "x" * DM_MESSAGE_BODY_MAX_LENGTH
    send_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": body},
    )

    assert send_response.status_code == 200, send_response.text
    assert send_response.json()["body"] == body


@pytest.mark.external_integration("minio")
def test_dm_message_attachments_are_private_to_participants(client: TestClient) -> None:
    sender = dev_login(client, "administrator")
    recipient = dev_login(client, "delivery-hub-member")
    outsider = dev_login(client, "delivery-hub-admin")

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert create_response.status_code == 201, create_response.text
    conversation_id = create_response.json()["id"]

    upload_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/attachments",
        headers=auth_headers(sender["token"]),
        files={"file": ("clipboard.png", PNG_BYTES, "image/png")},
    )
    assert upload_response.status_code == 201, upload_response.text
    attachment = upload_response.json()
    assert attachment["filename"] == "clipboard.png"
    assert attachment["content_type"] == "image/png"
    assert attachment["size_bytes"] == len(PNG_BYTES)
    assert attachment["is_image"] is True
    assert attachment["message_id"] is None
    assert attachment["download_url"].startswith(
        f"/api/v1/dm/attachments/{attachment['id']}/content?"
    )
    assert attachment["preview_url"].startswith(
        f"/api/v1/dm/attachments/{attachment['id']}/content?"
    )

    outsider_preview_response = client.get(
        f"/api/v1/dm/attachments/{attachment['id']}/preview",
        headers=auth_headers(outsider["token"]),
    )
    assert outsider_preview_response.status_code == 404, outsider_preview_response.text

    send_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "", "attachment_ids": [attachment["id"]]},
    )
    assert send_response.status_code == 200, send_response.text
    message = send_response.json()
    assert message["body"] == ""
    assert len(message["attachments"]) == 1
    assert message["attachments"][0]["id"] == attachment["id"]
    assert message["attachments"][0]["message_id"] == message["id"]

    recipient_messages_response = client.get(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(recipient["token"]),
    )
    assert recipient_messages_response.status_code == 200, recipient_messages_response.text
    recipient_attachment = recipient_messages_response.json()["items"][0]["attachments"][0]
    assert recipient_attachment["id"] == attachment["id"]

    preview_url_response = client.get(
        f"/api/v1/dm/attachments/{attachment['id']}/preview",
        headers=auth_headers(recipient["token"]),
    )
    assert preview_url_response.status_code == 200, preview_url_response.text
    content_response = client.get(preview_url_response.json()["url"])
    assert content_response.status_code == 200, content_response.text
    assert content_response.content == PNG_BYTES
    assert content_response.headers["content-type"].startswith("image/png")
    assert content_response.headers["content-disposition"].startswith("inline;")


def test_dm_spoofed_image_attachment_is_not_previewable(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    sender = dev_login(client, "administrator")
    recipient = dev_login(client, "delivery-hub-member")

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert create_response.status_code == 201, create_response.text
    conversation_id = create_response.json()["id"]

    upload_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/attachments",
        headers=auth_headers(sender["token"]),
        files={"file": ("spoof.png", b"not really an image", "image/png")},
    )
    assert upload_response.status_code == 201, upload_response.text
    attachment = upload_response.json()
    assert attachment["content_type"] == "application/octet-stream"
    assert attachment["is_image"] is False
    assert attachment["preview_url"] is None

    preview_response = client.get(
        f"/api/v1/dm/attachments/{attachment['id']}/preview",
        headers=auth_headers(recipient["token"]),
    )
    assert preview_response.status_code == 415, preview_response.text


def test_dm_file_attachment_download_uses_attachment_disposition(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    sender = dev_login(client, "administrator")
    recipient = dev_login(client, "delivery-hub-member")

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert create_response.status_code == 201, create_response.text
    conversation_id = create_response.json()["id"]

    upload_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/attachments",
        headers=auth_headers(sender["token"]),
        files={"file": ("notes.txt", b"plain notes", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    attachment = upload_response.json()
    assert attachment["is_image"] is False
    assert attachment["preview_url"] is None

    send_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "See file", "attachment_ids": [attachment["id"]]},
    )
    assert send_response.status_code == 200, send_response.text

    preview_response = client.get(
        f"/api/v1/dm/attachments/{attachment['id']}/preview",
        headers=auth_headers(recipient["token"]),
    )
    assert preview_response.status_code == 415, preview_response.text

    download_url_response = client.get(
        f"/api/v1/dm/attachments/{attachment['id']}/download",
        headers=auth_headers(recipient["token"]),
    )
    assert download_url_response.status_code == 200, download_url_response.text
    content_response = client.get(download_url_response.json()["url"])
    assert content_response.status_code == 200, content_response.text
    assert content_response.content == b"plain notes"
    assert content_response.headers["content-type"].startswith("text/plain")
    assert content_response.headers["content-disposition"].startswith("attachment;")
    assert "notes.txt" in content_response.headers["content-disposition"]


def test_dm_websocket_receives_message_created_event(client: TestClient) -> None:
    sender = dev_login(client, "administrator")
    recipient = dev_login(client, "delivery-hub-member")

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert create_response.status_code == 201, create_response.text
    conversation_id = create_response.json()["id"]

    with client.websocket_connect("/api/v1/realtime/ws") as websocket:
        websocket.send_json({"type": "auth", "token": recipient["token"]})
        assert websocket.receive_json() == {"type": "realtime.auth.ok", "data": {}}
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "notification.snapshot"
        assert snapshot["data"]["unread_count"] == 0

        send_response = client.post(
            f"/api/v1/dm/conversations/{conversation_id}/messages",
            headers=auth_headers(sender["token"]),
            json={"body": "Live sync"},
        )
        assert send_response.status_code == 200, send_response.text

        event = websocket.receive_json()
        assert event["type"] == "dm.message.created"
        assert event["data"]["message"]["body"] == "Live sync"
        assert event["data"]["conversation"]["id"] == conversation_id
        assert event["data"]["conversation"]["unread_count"] == 1
        websocket.close()


def test_group_dm_messages_update_dm_unread_without_global_notifications(
    client: TestClient,
) -> None:
    sender = dev_login(client, "administrator")
    first_recipient = dev_login(client, "delivery-hub-member")
    second_recipient = dev_login(client, "delivery-hub-admin")

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={
            "title": "Launch Room",
            "participant_user_ids": [
                first_recipient["user"]["id"],
                second_recipient["user"]["id"],
            ],
        },
    )
    assert create_response.status_code == 201, create_response.text
    conversation = create_response.json()
    conversation_id = conversation["id"]
    assert conversation["conversation_type"] == "group"
    assert conversation["title"] == "Launch Room"
    assert conversation["other_user"] is None
    assert conversation["participant_count"] == 3
    assert {item["user"]["id"] for item in conversation["participants"]} == {
        sender["user"]["id"],
        first_recipient["user"]["id"],
        second_recipient["user"]["id"],
    }

    send_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "Group hello"},
    )
    assert send_response.status_code == 200, send_response.text
    message = send_response.json()
    assert message["body"] == "Group hello"

    for recipient in (first_recipient, second_recipient):
        unread_response = client.get(
            "/api/v1/notifications/unread-count",
            headers=auth_headers(recipient["token"]),
        )
        assert unread_response.status_code == 200, unread_response.text
        assert unread_response.json() == {"count": 0}

        conversations_response = client.get(
            "/api/v1/dm/conversations",
            headers=auth_headers(recipient["token"]),
        )
        assert conversations_response.status_code == 200, conversations_response.text
        recipient_conversation = conversations_response.json()["items"][0]
        assert recipient_conversation["id"] == conversation_id
        assert recipient_conversation["conversation_type"] == "group"
        assert recipient_conversation["unread_count"] == 1

        notifications_response = client.get(
            "/api/v1/notifications",
            headers=auth_headers(recipient["token"]),
        )
        assert notifications_response.status_code == 200, notifications_response.text
        assert notifications_response.json()["items"] == []


def test_legacy_dm_threads_endpoint_creates_group_conversation(client: TestClient) -> None:
    sender = dev_login(client, "administrator")
    first_recipient = dev_login(client, "delivery-hub-member")
    second_recipient = dev_login(client, "delivery-hub-admin")

    create_response = client.post(
        "/api/v1/dm/threads",
        headers=auth_headers(sender["token"]),
        json={
            "title": "Legacy Group",
            "participant_user_ids": [
                first_recipient["user"]["id"],
                second_recipient["user"]["id"],
            ],
        },
    )

    assert create_response.status_code == 201, create_response.text
    conversation = create_response.json()
    assert conversation["conversation_type"] == "group"
    assert conversation["thread_type"] == "group"
    assert conversation["title"] == "Legacy Group"
    assert conversation["participant_count"] == 3
    assert {item["user"]["id"] for item in conversation["participants"]} == {
        sender["user"]["id"],
        first_recipient["user"]["id"],
        second_recipient["user"]["id"],
    }


def test_group_dm_management_tracks_membership_lifecycle(client: TestClient) -> None:
    owner = dev_login(client, "administrator")
    member = dev_login(client, "delivery-hub-member")
    removable = dev_login(client, "delivery-hub-admin")
    added = create_workspace_user_session(
        client,
        workspace_key="administrator",
        login_id="dmadded",
        email="dm-added@ai-do.local",
        full_name="DM Added",
    )
    member_added = create_workspace_user_session(
        client,
        workspace_key="administrator",
        login_id="dmmemberadded",
        email="dm-member-added@ai-do.local",
        full_name="DM Member Added",
    )

    create_response = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(owner["token"]),
        json={
            "title": "Original Room",
            "participant_user_ids": [member["user"]["id"], removable["user"]["id"]],
        },
    )
    assert create_response.status_code == 201, create_response.text
    conversation_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/dm/conversations/{conversation_id}",
        headers=auth_headers(owner["token"]),
        json={"title": "Updated Room"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["title"] == "Updated Room"

    member_update_response = client.patch(
        f"/api/v1/dm/conversations/{conversation_id}",
        headers=auth_headers(member["token"]),
        json={"title": "Member Rename"},
    )
    assert member_update_response.status_code == 403, member_update_response.text

    send_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(owner["token"]),
        json={"body": "Before add"},
    )
    assert send_response.status_code == 200, send_response.text
    first_message_id = send_response.json()["id"]

    add_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/participants",
        headers=auth_headers(owner["token"]),
        json={"user_ids": [added["user"]["id"]]},
    )
    assert add_response.status_code == 200, add_response.text
    added_snapshot = add_response.json()
    assert added_snapshot["participant_count"] == 4
    assert {item["user"]["id"] for item in added_snapshot["participants"]} == {
        owner["user"]["id"],
        member["user"]["id"],
        removable["user"]["id"],
        added["user"]["id"],
    }

    added_conversations_response = client.get(
        "/api/v1/dm/conversations",
        headers=auth_headers(added["token"]),
    )
    assert added_conversations_response.status_code == 200, added_conversations_response.text
    added_conversation = added_conversations_response.json()["items"][0]
    assert added_conversation["id"] == conversation_id
    assert added_conversation["unread_count"] == 0
    assert added_conversation["last_read_message_id"] == first_message_id

    reply_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(owner["token"]),
        json={
            "body": "Reply after add",
            "reply_to_message_id": first_message_id,
        },
    )
    assert reply_response.status_code == 200, reply_response.text
    reply_message = reply_response.json()
    assert reply_message["reply_to"]["id"] == first_message_id

    added_messages_response = client.get(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(added["token"]),
    )
    assert added_messages_response.status_code == 200, added_messages_response.text
    added_messages = added_messages_response.json()["items"]
    assert [item["id"] for item in added_messages] == [reply_message["id"]]
    assert added_messages[0]["reply_to"] is None

    member_add_response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/participants",
        headers=auth_headers(member["token"]),
        json={"user_ids": [member_added["user"]["id"]]},
    )
    assert member_add_response.status_code == 200, member_add_response.text
    assert member_add_response.json()["participant_count"] == 5

    remove_response = client.delete(
        f"/api/v1/dm/conversations/{conversation_id}/participants/{removable['user']['id']}",
        headers=auth_headers(owner["token"]),
    )
    assert remove_response.status_code == 200, remove_response.text
    assert remove_response.json()["participant_count"] == 4

    removed_conversations_response = client.get(
        "/api/v1/dm/conversations",
        headers=auth_headers(removable["token"]),
    )
    assert removed_conversations_response.status_code == 200, removed_conversations_response.text
    assert removed_conversations_response.json()["items"] == []

    leave_response = client.delete(
        f"/api/v1/dm/conversations/{conversation_id}/participants/me",
        headers=auth_headers(owner["token"]),
    )
    assert leave_response.status_code == 204, leave_response.text

    member_conversations_response = client.get(
        "/api/v1/dm/conversations",
        headers=auth_headers(member["token"]),
    )
    assert member_conversations_response.status_code == 200, member_conversations_response.text
    member_conversation = member_conversations_response.json()["items"][0]
    assert member_conversation["participant_count"] == 3
    assert any(
        item["user"]["id"] == member["user"]["id"] and item["role"] == "owner"
        for item in member_conversation["participants"]
    )
