import asyncio
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import complete, new_task, plan, send_message
from sqlalchemy import event, select

from codex_console import attachments, git, store
from codex_console.errors import ConsoleError
from codex_console.models import MessageAttachment, Operation, Task, WorkspaceLease


def test_pre_submission_failure_can_retry_same_request_and_attachment(client, monkeypatch):
    task = new_task(client)
    runtime = client.app.state.runtime
    file_id, operation_id = str(uuid4()), str(uuid4())
    assert (
        client.put(
            f"/api/tasks/{task['id']}/attachments/{file_id}",
            content=b"reference",
            headers={"x-file-name": "reference.bin", "content-type": "application/octet-stream"},
        ).status_code
        == 200
    )
    original = runtime.ensure_thread

    async def unavailable(*args):
        raise ConsoleError("codex_unavailable", 503)

    monkeypatch.setattr(runtime, "ensure_thread", unavailable)
    body = {"operation_id": operation_id, "text": "Use the reference", "attachment_ids": [file_id]}
    endpoint = f"/api/tasks/{task['id']}/messages"
    assert client.post(endpoint, json=body).status_code == 503
    with client.app.state.factory() as db:
        assert db.get(Operation, operation_id).state == "failed"
        assert db.get(WorkspaceLease, 1).task_id is None
    monkeypatch.setattr(runtime, "ensure_thread", original)
    assert client.post(endpoint, json=body).status_code == 200
    assert client.post(endpoint, json=body).status_code == 200
    assert len([c for c in runtime.rpc.calls if c[0] == "turn/start"]) == 1
    with client.app.state.factory() as db:
        assert db.get(Operation, operation_id).state == "accepted"
        assert len(list(db.scalars(select(MessageAttachment)))) == 1


def test_uncertain_retry_never_reports_success_or_resubmits(client):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    rpc.fail_turn = True
    task, key = new_task(client), str(uuid4())
    assert send_message(client, task, operation_id=key).status_code == 503
    rpc.fail_turn = False
    retry = send_message(client, task, operation_id=key)
    assert retry.status_code == 409
    assert retry.json()["code"] == "codex_request_uncertain"
    assert len([c for c in rpc.calls if c[0] == "turn/start"]) == 1


def test_recovery_can_acknowledge_native_confirmation_without_replaying(client):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    rpc.fail_turn = True
    task, key = new_task(client), str(uuid4())
    assert send_message(client, task, operation_id=key).status_code == 503
    task = client.get(f"/api/tasks/{task['id']}").json()
    rpc.fail_turn = False
    rpc.threads[task["thread_id"]]["turns"] = [
        {
            "id": "confirmed-turn",
            "status": "completed",
            "items": [
                {
                    "id": "native-item-id",
                    "clientId": key,
                    "type": "userMessage",
                    "content": [],
                }
            ],
        }
    ]
    assert client.post(f"/api/tasks/{task['id']}/recover", json={}).status_code == 200
    assert send_message(client, task, operation_id=key).status_code == 200
    assert len([c for c in rpc.calls if c[0] == "turn/start"]) == 1


def test_explicit_recovery_allows_new_request_but_never_replays_uncertain_id(client):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    rpc.fail_turn = True
    task, key = new_task(client), str(uuid4())
    assert send_message(client, task, operation_id=key).status_code == 503
    rpc.fail_turn = False
    assert client.post(f"/api/tasks/{task['id']}/recover", json={}).status_code == 200
    assert send_message(client, task, operation_id=key).json()["code"] == "codex_request_uncertain"
    assert len([c for c in rpc.calls if c[0] == "turn/start"]) == 1
    assert send_message(client, task, operation_id=str(uuid4())).status_code == 200
    assert len([c for c in rpc.calls if c[0] == "turn/start"]) == 2


def test_lost_start_response_can_interrupt_verified_native_turn(client):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    rpc.fail_turn = True
    task = new_task(client)
    assert send_message(client, task).status_code == 503
    task = client.get(f"/api/tasks/{task['id']}").json()
    assert task["turn_id"] is None
    thread = rpc.threads[task["thread_id"]]
    thread["status"] = {"type": "active"}
    thread["turns"] = [{"id": "actual-running-turn", "status": "inProgress", "items": []}]
    assert (
        client.post(f"/api/tasks/{task['id']}/recover", json={}).json()["code"]
        == "turn_not_finished"
    )
    response = client.post(f"/api/tasks/{task['id']}/interrupt", json={})
    assert response.status_code == 200
    assert rpc.calls[-1] == (
        "turn/interrupt",
        {
            "threadId": task["thread_id"],
            "turnId": "actual-running-turn",
        },
    )
    with client.app.state.factory() as db:
        assert db.get(WorkspaceLease, 1).task_id == task["id"]
        assert db.get(Task, task["id"]).status == "uncertain"
    task["turn_id"] = "actual-running-turn"
    assert complete(client, task, status="interrupted")["status"] == "interrupted"
    with client.app.state.factory() as db:
        assert db.get(WorkspaceLease, 1).task_id is None


def test_uncertain_interrupt_rejects_unverified_native_turn(client):
    client.get("/api/codex/account")
    rpc = client.app.state.runtime.rpc
    rpc.fail_turn = True
    task = new_task(client)
    assert send_message(client, task).status_code == 503
    assert (
        client.post(f"/api/tasks/{task['id']}/interrupt", json={}).json()["code"]
        == "turn_not_active"
    )
    assert not any(method == "turn/interrupt" for method, _ in rpc.calls)
    with client.app.state.factory() as db:
        assert db.get(WorkspaceLease, 1).task_id == task["id"]


@pytest.mark.parametrize("state", ["preparing", "pending"])
def test_restart_before_thread_creation_can_release_workspace(client, state):
    task, key = new_task(client), str(uuid4())
    with client.app.state.factory.begin() as db:
        saved = db.get(Task, task["id"])
        saved.status = "starting"
        db.add(
            Operation(
                id=key, task_id=saved.id, kind="requirements", digest="before-send", state=state
            )
        )
        store.lease(db, saved.id)
    store.recover_startup(client.app.state.factory)
    if state == "pending":
        # Older installations did not persist the submission boundary.
        assert client.post(f"/api/tasks/{task['id']}/recover", json={}).status_code == 200
    with client.app.state.factory() as db:
        assert db.get(WorkspaceLease, 1).task_id is None
        assert db.get(Operation, key).state == "failed"
    assert client.app.state.runtime.rpc is None
    assert send_message(client, new_task(client)).status_code == 200


def test_restart_at_submission_boundary_keeps_lease_and_never_replays(client):
    task = send_message(client, new_task(client)).json()
    with client.app.state.factory.begin() as db:
        op = db.scalar(select(Operation).where(Operation.task_id == task["id"]))
        op.state = "submitting"
        db.get(Task, task["id"]).status = "starting"
    store.recover_startup(client.app.state.factory)
    with client.app.state.factory() as db:
        assert db.get(Task, task["id"]).status == "uncertain"
        assert db.get(WorkspaceLease, 1).task_id == task["id"]
    assert send_message(client, new_task(client)).json()["code"] == "workspace_busy"
    assert len([c for c in client.app.state.runtime.rpc.calls if c[0] == "turn/start"]) == 1


@pytest.mark.parametrize("isolated", [False, True])
def test_interrupted_implementation_keeps_root_after_explicit_confirmation(
    client, repository, isolated
):
    task = plan(client)
    if isolated:
        (repository / "hello.txt").write_text("unrelated change\n")
    endpoint = f"/api/tasks/{task['id']}/implement"
    revision = task["revisions"][-1]["id"]
    task = client.post(
        endpoint, json={"operation_id": str(uuid4()), "revision_id": revision}
    ).json()
    root = Path(task["root"])
    (root / "hello.txt").write_text("interrupted implementation\n")
    client.portal.call(client.app.state.runtime.on_disconnect)
    recovered = client.post(f"/api/tasks/{task['id']}/recover", json={})
    assert recovered.status_code == 409
    assert recovered.json()["code"] == "workspace_confirmation_required"
    with client.app.state.factory() as db:
        assert db.get(WorkspaceLease, 1).task_id == task["id"]
    recovered = client.post(f"/api/tasks/{task['id']}/recover", json={"confirm_workspace": True})
    assert recovered.status_code == 200
    assert recovered.json()["root"] == str(root)
    assert recovered.json()["stage"] == "review"
    resumed = client.post(endpoint, json={"operation_id": str(uuid4()), "revision_id": revision})
    assert resumed.status_code == 200
    assert resumed.json()["root"] == str(root)
    assert (root / "hello.txt").read_text() == "interrupted implementation\n"
    complete(client, resumed.json())
    (root / "hello.txt").write_text("later external change\n")
    assert (
        client.post(endpoint, json={"operation_id": str(uuid4()), "revision_id": revision}).json()[
            "code"
        ]
        == "workspace_changed"
    )


def test_completion_fingerprint_failure_requires_recovery_without_moving_root(client, monkeypatch):
    task = plan(client)
    task = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": task["revisions"][-1]["id"],
        },
    ).json()

    def unavailable(root):
        raise ConsoleError("git_unavailable")

    monkeypatch.setattr(git, "fingerprint", unavailable)
    result = complete(client, task)
    assert result["status"] == "uncertain"
    assert result["stage"] == "implement"
    assert result["root"] == task["root"]
    with client.app.state.factory() as db:
        assert db.get(Task, task["id"]).fingerprint is not None
        assert db.get(WorkspaceLease, 1).task_id == task["id"]


def test_disconnect_waits_for_completion_without_blocking_event_loop(client, monkeypatch):
    task = plan(client)
    task = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    ).json()
    runtime = client.app.state.runtime
    started, release = threading.Event(), threading.Event()
    original = git.fingerprint

    def slow_fingerprint(root):
        started.set()
        assert release.wait(3)
        return original(root)

    def limit_locks(connection):
        # Make a regression fail within a bounded time instead of hanging pytest.
        connection.exec_driver_sql("SET LOCAL lock_timeout = '500ms'")

    monkeypatch.setattr(git, "fingerprint", slow_fingerprint)
    engine = runtime.factory.kw["bind"]
    event.listen(engine, "begin", limit_locks)

    async def scenario():
        completion = asyncio.create_task(
            runtime.on_message(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": task["thread_id"],
                        "turnId": task["turn_id"],
                        "turn": {"id": task["turn_id"], "status": "completed"},
                    },
                }
            )
        )
        assert await asyncio.to_thread(started.wait, 2)
        disconnected = asyncio.create_task(runtime.on_disconnect())
        try:
            await asyncio.sleep(0.05)
            assert not disconnected.done()
        finally:
            release.set()
            results = await asyncio.wait_for(
                asyncio.gather(completion, disconnected, return_exceptions=True), 2
            )
        assert results == [None, None]

    try:
        client.portal.call(scenario)
    finally:
        release.set()
        event.remove(engine, "begin", limit_locks)
    assert client.get("/healthz").status_code == 200
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert detail["status"] == "idle"
    assert detail["stage"] == "review"


def test_failed_steer_preparation_can_retry_but_uncertain_steer_cannot(client, monkeypatch):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    key = str(uuid4())
    body = {"operation_id": key, "text": "Follow up"}
    endpoint = f"/api/tasks/{task['id']}/steer"
    original = attachments.prepare

    def unavailable(*args):
        raise ConsoleError("attachment_cache_unavailable", 503)

    monkeypatch.setattr(attachments, "prepare", unavailable)
    assert client.post(endpoint, json=body).status_code == 503
    monkeypatch.setattr(attachments, "prepare", original)
    assert client.post(endpoint, json=body).status_code == 200
    assert client.post(endpoint, json=body).status_code == 200
    assert len([c for c in runtime.rpc.calls if c[0] == "turn/steer"]) == 1
    with client.app.state.factory.begin() as db:
        db.get(Operation, key).state = "uncertain"
    assert client.post(endpoint, json=body).json()["code"] == "codex_request_uncertain"
    assert len([c for c in runtime.rpc.calls if c[0] == "turn/steer"]) == 1
