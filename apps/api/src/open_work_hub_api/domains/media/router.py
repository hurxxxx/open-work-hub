"""Media upload endpoints for block editor images."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import require_admin_context, require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.content_access.dependencies import require_content_grant_issuer
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer
from open_work_hub_api.domains.media.lifecycle import (
    apply_media_links,
    build_media_upload_record,
    media_upload_response_payload,
    plan_orphan_media_cleanup,
)
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.object_storage import media_object_storage
from open_work_hub_api.domains.media.content_access import build_media_content_url
from open_work_hub_api.domains.media.resource_access import (
    can_resolve_media,
    ensure_media_link_resource_access,
    media_ids_from_urls,
)

MAX_MEDIA_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}

router = APIRouter(prefix="/media", tags=["media"])
logger = logging.getLogger(__name__)


# ── Upload ────────────────────────────────────────────────────────────


class MediaUploadResponse(BaseModel):
    id: str
    url: str


@router.post("/upload", response_model=MediaUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MediaUploadResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise localized_http_exception(
            status_code=400,
            code="media.unsupported_file_type",
            content_type=file.content_type,
            allowed_types=", ".join(sorted(ALLOWED_IMAGE_TYPES)),
        )

    data = await file.read()
    if len(data) > MAX_MEDIA_UPLOAD_SIZE:
        raise localized_http_exception(
            status_code=413,
            code="media.file_size_limit_exceeded",
            limit_mb=10,
        )

    storage = media_object_storage()
    media_id = new_id()

    # DB first, then MinIO — avoids permanently uncleanable orphans
    media = build_media_upload_record(
        {
            "media_id": media_id,
            "user_id": current_user.id,
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": len(data),
        }
    )
    db.add(media)
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise localized_http_exception(
            status_code=500,
            code="media.create_record_failed",
        )

    try:
        storage.put_bytes(
            storage_key=media.storage_key,
            data=data,
            content_type=file.content_type,
        )
    except Exception:
        db.rollback()
        raise localized_http_exception(
            status_code=502,
            code="media.storage_upload_failed",
        )

    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            storage.remove(storage_key=media.storage_key)
        except Exception:
            pass
        raise localized_http_exception(
            status_code=500,
            code="media.save_metadata_failed",
        )
    return MediaUploadResponse(**media_upload_response_payload(media_id))


# ── Resolve ───────────────────────────────────────────────────────────


class MediaResolveRequest(BaseModel):
    urls: list[str]


class MediaResolveResponse(BaseModel):
    resolved: dict[str, str]


@router.post("/resolve", response_model=MediaResolveResponse)
def resolve_media_urls(
    payload: MediaResolveRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MediaResolveResponse:
    """Resolve media:{id} URLs to same-origin proxy URLs for rendering."""
    media_ids = media_ids_from_urls(payload.urls)

    if not media_ids:
        return MediaResolveResponse(resolved={})

    media_files = db.scalars(select(MediaFile).where(MediaFile.id.in_(media_ids))).all()

    resolved: dict[str, str] = {}
    for media in media_files:
        if not can_resolve_media(db, current_user, media):
            continue
        resolved[f"media:{media.id}"] = build_media_content_url(
            db,
            user=current_user,
            media=media,
            content_grant_issuer=content_grant_issuer,
        )

    return MediaResolveResponse(resolved=resolved)


# ── Link ──────────────────────────────────────────────────────────────


class MediaLinkRequest(BaseModel):
    media_ids: list[str]
    resource_type: str
    resource_id: str


@router.post("/link", status_code=status.HTTP_204_NO_CONTENT)
def link_media(
    payload: MediaLinkRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    if not payload.media_ids:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    ensure_media_link_resource_access(
        db,
        current_user,
        payload.resource_type,
        payload.resource_id,
    )

    media_files = db.scalars(
        select(MediaFile).where(
            MediaFile.id.in_(payload.media_ids),
            MediaFile.resource_type.is_(None),
        )
    ).all()

    apply_media_links(media_files, current_user, payload.resource_type, payload.resource_id)

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Cleanup ───────────────────────────────────────────────────────────


class CleanupResponse(BaseModel):
    deleted_count: int
    failed_count: int


@router.post("/cleanup-orphans", response_model=CleanupResponse)
def cleanup_orphan_media(
    max_age_hours: int = Query(default=24, ge=1),
    db: Session = Depends(get_db_session),
    _context=Depends(require_admin_context),
) -> CleanupResponse:
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=max_age_hours)
    orphans = db.scalars(
        select(MediaFile)
        .where(MediaFile.resource_type.is_(None), MediaFile.created_at < cutoff)
        .limit(500)
    ).all()

    removal_result = media_object_storage().remove_many(
        orphan.storage_key for orphan in orphans
    )
    cleanup_plan = plan_orphan_media_cleanup(orphans, removal_result)

    for orphan in cleanup_plan.rows_to_delete:
        db.delete(orphan)

    db.commit()
    return CleanupResponse(
        deleted_count=cleanup_plan.deleted_count,
        failed_count=cleanup_plan.failed_count,
    )
