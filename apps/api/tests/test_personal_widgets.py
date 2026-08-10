from __future__ import annotations

from fastapi.testclient import TestClient

from dev_accounts import auth_headers, dev_login


def test_personal_todo_crud_and_completed_filter(client: TestClient) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])

    first = _create_todo(client, headers=headers, title="  First task  ")
    second = _create_todo(client, headers=headers, title="Second task")

    assert first["title"] == "First task"
    assert first["completed"] is False
    assert first["completedAt"] is None

    update_response = client.patch(
        f"/api/v1/personal-widgets/todos/{first['id']}",
        headers=headers,
        json={"completed": True, "title": "Done task"},
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["title"] == "Done task"
    assert updated["completed"] is True
    assert updated["completedAt"] is not None

    list_response = client.get("/api/v1/personal-widgets/todos", headers=headers)
    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()["items"]] == [
        second["id"],
        first["id"],
    ]

    active_response = client.get(
        "/api/v1/personal-widgets/todos",
        headers=headers,
        params={"include_completed": "false"},
    )
    assert active_response.status_code == 200, active_response.text
    assert [item["id"] for item in active_response.json()["items"]] == [second["id"]]

    delete_response = client.delete(
        f"/api/v1/personal-widgets/todos/{second['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text

    remaining_response = client.get("/api/v1/personal-widgets/todos", headers=headers)
    assert [item["id"] for item in remaining_response.json()["items"]] == [first["id"]]


def test_personal_todos_are_isolated_by_user(client: TestClient) -> None:
    owner = dev_login(client, "administrator")
    other = dev_login(client, "delivery-hub-member")
    owner_headers = auth_headers(owner["token"])
    other_headers = auth_headers(other["token"])
    todo = _create_todo(client, headers=owner_headers, title="Private task")

    other_list = client.get("/api/v1/personal-widgets/todos", headers=other_headers)
    assert other_list.status_code == 200, other_list.text
    assert other_list.json() == {"items": []}

    other_update = client.patch(
        f"/api/v1/personal-widgets/todos/{todo['id']}",
        headers=other_headers,
        json={"completed": True},
    )
    assert other_update.status_code == 404, other_update.text

    other_delete = client.delete(
        f"/api/v1/personal-widgets/todos/{todo['id']}",
        headers=other_headers,
    )
    assert other_delete.status_code == 404, other_delete.text

    owner_list = client.get("/api/v1/personal-widgets/todos", headers=owner_headers)
    assert [item["id"] for item in owner_list.json()["items"]] == [todo["id"]]


def test_personal_todo_title_validation(client: TestClient) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])

    blank_response = client.post(
        "/api/v1/personal-widgets/todos",
        headers=headers,
        json={"title": "   "},
    )
    assert blank_response.status_code == 422, blank_response.text

    long_response = client.post(
        "/api/v1/personal-widgets/todos",
        headers=headers,
        json={"title": "x" * 241},
    )
    assert long_response.status_code == 422, long_response.text


def test_personal_memo_get_and_save(client: TestClient) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])

    empty_response = client.get("/api/v1/personal-widgets/memo", headers=headers)
    assert empty_response.status_code == 200, empty_response.text
    assert empty_response.json() == {
        "id": None,
        "body": "",
        "createdAt": None,
        "updatedAt": None,
    }

    save_response = client.put(
        "/api/v1/personal-widgets/memo",
        headers=headers,
        json={"body": "Line one\nLine two"},
    )
    assert save_response.status_code == 200, save_response.text
    saved = save_response.json()
    assert saved["id"]
    assert saved["body"] == "Line one\nLine two"
    assert saved["createdAt"]
    assert saved["updatedAt"]

    update_response = client.put(
        "/api/v1/personal-widgets/memo",
        headers=headers,
        json={"body": "Updated memo"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["id"] == saved["id"]
    assert update_response.json()["body"] == "Updated memo"

    get_response = client.get("/api/v1/personal-widgets/memo", headers=headers)
    assert get_response.json()["body"] == "Updated memo"


def test_personal_memo_is_isolated_by_user(client: TestClient) -> None:
    owner = dev_login(client, "administrator")
    other = dev_login(client, "delivery-hub-member")

    owner_save = client.put(
        "/api/v1/personal-widgets/memo",
        headers=auth_headers(owner["token"]),
        json={"body": "Owner private memo"},
    )
    assert owner_save.status_code == 200, owner_save.text

    other_get = client.get(
        "/api/v1/personal-widgets/memo",
        headers=auth_headers(other["token"]),
    )
    assert other_get.status_code == 200, other_get.text
    assert other_get.json()["body"] == ""

    other_save = client.put(
        "/api/v1/personal-widgets/memo",
        headers=auth_headers(other["token"]),
        json={"body": "Other private memo"},
    )
    assert other_save.status_code == 200, other_save.text

    owner_get = client.get(
        "/api/v1/personal-widgets/memo",
        headers=auth_headers(owner["token"]),
    )
    assert owner_get.json()["body"] == "Owner private memo"


def _create_todo(client: TestClient, *, headers: dict[str, str], title: str) -> dict:
    response = client.post(
        "/api/v1/personal-widgets/todos",
        headers=headers,
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()
