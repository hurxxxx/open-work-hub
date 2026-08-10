from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from ai_do_api.domains.media.models import MediaFile
from ai_do_api.domains.media.proxy_urls import (
    build_media_proxy_url,
    is_media_proxy_url_expired,
    is_valid_media_proxy_signature,
    sign_media_proxy_url,
)


def _media(**overrides: object) -> MediaFile:
    defaults = {
        "id": "media-1",
        "storage_key": "media/user-1/media-1/fixture.png",
        "filename": "fixture.png",
        "content_type": "image/png",
        "size_bytes": 128,
        "uploaded_by_id": "user-1",
        "resource_type": None,
        "resource_id": None,
    }
    defaults.update(overrides)
    return MediaFile(**defaults)


def test_build_media_proxy_url_uses_prefix_expiry_and_signature() -> None:
    media = _media()

    url = build_media_proxy_url(
        media,
        api_prefix="/api/v1",
        secret="test-secret",
        issued_at=1_000,
        expires_seconds=60,
    )

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.path == "/api/v1/media/content/media-1"
    assert query["expires"] == ["1060"]
    assert query["signature"] == [
        sign_media_proxy_url(media, 1_060, secret="test-secret")
    ]


def test_media_proxy_signature_includes_storage_key_and_expiry() -> None:
    media = _media(storage_key="media/user-1/media-1/fixture.png")
    moved_media = _media(storage_key="media/user-1/media-1/moved.png")
    signature = sign_media_proxy_url(media, 1_060, secret="test-secret")

    assert is_valid_media_proxy_signature(
        media,
        expires=1_060,
        signature=signature,
        secret="test-secret",
    )
    assert not is_valid_media_proxy_signature(
        media,
        expires=1_061,
        signature=signature,
        secret="test-secret",
    )
    assert not is_valid_media_proxy_signature(
        moved_media,
        expires=1_060,
        signature=signature,
        secret="test-secret",
    )


def test_media_proxy_expiry_is_strictly_before_now() -> None:
    assert is_media_proxy_url_expired(999, now=1_000)
    assert not is_media_proxy_url_expired(1_000, now=1_000)
