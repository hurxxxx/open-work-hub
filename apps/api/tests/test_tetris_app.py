from fastapi.testclient import TestClient

from dev_accounts import create_company_user_session, dev_login
from open_work_hub_api.core.app_routes import app_route_pattern
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
from open_work_hub_api.domains.auth.models import CompanyAppControl


def test_tetris_catalog_contract():
    app = get_app_catalog_item("tetris")
    assert app is not None
    assert app.execution_context_kind == "personal"
    assert app.resource_scope == "personal"
    assert app.launcher_personal_tools
    assert not app.launcher_pinned_by_default
    assert app.nav_items == ()
    assert app_route_pattern("tetris.root") == "/apps/tetris"


def test_tetris_admission_and_revocation(client: TestClient):
    admin = dev_login(client, "administrator")
    member = create_company_user_session(
        client, login_id="tetris-member", email="tetris@example.test", full_name="Tetris Member"
    )
    admin_headers = {"Authorization": f"Bearer {admin['token']}"}
    member_headers = {"Authorization": f"Bearer {member['token']}"}

    def admitted(headers):
        response = client.get("/api/v1/apps/bootstrap", headers=headers)
        assert response.status_code == 200
        return "tetris" in {app["app_id"] for app in response.json()["apps"]}

    # Test fixtures may seed the full registry; remove only this test's app configuration.
    with get_session_factory()() as db:
        policy = db.get(AppAccessPolicy, "tetris")
        if policy is not None:
            db.delete(policy)
            db.flush()
        control = db.get(CompanyAppControl, "tetris")
        if control is not None:
            db.delete(control)
        db.commit()
    assert not admitted(member_headers)
    assert not admitted(admin_headers)

    def policy(**overrides):
        response = client.put(
            "/api/v1/admin/apps/tetris/access-policy",
            headers=admin_headers,
            json={
                "enabled": True,
                "audience": "selected",
                "user_ids": [],
                "group_ids": [],
                **overrides,
            },
        )
        assert response.status_code == 200, response.text

    policy()
    assert not admitted(member_headers)
    assert admitted(admin_headers)
    policy(user_ids=[member["user"]["id"]])
    assert admitted(member_headers)
    policy()
    assert not admitted(member_headers)
    group_response = client.post(
        "/api/v1/admin/groups", headers=admin_headers, json={"name": "Tetris Players"}
    )
    assert group_response.status_code == 201, group_response.text
    group_id = group_response.json()["id"]
    membership_path = f"/api/v1/admin/groups/{group_id}/members/{member['user']['id']}"
    assigned = client.put(membership_path, headers=admin_headers, json={"assigned": True})
    assert assigned.status_code == 200, assigned.text
    policy(group_ids=[group_id])
    assert admitted(member_headers)
    removed = client.put(membership_path, headers=admin_headers, json={"assigned": False})
    assert removed.status_code == 200, removed.text
    assert not admitted(member_headers)
    policy(audience="all")
    assert admitted(member_headers)
    policy(enabled=False, audience="all")
    assert not admitted(member_headers)
    assert not admitted(admin_headers)
