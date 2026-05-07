from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.access import ensure_dev_login_seed_data
from ai_do_api.domains.auth.models import Team, User, Workspace
from ai_do_api.domains.meeting.models import Meeting
from ai_do_api.domains.pms import rag_sync as pms_rag_sync
from ai_do_api.domains.pms.access_grants import (
    bump_grant_expiry_for_meeting,
    grant_issue_access,
    revoke_grants_for_issue_attachment,
    revoke_grants_for_meeting,
    revoke_grants_for_meeting_attendee,
)
from ai_do_api.domains.pms.models import Issue, IssueUserAccess, TaskList
from ai_do_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from ai_do_api.domains.rag.pms_projection import PMS_ISSUE_RESOURCE_TYPE


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


def _mark_sync_jobs_succeeded(*job_ids: str) -> None:
    if not job_ids:
        return
    with get_session_factory()() as db:
        rows = list(db.scalars(select(RagSyncJob).where(RagSyncJob.id.in_(job_ids))))
        for row in rows:
            row.status = "succeeded"
            db.add(row)
        db.commit()


def _mark_visibility_jobs_succeeded(*job_ids: str) -> None:
    if not job_ids:
        return
    with get_session_factory()() as db:
        rows = list(
            db.scalars(select(RagVisibilityRecomputeJob).where(RagVisibilityRecomputeJob.id.in_(job_ids)))
        )
        for row in rows:
            row.status = "succeeded"
            db.add(row)
        db.commit()


def _enable_pms_rag(monkeypatch) -> None:
    monkeypatch.setattr(
        pms_rag_sync,
        "get_settings",
        lambda: SimpleNamespace(rag_enabled=True),
    )


def _create_space(
    client: TestClient,
    token: str,
    *,
    name: str,
    workspace_slug: str = "delivery-hub",
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/spaces",
        headers=_auth_headers(token),
        json={"name": name, "description": ""},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list(
    client: TestClient,
    token: str,
    *,
    team_id: str,
    key: str,
    name: str,
    workspace_slug: str = "delivery-hub",
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/lists",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": "",
            "team_id": team_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_issue(
    client: TestClient,
    token: str,
    *,
    list_id: str,
    title: str,
    workspace_slug: str = "delivery-hub",
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/lists/{list_id}/issues",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "issue body",
            "status": "backlog",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_pms_router_issue_mutations_enqueue_distinct_rag_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_pms_rag(monkeypatch)
    owner = _dev_login(client, "delivery-hub-admin")
    space = _create_space(client, owner["token"], name="RAG PMS Space")
    task_list = _create_task_list(
        client,
        owner["token"],
        team_id=space["id"],
        key="RAGPMS",
        name="RAG PMS List",
    )
    issue = _create_issue(
        client,
        owner["token"],
        list_id=task_list["id"],
        title="RAG PMS Issue",
    )

    create_jobs = [job for job in _job_rows() if job.resource_id == issue["id"]]
    assert [job.operation for job in create_jobs] == ["upsert"]
    _mark_sync_jobs_succeeded(create_jobs[0].id)

    update_response = client.patch(
        f"/api/v1/workspaces/delivery-hub/pms/issues/{issue['id']}",
        headers=_auth_headers(owner["token"]),
        json={"title": "RAG PMS Issue Updated"},
    )
    assert update_response.status_code == 200, update_response.text

    update_jobs = [job for job in _job_rows() if job.resource_id == issue["id"]]
    assert [job.operation for job in update_jobs] == ["upsert", "upsert"]
    _mark_sync_jobs_succeeded(update_jobs[-1].id)

    comment_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/issues/{issue['id']}/comments",
        headers=_auth_headers(owner["token"]),
        json={"body": "latest progress note"},
    )
    assert comment_response.status_code == 201, comment_response.text

    comment_jobs = [job for job in _job_rows() if job.resource_id == issue["id"]]
    assert [job.operation for job in comment_jobs] == ["upsert", "upsert", "upsert"]
    _mark_sync_jobs_succeeded(comment_jobs[-1].id)

    delete_response = client.delete(
        f"/api/v1/workspaces/delivery-hub/pms/issues/{issue['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text

    jobs = [job for job in _job_rows() if job.resource_id == issue["id"]]
    assert [job.operation for job in jobs] == ["upsert", "upsert", "upsert", "delete"]
    assert all(job.resource_type == PMS_ISSUE_RESOURCE_TYPE for job in jobs)


def test_pms_bulk_issue_mutations_enqueue_rag_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_pms_rag(monkeypatch)
    owner = _dev_login(client, "delivery-hub-admin")
    space = _create_space(client, owner["token"], name="RAG PMS Bulk Space")
    task_list = _create_task_list(
        client,
        owner["token"],
        team_id=space["id"],
        key="RAGBLK",
        name="RAG PMS Bulk List",
    )
    first_issue = _create_issue(client, owner["token"], list_id=task_list["id"], title="Bulk First")
    second_issue = _create_issue(client, owner["token"], list_id=task_list["id"], title="Bulk Second")

    created_job_ids = [
        job.id
        for job in _job_rows()
        if job.resource_id in {first_issue["id"], second_issue["id"]}
    ]
    _mark_sync_jobs_succeeded(*created_job_ids)

    bulk_update_response = client.patch(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/issues/bulk",
        headers=_auth_headers(owner["token"]),
        json={
            "issue_ids": [first_issue["id"], second_issue["id"]],
            "status": "in_progress",
        },
    )
    assert bulk_update_response.status_code == 200, bulk_update_response.text
    assert bulk_update_response.json()["updated_count"] == 2

    updated_jobs = [
        job
        for job in _job_rows()
        if job.resource_id in {first_issue["id"], second_issue["id"]}
    ]
    assert [job.operation for job in updated_jobs if job.resource_id == first_issue["id"]] == ["upsert", "upsert"]
    assert [job.operation for job in updated_jobs if job.resource_id == second_issue["id"]] == ["upsert", "upsert"]
    _mark_sync_jobs_succeeded(
        *[
            job.id
            for job in updated_jobs
            if job.status == "pending"
        ]
    )

    bulk_delete_response = client.patch(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/issues/bulk",
        headers=_auth_headers(owner["token"]),
        json={
            "issue_ids": [first_issue["id"], second_issue["id"]],
            "delete": True,
        },
    )
    assert bulk_delete_response.status_code == 200, bulk_delete_response.text
    assert bulk_delete_response.json()["deleted_count"] == 2

    deleted_jobs = [
        job
        for job in _job_rows()
        if job.resource_id in {first_issue["id"], second_issue["id"]}
    ]
    assert [job.operation for job in deleted_jobs if job.resource_id == first_issue["id"]] == ["upsert", "upsert", "delete"]
    assert [job.operation for job in deleted_jobs if job.resource_id == second_issue["id"]] == ["upsert", "upsert", "delete"]


def test_pms_metadata_mutations_enqueue_visibility_recompute_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_pms_rag(monkeypatch)
    owner = _dev_login(client, "delivery-hub-admin")
    space = _create_space(client, owner["token"], name="RAG PMS Metadata Space")
    task_list = _create_task_list(
        client,
        owner["token"],
        team_id=space["id"],
        key="RAGMETA",
        name="RAG PMS Metadata List",
    )
    issue = _create_issue(client, owner["token"], list_id=task_list["id"], title="Metadata Issue")
    _mark_sync_jobs_succeeded(*[job.id for job in _job_rows() if job.resource_id == issue["id"]])

    list_update = client.patch(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}",
        headers=_auth_headers(owner["token"]),
        json={"name": "RAG PMS Metadata List Updated"},
    )
    assert list_update.status_code == 200, list_update.text
    list_jobs = [
        job for job in _visibility_job_rows() if job.scope_type == pms_rag_sync.PMS_TASK_LIST_RECOMPUTE_SCOPE
    ]
    assert len(list_jobs) == 1
    assert list_jobs[0].scope_id == task_list["id"]
    _mark_visibility_jobs_succeeded(list_jobs[0].id)

    milestone_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/milestones",
        headers=_auth_headers(owner["token"]),
        json={"title": "Sprint Alpha", "description": "", "status": "planned", "sort_order": 0},
    )
    assert milestone_response.status_code == 201, milestone_response.text
    milestone = milestone_response.json()

    milestone_update = client.patch(
        f"/api/v1/workspaces/delivery-hub/pms/milestones/{milestone['id']}",
        headers=_auth_headers(owner["token"]),
        json={"title": "Sprint Beta"},
    )
    assert milestone_update.status_code == 200, milestone_update.text
    milestone_jobs = [
        job for job in _visibility_job_rows() if job.scope_type == pms_rag_sync.PMS_MILESTONE_RECOMPUTE_SCOPE
    ]
    assert len(milestone_jobs) == 1
    assert milestone_jobs[0].scope_id == milestone["id"]
    _mark_visibility_jobs_succeeded(milestone_jobs[0].id)

    label_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/labels",
        headers=_auth_headers(owner["token"]),
        json={"name": "Backend", "color": "#111827"},
    )
    assert label_response.status_code == 201, label_response.text
    label = label_response.json()

    assign_label = client.patch(
        f"/api/v1/workspaces/delivery-hub/pms/issues/{issue['id']}",
        headers=_auth_headers(owner["token"]),
        json={"label_ids": [label["id"]]},
    )
    assert assign_label.status_code == 200, assign_label.text
    _mark_sync_jobs_succeeded(*[job.id for job in _job_rows() if job.resource_id == issue["id"] and job.status == "pending"])

    label_update = client.patch(
        f"/api/v1/workspaces/delivery-hub/pms/labels/{label['id']}",
        headers=_auth_headers(owner["token"]),
        json={"name": "Infra"},
    )
    assert label_update.status_code == 200, label_update.text
    label_jobs = [
        job for job in _visibility_job_rows() if job.scope_type == pms_rag_sync.PMS_LABEL_RECOMPUTE_SCOPE
    ]
    assert len(label_jobs) == 1
    assert label_jobs[0].scope_id == label["id"]
    _mark_visibility_jobs_succeeded(label_jobs[0].id)

    label_delete = client.delete(
        f"/api/v1/workspaces/delivery-hub/pms/labels/{label['id']}",
        headers=_auth_headers(owner["token"]),
    )
    assert label_delete.status_code == 204, label_delete.text
    deleted_label_jobs = [
        job for job in _visibility_job_rows() if job.scope_type == pms_rag_sync.PMS_LABEL_RECOMPUTE_SCOPE
    ]
    assert len(deleted_label_jobs) == 2
    assert deleted_label_jobs[-1].cursor == {"issue_ids": [issue["id"]], "operation": "upsert"}


def test_meeting_issue_acl_changes_enqueue_rag_visibility_recompute_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    from test_meeting import (
        _bootstrap_admin_session,
        _create_meeting,
        _create_user_with_workspaces,
        _login,
    )

    _enable_pms_rag(monkeypatch)
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    workspace_slug = "hq"
    space = _create_space(client, admin_token, name="RAG Meeting Space", workspace_slug=workspace_slug)
    task_list = _create_task_list(
        client,
        admin_token,
        team_id=space["id"],
        key="RAGMTG",
        name="RAG Meeting List",
        workspace_slug=workspace_slug,
    )
    issue = _create_issue(
        client,
        admin_token,
        list_id=task_list["id"],
        title="Meeting-shared RAG issue",
        workspace_slug=workspace_slug,
    )
    _mark_sync_jobs_succeeded(*[job.id for job in _job_rows() if job.resource_id == issue["id"]])

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="meeting-rag-issue-reader@ai-do.local",
        full_name="Meeting Rag Issue Reader",
        workspace_keys=["meeting", "pms"],
    )
    attendee_token = _login(
        client,
        attendee["user"]["email"],
        attendee["temporary_password"],
    )

    meeting = _create_meeting(
        client,
        admin_token,
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
        task_ids=[issue["id"]],
    )

    grant_jobs = [
        job
        for job in _visibility_job_rows()
        if job.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE and job.scope_id == meeting["id"]
    ]
    assert len(grant_jobs) == 1
    assert grant_jobs[0].cursor == {"issue_ids": [issue["id"]], "operation": "visibility_update"}
    assert [
        job for job in _job_rows() if job.resource_id == issue["id"] and job.operation == "visibility_update"
    ] == []
    _mark_visibility_jobs_succeeded(grant_jobs[0].id)

    issue_detail = client.get(
        f"/api/v1/workspaces/{workspace_slug}/pms/issues/{issue['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert issue_detail.status_code == 200, issue_detail.text

    detach_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/tasks/{issue['id']}",
        headers=_auth_headers(admin_token),
    )
    assert detach_response.status_code == 200, detach_response.text

    revoke_jobs = [
        job
        for job in _visibility_job_rows()
        if job.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE and job.scope_id == meeting["id"]
    ]
    assert len(revoke_jobs) == 2
    assert revoke_jobs[-1].cursor == {"issue_ids": [issue["id"]], "operation": "visibility_update"}


def test_pms_access_grant_helpers_enqueue_expected_job_types(
    client: TestClient,
    monkeypatch,
) -> None:
    _enable_pms_rag(monkeypatch)
    with get_session_factory()() as db:
        workspace = Workspace(
            id="rag-pms-ws",
            key="rag-pms-ws",
            name="RAG PMS Workspace",
            description="",
            active=True,
        )
        reporter = User(
            id="rag-pms-owner",
            email="rag-pms-owner@ai-do.local",
            full_name="RAG PMS Owner",
            password_hash="hash",
            status="active",
        )
        attendee = User(
            id="rag-pms-attendee",
            email="rag-pms-attendee@ai-do.local",
            full_name="RAG PMS Attendee",
            password_hash="hash",
            status="active",
        )
        team = Team(
            id="rag-pms-team",
            workspace_id=workspace.id,
            key="RAGTEAM",
            name="RAG Team",
            description="",
            active=True,
        )
        task_list = TaskList(
            id="rag-pms-list",
            key="RAGUNIT",
            name="RAG Unit List",
            description="",
            status="active",
            archived=False,
            team_id=team.id,
            folder_id=None,
            created_by_id=reporter.id,
        )
        issue = Issue(
            id="rag-pms-issue",
            list_id=task_list.id,
            issue_number=1,
            title="RAG Unit Issue",
            description="",
            status="backlog",
            priority="medium",
            reporter_id=reporter.id,
            assignee_id=None,
            archived=False,
        )
        meeting = Meeting(
            id="rag-pms-meeting",
            workspace_id=workspace.id,
            organizer_id=reporter.id,
            notes_doc_id=None,
            notes_page_id=None,
            title="RAG Unit Meeting",
            agenda="",
            start_at=datetime(2026, 4, 22, 0, 0, 0),
            end_at=datetime(2026, 4, 22, 1, 0, 0),
            status="scheduled",
        )
        db.add_all([workspace, reporter, attendee, team])
        db.commit()
        db.add_all([task_list, meeting])
        db.commit()
        db.add(issue)
        db.commit()

        grant_issue_access(
            db,
            issue_id=issue.id,
            user_id=attendee.id,
            granted_by_user_id=reporter.id,
            granted_by_meeting_id=None,
            reason="manual_share",
        )
        db.commit()

        sync_jobs = list(
            db.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.resource_id == issue.id,
                    RagSyncJob.operation == "visibility_update",
                )
            )
        )
        assert len(sync_jobs) == 1
        sync_jobs[0].status = "succeeded"
        db.add(sync_jobs[0])
        db.commit()

        grant_issue_access(
            db,
            issue_id=issue.id,
            user_id=attendee.id,
            granted_by_user_id=reporter.id,
            granted_by_meeting_id=meeting.id,
            reason="meeting_attendee",
        )
        db.commit()

        recompute_jobs = list(
            db.scalars(
                select(RagVisibilityRecomputeJob).where(
                    RagVisibilityRecomputeJob.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE,
                    RagVisibilityRecomputeJob.scope_id == meeting.id,
                )
            )
        )
        assert len(recompute_jobs) == 1
        recompute_jobs[0].status = "succeeded"
        db.add(recompute_jobs[0])
        db.commit()

        assert revoke_grants_for_meeting_attendee(
            db,
            meeting_id=meeting.id,
            user_id=attendee.id,
            revoked_by_user_id=reporter.id,
            reason="attendee_removed",
        ) == 1
        db.commit()
        attendee_revoke = db.scalar(
            select(RagVisibilityRecomputeJob)
            .where(RagVisibilityRecomputeJob.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE)
            .order_by(RagVisibilityRecomputeJob.created_at.desc(), RagVisibilityRecomputeJob.id.desc())
        )
        assert attendee_revoke is not None
        attendee_revoke.status = "succeeded"
        db.add(attendee_revoke)
        db.commit()

        grant_issue_access(
            db,
            issue_id=issue.id,
            user_id=attendee.id,
            granted_by_user_id=reporter.id,
            granted_by_meeting_id=meeting.id,
            reason="meeting_attendee",
        )
        db.commit()
        latest_grant = db.scalar(
            select(IssueUserAccess)
            .where(IssueUserAccess.issue_id == issue.id, IssueUserAccess.revoked_at.is_(None))
            .order_by(IssueUserAccess.created_at.desc())
        )
        assert latest_grant is not None
        latest_job = db.scalar(
            select(RagVisibilityRecomputeJob)
            .where(RagVisibilityRecomputeJob.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE)
            .order_by(RagVisibilityRecomputeJob.created_at.desc(), RagVisibilityRecomputeJob.id.desc())
        )
        assert latest_job is not None
        latest_job.status = "succeeded"
        db.add(latest_job)
        db.commit()

        assert revoke_grants_for_issue_attachment(
            db,
            meeting_id=meeting.id,
            issue_id=issue.id,
            revoked_by_user_id=reporter.id,
            reason="task_detached",
        ) == 1
        db.commit()
        latest_job = db.scalar(
            select(RagVisibilityRecomputeJob)
            .where(RagVisibilityRecomputeJob.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE)
            .order_by(RagVisibilityRecomputeJob.created_at.desc(), RagVisibilityRecomputeJob.id.desc())
        )
        assert latest_job is not None
        latest_job.status = "succeeded"
        db.add(latest_job)
        db.commit()

        grant_issue_access(
            db,
            issue_id=issue.id,
            user_id=attendee.id,
            granted_by_user_id=reporter.id,
            granted_by_meeting_id=meeting.id,
            reason="meeting_attendee",
        )
        db.commit()
        latest_job = db.scalar(
            select(RagVisibilityRecomputeJob)
            .where(RagVisibilityRecomputeJob.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE)
            .order_by(RagVisibilityRecomputeJob.created_at.desc(), RagVisibilityRecomputeJob.id.desc())
        )
        assert latest_job is not None
        latest_job.status = "succeeded"
        db.add(latest_job)
        db.commit()

        assert bump_grant_expiry_for_meeting(
            db,
            meeting_id=meeting.id,
            new_end_at=datetime(2026, 4, 22, 2, 0, 0),
        ) == 1
        db.commit()
        latest_job = db.scalar(
            select(RagVisibilityRecomputeJob)
            .where(RagVisibilityRecomputeJob.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE)
            .order_by(RagVisibilityRecomputeJob.created_at.desc(), RagVisibilityRecomputeJob.id.desc())
        )
        assert latest_job is not None
        latest_job.status = "succeeded"
        db.add(latest_job)
        db.commit()

        assert revoke_grants_for_meeting(
            db,
            meeting_id=meeting.id,
            revoked_by_user_id=reporter.id,
            reason="meeting_deleted",
        ) == 1
        db.commit()

        recompute_jobs = list(
            db.scalars(
                select(RagVisibilityRecomputeJob)
                .where(RagVisibilityRecomputeJob.scope_type == pms_rag_sync.PMS_MEETING_VISIBILITY_SCOPE)
                .order_by(RagVisibilityRecomputeJob.created_at.asc(), RagVisibilityRecomputeJob.id.asc())
            )
        )
        assert len(recompute_jobs) == 7
        assert all(job.cursor == {"issue_ids": [issue.id], "operation": "visibility_update"} for job in recompute_jobs)
