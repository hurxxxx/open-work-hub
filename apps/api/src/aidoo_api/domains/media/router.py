"""Media upload endpoints for block editor images."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from aidoo_api.core.db import get_db_session
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import get_minio_client
from aidoo_api.domains.auth.access import resolve_team_role
from aidoo_api.domains.auth.dependencies import require_admin_context, require_current_user
from aidoo_api.domains.auth.models import Team, User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import DocMeetingAccess, NativeDocPage, NativeDocUserShare
from aidoo_api.domains.docs.registry import ContainerRef, project_container_access
from aidoo_api.domains.media.models import MediaFile

MAX_MEDIA_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
MEDIA_ID_PATTERN = re.compile(r"media:([0-9a-f-]{36})")

router = APIRouter(prefix="/media", tags=["media"])

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
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Allowed: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}",
        )

    data = await file.read()
    if len(data) > MAX_MEDIA_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="File size exceeds 10 MB limit.")

    settings = get_settings()
    client = get_minio_client()
    media_id = new_id()
    filename = file.filename or "unnamed"
    storage_key = f"media/{current_user.id}/{media_id}/{filename}"

    # DB first, then MinIO — avoids permanently uncleanable orphans
    media = MediaFile(
        id=media_id,
        storage_key=storage_key,
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        uploaded_by_id=current_user.id,
    )
    db.add(media)
    try:
        db.flush()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create media record.")

    try:
        client.put_object(
            settings.minio_bucket,
            storage_key,
            BytesIO(data),
            length=len(data),
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception:
        db.rollback()
        raise HTTPException(status_code=502, detail="Storage upload failed.")

    try:
        db.commit()
    except Exception:
        db.rollback()
        try:
            client.remove_object(settings.minio_bucket, storage_key)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Failed to save media metadata.")
    return MediaUploadResponse(id=media_id, url=f"media:{media_id}")


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
) -> MediaResolveResponse:
    """Resolve media:{id} URLs to presigned GET URLs for rendering."""
    media_ids: list[str] = []
    for url in payload.urls:
        m = MEDIA_ID_PATTERN.fullmatch(url)
        if m:
            media_ids.append(m.group(1))

    if not media_ids:
        return MediaResolveResponse(resolved={})

    media_files = db.scalars(
        select(MediaFile).where(MediaFile.id.in_(media_ids))
    ).all()

    settings = get_settings()
    client = get_minio_client()
    resolved: dict[str, str] = {}

    for media in media_files:
        if not _can_resolve(db, current_user, media):
            continue
        presigned = client.presigned_get_object(
            settings.minio_bucket,
            media.storage_key,
            expires=timedelta(hours=1),
        )
        resolved[f"media:{media.id}"] = presigned

    return MediaResolveResponse(resolved=resolved)


def _can_resolve(db: Session, user: User, media: MediaFile) -> bool:
    """Check if the user is allowed to resolve this media file."""
    # Unlinked media: only the uploader can resolve
    if media.resource_type is None:
        return media.uploaded_by_id == user.id
    # Linked to an issue: check task list membership
    if media.resource_type == "issue":
        from aidoo_api.domains.pms.models import Issue, TaskList

        issue = db.scalar(select(Issue).where(Issue.id == media.resource_id))
        if issue is None:
            return False
        task_list = db.scalar(select(TaskList).where(TaskList.id == issue.list_id))
        return _has_space_access(db, user, task_list.team_id if task_list else None)
    if media.resource_type == "docs_native_page":
        return _can_access_docs_native_page(db, user, media.resource_id, require_edit=False)
    # Unknown resource type: allow uploader only
    return media.uploaded_by_id == user.id


def _can_link_unlinked_media(db: Session, user: User, media: MediaFile) -> bool:
    return media.uploaded_by_id == user.id


def _has_space_access(db: Session, user: User, team_id: str | None) -> bool:
    if team_id is None:
        return False
    team = db.scalar(
        select(Team)
        .options(joinedload(Team.workspace))
        .where(
            Team.id == team_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
        )
    )
    if team is None:
        return False
    return resolve_team_role(db, user, team) is not None


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

    # Validate resource access
    if payload.resource_type == "issue":
        _ensure_issue_access(db, current_user, payload.resource_id)
    elif payload.resource_type == "docs_native_page":
        _ensure_docs_native_page_access(db, current_user, payload.resource_id)
    else:
        raise HTTPException(status_code=400, detail="Unsupported media resource type.")

    media_files = db.scalars(
        select(MediaFile).where(
            MediaFile.id.in_(payload.media_ids),
            MediaFile.resource_type.is_(None),
        )
    ).all()

    for media in media_files:
        if not _can_link_unlinked_media(db, current_user, media):
            continue
        media.resource_type = payload.resource_type
        media.resource_id = payload.resource_id

    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _ensure_issue_access(db: Session, user: User, issue_id: str) -> None:
    """Verify the user has access to the issue's task list."""
    from aidoo_api.domains.pms.models import Issue, TaskList

    issue = db.scalar(select(Issue).where(Issue.id == issue_id))
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    task_list = db.scalar(select(TaskList).where(TaskList.id == issue.list_id))
    if not _has_space_access(db, user, task_list.team_id if task_list else None):
        raise HTTPException(status_code=403, detail="Task list space access required.")


def _can_access_docs_native_page(
    db: Session,
    user: User,
    page_id: str,
    *,
    require_edit: bool,
) -> bool:
    page = db.scalar(
        select(NativeDocPage)
        .options(joinedload(NativeDocPage.doc))
        .where(NativeDocPage.id == page_id)
    )
    if page is None or page.doc is None or page.trashed_at is not None or page.doc.trashed_at is not None:
        return False
    if page.doc.owner_id == user.id:
        return True

    direct_share = db.scalar(
        select(NativeDocUserShare).where(
            NativeDocUserShare.doc_id == page.doc_id,
            NativeDocUserShare.user_id == user.id,
        )
    )
    meeting_grant = db.scalar(
        select(DocMeetingAccess).where(
            DocMeetingAccess.doc_id == page.doc_id,
            DocMeetingAccess.user_id == user.id,
            DocMeetingAccess.revoked_at.is_(None),
            (
                DocMeetingAccess.expires_at.is_(None)
                | (DocMeetingAccess.expires_at > datetime.now(UTC).replace(tzinfo=None))
            ),
        )
    )

    access_levels = [
        level
        for level in (
            getattr(direct_share, "access_level", None),
            getattr(meeting_grant, "access_level", None),
        )
        if level in {"read", "edit"}
    ]
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == page.doc.workspace_id,
            Workspace.active.is_(True),
        )
    )
    if workspace is not None:
        for container in page.doc.containers:
            projection = project_container_access(
                db=db,
                user=user,
                workspace=workspace,
                ref=ContainerRef(
                    app=container.container_app,
                    type=container.container_type,
                    id=container.container_id,
                ),
            )
            if projection.can_manage or projection.can_edit:
                access_levels.append("edit")
            elif projection.can_view:
                access_levels.append("read")
    if not access_levels:
        return False
    if require_edit:
        return "edit" in access_levels
    return True


def _ensure_docs_native_page_access(db: Session, user: User, page_id: str) -> None:
    if not _can_access_docs_native_page(db, user, page_id, require_edit=True):
        raise HTTPException(status_code=403, detail="Doc edit access required.")


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

    settings = get_settings()
    client = get_minio_client()
    deleted = 0
    failed = 0

    for orphan in orphans:
        try:
            client.remove_object(settings.minio_bucket, orphan.storage_key)
        except Exception:
            failed += 1
            continue  # Keep DB row so we can retry later
        db.delete(orphan)
        deleted += 1

    db.commit()
    return CleanupResponse(deleted_count=deleted, failed_count=failed)


# ── Server-side media sync (link + unlink) ────────────────────────────


def sync_embedded_media(
    db: Session,
    blocks: object,
    resource_type: str,
    resource_id: str,
    current_user: User,
) -> None:
    """Full re-scan: link new media, unlink removed media for a resource."""
    raw = json.dumps(blocks) if not isinstance(blocks, str) else blocks
    current_ids = set(MEDIA_ID_PATTERN.findall(raw))

    # Link newly referenced media
    if current_ids:
        media_files = db.scalars(
            select(MediaFile).where(
                MediaFile.id.in_(current_ids),
                MediaFile.resource_type.is_(None),
            )
        ).all()
        for media in media_files:
            if not _can_link_unlinked_media(db, current_user, media):
                continue
            media.resource_type = resource_type
            media.resource_id = resource_id

    # Unlink media no longer referenced by this resource
    previously_linked = db.scalars(
        select(MediaFile).where(
            MediaFile.resource_type == resource_type,
            MediaFile.resource_id == resource_id,
        )
    ).all()

    for media in previously_linked:
        if media.id not in current_ids:
            media.resource_type = None
            media.resource_id = None


def cleanup_media_for_resource(db: Session, resource_type: str, resource_id: str) -> list[str]:
    """Mark media for deletion and return storage keys for post-commit MinIO cleanup."""
    media_files = db.scalars(
        select(MediaFile).where(
            MediaFile.resource_type == resource_type,
            MediaFile.resource_id == resource_id,
        )
    ).all()

    if not media_files:
        return []

    keys = [media.storage_key for media in media_files]
    for media in media_files:
        db.delete(media)
    return keys
