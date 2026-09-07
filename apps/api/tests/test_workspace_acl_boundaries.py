from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.access import (
    get_current_workspace,
    load_user_graph,
    resolve_team_role,
    resolve_workspace_role,
)
from open_work_hub_api.domains.auth.models import (
    CompanyAppControl,
    Team,
    TeamMember,
    User,
    UserSystemRole,
    Workspace,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.workspace_app_gate import (
    is_app_enabled_for_user_context,
    resolve_enabled_app_contexts_for_user,
)
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs.access_context import ensure_docs_workspace_access
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
from open_work_hub_api.domains.whiteboard.access import ensure_whiteboard_workspace_access
from open_work_hub_api.domains.whiteboard.models import Whiteboard, WhiteboardLinkShare


def _context(client):
    admin = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")
    return admin, member


def _workspace(db):
    return db.scalars(select(Workspace).where(Workspace.key == "delivery-hub")).one()


@pytest.mark.parametrize("relationship", ["owner", "user_share"])
def test_global_doc_api_requires_valid_link_after_membership_revocation(
    client: TestClient,
    relationship: str,
) -> None:
    admin, member = _context(client)
    with get_session_factory()() as db:
        workspace = _workspace(db)
        doc = NativeDoc(
            id=new_id(),
            workspace_id=workspace.id,
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
        db.execute(
            delete(WorkspaceUserBinding).where(
                WorkspaceUserBinding.workspace_id == workspace.id,
                WorkspaceUserBinding.user_id == member["user"]["id"],
            )
        )
        db.commit()

    headers = auth_headers(member["token"])
    response = client.get(
        f"/api/v1/workspaces/delivery-hub/docs/items/{doc_id}",
        headers=headers,
    )
    assert response.status_code == 403
    response = client.get(
        f"/api/v1/docs/items/{doc_id}",
        headers=headers,
        params={"share_token": "invalid-link"},
    )
    assert response.status_code == 404
    response = client.patch(
        f"/api/v1/docs/items/{doc_id}",
        headers=headers,
        params={"share_token": "invalid-link"},
        json={"title": "Unauthorized update"},
    )
    assert response.status_code == 404


def test_team_membership_does_not_survive_workspace_revocation(client: TestClient) -> None:
    _, member = _context(client)
    with get_session_factory()() as db:
        workspace = _workspace(db)
        user = load_user_graph(db, member["user"]["id"])
        team = Team(id=new_id(), workspace_id=workspace.id, key=new_id(), name="Private team")
        db.add(team)
        db.flush()
        db.add(TeamMember(id=new_id(), team_id=team.id, user_id=user.id, role="owner"))
        db.commit()
        assert resolve_workspace_role(db, user, workspace.id) == "member"
        assert resolve_team_role(db, user, team) == "owner"
        team_id = team.id
        with get_session_factory()() as writer:
            writer.execute(
                delete(WorkspaceUserBinding).where(
                    WorkspaceUserBinding.workspace_id == workspace.id,
                    WorkspaceUserBinding.user_id == user.id,
                )
            )
            writer.commit()
        # Reuse the already loaded user graph, as non-router callers can do.
        assert resolve_workspace_role(db, user, workspace.id) is None
        assert resolve_team_role(db, user, team) is None
    headers = auth_headers(member["token"])
    response = client.get(f"/api/v1/admin/teams/{team_id}/members", headers=headers)
    assert response.status_code == 403
    response = client.delete(f"/api/v1/admin/teams/{team_id}", headers=headers)
    assert response.status_code == 403


@pytest.mark.parametrize("resource_type", ["docs_native_doc", "meeting"])
@pytest.mark.parametrize("revocation", ["membership", "workspace", "user", "app"])
def test_source_acl_rechecks_revoked_execution_context(
    client: TestClient,
    resource_type: str,
    revocation: str,
) -> None:
    _, member = _context(client)
    with get_session_factory()() as db:
        workspace = _workspace(db)
        user = load_user_graph(db, member["user"]["id"])
        now = datetime.now(UTC).replace(tzinfo=None)
        resource = (
            NativeDoc(id=new_id(), workspace_id=workspace.id, owner_id=user.id, title="Private")
            if resource_type == "docs_native_doc"
            else Meeting(
                id=new_id(),
                workspace_id=workspace.id,
                organizer_id=user.id,
                title="Private",
                start_at=now,
                end_at=now + timedelta(hours=1),
            )
        )
        db.add(resource)
        db.commit()
        policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
        resource_id = resource.id
        assert policy.can_read_resource(resource_type, resource_id)
        with get_session_factory()() as writer:
            if revocation == "membership":
                writer.execute(
                    delete(WorkspaceUserBinding).where(
                        WorkspaceUserBinding.workspace_id == workspace.id,
                        WorkspaceUserBinding.user_id == user.id,
                    )
                )
            elif revocation == "workspace":
                writer.execute(
                    update(Workspace).where(Workspace.id == workspace.id).values(active=False)
                )
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
def test_company_source_dispatch_denies_workspace_only_adapters(
    client: TestClient,
    resource_type: str,
) -> None:
    _, member = _context(client)
    with get_session_factory()() as db:
        user = db.get(User, member["user"]["id"])
        policy = SourceAclPolicy.for_company(db, user=user)
        assert policy.can_read_resource(resource_type, "missing") is False
        assert policy.has_accessible_source(resource_type) is False


def test_pms_media_obeys_source_acl_and_write_role(client: TestClient) -> None:
    admin, member = _context(client)
    with get_session_factory()() as db:
        workspace = _workspace(db)
        admin_user = load_user_graph(db, admin["user"]["id"])
        member_user = load_user_graph(db, member["user"]["id"])
        team = Team(id=new_id(), workspace_id=workspace.id, key=new_id(), name="Private team")
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
        policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=admin_user)
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


@pytest.mark.parametrize("role", ["viewer", "unknown"])
def test_unsupported_workspace_role_denies_api_and_background_gates(client, role):
    _, member = _context(client)
    with get_session_factory()() as db:
        workspace = _workspace(db)
        user = load_user_graph(db, member["user"]["id"])
        db.execute(
            update(WorkspaceUserBinding)
            .where(
                WorkspaceUserBinding.workspace_id == workspace.id,
                WorkspaceUserBinding.user_id == user.id,
            )
            .values(role=role)
        )
        db.commit()
        assert resolve_workspace_role(db, user, workspace.id) is None
        assert not is_app_enabled_for_user_context(
            db,
            app_id="docs",
            user_id=user.id,
            workspace_id=workspace.id,
        )
        assert not resolve_enabled_app_contexts_for_user(
            db,
            user=user,
            contexts=[("docs", workspace.id)],
        )
    response = client.get(
        "/api/v1/workspaces/delivery-hub/docs/hub",
        headers=auth_headers(member["token"]),
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "require_context", [ensure_docs_workspace_access, ensure_whiteboard_workspace_access]
)
def test_app_services_never_choose_an_implicit_workspace(client, require_context):
    _, member = _context(client)
    with get_session_factory()() as db:
        user = load_user_graph(db, member["user"]["id"])
        assert user.workspace_bindings
        with pytest.raises(HTTPException) as denied:
            require_context(db, user)
        assert denied.value.status_code == 403
        assert get_current_workspace(db) is None


@pytest.mark.parametrize("app_id", ["docs", "whiteboard"])
def test_shared_link_limits_owner_rights_and_denies_inactive_workspace(client, app_id):
    _, member = _context(client)
    model, share_model = (
        (NativeDoc, NativeDocLinkShare) if app_id == "docs" else (Whiteboard, WhiteboardLinkShare)
    )
    token = new_id()
    with get_session_factory()() as db:
        workspace = _workspace(db)
        workspace_id = workspace.id
        item = model(
            id=new_id(),
            workspace_id=workspace_id,
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
        db.execute(
            delete(WorkspaceUserBinding).where(
                WorkspaceUserBinding.workspace_id == workspace_id,
                WorkspaceUserBinding.user_id == member["user"]["id"],
            )
        )
        db.commit()
    path = (
        f"/api/v1/docs/items/{item_id}"
        if app_id == "docs"
        else f"/api/v1/whiteboard/shared-links/{token}/item"
    )
    params = {"share_token": token} if app_id == "docs" else {}
    headers = auth_headers(member["token"])
    response = client.get(path, headers=headers, params=params)
    assert response.status_code == 200
    response = client.patch(path, headers=headers, params=params, json={"title": "Denied"})
    assert response.status_code == 403
    with get_session_factory()() as db:
        db.execute(update(Workspace).where(Workspace.id == workspace_id).values(active=False))
        db.commit()
    response = client.get(path, headers=headers, params=params)
    assert response.status_code == 404


@pytest.mark.parametrize("revocation", ["membership", "app"])
def test_global_media_link_rechecks_docs_execution_context(client, revocation):
    _, member = _context(client)
    with get_session_factory()() as db:
        workspace_id = _workspace(db).id
        doc = NativeDoc(
            id=new_id(),
            workspace_id=workspace_id,
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
            db.execute(
                delete(WorkspaceUserBinding).where(
                    WorkspaceUserBinding.workspace_id == workspace_id,
                    WorkspaceUserBinding.user_id == member["user"]["id"],
                )
            )
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


def test_explicit_system_role_revocation_clears_legacy_admin_authority(client):
    administrator = dev_login(client, "administrator")
    _, member = _context(client)
    member_id = member["user"]["id"]
    with get_session_factory()() as db:
        db.execute(update(User).where(User.id == member_id).values(is_admin=True))
        db.commit()
    headers = auth_headers(member["token"])
    response = client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 200
    response = client.patch(
        f"/api/v1/admin/users/{member_id}",
        headers=auth_headers(administrator["token"]),
        json={"system_roles": []},
    )
    assert response.status_code == 200
    assert response.json()["system_roles"] == []
    response = client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 403
