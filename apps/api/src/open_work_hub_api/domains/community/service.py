from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.elements import ColumnElement

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import hash_password, new_id, verify_password
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.content_access import build_media_content_url
from open_work_hub_api.domains.media.resource_access import (
    MEDIA_RESOURCE_COMMUNITY_COMMENT,
    MEDIA_RESOURCE_COMMUNITY_POST,
    media_ids_from_urls,
)
from open_work_hub_api.domains.media.service import sync_embedded_media

from . import notifications as comment_notifications
from .models import (
    CommunityChannel,
    CommunityComment,
    CommunityPost,
    CommunityPostRead,
    utcnow_naive,
)
from .schemas import (
    CommunityChannelOut,
    CommunityChannelsResponse,
    CommunityCommentOut,
    CommunityMediaResolveResponse,
    CommunityPostDetail,
    CommunityPostListResponse,
    CommunityPostOut,
)

DEFAULT_CHANNEL_KEY = "suggestions"
DEFAULT_CHANNEL_NAME = "Suggestions"
DEFAULT_CHANNEL_DESCRIPTION = "Ideas, requests, and improvement threads."
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
LOCKED_REASON_PASSWORD = "password"
LOCKED_REASON_ADMIN_ONLY = "admin_only"


class CommunityChannelKeyExistsError(Exception):
    pass


class CommunityChannelDeleteBlockedError(Exception):
    pass


class CommunityMediaAccessDeniedError(Exception):
    pass


def _display_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.display_name or user.full_name or None


def _resolve_names(db: Session, author_ids: set[str]) -> dict[str, str | None]:
    if not author_ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(author_ids))).all()
    return {user.id: _display_name(user) for user in rows}


def _channel_force_anonymous(channel: CommunityChannel | None) -> bool:
    return bool(channel and channel.force_anonymous)


def _channel_admin_only_content(channel: CommunityChannel | None) -> bool:
    return bool(channel and channel.admin_only_content)


def _channel_read_only(channel: CommunityChannel | None) -> bool:
    return bool(channel and channel.read_only)


def _post_is_anonymous(post: CommunityPost) -> bool:
    return post.is_anonymous or _channel_force_anonymous(post.channel)


def _post_author_name_visible(post: CommunityPost, *, viewer_is_admin: bool) -> bool:
    if viewer_is_admin:
        return True
    if _channel_admin_only_content(post.channel):
        return False
    return not _post_is_anonymous(post)


def _post_search_filter(
    channel: CommunityChannel,
    *,
    search: str | None,
    viewer_is_admin: bool,
) -> tuple[ColumnElement[bool] | None, bool]:
    query = (search or "").strip()
    if not query:
        return None, False

    pattern = f"%{query}%"
    conditions = []
    needs_author_join = False

    if viewer_is_admin or not channel.admin_only_content:
        conditions.append(CommunityPost.title.ilike(pattern))

    if viewer_is_admin or not channel.force_anonymous:
        needs_author_join = True
        author_match = or_(
            User.display_name.ilike(pattern),
            User.full_name.ilike(pattern),
        )
        if not viewer_is_admin:
            author_match = and_(CommunityPost.is_anonymous.is_(False), author_match)
        conditions.append(author_match)

    if not conditions:
        return false(), False
    return or_(*conditions), needs_author_join


def _comment_is_anonymous(comment: CommunityComment, *, force_anonymous: bool) -> bool:
    return comment.is_anonymous or force_anonymous


def _post_locked_reason(
    post: CommunityPost,
    *,
    unlocked: bool,
    viewer_is_admin: bool,
) -> str | None:
    if _channel_admin_only_content(post.channel) and not viewer_is_admin:
        return LOCKED_REASON_ADMIN_ONLY
    if post.is_secret and not unlocked:
        return LOCKED_REASON_PASSWORD
    return None


def post_read_locked_reason(
    post: CommunityPost,
    *,
    viewer_id: str,
    viewer_is_admin: bool,
) -> str | None:
    return _post_locked_reason(
        post,
        unlocked=viewer_is_admin or post.author_id == viewer_id,
        viewer_is_admin=viewer_is_admin,
    )


def _upsert_post_read(
    db: Session,
    *,
    post_id: str,
    user_id: str,
    read_at: datetime | None = None,
) -> datetime:
    timestamp = read_at or utcnow_naive()
    values = {"post_id": post_id, "user_id": user_id, "read_at": timestamp}
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        statement = postgresql_insert(CommunityPostRead).values(**values)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["post_id", "user_id"],
                set_={"read_at": timestamp},
            )
        )
    elif dialect_name == "sqlite":
        statement = sqlite_insert(CommunityPostRead).values(**values)
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["post_id", "user_id"],
                set_={"read_at": timestamp},
            )
        )
    else:
        existing = db.get(CommunityPostRead, (post_id, user_id))
        if existing is None:
            db.add(CommunityPostRead(**values))
        else:
            existing.read_at = timestamp
    return timestamp


def mark_post_read(
    db: Session,
    *,
    post: CommunityPost,
    user_id: str,
) -> None:
    _upsert_post_read(db, post_id=post.id, user_id=user_id)
    db.commit()


def ensure_default_channels(db: Session) -> None:
    existing = db.scalar(
        select(CommunityChannel).where(CommunityChannel.key == DEFAULT_CHANNEL_KEY)
    )
    if existing is not None:
        return
    db.add(
        CommunityChannel(
            id=new_id(),
            key=DEFAULT_CHANNEL_KEY,
            name=DEFAULT_CHANNEL_NAME,
            description=DEFAULT_CHANNEL_DESCRIPTION,
            position=0,
            active=True,
        )
    )
    db.flush()


def get_channel_by_key(
    db: Session,
    channel_key: str,
    *,
    active_only: bool = True,
) -> CommunityChannel | None:
    ensure_default_channels(db)
    query = select(CommunityChannel).where(CommunityChannel.key == channel_key)
    if active_only:
        query = query.where(CommunityChannel.active.is_(True))
    return db.scalar(query)


def _channel_out(channel: CommunityChannel) -> CommunityChannelOut:
    return CommunityChannelOut(
        id=channel.id,
        key=channel.key,
        name=channel.name,
        description=channel.description,
        position=channel.position,
        active=channel.active,
        read_only=channel.read_only,
        force_anonymous=channel.force_anonymous,
        admin_only_content=channel.admin_only_content,
        template_title=channel.template_title,
        template_body=channel.template_body,
    )


def list_channels(
    db: Session,
    *,
    include_inactive: bool = False,
) -> CommunityChannelsResponse:
    ensure_default_channels(db)
    query = select(CommunityChannel)
    if not include_inactive:
        query = query.where(CommunityChannel.active.is_(True))
    rows = db.scalars(
        query.order_by(
            CommunityChannel.position.asc(),
            CommunityChannel.name.asc(),
        )
    ).all()
    return CommunityChannelsResponse(channels=[_channel_out(row) for row in rows])


def create_channel(
    db: Session,
    *,
    key: str,
    name: str,
    description: str,
    position: int,
    active: bool,
    read_only: bool = False,
    force_anonymous: bool = False,
    admin_only_content: bool = False,
    template_title: str = "",
    template_body: str = "",
) -> CommunityChannelOut:
    ensure_default_channels(db)
    if db.scalar(select(CommunityChannel.id).where(CommunityChannel.key == key)):
        raise CommunityChannelKeyExistsError(key)
    channel = CommunityChannel(
        id=new_id(),
        key=key,
        name=name.strip(),
        description=description.strip(),
        position=position,
        active=active,
        read_only=read_only,
        force_anonymous=force_anonymous,
        admin_only_content=admin_only_content,
        template_title=template_title.strip(),
        template_body=template_body.strip(),
    )
    db.add(channel)
    db.commit()
    return _channel_out(channel)


def update_channel(
    db: Session,
    *,
    channel: CommunityChannel,
    key: str,
    name: str,
    description: str,
    position: int,
    active: bool,
    read_only: bool = False,
    force_anonymous: bool = False,
    admin_only_content: bool = False,
    template_title: str = "",
    template_body: str = "",
) -> CommunityChannelOut:
    existing_id = db.scalar(
        select(CommunityChannel.id).where(
            CommunityChannel.key == key,
            CommunityChannel.id != channel.id,
        )
    )
    if existing_id is not None:
        raise CommunityChannelKeyExistsError(key)
    channel.key = key
    channel.name = name.strip()
    channel.description = description.strip()
    channel.position = position
    channel.active = active
    channel.read_only = read_only
    channel.force_anonymous = force_anonymous
    channel.admin_only_content = admin_only_content
    channel.template_title = template_title.strip()
    channel.template_body = template_body.strip()
    db.commit()
    return _channel_out(channel)


def delete_channel(db: Session, *, channel: CommunityChannel) -> None:
    post_count = (
        db.scalar(
            select(func.count(CommunityPost.id)).where(
                CommunityPost.channel_id == channel.id,
            )
        )
        or 0
    )
    if channel.key == DEFAULT_CHANNEL_KEY or post_count > 0:
        raise CommunityChannelDeleteBlockedError(channel.key)
    db.delete(channel)
    db.commit()


def _post_out(
    post: CommunityPost,
    *,
    comment_count: int,
    names: dict[str, str | None],
    unlocked: bool,
    viewer_id: str | None,
    viewer_is_admin: bool,
    read_at: datetime | None,
) -> CommunityPostOut:
    locked_reason = _post_locked_reason(
        post,
        unlocked=unlocked,
        viewer_is_admin=viewer_is_admin,
    )
    locked = locked_reason is not None
    is_mine = viewer_id is not None and post.author_id == viewer_id
    is_anonymous = _post_is_anonymous(post)
    return CommunityPostOut(
        id=post.id,
        channel_key=post.channel.key if post.channel else DEFAULT_CHANNEL_KEY,
        title="" if locked else post.title,
        body="" if locked else post.body,
        is_anonymous=is_anonymous,
        is_secret=post.is_secret,
        locked=locked,
        locked_reason=locked_reason,
        is_read=locked_reason != LOCKED_REASON_ADMIN_ONLY
        and read_at is not None
        and read_at >= post.updated_at,
        is_mine=is_mine,
        can_modify=(viewer_is_admin or (is_mine and not _channel_read_only(post.channel)))
        and not (locked_reason == LOCKED_REASON_ADMIN_ONLY and not viewer_is_admin),
        author_name=names.get(post.author_id)
        if _post_author_name_visible(post, viewer_is_admin=viewer_is_admin)
        else None,
        comment_count=comment_count,
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def _comment_out(
    comment: CommunityComment,
    *,
    names: dict[str, str | None],
    viewer_id: str | None,
    viewer_is_admin: bool,
    anon_seq: int | None = None,
    force_anonymous: bool = False,
    channel_read_only: bool = False,
) -> CommunityCommentOut:
    is_anonymous = _comment_is_anonymous(comment, force_anonymous=force_anonymous)
    if comment.is_deleted:
        return CommunityCommentOut(
            id=comment.id,
            body="",
            is_anonymous=is_anonymous,
            is_deleted=True,
            parent_comment_id=comment.parent_comment_id,
            author_name=None,
            anon_seq=None,
            can_modify=False,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )
    is_mine = viewer_id is not None and comment.author_id == viewer_id
    return CommunityCommentOut(
        id=comment.id,
        body=comment.body,
        is_anonymous=is_anonymous,
        is_deleted=False,
        parent_comment_id=comment.parent_comment_id,
        author_name=names.get(comment.author_id) if viewer_is_admin or not is_anonymous else None,
        anon_seq=anon_seq if is_anonymous else None,
        can_modify=viewer_is_admin or (is_mine and not channel_read_only),
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


def _anon_seq_map(
    comments: list[CommunityComment],
    *,
    force_anonymous: bool = False,
) -> dict[str, int]:
    seq: dict[str, int] = {}
    for comment in comments:
        if (
            _comment_is_anonymous(comment, force_anonymous=force_anonymous)
            and comment.author_id not in seq
        ):
            seq[comment.author_id] = len(seq) + 1
    return seq


def verify_post_password(post: CommunityPost, password: str | None) -> bool:
    if not post.is_secret:
        return True
    if not password or not post.password_hash:
        return False
    return verify_password(password, post.password_hash)


def resolve_post_media_urls(
    db: Session,
    *,
    post: CommunityPost,
    urls: list[str],
    viewer: User,
    viewer_is_admin: bool,
    content_grant_issuer: ContentGrantIssuer,
    password: str | None = None,
) -> CommunityMediaResolveResponse:
    if _channel_admin_only_content(post.channel) and not viewer_is_admin:
        raise CommunityMediaAccessDeniedError(post.id)
    if (
        post.is_secret
        and post.author_id != viewer.id
        and not viewer_is_admin
        and not verify_post_password(post, password)
    ):
        raise CommunityMediaAccessDeniedError(post.id)

    media_ids = media_ids_from_urls(urls)
    if not media_ids:
        return CommunityMediaResolveResponse(resolved={})

    media_files = db.scalars(select(MediaFile).where(MediaFile.id.in_(media_ids))).all()
    if not media_files:
        return CommunityMediaResolveResponse(resolved={})

    comment_ids = {
        media.resource_id
        for media in media_files
        if media.resource_type == MEDIA_RESOURCE_COMMUNITY_COMMENT and media.resource_id
    }
    comments_by_id: dict[str, CommunityComment] = {}
    if comment_ids:
        comments_by_id = {
            comment.id: comment
            for comment in db.scalars(
                select(CommunityComment).where(CommunityComment.id.in_(comment_ids))
            ).all()
        }

    resolved: dict[str, str] = {}
    for media in media_files:
        if not _media_belongs_to_post(media, post, comments_by_id):
            continue
        password_authorized = (
            post.is_secret and post.author_id != viewer.id and not viewer_is_admin
        )
        resolved[f"media:{media.id}"] = build_media_content_url(
            db,
            user=viewer,
            media=media,
            content_grant_issuer=content_grant_issuer,
            authorization_mode=(
                "community_password" if password_authorized else "source_acl"
            ),
            authorized_community_post_id=post.id if password_authorized else None,
        )
    return CommunityMediaResolveResponse(resolved=resolved)


def _media_belongs_to_post(
    media: MediaFile,
    post: CommunityPost,
    comments_by_id: dict[str, CommunityComment],
) -> bool:
    if media.resource_type == MEDIA_RESOURCE_COMMUNITY_POST:
        return media.resource_id == post.id
    if media.resource_type != MEDIA_RESOURCE_COMMUNITY_COMMENT or not media.resource_id:
        return False
    comment = comments_by_id.get(media.resource_id)
    return comment is not None and not comment.is_deleted and comment.post_id == post.id


def list_posts(
    db: Session,
    *,
    channel: CommunityChannel,
    viewer_id: str,
    viewer_is_admin: bool,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    search: str | None = None,
) -> CommunityPostListResponse:
    bounded_page = max(1, page)
    bounded_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    filters: list[ColumnElement[bool]] = [CommunityPost.channel_id == channel.id]
    search_filter, needs_author_join = _post_search_filter(
        channel,
        search=search,
        viewer_is_admin=viewer_is_admin,
    )
    if search_filter is not None:
        filters.append(search_filter)

    count_query = select(func.count(CommunityPost.id))
    post_query = select(CommunityPost)
    if needs_author_join:
        count_query = count_query.join(User, User.id == CommunityPost.author_id)
        post_query = post_query.join(User, User.id == CommunityPost.author_id)
    total = db.scalar(count_query.where(*filters)) or 0
    posts = db.scalars(
        post_query.where(*filters)
        .options(selectinload(CommunityPost.channel))
        .order_by(CommunityPost.created_at.desc())
        .limit(bounded_page_size)
        .offset((bounded_page - 1) * bounded_page_size)
    ).all()
    if not posts:
        return CommunityPostListResponse(
            posts=[],
            total=total,
            page=bounded_page,
            page_size=bounded_page_size,
        )
    post_ids = [post.id for post in posts]
    reads = dict(
        db.execute(
            select(CommunityPostRead.post_id, CommunityPostRead.read_at).where(
                CommunityPostRead.user_id == viewer_id,
                CommunityPostRead.post_id.in_(post_ids),
            )
        ).all()
    )
    counts = dict(
        db.execute(
            select(CommunityComment.post_id, func.count(CommunityComment.id))
            .where(
                CommunityComment.post_id.in_(post_ids),
                CommunityComment.is_deleted.is_(False),
            )
            .group_by(CommunityComment.post_id)
        ).all()
    )
    if viewer_is_admin:
        author_ids = {post.author_id for post in posts}
    elif channel.force_anonymous or channel.admin_only_content:
        author_ids = set()
    else:
        author_ids = {post.author_id for post in posts if not post.is_anonymous}
    names = _resolve_names(db, author_ids)
    return CommunityPostListResponse(
        posts=[
            _post_out(
                post,
                comment_count=counts.get(post.id, 0),
                names=names,
                unlocked=False,
                viewer_id=viewer_id,
                viewer_is_admin=viewer_is_admin,
                read_at=reads.get(post.id),
            )
            for post in posts
        ],
        total=total,
        page=bounded_page,
        page_size=bounded_page_size,
    )


def create_post(
    db: Session,
    *,
    channel: CommunityChannel,
    author: User,
    title: str,
    body: str,
    is_anonymous: bool,
    is_secret: bool,
    password: str | None,
) -> CommunityPostOut:
    effective_is_secret = is_secret and not channel.admin_only_content
    post = CommunityPost(
        id=new_id(),
        channel_id=channel.id,
        author_id=author.id,
        is_anonymous=is_anonymous or channel.force_anonymous,
        is_secret=effective_is_secret,
        password_hash=hash_password(password) if effective_is_secret and password else None,
        title=title.strip(),
        body=body.strip(),
    )
    db.add(post)
    db.flush()
    _upsert_post_read(db, post_id=post.id, user_id=author.id)
    sync_embedded_media(
        db,
        post.body,
        MEDIA_RESOURCE_COMMUNITY_POST,
        post.id,
        author,
    )
    db.commit()
    return get_post_detail(
        db,
        post_id=post.id,
        unlocked=True,
        viewer_id=author.id,
        viewer_is_admin=False,
    )


def load_post(
    db: Session,
    *,
    post_id: str,
) -> CommunityPost | None:
    return db.scalar(
        select(CommunityPost)
        .where(CommunityPost.id == post_id)
        .options(selectinload(CommunityPost.channel))
    )


def get_post_detail(
    db: Session,
    *,
    post_id: str,
    unlocked: bool,
    viewer_id: str,
    viewer_is_admin: bool,
) -> CommunityPostDetail | None:
    post = load_post(db, post_id=post_id)
    if post is None:
        return None

    locked_reason = _post_locked_reason(
        post,
        unlocked=unlocked,
        viewer_is_admin=viewer_is_admin,
    )
    locked = locked_reason is not None
    force_anonymous = _channel_force_anonymous(post.channel)
    channel_read_only = _channel_read_only(post.channel)
    comments = (
        []
        if locked
        else db.scalars(
            select(CommunityComment)
            .where(CommunityComment.post_id == post_id)
            .order_by(CommunityComment.created_at.asc())
        ).all()
    )
    comment_count = (
        db.scalar(
            select(func.count(CommunityComment.id)).where(
                CommunityComment.post_id == post_id,
                CommunityComment.is_deleted.is_(False),
            )
        )
        or 0
        if locked
        else sum(1 for comment in comments if not comment.is_deleted)
    )
    author_ids: set[str] = set()
    if _post_author_name_visible(post, viewer_is_admin=viewer_is_admin):
        author_ids.add(post.author_id)
    author_ids.update(
        comment.author_id
        for comment in comments
        if viewer_is_admin or not _comment_is_anonymous(comment, force_anonymous=force_anonymous)
    )
    names = _resolve_names(db, author_ids)
    anon_seq = _anon_seq_map(comments, force_anonymous=force_anonymous)
    post_read = db.get(CommunityPostRead, (post.id, viewer_id))
    base = _post_out(
        post,
        comment_count=comment_count,
        names=names,
        unlocked=unlocked,
        viewer_id=viewer_id,
        viewer_is_admin=viewer_is_admin,
        read_at=post_read.read_at if post_read is not None else None,
    )
    return CommunityPostDetail(
        **base.model_dump(),
        comments=[
            _comment_out(
                comment,
                names=names,
                viewer_id=viewer_id,
                viewer_is_admin=viewer_is_admin,
                anon_seq=anon_seq.get(comment.author_id),
                force_anonymous=force_anonymous,
                channel_read_only=channel_read_only,
            )
            for comment in comments
        ],
    )


def update_post(
    db: Session,
    *,
    post: CommunityPost,
    title: str,
    body: str,
    user: User,
    viewer_is_admin: bool,
) -> CommunityPostOut:
    post.title = title.strip()
    post.body = body.strip()
    sync_embedded_media(
        db,
        post.body,
        MEDIA_RESOURCE_COMMUNITY_POST,
        post.id,
        user,
    )
    db.flush()
    _upsert_post_read(db, post_id=post.id, user_id=user.id)
    db.commit()
    detail = get_post_detail(
        db,
        post_id=post.id,
        unlocked=True,
        viewer_id=user.id,
        viewer_is_admin=viewer_is_admin,
    )
    assert detail is not None
    return detail


def delete_post(db: Session, *, post: CommunityPost) -> None:
    db.delete(post)
    db.commit()


def load_comment(
    db: Session,
    *,
    post_id: str,
    comment_id: str,
) -> CommunityComment | None:
    comment = db.get(CommunityComment, comment_id)
    if comment is None or comment.post_id != post_id:
        return None
    return comment


def create_comment(
    db: Session,
    *,
    post: CommunityPost,
    author: User,
    body: str,
    is_anonymous: bool,
    parent_comment_id: str | None = None,
    viewer_is_admin: bool = False,
    events: comment_notifications.CommunityNotificationPublisher | None = None,
) -> CommunityCommentOut:
    force_anonymous = _channel_force_anonymous(post.channel)
    comment = CommunityComment(
        id=new_id(),
        post_id=post.id,
        author_id=author.id,
        parent_comment_id=parent_comment_id,
        is_anonymous=is_anonymous or force_anonymous,
        body=body.strip(),
    )
    db.add(comment)
    db.flush()
    sync_embedded_media(
        db,
        comment.body,
        MEDIA_RESOURCE_COMMUNITY_COMMENT,
        comment.id,
        author,
    )
    notification_result = comment_notifications.create_comment_notification(
        db,
        post=post,
        comment=comment,
        author=author,
    )
    db.commit()
    comment_notifications.publish_comment_notification(
        db,
        result=notification_result,
        events=events,
    )
    comments = db.scalars(
        select(CommunityComment)
        .where(CommunityComment.post_id == post.id)
        .order_by(CommunityComment.created_at.asc())
    ).all()
    names = (
        {author.id: _display_name(author)}
        if viewer_is_admin or not _comment_is_anonymous(comment, force_anonymous=force_anonymous)
        else {}
    )
    return _comment_out(
        comment,
        names=names,
        viewer_id=author.id,
        viewer_is_admin=viewer_is_admin,
        anon_seq=_anon_seq_map(comments, force_anonymous=force_anonymous).get(author.id),
        force_anonymous=force_anonymous,
    )


def update_comment(
    db: Session,
    *,
    comment: CommunityComment,
    body: str,
    user: User,
    viewer_is_admin: bool,
) -> CommunityCommentOut:
    comment.body = body.strip()
    sync_embedded_media(
        db,
        comment.body,
        MEDIA_RESOURCE_COMMUNITY_COMMENT,
        comment.id,
        user,
    )
    db.commit()
    comments = db.scalars(
        select(CommunityComment)
        .where(CommunityComment.post_id == comment.post_id)
        .order_by(CommunityComment.created_at.asc())
    ).all()
    force_anonymous = _channel_force_anonymous(comment.post.channel if comment.post else None)
    names = (
        _resolve_names(db, {comment.author_id})
        if viewer_is_admin or not _comment_is_anonymous(comment, force_anonymous=force_anonymous)
        else {}
    )
    return _comment_out(
        comment,
        names=names,
        viewer_id=user.id,
        viewer_is_admin=viewer_is_admin,
        anon_seq=_anon_seq_map(comments, force_anonymous=force_anonymous).get(comment.author_id),
        force_anonymous=force_anonymous,
    )


def delete_comment(db: Session, *, comment: CommunityComment) -> None:
    comment.is_deleted = True
    comment.body = ""
    db.commit()
