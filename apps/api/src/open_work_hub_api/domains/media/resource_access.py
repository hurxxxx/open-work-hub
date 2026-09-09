"""Access rules for resolving and linking embedded media resources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import (
    is_platform_admin_user,
)
from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
)
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.docs.models import (
    NativeDocPage,
)
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.service import MEDIA_ID_PATTERN
from open_work_hub_api.domains.pms.space_models import Team

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


@dataclass(frozen=True)
class MediaAccessContext:
    owner_app_id: str
    execution_context_kind: Literal["personal", "company"]
    route_id: str | None
    source_type: str
    source_id: str
    source_version: str
    community_post_id: str | None = None


def resolve_media_access_context(
    db: Session,
    media: MediaFile,
) -> MediaAccessContext | None:
    if media.resource_type is None:
        return MediaAccessContext(
            owner_app_id="shell",
            execution_context_kind="personal",
            route_id=None,
            source_type="media_upload",
            source_id=media.id,
            source_version=_media_source_version(media.created_at),
        )
    if media.resource_type == MEDIA_RESOURCE_TASK and media.resource_id:
        from open_work_hub_api.domains.pms.models import Task, TaskList

        row = db.execute(
            select(Task.updated_at)
            .select_from(Task)
            .join(TaskList, Task.list_id == TaskList.id)
            .join(Team, TaskList.team_id == Team.id)
            .where(Task.id == media.resource_id)
        ).first()
        if row is None:
            return None
        return MediaAccessContext(
            owner_app_id="pms",
            execution_context_kind="company",
            route_id=None,
            source_type="pms_task",
            source_id=media.resource_id,
            source_version=_media_source_version(row.updated_at),
        )
    if media.resource_type == MEDIA_RESOURCE_DOCS_NATIVE_PAGE and media.resource_id:
        page = db.scalar(
            select(NativeDocPage)
            .options(joinedload(NativeDocPage.doc))
            .where(NativeDocPage.id == media.resource_id)
        )
        if page is None or page.doc is None or page.trashed_at is not None:
            return None
        return MediaAccessContext(
            owner_app_id="docs",
            execution_context_kind="company",
            route_id=None,
            source_type="native_doc",
            source_id=page.doc_id,
            source_version=_media_source_version(page.updated_at, page.doc.updated_at),
        )
    if (
        media.resource_type
        in {
            MEDIA_RESOURCE_COMMUNITY_POST,
            MEDIA_RESOURCE_COMMUNITY_COMMENT,
        }
        and media.resource_id
    ):
        from open_work_hub_api.domains.community.models import (
            CommunityComment,
            CommunityPost,
        )

        if media.resource_type == MEDIA_RESOURCE_COMMUNITY_POST:
            post = db.scalar(
                select(CommunityPost)
                .options(joinedload(CommunityPost.channel))
                .where(CommunityPost.id == media.resource_id)
            )
            comment_updated_at = None
        else:
            comment = db.scalar(
                select(CommunityComment)
                .options(joinedload(CommunityComment.post).joinedload(CommunityPost.channel))
                .where(CommunityComment.id == media.resource_id)
            )
            if comment is None or comment.is_deleted:
                return None
            post = comment.post
            comment_updated_at = comment.updated_at
        if post is None or post.channel is None or not post.channel.active:
            return None
        policy_fingerprint = _media_source_version(
            post.updated_at,
            comment_updated_at,
            post.channel.updated_at,
            post.is_secret,
            post.password_hash,
            post.channel.admin_only_content,
        )
        return MediaAccessContext(
            owner_app_id="community",
            execution_context_kind="company",
            route_id="community.post",
            source_type=media.resource_type,
            source_id=media.resource_id,
            source_version=policy_fingerprint,
            community_post_id=post.id,
        )
    return None


def _media_source_version(*values: object) -> str:
    payload = json.dumps(values, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def media_owner_app_enabled(db: Session, *, user: User, context: MediaAccessContext) -> bool:
    if context.owner_app_id == "shell":
        return True
    if context.execution_context_kind == "company":
        return can_use_app(
            db,
            app_id=context.owner_app_id,
            user_id=user.id,
        )
    return can_use_app(
        db,
        app_id=context.owner_app_id,
        user_id=user.id,
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

    return False


def ensure_media_link_resource_access(
    db: Session,
    user: User,
    resource_type: str,
    resource_id: str,
) -> None:
    if resource_type not in SUPPORTED_MEDIA_LINK_RESOURCE_TYPES:
        raise localized_http_exception(status_code=400, code="media.unsupported_resource_type")
    context = resolve_media_access_context(
        db,
        MediaFile(resource_type=resource_type, resource_id=resource_id),
    )
    if context is None:
        raise localized_http_exception(status_code=404, code="media.not_found")
    if not media_owner_app_enabled(db, user=user, context=context):
        raise localized_http_exception(status_code=403, code="platform.app_disabled")
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

    from open_work_hub_api.domains.source_access import can_read_pms_task

    return can_read_pms_task(db, user=user, task_id=task_id)


def _ensure_task_access(db: Session, user: User, task_id: str) -> None:
    from open_work_hub_api.domains.pms.access import (
        SPACE_TEAM_EDITOR_ROLES,
        resolve_pms_space_role,
    )
    from open_work_hub_api.domains.pms.models import Task, TaskList

    task = db.scalar(select(Task).where(Task.id == task_id))
    if task is None:
        raise localized_http_exception(status_code=404, code="pms.task_not_found")
    task_list = db.scalar(select(TaskList).where(TaskList.id == task.list_id))
    team = db.get(Team, task_list.team_id) if task_list else None
    if (
        team is None
        or not _can_access_task_resource(db, user, task_id)
        or resolve_pms_space_role(db, user, team) not in SPACE_TEAM_EDITOR_ROLES
    ):
        raise localized_http_exception(
            status_code=403,
            code="media.task_list_space_access_required",
        )


def can_access_docs_native_page(
    db: Session, user: User, page_id: str, *, require_edit: bool = False
) -> bool:
    from open_work_hub_api.domains.docs.access_context import resolve_native_doc_access

    page = db.scalar(
        select(NativeDocPage).where(NativeDocPage.id == page_id, NativeDocPage.trashed_at.is_(None))
    )
    if page is None or page.doc is None or page.doc.trashed_at is not None:
        return False
    access = resolve_native_doc_access(db, doc=page.doc, user=user)
    return access.can_edit if require_edit else access.can_view


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
    if post is None or post.channel is None or not post.channel.active:
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
