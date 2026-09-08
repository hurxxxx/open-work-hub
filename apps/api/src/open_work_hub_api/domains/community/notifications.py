from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from open_work_hub_api.core.app_routes import InternalAppLocation, build_app_href
from open_work_hub_api.domains.auth.access import is_platform_admin_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.notifications import realtime_event_types as notification_event_types
from open_work_hub_api.domains.notifications import service as notification_service
from open_work_hub_api.domains.notifications.visibility import notification_is_visible
from open_work_hub_api.domains.pms.models import Notification

from .models import CommunityComment, CommunityPost

DEFAULT_CHANNEL_KEY = "suggestions"


COMMENT_PREVIEW_MAX_LENGTH = 180
COMMENT_PREVIEW_SUFFIX = "..."


class CommunityNotificationPublisher(Protocol):
    def publish_notification(
        self,
        user_id: str,
        *,
        event_type: str,
        notification: dict[str, object] | None,
        unread_count: int,
    ) -> None: ...


@dataclass(frozen=True)
class CommunityCommentNotificationResult:
    notification: Notification


def create_comment_notification(
    db: Session,
    *,
    post: CommunityPost,
    comment: CommunityComment,
    author: User,
) -> CommunityCommentNotificationResult | None:
    if post.author_id == author.id:
        return None
    recipient = post.author or db.get(User, post.author_id)
    if recipient is None or recipient.status != "active":
        return None
    if (
        post.channel is not None
        and post.channel.admin_only_content
        and not is_platform_admin_user(recipient, db)
    ):
        return None

    action_url = _community_post_url(post)
    title, body = _notification_copy(
        recipient=recipient,
        post=post,
        comment=comment,
        author=author,
    )
    notification = Notification(
        id=new_id(),
        user_id=recipient.id,
        type="community_comment",
        title=title,
        body=body,
        source_type="community_post",
        source_id=post.id,
        origin_app_id="community",
        action_url=action_url,
    )
    db.add(notification)
    db.flush()
    return CommunityCommentNotificationResult(
        notification=notification,
    )


def publish_comment_notification(
    db: Session,
    *,
    result: CommunityCommentNotificationResult | None,
    events: CommunityNotificationPublisher | None,
) -> None:
    if result is None or events is None:
        return
    recipient = db.get(User, result.notification.user_id)
    if recipient is None or not notification_is_visible(
        db,
        notification=result.notification,
        user=recipient,
    ):
        return
    events.publish_notification(
        result.notification.user_id,
        event_type=notification_event_types.NOTIFICATION_CREATED,
        notification=notification_service.serialize_notification(result.notification).model_dump(
            mode="json"
        ),
        unread_count=notification_service.unread_count(db, result.notification.user_id),
    )


def _notification_copy(
    *,
    recipient: User,
    post: CommunityPost,
    comment: CommunityComment,
    author: User,
) -> tuple[str, str]:
    preview = _comment_preview(comment.body)
    author_label = _comment_author_label(comment=comment, author=author, locale=recipient.locale)
    if recipient.locale == "en-US":
        return (
            "New comment on your community post",
            f'{author_label} commented on "{post.title}": {preview}',
        )
    actor = "익명 사용자가" if comment.is_anonymous else f"{author_label}님이"
    return (
        "내 커뮤니티 글에 댓글이 달렸습니다",
        f'{actor} "{post.title}"에 댓글을 남겼습니다: {preview}',
    )


def _comment_author_label(*, comment: CommunityComment, author: User, locale: str) -> str:
    if comment.is_anonymous:
        return "Anonymous user" if locale == "en-US" else "익명 사용자"
    return author.display_name or author.full_name or author.email


def _comment_preview(body: str) -> str:
    compact = " ".join(body.split())
    if len(compact) <= COMMENT_PREVIEW_MAX_LENGTH:
        return compact
    return (
        compact[: COMMENT_PREVIEW_MAX_LENGTH - len(COMMENT_PREVIEW_SUFFIX)].rstrip()
        + COMMENT_PREVIEW_SUFFIX
    )


def _community_post_url(post: CommunityPost) -> str:
    channel_key = post.channel.key if post.channel is not None else DEFAULT_CHANNEL_KEY
    return build_app_href(
        InternalAppLocation(
            route_id="community.post",
            path_params={"postId": post.id},
            query_params={"channel": channel_key if channel_key != DEFAULT_CHANNEL_KEY else None},
        )
    )
