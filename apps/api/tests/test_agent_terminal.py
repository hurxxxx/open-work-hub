from __future__ import annotations

import asyncio
import base64
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import Settings
from open_work_hub_api.domains.agent_terminal.app_catalog import AGENT_TERMINAL_APP
from open_work_hub_api.domains.agent_terminal.codex_history import (
    AgentTerminalCodexHistoryError,
    list_codex_threads,
    require_codex_thread,
)
from open_work_hub_api.domains.agent_terminal.git_changes import (
    AgentTerminalGitError,
    get_git_commit_detail,
    get_git_commit_diff,
    get_git_diff,
    get_git_history,
    get_git_status,
    get_git_summary,
)
from open_work_hub_api.domains.agent_terminal.models import AgentTerminalSession
from open_work_hub_api.domains.agent_terminal.models import utcnow_naive
from open_work_hub_api.domains.agent_terminal.runtime import AgentTerminalRuntime
from open_work_hub_api.domains.agent_terminal.service import (
    AgentTerminalConfigurationError,
    AgentTerminalRoot,
    build_codex_environment,
    configured_roots,
    resolve_codex_binary,
    resolve_root,
    resolve_tmux_binary,
)
from open_work_hub_api.domains.auth.models import AuditLog


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_dsn": "sqlite://",
        "agent_terminal_allowed_roots": {"test-project": str(tmp_path)},
        "agent_terminal_codex_bin": "/bin/sh",
        "agent_terminal_enabled": True,
    }
    values.update(overrides)
    with patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
    )


def _git_output(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_agent_terminal_default_session_capacity(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    assert settings.agent_terminal_max_sessions_per_user == 4
    assert settings.agent_terminal_max_sessions_total == 20


def _initialize_git_repository(root: Path) -> None:
    _git(root, "init", "--initial-branch=dev")
    _git(root, "config", "user.email", "agent-terminal@example.test")
    _git(root, "config", "user.name", "Agent Terminal Test")
    (root / "tracked.txt").write_text("original\n", encoding="utf-8")
    (root / "staged.txt").write_text("before staging\n", encoding="utf-8")
    _git(root, "add", "tracked.txt", "staged.txt")
    _git(root, "commit", "-m", "initial")


def test_agent_terminal_catalog_is_admin_only_personal_tool() -> None:
    assert AGENT_TERMINAL_APP.app_id == "agent-terminal"
    from open_work_hub_api.core.app_registry import compile_app_registry

    assert (
        compile_app_registry([AGENT_TERMINAL_APP]).catalog[0].execution_context_kind == "personal"
    )
    assert AGENT_TERMINAL_APP.launcher_personal_tools is True
    assert AGENT_TERMINAL_APP.feature_flag == "agent_terminal_enabled"
    assert AGENT_TERMINAL_APP.required_system_roles == ("platform_admin",)


def test_configured_roots_only_resolve_server_allowlist(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    roots = configured_roots(settings)

    assert roots[0].key == "test-project"
    assert roots[0].path == tmp_path.resolve()
    assert resolve_root(settings, "test-project") == roots[0]
    with pytest.raises(
        AgentTerminalConfigurationError,
        match="agent_terminal.root_not_found",
    ):
        resolve_root(settings, "unlisted-project")


def test_configured_roots_reject_invalid_keys(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        agent_terminal_allowed_roots={"../escape": str(tmp_path)},
    )

    with pytest.raises(
        AgentTerminalConfigurationError,
        match="agent_terminal.root_config_invalid",
    ):
        configured_roots(settings)


def test_codex_process_environment_does_not_inherit_api_secrets() -> None:
    environment = build_codex_environment(
        {
            "HOME": "/srv/agent",
            "PATH": "/usr/bin",
            "CODEX_HOME": "/srv/agent/.codex",
            "OPEN_WORK_HUB_POSTGRES_DSN": "secret-dsn",
            "THIRD_PARTY_TOKEN": "secret-key",
        }
    )

    assert environment["HOME"] == "/srv/agent"
    assert environment["CODEX_HOME"] == "/srv/agent/.codex"
    assert environment["TERM"] == "xterm-256color"
    assert "OPEN_WORK_HUB_POSTGRES_DSN" not in environment
    assert "THIRD_PARTY_TOKEN" not in environment


def test_codex_binary_must_resolve_to_an_executable(tmp_path: Path) -> None:
    assert resolve_codex_binary(_settings(tmp_path)) == str(Path("/bin/sh").resolve())
    assert (
        resolve_codex_binary(_settings(tmp_path, agent_terminal_codex_bin="missing-codex-binary"))
        is None
    )
    tmux_binary = shutil.which("tmux")
    assert resolve_tmux_binary(_settings(tmp_path)) == (
        str(Path(tmux_binary).resolve()) if tmux_binary else None
    )
    assert resolve_tmux_binary(_settings(tmp_path, agent_terminal_tmux_bin="missing-tmux")) is None


def test_tmux_socket_is_stable_across_restarts_and_isolated_by_runtime(
    tmp_path: Path,
) -> None:
    session_factory = sessionmaker()
    dev_settings = _settings(tmp_path, env_profile="dev", instance_id="api-1")

    first = AgentTerminalRuntime(dev_settings, session_factory)
    restarted = AgentTerminalRuntime(dev_settings, session_factory)
    production = AgentTerminalRuntime(
        _settings(tmp_path, env_profile="prod", instance_id="api-1"),
        session_factory,
    )
    sibling = AgentTerminalRuntime(
        _settings(tmp_path, env_profile="dev", instance_id="api-2"),
        session_factory,
    )

    assert first._tmux_socket_name == restarted._tmux_socket_name
    assert first._tmux_socket_name != production._tmux_socket_name
    assert first._tmux_socket_name != sibling._tmux_socket_name


def test_tmux_session_launches_codex_without_approvals_or_sandbox(
    tmp_path: Path,
) -> None:
    runtime = AgentTerminalRuntime(_settings(tmp_path), sessionmaker())
    tmux_calls: list[tuple[str, ...]] = []

    async def run_tmux(*arguments: str, **_kwargs: object) -> tuple[int, str]:
        tmux_calls.append(arguments)
        return 0, ""

    runtime._run_tmux = run_tmux  # type: ignore[method-assign]

    asyncio.run(
        runtime._create_tmux_session(
            session_id="session-1",
            root_path=tmp_path,
            codex_binary="/bin/sh",
            cols=100,
            rows=30,
        )
    )

    launch_arguments = shlex.split(tmux_calls[0][-1])
    assert "--dangerously-bypass-approvals-and-sandbox" in launch_arguments
    assert "--no-alt-screen" in launch_arguments
    assert "--ask-for-approval" not in launch_arguments
    assert "--sandbox" not in launch_arguments

    tmux_calls.clear()
    asyncio.run(
        runtime._create_tmux_session(
            session_id="session-2",
            root_path=tmp_path,
            codex_binary="/bin/sh",
            codex_thread_id="12345678-1234-1234-1234-123456789abc",
            cols=100,
            rows=30,
        )
    )

    resume_arguments = shlex.split(tmux_calls[0][-1])
    assert resume_arguments[-6:] == [
        "resume",
        "-C",
        str(tmp_path),
        "--dangerously-bypass-approvals-and-sandbox",
        "--no-alt-screen",
        "12345678-1234-1234-1234-123456789abc",
    ]


def test_tmux_scrollback_uses_copy_mode_without_sending_arrow_keys(
    tmp_path: Path,
) -> None:
    runtime = AgentTerminalRuntime(_settings(tmp_path), sessionmaker())
    runtime._sessions["session-1"] = SimpleNamespace(  # type: ignore[assignment]
        control_lock=asyncio.Lock(),
        detaching=False,
        finished=False,
    )
    tmux_calls: list[tuple[str, ...]] = []

    async def run_tmux(*arguments: str, **_kwargs: object) -> tuple[int, bytes]:
        tmux_calls.append(arguments)
        return 0, b""

    runtime._run_tmux = run_tmux  # type: ignore[method-assign]

    async def exercise() -> None:
        await runtime.scroll("session-1", lines=-5)
        await runtime.scroll("session-1", lines=4)
        await runtime.end_scroll("session-1")

    asyncio.run(exercise())

    target = f"{runtime._tmux_target('session-1')}:0.0"
    assert tmux_calls == [
        ("copy-mode", "-e", "-t", target),
        ("send-keys", "-t", target, "-X", "-N", "5", "scroll-up"),
        ("copy-mode", "-e", "-t", target),
        ("send-keys", "-t", target, "-X", "-N", "4", "scroll-down"),
        ("send-keys", "-t", target, "-X", "cancel"),
    ]


def test_tmux_resize_updates_the_attachment_pty(tmp_path: Path) -> None:
    runtime = AgentTerminalRuntime(_settings(tmp_path), sessionmaker())
    runtime._sessions["session-1"] = SimpleNamespace(  # type: ignore[assignment]
        detaching=False,
        finished=False,
        master_fd=123,
    )

    with patch(
        "open_work_hub_api.domains.agent_terminal.runtime._set_terminal_size"
    ) as set_terminal_size:
        asyncio.run(runtime.resize("session-1", cols=180, rows=64))

    set_terminal_size.assert_called_once_with(123, cols=180, rows=64)


def test_codex_history_uses_app_server_and_enforces_allowed_root(tmp_path: Path) -> None:
    root_path = tmp_path / "allowed"
    outside_path = tmp_path / "outside"
    root_path.mkdir()
    outside_path.mkdir()
    matching_thread_id = "11111111-1111-1111-1111-111111111111"
    outside_thread_id = "22222222-2222-2222-2222-222222222222"
    threads = [
        {
            "id": matching_thread_id,
            "name": "Resume UI",
            "preview": "Review the agent terminal\n  resume experience",
            "cwd": str(root_path),
            "createdAt": 1_775_000_000,
            "updatedAt": 1_775_000_100,
        },
        {
            "id": outside_thread_id,
            "name": "Outside",
            "preview": "outside raw prompt",
            "cwd": str(outside_path),
            "createdAt": 1_775_000_200,
            "updatedAt": 1_775_000_300,
        },
    ]
    fake_codex = tmp_path / "fake-codex-app-server"
    fake_codex.write_text(
        f"#!{sys.executable}\n"
        "import json\n"
        "import sys\n"
        f"threads = {threads!r}\n"
        "for line in sys.stdin:\n"
        "    message = json.loads(line)\n"
        "    request_id = message.get('id')\n"
        "    if request_id is None:\n"
        "        continue\n"
        "    method = message.get('method')\n"
        "    if method == 'initialize':\n"
        "        response = {'id': request_id, 'result': {}}\n"
        "    elif method == 'thread/list':\n"
        "        response = {'id': request_id, 'result': {'data': threads, 'nextCursor': None}}\n"
        "    elif method == 'thread/read':\n"
        "        thread_id = message['params']['threadId']\n"
        "        thread = next((item for item in threads if item['id'] == thread_id), None)\n"
        "        response = ({'id': request_id, 'result': {'thread': thread}} if thread else {'id': request_id, 'error': {'code': -1}})\n"
        "    else:\n"
        "        response = {'id': request_id, 'error': {'code': -2}}\n"
        "    print(json.dumps(response), flush=True)\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)
    root = AgentTerminalRoot(key="allowed", label="Allowed", path=root_path.resolve())

    listed = asyncio.run(
        list_codex_threads(
            codex_binary=str(fake_codex),
            roots=(root,),
            limit=50,
        )
    )

    assert [thread.id for thread in listed] == [matching_thread_id]
    assert listed[0].name == "Resume UI"
    assert listed[0].preview == "Review the agent terminal resume experience"
    resumed = asyncio.run(
        require_codex_thread(
            codex_binary=str(fake_codex),
            root=root,
            thread_id=matching_thread_id,
        )
    )
    assert resumed.id == matching_thread_id
    with pytest.raises(
        AgentTerminalCodexHistoryError,
        match="agent_terminal.codex_thread_not_found",
    ):
        asyncio.run(
            require_codex_thread(
                codex_binary=str(fake_codex),
                root=root,
                thread_id=outside_thread_id,
            )
        )


def test_git_changes_are_scoped_to_the_configured_repository_root(tmp_path: Path) -> None:
    _initialize_git_repository(tmp_path)
    (tmp_path / "tracked.txt").write_text("working tree\n", encoding="utf-8")
    (tmp_path / "staged.txt").write_text("staged change\n", encoding="utf-8")
    _git(tmp_path, "add", "staged.txt")
    (tmp_path / "untracked.txt").write_text("new file\n", encoding="utf-8")

    status_response = get_git_status(tmp_path)

    assert status_response.is_repository is True
    assert status_response.branch == "dev"
    assert {(item.path, item.scope, item.kind) for item in status_response.changes} == {
        ("staged.txt", "staged", "modified"),
        ("tracked.txt", "unstaged", "modified"),
        ("untracked.txt", "untracked", "untracked"),
    }

    unstaged = get_git_diff(tmp_path, path="tracked.txt", scope="unstaged")
    assert unstaged.old_content == "original\n"
    assert unstaged.new_content == "working tree\n"
    staged = get_git_diff(tmp_path, path="staged.txt", scope="staged")
    assert staged.old_content == "before staging\n"
    assert staged.new_content == "staged change\n"
    untracked = get_git_diff(tmp_path, path="untracked.txt", scope="untracked")
    assert untracked.old_content == ""
    assert untracked.new_content == "new file\n"

    nested = tmp_path / "nested"
    nested.mkdir()
    assert get_git_status(nested).is_repository is False
    with pytest.raises(AgentTerminalGitError, match="agent_terminal.git_path_invalid"):
        get_git_diff(tmp_path, path="../outside.txt", scope="unstaged")


def test_git_history_refs_stashes_and_commit_diff_are_read_only_head_views(
    tmp_path: Path,
) -> None:
    _initialize_git_repository(tmp_path)
    first_commit = _git_output(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "remote", "add", "origin", str(tmp_path))
    _git(tmp_path, "update-ref", "refs/remotes/origin/dev", first_commit)
    _git(tmp_path, "branch", "--set-upstream-to=origin/dev", "dev")
    _git(tmp_path, "branch", "archive", first_commit)
    _git(tmp_path, "tag", "v1.0.0", first_commit)

    (tmp_path / "tracked.txt").write_text("second commit\n", encoding="utf-8")
    (tmp_path / "added.txt").write_text("added in second\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt", "added.txt")
    _git(tmp_path, "commit", "-m", "second commit")
    second_commit = _git_output(tmp_path, "rev-parse", "HEAD")

    _git(tmp_path, "switch", "-c", "other")
    (tmp_path / "other.txt").write_text("other branch\n", encoding="utf-8")
    _git(tmp_path, "add", "other.txt")
    _git(tmp_path, "commit", "-m", "other branch only")
    other_commit = _git_output(tmp_path, "rev-parse", "HEAD")
    _git(tmp_path, "switch", "dev")

    (tmp_path / "staged.txt").write_text("stashed work\n", encoding="utf-8")
    _git(tmp_path, "stash", "push", "-m", "saved work")

    status_response = get_git_status(tmp_path)
    assert status_response.upstream == "origin/dev"
    assert status_response.ahead == 1
    assert status_response.behind == 0

    summary = get_git_summary(tmp_path)
    assert summary.is_repository is True
    assert {(item.kind, item.name) for item in summary.refs} >= {
        ("local_branch", "dev"),
        ("local_branch", "other"),
        ("remote_branch", "origin/dev"),
        ("tag", "v1.0.0"),
    }
    assert next(item for item in summary.refs if item.name == "dev").current is True
    assert summary.stashes[0].ref == "stash@{0}"
    assert "saved work" in summary.stashes[0].subject

    history = get_git_history(tmp_path, limit=1)
    assert [item.sha for item in history.items] == [second_commit]
    assert history.has_more is True
    next_page = get_git_history(tmp_path, offset=1, limit=1)
    assert [item.sha for item in next_page.items] == [first_commit]

    detail = get_git_commit_detail(tmp_path, commit=second_commit)
    assert detail.subject == "second commit"
    assert {(item.path, item.kind) for item in detail.files} == {
        ("added.txt", "added"),
        ("tracked.txt", "modified"),
    }
    diff = get_git_commit_diff(
        tmp_path,
        commit=second_commit,
        path="tracked.txt",
    )
    assert diff.old_content == "original\n"
    assert diff.new_content == "second commit\n"

    with pytest.raises(AgentTerminalGitError, match="git_commit_not_found"):
        get_git_commit_detail(tmp_path, commit=other_commit)


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_runtime_keeps_tmux_session_across_api_runtime_restart(tmp_path: Path) -> None:
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        "printf 'ready\\n'\n"
        "while IFS= read -r line; do printf 'echo:%s\\n' \"$line\"; done\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)
    settings = _settings(
        tmp_path,
        agent_terminal_codex_bin=str(fake_codex),
        instance_id=f"agent-terminal-test-{tmp_path.name}",
    )
    runtime = AgentTerminalRuntime(settings, sessionmaker())
    runtime._mark_started = lambda _session_id, _pid: None  # type: ignore[method-assign]
    runtime._mark_finished = (  # type: ignore[method-assign]
        lambda _session_id, _status, _exit_code: None
    )

    async def wait_for_pane_size(
        active_runtime: AgentTerminalRuntime,
        expected: tuple[int, int],
    ) -> None:
        pane = None
        for _attempt in range(50):
            pane = await active_runtime._inspect_tmux_session("session-1")
            if pane is not None and (pane.cols, pane.rows) == expected:
                return
            await asyncio.sleep(0.02)
        assert pane is not None
        assert (pane.cols, pane.rows) == expected

    async def exercise() -> None:
        await runtime.start(
            session_id="session-1",
            owner_id="admin-1",
            root_path=tmp_path,
            cols=100,
            rows=30,
        )
        await runtime.resize("session-1", cols=140, rows=40)
        await wait_for_pane_size(runtime, (140, 40))
        queue, replay, active = runtime.subscribe("session-1")
        assert active is True
        output = bytearray(replay)
        while b"ready" not in output:
            chunk = await asyncio.wait_for(queue.get(), timeout=2)
            assert chunk is not None
            output.extend(chunk)

        await runtime.write("session-1", b"hello\n")
        while b"hello" not in output:
            chunk = await asyncio.wait_for(queue.get(), timeout=2)
            assert chunk is not None
            output.extend(chunk)

        reconnect_queue, reconnect_replay, reconnect_active = runtime.subscribe("session-1")
        assert reconnect_active is True
        assert b"ready" in reconnect_replay
        assert b"hello" in reconnect_replay
        runtime.unsubscribe("session-1", reconnect_queue)
        runtime.unsubscribe("session-1", queue)

        return_code, _output = await runtime._run_tmux(
            "set-window-option",
            "-t",
            runtime._tmux_target("session-1"),
            "window-size",
            "manual",
        )
        assert return_code == 0
        await runtime.shutdown()
        assert runtime.is_active("session-1") is False

        restarted_runtime = AgentTerminalRuntime(settings, sessionmaker())
        restarted_runtime._load_active_sessions = (  # type: ignore[method-assign]
            lambda: (("session-1", "admin-1"),)
        )
        restarted_runtime._mark_recovered = (  # type: ignore[method-assign]
            lambda _session_id, _pid: None
        )
        restarted_runtime._mark_finished = (  # type: ignore[method-assign]
            lambda _session_id, _status, _exit_code: None
        )
        await restarted_runtime.startup()
        return_code, output = await restarted_runtime._run_tmux(
            "show-window-options",
            "-v",
            "-t",
            restarted_runtime._tmux_target("session-1"),
            "window-size",
        )
        assert return_code == 0
        assert output.strip() == b"latest"
        queue, replay, active = restarted_runtime.subscribe("session-1")
        assert active is True
        output = bytearray(replay)
        await restarted_runtime.write("session-1", b"after-restart\n")
        while b"after-restart" not in output:
            chunk = await asyncio.wait_for(queue.get(), timeout=2)
            assert chunk is not None
            output.extend(chunk)

        restarted_runtime.unsubscribe("session-1", queue)
        await restarted_runtime.terminate("session-1")
        assert restarted_runtime.is_active("session-1") is False
        await restarted_runtime.shutdown()

    asyncio.run(exercise())


def test_runtime_startup_marks_missing_tmux_sessions_failed(
    client: TestClient,
) -> None:
    admin = dev_login(client, "administrator")
    session_id = "orphaned-terminal-session"
    now = utcnow_naive()
    with get_session_factory()() as db:
        db.add(
            AgentTerminalSession(
                id=session_id,
                owner_id=admin["user"]["id"],
                root_key="test-project",
                root_path="/tmp/test-project",
                status="running",
                runtime_instance_id="previous-api-process",
                pid=1234,
                created_at=now,
                started_at=now,
                updated_at=now,
            )
        )
        db.commit()

    runtime = client.app.state.agent_terminal_runtime
    runtime._settings.agent_terminal_enabled = True

    async def missing_tmux_session(_session_id: str) -> None:
        return None

    runtime._inspect_tmux_session = missing_tmux_session  # type: ignore[method-assign]
    asyncio.run(runtime.startup())

    with get_session_factory()() as db:
        row = db.get(AgentTerminalSession, session_id)
        audit_row = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == session_id,
                AuditLog.action == "agent_terminal.session.finish",
            )
        )
    assert row is not None
    assert row.status == "failed"
    assert row.failure_code == "agent_terminal.tmux_session_lost"
    assert row.ended_at is not None
    assert audit_row is not None
    assert audit_row.actor_user_id is None
    assert audit_row.payload["previous_status"] == "running"


def test_admin_can_reconnect_to_owned_codex_session_without_transcript_audit(
    client: TestClient,
    tmp_path: Path,
) -> None:
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        "printf 'ready\\n'\n"
        "while IFS= read -r line; do printf 'echo:%s\\n' \"$line\"; done\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o700)

    from open_work_hub_api.core.settings import get_settings

    settings = get_settings()
    settings.agent_terminal_enabled = True
    settings.agent_terminal_allowed_roots = {"test-project": str(tmp_path)}
    settings.agent_terminal_codex_bin = str(fake_codex)
    runtime = client.app.state.agent_terminal_runtime
    runtime._settings.agent_terminal_enabled = True
    runtime._settings.agent_terminal_allowed_roots = {"test-project": str(tmp_path)}
    runtime._settings.agent_terminal_codex_bin = str(fake_codex)

    admin = dev_login(client, "administrator")
    member = dev_login(client, "delivery-hub-member")
    admin_headers = auth_headers(admin["token"])
    member_headers = auth_headers(member["token"])

    admin_apps = client.get("/api/v1/apps/bootstrap", headers=admin_headers)
    member_apps = client.get("/api/v1/apps/bootstrap", headers=member_headers)
    assert admin_apps.status_code == 200
    assert member_apps.status_code == 200
    assert "agent-terminal" in admin_apps.json()["personal_tool_app_ids"]
    assert "agent-terminal" not in member_apps.json()["personal_tool_app_ids"]
    assert client.get("/api/v1/agent-terminal/config", headers=member_headers).status_code == 403

    _initialize_git_repository(tmp_path)
    (tmp_path / "tracked.txt").write_text("changed by Codex\n", encoding="utf-8")
    git_status_response = client.get(
        "/api/v1/agent-terminal/roots/test-project/git/status",
        headers=admin_headers,
    )
    assert git_status_response.status_code == 200, git_status_response.text
    assert git_status_response.json()["branch"] == "dev"
    assert {(item["path"], item["scope"]) for item in git_status_response.json()["changes"]} >= {
        ("tracked.txt", "unstaged")
    }
    assert (
        client.get(
            "/api/v1/agent-terminal/roots/test-project/git/status",
            headers=member_headers,
        ).status_code
        == 403
    )
    git_diff_response = client.get(
        "/api/v1/agent-terminal/roots/test-project/git/diff",
        headers=admin_headers,
        params={"path": "tracked.txt", "scope": "unstaged"},
    )
    assert git_diff_response.status_code == 200, git_diff_response.text
    assert git_diff_response.json()["old_content"] == "original\n"
    assert git_diff_response.json()["new_content"] == "changed by Codex\n"
    assert (
        client.get(
            "/api/v1/agent-terminal/roots/test-project/git/diff",
            headers=admin_headers,
            params={"path": "../outside.txt", "scope": "unstaged"},
        ).status_code
        == 400
    )
    git_summary_response = client.get(
        "/api/v1/agent-terminal/roots/test-project/git/summary",
        headers=admin_headers,
    )
    assert git_summary_response.status_code == 200, git_summary_response.text
    assert {(item["kind"], item["name"]) for item in git_summary_response.json()["refs"]} >= {
        ("local_branch", "dev")
    }
    git_history_response = client.get(
        "/api/v1/agent-terminal/roots/test-project/git/history",
        headers=admin_headers,
        params={"limit": 10},
    )
    assert git_history_response.status_code == 200, git_history_response.text
    history_commit = git_history_response.json()["items"][0]
    commit_detail_response = client.get(
        f"/api/v1/agent-terminal/roots/test-project/git/commits/{history_commit['sha']}",
        headers=admin_headers,
    )
    assert commit_detail_response.status_code == 200, commit_detail_response.text
    assert {item["path"] for item in commit_detail_response.json()["files"]} == {
        "staged.txt",
        "tracked.txt",
    }
    commit_diff_response = client.get(
        f"/api/v1/agent-terminal/roots/test-project/git/commits/{history_commit['sha']}/diff",
        headers=admin_headers,
        params={"path": "tracked.txt"},
    )
    assert commit_diff_response.status_code == 200, commit_diff_response.text
    assert commit_diff_response.json()["old_content"] == ""
    assert commit_diff_response.json()["new_content"] == "original\n"
    assert (
        client.get(
            "/api/v1/agent-terminal/roots/test-project/git/history",
            headers=member_headers,
        ).status_code
        == 403
    )

    config_response = client.get(
        "/api/v1/agent-terminal/config",
        headers=admin_headers,
    )
    assert config_response.status_code == 200, config_response.text
    assert config_response.json()["tmux_available"] is (shutil.which("tmux") is not None)
    assert config_response.json()["roots"] == [
        {
            "key": "test-project",
            "label": "Test Project",
            "path": str(tmp_path.resolve()),
        }
    ]

    if shutil.which("tmux") is None:
        pytest.skip("tmux is not installed")

    create_response = client.post(
        "/api/v1/agent-terminal/sessions",
        headers=admin_headers,
        json={"root_key": "test-project", "cols": 100, "rows": 30},
    )
    assert create_response.status_code == 201, create_response.text
    session = create_response.json()
    session_id = session["id"]
    websocket_path = f"/api/v1/agent-terminal/sessions/{session_id}/ws"

    with client.websocket_connect(websocket_path) as websocket:
        websocket.send_json({"type": "auth", "token": admin["token"]})
        assert websocket.receive_json() == {"type": "ready", "active": True}
        replay_message = websocket.receive_json()
        assert replay_message["type"] == "replay"
        output = base64.b64decode(replay_message["data"])
        while b"ready" not in output:
            output_message = websocket.receive_json()
            assert output_message["type"] == "output"
            output += base64.b64decode(output_message["data"])
        assert b"ready" in output
        websocket.send_json(
            {
                "type": "input",
                "data": base64.b64encode(b"hello\n").decode("ascii"),
            }
        )
        while b"hello" not in output:
            output += base64.b64decode(websocket.receive_json()["data"])

    with client.websocket_connect(websocket_path) as websocket:
        websocket.send_json({"type": "auth", "token": admin["token"]})
        assert websocket.receive_json() == {"type": "ready", "active": True}
        replay_message = websocket.receive_json()
        assert replay_message["type"] == "replay"
        replay = base64.b64decode(replay_message["data"])
        assert b"hello" in replay

    active_delete_response = client.delete(
        f"/api/v1/agent-terminal/sessions/{session_id}",
        headers=admin_headers,
    )
    assert active_delete_response.status_code == 409

    stop_response = client.post(
        f"/api/v1/agent-terminal/sessions/{session_id}/stop",
        headers=admin_headers,
    )
    assert stop_response.status_code == 200, stop_response.text
    assert stop_response.json()["status"] == "terminated"

    runtime.forget(session_id)
    with client.websocket_connect(websocket_path) as websocket:
        websocket.send_json({"type": "auth", "token": admin["token"]})
        assert websocket.receive_json() == {"type": "ready", "active": False}
        assert websocket.receive_json() == {"type": "exit"}

    delete_response = client.delete(
        f"/api/v1/agent-terminal/sessions/{session_id}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 204, delete_response.text
    sessions_response = client.get(
        "/api/v1/agent-terminal/sessions",
        headers=admin_headers,
    )
    assert sessions_response.status_code == 200
    assert session_id not in {item["id"] for item in sessions_response.json()["items"]}

    with get_session_factory()() as db:
        assert db.get(AgentTerminalSession, session_id) is None
        audit_rows = db.scalars(select(AuditLog).where(AuditLog.entity_id == session_id)).all()
    assert {row.action for row in audit_rows} >= {
        "agent_terminal.session.start",
        "agent_terminal.session.stop",
        "agent_terminal.session.finish",
        "agent_terminal.session.delete",
    }
    assert "hello" not in repr([row.payload for row in audit_rows])
