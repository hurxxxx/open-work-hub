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


def test_viewer_cannot_modify_issue_comment_or_folder(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    project = _create_project(client, admin_session["token"])
    issue = _create_issue(client, admin_session["token"], project["id"], title="Protected issue")

    viewer = _create_user(client, admin_session["token"], email="viewer@aidoo.local", full_name="Viewer User")
    _add_project_member(client, admin_session["token"], project["id"], viewer["user"]["id"], "viewer")
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
        json={"name": "Viewer folder", "team_id": project["team_id"]},
    )
    assert folder_response.status_code == 403


def test_explicit_null_clears_nullable_issue_fields(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    project = _create_project(client, admin_session["token"])
    issue = _create_issue(
        client,
        admin_session["token"],
        project["id"],
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
    project = _create_project(client, admin_session["token"])
    issue = _create_issue(client, admin_session["token"], project["id"], title="Assignee guard")
    outsider = _create_user(client, admin_session["token"], email="outsider@aidoo.local", full_name="Outsider User")

    response = client.put(
        f"/api/v1/pms/issues/{issue['id']}/assignees",
        headers=_auth_headers(admin_session["token"]),
        json={"user_ids": [outsider["user"]["id"]]},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Assignees must be project members."


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
    project = create_response.json()
    assert project["team_id"] is not None

    status_create_response = client.post(
        f"/api/v1/pms/lists/{project['id']}/statuses",
        headers=_auth_headers(admin_session["token"]),
        json={"name": "QA Ready", "category": "active"},
    )
    assert status_create_response.status_code == 201
    status_item = status_create_response.json()

    status_update_response = client.patch(
        f"/api/v1/pms/project-statuses/{status_item['id']}",
        headers=_auth_headers(admin_session["token"]),
        json={"name": "QA Signoff"},
    )
    assert status_update_response.status_code == 200
    assert status_update_response.json()["name"] == "QA Signoff"
    assert status_update_response.json()["slug"] == status_item["slug"]

    create_space_doc_response = client.post(
        f"/api/v1/pms/spaces/{project['team_id']}/docs",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Space Collection"},
    )
    assert create_space_doc_response.status_code == 201
    space_doc = create_space_doc_response.json()

    missing_query_response = client.get(
        f"/api/v1/pms/spaces/{project['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
    )
    assert missing_query_response.status_code == 400
    assert missing_query_response.json()["detail"] == "space_doc_id is required."

    create_page_response = client.post(
        f"/api/v1/pms/spaces/{project['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Space Page", "space_doc_id": space_doc["id"]},
    )
    assert create_page_response.status_code == 201
    page = create_page_response.json()
    assert page["space_doc_id"] == space_doc["id"]

    create_child_response = client.post(
        f"/api/v1/pms/spaces/{project['team_id']}/docs/pages",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Nested Space Page", "space_doc_id": space_doc["id"], "parent_id": page["id"]},
    )
    assert create_child_response.status_code == 201
    child_page = create_child_response.json()

    list_pages_response = client.get(
        f"/api/v1/pms/spaces/{project['team_id']}/docs/pages",
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
        f"/api/v1/pms/spaces/{project['team_id']}/docs/pages",
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


def test_space_docs_collection_permissions_and_soft_delete(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    project = _create_project(client, admin_session["token"])
    space_id = project["team_id"]
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

    project_editor = _create_user(client, admin_session["token"], email="space-editor@aidoo.local", full_name="Project Editor")
    _add_project_member(client, admin_session["token"], project["id"], project_editor["user"]["id"], "editor")
    project_editor_token = _login(client, project_editor["user"]["email"], project_editor["temporary_password"])

    editor_list_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(project_editor_token),
    )
    assert editor_list_response.status_code == 403

    second_collection_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(project_editor_token),
        json={"title": "Project Notes"},
    )
    assert second_collection_response.status_code == 403

    _add_team_member(client, admin_session["token"], space_id, project_editor["user"]["id"])

    editor_list_after_team_scope_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(project_editor_token),
    )
    assert editor_list_after_team_scope_response.status_code == 200
    assert [item["id"] for item in editor_list_after_team_scope_response.json()["items"]] == [collection["id"]]

    second_collection_response = client.post(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(project_editor_token),
        json={"title": "Project Notes"},
    )
    assert second_collection_response.status_code == 201
    second_collection = second_collection_response.json()

    forbidden_folder_response = client.post(
        "/api/v1/pms/folders",
        headers=_auth_headers(project_editor_token),
        json={"name": "Member cannot manage folders", "team_id": space_id},
    )
    assert forbidden_folder_response.status_code == 403

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
    assert [item["id"] for item in visible_collections_response.json()["items"]] == [second_collection["id"]]

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


def test_project_member_cannot_reach_space_surfaces_without_team_membership(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    project = _create_project(client, admin_session["token"])
    space_id = project["team_id"]
    assert space_id is not None

    issue = _create_issue(client, admin_session["token"], project["id"], title="Project-only issue")

    project_member = _create_user(
        client,
        admin_session["token"],
        email="project-member@aidoo.local",
        full_name="Project Member",
    )
    _add_project_member(client, admin_session["token"], project["id"], project_member["user"]["id"], "editor")
    project_member_token = _login(
        client,
        project_member["user"]["email"],
        project_member["temporary_password"],
    )

    project_detail_response = client.get(
        f"/api/v1/pms/projects/{project['id']}",
        headers=_auth_headers(project_member_token),
    )
    assert project_detail_response.status_code == 200

    project_issue_detail_response = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(project_member_token),
    )
    assert project_issue_detail_response.status_code == 200

    space_lists_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/lists",
        headers=_auth_headers(project_member_token),
    )
    assert space_lists_response.status_code == 403

    space_folders_response = client.get(
        "/api/v1/pms/folders",
        headers=_auth_headers(project_member_token),
        params={"team_id": space_id},
    )
    assert space_folders_response.status_code == 403

    space_docs_response = client.get(
        f"/api/v1/pms/spaces/{space_id}/docs",
        headers=_auth_headers(project_member_token),
    )
    assert space_docs_response.status_code == 403


def test_media_linking_follows_parent_resource_acl(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    project = _create_project(client, admin_session["token"])
    space_id = project["team_id"]
    assert space_id is not None

    issue = _create_issue(client, admin_session["token"], project["id"], title="Media ACL issue")

    doc_response = client.post(
        f"/api/v1/pms/projects/{project['id']}/docs",
        headers=_auth_headers(admin_session["token"]),
        json={"title": "Project Doc", "content_blocks": []},
    )
    assert doc_response.status_code == 201
    doc = doc_response.json()

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
        email="media-project-member@aidoo.local",
        full_name="Media Project Member",
    )
    _add_project_member(client, admin_session["token"], project["id"], project_member["user"]["id"], "editor")
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

    doc_media = _create_unlinked_media(project_member["user"]["id"])
    doc_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(project_member_token),
        json={"media_ids": [doc_media["id"]], "resource_type": "doc", "resource_id": doc["id"]},
    )
    assert doc_link_response.status_code == 204

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
    assert forbidden_space_link_response.status_code == 403

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

    forbidden_doc_media = _create_unlinked_media(space_member["user"]["id"])
    forbidden_doc_link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(space_member_token),
        json={"media_ids": [forbidden_doc_media["id"]], "resource_type": "doc", "resource_id": doc["id"]},
    )
    assert forbidden_doc_link_response.status_code == 403


def test_team_soft_delete_hides_space_data_and_untrashes_default_space(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    headers = _auth_headers(admin_session["token"])
    project = _create_project(client, admin_session["token"])
    space_id = project["team_id"]
    assert space_id is not None

    workspaces_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_response.status_code == 200
    pms_workspace = next(item for item in workspaces_response.json() if item["key"] == "pms")
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
    pms_workspace_after_delete = next(item for item in workspaces_after_delete_response.json() if item["key"] == "pms")
    assert pms_workspace_after_delete["team_count"] == 0

    recreated_project_response = client.post(
        "/api/v1/pms/projects",
        headers=headers,
        json={
            "key": "PMS2",
            "name": "Recovered Project",
            "description": "Project after untrash",
        },
    )
    assert recreated_project_response.status_code == 201
    recreated_project = recreated_project_response.json()
    assert recreated_project["team_id"] == space_id

    teams_after_restore_response = client.get(
        "/api/v1/admin/teams",
        headers=headers,
        params={"workspace_id": pms_workspace["id"]},
    )
    assert teams_after_restore_response.status_code == 200
    assert [item["id"] for item in teams_after_restore_response.json()] == [space_id]

    workspaces_after_restore_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_after_restore_response.status_code == 200
    pms_workspace_after_restore = next(item for item in workspaces_after_restore_response.json() if item["key"] == "pms")
    assert pms_workspace_after_restore["team_count"] == 1


def _bootstrap_admin(client: TestClient) -> str:
    return _bootstrap_admin_session(client)["token"]


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


def _create_project(
    client: TestClient,
    token: str,
    *,
    key: str = "PMS",
    name: str = "PMS Project",
) -> dict:
    response = client.post(
        "/api/v1/pms/projects",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
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
    assignee_id: str | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    recurrence_rule: str | None = None,
) -> dict:
    response = client.post(
        f"/api/v1/pms/projects/{project_id}/issues",
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
    return response.json()


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _add_project_member(client: TestClient, token: str, project_id: str, user_id: str, role: str) -> dict:
    response = client.post(
        f"/api/v1/pms/projects/{project_id}/members",
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
