from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.community import service
from open_work_hub_api.domains.community.models import (
    CommunityChannel,
    CommunityComment,
    CommunityPost,
    CommunityPostRead,
)
from open_work_hub_api.domains.dm.models import (
    DmConversation,
    DmConversationParticipant,
    DmMessage,
    DmMessageAttachment,
)
from open_work_hub_api.domains.community.router import _require_author_or_admin
from open_work_hub_api.domains.community.schemas import CommunityChannelCreateRequest
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer
from open_work_hub_api.domains.media import content_access as media_content_access
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.pms.models import Notification
from dev_accounts import auth_headers, dev_login


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite://")
    for table in (
        User.__table__,
        CommunityChannel.__table__,
        CommunityPost.__table__,
        CommunityPostRead.__table__,
        CommunityComment.__table__,
        MediaFile.__table__,
        Notification.__table__,
        DmConversation.__table__,
        DmMessage.__table__,
        DmConversationParticipant.__table__,
        DmMessageAttachment.__table__,
    ):
        table.create(engine, checkfirst=True)
    with Session(engine) as session:
        yield session


def _make_user(db: Session, name: str) -> User:
    user = User(
        id=new_id(),
        login_id=name,
        email=f"{name}@open-work-hub.local",
        full_name=name,
        display_name=name,
        password_hash="x",
    )
    db.add(user)
    db.commit()
    return user


def _content_grant_issuer(user: User) -> ContentGrantIssuer:
    return ContentGrantIssuer(user_id=user.id, session_id="test-session")


def _create_community_post(
    client: TestClient,
    *,
    token: str,
    title: str,
    body: str,
) -> dict:
    response = client.post(
        f"/api/v1/community/channels/{service.DEFAULT_CHANNEL_KEY}/posts",
        headers=auth_headers(token),
        json={
            "title": title,
            "body": body,
            "is_anonymous": False,
            "is_secret": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_admin_channel(
    client: TestClient,
    *,
    token: str,
    key: str,
    name: str,
    read_only: bool = False,
) -> dict:
    response = client.post(
        "/api/v1/community/admin/channels",
        headers=auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": "",
            "position": 1,
            "active": True,
            "readOnly": read_only,
            "forceAnonymous": False,
            "adminOnlyContent": False,
            "templateTitle": "",
            "templateBody": "",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _channel(db: Session) -> CommunityChannel:
    return service.get_channel_by_key(db, service.DEFAULT_CHANNEL_KEY)


def _media(db: Session, *, media_id: str, user: User) -> MediaFile:
    media = MediaFile(
        id=media_id,
        storage_key=f"media/{user.id}/{media_id}/screenshot.png",
        filename="screenshot.png",
        content_type="image/png",
        size_bytes=128,
        uploaded_by_id=user.id,
    )
    db.add(media)
    db.commit()
    return media


def test_default_channel_and_posts_are_company_scoped(db: Session) -> None:
    author = _make_user(db, "author")
    channel = _channel(db)

    service.create_post(
        db,
        channel=channel,
        author=author,
        title="건의합니다",
        body="첫 워크스페이스 내용",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    channels = service.list_channels(db)
    assert [item.key for item in channels.channels] == ["suggestions"]

    page = service.list_posts(
        db,
        channel=channel,
        viewer_id=author.id,
        viewer_is_admin=False,
    )

    assert page.total == 1
    assert page.posts[0].title == "건의합니다"


def test_post_read_state_is_per_user_idempotent_and_resets_for_other_users_on_edit(
    db: Session,
) -> None:
    author = _make_user(db, "author")
    reader = _make_user(db, "reader")
    channel = _channel(db)

    created = service.create_post(
        db,
        channel=channel,
        author=author,
        title="읽음 상태",
        body="최초 내용",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )
    assert created.is_read is True

    reader_detail = service.get_post_detail(
        db,
        post_id=created.id,
        unlocked=True,
        viewer_id=reader.id,
        viewer_is_admin=False,
    )
    assert reader_detail is not None
    assert reader_detail.is_read is False
    assert db.get(CommunityPostRead, (created.id, reader.id)) is None

    stored_post = service.load_post(db, post_id=created.id)
    assert stored_post is not None
    service.mark_post_read(db, post=stored_post, user_id=reader.id)
    first_read_at = db.get(CommunityPostRead, (created.id, reader.id)).read_at
    service.mark_post_read(db, post=stored_post, user_id=reader.id)

    assert (
        db.scalar(
            select(func.count())
            .select_from(CommunityPostRead)
            .where(
                CommunityPostRead.post_id == created.id,
                CommunityPostRead.user_id == reader.id,
            )
        )
        == 1
    )
    assert db.get(CommunityPostRead, (created.id, reader.id)).read_at >= first_read_at
    assert (
        service.list_posts(
            db,
            channel=channel,
            viewer_id=reader.id,
            viewer_is_admin=False,
        )
        .posts[0]
        .is_read
        is True
    )

    stored_post = service.load_post(db, post_id=created.id)
    assert stored_post is not None
    updated = service.update_post(
        db,
        post=stored_post,
        title="읽음 상태 수정",
        body="수정 내용",
        user=author,
        viewer_is_admin=False,
    )
    assert updated.is_read is True

    assert (
        service.list_posts(
            db,
            channel=channel,
            viewer_id=reader.id,
            viewer_is_admin=False,
        )
        .posts[0]
        .is_read
        is False
    )
    assert (
        service.list_posts(
            db,
            channel=channel,
            viewer_id=author.id,
            viewer_is_admin=False,
        )
        .posts[0]
        .is_read
        is True
    )


def test_deleting_post_removes_read_receipts(db: Session) -> None:
    author = _make_user(db, "author")
    reader = _make_user(db, "reader")
    channel = _channel(db)
    created = service.create_post(
        db,
        channel=channel,
        author=author,
        title="삭제할 글",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )
    stored_post = service.load_post(db, post_id=created.id)
    assert stored_post is not None
    service.mark_post_read(db, post=stored_post, user_id=reader.id)

    service.delete_post(db, post=stored_post)

    assert db.scalar(select(func.count()).select_from(CommunityPostRead)) == 0


def test_comment_on_my_community_post_creates_source_owned_notification_only(
    client: TestClient,
) -> None:
    author = dev_login(client, "administrator")
    commenter = dev_login(client, "delivery-hub-member")
    post = _create_community_post(
        client,
        token=author["token"],
        title="댓글 알림 테스트",
        body="작성자 본문",
    )

    comment_response = client.post(
        f"/api/v1/community/posts/{post['id']}/comments",
        headers=auth_headers(commenter["token"]),
        json={"body": "확인했습니다. 진행해주세요.", "is_anonymous": False},
    )
    assert comment_response.status_code == 201, comment_response.text

    notifications_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(author["token"]),
    )
    assert notifications_response.status_code == 200, notifications_response.text
    notification = notifications_response.json()["items"][0]
    assert notification["type"] == "community_comment"
    assert notification["source_type"] == "community_post"
    assert notification["source_id"] == post["id"]
    assert notification["origin_app_id"] == "community"
    assert notification["origin_workspace_id"] is None
    assert notification["action_url"] == f"/apps/community/posts/{post['id']}"
    assert notification["is_read"] is False
    assert "댓글 알림 테스트" in notification["body"]
    assert "확인했습니다" in notification["body"]
    assert commenter["user"]["full_name"] in notification["body"]

    conversations_response = client.get(
        "/api/v1/dm/conversations",
        headers=auth_headers(author["token"]),
    )
    assert conversations_response.status_code == 200, conversations_response.text
    assert all(
        item["display_name"] != "Open Work Hub Bot"
        for item in conversations_response.json()["items"]
    )

    read_response = client.patch(
        f"/api/v1/notifications/{notification['id']}/read",
        headers=auth_headers(author["token"]),
    )
    assert read_response.status_code == 200, read_response.text

    unread_response = client.get(
        "/api/v1/notifications/unread-count",
        headers=auth_headers(author["token"]),
    )
    assert unread_response.status_code == 200, unread_response.text
    assert unread_response.json() == {"count": 0}

    after_read_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(author["token"]),
    )
    assert after_read_response.status_code == 200, after_read_response.text
    assert after_read_response.json()["items"][0]["is_read"] is True


def test_anonymous_community_comment_notification_hides_commenter_identity(
    client: TestClient,
) -> None:
    author = dev_login(client, "administrator")
    commenter = dev_login(client, "delivery-hub-member")
    post = _create_community_post(
        client,
        token=author["token"],
        title="익명 알림 테스트",
        body="작성자 본문",
    )

    comment_response = client.post(
        f"/api/v1/community/posts/{post['id']}/comments",
        headers=auth_headers(commenter["token"]),
        json={"body": "익명 의견입니다.", "is_anonymous": True},
    )
    assert comment_response.status_code == 201, comment_response.text

    notifications_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(author["token"]),
    )
    assert notifications_response.status_code == 200, notifications_response.text
    notification = notifications_response.json()["items"][0]
    assert "익명 사용자가" in notification["body"]
    assert commenter["user"]["full_name"] not in notification["body"]
    assert commenter["user"]["email"] not in notification["body"]


def test_my_own_community_comment_does_not_notify_me(client: TestClient) -> None:
    author = dev_login(client, "administrator")
    post = _create_community_post(
        client,
        token=author["token"],
        title="셀프 댓글 테스트",
        body="작성자 본문",
    )

    comment_response = client.post(
        f"/api/v1/community/posts/{post['id']}/comments",
        headers=auth_headers(author["token"]),
        json={"body": "내 댓글", "is_anonymous": False},
    )
    assert comment_response.status_code == 201, comment_response.text

    notifications_response = client.get(
        "/api/v1/notifications",
        headers=auth_headers(author["token"]),
    )
    assert notifications_response.status_code == 200, notifications_response.text
    assert notifications_response.json()["items"] == []


def test_create_post_links_embedded_media_to_community_post(db: Session) -> None:
    author = _make_user(db, "author")
    channel = _channel(db)
    media_id = "00000000-0000-0000-0000-000000000001"
    _media(db, media_id=media_id, user=author)

    post = service.create_post(
        db,
        channel=channel,
        author=author,
        title="이미지 건의",
        body=f"본문\\n\\n![첨부](media:{media_id})",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    stored = db.get(MediaFile, media_id)
    assert stored is not None
    assert stored.resource_type == "community_post"
    assert stored.resource_id == post.id


def test_create_comment_links_embedded_media_to_community_comment(db: Session) -> None:
    author = _make_user(db, "author")
    commenter = _make_user(db, "commenter")
    channel = _channel(db)
    post = service.create_post(
        db,
        channel=channel,
        author=author,
        title="이미지 건의",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )
    stored_post = db.get(CommunityPost, post.id)
    media_id = "00000000-0000-0000-0000-000000000002"
    _media(db, media_id=media_id, user=commenter)

    comment = service.create_comment(
        db,
        post=stored_post,
        author=commenter,
        body=f"댓글 이미지\\n\\n![첨부](media:{media_id})",
        is_anonymous=False,
    )

    stored = db.get(MediaFile, media_id)
    assert stored is not None
    assert stored.resource_type == "community_comment"
    assert stored.resource_id == comment.id


def test_resolve_secret_post_media_accepts_post_password(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        media_content_access,
        "is_company_app_enabled_for_user_context",
        lambda *_args, **_kwargs: True,
    )
    author = _make_user(db, "author")
    reader = _make_user(db, "reader")
    channel = _channel(db)
    media_id = "00000000-0000-0000-0000-000000000003"
    _media(db, media_id=media_id, user=author)

    created = service.create_post(
        db,
        channel=channel,
        author=author,
        title="이미지 비밀 건의",
        body=f"본문\\n\\n![첨부](media:{media_id})",
        is_anonymous=False,
        is_secret=True,
        password="secret-pw",
    )
    stored_post = db.get(CommunityPost, created.id)
    assert stored_post is not None

    with pytest.raises(service.CommunityMediaAccessDeniedError):
        service.resolve_post_media_urls(
            db,
            post=stored_post,
            urls=[f"media:{media_id}"],
            viewer=reader,
            viewer_is_admin=False,
            content_grant_issuer=_content_grant_issuer(reader),
            password="wrong-pw",
        )

    resolved = service.resolve_post_media_urls(
        db,
        post=stored_post,
        urls=[f"media:{media_id}"],
        viewer=reader,
        viewer_is_admin=False,
        content_grant_issuer=_content_grant_issuer(reader),
        password="secret-pw",
    )

    resolved_url = resolved.resolved[f"media:{media_id}"]
    parsed = urlparse(resolved_url)
    assert parsed.path == "/api/v1/content"
    assert not parsed.query
    assert parse_qs(parsed.fragment)["grant"]


def test_inactive_channel_is_hidden_from_public_channel_list(db: Session) -> None:
    channel = CommunityChannel(
        id=new_id(),
        key="archived",
        name="Archived",
        description="",
        position=1,
        active=False,
    )
    db.add(channel)
    db.commit()

    visible = service.list_channels(db)
    admin = service.list_channels(db, include_inactive=True)

    assert [item.key for item in visible.channels] == ["suggestions"]
    assert [item.key for item in admin.channels] == ["suggestions", "archived"]


def test_list_posts_searches_visible_title_and_author_across_pages(db: Session) -> None:
    author = _make_user(db, "author")
    writer = _make_user(db, "writer")
    channel = _channel(db)

    service.create_post(
        db,
        channel=channel,
        author=author,
        title="Alpha release",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )
    service.create_post(
        db,
        channel=channel,
        author=writer,
        title="Beta handbook",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    by_title = service.list_posts(
        db,
        channel=channel,
        viewer_id=author.id,
        viewer_is_admin=False,
        page=1,
        page_size=1,
        search="beta",
    )
    assert by_title.total == 1
    assert by_title.posts[0].title == "Beta handbook"

    by_author = service.list_posts(
        db,
        channel=channel,
        viewer_id=author.id,
        viewer_is_admin=False,
        search="writer",
    )
    assert by_author.total == 1
    assert by_author.posts[0].author_name == "writer"


def test_list_posts_search_does_not_match_hidden_admin_only_content(
    db: Session,
) -> None:
    author = _make_user(db, "author")
    reader = _make_user(db, "reader")
    service.create_channel(
        db,
        key="private-search",
        name="Private Search",
        description="",
        position=1,
        active=True,
        admin_only_content=True,
    )
    channel = service.get_channel_by_key(db, "private-search")
    service.create_post(
        db,
        channel=channel,
        author=author,
        title="Needle private title",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    visible_without_search = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
    )
    assert visible_without_search.total == 1

    regular_search = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
        search="needle",
    )
    assert regular_search.total == 0

    author_search = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
        search="author",
    )
    assert author_search.total == 1
    assert author_search.posts[0].author_name is None

    admin_search = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=True,
        search="needle",
    )
    assert admin_search.total == 1
    assert admin_search.posts[0].title == "Needle private title"


def test_list_posts_search_respects_anonymous_channel_visibility(
    db: Session,
) -> None:
    author = _make_user(db, "hidden-author")
    reader = _make_user(db, "reader")
    service.create_channel(
        db,
        key="anonymous-search",
        name="Anonymous Search",
        description="",
        position=1,
        active=True,
        force_anonymous=True,
    )
    channel = service.get_channel_by_key(db, "anonymous-search")
    service.create_post(
        db,
        channel=channel,
        author=author,
        title="Visible anonymous title",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    by_title = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
        search="visible",
    )
    assert by_title.total == 1
    assert by_title.posts[0].author_name is None

    by_author = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
        search="hidden-author",
    )
    assert by_author.total == 0


def test_list_posts_search_disables_private_anonymous_channel_for_regular_viewer(
    db: Session,
) -> None:
    author = _make_user(db, "private-author")
    reader = _make_user(db, "reader")
    service.create_channel(
        db,
        key="private-anonymous-search",
        name="Private Anonymous Search",
        description="",
        position=1,
        active=True,
        admin_only_content=True,
        force_anonymous=True,
    )
    channel = service.get_channel_by_key(db, "private-anonymous-search")
    service.create_post(
        db,
        channel=channel,
        author=author,
        title="Hidden combined title",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    by_title = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
        search="combined",
    )
    assert by_title.total == 0

    by_author = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
        search="private-author",
    )
    assert by_author.total == 0

    admin_search = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=True,
        search="combined",
    )
    assert admin_search.total == 1
    assert admin_search.posts[0].title == "Hidden combined title"


def test_channel_admin_contract_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        CommunityChannelCreateRequest(key="team-news", name="   ")


def test_channel_key_must_be_unique(db: Session) -> None:
    service.create_channel(
        db,
        key="team-news",
        name="Team News",
        description="",
        position=1,
        active=True,
    )

    with pytest.raises(service.CommunityChannelKeyExistsError):
        service.create_channel(
            db,
            key="team-news",
            name="Team News 2",
            description="",
            position=2,
            active=True,
        )


def test_empty_non_default_channel_can_be_deleted(db: Session) -> None:
    service.create_channel(
        db,
        key="team-news",
        name="Team News",
        description="",
        position=1,
        active=True,
    )
    channel = service.get_channel_by_key(db, "team-news", active_only=False)

    service.delete_channel(db, channel=channel)

    assert service.get_channel_by_key(db, "team-news", active_only=False) is None


def test_channel_with_posts_cannot_be_deleted(db: Session) -> None:
    author = _make_user(db, "author")
    service.create_channel(
        db,
        key="team-news",
        name="Team News",
        description="",
        position=1,
        active=True,
    )
    channel = service.get_channel_by_key(db, "team-news")
    service.create_post(
        db,
        channel=channel,
        author=author,
        title="공지",
        body="내용",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    with pytest.raises(service.CommunityChannelDeleteBlockedError):
        service.delete_channel(db, channel=channel)


def test_read_only_channel_rejects_regular_posts_and_comments_but_allows_admin(
    client: TestClient,
) -> None:
    admin = dev_login(client, "administrator")
    member = dev_login(client, "delivery-hub-member")
    channel = _create_admin_channel(
        client,
        token=admin["token"],
        key="announcements",
        name="Announcements",
        read_only=True,
    )
    assert channel["readOnly"] is True

    denied_post = client.post(
        "/api/v1/community/channels/announcements/posts",
        headers=auth_headers(member["token"]),
        json={
            "title": "Member post",
            "body": "Should be blocked",
            "isAnonymous": False,
            "isSecret": False,
        },
    )
    assert denied_post.status_code == 403, denied_post.text

    admin_post = client.post(
        "/api/v1/community/channels/announcements/posts",
        headers=auth_headers(admin["token"]),
        json={
            "title": "공지",
            "body": "관리자 공지",
            "isAnonymous": False,
            "isSecret": False,
        },
    )
    assert admin_post.status_code == 201, admin_post.text
    post_id = admin_post.json()["id"]

    denied_comment = client.post(
        f"/api/v1/community/posts/{post_id}/comments",
        headers=auth_headers(member["token"]),
        json={"body": "댓글도 차단", "isAnonymous": False},
    )
    assert denied_comment.status_code == 403, denied_comment.text

    admin_comment = client.post(
        f"/api/v1/community/posts/{post_id}/comments",
        headers=auth_headers(admin["token"]),
        json={"body": "관리자 댓글", "isAnonymous": False},
    )
    assert admin_comment.status_code == 201, admin_comment.text


def test_read_only_channel_disables_regular_author_modifications(
    client: TestClient,
) -> None:
    admin = dev_login(client, "administrator")
    member = dev_login(client, "delivery-hub-member")
    _create_admin_channel(
        client,
        token=admin["token"],
        key="read-only-edits",
        name="Read Only Edits",
        read_only=True,
    )

    with get_session_factory()() as db:
        channel = service.get_channel_by_key(db, "read-only-edits")
        author = db.get(User, member["user"]["id"])
        assert channel is not None
        assert author is not None
        post = service.create_post(
            db,
            channel=channel,
            author=author,
            title="기존 글",
            body="읽기 전용 전환 전 글",
            is_anonymous=False,
            is_secret=False,
            password=None,
        )
        stored_post = db.get(CommunityPost, post.id)
        assert stored_post is not None
        comment = service.create_comment(
            db,
            post=stored_post,
            author=author,
            body="기존 댓글",
            is_anonymous=False,
        )

    detail = client.get(
        f"/api/v1/community/posts/{post.id}",
        headers=auth_headers(member["token"]),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["canModify"] is False
    assert detail.json()["comments"][0]["canModify"] is False

    post_update = client.patch(
        f"/api/v1/community/posts/{post.id}",
        headers=auth_headers(member["token"]),
        json={"title": "수정", "body": "수정"},
    )
    assert post_update.status_code == 403, post_update.text

    comment_update = client.patch(
        f"/api/v1/community/posts/{post.id}/comments/{comment.id}",
        headers=auth_headers(member["token"]),
        json={"body": "수정 댓글"},
    )
    assert comment_update.status_code == 403, comment_update.text

    comment_delete = client.delete(
        f"/api/v1/community/posts/{post.id}/comments/{comment.id}",
        headers=auth_headers(member["token"]),
    )
    assert comment_delete.status_code == 403, comment_delete.text

    post_delete = client.delete(
        f"/api/v1/community/posts/{post.id}",
        headers=auth_headers(member["token"]),
    )
    assert post_delete.status_code == 403, post_delete.text


def test_post_read_endpoint_is_authenticated_idempotent_and_detail_has_no_side_effect(
    client: TestClient,
) -> None:
    author = dev_login(client, "administrator")
    reader = dev_login(client, "delivery-hub-member")
    post = _create_community_post(
        client,
        token=author["token"],
        title="읽음 API",
        body="본문",
    )
    assert post["isRead"] is True

    anonymous = client.post(f"/api/v1/community/posts/{post['id']}/read")
    assert anonymous.status_code == 401, anonymous.text

    missing = client.post(
        "/api/v1/community/posts/does-not-exist/read",
        headers=auth_headers(reader["token"]),
    )
    assert missing.status_code == 404, missing.text

    detail = client.get(
        f"/api/v1/community/posts/{post['id']}",
        headers=auth_headers(reader["token"]),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["isRead"] is False

    before_read = client.get(
        f"/api/v1/community/channels/{service.DEFAULT_CHANNEL_KEY}/posts",
        headers=auth_headers(reader["token"]),
    )
    assert before_read.status_code == 200, before_read.text
    assert before_read.json()["posts"][0]["isRead"] is False

    for _ in range(2):
        marked = client.post(
            f"/api/v1/community/posts/{post['id']}/read",
            headers=auth_headers(reader["token"]),
        )
        assert marked.status_code == 204, marked.text

    after_read = client.get(
        f"/api/v1/community/channels/{service.DEFAULT_CHANNEL_KEY}/posts",
        headers=auth_headers(reader["token"]),
    )
    assert after_read.status_code == 200, after_read.text
    assert after_read.json()["posts"][0]["isRead"] is True


def test_unlock_marks_secret_post_read_but_direct_read_is_denied_while_locked(
    client: TestClient,
) -> None:
    author = dev_login(client, "administrator")
    reader = dev_login(client, "delivery-hub-member")
    created = client.post(
        f"/api/v1/community/channels/{service.DEFAULT_CHANNEL_KEY}/posts",
        headers=auth_headers(author["token"]),
        json={
            "title": "비밀 글",
            "body": "비밀 본문",
            "isAnonymous": False,
            "isSecret": True,
            "password": "secret-pw",
        },
    )
    assert created.status_code == 201, created.text
    post = created.json()

    author_mark = client.post(
        f"/api/v1/community/posts/{post['id']}/read",
        headers=auth_headers(author["token"]),
    )
    assert author_mark.status_code == 204, author_mark.text

    denied = client.post(
        f"/api/v1/community/posts/{post['id']}/read",
        headers=auth_headers(reader["token"]),
    )
    assert denied.status_code == 403, denied.text

    wrong_password = client.post(
        f"/api/v1/community/posts/{post['id']}/unlock",
        headers=auth_headers(reader["token"]),
        json={"password": "wrong-pw"},
    )
    assert wrong_password.status_code == 403, wrong_password.text

    unlocked = client.post(
        f"/api/v1/community/posts/{post['id']}/unlock",
        headers=auth_headers(reader["token"]),
        json={"password": "secret-pw"},
    )
    assert unlocked.status_code == 200, unlocked.text
    assert unlocked.json()["locked"] is False
    assert unlocked.json()["isRead"] is True

    listed = client.get(
        f"/api/v1/community/channels/{service.DEFAULT_CHANNEL_KEY}/posts",
        headers=auth_headers(reader["token"]),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["posts"][0]["locked"] is True
    assert listed.json()["posts"][0]["isRead"] is True


def test_admin_only_locked_post_cannot_be_marked_or_unlocked_by_regular_user(
    client: TestClient,
) -> None:
    admin = dev_login(client, "administrator")
    reader = dev_login(client, "delivery-hub-member")
    channel = client.post(
        "/api/v1/community/admin/channels",
        headers=auth_headers(admin["token"]),
        json={
            "key": "private-reports",
            "name": "Private Reports",
            "description": "",
            "position": 1,
            "active": True,
            "readOnly": False,
            "forceAnonymous": False,
            "adminOnlyContent": True,
            "templateTitle": "",
            "templateBody": "",
        },
    )
    assert channel.status_code == 201, channel.text
    created = client.post(
        "/api/v1/community/channels/private-reports/posts",
        headers=auth_headers(admin["token"]),
        json={
            "title": "관리자 전용",
            "body": "비공개 본문",
            "isAnonymous": False,
            "isSecret": False,
        },
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["id"]

    denied_read = client.post(
        f"/api/v1/community/posts/{post_id}/read",
        headers=auth_headers(reader["token"]),
    )
    assert denied_read.status_code == 403, denied_read.text
    denied_unlock = client.post(
        f"/api/v1/community/posts/{post_id}/unlock",
        headers=auth_headers(reader["token"]),
        json={"password": "anything"},
    )
    assert denied_unlock.status_code == 403, denied_unlock.text

    reader_list = client.get(
        "/api/v1/community/channels/private-reports/posts",
        headers=auth_headers(reader["token"]),
    )
    assert reader_list.status_code == 200, reader_list.text
    assert reader_list.json()["posts"][0]["locked"] is True
    assert reader_list.json()["posts"][0]["isRead"] is False

    admin_list = client.get(
        "/api/v1/community/channels/private-reports/posts",
        headers=auth_headers(admin["token"]),
    )
    assert admin_list.status_code == 200, admin_list.text
    assert admin_list.json()["posts"][0]["locked"] is False
    assert admin_list.json()["posts"][0]["isRead"] is True


def test_secret_post_is_masked_until_author_admin_or_password_unlock(
    db: Session,
) -> None:
    author = _make_user(db, "author")
    other = _make_user(db, "other")
    channel = _channel(db)

    created = service.create_post(
        db,
        channel=channel,
        author=author,
        title="비밀 제안",
        body="민감한 내용",
        is_anonymous=False,
        is_secret=True,
        password="secret-pw",
    )
    assert created.locked is False

    page = service.list_posts(
        db,
        channel=channel,
        viewer_id=other.id,
        viewer_is_admin=False,
    )
    masked = page.posts[0]
    assert masked.locked is True
    assert masked.title == ""
    assert masked.body == ""

    locked = service.get_post_detail(
        db,
        post_id=created.id,
        unlocked=False,
        viewer_id=other.id,
        viewer_is_admin=False,
    )
    assert locked is not None
    assert locked.locked is True
    assert locked.comments == []

    stored = db.get(CommunityPost, created.id)
    assert service.verify_post_password(stored, "nope") is False
    assert service.verify_post_password(stored, "secret-pw") is True

    author_detail = service.get_post_detail(
        db,
        post_id=created.id,
        unlocked=True,
        viewer_id=author.id,
        viewer_is_admin=False,
    )
    assert author_detail is not None
    assert author_detail.body == "민감한 내용"


def test_force_anonymous_channel_masks_names_except_for_admin(db: Session) -> None:
    author = _make_user(db, "author")
    commenter = _make_user(db, "commenter")
    service.create_channel(
        db,
        key="whistleblowing",
        name="Whistleblowing",
        description="",
        position=1,
        active=True,
        force_anonymous=True,
    )
    channel = service.get_channel_by_key(db, "whistleblowing")

    created = service.create_post(
        db,
        channel=channel,
        author=author,
        title="익명 제보",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )
    stored_post = db.get(CommunityPost, created.id)
    service.create_comment(
        db,
        post=stored_post,
        author=commenter,
        body="댓글",
        is_anonymous=False,
    )

    regular_page = service.list_posts(
        db,
        channel=channel,
        viewer_id=commenter.id,
        viewer_is_admin=False,
    )
    regular_post = regular_page.posts[0]
    assert regular_post.is_anonymous is True
    assert regular_post.author_name is None

    admin_page = service.list_posts(
        db,
        channel=channel,
        viewer_id=commenter.id,
        viewer_is_admin=True,
    )
    assert admin_page.posts[0].is_anonymous is True
    assert admin_page.posts[0].author_name == "author"

    regular_detail = service.get_post_detail(
        db,
        post_id=created.id,
        unlocked=True,
        viewer_id=commenter.id,
        viewer_is_admin=False,
    )
    assert regular_detail is not None
    assert regular_detail.comments[0].is_anonymous is True
    assert regular_detail.comments[0].author_name is None
    assert regular_detail.comments[0].anon_seq == 1

    admin_detail = service.get_post_detail(
        db,
        post_id=created.id,
        unlocked=True,
        viewer_id=commenter.id,
        viewer_is_admin=True,
    )
    assert admin_detail is not None
    assert admin_detail.author_name == "author"
    assert admin_detail.comments[0].author_name == "commenter"


def test_admin_only_channel_masks_content_and_media_for_regular_viewers(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        media_content_access,
        "is_company_app_enabled_for_user_context",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        media_content_access,
        "can_resolve_media",
        lambda *_args, **_kwargs: True,
    )
    author = _make_user(db, "author")
    reader = _make_user(db, "reader")
    service.create_channel(
        db,
        key="private-report",
        name="Private Report",
        description="",
        position=1,
        active=True,
        admin_only_content=True,
    )
    channel = service.get_channel_by_key(db, "private-report")
    media_id = "00000000-0000-0000-0000-000000000004"
    _media(db, media_id=media_id, user=author)

    created = service.create_post(
        db,
        channel=channel,
        author=author,
        title="비공개 제보",
        body=f"관리자 확인 필요\n\n![첨부](media:{media_id})",
        is_anonymous=False,
        is_secret=True,
        password=None,
    )
    assert created.locked is True
    assert created.locked_reason == service.LOCKED_REASON_ADMIN_ONLY
    assert created.author_name is None
    stored_post = db.get(CommunityPost, created.id)
    assert stored_post.is_secret is False

    regular_page = service.list_posts(
        db,
        channel=channel,
        viewer_id=reader.id,
        viewer_is_admin=False,
    )
    masked = regular_page.posts[0]
    assert masked.locked is True
    assert masked.locked_reason == service.LOCKED_REASON_ADMIN_ONLY
    assert masked.title == ""
    assert masked.body == ""
    assert masked.author_name is None

    regular_detail = service.get_post_detail(
        db,
        post_id=created.id,
        unlocked=True,
        viewer_id=author.id,
        viewer_is_admin=False,
    )
    assert regular_detail is not None
    assert regular_detail.locked is True
    assert regular_detail.title == ""
    assert regular_detail.author_name is None
    assert regular_detail.comments == []

    with pytest.raises(service.CommunityMediaAccessDeniedError):
        service.resolve_post_media_urls(
            db,
            post=stored_post,
            urls=[f"media:{media_id}"],
            viewer=reader,
            viewer_is_admin=False,
            content_grant_issuer=_content_grant_issuer(reader),
        )

    admin_detail = service.get_post_detail(
        db,
        post_id=created.id,
        unlocked=True,
        viewer_id=reader.id,
        viewer_is_admin=True,
    )
    assert admin_detail is not None
    assert admin_detail.locked is False
    assert admin_detail.title == "비공개 제보"
    assert admin_detail.author_name == "author"

    resolved = service.resolve_post_media_urls(
        db,
        post=stored_post,
        urls=[f"media:{media_id}"],
        viewer=reader,
        viewer_is_admin=True,
        content_grant_issuer=_content_grant_issuer(reader),
    )
    assert f"media:{media_id}" in resolved.resolved


def test_require_author_or_admin_allows_author_and_admin_only() -> None:
    with pytest.raises(HTTPException) as excinfo:
        _require_author_or_admin("author-id", _StubUser("other-id"), is_admin=False)
    assert excinfo.value.status_code == 403

    _require_author_or_admin("author-id", _StubUser("author-id"), is_admin=False)
    _require_author_or_admin("author-id", _StubUser("admin-id"), is_admin=True)


class _StubUser:
    def __init__(self, user_id: str) -> None:
        self.id = user_id


def test_anonymous_comment_numbering_is_stable_per_author(db: Session) -> None:
    author = _make_user(db, "author")
    first = _make_user(db, "first")
    second = _make_user(db, "second")
    channel = _channel(db)
    post = service.create_post(
        db,
        channel=channel,
        author=author,
        title="제목",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )

    base = datetime(2026, 6, 10, 0, 0, 0)
    for offset, commenter in enumerate((first, second, first)):
        db.add(
            CommunityComment(
                id=new_id(),
                post_id=post.id,
                author_id=commenter.id,
                is_anonymous=True,
                body="익명 의견",
                created_at=base + timedelta(seconds=offset),
                updated_at=base + timedelta(seconds=offset),
            )
        )
    db.commit()

    detail = service.get_post_detail(
        db,
        post_id=post.id,
        unlocked=True,
        viewer_id=author.id,
        viewer_is_admin=False,
    )

    assert detail is not None
    anon = [comment for comment in detail.comments if comment.is_anonymous]
    assert [comment.anon_seq for comment in anon] == [1, 2, 1]
    assert all(comment.author_name is None for comment in anon)


def test_deleting_comment_soft_deletes_and_keeps_replies(db: Session) -> None:
    author = _make_user(db, "author")
    replier = _make_user(db, "replier")
    channel = _channel(db)
    post = service.create_post(
        db,
        channel=channel,
        author=author,
        title="제목",
        body="본문",
        is_anonymous=False,
        is_secret=False,
        password=None,
    )
    stored_post = db.get(CommunityPost, post.id)

    parent = service.create_comment(
        db,
        post=stored_post,
        author=author,
        body="부모 댓글",
        is_anonymous=False,
    )
    service.create_comment(
        db,
        post=stored_post,
        author=replier,
        body="답글",
        is_anonymous=False,
        parent_comment_id=parent.id,
    )

    service.delete_comment(db, comment=db.get(CommunityComment, parent.id))

    detail = service.get_post_detail(
        db,
        post_id=post.id,
        unlocked=True,
        viewer_id=author.id,
        viewer_is_admin=False,
    )
    assert detail is not None
    by_id = {comment.id: comment for comment in detail.comments}
    assert by_id[parent.id].is_deleted is True
    assert by_id[parent.id].body == ""
    assert any(comment.parent_comment_id == parent.id for comment in detail.comments)
    assert detail.comment_count == 1
