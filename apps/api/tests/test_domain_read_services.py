from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.core.principal import user_principal
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.docs import service as docs_service
from aidoo_api.domains.pms import service as pms_service


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_pms_search_issues_service_returns_workspace_results(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRV", "name": "Service Search List", "description": "search source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        json={"title": "Service search issue", "description": "find me"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        result = pms_service.search_issues(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.search_issues",
            ),
            user=user,
            q="Service search issue",
            limit=10,
        )

    assert result["total"] >= 1
    assert any(item["id"] == issue["id"] for item in result["items"])


def test_docs_read_page_service_returns_page_content(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    doc_response = client.post(
        "/api/v1/docs/items",
        headers=_auth_headers(token),
        json={"title": "Service Doc"},
    )
    assert doc_response.status_code == 201, doc_response.text
    doc = doc_response.json()

    page_response = client.post(
        f"/api/v1/docs/items/{doc['id']}/pages",
        headers=_auth_headers(token),
        json={
            "title": "Service Page",
            "content_blocks": [{"type": "paragraph", "content": "hello from service"}],
        },
    )
    assert page_response.status_code == 201, page_response.text
    page = page_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        result = docs_service.read_page(
            db,
            user=user,
            page_id=page["id"],
        )

    assert result["id"] == page["id"]
    assert result["title"] == "Service Page"
    assert result["content_blocks"] == [{"type": "paragraph", "content": "hello from service"}]
