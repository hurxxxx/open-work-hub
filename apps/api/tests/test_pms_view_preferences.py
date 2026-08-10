from fastapi.testclient import TestClient

from dev_accounts import create_workspace_user_session


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _session(
    client: TestClient,
    *,
    workspace_key: str,
    login_id: str,
    email: str,
) -> dict:
    return create_workspace_user_session(
        client,
        workspace_key=workspace_key,
        login_id=login_id,
        email=email,
        full_name=login_id.replace("-", " ").title(),
    )


def test_pms_view_preference_defaults_and_persists_per_user_and_workspace(
    client: TestClient,
) -> None:
    first = _session(
        client,
        workspace_key="pref-workspace-a",
        login_id="pref-user-a",
        email="pref-user-a@ai-do.local",
    )
    path = "/api/v1/workspaces/pref-workspace-a/pms/view-preferences"

    default_response = client.get(path, headers=_headers(first["token"]))
    assert default_response.status_code == 200, default_response.text
    assert default_response.json() == {"task_list_group_by": "status"}

    update_response = client.patch(
        path,
        headers=_headers(first["token"]),
        json={"task_list_group_by": "assignee"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json() == {"task_list_group_by": "assignee"}
    assert client.get(path, headers=_headers(first["token"])).json() == {
        "task_list_group_by": "assignee"
    }

    ungroup_response = client.patch(
        path,
        headers=_headers(first["token"]),
        json={"task_list_group_by": "none"},
    )
    assert ungroup_response.status_code == 200, ungroup_response.text
    assert client.get(path, headers=_headers(first["token"])).json() == {
        "task_list_group_by": "none"
    }

    second = _session(
        client,
        workspace_key="pref-workspace-a",
        login_id="pref-user-b",
        email="pref-user-b@ai-do.local",
    )
    second_response = client.get(path, headers=_headers(second["token"]))
    assert second_response.status_code == 200, second_response.text
    assert second_response.json() == {"task_list_group_by": "status"}

    same_user_other_workspace = _session(
        client,
        workspace_key="pref-workspace-b",
        login_id="pref-user-a",
        email="pref-user-a@ai-do.local",
    )
    other_workspace_response = client.get(
        "/api/v1/workspaces/pref-workspace-b/pms/view-preferences",
        headers=_headers(same_user_other_workspace["token"]),
    )
    assert other_workspace_response.status_code == 200, other_workspace_response.text
    assert other_workspace_response.json() == {"task_list_group_by": "status"}


def test_pms_view_preference_rejects_invalid_or_inaccessible_requests(
    client: TestClient,
) -> None:
    session = _session(
        client,
        workspace_key="pref-guard-workspace",
        login_id="pref-guard-user",
        email="pref-guard-user@ai-do.local",
    )
    path = "/api/v1/workspaces/pref-guard-workspace/pms/view-preferences"

    invalid_response = client.patch(
        path,
        headers=_headers(session["token"]),
        json={"task_list_group_by": "reporter"},
    )
    assert invalid_response.status_code == 422, invalid_response.text

    unauthenticated_response = client.get(path)
    assert unauthenticated_response.status_code == 401

    cross_workspace_response = client.get(
        "/api/v1/workspaces/administrator/pms/view-preferences",
        headers=_headers(session["token"]),
    )
    assert cross_workspace_response.status_code == 403
    assert cross_workspace_response.json()["code"] == "workspace.membership_required"
