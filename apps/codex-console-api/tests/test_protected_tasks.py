import subprocess
from uuid import uuid4

import pytest
from conftest import complete, new_task

from codex_console import git
from codex_console.config import Settings
from codex_console.models import Task


def submit(client, task, stage="implement"):
    return client.post(
        f"/api/tasks/{task['id']}/" + ("messages" if stage == "plan" else "implement"),
        json={"operation_id": str(uuid4()), "text": "Inspect the repository"},
    )


def protect_existing(client, repository, tmp_path):
    replacement = tmp_path / "replacement"
    subprocess.run(
        ["git", "clone", str(repository), str(replacement)], check=True, capture_output=True
    )
    settings = Settings(
        **{
            **client.app.state.settings.model_dump(),
            "workspace": replacement,
            "protected_workspaces": [repository],
        },
        _env_file=None,
    )
    client.app.state.settings = client.app.state.runtime.settings = settings


@pytest.mark.parametrize("stage", ["plan", "implement"])
def test_changed_protection_blocks_stored_root_before_git_or_thread(
    client, repository, tmp_path, monkeypatch, stage
):
    task = new_task(client)
    (repository / "dirty.txt").write_text("preserve")
    protect_existing(client, repository, tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Git must not access the protected task root")

    monkeypatch.setattr(git, "prepare_workspace", forbidden)
    monkeypatch.setattr(git, "fingerprint", forbidden)
    response = submit(client, task, stage)
    assert response.status_code == 403
    assert response.json()["code"] == "path_denied"
    rpc = client.app.state.runtime.rpc
    assert not rpc or not any(
        m in ("thread/start", "thread/resume", "turn/start") for m, _ in rpc.calls
    )
    assert (repository / "dirty.txt").read_text() == "preserve"
    for endpoint in ("git", "changes", "diff?path=hello.txt"):
        assert client.get(f"/api/tasks/{task['id']}/{endpoint}").status_code == 403


@pytest.mark.parametrize("stored_path", ["root", "last_execution_root", "previous_execution_root"])
def test_protected_recovery_and_rejoin_preserve_state(
    client, repository, tmp_path, monkeypatch, stored_path
):
    task = submit(client, new_task(client)).json()
    runtime = client.app.state.runtime
    protect_existing(client, repository, tmp_path)
    with client.app.state.factory.begin() as db:
        row = db.get(Task, task["id"])
        row.status = "uncertain"
        row.root = str(runtime.settings.workspace)
        row.last_execution_root = str(runtime.settings.workspace)
        row.previous_execution_root = None
        setattr(row, stored_path, str(repository))
    calls = list(runtime.rpc.calls)

    def forbidden(*args, **kwargs):
        pytest.fail("Recovery must not remove protected registrations")

    monkeypatch.setattr(git, "remove_missing_worktree", forbidden)
    for suffix, body in (
        ("recover", {"confirm_workspace": True}),
        ("messages", {"operation_id": str(uuid4()), "text": "Continue"}),
    ):
        assert client.post(f"/api/tasks/{task['id']}/{suffix}", json=body).status_code == 403
    assert runtime.rpc.calls == calls
    with client.app.state.factory() as db:
        assert db.get(Task, task["id"]).status == "uncertain"


def test_protected_approval_and_steering_block_but_interrupt_and_completion_work(
    client, repository, tmp_path
):
    task = submit(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(
        runtime.on_message,
        {
            "id": 123,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": task["thread_id"],
                "turnId": task["turn_id"],
                "itemId": "command",
                "command": "git status",
            },
        },
    )
    path = f"/api/tasks/{task['id']}"
    request = client.get(path).json()["requests"][0]
    protect_existing(client, repository, tmp_path)
    responses = list(runtime.rpc.responses)
    assert (
        client.post(path + "/requests/" + request["id"], json={"decision": "accept"}).status_code
        == 403
    )
    assert runtime.rpc.responses == responses
    assert (
        client.post(
            path + "/steer", json={"operation_id": str(uuid4()), "text": "Continue"}
        ).status_code
        == 403
    )
    assert not any(m == "turn/steer" for m, _ in runtime.rpc.calls)
    assert client.post(path + "/interrupt").status_code == 200
    finished = complete(client, task, status="interrupted")
    assert finished["status"] == "interrupted"
    assert finished["error_code"] == "path_denied"


def test_missing_protected_worktree_is_not_unregistered(client, repository, tmp_path, monkeypatch):
    task = new_task(client)
    missing = repository / "removed-worktree"
    with client.app.state.factory.begin() as db:
        row = db.get(Task, task["id"])
        row.root, row.worktree_owned = str(missing), True
    protect_existing(client, repository, tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("Protected missing worktree registration must be preserved")

    monkeypatch.setattr(git, "remove_missing_worktree", forbidden)
    assert submit(client, task).status_code == 403
    with client.app.state.factory() as db:
        row = db.get(Task, task["id"])
        assert row.root == str(missing) and row.worktree_owned


def test_protection_failure_during_preparation_records_failure_and_releases_lease(
    client, repository, tmp_path, monkeypatch
):
    from codex_console.errors import ConsoleError
    from codex_console.models import Operation

    task = new_task(client)

    def preparation(*args, **kwargs):
        protect_existing(client, repository, tmp_path)
        raise ConsoleError("path_denied", 403)

    monkeypatch.setattr(git, "prepare_workspace", preparation)
    assert submit(client, task).status_code == 403
    with client.app.state.factory() as db:
        row = db.get(Task, task["id"])
        assert row.status == "failed" and row.error_code == "path_denied"
        assert db.get(Operation, row.current_operation_id).state == "failed"
    # A different allowed task can acquire the execution lease.
    assert submit(client, new_task(client), "plan").status_code == 200


def test_accepted_turn_is_recorded_after_protection_changes(
    client, repository, tmp_path, monkeypatch
):
    from codex_console.models import Operation

    runtime = client.app.state.runtime
    client.portal.call(runtime.authenticated_rpc)
    call = runtime.rpc.call

    async def reply(method, params):
        result = await call(method, params)
        if method == "turn/start":
            protect_existing(client, repository, tmp_path)
        return result

    monkeypatch.setattr(runtime.rpc, "call", reply)
    result = submit(client, new_task(client))
    assert result.status_code == 200
    with client.app.state.factory() as db:
        row = db.get(Task, result.json()["id"])
        assert row.status == "running" and row.turn_id
        assert db.get(Operation, row.current_operation_id).state == "accepted"
    assert client.post(f"/api/tasks/{result.json()['id']}/interrupt").status_code == 200


def test_sent_approval_is_recorded_after_protection_changes(
    client, repository, tmp_path, monkeypatch
):
    from codex_console.models import PendingRequest

    task = submit(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(
        runtime.on_message,
        {
            "id": 123,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": task["thread_id"],
                "turnId": task["turn_id"],
                "itemId": "command",
                "command": "git status",
            },
        },
    )
    path = f"/api/tasks/{task['id']}"
    request = client.get(path).json()["requests"][0]
    respond = runtime.rpc.respond

    async def reply(request_id, result):
        await respond(request_id, result)
        protect_existing(client, repository, tmp_path)

    monkeypatch.setattr(runtime.rpc, "respond", reply)
    assert (
        client.post(path + "/requests/" + request["id"], json={"decision": "accept"}).status_code
        == 200
    )
    with client.app.state.factory() as db:
        assert db.get(PendingRequest, request["id"]).state == "answered"
        assert db.get(Task, task["id"]).status == "running"
    assert client.post(path + "/interrupt").status_code == 200


def test_protected_paths_resolve_aliases_and_missing_descendants(settings, repository, tmp_path):
    from codex_console.errors import ConsoleError

    protected = tmp_path / "protected"
    protected.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(protected, target_is_directory=True)
    settings.protected_workspaces = [protected]
    with pytest.raises(ConsoleError, match="path_denied"):
        settings.require_allowed_paths(alias / "missing")
    settings.require_allowed_paths(repository)


def test_protected_prospective_worktree_is_checked_before_git_add(client, repository):
    from codex_console.models import Operation

    task = new_task(client)
    settings = client.app.state.settings
    target = settings.worktree_root / f"codex-{task['id']}"
    # The configured storage parent remains allowed; only this child is protected.
    current = Settings(
        **{**settings.model_dump(), "protected_workspaces": [target]}, _env_file=None
    )
    client.app.state.settings = client.app.state.runtime.settings = current
    (repository / "dirty.txt").write_text("preserve")
    before = subprocess.check_output(
        ["git", "-C", str(repository), "worktree", "list", "--porcelain"]
    )
    response = submit(client, task)
    assert response.status_code == 403 and response.json()["code"] == "path_denied"
    assert not target.exists()
    assert (
        subprocess.check_output(["git", "-C", str(repository), "worktree", "list", "--porcelain"])
        == before
    )
    assert (repository / "dirty.txt").read_text() == "preserve"
    assert not any(
        method in ("thread/start", "turn/start") for method, _ in client.app.state.runtime.rpc.calls
    )
    with client.app.state.factory() as db:
        row = db.get(Task, task["id"])
        assert row.status == "failed" and row.root == str(repository)
        assert db.get(Operation, row.current_operation_id).state == "failed"
    # Blocking one target does not prevent another allowed task from taking the lease.
    assert submit(client, new_task(client)).status_code == 200
