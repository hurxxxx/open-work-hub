from __future__ import annotations

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import (
    is_platform_admin_user,
    resolve_workspace_role,
)
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.roles import workspace_role_allows
from open_alm_api.domains.auth.security import new_id

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
        workspace_id=announcement.workspace_id,
        author_id=announcement.author_id,
        author_name=(
            announcement.author.full_name
            if announcement.author
            else announcement.author_id
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
    workspace: Workspace,
    announcement_id: str,
) -> Announcement:
    announcement = db.scalar(
        select(Announcement)
        .where(
            Announcement.id == announcement_id,
            or_(
                Announcement.workspace_id == workspace.id,
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


def _ensure_can_write(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    scope: str,
) -> None:
    """Workspace announcements need a workspace admin; company-wide notices
    need a platform admin."""
    if scope == "company":
        if is_platform_admin_user(user, db):
            return
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="announcements.company_admin_required",
        )
    role = resolve_workspace_role(db, user, workspace.id)
    if workspace_role_allows(role, "admin"):
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="announcements.admin_required",
    )


def list_announcements(
    db: Session,
    *,
    workspace: Workspace,
    scope: AnnouncementScope = "workspace",
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
    # Workspace notices are scoped to the current workspace; company notices
    # are global and visible from every workspace.
    if scope == "workspace":
        query = query.where(Announcement.workspace_id == workspace.id)
    rows = db.scalars(query).all()
    return AnnouncementsResponse(items=[_project(row) for row in rows])


def get_announcement(
    db: Session,
    *,
    workspace: Workspace,
    announcement_id: str,
) -> AnnouncementOut:
    return _project(_load(db, workspace=workspace, announcement_id=announcement_id))


def create_announcement(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    payload: AnnouncementCreateRequest,
) -> AnnouncementOut:
    _ensure_can_write(db, user=user, workspace=workspace, scope=payload.scope)
    announcement = Announcement(
        id=new_id(),
        workspace_id=workspace.id,
        author_id=user.id,
        scope=payload.scope,
        title=payload.title.strip(),
        body=payload.body,
        is_pinned=payload.is_pinned,
    )
    db.add(announcement)
    db.commit()
    return _project(_load(db, workspace=workspace, announcement_id=announcement.id))


def update_announcement(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    announcement_id: str,
    payload: AnnouncementUpdateRequest,
) -> AnnouncementOut:
    announcement = _load(db, workspace=workspace, announcement_id=announcement_id)
    _ensure_can_write(db, user=user, workspace=workspace, scope=announcement.scope)
    if payload.title is not None:
        announcement.title = payload.title.strip()
    if payload.body is not None:
        announcement.body = payload.body
    if payload.is_pinned is not None:
        announcement.is_pinned = payload.is_pinned
    db.commit()
    return _project(_load(db, workspace=workspace, announcement_id=announcement.id))


def delete_announcement(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    announcement_id: str,
) -> None:
    announcement = _load(db, workspace=workspace, announcement_id=announcement_id)
    _ensure_can_write(db, user=user, workspace=workspace, scope=announcement.scope)
    db.delete(announcement)
    db.commit()
