from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from open_alm_api.core.settings import get_settings
from open_alm_api.domains.dm import attachment_links
from open_alm_api.domains.dm.models import DmMessageAttachment


def _attachment(*, content_type: str = "text/plain") -> DmMessageAttachment:
    return DmMessageAttachment(
        id="attachment-1",
        conversation_id="conversation-1",
        message_id=None,
        uploader_id="user-1",
        filename="file.txt",
        content_type=content_type,
        size_bytes=12,
        storage_key="dm/conversation-1/attachment-1/file.txt",
    )


def test_build_dm_attachment_content_url_signs_attachment_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        attachment_links,
        "get_settings",
        lambda: SimpleNamespace(
            api_prefix="/custom/api",
            dm_attachment_signing_key="signing-secret",
        ),
    )
    monkeypatch.setattr(attachment_links.time, "time", lambda: 1000)

    url = attachment_links.build_dm_attachment_content_url(
        _attachment(),
        disposition="attachment",
    )

    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert parsed.path == "/custom/api/dm/attachments/attachment-1/content"
    assert params["expires"] == ["4600"]
    assert params["disposition"] == ["attachment"]
    assert params["signature"] == ["YHAifb62eccgZWrmq4Kj1qoYhpfnZNERayQvbdeyySk"]
    assert attachment_links.validate_dm_attachment_content_signature(
        _attachment(),
        expires=int(params["expires"][0]),
        disposition="attachment",
        signature=params["signature"][0],
    )


def test_dm_attachment_content_policy_and_signer_accept_injected_dependencies() -> None:
    policy = attachment_links.DmAttachmentContentUrlPolicy(
        disposition="inline",
        api_prefix="/custom/api",
        time_source=lambda: 1000.9,
    )
    signer = attachment_links.DmAttachmentContentSigner(
        signing_key="signing-secret",
    )

    payload = signer.signing_payload(
        _attachment(),
        expires=4600,
        disposition="inline",
    )
    url = policy.build_url(
        _attachment(),
        signer=signer,
    )
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert payload.encode() == (
        b"v1:attachment-1:conversation-1:dm/conversation-1/attachment-1/file.txt:"
        b"4600:inline"
    )
    assert parsed.path == "/custom/api/dm/attachments/attachment-1/content"
    assert params["expires"] == ["4600"]
    assert params["disposition"] == ["inline"]
    assert params["signature"] == ["DBnwctZ5M3ImKiJGeRn7lQTPnphAt9-nAfTtp5UjKek"]
    assert signer.validate(
        _attachment(),
        expires=4600,
        disposition="inline",
        signature=params["signature"][0],
    )

    expired_policy = attachment_links.DmAttachmentContentUrlPolicy(
        disposition="inline",
        api_prefix="/custom/api",
        time_source=lambda: 4601,
    )
    assert expired_policy.is_expired(4600)


def test_build_dm_attachment_download_and_preview_urls_express_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        attachment_links,
        "get_settings",
        lambda: SimpleNamespace(
            api_prefix="/custom/api",
            dm_attachment_signing_key="signing-secret",
        ),
    )
    monkeypatch.setattr(attachment_links.time, "time", lambda: 1000)

    download = attachment_links.build_dm_attachment_download_url(
        _attachment(content_type="image/png"),
    )
    preview = attachment_links.build_dm_attachment_preview_url(
        _attachment(content_type="image/png"),
    )
    unsupported_preview = attachment_links.build_dm_attachment_preview_url(
        _attachment(content_type="text/plain"),
    )

    assert parse_qs(urlparse(download).query)["disposition"] == ["attachment"]
    assert preview is not None
    assert parse_qs(urlparse(preview).query)["disposition"] == ["inline"]
    assert unsupported_preview is None


def test_validate_dm_attachment_content_signature_rejects_expired_or_changed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        attachment_links,
        "get_settings",
        lambda: SimpleNamespace(
            api_prefix="/custom/api",
            dm_attachment_signing_key="signing-secret",
        ),
    )
    monkeypatch.setattr(attachment_links.time, "time", lambda: 1000)
    url = attachment_links.build_dm_attachment_content_url(
        _attachment(),
        disposition="inline",
    )
    params = parse_qs(urlparse(url).query)
    expires = int(params["expires"][0])
    signature = params["signature"][0]

    assert attachment_links.validate_dm_attachment_content_signature(
        _attachment(),
        expires=expires,
        disposition="inline",
        signature=signature,
    )
    monkeypatch.setattr(attachment_links.time, "time", lambda: expires + 1)
    assert not attachment_links.validate_dm_attachment_content_signature(
        _attachment(),
        expires=expires,
        disposition="inline",
        signature=signature,
    )
    monkeypatch.setattr(attachment_links.time, "time", lambda: 1000)
    assert not attachment_links.validate_dm_attachment_content_signature(
        _attachment(),
        expires=expires,
        disposition="attachment",
        signature=signature,
    )


def test_dm_attachment_signature_uses_dedicated_signing_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        api_prefix="/custom/api",
        dm_attachment_signing_key="first-signing-secret",
    )
    monkeypatch.setattr(attachment_links, "get_settings", lambda: settings)
    monkeypatch.setattr(attachment_links.time, "time", lambda: 1000)
    url = attachment_links.build_dm_attachment_content_url(
        _attachment(),
        disposition="attachment",
    )
    params = parse_qs(urlparse(url).query)

    settings.dm_attachment_signing_key = "second-signing-secret"

    assert not attachment_links.validate_dm_attachment_content_signature(
        _attachment(),
        expires=int(params["expires"][0]),
        disposition="attachment",
        signature=params["signature"][0],
    )


def test_dm_attachment_signing_key_env_alias_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_ALM_DM_ATTACHMENT_SIGNING_KEY", "env-signing-secret")
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.dm_attachment_signing_key == "env-signing-secret"
