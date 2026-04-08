from fastapi.testclient import TestClient


def test_issue_list_archived_filters_and_bulk_restore(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    project = _create_project(client, token)

    active_issue = _create_issue(client, token, project["id"], title="Active issue")
    archived_issue = _create_issue(client, token, project["id"], title="Archived issue")

    archive_response = client.patch(
        f"/api/v1/pms/issues/{archived_issue['id']}",
        headers=_auth_headers(token),
        json={"archived": True},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["archived"] is True

    active_only_response = client.get(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(token),
        params={"archived": "false"},
    )
    assert active_only_response.status_code == 200
    assert [item["id"] for item in active_only_response.json()["items"]] == [active_issue["id"]]

    archived_only_response = client.get(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(token),
        params={"archived": "true"},
    )
    assert archived_only_response.status_code == 200
    assert [item["id"] for item in archived_only_response.json()["items"]] == [archived_issue["id"]]

    restore_response = client.patch(
        f"/api/v1/pms/projects/{project['id']}/issues/bulk",
        headers=_auth_headers(token),
        json={"issue_ids": [archived_issue["id"]], "archived": False},
    )
    assert restore_response.status_code == 200
    assert restore_response.json() == {"updated_count": 1, "deleted_count": 0}

    archived_after_restore_response = client.get(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(token),
        params={"archived": "true"},
    )
    assert archived_after_restore_response.status_code == 200
    assert archived_after_restore_response.json()["items"] == []

    active_after_restore_response = client.get(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(token),
        params={"archived": "false"},
    )
    assert active_after_restore_response.status_code == 200
    assert [item["id"] for item in active_after_restore_response.json()["items"]] == [
        active_issue["id"],
        archived_issue["id"],
    ]


def test_bulk_status_updates_append_in_requested_order(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    project = _create_project(client, token)

    existing_todo = _create_issue(client, token, project["id"], title="Existing todo", status="todo")
    backlog_first = _create_issue(client, token, project["id"], title="Backlog first", status="backlog")
    backlog_second = _create_issue(client, token, project["id"], title="Backlog second", status="backlog")

    bulk_response = client.patch(
        f"/api/v1/pms/projects/{project['id']}/issues/bulk",
        headers=_auth_headers(token),
        json={
            "issue_ids": [backlog_second["id"], backlog_first["id"]],
            "status": "todo",
        },
    )
    assert bulk_response.status_code == 200
    assert bulk_response.json() == {"updated_count": 2, "deleted_count": 0}

    todo_issues_response = client.get(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(token),
        params=[("status", "todo"), ("page_size", "100"), ("sort_by", "board_position"), ("sort_dir", "asc")],
    )
    assert todo_issues_response.status_code == 200
    todo_items = todo_issues_response.json()["items"]

    assert [item["id"] for item in todo_items] == [
        existing_todo["id"],
        backlog_second["id"],
        backlog_first["id"],
    ]
    assert [item["board_position"] for item in todo_items] == [1, 2, 3]


def _bootstrap_admin(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201
    return response.json()["token"]


def _create_project(client: TestClient, token: str) -> dict:
    response = client.post(
        "/api/v1/pms/projects",
        headers=_auth_headers(token),
        json={
            "key": "PMS",
            "name": "PMS Project",
            "description": "Project for PMS issue tests",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_issue(
    client: TestClient,
    token: str,
    project_id: str,
    *,
    title: str,
    status: str = "backlog",
) -> dict:
    response = client.post(
        f"/api/v1/pms/projects/{project_id}/issues",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "",
            "status": status,
            "priority": "medium",
            "assignee_id": None,
            "milestone_id": None,
            "parent_id": None,
            "start_date": None,
            "due_date": None,
            "label_ids": [],
        },
    )
    assert response.status_code == 201
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
