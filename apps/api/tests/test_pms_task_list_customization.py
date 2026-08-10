from fastapi.testclient import TestClient

from test_pms_issues import (
    _add_task_list_member,
    _auth_headers,
    _bootstrap_admin_session,
    _create_issue,
    _create_task_list,
    _create_user,
    _login,
)


def _create_task_list_user(
    client: TestClient,
    *,
    admin_token: str,
    task_list_id: str,
    email: str,
    full_name: str,
    role: str,
) -> str:
    user = _create_user(client, admin_token, email=email, full_name=full_name)
    _add_task_list_member(client, admin_token, task_list_id, user["user"]["id"], role)
    return _login(client, user["user"]["email"], user["temporary_password"])


def test_task_templates_crud_and_list_member_permissions(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(
        client,
        admin["token"],
        key="TMPL",
        name="Template customization list",
    )
    member_token = _create_task_list_user(
        client,
        admin_token=admin["token"],
        task_list_id=task_list["id"],
        email="template-member@ai-do.local",
        full_name="Template Member",
        role="member",
    )
    viewer_token = _create_task_list_user(
        client,
        admin_token=admin["token"],
        task_list_id=task_list["id"],
        email="template-viewer@ai-do.local",
        full_name="Template Viewer",
        role="viewer",
    )

    create_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/templates",
        headers=_auth_headers(member_token),
        json={
            "name": "  Launch task  ",
            "description": "  Template body  ",
            "default_status": "todo",
            "default_priority": "high",
            "checklist_items": [{"text": "Draft"}],
        },
    )
    assert create_response.status_code == 201
    template = create_response.json()
    assert template["name"] == "Launch task"
    assert template["description"] == "Template body"

    viewer_list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/templates",
        headers=_auth_headers(viewer_token),
    )
    assert viewer_list_response.status_code == 200
    assert [item["id"] for item in viewer_list_response.json()["items"]] == [template["id"]]

    viewer_create_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/templates",
        headers=_auth_headers(viewer_token),
        json={"name": "Viewer template"},
    )
    assert viewer_create_response.status_code == 403
    assert viewer_create_response.json()["code"] == "pms.task_list_viewer_modify_denied"

    update_response = client.patch(
        f"/api/v1/workspaces/administrator/pms/templates/{template['id']}",
        headers=_auth_headers(member_token),
        json={
            "name": "  Updated launch  ",
            "description": "  Updated body  ",
            "default_status": "in_progress",
            "default_priority": "critical",
            "checklist_items": [{"text": "Review"}],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Updated launch"
    assert updated["description"] == "Updated body"
    assert updated["default_status"] == "in_progress"
    assert updated["default_priority"] == "critical"
    assert updated["checklist_items"] == [{"text": "Review"}]

    delete_response = client.delete(
        f"/api/v1/workspaces/administrator/pms/templates/{template['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert delete_response.status_code == 204

    final_list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/templates",
        headers=_auth_headers(member_token),
    )
    assert final_list_response.status_code == 200
    assert final_list_response.json()["items"] == []


def test_custom_fields_values_wrong_list_and_permissions(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(
        client,
        admin["token"],
        key="CUSTA",
        name="Customization list A",
    )
    other_task_list = _create_task_list(
        client,
        admin["token"],
        key="CUSTB",
        name="Customization list B",
    )
    task = _create_issue(client, admin["token"], task_list["id"], title="Custom field task")
    member_token = _create_task_list_user(
        client,
        admin_token=admin["token"],
        task_list_id=task_list["id"],
        email="field-member@ai-do.local",
        full_name="Field Member",
        role="member",
    )
    viewer_token = _create_task_list_user(
        client,
        admin_token=admin["token"],
        task_list_id=task_list["id"],
        email="field-viewer@ai-do.local",
        full_name="Field Viewer",
        role="viewer",
    )

    select_field_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/custom-fields",
        headers=_auth_headers(admin["token"]),
        json={
            "name": "Severity",
            "field_type": "select",
            "options": ["low", "high"],
            "sort_order": 10,
        },
    )
    assert select_field_response.status_code == 201
    select_field = select_field_response.json()

    text_field_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/custom-fields",
        headers=_auth_headers(admin["token"]),
        json={"name": "Notes", "field_type": "text", "sort_order": 20},
    )
    assert text_field_response.status_code == 201
    text_field = text_field_response.json()

    list_response = client.get(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/custom-fields",
        headers=_auth_headers(viewer_token),
    )
    assert list_response.status_code == 200
    fields = list_response.json()["items"]
    assert [item["id"] for item in fields] == [select_field["id"], text_field["id"]]
    assert fields[0]["options"] == ["low", "high"]

    member_create_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{task_list['id']}/custom-fields",
        headers=_auth_headers(member_token),
        json={"name": "Member field", "field_type": "text"},
    )
    assert member_create_response.status_code == 403
    assert member_create_response.json()["code"] == "pms.task_list_owner_admin_required"

    first_value_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}/custom-field-values",
        headers=_auth_headers(member_token),
        json={"field_id": select_field["id"], "value": "low"},
    )
    assert first_value_response.status_code == 200
    assert first_value_response.json() == {"field_id": select_field["id"], "value": "low"}

    updated_value_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}/custom-field-values",
        headers=_auth_headers(member_token),
        json={"field_id": select_field["id"], "value": "high"},
    )
    assert updated_value_response.status_code == 200

    values_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}/custom-field-values",
        headers=_auth_headers(viewer_token),
    )
    assert values_response.status_code == 200
    assert values_response.json() == [{"field_id": select_field["id"], "value": "high"}]

    viewer_set_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}/custom-field-values",
        headers=_auth_headers(viewer_token),
        json={"field_id": select_field["id"], "value": "low"},
    )
    assert viewer_set_response.status_code == 403
    assert viewer_set_response.json()["code"] == "pms.task_list_viewer_modify_denied"

    foreign_field_response = client.post(
        f"/api/v1/workspaces/administrator/pms/lists/{other_task_list['id']}/custom-fields",
        headers=_auth_headers(admin["token"]),
        json={"name": "Foreign field", "field_type": "text"},
    )
    assert foreign_field_response.status_code == 201

    wrong_list_response = client.put(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}/custom-field-values",
        headers=_auth_headers(admin["token"]),
        json={"field_id": foreign_field_response.json()["id"], "value": "wrong"},
    )
    assert wrong_list_response.status_code == 400
    assert wrong_list_response.json()["code"] == "pms.custom_field_wrong_list"

    delete_response = client.delete(
        f"/api/v1/workspaces/administrator/pms/custom-fields/{select_field['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert delete_response.status_code == 204

    values_after_delete_response = client.get(
        f"/api/v1/workspaces/administrator/pms/tasks/{task['id']}/custom-field-values",
        headers=_auth_headers(member_token),
    )
    assert values_after_delete_response.status_code == 200
    assert values_after_delete_response.json() == []
