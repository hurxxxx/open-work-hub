import pytest
from fastapi.testclient import TestClient

from dev_accounts import create_company_user_session, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant
from open_work_hub_api.domains.auth.models import CompanyAppControl


def _headers(session):
    return {"Authorization": f"Bearer {session['token']}"}


def test_launch_catalog_has_single_app_routes_and_no_container_preferences(client: TestClient):
    session = dev_login(client, "administrator")
    response = client.get("/api/v1/apps/bootstrap", headers=_headers(session))
    assert response.status_code == 200, response.text
    payload = response.json()
    apps = {item["app_id"]: item for item in payload["apps"]}
    assert apps["mail"]["route_base"] == "/apps/mail"
    assert apps["docs"]["route_base"] == "/apps/docs"
    assert payload["principal"]["user_id"] == session["user"]["id"]
    for item in apps.values():
        assert not {
            "availability_scope",
            "eligible_workspace_count",
            "preferred_workspace",
            "single_eligible_workspace",
        }.intersection(item)
    assert "workspaces" not in session["user"]


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v1/apps/docs/eligible-workspaces", "get"),
        ("/api/v1/apps/docs/workspace-preference", "put"),
        ("/api/v1/workspaces/general/apps/bootstrap", "get"),
    ],
)
def test_removed_container_routes_are_not_exposed(client: TestClient, path, method):
    session = dev_login(client, "administrator")
    response = getattr(client, method)(path, headers=_headers(session))
    assert response.status_code == 404, response.text


def test_current_app_grants_control_catalog_and_direct_routes(client: TestClient):
    member = create_company_user_session(
        client, login_id="launch-member", email="launch@example.test", full_name="Launch Member"
    )
    user_id = member["user"]["id"]
    with get_session_factory()() as db:
        db.get(AppAccessPolicy, "docs").audience = "selected"
        db.add(AppUserGrant(app_id="docs", user_id=user_id))
        db.commit()
    admitted = client.get("/api/v1/apps/bootstrap", headers=_headers(member))
    assert admitted.status_code == 200, admitted.text
    assert "docs" in {a["app_id"] for a in admitted.json()["apps"]}
    with get_session_factory()() as db:
        db.delete(db.get(AppUserGrant, ("docs", user_id)))
        db.commit()
    revoked = client.get("/api/v1/apps/bootstrap", headers=_headers(member))
    assert revoked.status_code == 200, revoked.text
    assert "docs" not in {a["app_id"] for a in revoked.json()["apps"]}
    direct = client.get("/api/v1/docs/hub", headers=_headers(member))
    assert direct.status_code == 403, direct.text


def test_company_master_removes_app_even_for_platform_admin(client: TestClient):
    session = dev_login(client, "administrator")
    with get_session_factory()() as db:
        db.get(CompanyAppControl, "docs").enabled = False
        db.commit()
    response = client.get("/api/v1/apps/bootstrap", headers=_headers(session))
    assert response.status_code == 200, response.text
    assert "docs" not in {item["app_id"] for item in response.json()["apps"]}
    direct = client.get("/api/v1/docs/hub", headers=_headers(session))
    assert direct.status_code == 403, direct.text
