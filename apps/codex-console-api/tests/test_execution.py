import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from conftest import complete, new_task, notify, plan, send_message
from sqlalchemy import text

from codex_console.cli import ROOT
from codex_console.rpc import CodexRPC


def test_account_model_catalog_follows_native_pagination(client, monkeypatch):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    original = rpc.call

    async def paginated(method, params):
        result = await original(method, params)
        if method == "model/list":
            result["data"] = [result["data"][1 if params["cursor"] else 0]]
            result["nextCursor"] = None if params["cursor"] else "page-2"
        return result

    monkeypatch.setattr(rpc, "call", paginated)
    result = client.get("/api/codex/models")
    assert result.status_code == 200
    assert [row["model"] for row in result.json()] == ["account-default", "another-model"]
    assert result.json()[1]["efforts"] == ["low", "medium", "high"]
    assert client.delete("/api/session").status_code == 200
    assert client.get("/api/codex/models").status_code == 401


def test_task_model_catalog_uses_the_effective_codex_config(client):
    task = new_task(client)
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    rpc.config_model = "another-model"
    rpc.config_effort = "high"
    response = client.get(f"/api/codex/models?task_id={task['id']}")
    assert response.status_code == 200
    selected = [row for row in response.json() if row["is_default"]]
    assert [(row["model"], row["default_effort"]) for row in selected] == [
        ("another-model", "high")
    ]
    assert [
        row["model"] for row in client.get("/api/codex/models").json() if row["is_default"]
    ] == ["account-default"]


def test_unselected_model_follows_the_native_thread_after_a_user_change(client):
    task = new_task(client)
    path = f"/api/tasks/{task['id']}/messages"
    first = client.post(
        path,
        json={"operation_id": str(uuid4()), "text": "Inspect", "model": "another-model"},
    )
    assert first.status_code == 200
    assert first.json()["model"] == "another-model"
    complete(client, first.json())
    second = client.post(path, json={"operation_id": str(uuid4()), "text": "Continue"})
    assert second.status_code == 200
    assert second.json()["model"] == "another-model"


def test_retired_native_model_falls_back_to_the_available_catalog_default(client):
    task = new_task(client)
    client.get("/api/codex/account")
    client.app.state.runtime.rpc.config_model = "retired-model"
    result = client.post(
        f"/api/tasks/{task['id']}/messages",
        json={"operation_id": str(uuid4()), "text": "Inspect"},
    )
    assert result.status_code == 200
    assert result.json()["model"] == "account-default"


def test_selected_model_effort_and_yolo_are_scoped_to_approved_implementation(client):
    task = plan(client)
    body = {
        "operation_id": str(uuid4()),
        "revision_id": task["revisions"][-1]["id"],
        "text": "Continue the remaining work",
        "model": "another-model",
        "effort": "high",
        "permissions": "yolo",
    }
    path = f"/api/tasks/{task['id']}/implement"
    result = client.post(path, json=body)
    assert result.status_code == 200
    detail = result.json()
    assert (detail["model"], detail["effort"], detail["permissions"]) == (
        "another-model",
        "high",
        "yolo",
    )
    rpc = client.app.state.runtime.rpc
    params = [params for method, params in rpc.calls if method == "turn/start"][-1]
    assert params["model"] == "another-model"
    assert params["effort"] == "high"
    assert params["collaborationMode"]["mode"] == "default"
    assert params["collaborationMode"]["settings"]["model"] == "another-model"
    assert params["sandboxPolicy"] == {"type": "dangerFullAccess"}
    assert params["approvalPolicy"] == "never"
    assert params["approvalsReviewer"] == "user"
    assert params["input"][0]["text"] == body["text"]
    assert params["additionalContext"]["approved_plan"]["value"] == task["revisions"][-1]["body"]
    assert client.post(path, json=body).status_code == 200
    assert client.post(path, json={**body, "permissions": "ask"}).status_code == 409
    assert len([x for x in rpc.calls if x[0] == "turn/start"]) == 2
    complete(client, detail)
    result = client.post(
        f"/api/tasks/{task['id']}/messages",
        json={
            "operation_id": str(uuid4()),
            "text": "Revise the plan",
            "stage": "plan",
            "permissions": "yolo",
            "model": "another-model",
        },
    )
    assert result.status_code == 200
    params = [params for method, params in rpc.calls if method == "turn/start"][-1]
    assert result.json()["permissions"] == "read-only"
    assert params["sandboxPolicy"]["type"] == "readOnly"
    assert params["collaborationMode"]["mode"] == "plan"


@pytest.mark.parametrize(
    "options", [{"model": "missing"}, {"model": "another-model", "effort": "unsupported"}]
)
def test_invalid_native_options_never_submit_a_turn_and_release_the_workspace(client, options):
    task = new_task(client)
    path = f"/api/tasks/{task['id']}/messages"
    body = {"operation_id": str(uuid4()), "text": "Inspect", **options}
    assert client.post(path, json=body).status_code == 422
    rpc = client.app.state.runtime.rpc
    assert not any(method == "turn/start" for method, _ in rpc.calls)
    assert send_message(client, new_task(client)).status_code == 200


def test_native_progress_is_durable_and_ignores_other_turns(client):
    task = send_message(client, new_task(client)).json()
    steps = [
        {"step": "Inspect files", "status": "completed"},
        {"step": "Run checks", "status": "inProgress"},
    ]
    notify(client, task, "turn/plan/updated", {"plan": steps, "explanation": "Checking behavior"})
    saved = client.get(f"/api/tasks/{task['id']}").json()
    assert saved["progress"] == {
        "turn_id": task["turn_id"],
        "explanation": "Checking behavior",
        "steps": steps,
    }
    notify(client, task, "turn/plan/updated", {"turnId": "old-turn", "plan": []})
    assert client.get(f"/api/tasks/{task['id']}").json()["progress"] == saved["progress"]
    complete(client, task)
    assert send_message(client, task).json()["progress"] is None


def test_recovery_continues_same_native_thread_and_preserves_partial_files(client):
    task = plan(client)
    path = f"/api/tasks/{task['id']}"
    task = client.post(
        path + "/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": task["revisions"][-1]["id"],
        },
    ).json()
    root, thread = task["root"], task["thread_id"]
    (Path(root) / "partial.txt").write_text("completed before disconnect\n")
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect, "codex_event_failed")
    assert client.get(path).json()["error_code"] == "codex_event_failed"
    assert client.post(path + "/recover", json={}).status_code == 409
    assert client.post(path + "/recover", json={"confirm_workspace": True}).status_code == 200
    continued = client.post(
        path + "/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": task["revisions"][-1]["id"],
            "text": "Check completed work and finish the remaining steps",
        },
    ).json()
    assert (continued["root"], continued["thread_id"]) == (root, thread)
    assert (Path(root) / "partial.txt").read_text() == "completed before disconnect\n"
    assert continued["status"] == "running"


def test_obsolete_transport_cannot_mark_new_execution_disconnected(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime

    async def old_messages():
        await runtime.on_disconnect("codex_event_failed", generation="old-process")
        await runtime.on_message(
            {
                "method": "turn/completed",
                "params": {
                    "threadId": task["thread_id"],
                    "turn": {"id": task["turn_id"], "status": "failed"},
                },
            },
            generation="old-process",
        )

    client.portal.call(old_messages)
    assert client.get(f"/api/tasks/{task['id']}").json()["status"] == "running"


def test_transport_failure_stops_once_and_logs_no_event_content(caplog):
    async def scenario():
        reasons = []

        async def handler(message):
            raise TypeError("SENSITIVE-EVENT-CONTENT")

        async def disconnected(reason):
            reasons.append(reason)

        rpc = CodexRPC("unused", Path("/"), handler, disconnected)
        rpc.process = SimpleNamespace(returncode=None, terminate=Mock())
        await rpc.events.put(
            {"method": "item/commandExecution/outputDelta", "params": {"delta": "PRIVATE"}}
        )
        await rpc._dispatch()
        await rpc._failed("codex_disconnected")
        assert reasons == ["codex_event_failed"]
        assert not rpc.connected
        rpc.process.terminate.assert_called_once()

    asyncio.run(scenario())
    assert "codex_event_failed" in caplog.text
    assert "TypeError" in caplog.text
    assert "SENSITIVE-EVENT-CONTENT" not in caplog.text
    assert "PRIVATE" not in caplog.text


def test_transport_output_limit_has_a_distinct_diagnostic():
    async def scenario():
        reasons = []

        async def disconnected(reason):
            reasons.append(reason)

        rpc = CodexRPC("unused", Path("/"), None, disconnected)
        stream = asyncio.StreamReader(limit=8)
        stream.feed_data(b"x" * 40 + b"\n")
        rpc.process = SimpleNamespace(returncode=None, terminate=Mock(), stdout=stream)
        await rpc._read()
        assert reasons == ["codex_output_limit"]

    asyncio.run(scenario())


def test_execution_migration_preserves_approved_tasks_without_enabling_yolo(client):
    task = plan(client)
    task = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": task["revisions"][-1]["id"],
        },
    ).json()
    spec = spec_from_file_location(
        "execution_settings", ROOT / "migrations/versions/0004_execution_settings.py"
    )
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = client.app.state.factory.kw["bind"]
    with engine.connect() as connection, connection.begin() as transaction:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()
        row = connection.execute(
            text("SELECT thread_id, permissions, effort, progress FROM console_tasks WHERE id=:id"),
            {"id": task["id"]},
        ).one()
        assert row == (task["thread_id"], "ask", None, None)
        transaction.rollback()


def test_disconnect_is_recorded_for_its_task_even_when_account_reconnected_first(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime

    async def scenario():
        async with runtime.gate:
            old = runtime.rpc
            disconnected = asyncio.create_task(
                runtime.on_disconnect("codex_disconnected", generation=old.generation)
            )
            old.connected = False
            await runtime.connect()
            assert runtime.rpc.generation != old.generation
        await disconnected

    client.portal.call(scenario)
    assert client.get(f"/api/tasks/{task['id']}").json()["status"] == "uncertain"


def test_transport_teardown_does_not_cancel_queued_durable_disconnect():
    async def scenario():
        entered, release, recorded = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def disconnected(reason):
            entered.set()
            await release.wait()
            recorded.set()

        rpc = CodexRPC("unused", Path("/"), None, disconnected)
        rpc.process = SimpleNamespace(returncode=None, terminate=Mock())
        reporting = asyncio.create_task(rpc._failed("codex_disconnected"))
        await entered.wait()
        reporting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reporting
        release.set()
        await asyncio.wait_for(recorded.wait(), 1)
        await rpc.failure_task

    asyncio.run(scenario())


def test_active_turn_settings_cannot_be_silently_changed_by_steering(client):
    task = send_message(client, new_task(client)).json()
    result = client.post(
        f"/api/tasks/{task['id']}/steer",
        json={
            "operation_id": str(uuid4()),
            "text": "Continue",
            "permissions": "yolo",
        },
    )
    assert result.status_code == 422
    assert not any(method == "turn/steer" for method, _ in client.app.state.runtime.rpc.calls)
