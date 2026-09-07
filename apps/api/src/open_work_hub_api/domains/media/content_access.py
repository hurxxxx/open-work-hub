from __future__ import annotations

from itertools import chain
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.content_access.contracts import ContentStream
from open_work_hub_api.domains.content_access.grants import (
    ContentGrantClaims,
    ContentGrantIssuer,
    InvalidContentGrant,
    build_content_grant_url,
    object_identity,
)
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.object_storage import (
    MEDIA_OBJECT_STREAM_CHUNK_SIZE,
    MediaObjectNotFoundError,
    MediaObjectReadError,
    media_object_storage,
)
from open_work_hub_api.domains.media.resource_access import (
    can_resolve_media,
    media_owner_app_enabled,
    resolve_media_access_context,
)


SAFE_MEDIA_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)
MEDIA_CONTENT_URL_EXPIRES_SECONDS = 5 * 60


def build_media_content_url(
    db: Session,
    *,
    user: User,
    media: MediaFile,
    content_grant_issuer: ContentGrantIssuer,
    authorization_mode: str = "source_acl",
    authorized_community_post_id: str | None = None,
) -> str:
    context = resolve_media_access_context(db, media)
    if context is None or content_grant_issuer.user_id != user.id:
        raise ValueError("media grants require authoritative source/user context")
    if _normalized_media_content_type(media) not in SAFE_MEDIA_CONTENT_TYPES:
        raise ValueError("media grants require a safe raster content type")
    if not media_owner_app_enabled(db, user=user, context=context):
        raise ValueError("media owner app is disabled")
    if authorization_mode == "community_password":
        if (
            authorized_community_post_id is None
            or context.community_post_id != authorized_community_post_id
        ):
            raise ValueError("password authorization does not match the media source")
    elif authorization_mode != "source_acl" or not can_resolve_media(db, user, media):
        raise ValueError("media source ACL denied")
    return build_content_grant_url(
        resource_kind="media.file",
        resource_id=media.id,
        owner_app_id=context.owner_app_id,
        issuer=content_grant_issuer,
        execution_context_kind=context.execution_context_kind,
        execution_workspace_id=context.workspace_id,
        route_id=context.route_id,
        source_type=context.source_type,
        source_id=context.source_id,
        object_identity=_media_object_identity(media),
        resource_version=context.source_version,
        disposition="inline",
        expires_seconds=MEDIA_CONTENT_URL_EXPIRES_SECONDS,
        extra={
            "authorization_mode": authorization_mode,
            "community_post_id": authorized_community_post_id,
        },
    )


def open_media_content_grant(db: Session, *, claims: ContentGrantClaims) -> ContentStream:
    media = db.scalar(select(MediaFile).where(MediaFile.id == claims.resource_id))
    if media is None:
        raise InvalidContentGrant("resource")
    context = resolve_media_access_context(db, media)
    if (
        context is None
        or _normalized_media_content_type(media) not in SAFE_MEDIA_CONTENT_TYPES
        or claims.owner_app_id != context.owner_app_id
        or claims.execution_context_kind != context.execution_context_kind
        or claims.execution_workspace_id != context.workspace_id
        or claims.route_id != context.route_id
        or claims.source_type != context.source_type
        or claims.source_id != context.source_id
        or claims.object_identity != _media_object_identity(media)
        or claims.resource_version != context.source_version
        or claims.disposition != "inline"
    ):
        raise InvalidContentGrant("binding")
    user = db.get(User, claims.issuer_user_id)
    if user is None or user.status != "active" or user.login_blocked:
        raise InvalidContentGrant("principal")
    if not media_owner_app_enabled(db, user=user, context=context):
        raise InvalidContentGrant("app")
    authorization_mode = claims.extra.get("authorization_mode")
    if authorization_mode == "community_password":
        if (
            claims.extra.get("community_post_id") != context.community_post_id
            or context.owner_app_id != "community"
        ):
            raise InvalidContentGrant("source_acl")
    elif authorization_mode != "source_acl" or not can_resolve_media(db, user, media):
        raise InvalidContentGrant("source_acl")

    try:
        stream = media_object_storage().open_stream(
            storage_key=media.storage_key,
            chunk_size=MEDIA_OBJECT_STREAM_CHUNK_SIZE,
        )
    except MediaObjectNotFoundError as error:
        raise InvalidContentGrant("resource") from error
    except MediaObjectReadError as error:
        raise localized_http_exception(
            status_code=502,
            code="media.storage_download_failed",
        ) from error
    content_type = _normalized_media_content_type(media)
    iterator = iter(stream)
    try:
        first_chunk = next(iterator)
    except StopIteration as error:
        raise InvalidContentGrant("empty_object") from error
    if not _matches_safe_raster(content_type, first_chunk[:12]):
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
        raise InvalidContentGrant("unsafe_media_type")
    return ContentStream(
        body=chain((first_chunk,), iterator),
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(media.filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _media_object_identity(media: MediaFile) -> str:
    return object_identity(
        media.id,
        media.storage_key,
        media.size_bytes,
        media.resource_type,
        media.resource_id,
        media.created_at,
    )


def _matches_safe_raster(content_type: str, prefix: bytes) -> bool:
    if content_type == "image/png":
        return prefix.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return prefix.startswith(b"\xff\xd8\xff")
    if content_type == "image/gif":
        return prefix.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP"
    return False


def _normalized_media_content_type(media: MediaFile) -> str:
    return (media.content_type or "").split(";", 1)[0].strip().lower()


__all__ = ["build_media_content_url", "open_media_content_grant"]
