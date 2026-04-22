from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.core.principal import user_principal
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.docs import rag_sync as docs_rag_sync
from aidoo_api.domains.docs import service as docs_service
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from aidoo_api.domains.rag.models import RagSyncJob


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _job_rows() -> list[RagSyncJob]:
    with get_session_factory()() as db:
        return list(
            db.scalars(
                select(RagSyncJob).order_by(RagSyncJob.created_at.asc(), RagSyncJob.id.asc())
            )
        )


def _enable_docs_rag(monkeypatch) -> None:
    monkeypatch.setattr(
        docs_rag_sync,
        "get_settings",
        lambda: SimpleNamespace(rag_enabled=True),
    )


def test_docs_router_mutations_enqueue_rag_jobs(client: TestClient, monkeypatch) -> None:
    _enable_docs_rag(monkeypatch)
    owner = _dev_login(client, "delivery-hub-admin")
    member = _dev_login(client, "delivery-hub-member")

    create_response = client.post(
        "/api/v1/docs/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "RAG Hook Doc"},
    )
    assert create_response.status_code == 201, create_response.text
    doc = create_response.json()

    jobs = _job_rows()
    assert [job.operation for job in jobs] == ["upsert"]
    assert jobs[0].resource_type == NATIVE_DOC_RESOURCE_TYPE
    assert jobs[0].resource_id == doc["id"]

    create_page_response = client.post(
        f"/api/v1/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner["token"]),
        json={"title": "Follow-up"},
    )
    assert create_page_response.status_code == 201, create_page_response.text

    share_response = client.put(
        f"/api/v1/docs/items/{doc['id']}/sharing/users/{member['user']['id']}",
        headers=_auth_headers(owner["token"]),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200, share_response.text

    delete_response = client.delete(
        f"/api/v1/docs/items/{doc['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text

    jobs = _job_rows()
    assert [job.operation for job in jobs] == [
        "upsert",
        "upsert",
        "visibility_update",
        "delete",
    ]
    assert all(job.resource_type == NATIVE_DOC_RESOURCE_TYPE for job in jobs)
    assert all(job.resource_id == doc["id"] for job in jobs)


def test_docs_service_create_paths_enqueue_once_for_idempotent_replay(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_docs_rag(monkeypatch)
    session = _dev_login(client, "delivery-hub-admin")

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            title="Service Hook Doc",
        )
        db.commit()

        created = docs_service.create_page(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.docs.rag.create_page",
            ),
            user=user,
            hub_id=doc.id,
            title="Approval Page",
            content_markdown="본문",
            approved_call_id="approval-page-rag-1",
        )
        replayed = docs_service.create_page(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.docs.rag.create_page.replay",
            ),
            user=user,
            hub_id=doc.id,
            title="Approval Page",
            content_markdown="본문",
            approved_call_id="approval-page-rag-1",
        )

    assert created["id"] == replayed["id"]

    jobs = [job for job in _job_rows() if job.resource_id == doc.id]
    assert [job.operation for job in jobs] == ["upsert", "upsert"]
    assert all(job.resource_type == NATIVE_DOC_RESOURCE_TYPE for job in jobs)
