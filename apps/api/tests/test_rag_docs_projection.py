from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs import service as docs_service
from aidoo_api.domains.docs.access_grants import grant_doc_access
from aidoo_api.domains.docs.models import NativeDocLinkShare, NativeDocPage, NativeDocUserShare
from aidoo_api.domains.rag.contracts import RagAnswerMode, RagQueryRequest
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE, load_native_doc_projection
from aidoo_api.domains.rag.providers.fake import (
    FakeEmbeddingClient,
    FakeRerankClient,
    FakeVectorIndexClient,
)
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.service import RagService


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def test_native_doc_projection_includes_acl_refs_without_raw_share_token(
    client: TestClient,
) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        shared_user = db.scalar(select(User).where(User.email == "platform-admin@aidoo.local"))
        expired_user = db.scalar(select(User).where(User.email == "hq-admin@aidoo.local"))
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert shared_user is not None
        assert expired_user is not None
        assert workspace is not None
        owner_id = owner.id
        shared_user_id = shared_user.id
        expired_user_id = expired_user.id
        workspace_id = workspace.id

        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace_id,
            owner_id=owner_id,
            title="RAG Projection Smoke",
            content_blocks=[
                {"type": "heading", "content": [{"type": "text", "text": "Launch Plan"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Qdrant payload index early."}]},
            ],
            primary_container=("pms", "space", "space-42", 0),
        )
        db.add(
            NativeDocPage(
                id=new_id(),
                doc_id=doc.id,
                parent_id=None,
                title="Execution Notes",
                content_blocks=[
                    {"type": "paragraph", "content": [{"type": "text", "text": "Hybrid retrieval with rerank."}]},
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
    assert f"meeting_grant:{expired_user_id}" not in projection.visibility_refs
    assert "container:pms:space:space-42" in projection.visibility_refs
    assert any(ref.startswith("link_share_ref:") for ref in projection.visibility_refs)
    assert "secret-link-token" not in projection.text_content
    assert "secret-link-token" not in str(projection.metadata)
    assert projection.metadata["container_refs"] == ["pms:space:space-42"]
    assert projection.metadata["origin_ref"] is None


def test_native_doc_projection_smoke_syncs_and_queries_with_fake_provider(
    client: TestClient,
) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert workspace is not None
        owner_id = owner.id
        workspace_id = workspace.id

        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace_id,
            owner_id=owner_id,
            title="Searchable RAG Notes",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "Qdrant hybrid retrieval and ACL post-filter."}]},
            ],
        )
        db.commit()
        doc_id = doc.id
        projection = load_native_doc_projection(db, doc_id=doc.id)

    assert projection is not None

    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        rerank_client=FakeRerankClient(),
        default_collection="docs-vertical-smoke",
    )
    sync_result = rag_service.sync_projection(projection)

    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        rerank_client=FakeRerankClient(),
    )
    response = query_service.query(
        RagQueryRequest(
            collection="docs-vertical-smoke",
            workspace_id=workspace_id,
            query="hybrid retrieval post-filter",
            answer_mode=RagAnswerMode.GROUNDED_ANSWER,
            filters={"visibility_refs_contains": f"owner:{owner_id}"},
        ),
        post_filter=lambda hit: f"owner:{owner_id}" in hit.projection.visibility_refs,
    )

    assert sync_result.chunk_count >= 1
    assert response.hits
    assert response.hits[0].resource_id == doc_id
    assert response.hits[0].resource_type == NATIVE_DOC_RESOURCE_TYPE
    assert response.grounded_answer is not None
    assert response.grounded_answer.citations
    assert response.sources_used == [projection.source_kind]


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
