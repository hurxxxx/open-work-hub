from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from dev_accounts import auth_headers, content_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import AuthSession, User
from open_work_hub_api.domains.dm.models import DmConversationParticipant, DmMessageAttachment
from test_dm import PNG_BYTES


@pytest.fixture
def shared_attachment(client, in_memory_object_storage):
    sender = dev_login(client, "delivery-hub-member")
    recipient = dev_login(client, "delivery-hub-admin")
    administrator = dev_login(client, "administrator")
    created = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(sender["token"]),
        json={"recipient_user_id": recipient["user"]["id"]},
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    uploaded = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/attachments",
        headers=auth_headers(sender["token"]),
        files={"file": ("private-message.png", PNG_BYTES, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]
    sent = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(sender["token"]),
        json={"body": "private attachment", "attachment_ids": [attachment_id]},
    )
    assert sent.status_code == 200, sent.text
    preview = client.get(
        f"/api/v1/dm/attachments/{attachment_id}/preview",
        headers=auth_headers(recipient["token"]),
    )
    assert preview.status_code == 200, preview.text
    return {
        "sender": sender,
        "recipient": recipient,
        "administrator": administrator,
        "conversation_id": conversation_id,
        "attachment_id": attachment_id,
        "url": preview.json()["url"],
    }


def test_dm_attachment_content_requires_authentication(shared_attachment, client):
    response = client.get(shared_attachment["url"])
    assert response.status_code in {401, 403}, response.text
    assert response.content != PNG_BYTES


def test_dm_attachment_content_is_bound_to_issuer_user_and_session(shared_attachment, client):
    grant = shared_attachment
    recipient = grant["recipient"]
    allowed = client.get(grant["url"], headers=content_headers(recipient["token"], grant["url"]))
    assert allowed.status_code == 200, allowed.text
    assert allowed.content == PNG_BYTES
    # Another participant and a platform administrator cannot reuse this session's byte grant.
    for other in (grant["sender"], grant["administrator"]):
        denied = client.get(grant["url"], headers=content_headers(other["token"], grant["url"]))
        assert denied.status_code == 403, denied.text
        assert denied.content != PNG_BYTES
    new_session = dev_login(client, "delivery-hub-admin")
    denied = client.get(grant["url"], headers=content_headers(new_session["token"], grant["url"]))
    assert denied.status_code == 403, denied.text


@pytest.mark.parametrize(
    "revocation",
    ["password_change", "blocked", "inactive", "session", "membership", "replacement"],
)
def test_dm_attachment_content_rechecks_current_authority(shared_attachment, client, revocation):
    grant = shared_attachment
    recipient = grant["recipient"]
    headers = content_headers(recipient["token"], grant["url"])
    before = client.get(grant["url"], headers=headers)
    assert before.status_code == 200, before.text
    assert before.content == PNG_BYTES
    with get_session_factory().begin() as db:
        user_id = recipient["user"]["id"]
        if revocation == "password_change":
            db.get(User, user_id).must_change_password = True
        elif revocation == "blocked":
            db.get(User, user_id).login_blocked = True
        elif revocation == "inactive":
            db.get(User, user_id).status = "inactive"
        elif revocation == "session":
            for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user_id)):
                session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        elif revocation == "membership":
            participant = db.scalar(
                select(DmConversationParticipant).where(
                    DmConversationParticipant.conversation_id == grant["conversation_id"],
                    DmConversationParticipant.user_id == user_id,
                )
            )
            assert participant is not None
            participant.left_at = datetime.now(UTC).replace(tzinfo=None)
        elif revocation == "replacement":
            db.get(
                DmMessageAttachment, grant["attachment_id"]
            ).storage_key = "dm/replaced-content.png"
    denied = client.get(grant["url"], headers=headers)
    assert denied.status_code in {401, 403, 404}, denied.text
    assert denied.content != PNG_BYTES


def test_platform_admin_has_no_implicit_personal_message_or_attachment_access(
    shared_attachment, client
):
    grant = shared_attachment
    headers = auth_headers(grant["administrator"]["token"])
    messages = client.get(
        f"/api/v1/dm/conversations/{grant['conversation_id']}/messages", headers=headers
    )
    assert messages.status_code == 404, messages.text
    preview = client.get(
        f"/api/v1/dm/attachments/{grant['attachment_id']}/preview", headers=headers
    )
    assert preview.status_code == 404, preview.text


def test_dm_unsent_upload_is_private_to_its_uploader(shared_attachment, client):
    grant = shared_attachment
    uploaded = client.post(
        f"/api/v1/dm/conversations/{grant['conversation_id']}/attachments",
        headers=auth_headers(grant["sender"]["token"]),
        files={"file": ("unsent-private.png", PNG_BYTES, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    attachment_id = uploaded.json()["id"]
    assert uploaded.json()["message_id"] is None
    peer_preview = client.get(
        f"/api/v1/dm/attachments/{attachment_id}/preview",
        headers=auth_headers(grant["recipient"]["token"]),
    )
    assert peer_preview.status_code == 404, peer_preview.text
    owner_preview = client.get(
        f"/api/v1/dm/attachments/{attachment_id}/preview",
        headers=auth_headers(grant["sender"]["token"]),
    )
    assert owner_preview.status_code == 200, owner_preview.text
    url = owner_preview.json()["url"]
    content = client.get(url, headers=content_headers(grant["sender"]["token"], url))
    assert content.status_code == 200, content.text
    assert content.content == PNG_BYTES


def test_dm_rejoined_participant_cannot_read_attachments_from_before_rejoining(
    shared_attachment, client
):
    from datetime import timedelta

    grant = shared_attachment
    recipient = grant["recipient"]
    with get_session_factory().begin() as db:
        attachment = db.get(DmMessageAttachment, grant["attachment_id"])
        assert attachment is not None and attachment.message is not None
        participant = db.scalar(
            select(DmConversationParticipant).where(
                DmConversationParticipant.conversation_id == grant["conversation_id"],
                DmConversationParticipant.user_id == recipient["user"]["id"],
            )
        )
        assert participant is not None
        participant.joined_at = attachment.message.created_at + timedelta(seconds=1)
    preview = client.get(
        f"/api/v1/dm/attachments/{grant['attachment_id']}/preview",
        headers=auth_headers(recipient["token"]),
    )
    assert preview.status_code == 404, preview.text
    content = client.get(grant["url"], headers=content_headers(recipient["token"], grant["url"]))
    assert content.status_code == 403, content.text
    assert content.content != PNG_BYTES
