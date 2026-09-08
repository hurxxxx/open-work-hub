from fastapi.testclient import TestClient

from dev_accounts import create_company_user_session


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _session(
    client: TestClient,
    *,
    login_id: str,
    email: str,
) -> dict:
    return create_company_user_session(
        client,
        login_id=login_id,
        email=email,
        full_name=login_id.replace("-", " ").title(),
    )


def test_pms_view_preference_is_per_user_and_shared_across_sessions(
    client: TestClient,
) -> None:
    first = _session(
        client,
        login_id="pref-user-a",
        email="pref-user-a@open-work-hub.local",
    )
    path = "/api/v1/pms/view-preferences"

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
        login_id="pref-user-b",
        email="pref-user-b@open-work-hub.local",
    )
    second_response = client.get(path, headers=_headers(second["token"]))
    assert second_response.status_code == 200, second_response.text
    assert second_response.json() == {"task_list_group_by": "status"}

    same_user_next_session = _session(
        client,
        login_id="pref-user-a",
        email="pref-user-a@open-work-hub.local",
    )
    next_session_response = client.get(
        "/api/v1/pms/view-preferences",
        headers=_headers(same_user_next_session["token"]),
    )
    assert next_session_response.status_code == 200, next_session_response.text
    assert next_session_response.json() == {"task_list_group_by": "none"}


def test_pms_view_preference_rejects_invalid_or_inaccessible_requests(
    client: TestClient,
) -> None:
    session = _session(
        client,
        login_id="pref-guard-user",
        email="pref-guard-user@open-work-hub.local",
    )
    path = "/api/v1/pms/view-preferences"

    invalid_response = client.patch(
        path,
        headers=_headers(session["token"]),
        json={"task_list_group_by": "reporter"},
    )
    assert invalid_response.status_code == 422, invalid_response.text

    unauthenticated_response = client.get(path)
    assert unauthenticated_response.status_code == 401

    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

    with get_session_factory()() as db:
        db.get(AppAccessPolicy, "pms").audience = "selected"
        db.commit()
    denied_response = client.get(
        "/api/v1/pms/view-preferences",
        headers=_headers(session["token"]),
    )
    assert denied_response.status_code == 403
    assert denied_response.json()["code"] == "app.access_required"
