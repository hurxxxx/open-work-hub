import pytest
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import AuditLog, User
from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.whiteboard.models import Whiteboard
from open_work_hub_api.domains.source_access.policy import SourceAclPolicy
from test_company_groups import _setup


def _enable(client, headers, app):
    response = client.put(
        f"/api/v1/admin/apps/{app}/access-policy",
        headers=headers,
        json={"enabled": True, "audience": "all"},
    )
    assert response.status_code == 200, response.text


def _user(client, admin, name):
    response = client.post(
        "/api/v1/admin/users",
        headers=admin,
        json={
            "login_id": name,
            "email": f"{name}@example.test",
            "full_name": name,
            "temporary_password": "company-test-password",
        },
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    response = client.patch(
        f"/api/v1/admin/users/{user_id}", headers=admin, json={"must_change_password": False}
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/v1/auth/login", json={"login_id": name, "password": "company-test-password"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}, user_id


def _group(client, admin, user_ids):
    response = client.post("/api/v1/admin/groups", headers=admin, json={"name": "Working Group"})
    assert response.status_code == 201, response.text
    group_id = response.json()["id"]
    response = client.put(
        f"/api/v1/admin/groups/{group_id}/members", headers=admin, json={"user_ids": user_ids}
    )
    assert response.status_code == 200, response.text
    return group_id


@pytest.mark.parametrize("app, model", [("docs", NativeDoc), ("whiteboard", Whiteboard)])
def test_personal_group_sharing_does_not_publish_or_grant_resharing(client, app, model):
    admin, admin_id = _setup(client)
    _enable(client, admin, app)
    owner, _ = _user(client, admin, "contentowner")
    member, member_id = _user(client, admin, "contentmember")
    group_id = _group(client, admin, [member_id])
    response = client.post(f"/api/v1/{app}/items", headers=owner, json={"title": "Private draft"})
    assert response.status_code == 201, response.text
    item_id = response.json()["id"]
    item_url = f"/api/v1/{app}/items/{item_id}"
    assert client.get(item_url, headers=admin).status_code == 404
    assert client.get(item_url, headers=member).status_code == 404
    share_url = f"{item_url}/sharing/groups/{group_id}"
    response = client.put(share_url, headers=owner, json={"access_level": "edit"})
    assert response.status_code == 200, response.text
    response = client.get(item_url, headers=member)
    assert response.status_code == 200, response.text
    assert response.json()["can_edit"] and not response.json()["can_share"]
    assert client.put(share_url, headers=member, json={"access_level": "read"}).status_code == 403
    assert client.get(item_url, headers=admin).status_code == 404
    with get_session_factory()() as db:
        record = db.get(model, item_id.split("__")[-1])
        assert record.ownership_kind == "personal"
        if app == "docs":
            assert not SourceAclPolicy.for_user(db, user=db.get(User, admin_id)).can_read_resource(
                "docs_native_doc", record.id
            )
            assert SourceAclPolicy.for_user(db, user=db.get(User, member_id)).can_read_resource(
                "docs_native_doc", record.id
            )
    response = client.put(
        f"/api/v1/admin/groups/{group_id}/members", headers=admin, json={"user_ids": []}
    )
    assert response.status_code == 200, response.text
    assert client.get(item_url, headers=member).status_code == 404


@pytest.mark.parametrize("app, model", [("docs", NativeDoc), ("whiteboard", Whiteboard)])
def test_company_publication_requires_source_authority_and_acknowledgement(client, app, model):
    admin, _ = _setup(client)
    for enabled in (app, "pms"):
        _enable(client, admin, enabled)
    owner, owner_id = _user(client, admin, "publicationowner")
    response = client.post("/api/v1/pms/spaces", headers=owner, json={"name": "Project space"})
    assert response.status_code == 201, response.text
    space_id = response.json()["id"]
    response = client.post(f"/api/v1/{app}/items", headers=owner, json={"title": "Publish draft"})
    assert response.status_code == 201, response.text
    item_id = response.json()["id"]
    item_url = f"/api/v1/{app}/items/{item_id}"
    target = {"app": "pms", "type": "space", "id": space_id}
    response = client.put(f"{item_url}/target", headers=owner, json=target)
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "content.company_publication_required"
    response = client.put(
        f"{item_url}/target",
        headers=owner,
        json={**target, "company_admin_read_acknowledged": True},
    )
    assert response.status_code == 200, response.text
    response = client.get(item_url, headers=admin)
    assert response.status_code == 200, response.text
    assert (
        response.json()["can_view"]
        and not response.json()["can_edit"]
        and not response.json()["can_manage"]
    )
    assert (
        client.patch(item_url, headers=admin, json={"title": "Admin mutation"}).status_code == 403
    )
    response = client.delete(f"{item_url}/target", headers=owner)
    assert response.status_code == 200, response.text
    assert client.get(item_url, headers=admin).status_code == 200
    with get_session_factory()() as db:
        record = db.get(model, item_id.split("__")[-1])
        assert record.ownership_kind == "company"
        audits = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.action == "content.publish_to_company", AuditLog.entity_id == record.id
                )
            )
        )
        assert len(audits) == 1 and audits[0].actor_user_id == owner_id


def test_pms_groups_grant_only_app_space_roles_and_revoke_live(client):
    admin, _ = _setup(client)
    _enable(client, admin, "pms")
    owner, _ = _user(client, admin, "spaceowner")
    member, member_id = _user(client, admin, "spacemember")
    group_id = _group(client, admin, [member_id])
    response = client.post("/api/v1/pms/spaces", headers=owner, json={"name": "Group project"})
    assert response.status_code == 201, response.text
    space_id = response.json()["id"]
    url = f"/api/v1/pms/spaces/{space_id}/groups/{group_id}"
    assert client.put(url, headers=owner, json={"role": "owner"}).status_code == 422
    response = client.put(url, headers=owner, json={"role": "member"})
    assert response.status_code == 200, response.text
    response = client.get("/api/v1/pms/spaces", headers=member)
    assert response.status_code == 200, response.text
    space = next(s for s in response.json() if s["id"] == space_id)
    assert space["current_user_role"] == "member"
    assert client.put(url, headers=member, json={"role": "admin"}).status_code == 403
    assert (
        client.patch(
            f"/api/v1/pms/spaces/{space_id}", headers=admin, json={"name": "Unauthorized edit"}
        ).status_code
        == 403
    )
    response = client.put(
        f"/api/v1/admin/groups/{group_id}/members", headers=admin, json={"user_ids": []}
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/api/v1/pms/spaces/{space_id}/groups", headers=member).status_code in {
        403,
        404,
    }


def test_last_active_admin_cannot_be_removed_and_old_workspace_routes_are_absent(client):
    admin, admin_id = _setup(client)
    for update in ({"system_roles": []}, {"status": "suspended"}, {"login_blocked": True}):
        response = client.patch(f"/api/v1/admin/users/{admin_id}", headers=admin, json=update)
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "admin.last_active_admin_required"
    assert client.get("/api/v1/admin/workspaces", headers=admin).status_code == 404
    response = client.get("/api/v1/apps/bootstrap", headers=admin)
    assert response.status_code == 200, response.text
    assert "workspace" not in str(response.json()).lower()


@pytest.mark.parametrize("app, model", [("docs", NativeDoc), ("whiteboard", Whiteboard)])
def test_company_read_audience_can_be_revoked_without_reverting_ownership(client, app, model):
    admin, _ = _setup(client)
    _enable(client, admin, app)
    owner, _ = _user(client, admin, "audienceowner")
    reader, reader_id = _user(client, admin, "audiencereader")
    response = client.post(f"/api/v1/{app}/items", headers=owner, json={"title": "Company notice"})
    assert response.status_code == 201, response.text
    item_id = response.json()["id"]
    url = f"/api/v1/{app}/items/{item_id}"
    response = client.put(f"{url}/sharing/company", headers=owner, json={"enabled": True})
    assert response.status_code == 409, response.text
    response = client.put(
        f"{url}/sharing/company",
        headers=owner,
        json={"enabled": True, "company_admin_read_acknowledged": True},
    )
    assert response.status_code == 204, response.text
    response = client.get(url, headers=reader)
    assert response.status_code == 200, response.text
    assert response.json()["ownership_kind"] == "company"
    assert response.json()["company_visible"] is True
    assert response.json()["can_edit"] is False
    if app == "docs":
        with get_session_factory()() as db:
            assert SourceAclPolicy.for_user(db, user=db.get(User, reader_id)).can_read_resource(
                "docs_native_doc", item_id
            )
    response = client.put(f"{url}/sharing/company", headers=admin, json={"enabled": False})
    assert response.status_code == 403, response.text
    response = client.put(f"{url}/sharing/company", headers=owner, json={"enabled": False})
    assert response.status_code == 204, response.text
    response = client.get(url, headers=reader)
    assert response.status_code == 404, response.text
    response = client.get(url, headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()["ownership_kind"] == "company"
    assert response.json()["company_visible"] is False


@pytest.mark.parametrize("app", ["docs", "whiteboard"])
def test_shared_content_does_not_disclose_inaccessible_target_title(client, app):
    admin, _ = _setup(client)
    for enabled in (app, "pms"):
        _enable(client, admin, enabled)
    owner, _ = _user(client, admin, "targetowner")
    reader, reader_id = _user(client, admin, "targetreader")
    response = client.post(
        "/api/v1/pms/spaces", headers=owner, json={"name": "Confidential project title"}
    )
    assert response.status_code == 201, response.text
    space_id = response.json()["id"]
    response = client.post(
        f"/api/v1/{app}/items",
        headers=owner,
        json={
            "title": "Shared instructions",
            "primary_target": {
                "app": "pms",
                "type": "space",
                "id": space_id,
                "company_admin_read_acknowledged": True,
            },
        },
    )
    assert response.status_code == 201, response.text
    url = f"/api/v1/{app}/items/{response.json()['id']}"
    group_id = _group(client, admin, [reader_id])
    response = client.put(
        f"{url}/sharing/groups/{group_id}", headers=owner, json={"access_level": "read"}
    )
    assert response.status_code == 200, response.text
    response = client.get(url, headers=reader)
    assert response.status_code == 200, response.text
    assert "Confidential project title" not in response.text
    response = client.get(url, headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["location_label"] == "Confidential project title"


def test_meeting_admin_business_read_is_separate_from_participant_writes(client):
    admin, admin_id = _setup(client)
    for app in ("meeting", "docs"):
        _enable(client, admin, app)
    owner, owner_id = _user(client, admin, "meetingowner")
    outsider, outsider_id = _user(client, admin, "meetingoutsider")
    response = client.post(
        "/api/v1/meeting/meetings",
        headers=owner,
        json={
            "title": "Company review",
            "start_at": "2026-09-08T10:00:00",
            "end_at": "2026-09-08T11:00:00",
        },
    )
    assert response.status_code == 201, response.text
    meeting_id = response.json()["id"]
    url = f"/api/v1/meeting/meetings/{meeting_id}"
    response = client.get(url, headers=admin)
    assert response.status_code == 200, response.text
    response = client.get(url, headers=outsider)
    assert response.status_code == 403, response.text
    response = client.get("/api/v1/meeting/meetings?scope=all", headers=admin)
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [meeting_id]
    response = client.get("/api/v1/meeting/meetings?scope=mine", headers=admin)
    assert response.status_code == 200 and response.json()["items"] == [], response.text
    response = client.patch(url, headers=admin, json={"title": "Unauthorized mutation"})
    assert response.status_code == 403, response.text
    response = client.post(
        f"{url}/attendees", headers=admin, json={"attendees": [{"user_id": outsider_id}]}
    )
    assert response.status_code == 403, response.text
    response = client.post(f"{url}/notes/ensure", headers=admin)
    assert response.status_code == 403, response.text
    response = client.post(f"{url}/notes/ensure", headers=owner)
    assert response.status_code == 200, response.text
    doc_id = response.json()["notes_doc_id"]
    with get_session_factory()() as db:
        doc = db.get(NativeDoc, doc_id)
        assert doc.ownership_kind == "company" and not doc.company_visible
        assert SourceAclPolicy.for_user(db, user=db.get(User, admin_id)).can_read_meeting(
            meeting_id
        )
        assert not SourceAclPolicy.for_user(db, user=db.get(User, outsider_id)).can_read_meeting(
            meeting_id
        )
        assert db.scalar(
            select(AuditLog.id).where(
                AuditLog.action == "content.create_company", AuditLog.entity_id == doc_id
            )
        )
    response = client.get(f"/api/v1/docs/items/native_doc__{doc_id}", headers=admin)
    assert response.status_code == 200, response.text
    assert response.json()["can_view"] and not response.json()["can_edit"]
    response = client.get(f"/api/v1/docs/items/native_doc__{doc_id}", headers=outsider)
    assert response.status_code == 404, response.text
    response = client.put(
        "/api/v1/admin/apps/meeting/access-policy",
        headers=admin,
        json={"enabled": False, "audience": "all"},
    )
    assert response.status_code == 200, response.text
    response = client.get(url, headers=admin)
    assert response.status_code == 403, response.text
    with get_session_factory()() as db:
        assert not SourceAclPolicy.for_user(db, user=db.get(User, admin_id)).can_read_meeting(
            meeting_id
        )


def test_temporary_password_blocks_app_use_and_reset_revokes_existing_session(client, monkeypatch):
    admin, _ = _setup(client)
    _enable(client, admin, "docs")
    response = client.post(
        "/api/v1/admin/users",
        headers=admin,
        json={
            "login_id": "temporaryuser",
            "email": "temporary@example.test",
            "full_name": "Temporary User",
            "temporary_password": "company-test-password",
        },
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    response = client.post(
        "/api/v1/auth/login",
        json={"login_id": "temporaryuser", "password": "company-test-password"},
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['token']}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200 and response.json()["must_change_password"], response.text
    response = client.get("/api/v1/apps/bootstrap", headers=headers)
    assert (
        response.status_code == 403 and response.json()["code"] == "auth.password_change_required"
    ), response.text
    from open_work_hub_api.domains.auth.app_access import can_use_app

    with get_session_factory()() as db:
        assert not can_use_app(db, user_id=user_id, app_id="docs")
    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={
            "current_password": "company-test-password",
            "new_password": "changed-company-test-password",
            "new_password_confirm": "changed-company-test-password",
        },
    )
    assert response.status_code == 204, response.text
    response = client.get("/api/v1/apps/bootstrap", headers=headers)
    assert response.status_code == 200, response.text
    recipients: set[str] = set()
    monkeypatch.setattr(
        "open_work_hub_api.domains.admin.router.publish_principal_access_changed",
        lambda _hub, user_ids: recipients.update(user_ids),
    )
    response = client.post(
        f"/api/v1/admin/users/{user_id}/reset-password",
        headers=admin,
        json={"temporary_password": "reset-company-test-password"},
    )
    assert recipients == {user_id}
    assert response.status_code == 200
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401, response.text
