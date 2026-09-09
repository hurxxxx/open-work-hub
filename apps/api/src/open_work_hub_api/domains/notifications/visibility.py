from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import Select

from open_work_hub_api.domains.auth.access import is_platform_admin_user
from open_work_hub_api.domains.auth.app_gate import (
    allowed_app_ids,
)
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.community.models import CommunityPost
from open_work_hub_api.domains.pms.models import Notification
from open_work_hub_api.domains.source_access import SourceAclPolicy

NOTIFICATION_SCAN_BATCH_SIZE = 200


def notification_is_visible(
    db: Session,
    *,
    notification: Notification,
    user: User,
) -> bool:
    """Revalidate app context and source ACL for a global notification."""

    return bool(visible_notifications(db, user=user, rows=[notification]))


def visible_notifications(
    db: Session,
    *,
    user: User,
    rows: list[Notification],
) -> list[Notification]:
    """Filter one bounded batch with app and source checks grouped by context."""

    owned_rows = [
        row
        for row in rows
        if row.user_id == user.id and row.type != "dm_message" and row.origin_app_id
    ]
    enabled_app_ids = allowed_app_ids(db, user_id=user.id)
    candidates = [row for row in owned_rows if row.origin_app_id in enabled_app_ids]

    allowed_notification_ids: set[str] = set()
    pms_rows = [
        row
        for row in candidates
        if row.origin_app_id == "pms" and row.source_type == "pms_task" and row.source_id
    ]
    community_rows = [
        row
        for row in candidates
        if row.origin_app_id == "community"
        and row.source_type == "community_post"
        and row.source_id
    ]
    policy = SourceAclPolicy.for_user(db, user=user)
    allowed_sources = policy.authorize_many_resources(
        ("pms_task", row.source_id) for row in pms_rows
    )
    allowed_notification_ids.update(
        row.id for row in pms_rows if ("pms_task", row.source_id) in allowed_sources
    )

    if community_rows:
        source_ids = {row.source_id for row in community_rows if row.source_id is not None}
        posts_by_id = {
            post.id: post
            for post in db.scalars(
                select(CommunityPost)
                .options(joinedload(CommunityPost.channel))
                .where(CommunityPost.id.in_(source_ids))
            )
        }
        viewer_is_admin = is_platform_admin_user(user, db)
        for row in community_rows:
            post = posts_by_id.get(row.source_id)
            if post is None or post.channel is None or not post.channel.active:
                continue
            if post.channel.admin_only_content and not viewer_is_admin:
                continue
            if not post.is_secret or viewer_is_admin or post.author_id == user.id:
                allowed_notification_ids.add(row.id)

    return [row for row in rows if row.id in allowed_notification_ids]


def iter_visible_notification_batches(
    db: Session,
    *,
    user: User,
    statement: Select[tuple[Notification]],
    batch_size: int = NOTIFICATION_SCAN_BATCH_SIZE,
) -> Iterator[list[Notification]]:
    """Stream and authorize notifications without materializing a user's history."""

    batch: list[Notification] = []
    for row in db.scalars(statement.execution_options(yield_per=batch_size)):
        batch.append(row)
        if len(batch) == batch_size:
            yield visible_notifications(db, user=user, rows=batch)
            batch = []
    if batch:
        yield visible_notifications(db, user=user, rows=batch)


__all__ = [
    "NOTIFICATION_SCAN_BATCH_SIZE",
    "iter_visible_notification_batches",
    "notification_is_visible",
    "visible_notifications",
]
