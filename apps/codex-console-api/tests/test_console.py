import json
from importlib.util import module_from_spec, spec_from_file_location
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import complete, new_task, notify, plan, send_message
from sqlalchemy import select, text

from codex_console import auth
from codex_console.models import Base, PendingRequest, Task, database
from codex_console.runtime import QUESTION


def test_migration_matches_models(settings):
    engine, _ = database(settings.database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "include_object": lambda obj, name, kind, reflected, compare: (
                    name != "console_alembic_version"
                )
            },
        )
        assert compare_metadata(context, Base.metadata) == []
    engine.dispose()


def test_command_output_stream_accepts_native_initial_null_output(client):
    task = send_message(client, new_task(client)).json()
    notify(
        client,
        task,
        "item/started",
        {
            "item": {
                "id": "command",
                "type": "commandExecution",
                "command": "pwd",
                "status": "inProgress",
                "aggregatedOutput": None,
            }
        },
    )
    notify(
        client,
        task,
        "item/commandExecution/outputDelta",
        {"itemId": "command", "delta": "/workspace\n"},
    )
    current = client.get(f"/api/tasks/{task['id']}").json()
    assert current["status"] == "running"
    assert (
        next(item for item in current["items"] if item["id"] == "command")["aggregatedOutput"]
        == "/workspace\n"
    )


def test_turn_provenance_migration_preserves_existing_documents(client):
    from codex_console.cli import ROOT

    task = new_task(client)
    operation_id = str(uuid4())
    task = send_message(client, task, "plan", operation_id=operation_id).json()
    completed = complete(client, task, "Keep the existing approved design")
    spec = spec_from_file_location(
        "revision_turn", ROOT / "migrations/versions/0003_revision_turn.py"
    )
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = client.app.state.factory.kw["bind"]
    # Transactional PostgreSQL DDL keeps this upgrade probe isolated from the
    # shared test schema, even when an assertion fails.
    with engine.connect() as connection, connection.begin() as transaction:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()
        assert (
            connection.scalar(
                text("SELECT current_operation_id FROM console_tasks WHERE id = :id"),
                {"id": task["id"]},
            )
            == operation_id
        )
        revisions = connection.execute(
            text("SELECT body, source_turn_id FROM console_revisions WHERE task_id = :id"),
            {"id": task["id"]},
        ).all()
        assert revisions == [(completed["revisions"][0]["body"], None)]
        transaction.rollback()


def test_authentication_csrf_origin_and_logout(client):
    assert client.get("/api/tasks").status_code == 200
    assert (
        client.post(
            "/api/tasks", json={"title": "Blocked"}, headers={"origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/tasks", json={"title": "Blocked"}, headers={"x-csrf-token": "bad"}
        ).status_code
        == 401
    )
    session = client.cookies[auth.COOKIE]
    assert client.delete("/api/session").status_code == 200
    assert client.get("/api/tasks").status_code == 401
    client.cookies.set(auth.COOKIE, session)
    assert client.get("/api/tasks").status_code == 401


def test_validation_does_not_echo_password(client):
    sentinel = "private-password-do-not-echo"
    result = client.post("/api/session", json={"password": sentinel, "extra": sentinel})
    assert result.status_code == 422
    assert sentinel not in result.text


def test_body_size_boundary(client):
    result = client.post("/api/tasks", content=b"x" * (128 * 1024 + 1))
    assert result.status_code == 413


@pytest.mark.parametrize("character", ["한", "😀"])
@pytest.mark.parametrize("escaped", [False, True])
def test_document_json_supports_full_unicode_character_limit(client, character, escaped):
    task = new_task(client)
    endpoint = f"/api/tasks/{task['id']}/documents"
    body = {"kind": "requirements", "base_version": 0, "body": character * 100000}
    response = client.put(
        endpoint,
        content=json.dumps(body, ensure_ascii=escaped).encode(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["revisions"][-1]["body"] == body["body"]
    body["body"] += character
    assert client.put(endpoint, json=body).status_code == 422
    assert client.put(endpoint, content=b"x" * (100000 * 12 + 4097)).status_code == 413


def test_message_json_supports_escaped_unicode_at_character_limit(client):
    task = new_task(client)
    body = {"operation_id": str(uuid4()), "text": "😀" * 32000}
    assert (
        client.post(
            f"/api/tasks/{task['id']}/messages",
            content=json.dumps(body).encode(),
            headers={"content-type": "application/json"},
        ).status_code
        == 200
    )


def test_detail_cursor_and_projection_share_a_database_snapshot(client, monkeypatch):
    from codex_console import store

    factory = client.app.state.factory
    task = new_task(client)
    before = client.get(f"/api/tasks/{task['id']}").json()
    original = store.require_task

    def commit_between_reads(db, task_id, **kwargs):
        row = original(db, task_id, **kwargs)
        with factory.begin() as writer:
            changed = writer.get(Task, task_id)
            changed.status = "interrupted"
            store.changed(writer, changed, "test.concurrent_change")
        return row

    monkeypatch.setattr(store, "require_task", commit_between_reads)
    during = store.detail(factory, task["id"], client.app.state.settings)
    assert during["status"] == before["status"]
    assert during["event_id"] == before["event_id"]
    monkeypatch.setattr(store, "require_task", original)
    after = store.detail(factory, task["id"], client.app.state.settings)
    assert after["status"] == "interrupted"
    assert after["event_id"] > during["event_id"]


def test_requirements_and_plan_turns_are_read_only(client):
    task = send_message(client, new_task(client)).json()
    rpc = client.app.state.runtime.rpc
    thread = next(params for method, params in rpc.calls if method == "thread/start")
    turn = next(params for method, params in rpc.calls if method == "turn/start")
    assert thread["sandbox"] == "read-only"
    assert thread["config"]["mcp_servers.example.enabled"] is False
    assert turn["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert turn["approvalPolicy"] == "never"
    assert turn["collaborationMode"]["mode"] == "plan"
    result = complete(client, task, "Requirements with acceptance evidence")
    assert result["revisions"][0]["kind"] == "requirements"


def test_implementation_requires_current_plan_and_is_idempotent(client):
    task = plan(client)
    endpoint = f"/api/tasks/{task['id']}/implement"
    body = {"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"] + 1}
    assert client.post(endpoint, json=body).json()["code"] == "stale_plan"
    body["revision_id"] -= 1
    first = client.post(endpoint, json=body)
    assert first.status_code == 200
    assert client.post(endpoint, json=body).status_code == 200
    calls = [p for method, p in client.app.state.runtime.rpc.calls if method == "turn/start"]
    assert len(calls) == 2  # plan + exactly one implementation
    assert calls[-1]["sandboxPolicy"]["type"] == "workspaceWrite"
    assert calls[-1]["approvalPolicy"] == "on-request"
    assert calls[-1]["collaborationMode"]["mode"] == "default"
    assert first.json()["approved_revision"] == body["revision_id"]


def test_modified_requirements_invalidate_plan(client):
    task = plan(client)
    assert (
        client.put(
            f"/api/tasks/{task['id']}/documents",
            json={"kind": "requirements", "base_version": 0, "body": "Changed scope"},
        ).status_code
        == 200
    )
    result = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    )
    assert result.json()["code"] == "stale_plan"


def test_documents_use_optimistic_version_check(client):
    task = plan(client)
    endpoint = f"/api/tasks/{task['id']}/documents"
    body = {"kind": "plan", "base_version": 1, "body": "Revised plan"}
    assert client.put(endpoint, json=body).status_code == 200
    assert client.put(endpoint, json=body).json()["code"] == "stale_document"


def test_task_search_reaches_older_isolated_tasks_beyond_recent_limit(client, repository):
    from datetime import UTC, datetime

    with client.app.state.factory.begin() as db:
        old = Task(
            title="Archived 100%_done",
            root=str(repository.parent / "worktrees" / "archive"),
            worktree_owned=True,
            updated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        db.add(old)
        db.add_all(Task(title=f"Recent {i}", root=str(repository)) for i in range(201))
        db.flush()
        old_id = old.id
    recent = client.get("/api/tasks").json()
    assert len(recent) == 200
    assert old_id not in {row["id"] for row in recent}
    found = client.get("/api/tasks", params={"search": "ARCHIVED 100%_done"}).json()
    assert [row["id"] for row in found] == [old_id]
    assert client.get("/api/tasks", params={"search": "x" * 201}).status_code == 422


def test_identical_regenerated_plan_can_approve_new_requirements(client):
    task = plan(client)
    previous = task["revisions"][-1]
    endpoint = f"/api/tasks/{task['id']}"
    assert (
        client.put(
            endpoint + "/documents",
            json={"kind": "requirements", "base_version": 0, "body": "Clarified scope"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            endpoint + "/implement",
            json={"operation_id": str(uuid4()), "revision_id": previous["id"]},
        ).json()["code"]
        == "stale_plan"
    )
    task = send_message(client, task, "plan").json()
    task = complete(client, task, previous["body"])
    revised = [row for row in task["revisions"] if row["kind"] == "plan"][-1]
    assert revised["version"] == previous["version"] + 1
    assert revised["body"] == previous["body"]
    assert revised["created_at"] > previous["created_at"]
    assert (
        client.post(
            endpoint + "/implement",
            json={"operation_id": str(uuid4()), "revision_id": revised["id"]},
        ).status_code
        == 200
    )


def test_workspace_lease_prevents_parallel_turns(client):
    first, second = new_task(client), new_task(client)
    running = send_message(client, first).json()
    assert send_message(client, second).json()["code"] == "workspace_busy"
    complete(client, running)
    assert send_message(client, second).status_code == 200


def test_cannot_supply_execution_paths_permissions_or_provider(client):
    task = new_task(client)
    body = {"text": "Hello", "operation_id": str(uuid4()), "stage": "implement", "cwd": "/"}
    assert client.post(f"/api/tasks/{task['id']}/messages", json=body).status_code == 422


def test_api_key_authentication_cannot_start_a_turn(client):
    client.get("/api/codex/account")
    client.app.state.runtime.rpc.auth_type = "apiKey"
    assert send_message(client, new_task(client)).json()["code"] == "login_required"


def test_console_inherits_native_thread_model_without_choosing_a_route(client, monkeypatch):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    original = rpc.call

    async def native_model(method, params):
        result = await original(method, params)
        if method in ("thread/start", "thread/resume"):
            result["model"] = "native-session-model"
        return result

    monkeypatch.setattr(rpc, "call", native_model)
    assert send_message(client, new_task(client)).status_code == 200
    thread = next(params for method, params in rpc.calls if method == "thread/start")
    turn = next(params for method, params in rpc.calls if method == "turn/start")
    for params in (thread, turn):
        assert not {"model", "modelProvider", "provider", "apiKey"}.intersection(params)
    assert turn["collaborationMode"]["settings"]["model"] == "native-session-model"


def test_questions_require_exact_live_task_and_turn(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(
        runtime.on_message,
        {
            "id": 73,
            "method": QUESTION,
            "params": {
                "threadId": task["thread_id"],
                "turnId": task["turn_id"],
                "itemId": "question-1",
                "questions": [
                    {"id": "choice", "header": "Scope", "question": "Which scope?", "options": []}
                ],
            },
        },
    )
    detail = client.get(f"/api/tasks/{task['id']}").json()
    request_id = detail["requests"][0]["id"]
    other = new_task(client)
    assert (
        client.post(
            f"/api/tasks/{other['id']}/requests/{request_id}",
            json={"answers": {"choice": ["Small"]}},
        ).status_code
        == 409
    )
    endpoint = f"/api/tasks/{task['id']}/requests/{request_id}"
    assert client.post(endpoint, json={"answers": {"unexpected": ["Small"]}}).status_code == 422
    assert client.post(endpoint, json={"answers": {"choice": ["Small"]}}).status_code == 200
    assert runtime.rpc.responses[-1] == (73, {"answers": {"choice": {"answers": ["Small"]}}})
    assert client.post(endpoint, json={"answers": {"choice": ["Small"]}}).status_code == 409


def test_planning_cannot_approve_writes(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(
        runtime.on_message,
        {
            "id": 8,
            "method": "item/fileChange/requestApproval",
            "params": {"threadId": task["thread_id"], "turnId": task["turn_id"], "itemId": "write"},
        },
    )
    assert runtime.rpc.responses[-1] == (8, {"decision": "decline"})
    assert not client.get(f"/api/tasks/{task['id']}").json()["requests"]


def test_approval_does_not_allow_session_wide_grants(client):
    task = plan(client)
    task = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    ).json()
    runtime = client.app.state.runtime
    client.portal.call(
        runtime.on_message,
        {
            "id": 9,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": task["thread_id"],
                "turnId": task["turn_id"],
                "itemId": "cmd",
                "command": "test",
            },
        },
    )
    detail = client.get(f"/api/tasks/{task['id']}").json()
    request_id = detail["requests"][0]["id"]
    endpoint = f"/api/tasks/{task['id']}/requests/{request_id}"
    assert client.post(endpoint, json={"decision": "acceptForSession"}).status_code == 422
    assert client.post(endpoint, json={"decision": "accept"}).status_code == 200
    assert runtime.rpc.responses[-1] == (9, {"decision": "accept"})


def test_disconnect_is_uncertain_and_never_replays(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert detail["status"] == "uncertain"
    assert send_message(client, detail).json()["code"] == "task_busy"
    assert client.post(f"/api/tasks/{task['id']}/recover", json={}).status_code == 200
    assert len([x for x in runtime.rpc.calls if x[0] == "turn/start"]) == 1


def test_permissions_are_denied_in_plan_and_scoped_to_approved_turn(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime

    def permission_request(task, rpc_id):
        client.portal.call(
            runtime.on_message,
            {
                "id": rpc_id,
                "method": "item/permissions/requestApproval",
                "params": {
                    "threadId": task["thread_id"],
                    "turnId": task["turn_id"],
                    "itemId": "permissions",
                    "permissions": {"network": {"enabled": True}},
                },
            },
        )

    permission_request(task, 41)
    assert runtime.rpc.responses[-1] == (41, {"permissions": {}, "scope": "turn"})
    complete(client, task)
    task = plan(client)
    task = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    ).json()
    permission_request(task, 42)
    pending = client.get(f"/api/tasks/{task['id']}").json()["requests"][0]
    endpoint = f"/api/tasks/{task['id']}/requests/{pending['id']}"
    assert client.post(endpoint, json={"decision": "accept", "scope": "session"}).status_code == 422
    assert client.post(endpoint, json={"decision": "accept"}).status_code == 200
    assert runtime.rpc.responses[-1] == (
        42,
        {"permissions": {"network": {"enabled": True}}, "scope": "turn", "strictAutoReview": True},
    )


def test_ambiguous_start_keeps_lease_until_explicit_recovery(client):
    client.get("/api/codex/account")
    runtime = client.app.state.runtime
    runtime.rpc.fail_turn = True
    task = new_task(client)
    response = send_message(client, task)
    assert response.status_code == 503
    assert client.get(f"/api/tasks/{task['id']}").json()["status"] == "uncertain"
    runtime.rpc.fail_turn = False
    assert send_message(client, new_task(client)).json()["code"] == "workspace_busy"


def test_delta_and_final_plan_are_projected_from_official_items(client):
    task = send_message(client, new_task(client), "plan").json()
    notify(client, task, "item/started", {"item": {"id": "plan-item", "type": "plan", "text": ""}})
    notify(client, task, "item/plan/delta", {"itemId": "plan-item", "delta": "partial"})
    assert client.get(f"/api/tasks/{task['id']}").json()["items"][-1]["text"] == "partial"
    result = complete(client, task, "authoritative final plan")
    assert result["revisions"][-1]["body"] == "authoritative final plan"


def test_completion_expires_unanswered_questions(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    with client.app.state.factory.begin() as db:
        db.add(
            PendingRequest(
                task_id=task["id"],
                turn_id=task["turn_id"],
                rpc_id=json.dumps(1),
                generation=runtime.rpc.generation,
                method=QUESTION,
                payload={},
            )
        )
    result = complete(client, task, status="interrupted")
    assert not result["requests"]
    assert result["status"] == "interrupted"


def test_dirty_dev_is_preserved_in_isolated_worktree(client, repository):
    task = plan(client)
    (repository / "hello.txt").write_text("unrelated edit\n")
    result = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    )
    assert result.status_code == 200
    assert result.json()["isolated"] is True
    assert (repository / "hello.txt").read_text() == "unrelated edit\n"
    assert result.json()["root"] != str(repository)


def test_current_task_dirty_changes_can_continue_but_external_edits_cannot(client, repository):
    task = plan(client)
    revision = task["revisions"][-1]["id"]
    endpoint = f"/api/tasks/{task['id']}/implement"
    task = client.post(
        endpoint, json={"operation_id": str(uuid4()), "revision_id": revision}
    ).json()
    (repository / "hello.txt").write_text("task change\n")
    task = complete(client, task)
    assert task["status"] == "idle"
    (repository / "hello.txt").write_text("external change\n")
    assert (
        client.post(endpoint, json={"operation_id": str(uuid4()), "revision_id": revision}).json()[
            "code"
        ]
        == "workspace_changed"
    )


def test_diff_blocks_secrets_and_symlink_escape(client, repository, tmp_path):
    task = new_task(client)
    (repository / ".env").write_text("SENSITIVE=hidden")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    (repository / "link.txt").symlink_to(outside)
    (repository / "hello.txt").write_text("changed\n")
    rows = client.get(f"/api/tasks/{task['id']}/changes").json()
    assert [row["path"] for row in rows] == ["hello.txt"]
    result = client.get(f"/api/tasks/{task['id']}/diff", params={"path": "hello.txt"}).json()
    assert result["old"] == "hello\n" and result["new"] == "changed\n"
    assert (
        client.get(f"/api/tasks/{task['id']}/diff", params={"path": "../outside.txt"}).status_code
        != 200
    )


def test_untracked_file_boundaries_are_included_in_workspace_fingerprint(repository):
    from codex_console.git import fingerprint

    (repository / "a.txt").write_bytes(b"a")
    (repository / "b.txt").write_bytes(b"bc")
    previous = fingerprint(repository)
    (repository / "a.txt").write_bytes(b"ab")
    (repository / "b.txt").write_bytes(b"c")
    assert fingerprint(repository) != previous


def test_failed_turn_never_becomes_success(client):
    task = send_message(client, new_task(client)).json()
    result = complete(client, task, status="failed")
    assert result["status"] == "failed"
    assert not result["revisions"]


def test_web_logout_does_not_log_out_codex(client):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    client.delete("/api/session")
    assert not any(method == "account/logout" for method, _ in rpc.calls)


def test_import_cannot_read_another_checkout(client, tmp_path):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    rpc.threads["outside"] = {"id": "outside", "cwd": str(tmp_path), "turns": []}
    assert (
        client.post(
            "/api/tasks/import", json={"thread_id": "outside", "confirm_inactive": True}
        ).status_code
        == 403
    )


def test_startup_recovery_retains_uncertain_work(client):
    from codex_console.store import recover_startup

    task = send_message(client, new_task(client)).json()
    recover_startup(client.app.state.factory)
    with client.app.state.factory() as db:
        saved = db.scalar(select(Task).where(Task.id == task["id"]))
        assert saved.status == "uncertain"


def test_session_cookie_is_http_only(client):
    from conftest import PASSWORD

    response = client.post("/api/session", json={"password": PASSWORD})
    cookies = response.headers.get_list("set-cookie")
    assert any(
        auth.COOKIE in value and "HttpOnly" in value and "SameSite=strict" in value
        for value in cookies
    )


def test_proxy_base_path_scopes_cookies_and_api_cache_headers(client):
    from conftest import PASSWORD

    client.app.state.settings.base_path = "/codex-console"
    client.app.root_path = "/codex-console"
    response = client.post("/codex-console/api/session", json={"password": PASSWORD})
    assert response.status_code == 200
    assert all(
        "Path=/codex-console" in cookie
        for cookie in response.headers.get_list("set-cookie")
        if "Max-Age=0" not in cookie
    )
    assert response.headers["cache-control"] == "no-store"
    csrf = next(
        c.value
        for c in client.cookies.jar
        if c.name == auth.CSRF_COOKIE and c.path == "/codex-console"
    )
    response = client.delete("/codex-console/api/session", headers={"x-csrf-token": csrf})
    assert response.status_code == 200
    assert all(
        "Path=/codex-console" in cookie for cookie in response.headers.get_list("set-cookie")
    )
