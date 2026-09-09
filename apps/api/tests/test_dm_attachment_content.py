from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.content_access.grants import (
    ContentGrantIssuer,
    InvalidContentGrant,
    decode_content_grant,
)
from open_work_hub_api.domains.dm import attachment_content, attachment_links
from open_work_hub_api.domains.dm.models import DmMessageAttachment


@pytest.fixture
def authorized_source(monkeypatch):
    attachment = DmMessageAttachment(
        id="attachment-1",
        conversation_id="conversation-1",
        message_id="message-1",
        uploader_id="user-1",
        filename="report.txt",
        content_type="image/png",
        size_bytes=12,
        storage_key="dm/private/report.txt",
        created_at=datetime(2026, 9, 8),
    )
    url = attachment_links.build_dm_attachment_content_url(
        attachment,
        issuer=ContentGrantIssuer(user_id="user-1", session_id="session-1"),
        disposition="inline",
    )
    claims = decode_content_grant(parse_qs(urlparse(url).fragment)["grant"][0])
    monkeypatch.setattr(
        attachment_content.attachment_records,
        "require_attachment_access",
        lambda _db, **kwargs: attachment,
    )
    return SimpleNamespace(get=lambda _model, _id: SimpleNamespace(id="user-1")), attachment, claims


def test_dm_content_headers_disable_caching_and_encode_untrusted_filename():
    assert attachment_content.dm_attachment_content_headers(
        filename="quarterly/report #1?.txt", disposition="attachment"
    ) == {
        "Cache-Control": "private, no-store",
        "Content-Disposition": "attachment; filename*=UTF-8''quarterly%2Freport%20%231%3F.txt",
        "X-Content-Type-Options": "nosniff",
    }


def test_dm_content_grant_stream_preserves_storage_cleanup(monkeypatch, authorized_source):
    db, attachment, claims = authorized_source
    stored = SimpleNamespace(closed=False, released=False)

    def stream(*, storage_key, chunk_size):
        assert storage_key == attachment.storage_key
        assert chunk_size == attachment_content.DM_ATTACHMENT_PROXY_CHUNK_SIZE

        class Object:
            def stream(self, chunk_size):
                yield b"first"
                yield b"second"

            def close(self):
                stored.closed = True

            def release_conn(self):
                stored.released = True

        return attachment_content.attachment_storage.stream_attachment_storage_object(
            Object(), chunk_size=chunk_size
        )

    monkeypatch.setattr(
        attachment_content.attachment_storage,
        "dm_attachment_storage",
        lambda: SimpleNamespace(open_stream=stream),
    )
    content = attachment_content.open_dm_attachment_content_grant(db, claims=claims)
    assert content.media_type == "image/png"
    assert list(content.body) == [b"first", b"second"]
    assert stored.closed and stored.released


@pytest.mark.parametrize(
    "binding",
    [
        "resource_kind",
        "owner_app_id",
        "execution_context_kind",
        "source_type",
        "source_id",
        "object_identity",
        "resource_version",
    ],
)
def test_dm_content_grant_rejects_wrong_binding_before_storage(
    monkeypatch, authorized_source, binding
):
    db, _attachment, claims = authorized_source
    monkeypatch.setattr(
        attachment_content.attachment_storage,
        "dm_attachment_storage",
        lambda: pytest.fail("invalid grants must not open storage"),
    )
    with pytest.raises(InvalidContentGrant, match="binding"):
        attachment_content.open_dm_attachment_content_grant(
            db, claims=replace(claims, **{binding: "wrong-binding"})
        )


@pytest.mark.parametrize("status_code", [403, 404])
def test_dm_content_grant_checks_current_account_and_source_before_storage(
    monkeypatch, authorized_source, status_code
):
    db, _attachment, claims = authorized_source
    monkeypatch.setattr(
        attachment_content.attachment_storage,
        "dm_attachment_storage",
        lambda: pytest.fail("revoked authority must not open storage"),
    )

    def denied(*_args, **_kwargs):
        raise HTTPException(status_code=status_code)

    monkeypatch.setattr(attachment_content.attachment_records, "require_attachment_access", denied)
    with pytest.raises(InvalidContentGrant, match="source_acl"):
        attachment_content.open_dm_attachment_content_grant(db, claims=claims)


def test_dm_content_grant_maps_storage_open_failure(monkeypatch, authorized_source):
    db, _attachment, claims = authorized_source

    def unavailable(**_kwargs):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(
        attachment_content.attachment_storage,
        "dm_attachment_storage",
        lambda: SimpleNamespace(open_stream=unavailable),
    )
    with pytest.raises(HTTPException) as error:
        attachment_content.open_dm_attachment_content_grant(db, claims=claims)
    assert error.value.status_code == 502


def test_dm_content_grant_rejects_inline_nonimage_before_storage(monkeypatch, authorized_source):
    db, attachment, claims = authorized_source
    attachment.content_type = "text/plain"
    claims = replace(
        claims, object_identity=attachment_links.dm_attachment_object_identity(attachment)
    )
    monkeypatch.setattr(
        attachment_content.attachment_storage,
        "dm_attachment_storage",
        lambda: pytest.fail("nonimage preview must not open storage"),
    )
    with pytest.raises(InvalidContentGrant, match="disposition"):
        attachment_content.open_dm_attachment_content_grant(db, claims=claims)
