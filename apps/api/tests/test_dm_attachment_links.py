from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from open_work_hub_api.core.model_registry import import_all_models
from open_work_hub_api.domains.content_access import grants
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer, InvalidContentGrant
from open_work_hub_api.domains.dm import attachment_links
from open_work_hub_api.domains.dm.models import DmMessageAttachment


@pytest.fixture(scope="module", autouse=True)
def load_attachment_model_registry():
    import_all_models()


@pytest.fixture(autouse=True)
def shared_content_signing(monkeypatch):
    settings = SimpleNamespace(
        api_prefix="/api/v1", content_grant_signing_key="unit-test-shared-signing-key"
    )
    monkeypatch.setattr(grants, "get_settings", lambda: settings)
    return settings


def _attachment(*, content_type="image/png") -> DmMessageAttachment:
    return DmMessageAttachment(
        id="attachment-1",
        conversation_id="conversation-1",
        message_id="message-1",
        uploader_id="user-1",
        filename="file.png",
        content_type=content_type,
        size_bytes=12,
        storage_key="dm/conversation-1/attachment-1/file.png",
        created_at=datetime(2026, 9, 8),
    )


def _token(url):
    parsed = urlparse(url)
    assert parsed.path == "/api/v1/content" and not parsed.query
    return parse_qs(parsed.fragment)["grant"][0]


def test_dm_attachment_grant_binds_personal_source_object_and_current_issuer():
    attachment = _attachment()
    url = attachment_links.build_dm_attachment_content_url(
        attachment,
        issuer=ContentGrantIssuer(user_id="reader-1", session_id="session-1"),
        disposition="inline",
        now=1000,
    )
    claims = grants.decode_content_grant(_token(url), now=1001)
    assert claims.resource_kind == "dm.attachment"
    assert claims.resource_id == attachment.id
    assert claims.owner_app_id == "dm"
    assert claims.execution_context_kind == "personal"
    assert claims.issuer_user_id == "reader-1"
    assert claims.issuer_session_id == "session-1"
    assert claims.source_id == attachment.conversation_id
    assert claims.source_type == "dm_conversation"
    assert claims.disposition == "inline"
    assert claims.expires - claims.issued_at == 300
    assert claims.object_identity == attachment_links.dm_attachment_object_identity(attachment)
    assert claims.resource_version == attachment_links.dm_attachment_version(attachment)
    assert attachment.storage_key not in url


def test_dm_attachment_helpers_express_disposition_and_reject_nonimage_preview():
    issuer = ContentGrantIssuer(user_id="user-1", session_id="session-1")
    download = attachment_links.build_dm_attachment_download_url(_attachment(), issuer=issuer)
    preview = attachment_links.build_dm_attachment_preview_url(_attachment(), issuer=issuer)
    assert grants.decode_content_grant(_token(download)).disposition == "attachment"
    assert preview is not None
    assert grants.decode_content_grant(_token(preview)).disposition == "inline"
    assert (
        attachment_links.build_dm_attachment_preview_url(
            _attachment(content_type="text/plain"), issuer=issuer
        )
        is None
    )


def test_dm_grant_expires_and_shared_signing_rotation_invalidates_old_capabilities(
    shared_content_signing,
):
    url = attachment_links.build_dm_attachment_content_url(
        _attachment(),
        issuer=ContentGrantIssuer(user_id="user-1", session_id="session-1"),
        disposition="attachment",
        now=1000,
    )
    token = _token(url)
    with pytest.raises(InvalidContentGrant, match="expired"):
        grants.decode_content_grant(token, now=1301)
    shared_content_signing.content_grant_signing_key = "rotated-unit-test-shared-key"
    with pytest.raises(InvalidContentGrant, match="signature"):
        grants.decode_content_grant(token, now=1001)


@pytest.mark.parametrize(
    "changed", ["storage_key", "filename", "content_type", "size_bytes", "conversation_id"]
)
def test_dm_object_binding_changes_when_source_object_identity_changes(changed):
    attachment = _attachment()
    before = attachment_links.dm_attachment_object_identity(attachment)
    setattr(attachment, changed, 13 if changed == "size_bytes" else "replacement")
    assert attachment_links.dm_attachment_object_identity(attachment) != before


def test_dm_grant_version_changes_when_staged_attachment_is_sent():
    attachment = _attachment()
    attachment.message_id = None
    before = attachment_links.dm_attachment_version(attachment)
    attachment.message_id = "new-message"
    assert attachment_links.dm_attachment_version(attachment) != before
