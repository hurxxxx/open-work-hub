from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.core.i18n import ERROR_CODE_HEADER
from open_work_hub_api.domains.auth.models import (
    CompanyAppControl,
    Team,
    TeamMember,
    User,
    UserSystemRole,
    Workspace,
    WorkspaceAppDefault,
    WorkspaceAppOverride,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.docs.models import (
    DocMeetingAccess,
    DocsCollection,
    NativeDoc,
    NativeDocTarget,
    NativeDocPage,
    NativeDocUserShare,
)
from open_work_hub_api.domains.community.models import (
    CommunityChannel,
    CommunityComment,
    CommunityPost,
)
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.resource_access import (
    MEDIA_RESOURCE_COMMUNITY_COMMENT,
    MEDIA_RESOURCE_COMMUNITY_POST,
    can_access_docs_native_page,
    can_resolve_media,
    ensure_media_link_resource_access,
    media_ids_from_urls,
)
from open_work_hub_api.domains.meeting.models import Meeting
from open_work_hub_api.domains.pms.models import Folder, Milestone, Task, TaskList, TaskUserAccess


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            CompanyAppControl.__table__,
            WorkspaceAppDefault.__table__,
            WorkspaceAppOverride.__table__,
            User.__table__,
            WorkspaceUserBinding.__table__,
            UserSystemRole.__table__,
            Team.__table__,
            TeamMember.__table__,
            Folder.__table__,
            TaskList.__table__,
            Milestone.__table__,
            Task.__table__,
            TaskUserAccess.__table__,
            DocsCollection.__table__,
            NativeDoc.__table__,
            NativeDocPage.__table__,
            NativeDocTarget.__table__,
            NativeDocUserShare.__table__,
            Meeting.__table__,
            DocMeetingAccess.__table__,
            CommunityChannel.__table__,
            CommunityPost.__table__,
            CommunityComment.__table__,
            MediaFile.__table__,
        ],
    )
    return Session(engine)


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@open-work-hub.local",
        full_name=user_id.title(),
        password_hash="hash",
        status="active",
    )


def _media(**overrides: object) -> MediaFile:
    defaults = {
        "id": "00000000-0000-0000-0000-000000000001",
        "storage_key": "media/uploader/media-1/fixture.png",
        "filename": "fixture.png",
        "content_type": "image/png",
        "size_bytes": 128,
        "uploaded_by_id": "uploader",
        "resource_type": None,
        "resource_id": None,
    }
    defaults.update(overrides)
    return MediaFile(**defaults)


def test_media_ids_from_urls_keeps_only_exact_media_refs() -> None:
    assert media_ids_from_urls(
        [
            "media:00000000-0000-0000-0000-000000000001",
            "prefix media:00000000-0000-0000-0000-000000000002",
            "media:not-a-uuid",
            "media:00000000-0000-0000-0000-000000000003",
        ]
    ) == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000003",
    ]


def test_can_resolve_only_unlinked_media_for_uploader_and_rejects_unknown_sources() -> None:
    uploader = SimpleNamespace(id="uploader")
    outsider = SimpleNamespace(id="outsider")

    assert can_resolve_media(None, uploader, _media()) is True
    assert can_resolve_media(None, outsider, _media()) is False
    assert (
        can_resolve_media(
            None,
            uploader,
            _media(resource_type="legacy_unknown", resource_id="resource-1"),
        )
        is False
    )
    assert (
        can_resolve_media(
            None,
            outsider,
            _media(resource_type="legacy_unknown", resource_id="resource-1"),
        )
        is False
    )


def test_can_resolve_task_media_through_space_membership() -> None:
    session = _session()
    try:
        member = _user("member")
        outsider = _user("outsider")
        session.add_all(
            [
                Workspace(id="workspace-1", key="workspace", name="Workspace", description=""),
                member,
                outsider,
                Team(
                    id="team-1",
                    workspace_id="workspace-1",
                    key="space",
                    name="Space",
                    description="",
                    active=True,
                ),
                TeamMember(id="membership-1", team_id="team-1", user_id="member", role="member"),
                WorkspaceUserBinding(
                    id="workspace-member", workspace_id="workspace-1", user_id="member", role="member",
                ),
                CompanyAppControl(app_id="pms", enabled=True),
                WorkspaceAppDefault(app_id="pms", enabled=True),
                TaskList(
                    id="list-1",
                    key="LIST",
                    name="List",
                    description="",
                    team_id="team-1",
                    created_by_id="member",
                ),
                Task(
                    id="task-1",
                    list_id="list-1",
                    task_number=1,
                    title="Task",
                    description="",
                    reporter_id="member",
                ),
            ]
        )
        session.commit()

        media = _media(resource_type="task", resource_id="task-1")

        assert can_resolve_media(session, member, media) is True
        assert can_resolve_media(session, outsider, media) is False
    finally:
        session.close()


def test_can_resolve_community_post_media_for_public_posts() -> None:
    session = _session()
    try:
        author = _user("author")
        reader = _user("reader")
        session.add_all(
            [
                author,
                reader,
                CommunityChannel(
                    id="channel-1",
                    key="suggestions",
                    name="Suggestions",
                    description="",
                ),
                CommunityPost(
                    id="post-1",
                    channel_id="channel-1",
                    author_id="author",
                    title="Post",
                    body="![첨부](media:00000000-0000-0000-0000-000000000001)",
                    is_secret=False,
                ),
            ]
        )
        session.commit()

        media = _media(
            resource_type=MEDIA_RESOURCE_COMMUNITY_POST,
            resource_id="post-1",
            uploaded_by_id="author",
        )

        assert can_resolve_media(session, reader, media) is True
    finally:
        session.close()


def test_can_resolve_community_post_media_keeps_secret_posts_private() -> None:
    session = _session()
    try:
        author = _user("author")
        reader = _user("reader")
        session.add_all(
            [
                author,
                reader,
                CommunityChannel(
                    id="channel-1",
                    key="suggestions",
                    name="Suggestions",
                    description="",
                ),
                CommunityPost(
                    id="post-1",
                    channel_id="channel-1",
                    author_id="author",
                    title="Post",
                    body="![첨부](media:00000000-0000-0000-0000-000000000001)",
                    is_secret=True,
                ),
            ]
        )
        session.commit()

        media = _media(
            resource_type=MEDIA_RESOURCE_COMMUNITY_POST,
            resource_id="post-1",
            uploaded_by_id="author",
        )

        assert can_resolve_media(session, author, media) is True
        assert can_resolve_media(session, reader, media) is False
    finally:
        session.close()


def test_can_resolve_community_post_media_keeps_admin_only_channels_private() -> None:
    session = _session()
    try:
        author = _user("author")
        admin = _user("admin")
        session.add_all(
            [
                author,
                admin,
                UserSystemRole(id="admin-role", user_id="admin", role="platform_admin"),
                CommunityChannel(
                    id="channel-1",
                    key="private",
                    name="Private",
                    description="",
                    admin_only_content=True,
                ),
                CommunityPost(
                    id="post-1",
                    channel_id="channel-1",
                    author_id="author",
                    title="Post",
                    body="![첨부](media:00000000-0000-0000-0000-000000000001)",
                    is_secret=False,
                ),
            ]
        )
        session.commit()

        media = _media(
            resource_type=MEDIA_RESOURCE_COMMUNITY_POST,
            resource_id="post-1",
            uploaded_by_id="author",
        )

        assert can_resolve_media(session, author, media) is False
        assert can_resolve_media(session, admin, media) is True
    finally:
        session.close()


def test_can_resolve_community_comment_media_through_parent_post_access() -> None:
    session = _session()
    try:
        author = _user("author")
        reader = _user("reader")
        session.add_all(
            [
                author,
                reader,
                CommunityChannel(
                    id="channel-1",
                    key="suggestions",
                    name="Suggestions",
                    description="",
                ),
                CommunityPost(
                    id="post-1",
                    channel_id="channel-1",
                    author_id="author",
                    title="Post",
                    body="Body",
                    is_secret=False,
                ),
                CommunityComment(
                    id="comment-1",
                    post_id="post-1",
                    author_id="author",
                    body="![첨부](media:00000000-0000-0000-0000-000000000001)",
                ),
            ]
        )
        session.commit()

        media = _media(
            resource_type=MEDIA_RESOURCE_COMMUNITY_COMMENT,
            resource_id="comment-1",
            uploaded_by_id="author",
        )

        assert can_resolve_media(session, reader, media) is True
    finally:
        session.close()


def test_docs_native_page_access_distinguishes_read_from_edit() -> None:
    session = _session()
    try:
        owner = _user("owner")
        reader = _user("reader")
        session.add_all(
            [
                Workspace(id="workspace-1", key="workspace", name="Workspace", description=""),
                owner,
                reader,
                NativeDoc(
                    id="doc-1",
                    workspace_id="workspace-1",
                    owner_id="owner",
                    title="Doc",
                    source_app="docs",
                    source_kind="manual",
                    source_ref="doc-1",
                ),
                NativeDocPage(
                    id="page-1",
                    doc_id="doc-1",
                    parent_id=None,
                    title="Page",
                    content_format="block",
                    content_blocks=[],
                    sort_order=0,
                    created_by_id="owner",
                ),
                NativeDocUserShare(
                    id="share-1",
                    doc_id="doc-1",
                    user_id="reader",
                    access_level="read",
                    created_by_id="owner",
                ),
            ]
        )
        session.commit()

        assert can_access_docs_native_page(session, owner, "page-1", require_edit=True) is True
        assert can_access_docs_native_page(session, reader, "page-1", require_edit=False) is True
        assert can_access_docs_native_page(session, reader, "page-1", require_edit=True) is False
    finally:
        session.close()


def test_ensure_media_link_resource_access_rejects_unsupported_type() -> None:
    with pytest.raises(HTTPException) as exc_info:
        ensure_media_link_resource_access(None, SimpleNamespace(id="user-1"), "doc", "doc-1")

    assert exc_info.value.status_code == 400
    assert exc_info.value.headers[ERROR_CODE_HEADER] == "media.unsupported_resource_type"
