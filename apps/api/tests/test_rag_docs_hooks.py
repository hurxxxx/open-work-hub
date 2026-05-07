from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.principal import user_principal
from ai_do_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from ai_do_api.domains.auth.models import Workspace
from ai_do_api.domains.docs import rag_sync as docs_rag_sync
from ai_do_api.domains.docs import service as docs_service
from ai_do_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from ai_do_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob


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


def _mark_sync_jobs_succeeded(*job_ids: str) -> None:
    if not job_ids:
        return
    with get_session_factory()() as db:
        rows = list(db.scalars(select(RagSyncJob).where(RagSyncJob.id.in_(job_ids))))
        for row in rows:
            row.status = "succeeded"
            db.add(row)
        db.commit()


def _visibility_job_rows() -> list[RagVisibilityRecomputeJob]:
    with get_session_factory()() as db:
        return list(
            db.scalars(
                select(RagVisibilityRecomputeJob).order_by(
                    RagVisibilityRecomputeJob.created_at.asc(),
                    RagVisibilityRecomputeJob.id.asc(),
                )
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
        "/api/v1/workspaces/delivery-hub/docs/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "RAG Hook Doc"},
    )
    assert create_response.status_code == 201, create_response.text
    doc = create_response.json()

    create_jobs = [job for job in _job_rows() if job.resource_id == doc["id"]]
    assert [job.operation for job in create_jobs] == ["upsert"]
    assert create_jobs[0].resource_type == NATIVE_DOC_RESOURCE_TYPE
    _mark_sync_jobs_succeeded(create_jobs[0].id)

    create_page_response = client.post(
        f"/api/v1/workspaces/delivery-hub/docs/items/{doc['id']}/pages",
        headers=_auth_headers(owner["token"]),
        json={"title": "Follow-up"},
    )
    assert create_page_response.status_code == 201, create_page_response.text

    page_jobs = [job for job in _job_rows() if job.resource_id == doc["id"]]
    assert [job.operation for job in page_jobs] == ["upsert", "upsert"]
    _mark_sync_jobs_succeeded(page_jobs[-1].id)

    share_response = client.put(
        f"/api/v1/workspaces/delivery-hub/docs/items/{doc['id']}/sharing/users/{member['user']['id']}",
        headers=_auth_headers(owner["token"]),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200, share_response.text

    share_jobs = [job for job in _job_rows() if job.resource_id == doc["id"]]
    assert [job.operation for job in share_jobs] == ["upsert", "upsert", "visibility_update"]
    _mark_sync_jobs_succeeded(share_jobs[-1].id)

    delete_response = client.delete(
        f"/api/v1/workspaces/delivery-hub/docs/items/{doc['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text

    jobs = [job for job in _job_rows() if job.resource_id == doc["id"]]
    assert [job.operation for job in jobs] == ["upsert", "upsert", "visibility_update", "delete"]
    assert all(job.resource_type == NATIVE_DOC_RESOURCE_TYPE for job in jobs)


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
    assert [job.operation for job in jobs] == ["upsert"]
    assert all(job.resource_type == NATIVE_DOC_RESOURCE_TYPE for job in jobs)


def test_meeting_doc_acl_changes_enqueue_rag_visibility_recompute_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    from test_meeting import (
        _auth_headers,
        _bootstrap_admin_session,
        _create_meeting,
        _create_user_with_workspaces,
        _login,
    )

    _enable_docs_rag(monkeypatch)
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="meeting-rag-reader@ai-do.local",
        full_name="Meeting Rag Reader",
        workspace_keys=["meeting", "docs"],
    )
    attendee_token = _login(
        client,
        attendee["user"]["email"],
        attendee["temporary_password"],
    )

    create_doc = client.post(
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(admin_token),
        json={"title": "Meeting RAG Reference"},
    )
    assert create_doc.status_code == 201, create_doc.text
    doc = create_doc.json()
    doc_id = doc["source_id"]

    initial_recompute_jobs = [
        job for job in _visibility_job_rows()
        if job.scope_type == "meeting"
    ]
    assert initial_recompute_jobs == []

    meeting = _create_meeting(
        client,
        admin_token,
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
        doc_ids=[doc_id],
    )

    grant_jobs = [
        job for job in _visibility_job_rows()
        if job.scope_type == "meeting" and job.scope_id == meeting["id"]
    ]
    assert grant_jobs
    assert [
        job for job in _job_rows()
        if job.resource_id == doc_id and job.operation == "visibility_update"
    ] == []

    doc_lookup = client.get(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert doc_lookup.status_code == 200

    detach_response = client.delete(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}/docs/{doc_id}",
        headers=_auth_headers(admin_token),
    )
    assert detach_response.status_code == 200, detach_response.text

    revoke_jobs = [
        job for job in _visibility_job_rows()
        if job.scope_type == "meeting" and job.scope_id == meeting["id"]
    ]
    assert len(revoke_jobs) == 1
    assert revoke_jobs[0].id == grant_jobs[0].id
    assert revoke_jobs[0].cursor == {"doc_ids": [doc_id]}
