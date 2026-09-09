from __future__ import annotations

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import is_platform_admin_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id

from .models import Announcement
from .schemas import (
    AnnouncementCreateRequest,
    AnnouncementOut,
    AnnouncementScope,
    AnnouncementsResponse,
    AnnouncementUpdateRequest,
)

DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100


def _project(announcement: Announcement) -> AnnouncementOut:
    return AnnouncementOut(
        id=announcement.id,
        author_id=announcement.author_id,
        author_name=(
            announcement.author.full_name if announcement.author else announcement.author_id
        ),
        scope=announcement.scope,  # type: ignore[arg-type]
        title=announcement.title,
        body=announcement.body,
        is_pinned=announcement.is_pinned,
        created_at=announcement.created_at,
        updated_at=announcement.updated_at,
    )


def _load(
    db: Session,
    *,
    announcement_id: str,
) -> Announcement:
    announcement = db.scalar(
        select(Announcement)
        .where(
            Announcement.id == announcement_id,
            or_(
                Announcement.scope == "company",
            ),
        )
        .options(selectinload(Announcement.author))
    )
    if announcement is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="announcements.not_found",
        )
    return announcement


def _ensure_can_write(db: Session, *, user: User, scope: str) -> None:
    if scope != "company" or not is_platform_admin_user(user, db):
        raise localized_http_exception(status_code=403, code="announcements.company_admin_required")


def list_announcements(
    db: Session,
    *,
    scope: AnnouncementScope = "company",
    limit: int = DEFAULT_LIST_LIMIT,
) -> AnnouncementsResponse:
    bounded = max(1, min(limit, MAX_LIST_LIMIT))
    query = (
        select(Announcement)
        .options(selectinload(Announcement.author))
        .where(Announcement.scope == scope)
        .order_by(
            Announcement.is_pinned.desc(),
            Announcement.created_at.desc(),
        )
        .limit(bounded)
    )
    if scope == "company":
        query = query.where()
    rows = db.scalars(query).all()
    return AnnouncementsResponse(items=[_project(row) for row in rows])


def get_announcement(
    db: Session,
    *,
    announcement_id: str,
) -> AnnouncementOut:
    return _project(_load(db, announcement_id=announcement_id))


def create_announcement(
    db: Session,
    *,
    user: User,
    payload: AnnouncementCreateRequest,
) -> AnnouncementOut:
    _ensure_can_write(db, user=user, scope=payload.scope)
    announcement = Announcement(
        id=new_id(),
        author_id=user.id,
        scope=payload.scope,
        title=payload.title.strip(),
        body=payload.body,
        is_pinned=payload.is_pinned,
    )
    db.add(announcement)
    db.commit()
    return _project(_load(db, announcement_id=announcement.id))


def update_announcement(
    db: Session,
    *,
    user: User,
    announcement_id: str,
    payload: AnnouncementUpdateRequest,
) -> AnnouncementOut:
    announcement = _load(db, announcement_id=announcement_id)
    _ensure_can_write(db, user=user, scope=announcement.scope)
    if payload.title is not None:
        announcement.title = payload.title.strip()
    if payload.body is not None:
        announcement.body = payload.body
    if payload.is_pinned is not None:
        announcement.is_pinned = payload.is_pinned
    db.commit()
    return _project(_load(db, announcement_id=announcement.id))


def delete_announcement(
    db: Session,
    *,
    user: User,
    announcement_id: str,
) -> None:
    announcement = _load(db, announcement_id=announcement_id)
    _ensure_can_write(db, user=user, scope=announcement.scope)
    db.delete(announcement)
    db.commit()
