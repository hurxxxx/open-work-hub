from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from dev_accounts import dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import (
    CompanyAppControl,
    UserAppWorkspacePreference,
    Workspace,
    WorkspaceAppOverride,
)


def _admin_session(client: TestClient) -> dict:
    return dev_login(client, "administrator")


def _headers(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['token']}"}


def test_launch_catalog_combines_platform_and_eligible_workspace_apps(
    client: TestClient,
) -> None:
    session = _admin_session(client)
    response = client.get("/api/v1/apps/bootstrap", headers=_headers(session))

    assert response.status_code == 200, response.text
    apps = {item["app_id"]: item for item in response.json()["apps"]}
    assert apps["mail"]["route_base"] == "/apps/mail"
    assert apps["mail"]["availability_scope"] == "platform"
    assert apps["mail"]["eligible_workspace_count"] == 0
    assert apps["mail"]["preferred_workspace"] is None
    assert apps["docs"]["route_base"] == "/apps/docs"
    assert apps["docs"]["availability_scope"] == "workspace"
    assert apps["docs"]["eligible_workspace_count"] == 2
    assert apps["docs"]["single_eligible_workspace"] is None
    assert "docs" in response.json()["global_route_app_ids"]
    assert response.json()["personal_tool_app_ids"] == ["agent-terminal", "mail", "planner"]


def test_eligible_workspaces_are_searchable_and_paginated(client: TestClient) -> None:
    session = _admin_session(client)
    response = client.get(
        "/api/v1/apps/docs/eligible-workspaces",
        headers=_headers(session),
        params={"q": "gen", "page": 1, "page_size": 1},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "app_id": "docs",
        "items": [
            {
                "id": response.json()["items"][0]["id"],
                "slug": "general",
                "name": "General",
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 1,
    }

    exact_response = client.get(
        "/api/v1/apps/docs/eligible-workspaces",
        headers=_headers(session),
        params={"slug": "GENERAL", "page_size": 1},
    )
    assert exact_response.status_code == 200, exact_response.text
    assert exact_response.json()["total"] == 1
    assert exact_response.json()["items"][0]["slug"] == "general"


def test_explicit_workspace_preference_is_projected_only_while_eligible(
    client: TestClient,
) -> None:
    session = _admin_session(client)
    general = next(
        workspace for workspace in session["user"]["workspaces"] if workspace["slug"] == "general"
    )
    update_response = client.put(
        "/api/v1/apps/docs/workspace-preference",
        headers=_headers(session),
        json={"workspace_id": general["id"]},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["workspace_id"] == general["id"]

    catalog_response = client.get("/api/v1/apps/bootstrap", headers=_headers(session))
    docs = next(item for item in catalog_response.json()["apps"] if item["app_id"] == "docs")
    assert docs["preferred_workspace"]["slug"] == "general"

    with get_session_factory()() as db:
        db.add(
            WorkspaceAppOverride(
                workspace_id=general["id"],
                app_id="docs",
                enabled=False,
            )
        )
        db.commit()

    stale_response = client.get("/api/v1/apps/bootstrap", headers=_headers(session))
    stale_docs = next(item for item in stale_response.json()["apps"] if item["app_id"] == "docs")
    assert stale_docs["preferred_workspace"] is None
    with get_session_factory()() as db:
        assert db.get(UserAppWorkspacePreference, (session["user"]["id"], "docs")) is not None


def test_workspace_preference_rejects_platform_and_inaccessible_workspaces(
    client: TestClient,
) -> None:
    session = _admin_session(client)
    platform_response = client.put(
        "/api/v1/apps/mail/workspace-preference",
        headers=_headers(session),
        json={"workspace_id": session["user"]["workspaces"][0]["id"]},
    )
    assert platform_response.status_code == 400
    assert platform_response.json()["code"] == "app.workspace_context_unsupported"

    missing_response = client.put(
        "/api/v1/apps/docs/workspace-preference",
        headers=_headers(session),
        json={"workspace_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "workspace.not_found"


def test_company_master_removes_workspace_app_from_launch_catalog(
    client: TestClient,
) -> None:
    session = _admin_session(client)
    with get_session_factory()() as db:
        control = db.get(CompanyAppControl, "docs")
        assert control is not None
        control.enabled = False
        db.add(control)
        db.commit()

    response = client.get("/api/v1/apps/bootstrap", headers=_headers(session))
    assert response.status_code == 200, response.text
    assert "docs" not in {item["app_id"] for item in response.json()["apps"]}
    assert "docs" not in response.json()["global_route_app_ids"]


def test_shared_route_app_remains_available_without_an_eligible_workspace(
    client: TestClient,
) -> None:
    session = _admin_session(client)
    with get_session_factory()() as db:
        for workspace in db.scalars(select(Workspace)).all():
            db.add(
                WorkspaceAppOverride(
                    workspace_id=workspace.id,
                    app_id="docs",
                    enabled=False,
                )
            )
        db.commit()

    response = client.get("/api/v1/apps/bootstrap", headers=_headers(session))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "docs" not in {item["app_id"] for item in payload["apps"]}
    assert "docs" in payload["global_route_app_ids"]


def test_membership_removal_cascades_app_workspace_preference(client: TestClient) -> None:
    session = _admin_session(client)
    general = next(
        workspace for workspace in session["user"]["workspaces"] if workspace["slug"] == "general"
    )
    update_response = client.put(
        "/api/v1/apps/docs/workspace-preference",
        headers=_headers(session),
        json={"workspace_id": general["id"]},
    )
    assert update_response.status_code == 200, update_response.text

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.id == general["id"]))
        assert workspace is not None
        binding = next(
            item for item in workspace.user_bindings if item.user_id == session["user"]["id"]
        )
        db.delete(binding)
        db.commit()
        assert db.get(UserAppWorkspacePreference, (session["user"]["id"], "docs")) is None
