from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest

from dev_accounts import create_workspace_user_session, dev_login
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.access import load_user_graph
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.docs import service as docs_service
from ai_do_api.domains.docs.access_grants import grant_doc_access
from ai_do_api.domains.docs.models import NativeDocLinkShare, NativeDocPage, NativeDocUserShare
from ai_do_api.domains.rag.contracts import RagQueryRequest, RagVectorSearchHit
from ai_do_api.domains.rag.access_filter import build_user_rag_post_filter
from ai_do_api.domains.rag.docs_projection import (
    NATIVE_DOC_RESOURCE_TYPE,
    load_native_doc_projection,
)
from ai_do_api.domains.rag.providers.fake import (
    FakeEmbeddingClient,
    FakeVectorIndexClient,
)
from ai_do_api.domains.rag.query_service import RagQueryService
from ai_do_api.domains.rag.service import RagService


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def test_native_doc_projection_preserves_grants_for_query_time_expiry_checks(
    client: TestClient,
) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    shared_session = _dev_login(client, "administrator")
    expired_session = create_workspace_user_session(
        client,
        workspace_key="delivery-hub",
        login_id="docsragexpiredprojection",
        email="docs-rag-expired-projection@ai-do.local",
        full_name="Docs RAG Expired Projection",
    )
    revoked_session = _dev_login(client, "delivery-hub-member")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        shared_user = db.get(User, shared_session["user"]["id"])
        expired_user = db.get(User, expired_session["user"]["id"])
        revoked_user = db.get(User, revoked_session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert shared_user is not None
        assert expired_user is not None
        assert revoked_user is not None
        assert workspace is not None
        owner_id = owner.id
        shared_user_id = shared_user.id
        expired_user_id = expired_user.id
        revoked_user_id = revoked_user.id
        workspace_id = workspace.id

        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace_id,
            owner_id=owner_id,
            title="RAG Projection Smoke",
            content_blocks=[
                {"type": "heading", "content": [{"type": "text", "text": "Launch Plan"}]},
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Qdrant payload index early."}],
                },
            ],
            primary_target=("pms", "space", "space-42", 0),
        )
        db.add(
            NativeDocPage(
                id=new_id(),
                doc_id=doc.id,
                parent_id=None,
                title="Execution Notes",
                content_blocks=[
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Hybrid retrieval with rerank."}],
                    },
                ],
                sort_order=1,
                created_by_id=owner_id,
            )
        )
        db.add(
            NativeDocUserShare(
                id=new_id(),
                doc_id=doc.id,
                user_id=shared_user_id,
                access_level="read",
                created_by_id=owner_id,
            )
        )
        db.add(
            NativeDocLinkShare(
                id=new_id(),
                doc_id=doc.id,
                token="secret-link-token",
                access_level="read",
                active=True,
                created_by_id=owner_id,
            )
        )
        grant_doc_access(
            db,
            doc_id=doc.id,
            user_id=shared_user_id,
            granted_by_user_id=owner_id,
            granted_by_meeting_id=None,
            reason="meeting_attendee",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        grant_doc_access(
            db,
            doc_id=doc.id,
            user_id=revoked_user_id,
            granted_by_user_id=owner_id,
            granted_by_meeting_id=None,
            reason="meeting_attendee",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        ).revoked_at = datetime.now(UTC).replace(tzinfo=None)
        grant_doc_access(
            db,
            doc_id=doc.id,
            user_id=expired_user_id,
            granted_by_user_id=owner_id,
            granted_by_meeting_id=None,
            reason="meeting_attendee",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        )
        db.commit()

        projection = load_native_doc_projection(db, doc_id=doc.id)

    assert projection is not None
    assert projection.resource_type == NATIVE_DOC_RESOURCE_TYPE
    assert projection.title == "RAG Projection Smoke"
    assert "Launch Plan" in projection.text_content
    assert "Hybrid retrieval with rerank." in projection.text_content
    assert f"workspace:{workspace_id}" in projection.visibility_refs
    assert f"owner:{owner_id}" in projection.visibility_refs
    assert f"share_user:{shared_user_id}" in projection.visibility_refs
    assert f"meeting_grant:{shared_user_id}" in projection.visibility_refs
    assert f"meeting_grant:{expired_user_id}" in projection.visibility_refs
    assert f"meeting_grant:{revoked_user_id}" not in projection.visibility_refs
    assert "target:pms:space:space-42" in projection.visibility_refs
    assert any(ref.startswith("link_share_ref:") for ref in projection.visibility_refs)
    assert "secret-link-token" not in projection.text_content
    assert "secret-link-token" not in str(projection.metadata)
    assert projection.metadata["target_refs"] == ["pms:space:space-42"]
    assert projection.metadata["origin_ref"] is None


def test_native_doc_query_post_filter_rejects_expired_grant_hits(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    expired_session = create_workspace_user_session(
        client,
        workspace_key="delivery-hub",
        login_id="docsragexpiredquery",
        email="docs-rag-expired-query@ai-do.local",
        full_name="Docs RAG Expired Query",
    )
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        default_collection="docs-expired-grant-smoke",
    )

    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        expired_user = db.get(User, expired_session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert expired_user is not None
        assert workspace is not None

        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner.id,
            title="Expired Grant Doc",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Grant expiry must be rechecked at query time."}
                    ],
                },
            ],
        )
        grant_doc_access(
            db,
            doc_id=doc.id,
            user_id=expired_user.id,
            granted_by_user_id=owner.id,
            granted_by_meeting_id=None,
            reason="meeting_attendee",
            expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
        )
        db.commit()
        projection = load_native_doc_projection(db, doc_id=doc.id)
        post_filter = build_user_rag_post_filter(db, user=expired_user)
        assert projection is not None

        rag_service.sync_projection(projection)
        response = query_service.query(
            RagQueryRequest(
                collection="docs-expired-grant-smoke",
                workspace_id=workspace.id,
                query="grant expiry query time",
                filters={"visibility_refs_contains": f"meeting_grant:{expired_user.id}"},
            ),
            post_filter=post_filter,
        )

        assert response.hits == []


@pytest.mark.slow
def test_rag_post_filter_keeps_route_workspace_authoritative(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert workspace is not None

        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner.id,
            title="Workspace Boundary Doc",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Workspace scoped result."}],
                },
            ],
        )
        db.commit()
        projection = load_native_doc_projection(db, doc_id=doc.id)
        assert projection is not None

        post_filter = build_user_rag_post_filter(
            db,
            user=owner,
            workspace_id=workspace.id,
        )
        same_workspace_hit = RagVectorSearchHit(
            chunk_id="chunk-1",
            text="Workspace scoped result.",
            score=1.0,
            projection=projection,
        )
        other_workspace_hit = RagVectorSearchHit(
            chunk_id="chunk-2",
            text="Workspace scoped result.",
            score=1.0,
            projection=projection.model_copy(update={"workspace_id": "ws-other"}),
        )

        assert post_filter(same_workspace_hit) is True
        assert post_filter(other_workspace_hit) is False


@pytest.mark.slow
def test_trashed_native_doc_is_not_projected(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert workspace is not None

        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner.id,
            title="Soon Deleted",
        )
        doc.trashed_at = datetime.now(UTC).replace(tzinfo=None)
        db.add(doc)
        db.commit()

        projection = load_native_doc_projection(db, doc_id=doc.id)

    assert projection is None
