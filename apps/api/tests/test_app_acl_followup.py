from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.access import load_user_graph
from open_work_hub_api.domains.auth.dependencies import resolve_auth_context_from_token
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.pms.space_models import Team, TeamMember
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs.models import (
    DocMeetingAccess,
    NativeDoc,
    NativeDocTarget,
    NativeDocUserShare,
)
from open_work_hub_api.domains.pms.models import Task, TaskList, TaskUserAccess
from open_work_hub_api.domains.source_access import SourceAclPolicy


def _private_task(db, owner_id):
    team = Team(id=new_id(), key=new_id(), name="Private space")
    task_list = TaskList(
        id=new_id(), key=new_id()[:12], name="Private list", team_id=team.id, created_by_id=owner_id
    )
    task = Task(
        id=new_id(), list_id=task_list.id, task_number=1, title="Private task", reporter_id=owner_id
    )
    db.add(team)
    db.flush()
    db.add(task_list)
    db.flush()
    db.add(task)
    db.flush()
    return team, task_list, task


def test_admin_cannot_issue_impersonation_sessions(client: TestClient) -> None:
    member = dev_login(client, "delivery-hub-member")
    admin = dev_login(client)
    response = client.post(
        f"/api/v1/auth/impersonations/{member['user']['id']}", headers=auth_headers(admin["token"])
    )
    assert response.status_code == 404, response.text
    current = client.get("/api/v1/auth/me", headers=auth_headers(member["token"]))
    assert current.status_code == 200, current.text
    assert current.json()["id"] == member["user"]["id"]


def test_reused_auth_context_refreshes_current_account_state(client: TestClient) -> None:
    member = dev_login(client, "delivery-hub-member")
    with get_session_factory()() as db:
        previous = resolve_auth_context_from_token(db, member["token"], update_last_seen=False)
        with get_session_factory()() as writer:
            writer.execute(
                update(User).where(User.id == previous.user.id).values(login_blocked=True)
            )
            writer.commit()
        with pytest.raises(HTTPException) as denied:
            resolve_auth_context_from_token(db, member["token"], update_last_seen=False)
        assert denied.value.status_code == 403


def test_admin_state_does_not_change_independently_issued_user_session(client: TestClient) -> None:
    member = dev_login(client, "delivery-hub-member")
    admin = dev_login(client)
    with get_session_factory()() as db:
        db.execute(update(User).where(User.id == admin["user"]["id"]).values(login_blocked=True))
        db.commit()
    denied = client.get("/api/v1/auth/me", headers=auth_headers(admin["token"]))
    assert denied.status_code == 403, denied.text
    current = client.get("/api/v1/auth/me", headers=auth_headers(member["token"]))
    assert current.status_code == 200, current.text
    assert current.json()["id"] == member["user"]["id"]


@pytest.mark.parametrize("grant", ["private_team", "invalid_direct", "invalid_meeting"])
def test_docs_source_acl_cannot_exceed_document_acl(client: TestClient, grant: str) -> None:
    admin = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")
    actor = admin if grant == "private_team" else member
    owner = member if grant == "private_team" else admin
    with get_session_factory()() as db:
        doc = NativeDoc(
            id=new_id(),
            owner_id=owner["user"]["id"],
            title="Private document",
            rag_scope="official",
            source_kind="private_review_source",
        )
        if grant == "private_team":
            team = Team(id=new_id(), key=new_id(), name="Private team")
            db.add(team)
            db.flush()
            doc.targets.append(
                NativeDocTarget(
                    id=new_id(),
                    target_app="pms",
                    target_type="space",
                    target_id=team.id,
                )
            )
        elif grant == "invalid_direct":
            doc.user_shares.append(
                NativeDocUserShare(
                    id=new_id(),
                    user_id=actor["user"]["id"],
                    created_by_id=owner["user"]["id"],
                    access_level="unknown",
                )
            )
        else:
            doc.meeting_access_grants.append(
                DocMeetingAccess(
                    id=new_id(),
                    user_id=actor["user"]["id"],
                    granted_by_user_id=owner["user"]["id"],
                    access_level="unknown",
                )
            )
        db.add(doc)
        db.commit()
        doc_id = doc.id
    response = client.get(
        f"/api/v1/docs/items/{doc_id}",
        headers=auth_headers(actor["token"]),
    )
    assert response.status_code == 404
    with get_session_factory()() as db:
        policy = SourceAclPolicy.for_user(
            db,
            user=load_user_graph(db, actor["user"]["id"]),
        )
        assert policy.can_read_native_doc(doc_id) is False
        assert policy.can_read_official_native_doc(doc_id) is False
        assert policy.authorize_many_resources([("docs_native_doc", doc_id)]) == set()
        assert policy.authorize_many_rag_resources([("docs_native_doc", doc_id)]) == set()
        assert "private_review_source" not in policy.visible_native_doc_source_kinds()
        if grant == "private_team":
            target = db.scalar(select(NativeDocTarget).where(NativeDocTarget.doc_id == doc_id))
            db.add(
                TeamMember(
                    id=new_id(),
                    team_id=target.target_id,
                    user_id=actor["user"]["id"],
                    role="viewer",
                )
            )
        else:
            model = NativeDocUserShare if grant == "invalid_direct" else DocMeetingAccess
            db.execute(update(model).where(model.doc_id == doc_id).values(access_level="read"))
        db.commit()
        assert policy.can_read_native_doc(doc_id) is True
        assert policy.can_read_official_native_doc(doc_id) is True
        assert policy.authorize_many_rag_resources([("docs_native_doc", doc_id)]) == {
            ("docs_native_doc", doc_id)
        }
        if grant == "private_team":
            db.execute(
                delete(TeamMember).where(
                    TeamMember.team_id == target.target_id,
                    TeamMember.user_id == actor["user"]["id"],
                )
            )
        elif grant == "invalid_direct":
            db.execute(delete(NativeDocUserShare).where(NativeDocUserShare.doc_id == doc_id))
        else:
            db.execute(
                update(DocMeetingAccess)
                .where(DocMeetingAccess.doc_id == doc_id)
                .values(revoked_at=datetime.now(UTC).replace(tzinfo=None))
            )
        db.commit()
        assert policy.can_read_native_doc(doc_id) is False


@pytest.mark.parametrize(
    "boundary", ["app_revoked", "inactive_team", "trashed_team", "invalid_grant"]
)
def test_task_grant_does_not_bypass_resource_context(client: TestClient, boundary: str) -> None:
    admin = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")
    dev_login(client, "knowledge-base-admin")
    with get_session_factory()() as db:
        team, _, task = _private_task(db, admin["user"]["id"])
        db.add(
            TaskUserAccess(
                id=new_id(),
                task_id=task.id,
                user_id=member["user"]["id"],
                granted_by_user_id=admin["user"]["id"],
            )
        )
        db.commit()
        task_id, team_id = task.id, team.id
    headers = auth_headers(member["token"])
    response = client.get(f"/api/v1/pms/tasks/{task_id}", headers=headers)
    assert response.status_code == 200
    with get_session_factory()() as db:
        if boundary == "app_revoked":
            from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

            db.get(AppAccessPolicy, "pms").audience = "selected"
        elif boundary == "inactive_team":
            db.execute(update(Team).where(Team.id == team_id).values(active=False))
        elif boundary == "trashed_team":
            db.execute(
                update(Team)
                .where(Team.id == team_id)
                .values(trashed_at=datetime.now(UTC).replace(tzinfo=None))
            )
        else:
            db.execute(
                update(TaskUserAccess)
                .where(TaskUserAccess.task_id == task_id)
                .values(access_level="unknown")
            )
        db.commit()
    for suffix in ("", "/custom-field-values"):
        response = client.get(f"/api/v1/pms/tasks/{task_id}{suffix}", headers=headers)
        assert response.status_code == 403


def test_unsupported_team_role_cannot_read_lists_or_sources(client: TestClient) -> None:
    admin = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")
    with get_session_factory()() as db:
        team, task_list, task = _private_task(db, admin["user"]["id"])
        db.add(
            TeamMember(id=new_id(), team_id=team.id, user_id=member["user"]["id"], role="unknown")
        )
        db.commit()
        team_id, list_id, task_id = team.id, task_list.id, task.id
    response = client.get("/api/v1/pms/spaces", headers=auth_headers(member["token"]))
    assert response.status_code == 200
    assert team_id not in {item["id"] for item in response.json()}
    response = client.get("/api/v1/pms/lists", headers=auth_headers(member["token"]))
    assert response.status_code == 200
    assert list_id not in {item["id"] for item in response.json()["items"]}
    with get_session_factory()() as db:
        policy = SourceAclPolicy.for_user(
            db,
            user=load_user_graph(db, member["user"]["id"]),
        )
        assert policy.can_read_pms_task(task_id) is False
        assert policy.can_access_scope("team", team_id) is False
        db.execute(
            update(TeamMember)
            .where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == member["user"]["id"],
            )
            .values(role=" Viewer ")
        )
        db.commit()
        assert policy.can_read_pms_task(task_id) is True
        assert policy.can_access_scope("team", team_id) is True
    response = client.get("/api/v1/pms/spaces", headers=auth_headers(member["token"]))
    assert response.status_code == 200
    assert team_id in {item["id"] for item in response.json()}
    response = client.patch(
        f"/api/v1/pms/tasks/{task_id}",
        headers=auth_headers(member["token"]),
        json={"title": "Viewer cannot write"},
    )
    assert response.status_code == 403
