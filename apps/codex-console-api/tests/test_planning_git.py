import json
import subprocess
from uuid import uuid4

import pytest
from conftest import complete, new_task, plan, send_message

from codex_console import git
from codex_console.models import Operation


def run(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.mark.parametrize("permissions", ["ask", "yolo"])
def test_implementation_resume_and_planning_downgrade_preserve_documents(client, permissions):
    task = plan(client)
    path = f"/api/tasks/{task['id']}"
    body = {"revision_id": task["revisions"][-1]["id"], "permissions": permissions}
    for _ in range(2):
        response = client.post(path + "/implement", json={**body, "operation_id": str(uuid4())})
        assert response.status_code == 200
        task = complete(client, response.json())
    revisions, approved = task["revisions"], task["approved_revision"]
    reply = client.post(
        path + "/messages",
        json={"operation_id": str(uuid4()), "text": "Explain the result", "permissions": "yolo"},
    )
    assert reply.status_code == 200
    params = [p for method, p in client.app.state.runtime.rpc.calls if method == "turn/start"][-1]
    assert params["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert params["approvalPolicy"] == "never"
    assert params["collaborationMode"]["mode"] == "plan"
    assert reply.json()["permissions"] == "read-only"
    finished = complete(client, reply.json(), "Just an explanation", documents=[])
    assert finished["stage"] == "plan"
    assert finished["revisions"] == revisions
    assert finished["approved_revision"] == approved


def test_default_planning_does_not_generate_a_document(client):
    task = new_task(client)
    assert task["stage"] == "plan"
    task = send_message(client, task, "plan").json()
    assert complete(client, task, documents=[])["revisions"] == []


def test_loaded_thread_cwd_does_not_override_an_isolated_workspace(client, repository):
    task = plan(client)
    (repository / "unrelated.txt").write_text("preserve me")
    result = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]},
    )
    assert result.status_code == 200
    isolated = result.json()
    assert isolated["isolated"]
    params = [p for method, p in client.app.state.runtime.rpc.calls if method == "turn/start"][-1]
    assert params["cwd"] == isolated["root"] != str(repository)
    assert params["sandboxPolicy"]["writableRoots"] == [isolated["root"]]


@pytest.mark.parametrize(
    "policy",
    [
        {"type": "dangerFullAccess"},
        {"type": "workspaceWrite", "writableRoots": ["/"], "networkAccess": False},
        {"type": "externalSandbox"},
    ],
)
def test_ungranted_resume_policies_still_fail_closed_and_keep_unsent_text(client, policy):
    task = plan(client)
    rpc = client.app.state.runtime.rpc
    rpc.policies[task["thread_id"]] = policy
    before = sum(method == "turn/start" for method, _ in rpc.calls)
    response = send_message(client, task, "plan", "An unsent question")
    assert response.status_code == 409
    assert response.json()["code"] == "sandbox_policy_mismatch"
    assert sum(method == "turn/start" for method, _ in rpc.calls) == before
    saved = client.get(f"/api/tasks/{task['id']}").json()
    assert saved["failed_request_text"] == "An unsent question"


def test_git_status_tracks_real_branch_dirty_counts_and_detached_head(repository):
    run(repository, "remote", "add", "origin", "https://example.invalid/repo.git")
    run(repository, "branch", "--set-upstream-to=origin/dev", "dev")
    (repository / "hello.txt").write_text("changed\n")
    run(repository, "add", "hello.txt")
    run(repository, "commit", "-m", "local change")
    run(repository, "mv", "hello.txt", "renamed file.txt")
    (repository / "renamed file.txt").write_text("another change\n")
    (repository / "new\nfile.txt").write_text("untracked")
    before = git.status(repository)
    assert (before["branch"], before["upstream"], before["ahead"], before["behind"]) == (
        "dev",
        "origin/dev",
        1,
        0,
    )
    assert (before["changed"], before["staged"], before["unstaged"], before["untracked"]) == (
        2,
        1,
        1,
        1,
    )
    assert "renamed file.txt" not in json.dumps(before)
    run(repository, "checkout", "--detach")
    after = git.status(repository)
    assert after["detached"] and after["branch"] is None and after["head"]
    assert after["upstream"] is None and after["ahead"] is None
    assert "targets" not in after and "snapshot" not in after


def test_direct_execution_accepts_explicit_text_and_retains_native_approval(client):
    task = new_task(client)
    body = {"operation_id": str(uuid4()), "text": "Inspect and fix the failing test"}
    path = f"/api/tasks/{task['id']}/implement"
    response = client.post(path, json=body)
    assert response.status_code == 200
    task = response.json()
    assert task["approved_revision"] is None
    rpc = client.app.state.runtime.rpc
    params = [p for method, p in rpc.calls if method == "turn/start"][-1]
    assert params["sandboxPolicy"]["type"] == "workspaceWrite"
    assert params["approvalPolicy"] == "on-request"
    with client.app.state.factory() as db:
        assert db.get(Operation, body["operation_id"]).kind == "execute"
    client.portal.call(
        client.app.state.runtime.on_message,
        {
            "id": 789,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": task["thread_id"],
                "turnId": task["turn_id"],
                "itemId": "command",
                "command": "git status",
            },
        },
    )
    pending = client.get(f"/api/tasks/{task['id']}").json()["requests"]
    assert len(pending) == 1
    assert (
        client.post(
            f"/api/tasks/{task['id']}/requests/{pending[0]['id']}", json={"decision": "accept"}
        ).status_code
        == 200
    )
    assert client.post(path, json=body).status_code == 200
    assert sum(method == "turn/start" for method, _ in rpc.calls) == 1


def test_execution_needs_text_or_approved_plan_and_git_status_requires_auth(client):
    task = new_task(client)
    assert (
        client.post(
            f"/api/tasks/{task['id']}/implement", json={"operation_id": str(uuid4())}
        ).status_code
        == 422
    )
    assert client.delete("/api/session").status_code == 200
    assert client.get(f"/api/tasks/{task['id']}/git").status_code == 401


def test_completed_structured_turn_from_previous_release_recovers_only_its_plan(client):
    task = send_message(client, new_task(client)).json()
    documents = [
        {"kind": kind, "base_version": 0, "body": f"Initial {kind}", "summary": "Created"}
        for kind in ("requirements", "plan")
    ]
    task = complete(client, task, "Both documents saved", documents=documents)
    assert [(row["kind"], row["body"]) for row in task["revisions"]] == [
        ("plan", "Initial plan")
    ]
    assert task["items"][-1]["text"] == "Both documents saved"

    task = send_message(client, task, text="Revise the plan").json()
    task = complete(client, task, "Revised native plan")
    assert [row["version"] for row in task["revisions"]] == [1, 2]
    response = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": task["revisions"][-1]["id"],
        },
    )
    assert response.status_code == 200
    assert response.json()["approved_revision"] == task["revisions"][-1]["id"]


def test_plain_agent_answer_does_not_overwrite_the_native_plan(client):
    from conftest import notify

    task = plan(client)
    before = task["revisions"]
    task = send_message(client, task).json()
    notify(
        client,
        task,
        "item/completed",
        {
            "item": {
                "id": "malformed",
                "type": "agentMessage",
                "phase": "final_answer",
                "text": "not JSON",
            }
        },
    )
    notify(client, task, "turn/completed", {"turn": {"id": task["turn_id"], "status": "completed"}})
    result = client.get(f"/api/tasks/{task['id']}").json()
    assert result["error_code"] is None
    assert result["revisions"] == before


def test_new_prompt_steers_a_verified_active_uncertain_turn_without_replaying(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    runtime.rpc.threads[task["thread_id"]].update(
        status={"type": "active"}, turns=[{"id": task["turn_id"], "status": "inProgress"}]
    )
    response = send_message(client, task, text="Also inspect the tests")
    assert response.status_code == 200
    methods = [method for method, _ in runtime.rpc.calls]
    assert methods.count("turn/start") == 1
    assert methods.count("turn/steer") == 1


@pytest.mark.parametrize("removal", ["git", "directory"])
def test_removed_owned_worktree_keeps_thread_but_resets_file_ownership(client, repository, removal):
    from codex_console.models import Task

    (repository / "unrelated.txt").write_text("must stay")
    task = client.post(
        f"/api/tasks/{new_task(client)['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "text": "Make the requested change",
        },
    ).json()
    assert task["isolated"]
    task = complete(client, task)
    old_root, thread = task["root"], task["thread_id"]
    if removal == "directory":
        import shutil
        from pathlib import Path

        other_paths = [
            repository.parent / name for name in ("other-missing", "other-locked", "other-active")
        ]
        for path in other_paths:
            run(repository, "worktree", "add", "--detach", str(path), "HEAD")
        run(repository, "worktree", "lock", str(other_paths[1]))
        (other_paths[2] / "preserve.txt").write_text("keep this active worktree")
        shutil.rmtree(other_paths[0])
        shutil.rmtree(other_paths[1])
        shutil.rmtree(Path(old_root))
        before = git.git(repository, "worktree", "list", "--porcelain", "-z")
    else:
        run(repository, "worktree", "remove", old_root)
    response = send_message(client, task, text="Explain the completed work")
    assert response.status_code == 200
    assert response.json()["thread_id"] == thread
    assert response.json()["root"] == str(repository)
    assert not response.json()["isolated"]
    if removal == "directory":
        after = git.git(repository, "worktree", "list", "--porcelain", "-z")
        for path in other_paths:
            marker = b"worktree " + str(path).encode()
            previous = next(record for record in before.split(b"\0\0") if record.startswith(marker))
            assert previous in after.split(b"\0\0")
        assert (other_paths[2] / "preserve.txt").read_text() == "keep this active worktree"
        assert b"worktree " + old_root.encode() not in after
    with client.app.state.factory() as db:
        assert db.get(Task, task["id"]).fingerprint is None
    complete(client, response.json(), documents=[])
    result = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "text": "Start another change",
        },
    )
    assert result.status_code == 200 and result.json()["isolated"]
    assert (repository / "unrelated.txt").read_text() == "must stay"


def test_isolation_works_without_an_origin_or_dev_branch(repository, tmp_path):
    run(repository, "branch", "-m", "trunk")
    run(repository, "update-ref", "-d", "refs/remotes/origin/dev")
    (repository / "unrelated.txt").write_text("preserve")
    root, owned = git.prepare_workspace(
        repository, str(uuid4()), None, base_ref="HEAD", worktree_root=tmp_path / "sessions"
    )
    assert owned and run(root, "rev-parse", "HEAD") == run(repository, "rev-parse", "HEAD")
    assert (repository / "unrelated.txt").read_text() == "preserve"


@pytest.mark.parametrize("streamed", [False, True])
def test_large_native_plan_and_command_output_keep_their_respective_bounds(client, streamed):
    from conftest import notify

    task = send_message(client, new_task(client)).json()
    plan_body = "문" * 100000
    item = {"id": "large-final", "type": "plan", "text": plan_body}
    if streamed:
        notify(client, task, "item/started", {"item": {**item, "text": ""}})
        for offset in range(0, len(plan_body), 40000):
            notify(
                client,
                task,
                "item/plan/delta",
                {
                    "itemId": item["id"],
                    "delta": plan_body[offset : offset + 40000],
                },
            )
    notify(client, task, "item/completed", {"item": item})
    notify(
        client,
        task,
        "item/completed",
        {
            "item": {
                "id": "command",
                "type": "commandExecution",
                "aggregatedOutput": "x" * 110000 + "end",
            }
        },
    )
    notify(client, task, "turn/completed", {"turn": {"id": task["turn_id"], "status": "completed"}})
    saved = client.get(f"/api/tasks/{task['id']}").json()
    assert saved["error_code"] is None
    assert [r["body"] for r in saved["revisions"]] == [plan_body]
    assert next(i for i in saved["items"] if i["id"] == "large-final")["text"] == plan_body
    output = next(i for i in saved["items"] if i["id"] == "command")["aggregatedOutput"]
    assert len(output) == 100000 and output.endswith("end")

    # Recovery keeps the native plan while the task is now implementing/reviewing.
    response = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": saved["revisions"][-1]["id"],
        },
    )
    assert response.status_code == 200
    executing = response.json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    runtime.rpc.threads[task["thread_id"]].update(
        status={"type": "idle"},
        turns=[
            {
                "id": task["turn_id"],
                "status": "completed",
                "items": [
                    item,
                    {
                        "id": "command",
                        "type": "commandExecution",
                        "aggregatedOutput": "x" * 110000 + "end",
                    },
                ],
            },
            {"id": executing["turn_id"], "status": "completed", "items": []},
        ],
    )
    for _ in range(2):
        recovered = client.post(
            f"/api/tasks/{task['id']}/recover", json={"confirm_workspace": True}
        )
        assert recovered.status_code == 200
        history = recovered.json()
        assert history["stage"] == "review"
        assert history["revisions"] == saved["revisions"]
        final = next(i for i in history["items"] if i["id"] == "large-final")
        assert final["text"] == plan_body
        output = next(i for i in history["items"] if i["id"] == "command")["aggregatedOutput"]
        assert len(output) == 100000 and output.endswith("end")


@pytest.mark.parametrize("proof", ["client_id", "turn_id", "unrelated", "missing"])
def test_uncertain_direct_execution_requires_acceptance_proof_and_restores_approvals(client, proof):
    from codex_console.models import Task

    runtime = client.app.state.runtime
    task = new_task(client)
    operation_id = str(uuid4())
    client.portal.call(runtime.authenticated_rpc)
    runtime.rpc.fail_turn = True
    assert (
        client.post(
            f"/api/tasks/{task['id']}/implement",
            json={
                "operation_id": operation_id,
                "text": "Fix the test",
            },
        ).status_code
        == 503
    )
    task = client.get(f"/api/tasks/{task['id']}").json()
    turn_id = "accepted-native-turn"
    if proof == "turn_id":
        with client.app.state.factory.begin() as db:
            db.get(Task, task["id"]).turn_id = turn_id
    items = (
        []
        if proof in ("missing", "turn_id")
        else [
            {
                "id": "user",
                "type": "userMessage",
                "clientId": operation_id if proof == "client_id" else str(uuid4()),
                "content": [],
            }
        ]
    )
    runtime.rpc.threads[task["thread_id"]].update(
        status={"type": "active"}, turns=[{"id": turn_id, "status": "inProgress", "items": items}]
    )
    response = client.post(
        f"/api/tasks/{task['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "text": "Also check formatting",
        },
    )
    verified = proof in ("client_id", "turn_id")
    assert response.status_code == (200 if verified else 409)
    with client.app.state.factory() as db:
        assert db.get(Operation, operation_id).state == ("accepted" if verified else "uncertain")
        assert db.get(Task, task["id"]).status == ("running" if verified else "uncertain")
    assert sum(method == "turn/start" for method, _ in runtime.rpc.calls) == 1
    assert sum(method == "turn/steer" for method, _ in runtime.rpc.calls) == int(verified)
    client.portal.call(
        runtime.on_message,
        {
            "id": 789,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": task["thread_id"],
                "turnId": turn_id,
                "itemId": "command",
                "command": "git status",
            },
        },
    )
    requests = client.get(f"/api/tasks/{task['id']}").json()["requests"]
    assert len(requests) == int(verified)
    if verified:
        assert (
            client.post(
                f"/api/tasks/{task['id']}/requests/{requests[0]['id']}", json={"decision": "accept"}
            ).status_code
            == 200
        )


@pytest.mark.parametrize("new_request", [False, True])
@pytest.mark.parametrize("native_active", [False, True])
def test_prepare_submission_discards_read_results_after_completion_or_new_request(
    client, monkeypatch, new_request, native_active
):
    from copy import deepcopy

    from codex_console.errors import ConsoleError

    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    rpc = runtime.rpc
    rpc.threads[task["thread_id"]].update(
        status={"type": "active" if native_active else "idle"},
        turns=[{"id": task["turn_id"], "status": "inProgress" if native_active else "completed"}],
    )
    original = rpc.call
    new_operation = str(uuid4())

    async def racing_read(method, params):
        result = deepcopy(await original(method, params))
        if method == "thread/read":
            await runtime.on_message(
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": task["thread_id"],
                        "turn": {"id": task["turn_id"], "status": "completed"},
                    },
                }
            )
            if new_request:
                await runtime.start(task["id"], new_operation, "A new explicit request", "plan")
        return result

    monkeypatch.setattr(rpc, "call", racing_read)
    with pytest.raises(ConsoleError, match="task_busy"):
        client.portal.call(runtime.prepare_submission, task["id"])
    saved = client.get(f"/api/tasks/{task['id']}").json()
    assert saved["status"] == ("running" if new_request else "idle")
    if new_request:
        assert saved["turn_id"] != task["turn_id"]
    assert sum(method == "turn/start" for method, _ in rpc.calls) == (2 if new_request else 1)


@pytest.mark.parametrize(
    "before,permissions,after,requested",
    [
        ("implement", "ask", "plan", "ask"),
        ("implement", "yolo", "plan", "yolo"),
        ("plan", "ask", "implement", "ask"),
        ("plan", "ask", "implement", "yolo"),
        ("implement", "ask", "implement", "yolo"),
        ("implement", "yolo", "implement", "ask"),
        ("implement", "ask", "implement", "ask"),
        ("implement", "yolo", "implement", "yolo"),
    ],
)
def test_active_recovery_cannot_change_mode_or_permissions(
    client, before, permissions, after, requested
):
    task = new_task(client)
    endpoint = f"/api/tasks/{task['id']}"
    started = client.post(
        endpoint + ("/messages" if before == "plan" else "/implement"),
        json={
            "operation_id": str(uuid4()),
            "text": "Inspect the code",
            "permissions": permissions,
        },
    )
    assert started.status_code == 200
    task = started.json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    runtime.rpc.threads[task["thread_id"]].update(
        status={"type": "active"},
        turns=[
            {
                "id": task["turn_id"],
                "status": "inProgress",
                "items": [],
            }
        ],
    )
    response = client.post(
        endpoint + ("/messages" if after == "plan" else "/implement"),
        json={
            "operation_id": str(uuid4()),
            "text": "Check one more thing",
            "permissions": requested,
        },
    )
    matches = before == after and permissions == requested
    assert response.status_code == (200 if matches else 409)
    if not matches:
        assert response.json()["code"] == "turn_settings_mismatch"
    assert sum(method == "turn/steer" for method, _ in runtime.rpc.calls) == int(matches)
    saved = client.get(endpoint).json()
    assert saved["status"] == ("running" if matches else "uncertain")
    assert saved["stage"] == before
    assert saved["permissions"] == (permissions if before == "implement" else "read-only")


@pytest.mark.parametrize("permissions", ["ask", "yolo"])
@pytest.mark.parametrize("target", ["plan", "implement"])
def test_failed_permission_transition_recovers_previous_native_sandbox(client, permissions, target):
    from codex_console import store
    from codex_console.models import Task

    task = new_task(client)
    endpoint = f"/api/tasks/{task['id']}"
    task = client.post(
        endpoint + "/implement",
        json={
            "operation_id": str(uuid4()),
            "text": "Inspect the code",
            "permissions": permissions,
        },
    ).json()
    complete(client, task)
    rpc = client.app.state.runtime.rpc
    previous_policy = rpc.policies[task["thread_id"]].copy()
    rpc.fail_turn = True
    next_permissions = "yolo" if permissions == "ask" else "ask"
    path = endpoint + ("/messages" if target == "plan" else "/implement")
    response = client.post(
        path,
        json={
            "operation_id": str(uuid4()),
            "text": "Review the next step",
            "permissions": next_permissions,
        },
    )
    assert response.status_code == 503
    with client.app.state.factory() as db:
        row = db.get(Task, task["id"])
        assert row.previous_permissions == permissions
        assert row.previous_execution_root == task["root"]
    assert rpc.policies[task["thread_id"]] == previous_policy
    store.recover_startup(client.app.state.factory)
    rpc.fail_turn = False
    recovered = client.post(endpoint + "/recover", json={"confirm_workspace": True})
    assert recovered.status_code == 200
    assert recovered.json()["permissions"] == permissions
    retry = client.post(
        path,
        json={
            "operation_id": str(uuid4()),
            "text": "Review the next step",
            "permissions": next_permissions,
        },
    )
    assert retry.status_code == 200
    assert retry.json()["permissions"] == ("read-only" if target == "plan" else next_permissions)
    with client.app.state.factory() as db:
        row = db.get(Task, task["id"])
        assert row.previous_permissions is None and row.previous_execution_root is None


@pytest.mark.parametrize("target", ["plan", "implement"])
@pytest.mark.parametrize("foreign_cwd", [False, True])
def test_uncertain_workspace_transition_accepts_only_recorded_previous_cwd(
    client, repository, target, foreign_cwd
):
    from codex_console.models import Task

    task = plan(client)
    (repository / "unrelated.txt").write_text("preserve this file")
    endpoint = f"/api/tasks/{task['id']}"
    rpc = client.app.state.runtime.rpc
    rpc.fail_turn = True
    failed = client.post(
        endpoint + "/implement",
        json={
            "operation_id": str(uuid4()),
            "text": "Make the requested change",
        },
    )
    assert failed.status_code == 503
    with client.app.state.factory() as db:
        row = db.get(Task, task["id"])
        assert row.worktree_owned and row.root != str(repository)
        assert row.last_execution_root == row.root
        assert row.previous_execution_root == str(repository)
    assert rpc.threads[task["thread_id"]]["cwd"] == str(repository)
    if foreign_cwd:
        rpc.threads[task["thread_id"]]["cwd"] = str(repository.parent / "unverified")
    rpc.fail_turn = False
    response = client.post(
        endpoint + ("/messages" if target == "plan" else "/implement"),
        json={
            "operation_id": str(uuid4()),
            "text": "Continue after the failed transition",
        },
    )
    assert response.status_code == (409 if foreign_cwd else 200)
    if foreign_cwd:
        assert response.json()["code"] == "thread_unavailable"
    else:
        assert response.json()["stage"] == target
        assert response.json()["thread_id"] == task["thread_id"]
    assert sum(method == "turn/start" for method, _ in rpc.calls) == (2 if foreign_cwd else 3)
    assert (repository / "unrelated.txt").read_text() == "preserve this file"


@pytest.mark.parametrize(
    "requested_settings,matches",
    [
        ({}, True),
        ({"model": "account-default", "effort": "high"}, True),
        ({"model": "another-model"}, False),
        ({"effort": "low"}, False),
    ],
)
@pytest.mark.parametrize("mode", ["plan", "implement"])
def test_active_recovery_preserves_omitted_settings_and_rejects_explicit_changes(
    client, requested_settings, matches, mode
):
    task = new_task(client)
    endpoint = f"/api/tasks/{task['id']}"
    path = endpoint + ("/messages" if mode == "plan" else "/implement")
    started = client.post(
        path,
        json={
            "operation_id": str(uuid4()),
            "text": "Inspect the code",
            "model": "account-default",
            "effort": "high",
        },
    )
    assert started.status_code == 200
    task = started.json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    runtime.rpc.threads[task["thread_id"]].update(
        status={"type": "active"},
        turns=[
            {
                "id": task["turn_id"],
                "status": "inProgress",
                "items": [],
            }
        ],
    )
    response = client.post(
        path,
        json={
            "operation_id": str(uuid4()),
            "text": "Check the result",
            **requested_settings,
        },
    )
    assert response.status_code == (200 if matches else 409)
    if not matches:
        assert response.json()["code"] == "turn_settings_mismatch"
    assert sum(method == "turn/steer" for method, _ in runtime.rpc.calls) == int(matches)
    saved = client.get(endpoint).json()
    assert saved["model"] == "account-default" and saved["effort"] == "high"
    assert saved["status"] == ("running" if matches else "uncertain")


@pytest.mark.parametrize("mode", ["plan", "direct", "revision"])
def test_lost_start_response_retry_returns_verified_acceptance_without_steering(client, mode):
    from codex_console.models import Operation

    task = plan(client) if mode == "revision" else new_task(client)
    runtime = client.app.state.runtime
    client.portal.call(runtime.authenticated_rpc)
    rpc = runtime.rpc
    before = sum(method == "turn/start" for method, _ in rpc.calls)
    path = f"/api/tasks/{task['id']}" + ("/messages" if mode == "plan" else "/implement")
    body = {"operation_id": str(uuid4()), "text": "Inspect the tests"}
    if mode == "revision":
        body = {"operation_id": str(uuid4()), "revision_id": task["revisions"][-1]["id"]}
    rpc.fail_turn = True
    assert client.post(path, json=body).status_code == 503
    saved = client.get(f"/api/tasks/{task['id']}").json()
    rpc.threads[saved["thread_id"]].update(
        status={"type": "active"},
        turns=[
            {
                "id": "verified-submitted-turn",
                "status": "inProgress",
                "items": [
                    {
                        "id": "user",
                        "type": "userMessage",
                        "clientId": body["operation_id"],
                        "content": [],
                    }
                ],
            }
        ],
    )
    for _ in range(2):
        response = client.post(path, json=body)
        assert response.status_code == 200
        assert response.json()["turn_id"] == "verified-submitted-turn"
    assert sum(method == "turn/start" for method, _ in rpc.calls) == before + 1
    assert not any(method == "turn/steer" for method, _ in rpc.calls)
    with client.app.state.factory() as db:
        assert db.get(Operation, body["operation_id"]).state == "accepted"
    assert (
        client.post(path, json={**body, "text": "Different request"}).json()["code"]
        == "duplicate_request"
    )


@pytest.mark.parametrize("revision", ["current", "old", "missing"])
def test_new_plan_execution_is_not_silently_steered_into_a_recovered_turn(client, revision):
    task = plan(client)
    old_id = task["revisions"][-1]["id"]
    task = complete(client, send_message(client, task).json(), "Updated plan")
    latest_id = task["revisions"][-1]["id"]
    endpoint = f"/api/tasks/{task['id']}"
    task = client.post(
        endpoint + "/implement",
        json={
            "operation_id": str(uuid4()),
            "text": "Inspect the code",
        },
    ).json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    runtime.rpc.threads[task["thread_id"]].update(
        status={"type": "active"},
        turns=[
            {
                "id": task["turn_id"],
                "status": "inProgress",
                "items": [],
            }
        ],
    )
    revision_id = {"current": latest_id, "old": old_id, "missing": latest_id + 1000}[revision]
    response = client.post(
        endpoint + "/implement",
        json={
            "operation_id": str(uuid4()),
            "revision_id": revision_id,
            "text": "Execute this plan",
        },
    )
    assert response.status_code == 409 and response.json()["code"] == "turn_not_finished"
    assert not any(method == "turn/steer" for method, _ in runtime.rpc.calls)
    saved = client.get(endpoint).json()
    assert saved["status"] == "uncertain" and saved["approved_revision"] is None


def test_retry_of_submission_steered_after_recovery_is_also_idempotent(client):
    task = send_message(client, new_task(client)).json()
    runtime = client.app.state.runtime
    client.portal.call(runtime.on_disconnect)
    runtime.rpc.threads[task["thread_id"]].update(
        status={"type": "active"},
        turns=[
            {
                "id": task["turn_id"],
                "status": "inProgress",
                "items": [],
            }
        ],
    )
    body = {"operation_id": str(uuid4()), "text": "Check the tests too"}
    for _ in range(2):
        assert client.post(f"/api/tasks/{task['id']}/messages", json=body).status_code == 200
    assert sum(method == "turn/steer" for method, _ in runtime.rpc.calls) == 1
    assert sum(method == "turn/start" for method, _ in runtime.rpc.calls) == 1


def test_removed_locked_owned_worktree_is_not_forced_or_relocated(client, repository):
    import shutil

    from codex_console.models import Task

    (repository / "unrelated.txt").write_text("keep this file")
    task = client.post(
        f"/api/tasks/{new_task(client)['id']}/implement",
        json={
            "operation_id": str(uuid4()),
            "text": "Inspect the workspace",
        },
    ).json()
    complete(client, task)
    run(repository, "worktree", "lock", task["root"])
    shutil.rmtree(task["root"])
    before = git.git(repository, "worktree", "list", "--porcelain", "-z")
    response = send_message(client, task, text="Explain the result")
    assert response.status_code == 409 and response.json()["code"] == "worktree_exists"
    assert git.git(repository, "worktree", "list", "--porcelain", "-z") == before
    with client.app.state.factory() as db:
        saved = db.get(Task, task["id"])
        assert saved.worktree_owned and saved.root == task["root"]
    assert (repository / "unrelated.txt").read_text() == "keep this file"
