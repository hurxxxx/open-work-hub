import json
from importlib.util import module_from_spec, spec_from_file_location
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import complete, new_task, notify, plan, planning_text, send_message
from sqlalchemy import select, text

from codex_console import auth, store
from codex_console.models import Base, PendingRequest, Revision, Task, database
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
            current_spec = spec_from_file_location(
                "planning_migration", ROOT / "migrations/versions/0005_planning.py"
            )
            current = module_from_spec(current_spec)
            current_spec.loader.exec_module(current)
            current.downgrade()
            migration.downgrade()
            migration.upgrade()
            current.upgrade()
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


def test_open_work_hub_handoff_creates_console_session(client, monkeypatch):
    from codex_console import owh_sso

    assert client.delete("/api/session").status_code == 200
    owner_subject = UUID("11111111-1111-4111-8111-111111111111")
    client.app.state.settings.sso_subjects = {
        "https://dev.example.test": owner_subject,
    }
    exchange = monkeypatch.setattr(
        owh_sso,
        "exchange_code",
        lambda **values: str(owner_subject)
        if values
        == {"issuer": "https://dev.example.test", "code": "cc1_" + "a" * 32}
        else None,
    )
    assert exchange is None

    response = client.post(
        "/api/session/owh",
        json={"issuer": "https://dev.example.test", "code": "cc1_" + "a" * 32},
    )
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    assert client.get("/api/tasks").status_code == 200


def test_open_work_hub_handoff_fails_closed(client, monkeypatch):
    from codex_console import owh_sso

    assert client.delete("/api/session").status_code == 200
    client.app.state.settings.sso_subjects = {}
    monkeypatch.setattr(
        owh_sso,
        "exchange_code",
        lambda **values: pytest.fail("an unconfigured issuer must not be contacted"),
    )
    response = client.post(
        "/api/session/owh",
        json={"issuer": "https://evil.example", "code": "cc1_" + "a" * 32},
    )
    assert response.status_code == 401
    assert response.json() == {"code": "login_failed"}
    assert client.get("/api/tasks").status_code == 401


def test_open_work_hub_handoff_rejects_a_different_user(client, monkeypatch):
    from codex_console import owh_sso

    assert client.delete("/api/session").status_code == 200
    client.app.state.settings.sso_subjects = {
        "https://dev.example.test": UUID("11111111-1111-4111-8111-111111111111"),
    }
    monkeypatch.setattr(
        owh_sso,
        "exchange_code",
        lambda **values: "22222222-2222-4222-8222-222222222222",
    )

    response = client.post(
        "/api/session/owh",
        json={"issuer": "https://dev.example.test", "code": "cc1_" + "a" * 32},
    )
    assert response.status_code == 401
    assert response.json() == {"code": "login_failed"}
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
    body = {"base_version": 0, "body": character * 100000}
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


def test_native_plan_turns_are_read_only_and_project_the_final_plan(client):
    task = send_message(client, new_task(client)).json()
    rpc = client.app.state.runtime.rpc
    thread = next(params for method, params in rpc.calls if method == "thread/start")
    turn = next(params for method, params in rpc.calls if method == "turn/start")
    assert thread["sandbox"] == "read-only"
    assert thread["config"]["mcp_servers.example.enabled"] is False
    assert turn["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert turn["approvalPolicy"] == "never"
    assert turn["collaborationMode"]["mode"] == "plan"
    result = complete(
        client,
        task,
        "<proposed_plan>\nPlan with acceptance evidence\n</proposed_plan>",
    )
    assert result["revisions"][0]["kind"] == "plan"
    assert result["revisions"][0]["body"] == "Plan with acceptance evidence"
    assert result["items"][-1]["text"] == "Plan with acceptance evidence"
    assert "outputSchema" not in turn
    assert "planning" not in turn["additionalContext"]
    updated = send_message(client, result, text="Refine the saved plan").json()
    assert updated["status"] == "running"
    resumed = [params for method, params in rpc.calls if method == "turn/start"][-1]
    assert json.loads(resumed["additionalContext"]["saved_plan"]["value"]) == {
        "version": 1,
        "body": "Plan with acceptance evidence",
    }


def test_existing_wrapped_plan_is_unwrapped_for_display_and_execution(client):
    task = plan(client)
    with client.app.state.factory.begin() as db:
        revision = db.get(Revision, task["revisions"][-1]["id"])
        revision.body = "<proposed_plan>\nRecovered plan\n</proposed_plan>"
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert detail["revisions"][-1]["body"] == "Recovered plan"
    response = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": revision.id},
    )
    assert response.status_code == 200
    params = [
        params for method, params in client.app.state.runtime.rpc.calls if method == "turn/start"
    ][-1]
    assert params["additionalContext"]["approved_plan"]["value"] == "Recovered plan"


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


def test_retired_requirements_do_not_invalidate_the_native_plan(client):
    task = plan(client)
    with client.app.state.factory.begin() as db:
        row = db.get(Task, task["id"])
        store.save_revision(db, row, "requirements", "Legacy scope")
    assert [row["kind"] for row in client.get(f"/api/tasks/{task['id']}").json()["revisions"]] == [
        "plan"
    ]
    result = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    )
    assert result.status_code == 200


def test_documents_use_optimistic_version_check(client):
    task = plan(client)
    endpoint = f"/api/tasks/{task['id']}/documents"
    body = {"base_version": 1, "body": "Revised plan"}
    assert client.put(endpoint, json=body).status_code == 200
    assert client.put(endpoint, json=body).json()["code"] == "stale_document"


def test_document_endpoint_accepts_the_previous_plan_payload_but_rejects_requirements(client):
    endpoint = f"/api/tasks/{new_task(client)['id']}/documents"
    body = {"kind": "plan", "base_version": 0, "body": "Compatible plan"}
    assert client.put(endpoint, json=body).status_code == 200
    body.update(kind="requirements", base_version=1)
    assert client.put(endpoint, json=body).status_code == 422


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


def test_identical_native_plan_is_saved_as_a_new_authoritative_version(client):
    task = plan(client)
    previous = task["revisions"][-1]
    endpoint = f"/api/tasks/{task['id']}"
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


def test_auto_review_configuration_cannot_replace_console_owner_approval(client, monkeypatch):
    client.get("/api/codex/account")
    runtime = client.app.state.runtime
    rpc = runtime.rpc
    original = rpc.call
    reviewers = []

    async def configured_auto_review(method, params):
        result = await original(method, params)
        if method == "config/read":
            result["config"]["approvals_reviewer"] = "auto_review"
        if method in ("thread/start", "thread/resume", "turn/start"):
            reviewers.append((method, params.get("approvalsReviewer", "auto_review")))
        return result

    monkeypatch.setattr(rpc, "call", configured_auto_review)
    task = plan(client)
    task = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    ).json()
    assert {method for method, _ in reviewers} == {"thread/start", "thread/resume", "turn/start"}
    assert all(reviewer == "user" for _, reviewer in reviewers)
    client.portal.call(
        runtime.on_message,
        {
            "id": 71,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": task["thread_id"],
                "turnId": task["turn_id"],
                "itemId": "command",
            },
        },
    )
    pending = client.get(f"/api/tasks/{task['id']}").json()
    assert pending["status"] == "waiting"
    assert len(pending["requests"]) == 1
    assert rpc.responses == []
    assert (
        client.post(
            f"/api/tasks/{task['id']}/requests/{pending['requests'][0]['id']}",
            json={"decision": "accept"},
        ).status_code
        == 200
    )
    assert rpc.responses == [(71, {"decision": "accept"})]


def test_console_inherits_native_thread_model_without_choosing_a_route(client, monkeypatch):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    original = rpc.call

    async def native_model(method, params):
        result = await original(method, params)
        if method in ("thread/start", "thread/resume"):
            result["model"] = "native-session-model"
        if method == "model/list":
            result["data"][0]["model"] = "native-session-model"
        return result

    monkeypatch.setattr(rpc, "call", native_model)
    assert send_message(client, new_task(client)).status_code == 200
    thread = next(params for method, params in rpc.calls if method == "thread/start")
    turn = next(params for method, params in rpc.calls if method == "turn/start")
    for params in (thread, turn):
        assert not {"modelProvider", "provider", "apiKey"}.intersection(params)
    assert "model" not in thread
    assert turn["model"] == "native-session-model"
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
    assert len([x for x in runtime.rpc.calls if x[0] == "turn/start"]) == 1
    assert send_message(client, detail, text="Continue the unfinished work").status_code == 200
    assert len([x for x in runtime.rpc.calls if x[0] == "turn/start"]) == 2


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
    notify(
        client,
        task,
        "item/completed",
        {"item": {"id": "plan-item", "type": "plan", "text": "authoritative final plan"}},
    )
    notify(client, task, "turn/completed", {"turn": {"id": task["turn_id"], "status": "completed"}})
    result = client.get(f"/api/tasks/{task['id']}").json()
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


def test_previous_execution_migration_preserves_existing_tasks_and_documents(client):
    from codex_console.cli import ROOT

    task = complete(client, send_message(client, new_task(client)).json())
    spec = spec_from_file_location(
        "previous_execution", ROOT / "migrations/versions/0006_previous_execution.py"
    )
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = client.app.state.factory.kw["bind"]
    with engine.connect() as connection, connection.begin() as transaction:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()
        row = connection.execute(
            text(
                "SELECT permissions, previous_permissions, previous_execution_root "
                "FROM console_tasks WHERE id = :id"
            ),
            {"id": task["id"]},
        ).one()
        assert row == ("read-only", None, None)
        assert (
            connection.scalar(
                text("SELECT body FROM console_revisions WHERE task_id = :id"), {"id": task["id"]}
            )
            == task["revisions"][0]["body"]
        )
        transaction.rollback()


def test_native_plan_migration_backfills_a_missing_structured_plan(client):
    from codex_console.cli import ROOT

    task = plan(client)
    spec = spec_from_file_location(
        "native_plans", ROOT / "migrations/versions/0007_native_plans.py"
    )
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = client.app.state.factory.kw["bind"]
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text("DELETE FROM console_revisions WHERE task_id = :id"), {"id": task["id"]}
        )
        connection.execute(
            text(
                "UPDATE console_items SET payload = CAST(:payload AS json) "
                "WHERE task_id = :id AND payload->>'type' = 'plan'"
            ),
            {
                "id": task["id"],
                "payload": json.dumps(
                    {
                        "id": "native-plan",
                        "type": "plan",
                        "text": planning_text("Recovered native plan", []),
                    }
                ),
            },
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        revisions = connection.execute(
            text(
                "SELECT kind, version, body FROM console_revisions "
                "WHERE task_id = :id ORDER BY id"
            ),
            {"id": task["id"]},
        ).all()
        assert revisions == [("plan", 1, "Recovered native plan")]
        transaction.rollback()


def test_legacy_plan_answer_migration_requires_an_accepted_plan_operation(client):
    from codex_console.cli import ROOT

    operation_id = str(uuid4())
    task = send_message(
        client, new_task(client), "plan", operation_id=operation_id
    ).json()
    turn_id = task["turn_id"]
    task = complete(
        client,
        task,
        "<proposed_plan>\nRecovered legacy answer\n</proposed_plan>",
        documents=[],
    )
    assert task["revisions"] == []
    spec = spec_from_file_location(
        "legacy_plan_answers", ROOT / "migrations/versions/0008_legacy_plan_answers.py"
    )
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = client.app.state.factory.kw["bind"]
    with engine.connect() as connection, connection.begin() as transaction:
        connection.execute(
            text(
                "INSERT INTO console_items (task_id, item_id, turn_id, payload) "
                "VALUES (:task_id, :item_id, :turn_id, CAST(:payload AS json))"
            ),
            {
                "task_id": task["id"],
                "item_id": str(uuid4()),
                "turn_id": turn_id,
                "payload": json.dumps(
                    {"id": str(uuid4()), "type": "userMessage", "clientId": operation_id}
                ),
            },
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        revisions = connection.execute(
            text(
                "SELECT kind, version, body FROM console_revisions "
                "WHERE task_id = :id ORDER BY id"
            ),
            {"id": task["id"]},
        ).all()
        assert revisions == [("plan", 1, "Recovered legacy answer")]
        transaction.rollback()
