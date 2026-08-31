from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import is_platform_admin_user
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.workspace_app_gate import require_platform_app_enabled
from open_work_hub_api.domains.content_access.dependencies import require_content_grant_issuer
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer
from open_work_hub_api.domains.community.app_catalog import COMMUNITY_WORKSPACE_APP
from open_work_hub_api.domains.dm import realtime_events

from . import service
from .models import CommunityChannel, CommunityComment, CommunityPost
from .schemas import (
    CommunityChannelCreateRequest,
    CommunityChannelOut,
    CommunityChannelUpdateRequest,
    CommunityChannelsResponse,
    CommunityCommentCreateRequest,
    CommunityCommentOut,
    CommunityCommentUpdateRequest,
    CommunityMediaResolveRequest,
    CommunityMediaResolveResponse,
    CommunityPostCreateRequest,
    CommunityPostDetail,
    CommunityPostListResponse,
    CommunityPostOut,
    CommunityPostUpdateRequest,
    CommunityUnlockRequest,
)

require_community_app_enabled = require_platform_app_enabled(
    COMMUNITY_WORKSPACE_APP.app_id,
    error_code="platform.app_disabled",
)

router = APIRouter(
    prefix="/community",
    tags=["community"],
    dependencies=[Depends(require_community_app_enabled)],
)


def _community_events(request: Request, db: Session) -> realtime_events.DmEventPublisher:
    return realtime_events.DmEventPublisher(db=db, realtime=request.app.state.app_realtime)


def _get_channel_or_404(db: Session, channel_key: str) -> CommunityChannel:
    channel = service.get_channel_by_key(db, channel_key)
    if channel is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="community.channel_not_found",
        )
    return channel


def _get_admin_channel_or_404(db: Session, channel_key: str) -> CommunityChannel:
    channel = service.get_channel_by_key(db, channel_key, active_only=False)
    if channel is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="community.channel_not_found",
        )
    return channel


def _get_post_or_404(
    db: Session,
    *,
    post_id: str,
) -> CommunityPost:
    post = service.load_post(db, post_id=post_id)
    if post is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="community.post_not_found",
        )
    return post


def _get_comment_or_404(
    db: Session,
    *,
    post_id: str,
    comment_id: str,
) -> CommunityComment:
    comment = service.load_comment(db, post_id=post_id, comment_id=comment_id)
    if comment is None or comment.is_deleted:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="community.comment_not_found",
        )
    return comment


def _require_author_or_admin(author_id: str, user: User, *, is_admin: bool) -> None:
    if author_id == user.id or is_admin:
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="community.not_author",
    )


def _require_platform_admin(user: User, db: Session) -> None:
    if is_platform_admin_user(user, db):
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="admin.platform_admin_required",
    )


def _channel_key_exists() -> NoReturn:
    raise localized_http_exception(
        status_code=status.HTTP_409_CONFLICT,
        code="community.channel_key_exists",
    )


def _channel_delete_blocked() -> NoReturn:
    raise localized_http_exception(
        status_code=status.HTTP_409_CONFLICT,
        code="community.channel_delete_blocked",
    )


def _channel_read_only() -> NoReturn:
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="community.channel_read_only",
    )


def _require_channel_writable(
    channel: CommunityChannel | None,
    *,
    is_admin: bool,
) -> None:
    if channel is not None and channel.read_only and not is_admin:
        _channel_read_only()


@router.get("/channels", response_model=CommunityChannelsResponse)
def list_community_channels(
    db: Session = Depends(get_db_session),
) -> CommunityChannelsResponse:
    return service.list_channels(db)


@router.get("/admin/channels", response_model=CommunityChannelsResponse)
def list_community_admin_channels(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityChannelsResponse:
    _require_platform_admin(current_user, db)
    return service.list_channels(db, include_inactive=True)


@router.post(
    "/admin/channels",
    response_model=CommunityChannelOut,
    status_code=status.HTTP_201_CREATED,
)
def create_community_channel(
    payload: CommunityChannelCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityChannelOut:
    _require_platform_admin(current_user, db)
    try:
        return service.create_channel(
            db,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            position=payload.position,
            active=payload.active,
            read_only=payload.read_only,
            force_anonymous=payload.force_anonymous,
            admin_only_content=payload.admin_only_content,
            template_title=payload.template_title,
            template_body=payload.template_body,
        )
    except service.CommunityChannelKeyExistsError:
        _channel_key_exists()


@router.patch("/admin/channels/{channel_key}", response_model=CommunityChannelOut)
def update_community_channel(
    channel_key: str,
    payload: CommunityChannelUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityChannelOut:
    _require_platform_admin(current_user, db)
    channel = _get_admin_channel_or_404(db, channel_key)
    try:
        return service.update_channel(
            db,
            channel=channel,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            position=payload.position,
            active=payload.active,
            read_only=payload.read_only,
            force_anonymous=payload.force_anonymous,
            admin_only_content=payload.admin_only_content,
            template_title=payload.template_title,
            template_body=payload.template_body,
        )
    except service.CommunityChannelKeyExistsError:
        _channel_key_exists()


@router.delete("/admin/channels/{channel_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community_channel(
    channel_key: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _require_platform_admin(current_user, db)
    channel = _get_admin_channel_or_404(db, channel_key)
    try:
        service.delete_channel(db, channel=channel)
    except service.CommunityChannelDeleteBlockedError:
        _channel_delete_blocked()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/channels/{channel_key}/posts",
    response_model=CommunityPostListResponse,
)
def list_community_posts(
    channel_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    q: str | None = Query(None, max_length=120),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityPostListResponse:
    channel = _get_channel_or_404(db, channel_key)
    return service.list_posts(
        db,
        channel=channel,
        viewer_id=current_user.id,
        viewer_is_admin=is_platform_admin_user(current_user, db),
        page=page,
        page_size=page_size,
        search=q,
    )


@router.post(
    "/channels/{channel_key}/posts",
    response_model=CommunityPostOut,
    status_code=status.HTTP_201_CREATED,
)
def create_community_post(
    channel_key: str,
    payload: CommunityPostCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityPostOut:
    channel = _get_channel_or_404(db, channel_key)
    is_admin = is_platform_admin_user(current_user, db)
    _require_channel_writable(channel, is_admin=is_admin)
    if (
        payload.is_secret
        and not channel.admin_only_content
        and not (payload.password or "").strip()
    ):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="community.password_required",
        )
    return service.create_post(
        db,
        channel=channel,
        author=current_user,
        title=payload.title,
        body=payload.body,
        is_anonymous=payload.is_anonymous,
        is_secret=payload.is_secret,
        password=payload.password,
    )


@router.get("/posts/{post_id}", response_model=CommunityPostDetail)
def get_community_post(
    post_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityPostDetail:
    post = _get_post_or_404(db, post_id=post_id)
    is_admin = is_platform_admin_user(current_user, db)
    detail = service.get_post_detail(
        db,
        post_id=post.id,
        unlocked=is_admin or post.author_id == current_user.id,
        viewer_id=current_user.id,
        viewer_is_admin=is_admin,
    )
    if detail is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="community.post_not_found",
        )
    return detail


@router.patch("/posts/{post_id}", response_model=CommunityPostOut)
def update_community_post(
    post_id: str,
    payload: CommunityPostUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityPostOut:
    post = _get_post_or_404(db, post_id=post_id)
    is_admin = is_platform_admin_user(current_user, db)
    _require_author_or_admin(post.author_id, current_user, is_admin=is_admin)
    _require_channel_writable(post.channel, is_admin=is_admin)
    return service.update_post(
        db,
        post=post,
        title=payload.title,
        body=payload.body,
        user=current_user,
        viewer_is_admin=is_admin,
    )


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community_post(
    post_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    post = _get_post_or_404(db, post_id=post_id)
    is_admin = is_platform_admin_user(current_user, db)
    _require_author_or_admin(post.author_id, current_user, is_admin=is_admin)
    _require_channel_writable(post.channel, is_admin=is_admin)
    service.delete_post(db, post=post)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/posts/{post_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_community_post_read(
    post_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    post = _get_post_or_404(db, post_id=post_id)
    locked_reason = service.post_read_locked_reason(
        post,
        viewer_id=current_user.id,
        viewer_is_admin=is_platform_admin_user(current_user, db),
    )
    if locked_reason == service.LOCKED_REASON_ADMIN_ONLY:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="community.admin_only_content",
        )
    if locked_reason is not None:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="community.invalid_password",
        )
    service.mark_post_read(db, post=post, user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/posts/{post_id}/unlock", response_model=CommunityPostDetail)
def unlock_community_post(
    post_id: str,
    payload: CommunityUnlockRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityPostDetail:
    post = _get_post_or_404(db, post_id=post_id)
    is_admin = is_platform_admin_user(current_user, db)
    if (
        service.post_read_locked_reason(
            post,
            viewer_id=current_user.id,
            viewer_is_admin=is_admin,
        )
        == service.LOCKED_REASON_ADMIN_ONLY
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="community.admin_only_content",
        )
    if not service.verify_post_password(post, payload.password):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="community.invalid_password",
        )
    service.mark_post_read(db, post=post, user_id=current_user.id)
    detail = service.get_post_detail(
        db,
        post_id=post.id,
        unlocked=True,
        viewer_id=current_user.id,
        viewer_is_admin=is_admin,
    )
    if detail is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="community.post_not_found",
        )
    return detail


@router.post(
    "/posts/{post_id}/media/resolve",
    response_model=CommunityMediaResolveResponse,
)
def resolve_community_post_media(
    post_id: str,
    payload: CommunityMediaResolveRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> CommunityMediaResolveResponse:
    post = _get_post_or_404(db, post_id=post_id)
    try:
        return service.resolve_post_media_urls(
            db,
            post=post,
            urls=payload.urls,
            viewer=current_user,
            viewer_is_admin=is_platform_admin_user(current_user, db),
            content_grant_issuer=content_grant_issuer,
            password=payload.password,
        )
    except service.CommunityMediaAccessDeniedError:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="community.invalid_password",
        )


@router.post(
    "/posts/{post_id}/comments",
    response_model=CommunityCommentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_community_comment(
    post_id: str,
    payload: CommunityCommentCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityCommentOut:
    post = _get_post_or_404(db, post_id=post_id)
    is_admin = is_platform_admin_user(current_user, db)
    _require_channel_writable(post.channel, is_admin=is_admin)
    if post.channel and post.channel.admin_only_content and not is_admin:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="community.admin_only_content",
        )
    if (
        post.is_secret
        and post.author_id != current_user.id
        and not is_admin
        and not service.verify_post_password(post, payload.password)
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="community.invalid_password",
        )
    parent_comment_id: str | None = None
    if payload.parent_comment_id:
        parent = _get_comment_or_404(
            db,
            post_id=post.id,
            comment_id=payload.parent_comment_id,
        )
        parent_comment_id = parent.parent_comment_id or parent.id
    return service.create_comment(
        db,
        post=post,
        author=current_user,
        body=payload.body,
        is_anonymous=payload.is_anonymous,
        parent_comment_id=parent_comment_id,
        viewer_is_admin=is_admin,
        events=_community_events(request, db),
    )


@router.patch(
    "/posts/{post_id}/comments/{comment_id}",
    response_model=CommunityCommentOut,
)
def update_community_comment(
    post_id: str,
    comment_id: str,
    payload: CommunityCommentUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CommunityCommentOut:
    post = _get_post_or_404(db, post_id=post_id)
    comment = _get_comment_or_404(db, post_id=post_id, comment_id=comment_id)
    is_admin = is_platform_admin_user(current_user, db)
    _require_author_or_admin(comment.author_id, current_user, is_admin=is_admin)
    _require_channel_writable(post.channel, is_admin=is_admin)
    return service.update_comment(
        db,
        comment=comment,
        body=payload.body,
        user=current_user,
        viewer_is_admin=is_admin,
    )


@router.delete(
    "/posts/{post_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_community_comment(
    post_id: str,
    comment_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    post = _get_post_or_404(db, post_id=post_id)
    comment = _get_comment_or_404(db, post_id=post_id, comment_id=comment_id)
    is_admin = is_platform_admin_user(current_user, db)
    _require_author_or_admin(comment.author_id, current_user, is_admin=is_admin)
    _require_channel_writable(post.channel, is_admin=is_admin)
    service.delete_comment(db, comment=comment)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
