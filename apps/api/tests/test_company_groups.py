from fastapi.testclient import TestClient
import pytest

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.groups.service import current_group_ids


def test_organization_events_only_refresh_changed_member_or_head_projections(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    headers, admin_id = _setup(client)
    recipients: set[str] = set()
    monkeypatch.setattr(
        "open_work_hub_api.domains.organization.admin_router.publish_principal_access_changed",
        lambda _hub, user_ids: recipients.update(user_ids),
    )
    parent = _organization(client, headers, "Parent")
    child = _organization(client, headers, "Child", parent["id"])
    assert not recipients
    user_id = _person(client, headers, child["id"])

    for org_id, payload, expected in (
        (parent["id"], {"name": "Renamed parent"}, set()),
        (parent["id"], {"head_user_id": admin_id}, {admin_id}),
        (parent["id"], {"head_user_id": admin_id}, set()),
        (parent["id"], {"active": False}, {admin_id}),
        (parent["id"], {"active": True}, {admin_id}),
        (child["id"], {"name": "Renamed child"}, {user_id}),
        (child["id"], {"parent_id": None}, set()),
        (child["id"], {"head_user_id": admin_id}, {admin_id}),
        (child["id"], {"head_user_id": user_id}, {admin_id, user_id}),
        (child["id"], {"active": False}, {user_id}),
        (child["id"], {"active": True}, {user_id}),
    ):
        recipients.clear()
        response = client.patch(
            f"/api/v1/admin/organization-units/{org_id}", headers=headers, json=payload
        )
        assert response.status_code == 200, response.text
        assert recipients == expected, payload
        if org_id == child["id"] and "active" in payload:
            with get_session_factory()() as db:
                assert bool(current_group_ids(db, user_id)) == payload["active"]

    recipients.clear()
    response = client.post(
        "/api/v1/admin/organization-units",
        headers=headers,
        json={"name": "New headed organization", "head_user_id": admin_id},
    )
    assert response.status_code == 201, response.text
    assert recipients == {admin_id}


def test_group_access_events_only_reach_users_whose_permissions_change(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    headers, admin_id = _setup(client)
    organization = _organization(client, headers, "Support")
    user_id = _person(client, headers, organization["id"])
    recipients: set[str] = set()
    monkeypatch.setattr(
        "open_work_hub_api.domains.groups.admin_router.publish_app_availability_access_changed",
        lambda _hub, user_ids: recipients.update(user_ids),
    )
    response = client.post("/api/v1/admin/groups", headers=headers, json={"name": "Support TF"})
    assert response.status_code == 201, response.text
    group_id = response.json()["id"]
    assert not recipients

    response = client.put(
        f"/api/v1/admin/groups/{group_id}/members",
        headers=headers,
        json={"user_ids": [user_id]},
    )
    assert response.status_code == 200, response.text
    assert recipients == {user_id}
    assert admin_id not in recipients
    recipients.clear()

    response = client.patch(
        f"/api/v1/admin/groups/{group_id}", headers=headers, json={"name": "Renamed TF"}
    )
    assert response.status_code == 200, response.text
    response = client.put(
        f"/api/v1/admin/groups/{group_id}/members",
        headers=headers,
        json={"user_ids": [user_id]},
    )
    assert response.status_code == 200, response.text
    assert not recipients

    for active in (False, True):
        response = client.patch(
            f"/api/v1/admin/groups/{group_id}", headers=headers, json={"active": active}
        )
        assert response.status_code == 200, response.text
        assert recipients == {user_id}
        recipients.clear()

    response = client.put(
        f"/api/v1/admin/groups/{group_id}/members", headers=headers, json={"user_ids": []}
    )
    assert response.status_code == 200, response.text
    assert recipients == {user_id}


def _setup(client: TestClient):
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Group Admin",
            "email": "groups@example.test",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    return {"Authorization": f"Bearer {data['token']}"}, data["user"]["id"]


def _organization(client, headers, name, parent_id=None):
    response = client.post(
        "/api/v1/admin/organization-units",
        headers=headers,
        json={"name": name, "parent_id": parent_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _person(client, headers, organization_id):
    response = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "member@example.test",
            "full_name": "Group Member",
            "primary_organization_unit_id": organization_id,
        },
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]
    response = client.patch(
        f"/api/v1/admin/users/{user_id}", headers=headers, json={"must_change_password": False}
    )
    assert response.status_code == 200, response.text
    return user_id


def test_hr_membership_is_direct_and_manual_membership_survives_transfer(client: TestClient):
    headers, _ = _setup(client)
    parent = _organization(client, headers, "Engineering")
    child = _organization(client, headers, "Research", parent["id"])
    user_id = _person(client, headers, child["id"])
    response = client.post("/api/v1/admin/groups", headers=headers, json={"name": "Review TF"})
    assert response.status_code == 201, response.text
    manual = response.json()
    response = client.put(
        f"/api/v1/admin/groups/{manual['id']}/members",
        headers=headers,
        json={"user_ids": [user_id]},
    )
    assert response.status_code == 200, response.text
    response = client.get("/api/v1/directory/groups", headers=headers)
    assert response.status_code == 200, response.text
    formal = {
        g["organization_unit_id"]: g["id"]
        for g in response.json()["items"]
        if g["kind"] == "organization"
    }
    with get_session_factory()() as db:
        assert current_group_ids(db, user_id) == {formal[child["id"]], manual["id"]}
    response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=headers,
        json={"primary_organization_unit_id": parent["id"]},
    )
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        assert current_group_ids(db, user_id) == {formal[parent["id"]], manual["id"]}
    response = client.put(
        f"/api/v1/admin/groups/{formal[parent['id']]}/members",
        headers=headers,
        json={"user_ids": []},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "group.organization_managed"


def test_group_app_admission_tracks_current_membership_and_master_disable(client: TestClient):
    headers, admin_id = _setup(client)
    organization = _organization(client, headers, "Operations")
    user_id = _person(client, headers, organization["id"])
    response = client.get("/api/v1/directory/groups", headers=headers)
    assert response.status_code == 200, response.text
    group_id = response.json()["items"][0]["id"]
    with get_session_factory()() as db:
        assert not can_use_app(db, user_id=user_id, app_id="community")
    policy = {"enabled": True, "audience": "selected", "group_ids": [group_id]}
    response = client.put(
        "/api/v1/admin/apps/community/access-policy", headers=headers, json=policy
    )
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        assert can_use_app(db, user_id=user_id, app_id="community")
        assert can_use_app(db, user_id=admin_id, app_id="community")
    response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=headers,
        json={"primary_organization_unit_id": None},
    )
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        assert not can_use_app(db, user_id=user_id, app_id="community")
    response = client.put(
        "/api/v1/admin/apps/community/access-policy",
        headers=headers,
        json={**policy, "enabled": False},
    )
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        assert not can_use_app(db, user_id=admin_id, app_id="community")


def test_department_head_can_manage_multiple_departments_without_joining_groups(client: TestClient):
    headers, user_id = _setup(client)
    first = _organization(client, headers, "First Department")
    second = _organization(client, headers, "Second Department")
    for org in (first, second):
        response = client.patch(
            f"/api/v1/admin/organization-units/{org['id']}",
            headers=headers,
            json={"head_user_id": user_id},
        )
        assert response.status_code == 200, response.text
    response = client.get("/api/v1/directory/people", headers=headers)
    assert response.status_code == 200, response.text
    person = next(p for p in response.json()["items"] if p["id"] == user_id)
    assert person["is_department_head"]
    assert set(person["managed_organization_unit_ids"]) == {first["id"], second["id"]}
    assert "email" not in person and "system_roles" not in person
    with get_session_factory()() as db:
        assert not current_group_ids(db, user_id)
