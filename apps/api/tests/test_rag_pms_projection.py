from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data
from aidoo_api.domains.auth.models import Team, User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.pms.access_grants import grant_issue_access
from aidoo_api.domains.pms.models import Issue, TaskList
from aidoo_api.domains.rag.access_filter import build_user_rag_post_filter
from aidoo_api.domains.rag.contracts import RagQueryRequest
from aidoo_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from aidoo_api.domains.rag.pms_projection import PMS_ISSUE_RESOURCE_TYPE, load_issue_projection
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.service import RagService


def test_issue_projection_preserves_expired_grants_for_query_time_acl_checks(client) -> None:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
        owner = db.scalar(select(User).where(User.email == "delivery-hub-admin@aidoo.local"))
        shared_user = db.scalar(select(User).where(User.email == "platform-admin@aidoo.local"))
        expired_user = db.scalar(select(User).where(User.email == "hq-admin@aidoo.local"))
        revoked_user = db.scalar(select(User).where(User.email == "delivery-hub-member@aidoo.local"))
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert shared_user is not None
        assert expired_user is not None
        assert revoked_user is not None
        assert workspace is not None
        shared_user_id = shared_user.id
        expired_user_id = expired_user.id
        revoked_user_id = revoked_user.id
        workspace_id = workspace.id

        team_id = new_id()
        list_id = new_id()
        issue_id = new_id()
        team = Team(
            id=team_id,
            workspace_id=workspace_id,
            key=f"RAG{team_id[:8]}",
            name="RAG Projection Team",
            description="",
            active=True,
        )
        task_list = TaskList(
            id=list_id,
            key=f"RAG{list_id[:8]}",
            name="RAG Projection List",
            description="",
            status="active",
            archived=False,
            team_id=team_id,
            folder_id=None,
            created_by_id=owner.id,
        )
        issue = Issue(
            id=issue_id,
            list_id=list_id,
            issue_number=1,
            title="Projection Issue",
            description="Meeting-shared issue content.",
            status="backlog",
            priority="medium",
            reporter_id=owner.id,
            assignee_id=None,
            archived=False,
        )
        db.add(team)
        db.commit()
        db.add(task_list)
        db.commit()
        db.add(issue)
        db.flush()

        grant_issue_access(
            db,
            issue_id=issue_id,
            user_id=shared_user.id,
            granted_by_user_id=owner.id,
            granted_by_meeting_id=None,
            reason="manual_share",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        grant_issue_access(
            db,
            issue_id=issue_id,
            user_id=revoked_user_id,
            granted_by_user_id=owner.id,
            granted_by_meeting_id=None,
            reason="manual_share",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        ).revoked_at = datetime.now(UTC).replace(tzinfo=None)
        grant_issue_access(
            db,
            issue_id=issue_id,
            user_id=expired_user_id,
            granted_by_user_id=owner.id,
            granted_by_meeting_id=None,
            reason="manual_share",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        )
        db.commit()

        projection = load_issue_projection(db, issue_id=issue_id)

    assert projection is not None
    assert projection.resource_type == PMS_ISSUE_RESOURCE_TYPE
    assert f"workspace:{workspace_id}" in projection.visibility_refs
    assert f"team:{team_id}" in projection.visibility_refs
    assert f"issue_grant:{shared_user_id}" in projection.visibility_refs
    assert f"issue_grant:{expired_user_id}" in projection.visibility_refs
    assert f"issue_grant:{revoked_user_id}" not in projection.visibility_refs


def test_issue_query_post_filter_rejects_expired_grant_hits(client) -> None:
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        default_collection="pms-expired-grant-smoke",
    )

    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
        owner = db.scalar(select(User).where(User.email == "delivery-hub-admin@aidoo.local"))
        expired_user = db.scalar(select(User).where(User.email == "hq-admin@aidoo.local"))
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert expired_user is not None
        assert workspace is not None
        workspace_id = workspace.id

        team_id = new_id()
        list_id = new_id()
        issue_id = new_id()
        team = Team(
            id=team_id,
            workspace_id=workspace_id,
            key=f"RAG{team_id[:8]}",
            name="RAG Query Team",
            description="",
            active=True,
        )
        task_list = TaskList(
            id=list_id,
            key=f"RAG{list_id[:8]}",
            name="RAG Query List",
            description="",
            status="active",
            archived=False,
            team_id=team_id,
            folder_id=None,
            created_by_id=owner.id,
        )
        issue = Issue(
            id=issue_id,
            list_id=list_id,
            issue_number=1,
            title="Expired Grant Issue",
            description="Expired grant should be filtered at query time.",
            status="backlog",
            priority="medium",
            reporter_id=owner.id,
            assignee_id=None,
            archived=False,
        )
        db.add(team)
        db.commit()
        db.add(task_list)
        db.commit()
        db.add(issue)
        db.flush()

        grant_issue_access(
            db,
            issue_id=issue_id,
            user_id=expired_user.id,
            granted_by_user_id=owner.id,
            granted_by_meeting_id=None,
            reason="manual_share",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        )
        db.commit()

        projection = load_issue_projection(db, issue_id=issue_id)
        post_filter = build_user_rag_post_filter(db, user=expired_user)
        assert projection is not None

        rag_service.sync_projection(projection)
        response = query_service.query(
            RagQueryRequest(
                collection="pms-expired-grant-smoke",
                workspace_id=workspace_id,
                query="expired grant query time",
                filters={"visibility_refs_contains": f"issue_grant:{expired_user.id}"},
            ),
            post_filter=post_filter,
        )

        assert response.hits == []
