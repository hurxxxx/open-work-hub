from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
import aidoo_api.core.settings as core_settings
import aidoo_api.domains.meeting.rag_sync as meeting_rag_sync
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from aidoo_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.meeting.models import Meeting, MeetingAttendee, MeetingRecording
from aidoo_api.domains.rag.access_filter import build_user_rag_post_filter
from aidoo_api.domains.rag.contracts import RagQueryRequest, RagSyncOperation
from aidoo_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE, load_meeting_projection
from aidoo_api.domains.rag.models import RagSyncJob
from aidoo_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.service import RagService


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _job_rows(resource_id: str) -> list[RagSyncJob]:
    with get_session_factory()() as db:
        return list(
            db.scalars(
                select(RagSyncJob)
                .where(RagSyncJob.resource_id == resource_id)
                .order_by(RagSyncJob.created_at.asc(), RagSyncJob.id.asc())
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


def _enable_meeting_rag(monkeypatch) -> None:
    settings = SimpleNamespace(rag_enabled=True)
    monkeypatch.setattr(
        core_settings,
        "get_settings",
        lambda: settings,
    )
    monkeypatch.setattr(meeting_rag_sync, "get_settings", lambda: settings)


def test_meeting_projection_and_query_acl_follow_participants(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        organizer = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert organizer is not None
        assert workspace is not None

        attendee = User(
            id=new_id(),
            email="meeting-attendee-rag@aidoo.local",
            full_name="Meeting Attendee",
            password_hash="hash",
            status="active",
        )
        outsider = User(
            id=new_id(),
            email="meeting-outsider-rag@aidoo.local",
            full_name="Meeting Outsider",
            password_hash="hash",
            status="active",
        )
        db.add_all([attendee, outsider])
        db.flush()
        db.add_all(
            [
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace.id,
                    user_id=attendee.id,
                    role="member",
                ),
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace.id,
                    user_id=outsider.id,
                    role="member",
                ),
            ]
        )
        meeting = Meeting(
            id=new_id(),
            workspace_id=workspace.id,
            organizer_id=organizer.id,
            title="RAG Meeting Sync",
            agenda="Finalize rollout checklist",
            start_at=datetime(2026, 5, 20, 1, 0, 0),
            end_at=datetime(2026, 5, 20, 2, 0, 0),
            status="scheduled",
        )
        db.add(meeting)
        db.flush()
        db.add(
            MeetingAttendee(
                id=new_id(),
                meeting_id=meeting.id,
                user_id=attendee.id,
                role="required",
                response="accepted",
            )
        )
        db.add(
            MeetingRecording(
                id=new_id(),
                meeting_id=meeting.id,
                storage_key="meeting/test-audio.webm",
                file_size=123,
                mime_type="audio/webm",
                idempotency_key="rag-meeting-recording",
                uploaded_by_id=organizer.id,
                source="manual_upload",
                transcription_status="done",
                progress_pct=100,
                transcript_text="Budget risk was reviewed and rollout owners were assigned.",
                summary_text="Rollout owners assigned and budget risk reviewed.",
            )
        )
        db.commit()

        projection = load_meeting_projection(db, meeting_id=meeting.id)
        assert projection is not None
        assert projection.resource_type == MEETING_RESOURCE_TYPE
        assert f"meeting_organizer:{organizer.id}" in projection.visibility_refs
        assert f"meeting_attendee:{attendee.id}" in projection.visibility_refs
        assert "budget risk reviewed" in projection.text_content.lower()

        vector_index = FakeVectorIndexClient()
        rag_service = RagService(
            vector_index=vector_index,
            embedding_client=FakeEmbeddingClient(),
        )
        query_service = RagQueryService(
            vector_index=vector_index,
            embedding_client=FakeEmbeddingClient(),
        )
        rag_service.sync_projection(projection, collection="meeting-rag-test")

        attendee_filter = build_user_rag_post_filter(db, user=attendee)
        outsider_filter = build_user_rag_post_filter(db, user=outsider)

        attendee_response = query_service.query(
            RagQueryRequest(
                collection="meeting-rag-test",
                workspace_id=workspace.id,
                query="budget risk owners assigned",
                top_k=3,
            ),
            post_filter=attendee_filter,
        )
        outsider_response = query_service.query(
            RagQueryRequest(
                collection="meeting-rag-test",
                workspace_id=workspace.id,
                query="budget risk owners assigned",
                top_k=3,
            ),
            post_filter=outsider_filter,
        )

    assert [hit.resource_id for hit in attendee_response.hits] == [projection.resource_id]
    assert outsider_response.hits == []


def test_meeting_router_mutations_enqueue_rag_jobs(client: TestClient, monkeypatch) -> None:
    _enable_meeting_rag(monkeypatch)
    owner = _dev_login(client, "delivery-hub-admin")

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        attendee = User(
            id=new_id(),
            email="meeting-hook-attendee@aidoo.local",
            full_name="Meeting Hook Attendee",
            password_hash="hash",
            status="active",
        )
        late_attendee = User(
            id=new_id(),
            email="meeting-hook-late@aidoo.local",
            full_name="Meeting Hook Late",
            password_hash="hash",
            status="active",
        )
        db.add_all([attendee, late_attendee])
        db.flush()
        db.add_all(
            [
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace.id,
                    user_id=attendee.id,
                    role="member",
                ),
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace.id,
                    user_id=late_attendee.id,
                    role="member",
                ),
            ]
        )
        db.commit()
        attendee_id = attendee.id
        late_attendee_id = late_attendee.id

    create_response = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(owner["token"]),
        json={
            "title": "Meeting Hook Sync",
            "agenda": "Discuss rollout",
            "start_at": "2026-05-21T01:00:00",
            "end_at": "2026-05-21T02:00:00",
            "attendees": [{"user_id": attendee_id, "role": "required"}],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert create_response.status_code == 201, create_response.text
    meeting = create_response.json()

    create_jobs = _job_rows(meeting["id"])
    assert [job.operation for job in create_jobs] == [RagSyncOperation.UPSERT.value]
    _mark_sync_jobs_succeeded(create_jobs[0].id)

    update_response = client.patch(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(owner["token"]),
        json={"title": "Meeting Hook Sync Updated"},
    )
    assert update_response.status_code == 200, update_response.text

    update_jobs = _job_rows(meeting["id"])
    assert [job.operation for job in update_jobs] == [
        RagSyncOperation.UPSERT.value,
        RagSyncOperation.UPSERT.value,
    ]
    _mark_sync_jobs_succeeded(update_jobs[-1].id)

    attendee_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/attendees",
        headers=_auth_headers(owner["token"]),
        json={"attendees": [{"user_id": late_attendee_id, "role": "optional"}]},
    )
    assert attendee_response.status_code == 200, attendee_response.text

    attendee_jobs = _job_rows(meeting["id"])
    assert [job.operation for job in attendee_jobs] == [
        RagSyncOperation.UPSERT.value,
        RagSyncOperation.UPSERT.value,
        RagSyncOperation.UPSERT.value,
    ]
    _mark_sync_jobs_succeeded(attendee_jobs[-1].id)

    delete_response = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text

    jobs = _job_rows(meeting["id"])
    assert [job.operation for job in jobs] == [
        RagSyncOperation.UPSERT.value,
        RagSyncOperation.UPSERT.value,
        RagSyncOperation.UPSERT.value,
        RagSyncOperation.DELETE.value,
    ]
    assert all(job.resource_type == MEETING_RESOURCE_TYPE for job in jobs)
