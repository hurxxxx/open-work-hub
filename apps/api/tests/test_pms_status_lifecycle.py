from fastapi.testclient import TestClient

from test_pms_issues import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_task_list,
)


DEFAULT_STATUS_SLUGS = ["todo", "in_progress", "review", "done", "complete"]


def test_status_defaults_are_shared_between_space_and_task_list(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(
        client,
        admin["token"],
        key="STAT",
        name="Status lifecycle list",
    )

    space_statuses_response = client.get(
        f"/api/v1/workspaces/administrator/pms/spaces/{task_list['team_id']}/statuses",
        headers=_auth_headers(admin["token"]),
    )
    assert space_statuses_response.status_code == 200
    assert [item["slug"] for item in space_statuses_response.json()["items"]] == DEFAULT_STATUS_SLUGS

    inherited_statuses_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/statuses",
        headers=_auth_headers(admin["token"]),
    )
    assert inherited_statuses_response.status_code == 200
    inherited_payload = inherited_statuses_response.json()
    assert inherited_payload["mode"] == "inherit"
    assert inherited_payload["source"] == "space"
    assert [item["slug"] for item in inherited_payload["items"]] == DEFAULT_STATUS_SLUGS

    custom_statuses_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/status-mode",
        headers=_auth_headers(admin["token"]),
        json={"mode": "custom"},
    )
    assert custom_statuses_response.status_code == 200
    custom_payload = custom_statuses_response.json()
    assert custom_payload["mode"] == "custom"
    assert custom_payload["source"] == "list"
    assert [item["slug"] for item in custom_payload["items"]] == DEFAULT_STATUS_SLUGS
