from fastapi.testclient import TestClient


def _dev_login(client: TestClient, account_key: str) -> dict:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": account_key},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_issue_list_archived_filters_and_bulk_restore(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    task_list = _create_task_list(client, token)

    active_issue = _create_issue(client, token, task_list["id"], title="Active issue")
    archived_issue = _create_issue(client, token, task_list["id"], title="Archived issue")

    archive_response = client.patch(
        f"/api/v1/pms/issues/{archived_issue['id']}",
        headers=_auth_headers(token),
        json={"archived": True},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["archived"] is True

    active_only_response = client.get(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        params={"archived": "false"},
    )
    assert active_only_response.status_code == 200
    assert [item["id"] for item in active_only_response.json()["items"]] == [active_issue["id"]]

    archived_only_response = client.get(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        params={"archived": "true"},
    )
    assert archived_only_response.status_code == 200
    assert [item["id"] for item in archived_only_response.json()["items"]] == [archived_issue["id"]]

    restore_response = client.patch(
        f"/api/v1/pms/lists/{task_list['id']}/issues/bulk",
        headers=_auth_headers(token),
        json={"issue_ids": [archived_issue["id"]], "archived": False},
    )
    assert restore_response.status_code == 200
    assert restore_response.json() == {"updated_count": 1, "deleted_count": 0}

    archived_after_restore_response = client.get(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(token),
        params={"archived": "true"},
    )
    assert archived_after_restore_response.status_code == 200
    assert archived_after_restore_response.json()["items"] == []

    active_after_restore_response = client.get(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
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
    task_list = _create_task_list(client, token)

    existing_todo = _create_issue(client, token, task_list["id"], title="Existing todo", status="todo")
    backlog_first = _create_issue(client, token, task_list["id"], title="Backlog first", status="backlog")
    backlog_second = _create_issue(client, token, task_list["id"], title="Backlog second", status="backlog")

    bulk_response = client.patch(
        f"/api/v1/pms/lists/{task_list['id']}/issues/bulk",
        headers=_auth_headers(token),
        json={
            "issue_ids": [backlog_second["id"], backlog_first["id"]],
            "status": "todo",
        },
    )
    assert bulk_response.status_code == 200
    assert bulk_response.json() == {"updated_count": 2, "deleted_count": 0}

    todo_issues_response = client.get(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
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


def test_viewer_cannot_modify_issue_comment_or_folder(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    issue = _create_issue(client, admin_session["token"], task_list["id"], title="Protected issue")

    viewer = _create_user(client, admin_session["token"], email="viewer@aidoo.local", full_name="Viewer User")
    _add_task_list_member(client, admin_session["token"], task_list["id"], viewer["user"]["id"], "viewer")
    viewer_token = _login(client, viewer["user"]["email"], viewer["temporary_password"])

    update_response = client.patch(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(viewer_token),
        json={"title": "Viewer edit attempt"},
    )
    assert update_response.status_code == 403

    comment_response = client.post(
        f"/api/v1/pms/issues/{issue['id']}/comments",
        headers=_auth_headers(viewer_token),
        json={"body": "viewer comment"},
    )
    assert comment_response.status_code == 403

    folder_response = client.post(
        "/api/v1/pms/folders",
        headers=_auth_headers(viewer_token),
        json={"name": "Viewer folder", "team_id": task_list["team_id"]},
    )
    assert folder_response.status_code == 403

    space_doc_response = client.post(
        f"/api/v1/pms/spaces/{task_list['team_id']}/docs",
        headers=_auth_headers(viewer_token),
        json={"title": "Viewer collection"},
    )
    assert space_doc_response.status_code == 403


def test_explicit_null_clears_nullable_issue_fields(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    issue = _create_issue(
        client,
        admin_session["token"],
        task_list["id"],
        title="Clear me",
        assignee_id=admin_session["user"]["id"],
        start_date="2026-04-01",
        due_date="2026-04-10",
        recurrence_rule="FREQ=DAILY",
    )

    clear_response = client.patch(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(admin_session["token"]),
        json={
            "assignee_id": None,
            "start_date": None,
            "due_date": None,
            "recurrence_rule": None,
        },
    )
    assert clear_response.status_code == 200
    payload = clear_response.json()
    assert payload["assignee_id"] is None
    assert payload["start_date"] is None
    assert payload["due_date"] is None
    assert payload["recurrence_rule"] is None


def test_issue_assignees_reject_non_members(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    issue = _create_issue(client, admin_session["token"], task_list["id"], title="Assignee guard")
    outsider = _create_user(client, admin_session["token"], email="outsider@aidoo.local", full_name="Outsider User")

    response = client.put(
        f"/api/v1/pms/issues/{issue['id']}/assignees",
        headers=_auth_headers(admin_session["token"]),
        json={"user_ids": [outsider["user"]["id"]]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Assignees must be task list members."


def test_list_alias_space_docs_and_status_rename_behave_as_expected(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    create_response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(admin_session["token"]),
        json={
            "key": "LIST",
            "name": "List alias",
            "description": "Created via list alias",
        },
    )
    assert create_response.status_code == 201
    task_list = create_response.json()
    assert task_list["team_id"] is not None

    create_issue_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/issues",
        headers=_auth_headers(admin_session["token"]),
        json={
            "title": "List-id issue",
            "description": "",
            "status": "backlog",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert create_issue_response.status_code == 201
    issue = create_issue_response.json()
    assert issue["list_id"] == task_list["id"]
    assert "project_id" not in issue

    status_create_response = client.post(
        f"/api/v1/pms/lists/{task_list['id']}/statuses",
        headers=_auth_headers(admin_session["token"]),
        json={"name": "QA Ready", "category": "active"},
    )
    assert status_create_response.status_code == 201
    status_item = status_create_response.json()

    status_update_response = client.patch(
        f"/api/v1/pms/task-list-statuses/{status_item['id']}",
        headers=_auth_headers(admin_session["token"]),
        json={"name": "QA Signoff"},
    )
    assert status_update_response.status_code == 200
    assert status_update_response.json()["name"] == "QA Signoff"
    assert status_update_response.json()["slug"] == status_item["slug"]

    create_space_doc_response = client.post(
        f"/api/v1/pms/spaces/{task_list['team_id']}/docs",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Space Collection"},
    )
    assert create_space_doc_response.status_code == 201
    space_doc = create_space_doc_response.json()

    missing_query_response = client.get(
        f"/api/v1/pms/spaces/{task_list['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
    )
    assert missing_query_response.status_code == 400
    assert missing_query_response.json()["detail"] == "space_doc_id is required."

    create_page_response = client.post(
        f"/api/v1/pms/spaces/{task_list['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Space Page", "space_doc_id": space_doc["id"]},
    )
    assert create_page_response.status_code == 201
    page = create_page_response.json()
    assert page["space_doc_id"] == space_doc["id"]

    create_child_response = client.post(
        f"/api/v1/pms/spaces/{task_list['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Nested Space Page", "space_doc_id": space_doc["id"], "parent_id": page["id"]},
    )
    assert create_child_response.status_code == 201
    child_page = create_child_response.json()

    list_pages_response = client.get(
        f"/api/v1/pms/spaces/{task_list['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        params={"space_doc_id": space_doc["id"]},
    )
    assert list_pages_response.status_code == 200
    assert [item["id"] for item in list_pages_response.json()["items"]] == [page["id"], child_page["id"]]

    update_page_response = client.patch(
        f"/api/v1/pms/space-doc-pages/{page['id']}",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Updated Space Page"},
    )
    assert update_page_response.status_code == 200
    assert update_page_response.json()["title"] == "Updated Space Page"

    delete_page_response = client.delete(
        f"/api/v1/pms/space-doc-pages/{page['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert delete_page_response.status_code == 204

    list_pages_after_delete_response = client.get(
        f"/api/v1/pms/spaces/{task_list['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        params={"space_doc_id": space_doc["id"]},
    )
    assert list_pages_after_delete_response.status_code == 200
    assert list_pages_after_delete_response.json()["items"] == []

    deleted_page_response = client.get(
        f"/api/v1/pms/space-doc-pages/{page['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_page_response.status_code == 404

    deleted_child_response = client.get(
        f"/api/v1/pms/space-doc-pages/{child_page['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_child_response.status_code == 404


def test_workspace_scoped_default_pms_space_stays_inside_requested_workspace(
    client: TestClient,
) -> None:
    _bootstrap_admin_session(client)

    hq_admin = _dev_login(client, "hq-admin")
    platform_admin = _dev_login(client, "platform-admin")
    hq_admin_token = hq_admin["token"]
    platform_admin_token = platform_admin["token"]

    before_hq_spaces = client.get(
        "/api/v1/workspaces/hq/pms/spaces",
        headers=_auth_headers(hq_admin_token),
    )
    assert before_hq_spaces.status_code == 200
    hq_space_ids = {item["id"] for item in before_hq_spaces.json()}

    before_delivery_spaces = client.get(
        "/api/v1/workspaces/delivery-hub/pms/spaces",
        headers=_auth_headers(platform_admin_token),
    )
    assert before_delivery_spaces.status_code == 403

    create_list_response = client.post(
        "/api/v1/workspaces/hq/pms/lists",
        headers=_auth_headers(hq_admin_token),
        json={
            "key": "HQCTX",
            "name": "HQ Context List",
            "description": "Should bind to HQ default space",
        },
    )
    assert create_list_response.status_code == 201, create_list_response.text
    created_list = create_list_response.json()
    assert created_list["team_id"] in hq_space_ids

    create_folder_response = client.post(
        "/api/v1/workspaces/hq/pms/folders",
        headers=_auth_headers(hq_admin_token),
        json={"name": "HQ Context Folder"},
    )
    assert create_folder_response.status_code == 201, create_folder_response.text
    created_folder = create_folder_response.json()
    assert created_folder["team_id"] in hq_space_ids


def test_space_docs_collection_permissions_and_soft_delete(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    collection_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Engineering Handbook"},
    )
    assert collection_response.status_code == 201
    collection = collection_response.json()

    first_page_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Overview", "space_doc_id": collection["id"]},
    )
    assert first_page_response.status_code == 201
    first_page = first_page_response.json()

    child_page_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Checklist", "space_doc_id": collection["id"], "parent_id": first_page["id"]},
    )
    assert child_page_response.status_code == 201
    child_page = child_page_response.json()

    outsider = _create_user(client, admin_session["token"], email="space-outsider@aidoo.local", full_name="Space Outsider")
    outsider_token = _login(client, outsider["user"]["email"], outsider["temporary_password"])

    outsider_list_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(outsider_token),
    )
    assert outsider_list_response.status_code == 403

    outsider_create_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(outsider_token),
        json={"title": "Forbidden"},
    )
    assert outsider_create_response.status_code == 403

    task_list_editor = _create_user(
        client,
        admin_session["token"],
        email="space-editor@aidoo.local",
        full_name="Task List Editor",
    )
    _add_task_list_member(client, admin_session["token"], task_list["id"], task_list_editor["user"]["id"], "member")
    task_list_editor_token = _login(
        client,
        task_list_editor["user"]["email"],
        task_list_editor["temporary_password"],
    )

    editor_list_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(task_list_editor_token),
    )
    assert editor_list_response.status_code == 200
    assert [item["id"] for item in editor_list_response.json()["items"]] == [collection["id"]]

    member_collection_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(task_list_editor_token),
        json={"title": "Task List Notes"},
    )
    assert member_collection_response.status_code == 201
    member_collection = member_collection_response.json()
    assert member_collection["created_by_id"] == task_list_editor["user"]["id"]

    member_page_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs/pages",
        headers=_auth_headers(task_list_editor_token),
        json={"title": "Member page", "space_doc_id": collection["id"]},
    )
    assert member_page_response.status_code == 201

    member_folder_response = client.post(
        "/api/v1/pms/folders",
        headers=_auth_headers(task_list_editor_token),
        json={"name": "Member folder", "team_id": space_id},
    )
    assert member_folder_response.status_code == 201
    member_folder = member_folder_response.json()
    assert member_folder["team_id"] == space_id

    second_collection_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Admin Notes"},
    )
    assert second_collection_response.status_code == 201
    second_collection = second_collection_response.json()

    cross_collection_parent_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={
            "title": "Invalid child",
            "space_doc_id": second_collection["id"],
            "parent_id": first_page["id"],
        },
    )
    assert cross_collection_parent_response.status_code == 409
    assert cross_collection_parent_response.json()["detail"] == "Parent page must belong to the same document collection."

    delete_collection_response = client.delete(
        f"/api/v1/pms/space-docs/{collection['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert delete_collection_response.status_code == 204

    visible_collections_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin_session["token"]),
    )
    assert visible_collections_response.status_code == 200
    visible_ids = sorted(item["id"] for item in visible_collections_response.json()["items"])
    assert visible_ids == sorted([member_collection["id"], second_collection["id"]])

    deleted_collection_response = client.get(
        f"/api/v1/pms/space-docs/{collection['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_collection_response.status_code == 404

    deleted_page_response = client.get(
        f"/api/v1/pms/space-doc-pages/{first_page['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_page_response.status_code == 404

    deleted_child_response = client.get(
        f"/api/v1/pms/space-doc-pages/{child_page['id']}",
        headers=_auth_headers(admin_session["token"]),
    )
    assert deleted_child_response.status_code == 404

    deleted_collection_pages_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        params={"space_doc_id": collection["id"]},
    )
    assert deleted_collection_pages_response.status_code == 404


def test_task_list_member_api_grants_space_scope_for_task_list_resources(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    issue = _create_issue(client, admin_session["token"], task_list["id"], title="List-only issue")

    task_list_member = _create_user(
        client,
        admin_session["token"],
        email="task-list-member@aidoo.local",
        full_name="Task List Member",
    )
    _add_task_list_member(client, admin_session["token"], task_list["id"], task_list_member["user"]["id"], "member")
    task_list_member_token = _login(
        client,
        task_list_member["user"]["email"],
        task_list_member["temporary_password"],
    )

    task_list_detail_response = client.get(
        f"/api/v1/pms/lists/{task_list['id']}",
        headers=_auth_headers(task_list_member_token),
    )
    assert task_list_detail_response.status_code == 200

    task_list_issue_detail_response = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(task_list_member_token),
    )
    assert task_list_issue_detail_response.status_code == 200

    space_lists_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/lists",
        headers=_auth_headers(task_list_member_token),
    )
    assert space_lists_response.status_code == 200
    assert any(item["id"] == task_list["id"] for item in space_lists_response.json()["items"])

    space_folders_response = client.get(
        "/api/v1/pms/folders",
        headers=_auth_headers(task_list_member_token),
        params={"team_id": space_id},
    )
    assert space_folders_response.status_code == 200

    space_docs_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(task_list_member_token),
    )
    assert space_docs_response.status_code == 200


def test_media_linking_follows_parent_resource_acl(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    issue = _create_issue(client, admin_session["token"], task_list["id"], title="Media ACL issue")

    collection_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Space Collection"},
    )
    assert collection_response.status_code == 201
    collection = collection_response.json()

    page_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Space Page", "space_doc_id": collection["id"]},
    )
    assert page_response.status_code == 201
    page = page_response.json()

    project_member = _create_user(
        client,
        admin_session["token"],
        email="media-task-list-member@aidoo.local",
        full_name="Media Task List Member",
    )
    _add_task_list_member(client, admin_session["token"], task_list["id"], project_member["user"]["id"], "member")
    project_member_token = _login(
        client,
        project_member["user"]["email"],
        project_member["temporary_password"],
    )

    issue_media = _create_unlinked_media(project_member["user"]["id"])
    issue_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(project_member_token),
        json={"media_ids": [issue_media["id"]], "resource_type": "issue", "resource_id": issue["id"]},
    )
    assert issue_link_response.status_code == 204

    removed_doc_media = _create_unlinked_media(project_member["user"]["id"])
    removed_doc_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(project_member_token),
        json={"media_ids": [removed_doc_media["id"]], "resource_type": "doc", "resource_id": issue["id"]},
    )
    assert removed_doc_link_response.status_code == 400

    forbidden_space_media = _create_unlinked_media(project_member["user"]["id"])
    forbidden_space_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(project_member_token),
        json={
            "media_ids": [forbidden_space_media["id"]],
            "resource_type": "space_doc_page",
            "resource_id": page["id"],
        },
    )
    assert forbidden_space_link_response.status_code == 204

    space_member = _create_user(
        client,
        admin_session["token"],
        email="media-space-member@aidoo.local",
        full_name="Media Space Member",
    )
    _add_team_member(client, admin_session["token"], space_id, space_member["user"]["id"])
    space_member_token = _login(
        client,
        space_member["user"]["email"],
        space_member["temporary_password"],
    )

    page_media = _create_unlinked_media(space_member["user"]["id"])
    page_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(space_member_token),
        json={
            "media_ids": [page_media["id"]],
            "resource_type": "space_doc_page",
            "resource_id": page["id"],
        },
    )
    assert page_link_response.status_code == 204


def test_team_soft_delete_hides_space_data_and_untrashes_default_space(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    headers = _auth_headers(admin_session["token"])
    task_list = _create_task_list(client, admin_session["token"])
    space_id = task_list["team_id"]
    assert space_id is not None

    workspaces_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_response.status_code == 200
    pms_workspace = next(item for item in workspaces_response.json() if item["key"] == "hq")
    assert pms_workspace["team_count"] == 1

    folder_response = client.post(
        "/api/v1/pms/folders",
        headers=headers,
        json={"name": "Operations", "team_id": space_id},
    )
    assert folder_response.status_code == 201

    collection_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=headers,
        json={"title": "Runbook"},
    )
    assert collection_response.status_code == 201
    collection = collection_response.json()

    page_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs/pages",
        headers=headers,
        json={"title": "Overview", "space_doc_id": collection["id"]},
    )
    assert page_response.status_code == 201
    page = page_response.json()

    delete_response = client.delete(
        f"/api/v1/admin/teams/{space_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204

    teams_response = client.get(
        "/api/v1/admin/teams",
        headers=headers,
        params={"workspace_id": pms_workspace["id"]},
    )
    assert teams_response.status_code == 200
    assert teams_response.json() == []

    deleted_team_update_response = client.patch(
        f"/api/v1/admin/teams/{space_id}",
        headers=headers,
        json={"name": "Archived Space", "description": ""},
    )
    assert deleted_team_update_response.status_code == 404

    deleted_team_members_response = client.get(
        f"/api/v1/admin/teams/{space_id}/members",
        headers=headers,
    )
    assert deleted_team_members_response.status_code == 404

    visible_lists_response = client.get(
        "/api/v1/pms/lists",
        headers=headers,
    )
    assert visible_lists_response.status_code == 200
    assert [item for item in visible_lists_response.json()["items"] if item["team_id"] == space_id] == []

    deleted_space_lists_response = client.get(
        "/api/v1/pms/lists",
        headers=headers,
        params={"team_id": space_id},
    )
    assert deleted_space_lists_response.status_code == 404

    deleted_space_folders_response = client.get(
        "/api/v1/pms/folders",
        headers=headers,
        params={"team_id": space_id},
    )
    assert deleted_space_folders_response.status_code == 404

    deleted_space_docs_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=headers,
    )
    assert deleted_space_docs_response.status_code == 404

    deleted_page_response = client.get(
        f"/api/v1/pms/space-doc-pages/{page['id']}",
        headers=headers,
    )
    assert deleted_page_response.status_code == 404

    workspaces_after_delete_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_after_delete_response.status_code == 200
    pms_workspace_after_delete = next(
        item for item in workspaces_after_delete_response.json() if item["key"] == "hq"
    )
    assert pms_workspace_after_delete["team_count"] == 0

    recreated_task_list_response = client.post(
        "/api/v1/pms/lists",
        headers=headers,
        json={
            "key": "PMS2",
            "name": "Recovered List",
            "description": "List after untrash",
        },
    )
    assert recreated_task_list_response.status_code == 201
    recreated_task_list = recreated_task_list_response.json()
    assert recreated_task_list["team_id"] == space_id

    teams_after_restore_response = client.get(
        "/api/v1/admin/teams",
        headers=headers,
        params={"workspace_id": pms_workspace["id"]},
    )
    assert teams_after_restore_response.status_code == 200
    assert [item["id"] for item in teams_after_restore_response.json()] == [space_id]

    workspaces_after_restore_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_after_restore_response.status_code == 200
    pms_workspace_after_restore = next(
        item for item in workspaces_after_restore_response.json() if item["key"] == "hq"
    )
    assert pms_workspace_after_restore["team_count"] == 1


def _bootstrap_admin(client: TestClient) -> str:
    return _bootstrap_admin_session(client)["token"]


def test_task_list_patch_sort_order_and_cross_folder_move(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list_a = _create_task_list(client, admin["token"], key="REORD", name="Reorder List A")
    space_id = task_list_a["team_id"]
    assert space_id is not None

    folder_one = client.post(
        "/api/v1/pms/folders",
        headers=_auth_headers(admin["token"]),
        json={"name": "Alpha", "team_id": space_id},
    ).json()
    folder_two = client.post(
        "/api/v1/pms/folders",
        headers=_auth_headers(admin["token"]),
        json={"name": "Bravo", "team_id": space_id},
    ).json()

    task_list_b = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(admin["token"]),
        json={"name": "Reorder List B", "description": "", "team_id": space_id, "folder_id": folder_one["id"]},
    ).json()
    task_list_c = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(admin["token"]),
        json={"name": "Reorder List C", "description": "", "team_id": space_id, "folder_id": folder_one["id"]},
    ).json()

    # Reorder: B and C both live in folder_one. Assign explicit sort_order values.
    patch_b = client.patch(
        f"/api/v1/pms/lists/{task_list_b['id']}",
        headers=_auth_headers(admin["token"]),
        json={"sort_order": 1000},
    )
    assert patch_b.status_code == 200
    assert patch_b.json()["sort_order"] == 1000

    patch_c = client.patch(
        f"/api/v1/pms/lists/{task_list_c['id']}",
        headers=_auth_headers(admin["token"]),
        json={"sort_order": 0},
    )
    assert patch_c.status_code == 200
    assert patch_c.json()["sort_order"] == 0

    listed = client.get(
        f"/api/v1/pms/spaces/{space_id}/lists",
        headers=_auth_headers(admin["token"]),
        params={"sort_by": "sort_order"},
    ).json()["items"]
    tracked_ids = {task_list_b["id"], task_list_c["id"]}
    folder_one_order = [item["name"] for item in listed if item["id"] in tracked_ids]
    assert folder_one_order == ["Reorder List C", "Reorder List B"]

    # Cross-folder move: B → folder_two, with new sort_order.
    move_b = client.patch(
        f"/api/v1/pms/lists/{task_list_b['id']}",
        headers=_auth_headers(admin["token"]),
        json={"folder_id": folder_two["id"], "sort_order": 0},
    )
    assert move_b.status_code == 200
    assert move_b.json()["folder_id"] == folder_two["id"]
    assert move_b.json()["sort_order"] == 0

    listed_after = client.get(
        f"/api/v1/pms/spaces/{space_id}/lists",
        headers=_auth_headers(admin["token"]),
        params={"sort_by": "sort_order"},
    ).json()["items"]
    by_folder = {item["id"]: item["folder_id"] for item in listed_after}
    assert by_folder[task_list_b["id"]] == folder_two["id"]
    assert by_folder[task_list_c["id"]] == folder_one["id"]


def test_space_doc_collection_patch_sort_order(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="DOCORD", name="Doc Reorder List")
    space_id = task_list["team_id"]
    assert space_id is not None

    doc_a = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Alpha Doc"},
    ).json()
    doc_b = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Bravo Doc"},
    ).json()
    doc_c = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Charlie Doc"},
    ).json()

    # Reorder: C first, A second, B third.
    client.patch(
        f"/api/v1/pms/space-docs/{doc_c['id']}",
        headers=_auth_headers(admin["token"]),
        json={"sort_order": 0},
    )
    client.patch(
        f"/api/v1/pms/space-docs/{doc_a['id']}",
        headers=_auth_headers(admin["token"]),
        json={"sort_order": 1000},
    )
    client.patch(
        f"/api/v1/pms/space-docs/{doc_b['id']}",
        headers=_auth_headers(admin["token"]),
        json={"sort_order": 2000},
    )

    listed = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
    ).json()["items"]
    assert [item["title"] for item in listed] == ["Charlie Doc", "Alpha Doc", "Bravo Doc"]
    assert [item["sort_order"] for item in listed] == [0, 1000, 2000]


def test_space_member_can_reorder_task_list_without_owner_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list_a = _create_task_list(client, admin["token"], key="LREORD", name="List Reorder A")
    space_id = task_list_a["team_id"]
    assert space_id is not None

    folder = client.post(
        "/api/v1/pms/folders",
        headers=_auth_headers(admin["token"]),
        json={"name": "Target Folder", "team_id": space_id},
    ).json()
    task_list_b = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(admin["token"]),
        json={"name": "List Reorder B", "description": "", "team_id": space_id},
    ).json()

    member = _create_user(client, admin["token"], email="list-reorder-member@aidoo.local", full_name="List Reorder Member")
    _add_task_list_member(client, admin["token"], task_list_a["id"], member["user"]["id"], "member")
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    reorder_response = client.patch(
        f"/api/v1/pms/lists/{task_list_b['id']}",
        headers=_auth_headers(member_token),
        json={"folder_id": folder["id"], "sort_order": 0},
    )
    assert reorder_response.status_code == 200
    assert reorder_response.json()["folder_id"] == folder["id"]
    assert reorder_response.json()["sort_order"] == 0

    rename_response = client.patch(
        f"/api/v1/pms/lists/{task_list_b['id']}",
        headers=_auth_headers(member_token),
        json={"name": "Should still fail"},
    )
    assert rename_response.status_code == 403


def test_space_member_can_reorder_space_doc_without_manager_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="DREORD", name="Doc Reorder Access")
    space_id = task_list["team_id"]
    assert space_id is not None

    doc_a = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Alpha Doc"},
    ).json()
    doc_b = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Bravo Doc"},
    ).json()

    member = _create_user(client, admin["token"], email="doc-reorder-member@aidoo.local", full_name="Doc Reorder Member")
    _add_task_list_member(client, admin["token"], task_list["id"], member["user"]["id"], "member")
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    reorder_response = client.patch(
        f"/api/v1/pms/space-docs/{doc_b['id']}",
        headers=_auth_headers(member_token),
        json={"sort_order": 0},
    )
    assert reorder_response.status_code == 200
    assert reorder_response.json()["sort_order"] == 0

    rename_response = client.patch(
        f"/api/v1/pms/space-docs/{doc_a['id']}",
        headers=_auth_headers(member_token),
        json={"title": "Should still fail"},
    )
    assert rename_response.status_code == 403


def test_bulk_reorder_space_lists_updates_order_and_folder_in_one_request(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list_a = _create_task_list(client, admin["token"], key="BLST1", name="Bulk List A")
    space_id = task_list_a["team_id"]
    assert space_id is not None

    folder = client.post(
        "/api/v1/pms/folders",
        headers=_auth_headers(admin["token"]),
        json={"name": "Bulk Folder", "team_id": space_id},
    ).json()
    task_list_b = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(admin["token"]),
        json={"name": "Bulk List B", "description": "", "team_id": space_id},
    ).json()
    task_list_c = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(admin["token"]),
        json={"name": "Bulk List C", "description": "", "team_id": space_id},
    ).json()

    reorder_response = client.patch(
        f"/api/v1/pms/spaces/{space_id}/lists/reorder",
        headers=_auth_headers(admin["token"]),
        json={
            "items": [
                {"id": task_list_b["id"], "folder_id": folder["id"], "sort_order": 0},
                {"id": task_list_a["id"], "folder_id": None, "sort_order": 1000},
                {"id": task_list_c["id"], "folder_id": None, "sort_order": 2000},
            ]
        },
    )
    assert reorder_response.status_code == 204

    listed = client.get(
        f"/api/v1/pms/spaces/{space_id}/lists",
        headers=_auth_headers(admin["token"]),
        params={"sort_by": "sort_order"},
    ).json()["items"]
    by_id = {item["id"]: item for item in listed}
    assert by_id[task_list_b["id"]]["folder_id"] == folder["id"]
    root_order = [item["id"] for item in listed if item["folder_id"] is None]
    assert root_order[:2] == [task_list_a["id"], task_list_c["id"]]


def test_bulk_reorder_space_docs_allows_member_and_updates_order(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="BDOC1", name="Bulk Doc List")
    space_id = task_list["team_id"]
    assert space_id is not None

    doc_a = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Bulk Doc A"},
    ).json()
    doc_b = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Bulk Doc B"},
    ).json()
    doc_c = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Bulk Doc C"},
    ).json()

    member = _create_user(client, admin["token"], email="bulk-doc-member@aidoo.local", full_name="Bulk Doc Member")
    _add_task_list_member(client, admin["token"], task_list["id"], member["user"]["id"], "member")
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    reorder_response = client.patch(
        f"/api/v1/pms/spaces/{space_id}/docs/reorder",
        headers=_auth_headers(member_token),
        json={
            "items": [
                {"id": doc_b["id"], "sort_order": 0},
                {"id": doc_a["id"], "sort_order": 1000},
                {"id": doc_c["id"], "sort_order": 2000},
            ]
        },
    )
    assert reorder_response.status_code == 204

    listed = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(admin["token"]),
    ).json()["items"]
    assert [item["id"] for item in listed] == [doc_b["id"], doc_a["id"], doc_c["id"]]


def test_assigned_issues_returns_only_current_users_open_issues(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="ASGN", name="Assigned List")

    teammate = _create_user(client, admin["token"], email="assigned-teammate@aidoo.local", full_name="Teammate")
    _add_task_list_member(client, admin["token"], task_list["id"], teammate["user"]["id"], "member")

    _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Assigned to admin (due soon)",
        assignee_id=admin["user"]["id"],
        due_date="2026-04-20",
    )
    _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Assigned to admin (no due)",
        assignee_id=admin["user"]["id"],
    )
    teammate_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Assigned to teammate",
        assignee_id=teammate["user"]["id"],
    )
    unassigned_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Unassigned issue",
    )

    closed_issue = _create_issue(
        client,
        admin["token"],
        task_list["id"],
        title="Closed assigned issue",
        assignee_id=admin["user"]["id"],
    )
    close_response = client.patch(
        f"/api/v1/pms/issues/{closed_issue['id']}",
        headers=_auth_headers(admin["token"]),
        json={"status": "done"},
    )
    assert close_response.status_code == 200

    response = client.get(
        "/api/v1/pms/issues/assigned",
        headers=_auth_headers(admin["token"]),
    )
    assert response.status_code == 200
    payload = response.json()
    titles = [item["title"] for item in payload["items"]]
    assert titles == [
        "Assigned to admin (due soon)",
        "Assigned to admin (no due)",
    ]
    assert teammate_issue["id"] not in {item["id"] for item in payload["items"]}
    assert unassigned_issue["id"] not in {item["id"] for item in payload["items"]}


def test_assigned_issues_respects_limit_bounds(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    task_list = _create_task_list(client, admin["token"], key="LIMIT", name="Limit List")

    for index in range(3):
        _create_issue(
            client,
            admin["token"],
            task_list["id"],
            title=f"Assigned {index}",
            assignee_id=admin["user"]["id"],
        )

    default_response = client.get(
        "/api/v1/pms/issues/assigned",
        headers=_auth_headers(admin["token"]),
    )
    assert default_response.status_code == 200
    assert len(default_response.json()["items"]) == 3

    capped_response = client.get(
        "/api/v1/pms/issues/assigned",
        headers=_auth_headers(admin["token"]),
        params={"limit": 2},
    )
    assert capped_response.status_code == 200
    assert len(capped_response.json()["items"]) == 2

    too_low_response = client.get(
        "/api/v1/pms/issues/assigned",
        headers=_auth_headers(admin["token"]),
        params={"limit": 0},
    )
    assert too_low_response.status_code == 422

    too_high_response = client.get(
        "/api/v1/pms/issues/assigned",
        headers=_auth_headers(admin["token"]),
        params={"limit": 999},
    )
    assert too_high_response.status_code == 422


def test_assigned_issues_honors_workspace_scoped_route(client: TestClient) -> None:
    _bootstrap_admin_session(client)
    hq_admin = _dev_login(client, "hq-admin")

    task_list = _create_task_list(client, hq_admin["token"], key="HQASGN", name="HQ Assigned Route")
    _create_issue(
        client,
        hq_admin["token"],
        task_list["id"],
        title="HQ scoped assigned issue",
        assignee_id=hq_admin["user"]["id"],
    )

    response = client.get(
        "/api/v1/workspaces/hq/pms/issues/assigned",
        headers=_auth_headers(hq_admin["token"]),
    )
    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["HQ scoped assigned issue"]

    denied_response = client.get(
        "/api/v1/workspaces/delivery-hub/pms/issues/assigned",
        headers=_auth_headers(hq_admin["token"]),
    )
    assert denied_response.status_code == 403


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_task_list(
    client: TestClient,
    token: str,
    *,
    key: str = "PMS",
    name: str = "PMS List",
) -> dict:
    response = client.post(
        "/api/v1/pms/lists",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": "List for PMS issue tests",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_issue(
    client: TestClient,
    token: str,
    list_id: str,
    *,
    title: str,
    status: str = "backlog",
    assignee_id: str | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    recurrence_rule: str | None = None,
) -> dict:
    response = client.post(
        f"/api/v1/pms/lists/{list_id}/issues",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "",
            "status": status,
            "priority": "medium",
            "assignee_id": assignee_id,
            "milestone_id": None,
            "parent_id": None,
            "start_date": start_date,
            "due_date": due_date,
            "recurrence_rule": recurrence_rule,
            "label_ids": [],
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_user(client: TestClient, token: str, *, email: str, full_name: str) -> dict:
    response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": email,
            "full_name": full_name,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    _grant_workspace_access(client, token, payload["user"]["id"], "pms")
    return payload


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _add_task_list_member(client: TestClient, token: str, list_id: str, user_id: str, role: str) -> dict:
    response = client.post(
        f"/api/v1/pms/lists/{list_id}/members",
        headers=_auth_headers(token),
        json={"user_id": user_id, "role": role},
    )
    assert response.status_code == 201
    return response.json()


def _add_team_member(client: TestClient, token: str, team_id: str, user_id: str) -> list[dict]:
    current_members_response = client.get(
        f"/api/v1/admin/teams/{team_id}/members",
        headers=_auth_headers(token),
    )
    assert current_members_response.status_code == 200
    current_member_ids = [item["id"] for item in current_members_response.json()]

    response = client.put(
        f"/api/v1/admin/teams/{team_id}/members",
        headers=_auth_headers(token),
        json={"user_ids": sorted({*current_member_ids, user_id})},
    )
    assert response.status_code == 200
    return response.json()


def _grant_workspace_access(
    client: TestClient,
    token: str,
    user_id: str,
    workspace_key: str,
    role: str = "member",
) -> None:
    workspaces_response = client.get(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(token),
    )
    assert workspaces_response.status_code == 200
    workspace = next(
        (item for item in workspaces_response.json() if item["key"] == workspace_key),
        None,
    )
    if workspace is None:
        workspace = next(iter(workspaces_response.json()), None)
    assert workspace is not None

    bindings_response = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
    )
    assert bindings_response.status_code == 200
    bindings = bindings_response.json()

    user_bindings = [
        {"subject_id": item["subject_id"], "role": item["role"]}
        for item in bindings
        if item["subject_type"] == "user"
    ]
    group_bindings = [
        {"subject_id": item["subject_id"], "role": item["role"]}
        for item in bindings
        if item["subject_type"] == "group"
    ]
    user_bindings = [
        item
        for item in user_bindings
        if item["subject_id"] != user_id
    ] + [{"subject_id": user_id, "role": role}]

    update_response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(token),
        json={"users": user_bindings, "groups": group_bindings},
    )
    assert update_response.status_code == 200


def _create_unlinked_media(uploaded_by_id: str) -> dict[str, str]:
    from aidoo_api.core.db import get_session_factory
    from aidoo_api.domains.media.models import MediaFile
    from aidoo_api.domains.auth.security import new_id

    media_id = new_id()
    db = get_session_factory()()
    try:
        db.add(
            MediaFile(
                id=media_id,
                storage_key=f"media/{uploaded_by_id}/{media_id}/fixture.png",
                filename="fixture.png",
                content_type="image/png",
                size_bytes=128,
                uploaded_by_id=uploaded_by_id,
            )
        )
        db.commit()
    finally:
        db.close()

    return {"id": media_id}


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
