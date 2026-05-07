from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
import ai_do_api.core.settings as core_settings
from ai_do_api.domains.auth.access import ensure_dev_login_seed_data
from ai_do_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from ai_do_api.domains.auth.security import new_id
import ai_do_api.domains.planner.rag_sync as planner_rag_sync
from ai_do_api.domains.rag.access_filter import build_user_rag_post_filter
from ai_do_api.domains.rag.contracts import RagQueryRequest
from ai_do_api.domains.rag.models import RagSyncJob
from ai_do_api.domains.rag.planner_projection import load_planner_event_projection
from ai_do_api.domains.rag.planner_projection import PLANNER_EVENT_RESOURCE_TYPE
from ai_do_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from ai_do_api.domains.rag.query_service import RagQueryService
from ai_do_api.domains.rag.service import RagService


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


def _enable_planner_rag(monkeypatch) -> None:
    settings = SimpleNamespace(rag_enabled=True)
    monkeypatch.setattr(
        core_settings,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(planner_rag_sync, "get_settings", lambda: settings)


def test_planner_router_mutations_enqueue_rag_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_planner_rag(monkeypatch)
    owner = _dev_login(client, "delivery-hub-admin")

    create_response = client.post(
        "/api/v1/workspaces/delivery-hub/planner/events",
        headers=_auth_headers(owner["token"]),
        json={
            "title": "RAG Planner Event",
            "description": "schedule sync",
            "location": "Pangyo",
            "visibility": "private",
            "all_day": False,
            "start": "2026-05-17T01:00:00+00:00",
            "end": "2026-05-17T02:00:00+00:00",
        },
    )
    assert create_response.status_code == 201, create_response.text
    event = create_response.json()

    create_jobs = [job for job in _job_rows() if job.resource_id == event["id"]]
    assert [job.operation for job in create_jobs] == ["upsert"]
    _mark_sync_jobs_succeeded(create_jobs[0].id)

    visibility_response = client.patch(
        f"/api/v1/workspaces/delivery-hub/planner/events/{event['id']}",
        headers=_auth_headers(owner["token"]),
        json={"visibility": "public"},
    )
    assert visibility_response.status_code == 200, visibility_response.text

    visibility_jobs = [job for job in _job_rows() if job.resource_id == event["id"]]
    assert [job.operation for job in visibility_jobs] == ["upsert", "visibility_update"]
    _mark_sync_jobs_succeeded(visibility_jobs[-1].id)

    update_response = client.patch(
        f"/api/v1/workspaces/delivery-hub/planner/events/{event['id']}",
        headers=_auth_headers(owner["token"]),
        json={"location": "Seoul"},
    )
    assert update_response.status_code == 200, update_response.text

    update_jobs = [job for job in _job_rows() if job.resource_id == event["id"]]
    assert [job.operation for job in update_jobs] == ["upsert", "visibility_update", "upsert"]
    _mark_sync_jobs_succeeded(update_jobs[-1].id)

    delete_response = client.delete(
        f"/api/v1/workspaces/delivery-hub/planner/events/{event['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text

    jobs = [job for job in _job_rows() if job.resource_id == event["id"]]
    assert [job.operation for job in jobs] == ["upsert", "visibility_update", "upsert", "delete"]
    assert all(job.resource_type == PLANNER_EVENT_RESOURCE_TYPE for job in jobs)


def test_public_planner_event_survives_rag_post_filter_for_workspace_member(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_planner_rag(monkeypatch)
    owner = _dev_login(client, "delivery-hub-admin")

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        workspace_id = workspace.id
        viewer = User(
            id=new_id(),
            email="planner-rag-viewer@ai-do.local",
            full_name="Planner Rag Viewer",
            password_hash="hash",
            status="active",
        )
        db.add(viewer)
        db.flush()
        db.add(
            WorkspaceUserBinding(
                id=new_id(),
                workspace_id=workspace.id,
                user_id=viewer.id,
                role="member",
            )
        )
        db.commit()
        viewer_id = viewer.id

    create_response = client.post(
        "/api/v1/workspaces/delivery-hub/planner/events",
        headers=_auth_headers(owner["token"]),
        json={
            "title": "Public Planner RAG Event",
            "description": "Shared rollout checkpoint",
            "location": "Seoul",
            "visibility": "public",
            "all_day": False,
            "start": "2026-05-19T01:00:00+00:00",
            "end": "2026-05-19T02:00:00+00:00",
        },
    )
    assert create_response.status_code == 201, create_response.text
    event = create_response.json()

    with get_session_factory()() as db:
        viewer = db.get(User, viewer_id)
        assert viewer is not None
        projection = load_planner_event_projection(db, event_id=event["id"])
        assert projection is not None
        vector_index = FakeVectorIndexClient()
        service = RagService(
            vector_index=vector_index,
            embedding_client=FakeEmbeddingClient(),
        )
        query = RagQueryService(
            vector_index=vector_index,
            embedding_client=FakeEmbeddingClient(),
        )
        service.sync_projection(projection, collection="planner-rag-public")
        response = query.query(
            RagQueryRequest(
                collection="planner-rag-public",
                workspace_id=workspace_id,
                query="rollout checkpoint",
                top_k=3,
            ),
            post_filter=build_user_rag_post_filter(db, user=viewer),
        )

    assert [hit.resource_id for hit in response.hits] == [event["id"]]
