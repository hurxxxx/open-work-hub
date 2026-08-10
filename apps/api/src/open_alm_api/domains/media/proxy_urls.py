"""Short-lived same-origin media proxy URL policy."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from open_alm_api.domains.media.models import MediaFile

MEDIA_PROXY_EXPIRES_SECONDS = 60 * 60


def build_media_proxy_url(
    media: MediaFile,
    *,
    api_prefix: str,
    secret: str,
    issued_at: int | None = None,
    expires_seconds: int = MEDIA_PROXY_EXPIRES_SECONDS,
) -> str:
    expires = (issued_at if issued_at is not None else int(time.time())) + expires_seconds
    signature = sign_media_proxy_url(media, expires, secret=secret)
    return (
        f"{api_prefix}/media/content/{media.id}"
        f"?expires={expires}&signature={signature}"
    )


def sign_media_proxy_url(media: MediaFile, expires: int, *, secret: str) -> str:
    message = f"v1:{media.id}:{media.storage_key}:{expires}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def is_media_proxy_url_expired(expires: int, *, now: int | None = None) -> bool:
    return expires < (now if now is not None else int(time.time()))


def is_valid_media_proxy_signature(
    media: MediaFile,
    *,
    expires: int,
    signature: str,
    secret: str,
) -> bool:
    return hmac.compare_digest(
        signature,
        sign_media_proxy_url(media, expires, secret=secret),
    )


__all__ = [
    "MEDIA_PROXY_EXPIRES_SECONDS",
    "build_media_proxy_url",
    "is_media_proxy_url_expired",
    "is_valid_media_proxy_signature",
    "sign_media_proxy_url",
]
