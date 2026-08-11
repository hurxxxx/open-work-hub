"""Access rules for resolving and linking embedded media resources."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import (
    is_platform_admin_user,
    resolve_team_role,
)
from open_work_hub_api.domains.auth.models import Team, User, Workspace
from open_work_hub_api.domains.docs.models import DocMeetingAccess, NativeDocPage, NativeDocUserShare
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.service import MEDIA_ID_PATTERN
from open_work_hub_api.domains.source_access.targets import (
    TargetRef,
    project_target_access,
)

MEDIA_RESOURCE_TASK = "task"
MEDIA_RESOURCE_DOCS_NATIVE_PAGE = "docs_native_page"
MEDIA_RESOURCE_COMMUNITY_POST = "community_post"
MEDIA_RESOURCE_COMMUNITY_COMMENT = "community_comment"
SUPPORTED_MEDIA_LINK_RESOURCE_TYPES = frozenset(
    {
        MEDIA_RESOURCE_TASK,
        MEDIA_RESOURCE_DOCS_NATIVE_PAGE,
        MEDIA_RESOURCE_COMMUNITY_POST,
        MEDIA_RESOURCE_COMMUNITY_COMMENT,
    }
)


def media_ids_from_urls(urls: Iterable[str]) -> list[str]:
    media_ids: list[str] = []
    for url in urls:
        match = MEDIA_ID_PATTERN.fullmatch(url)
        if match:
            media_ids.append(match.group(1))
    return media_ids


def can_resolve_media(db: Session, user: User, media: MediaFile) -> bool:
    """Return whether ``user`` can render a resolved URL for ``media``."""
    if media.resource_type is None:
        return media.uploaded_by_id == user.id

    if media.resource_type == MEDIA_RESOURCE_TASK:
        return _can_access_task_resource(db, user, media.resource_id)

    if media.resource_type == MEDIA_RESOURCE_DOCS_NATIVE_PAGE:
        return can_access_docs_native_page(
            db,
            user,
            media.resource_id,
            require_edit=False,
        )

    if media.resource_type == MEDIA_RESOURCE_COMMUNITY_POST:
        return _can_access_community_post_resource(db, user, media.resource_id)

    if media.resource_type == MEDIA_RESOURCE_COMMUNITY_COMMENT:
        return _can_access_community_comment_resource(db, user, media.resource_id)

    return media.uploaded_by_id == user.id


def ensure_media_link_resource_access(
    db: Session,
    user: User,
    resource_type: str,
    resource_id: str,
) -> None:
    if resource_type == MEDIA_RESOURCE_TASK:
        _ensure_task_access(db, user, resource_id)
        return

    if resource_type == MEDIA_RESOURCE_DOCS_NATIVE_PAGE:
        _ensure_docs_native_page_access(db, user, resource_id)
        return

    if resource_type == MEDIA_RESOURCE_COMMUNITY_POST:
        _ensure_community_post_edit_access(db, user, resource_id)
        return

    if resource_type == MEDIA_RESOURCE_COMMUNITY_COMMENT:
        _ensure_community_comment_edit_access(db, user, resource_id)
        return

    raise localized_http_exception(
        status_code=400,
        code="media.unsupported_resource_type",
    )


def _can_access_task_resource(db: Session, user: User, task_id: str | None) -> bool:
    if task_id is None:
        return False

    from open_work_hub_api.domains.pms.models import Task, TaskList

    task = db.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        return False
    task_list = db.scalar(select(TaskList).where(TaskList.id == task.list_id))
    return _has_space_access(db, user, task_list.team_id if task_list else None)


def _ensure_task_access(db: Session, user: User, task_id: str) -> None:
    from open_work_hub_api.domains.pms.models import Task, TaskList

    task = db.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        raise localized_http_exception(status_code=404, code="pms.task_not_found")
    task_list = db.scalar(select(TaskList).where(TaskList.id == task.list_id))
    if not _has_space_access(db, user, task_list.team_id if task_list else None):
        raise localized_http_exception(
            status_code=403,
            code="media.task_list_space_access_required",
        )


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


def can_access_docs_native_page(
    db: Session,
    user: User,
    page_id: str | None,
    *,
    require_edit: bool,
) -> bool:
    if page_id is None:
        return False

    page = db.scalar(
        select(NativeDocPage)
        .options(joinedload(NativeDocPage.doc))
        .where(NativeDocPage.id == page_id)
    )
    if (
        page is None
        or page.doc is None
        or page.trashed_at is not None
        or page.doc.trashed_at is not None
    ):
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
        for target in page.doc.targets:
            projection = project_target_access(
                db=db,
                user=user,
                workspace=workspace,
                ref=TargetRef(
                    app=target.target_app,
                    type=target.target_type,
                    id=target.target_id,
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
    if not can_access_docs_native_page(db, user, page_id, require_edit=True):
        raise localized_http_exception(
            status_code=403,
            code="docs.doc_edit_access_required",
        )


def _can_access_community_post_resource(
    db: Session,
    user: User,
    post_id: str | None,
) -> bool:
    if post_id is None:
        return False

    from open_work_hub_api.domains.community.models import CommunityPost

    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id))
    if post is None:
        return False
    if post.channel is not None and post.channel.admin_only_content:
        return is_platform_admin_user(user, db)
    if not post.is_secret:
        return True
    return post.author_id == user.id or is_platform_admin_user(user, db)


def _can_access_community_comment_resource(
    db: Session,
    user: User,
    comment_id: str | None,
) -> bool:
    if comment_id is None:
        return False

    from open_work_hub_api.domains.community.models import CommunityComment

    comment = db.scalar(select(CommunityComment).where(CommunityComment.id == comment_id))
    if comment is None or comment.is_deleted:
        return False
    return _can_access_community_post_resource(db, user, comment.post_id)


def _ensure_community_post_edit_access(
    db: Session,
    user: User,
    post_id: str,
) -> None:
    from open_work_hub_api.domains.community.models import CommunityPost

    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id))
    if post is None:
        raise localized_http_exception(status_code=404, code="community.post_not_found")
    if post.author_id == user.id or is_platform_admin_user(user, db):
        return
    raise localized_http_exception(status_code=403, code="community.not_author")


def _ensure_community_comment_edit_access(
    db: Session,
    user: User,
    comment_id: str,
) -> None:
    from open_work_hub_api.domains.community.models import CommunityComment

    comment = db.scalar(select(CommunityComment).where(CommunityComment.id == comment_id))
    if comment is None or comment.is_deleted:
        raise localized_http_exception(
            status_code=404,
            code="community.comment_not_found",
        )
    if comment.author_id == user.id or is_platform_admin_user(user, db):
        return
    raise localized_http_exception(status_code=403, code="community.not_author")
