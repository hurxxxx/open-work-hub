from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from aidoo_api.core.db import get_session_factory
from aidoo_api.core.principal import CallerPrincipal, user_principal
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
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRV", "name": "Service Search List", "description": "search source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/issues",
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
        "/api/v1/workspaces/delivery-hub/docs/items",
        headers=_auth_headers(token),
        json={"title": "Service Doc"},
    )
    assert doc_response.status_code == 201, doc_response.text
    doc = doc_response.json()

    page_response = client.post(
        f"/api/v1/workspaces/delivery-hub/docs/items/{doc['id']}/pages",
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


def test_pms_create_issue_service_creates_issue(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRVCREATE", "name": "Service Create List", "description": "write source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        issue = pms_service.create_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.create_issue",
            ),
            user=user,
            list_id=task_list["id"],
            title="Service-created issue",
            description="created through service",
        )

    assert issue["title"] == "Service-created issue"
    assert issue["description"] == "created through service"
    assert issue["list_id"] == task_list["id"]


def test_pms_update_issue_service_updates_issue(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRVUPD", "name": "Service Update List", "description": "update source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        json={"title": "Issue before update", "description": "old"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        updated = pms_service.update_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.update_issue",
            ),
            user=user,
            issue_id=issue["id"],
            provided_fields={"title", "status"},
            title="Issue after update",
            status="in_progress",
        )

    assert updated["id"] == issue["id"]
    assert updated["title"] == "Issue after update"
    assert updated["status"] == "in_progress"


def test_pms_add_issue_comment_service_creates_comment(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRVCMT", "name": "Service Comment List", "description": "comment source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        json={"title": "Comment target"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        comment = pms_service.add_issue_comment(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.add_issue_comment",
            ),
            user=user,
            issue_id=issue["id"],
            body="hello from service comment",
        )

    assert comment["issue_id"] == issue["id"]
    assert comment["body"] == "hello from service comment"
    assert comment["author_id"] == session["user"]["id"]


def test_pms_create_issue_service_supports_multi_assignee_input(client: TestClient) -> None:
    admin_session = _dev_login(client, "delivery-hub-admin")
    member_session = _dev_login(client, "delivery-hub-member")
    token = admin_session["token"]

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRVMULTI", "name": "Service Multi List", "description": "multi assignee source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, admin_session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        issue = pms_service.create_issue(
            db,
            workspace=workspace,
            principal=user_principal(
                workspace_id=workspace.id,
                user_id=user.id,
                source="test.pms.create_issue.multi_assignee",
            ),
            user=user,
            list_id=task_list["id"],
            title="Service multi-assignee issue",
            assignee_ids=[member_session["user"]["id"]],
        )

    assert issue["assignee_id"] == member_session["user"]["id"]
    assert issue["assignee_ids"] == [member_session["user"]["id"]]


def test_pms_update_issue_service_supports_multi_assignee_input(client: TestClient) -> None:
    admin_session = _dev_login(client, "delivery-hub-admin")
    member_session = _dev_login(client, "delivery-hub-member")
    token = admin_session["token"]

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRVMULTUPD", "name": "Service Multi Update List", "description": "multi update source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    issue_response = client.post(
        f"/api/v1/workspaces/delivery-hub/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        json={"title": "Issue before assignee update"},
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
                source="test.pms.update_issue.multi_assignee",
            ),
            user=user,
            issue_id=issue["id"],
            provided_fields={"assignee_ids"},
            assignee_ids=[member_session["user"]["id"]],
        )

    assert updated["assignee_id"] == member_session["user"]["id"]
    assert updated["assignee_ids"] == [member_session["user"]["id"]]


def test_pms_create_issue_service_rejects_mismatched_user_principal(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRVMISMATCH", "name": "Service Mismatch List", "description": "mismatch source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        with pytest.raises(HTTPException) as exc_info:
            pms_service.create_issue(
                db,
                workspace=workspace,
                principal=user_principal(
                    workspace_id=workspace.id,
                    user_id="00000000-0000-0000-0000-000000000000",
                    source="test.pms.create_issue.mismatch",
                ),
                user=user,
                list_id=task_list["id"],
                title="Should fail",
            )
        assert exc_info.value.detail.code == "pms.principal_user_mismatch"


def test_pms_create_issue_service_rejects_non_user_principal(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    task_list_response = client.post(
        "/api/v1/workspaces/delivery-hub/pms/lists",
        headers=_auth_headers(token),
        json={"key": "SRVNONUSER", "name": "Service Non User List", "description": "non-user source"},
    )
    assert task_list_response.status_code == 201, task_list_response.text
    task_list = task_list_response.json()

    with get_session_factory()() as db:
        user = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert user is not None
        assert workspace is not None

        with pytest.raises(HTTPException) as exc_info:
            pms_service.create_issue(
                db,
                workspace=workspace,
                principal=CallerPrincipal(
                    kind="service_account",
                    workspace_id=workspace.id,
                    service_account_id="service-account-1",
                    source="test.pms.create_issue.service_account",
                ),
                user=user,
                list_id=task_list["id"],
                title="Should also fail",
            )
        assert exc_info.value.detail.code == "pms.write_user_principal_required"
