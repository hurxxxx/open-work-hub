from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.core.principal import user_principal
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.docs import service as docs_service
from aidoo_api.domains.meeting import service as meeting_service
from aidoo_api.domains.pms import service as pms_service
from aidoo_api.domains.pms.models import Issue, IssueActivityLog, IssueComment, Notification
from aidoo_api.domains.planner import service as planner_service
from aidoo_api.domains.planner.models import PlannerEvent


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def test_meeting_create_meeting_for_ai_creates_meeting_and_is_idempotent(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        created = meeting_service.create_meeting_for_ai(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.meeting.create_meeting_for_ai",
            ),
            user=user,
            title="AI-created meeting",
            start_at=planner_service.parse_iso_or_date("2026-05-15T01:00:00+00:00"),
            end_at=planner_service.parse_iso_or_date("2026-05-15T02:00:00+00:00"),
            approved_call_id="approval-meeting-1",
        )
        replayed = meeting_service.create_meeting_for_ai(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.meeting.create_meeting_for_ai.replay",
            ),
            user=user,
            title="AI-created meeting",
            start_at=planner_service.parse_iso_or_date("2026-05-15T01:00:00+00:00"),
            end_at=planner_service.parse_iso_or_date("2026-05-15T02:00:00+00:00"),
            approved_call_id="approval-meeting-1",
        )

    assert created["id"] == "approval-meeting-1"
    assert replayed["id"] == created["id"]
    assert created["title"] == "AI-created meeting"


def test_planner_create_event_for_ai_creates_event_and_is_idempotent(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        created = planner_service.create_event_for_ai(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.planner.create_event_for_ai",
            ),
            user=user,
            title="AI-created event",
            start_at=planner_service.parse_iso_or_date("2026-05-16T01:00:00+00:00"),
            end_at=planner_service.parse_iso_or_date("2026-05-16T02:00:00+00:00"),
            approved_call_id="approval-event-1",
        )
        replayed = planner_service.create_event_for_ai(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.planner.create_event_for_ai.replay",
            ),
            user=user,
            title="AI-created event",
            start_at=planner_service.parse_iso_or_date("2026-05-16T01:00:00+00:00"),
            end_at=planner_service.parse_iso_or_date("2026-05-16T02:00:00+00:00"),
            approved_call_id="approval-event-1",
        )

    assert created["id"] == "approval-event-1"
    assert replayed["id"] == created["id"]
    assert created["title"] == "AI-created event"


def test_planner_create_event_for_ai_rejects_team_scope(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        with pytest.raises(HTTPException, match="Team-scoped planner events are not supported yet"):
            planner_service.create_event_for_ai(
                db,
                workspace=workspace,
                principal=user_principal(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    source="test.planner.create_event_for_ai.team_scope",
                ),
                user=user,
                title="AI-created team event",
                start_at=planner_service.parse_iso_or_date("2026-05-16T01:00:00+00:00"),
                end_at=planner_service.parse_iso_or_date("2026-05-16T02:00:00+00:00"),
                scope="team",
                team_id="team-1",
            )


def test_planner_update_and_delete_event_for_ai_mutate_event(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None
        principal = user_principal(
            workspace_id=workspace.id,
            user_id=user.id,
            source="test.planner.crud_for_ai",
        )

        created = planner_service.create_event_for_ai(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            title="AI event before update",
            start_at=planner_service.parse_iso_or_date("2026-05-17T01:00:00+00:00"),
            end_at=planner_service.parse_iso_or_date("2026-05-17T02:00:00+00:00"),
            approved_call_id="approval-event-crud-1",
        )
        updated = planner_service.update_event_for_ai(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            event_id=created["id"],
            title="AI event after update",
            description="updated by AI approval path",
            visibility="public",
            approved_call_id="approval-event-crud-update-1",
        )

        assert updated["title"] == "AI event after update"
        assert updated["description"] == "updated by AI approval path"
        assert updated["visibility"] == "public"

        deleted = planner_service.delete_event_for_ai(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            event_id=created["id"],
            approved_call_id="approval-event-crud-delete-1",
        )
        remaining = db.scalar(select(PlannerEvent).where(PlannerEvent.id == created["id"]))

    assert deleted == {"id": "approval-event-crud-1", "deleted": True}
    assert remaining is None


def test_docs_create_page_service_creates_page_and_is_idempotent(client: TestClient) -> None:
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
            title="AI docs hub",
        )
        db.commit()

        created = docs_service.create_page(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.docs.create_page",
            ),
            user=user,
            hub_id=doc.id,
            title="AI-created page",
            content_markdown="# 제목\n\n본문",
            approved_call_id="approval-page-1",
        )
        replayed = docs_service.create_page(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.docs.create_page.replay",
            ),
            user=user,
            hub_id=doc.id,
            title="AI-created page",
            content_markdown="# 제목\n\n본문",
            approved_call_id="approval-page-1",
        )

    assert created["id"] == "approval-page-1"
    assert replayed["id"] == created["id"]
    assert created["doc_id"] == doc.id
    assert created["title"] == "AI-created page"


def test_pms_create_issue_service_is_idempotent_with_approved_call_id(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "AIWRITECREATE", "name": "AI Write Create", "description": "write source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        created = pms_service.create_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.create_issue.idempotent",
            ),
            user=user,
            list_id=task_list["id"],
            title="AI idempotent issue",
            approved_call_id="approval-pms-issue-1",
        )
        replayed = pms_service.create_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.create_issue.idempotent.replay",
            ),
            user=user,
            list_id=task_list["id"],
            title="AI idempotent issue",
            approved_call_id="approval-pms-issue-1",
        )
        issue_rows = list(db.scalars(select(Issue).where(Issue.id == "approval-pms-issue-1")))

    assert created["id"] == "approval-pms-issue-1"
    assert replayed["id"] == created["id"]
    assert len(issue_rows) == 1


def test_pms_add_issue_comment_service_is_idempotent_with_approved_call_id(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "AIWRITECMT", "name": "AI Write Comment", "description": "write source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "AI comment target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        created = pms_service.add_issue_comment(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.add_issue_comment.idempotent",
            ),
            user=user,
            issue_id=issue["id"],
            body="hello idempotent comment",
            approved_call_id="approval-pms-comment-1",
        )
        replayed = pms_service.add_issue_comment(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.add_issue_comment.idempotent.replay",
            ),
            user=user,
            issue_id=issue["id"],
            body="hello idempotent comment",
            approved_call_id="approval-pms-comment-1",
        )
        comment_rows = list(
            db.scalars(select(IssueComment).where(IssueComment.id == "approval-pms-comment-1"))
        )

    assert created["id"] == "approval-pms-comment-1"
    assert replayed["id"] == created["id"]
    assert len(comment_rows) == 1


def test_pms_update_issue_service_does_not_duplicate_side_effects_on_replay(
    client: TestClient,
) -> None:
    admin_session = _dev_login(client, "delivery-hub-admin")
    member_session = _dev_login(client, "delivery-hub-member")
    token = admin_session["token"]

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "AIWRITEUPD", "name": "AI Write Update", "description": "write source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "AI update target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, admin_session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        updated = pms_service.update_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.update_issue.idempotent",
            ),
            user=user,
            issue_id=issue["id"],
            provided_fields={"status", "assignee_ids"},
            status="in_progress",
            assignee_ids=[member_session["user"]["id"]],
            approved_call_id="approval-pms-update-1",
        )
        activity_ids_after_first = list(
            db.scalars(select(IssueActivityLog.id).where(IssueActivityLog.issue_id == issue["id"]))
        )
        notification_ids_after_first = list(
            db.scalars(select(Notification.id).where(Notification.reference_id == issue["id"]))
        )

        replayed = pms_service.update_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.update_issue.idempotent.replay",
            ),
            user=user,
            issue_id=issue["id"],
            provided_fields={"status", "assignee_ids"},
            status="in_progress",
            assignee_ids=[member_session["user"]["id"]],
            approved_call_id="approval-pms-update-1",
        )
        activity_ids_after_second = list(
            db.scalars(select(IssueActivityLog.id).where(IssueActivityLog.issue_id == issue["id"]))
        )
        notification_ids_after_second = list(
            db.scalars(select(Notification.id).where(Notification.reference_id == issue["id"]))
        )

    assert updated["assignee_ids"] == [member_session["user"]["id"]]
    assert replayed["id"] == updated["id"]
    assert activity_ids_after_second == activity_ids_after_first
    assert notification_ids_after_second == notification_ids_after_first


def test_pms_delete_issue_service_deletes_issue(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers={"Authorization": f"Bearer {token}"},
        json={"key": "AIWRITEDEL", "name": "AI Write Delete", "description": "write source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "AI delete target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        deleted = pms_service.delete_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.delete_issue",
            ),
            user=user,
            issue_id=issue["id"],
            approved_call_id="approval-pms-delete-1",
        )
        remaining = db.scalar(select(Issue).where(Issue.id == issue["id"]))

    assert deleted == {"id": issue["id"], "deleted": True}
    assert remaining is None
