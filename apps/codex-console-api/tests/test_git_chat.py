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
def test_implementation_resume_and_chat_downgrade_preserve_documents(client, permissions):
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
    assert params["collaborationMode"]["mode"] == "default"
    assert reply.json()["permissions"] == "read-only"
    finished = complete(client, reply.json(), "Just an explanation")
    assert finished["stage"] == "chat"
    assert finished["revisions"] == revisions
    assert finished["approved_revision"] == approved


def test_default_chat_does_not_generate_a_document(client):
    task = new_task(client)
    assert task["stage"] == "chat"
    task = send_message(client, task, "chat").json()
    assert complete(client, task)["revisions"] == []


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
    response = send_message(client, task, "chat", "An unsent question")
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
    assert before["snapshot"] != after["snapshot"]


def git_body(client, task, scope="create"):
    state = client.get(f"/api/tasks/{task['id']}/git").json()
    return {
        "operation_id": str(uuid4()),
        "text": "Execute only the selected Git request",
        "git_request": {
            "snapshot": state["snapshot"],
            "target_ref": "refs/remotes/origin/dev",
            "scope": scope,
        },
    }


@pytest.mark.parametrize("scope", ["create", "merge"])
def test_git_request_has_explicit_scoped_authorization_and_uses_original_workspace(
    client, repository, scope
):
    task = new_task(client)
    (repository / "feature.txt").write_text("task change")
    body = git_body(client, task, scope)
    path = f"/api/tasks/{task['id']}/implement"
    response = client.post(path, json=body)
    assert response.status_code == 200
    task = response.json()
    assert task["root"] == str(repository) and not task["isolated"]
    rpc = client.app.state.runtime.rpc
    params = [p for method, p in rpc.calls if method == "turn/start"][-1]
    context = json.loads(params["additionalContext"]["git_request"]["value"])
    assert context["scope"] == scope and context["source_branch"] == "dev"
    assert context["target"]["ref"] == "refs/remotes/origin/dev"
    with client.app.state.factory() as db:
        assert db.get(Operation, body["operation_id"]).kind == f"git_{scope}"
    client.portal.call(
        client.app.state.runtime.on_message,
        {
            "id": 789,
            "method": "item/commandExecution/requestApproval",
            "params": {
                "threadId": task["thread_id"],
                "turnId": task["turn_id"],
                "itemId": "git-command",
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


def test_stale_git_request_never_starts_a_turn_or_switches_branch(client, repository):
    task = new_task(client)
    body = git_body(client, task)
    run(repository, "checkout", "-b", "another-branch")
    result = client.post(f"/api/tasks/{task['id']}/implement", json=body)
    assert result.status_code == 409 and result.json()["code"] == "git_state_changed"
    assert not any(method == "turn/start" for method, _ in client.app.state.runtime.rpc.calls)
    assert run(repository, "branch", "--show-current") == "another-branch"
    assert client.delete("/api/session").status_code == 200
    assert client.get(f"/api/tasks/{task['id']}/git").status_code == 401
