from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import update

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.access import load_user_graph
from open_work_hub_api.domains.pms.access import resolve_pms_space_role
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
from open_work_hub_api.domains.auth.models import CompanyAppControl, User, UserSystemRole
from open_work_hub_api.domains.pms.space_models import Team, TeamMember
from open_work_hub_api.domains.auth.app_gate import can_use_app
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs.access_context import ensure_docs_app_access
from open_work_hub_api.domains.docs.models import (
    NativeDoc,
    NativeDocLinkShare,
    NativeDocPage,
    NativeDocUserShare,
)
from open_work_hub_api.domains.media.models import MediaFile
from open_work_hub_api.domains.media.resource_access import (
    can_resolve_media,
    ensure_media_link_resource_access,
)
from open_work_hub_api.domains.meeting.models import Meeting
from open_work_hub_api.domains.pms.models import Task, TaskList, TaskUserAccess
from open_work_hub_api.domains.source_access import SourceAclPolicy
from open_work_hub_api.domains.whiteboard.access import ensure_whiteboard_app_access
from open_work_hub_api.domains.whiteboard.models import Whiteboard, WhiteboardLinkShare


def _context(client):
    admin = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")
    return admin, member


@pytest.mark.parametrize("relationship", ["owner", "user_share"])
def test_owner_and_direct_share_require_admission_even_with_link_token(
    client: TestClient,
    relationship: str,
) -> None:
    admin, member = _context(client)
    with get_session_factory()() as db:
        doc = NativeDoc(
            id=new_id(),
            owner_id=member["user"]["id"] if relationship == "owner" else admin["user"]["id"],
            title="Revoked member document",
        )
        if relationship == "user_share":
            doc.user_shares.append(
                NativeDocUserShare(
                    id=new_id(),
                    user_id=member["user"]["id"],
                    created_by_id=admin["user"]["id"],
                    access_level="edit",
                )
            )
        db.add(doc)
        db.flush()
        doc_id = doc.id
        db.get(AppAccessPolicy, "docs").audience = "selected"
        db.commit()

    headers = auth_headers(member["token"])
    response = client.get(
        f"/api/v1/docs/items/{doc_id}",
        headers=headers,
    )
    assert response.status_code == 403
    response = client.get(
        f"/api/v1/docs/items/{doc_id}",
        headers=headers,
        params={"share_token": "invalid-link"},
    )
    assert response.status_code == 403
    response = client.patch(
        f"/api/v1/docs/items/{doc_id}",
        headers=headers,
        params={"share_token": "invalid-link"},
        json={"title": "Unauthorized update"},
    )
    assert response.status_code == 403


def test_stored_space_owner_requires_current_pms_admission(client: TestClient) -> None:
    _, member = _context(client)
    with get_session_factory()() as db:
        user = load_user_graph(db, member["user"]["id"])
        team = Team(id=new_id(), key=new_id(), name="Private space")
        db.add(team)
        db.flush()
        db.add(TeamMember(id=new_id(), team_id=team.id, user_id=user.id, role="owner"))
        db.commit()
        assert resolve_pms_space_role(db, user, team) == "owner"
        with get_session_factory()() as writer:
            writer.get(AppAccessPolicy, "pms").audience = "selected"
            writer.commit()
        assert resolve_pms_space_role(db, user, team) is None
        space_id = team.id
    response = client.get(
        f"/api/v1/pms/spaces/{space_id}/members", headers=auth_headers(member["token"])
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("resource_type", ["docs_native_doc", "meeting"])
@pytest.mark.parametrize("revocation", ["admission", "inactive", "user", "app"])
def test_source_acl_rechecks_revoked_execution_context(
    client: TestClient,
    resource_type: str,
    revocation: str,
) -> None:
    _, member = _context(client)
    with get_session_factory()() as db:
        user = load_user_graph(db, member["user"]["id"])
        now = datetime.now(UTC).replace(tzinfo=None)
        resource = (
            NativeDoc(id=new_id(), owner_id=user.id, title="Private")
            if resource_type == "docs_native_doc"
            else Meeting(
                id=new_id(),
                organizer_id=user.id,
                title="Private",
                start_at=now,
                end_at=now + timedelta(hours=1),
            )
        )
        db.add(resource)
        db.commit()
        policy = SourceAclPolicy.for_user(db, user=user)
        resource_id = resource.id
        assert policy.can_read_resource(resource_type, resource_id)
        with get_session_factory()() as writer:
            if revocation == "admission":
                app_id = "docs" if resource_type == "docs_native_doc" else "meeting"
                writer.get(AppAccessPolicy, app_id).audience = "selected"
            elif revocation == "inactive":
                writer.execute(update(User).where(User.id == user.id).values(status="inactive"))
            elif revocation == "user":
                writer.execute(update(User).where(User.id == user.id).values(login_blocked=True))
            else:
                app_id = "docs" if resource_type == "docs_native_doc" else "meeting"
                writer.execute(
                    update(CompanyAppControl)
                    .where(
                        CompanyAppControl.app_id == app_id,
                    )
                    .values(enabled=False)
                )
            writer.commit()
        assert policy.can_read_resource(resource_type, resource_id) is False
        assert policy.can_read_rag_resource(resource_type, resource_id) is False
        assert policy.authorize_many_resources([(resource_type, resource_id)]) == set()
        assert policy.authorize_many_rag_resources([(resource_type, resource_id)]) == set()
        assert policy.has_accessible_source(resource_type) is False


@pytest.mark.parametrize("resource_type", ["docs_native_doc", "meeting", "pms_task"])
def test_source_dispatch_denies_missing_resources(
    client: TestClient,
    resource_type: str,
) -> None:
    _, member = _context(client)
    with get_session_factory()() as db:
        user = db.get(User, member["user"]["id"])
        policy = SourceAclPolicy.for_user(db, user=user)
        assert policy.can_read_resource(resource_type, "missing") is False
        assert policy.has_accessible_source(resource_type) is False


def test_pms_media_obeys_source_acl_and_write_role(client: TestClient) -> None:
    admin, member = _context(client)
    with get_session_factory()() as db:
        admin_user = load_user_graph(db, admin["user"]["id"])
        member_user = load_user_graph(db, member["user"]["id"])
        team = Team(id=new_id(), key=new_id(), name="Private team")
        db.add(team)
        db.flush()
        task_list = TaskList(
            id=new_id(),
            key=new_id()[:12],
            name="Private list",
            team_id=team.id,
            created_by_id=member_user.id,
        )
        task = Task(
            id=new_id(),
            task_list=task_list,
            task_number=1,
            title="Private task",
            reporter_id=member_user.id,
        )
        db.add_all([team, task_list, task])
        db.flush()
        membership = TeamMember(id=new_id(), team_id=team.id, user_id=member_user.id, role="viewer")
        db.add(membership)
        db.commit()
        media = MediaFile(resource_type="task", resource_id=task.id)
        policy = SourceAclPolicy.for_user(db, user=admin_user)
        assert policy.can_read_resource("pms_task", task.id) is False
        assert can_resolve_media(db, admin_user, media) is False
        assert can_resolve_media(db, member_user, media) is True
        with pytest.raises(HTTPException) as denied:
            ensure_media_link_resource_access(db, member_user, "task", task.id)
        assert denied.value.status_code == 403
        membership.role = "member"
        db.commit()
        ensure_media_link_resource_access(db, member_user, "task", task.id)
        db.delete(membership)
        grant = TaskUserAccess(
            id=new_id(),
            task_id=task.id,
            user_id=member_user.id,
            granted_by_user_id=admin_user.id,
            access_level="read",
        )
        db.add(grant)
        db.commit()
        assert can_resolve_media(db, member_user, media) is True
        with pytest.raises(HTTPException):
            ensure_media_link_resource_access(db, member_user, "task", task.id)
        grant.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        assert can_resolve_media(db, member_user, media) is False


@pytest.mark.parametrize("legacy_role", ["audit_viewer", "workspace_admin"])
def test_legacy_system_role_does_not_authorize_admin_api(client, legacy_role):
    _, member = _context(client)
    with get_session_factory()() as db:
        db.add(UserSystemRole(id=new_id(), user_id=member["user"]["id"], role=legacy_role))
        db.commit()
    response = client.get("/api/v1/admin/users", headers=auth_headers(member["token"]))
    assert response.status_code == 403


@pytest.mark.parametrize("status", ["inactive", "suspended"])
def test_non_active_user_denied_by_api_and_background_gates(client, status):
    _, member = _context(client)
    with get_session_factory()() as db:
        user = load_user_graph(db, member["user"]["id"])
        user.status = status
        db.commit()
        assert not can_use_app(db, app_id="docs", user_id=user.id)
    response = client.get("/api/v1/docs/hub", headers=auth_headers(member["token"]))
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(
    "app_id,require_access",
    [("docs", ensure_docs_app_access), ("whiteboard", ensure_whiteboard_app_access)],
)
def test_app_services_require_current_app_admission(client, app_id, require_access):
    _, member = _context(client)
    with get_session_factory()() as db:
        user = load_user_graph(db, member["user"]["id"])
        require_access(db, user)
        db.get(AppAccessPolicy, app_id).audience = "selected"
        db.commit()
        with pytest.raises(HTTPException) as denied:
            require_access(db, user)
        assert denied.value.status_code == 403


@pytest.mark.parametrize("app_id", ["docs", "whiteboard"])
def test_shared_link_limits_owner_rights_and_denies_revoked_admission(client, app_id):
    _, member = _context(client)
    model, share_model = (
        (NativeDoc, NativeDocLinkShare) if app_id == "docs" else (Whiteboard, WhiteboardLinkShare)
    )
    token = new_id()
    with get_session_factory()() as db:
        item = model(
            id=new_id(),
            owner_id=member["user"]["id"],
            title="Shared source",
        )
        item.link_shares.append(
            share_model(
                id=new_id(),
                token=token,
                active=True,
                access_level="read",
                created_by_id=member["user"]["id"],
            )
        )
        db.add(item)
        db.commit()
        item_id = item.id
    path = (
        f"/api/v1/docs/items/{item_id}"
        if app_id == "docs"
        else f"/api/v1/whiteboard/items/{item_id}"
    )
    params = {"share_token": token}
    headers = auth_headers(member["token"])
    response = client.get(path, headers=headers, params=params)
    assert response.status_code == 200
    response = client.patch(path, headers=headers, params=params, json={"title": "Denied"})
    assert response.status_code == 403
    with get_session_factory()() as db:
        db.get(AppAccessPolicy, app_id).audience = "selected"
        db.commit()
    response = client.get(path, headers=headers, params=params)
    assert response.status_code == 403


@pytest.mark.parametrize("revocation", ["membership", "app"])
def test_global_media_link_rechecks_docs_execution_context(client, revocation):
    _, member = _context(client)
    with get_session_factory()() as db:
        doc = NativeDoc(
            id=new_id(),
            owner_id=member["user"]["id"],
            title="Media source",
        )
        page = NativeDocPage(id=new_id(), doc=doc, title="Page", created_by_id=member["user"]["id"])
        db.add_all([doc, page])
        db.commit()
        page_id = page.id
    payload = {"media_ids": [new_id()], "resource_type": "docs_native_page", "resource_id": page_id}
    headers = auth_headers(member["token"])
    response = client.post("/api/v1/media/link", headers=headers, json=payload)
    assert response.status_code == 204
    with get_session_factory()() as db:
        if revocation == "membership":
            db.get(AppAccessPolicy, "docs").audience = "selected"
        else:
            db.execute(
                update(CompanyAppControl)
                .where(
                    CompanyAppControl.app_id == "docs",
                )
                .values(enabled=False)
            )
        db.commit()
    response = client.post("/api/v1/media/link", headers=headers, json=payload)
    assert response.status_code == 403


def test_system_role_revocation_is_effective_for_existing_session(client):
    administrator = dev_login(client, "administrator")
    _, member = _context(client)
    member_id = member["user"]["id"]
    with get_session_factory()() as db:
        db.add(UserSystemRole(id=new_id(), user_id=member_id, role="platform_admin"))
        db.commit()
    headers = auth_headers(member["token"])
    response = client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 200, response.text
    response = client.patch(
        f"/api/v1/admin/users/{member_id}",
        headers=auth_headers(administrator["token"]),
        json={"system_roles": []},
    )
    assert response.status_code == 200, response.text
    response = client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 403, response.text
