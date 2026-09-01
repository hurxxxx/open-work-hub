from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.app_contracts_generated import APP_CONTRACT_BY_ID
from open_work_hub_api.core.settings import HERMES_MODEL, HERMES_PROVIDER, Settings
from open_work_hub_api.domains.auth.models import User, Workspace, utcnow_naive
from open_work_hub_api.domains.hermes.models import HermesProfileBinding
from open_work_hub_api.domains.hermes_terminal.app_catalog import HERMES_TERMINAL_APP
from open_work_hub_api.domains.hermes_terminal import lifecycle, maintenance, mcp_router
from open_work_hub_api.domains.hermes_terminal.broker_runtime import (
    BrokerRuntimeError,
    HermesTerminalBrokerRuntime,
    build_profile_config_commands,
    build_profile_sanitize_commands,
    build_runner_command,
    build_runner_environment,
    build_runner_mounts,
)
from open_work_hub_api.domains.hermes_terminal.schemas import (
    HermesTerminalSessionCreateRequest,
)
from open_work_hub_api.domains.hermes_terminal.models import HermesTerminalSession
from open_work_hub_api.domains.hermes_terminal.mcp_socket_server import (
    HermesTerminalMcpSocketServer,
)
from open_work_hub_api.domains.hermes_terminal.security import (
    broker_bearer_token,
    normalize_relative_path,
    terminal_profile_name,
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"postgres_dsn": "sqlite://"}
    values.update(overrides)
    with patch.dict(os.environ, {}, clear=True):
        return Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_catalog_exposes_a_workspace_personal_app_to_all_members() -> None:
    assert HERMES_TERMINAL_APP.app_id == "hermes-terminal"
    assert HERMES_TERMINAL_APP.availability_scope == "workspace"
    assert APP_CONTRACT_BY_ID["hermes-terminal"]["resource_scope"] == "personal"
    assert HERMES_TERMINAL_APP.required_system_roles == ()
    assert HERMES_TERMINAL_APP.feature_flag == "hermes_enabled"


def test_standard_and_yolo_commands_use_only_official_hermes_flags() -> None:
    standard = build_runner_command("standard")
    yolo = build_runner_command("yolo")

    assert standard == [
        "chat",
        "--tui",
        "--in",
        "/workspace",
        "--checkpoints",
        "--provider",
        HERMES_PROVIDER,
        "--model",
        HERMES_MODEL,
    ]
    assert "--yolo" not in standard
    assert yolo == [*standard, "--yolo"]
    with pytest.raises(BrokerRuntimeError, match="hermes_terminal.mode_invalid"):
        build_runner_command("unsafe-default")


def test_yolo_requires_a_fresh_explicit_acknowledgement() -> None:
    assert HermesTerminalSessionCreateRequest().mode == "standard"
    with pytest.raises(ValidationError, match="explicit risk acknowledgement"):
        HermesTerminalSessionCreateRequest(mode="yolo")
    request = HermesTerminalSessionCreateRequest(mode="yolo", risk_acknowledged=True)
    assert request.mode == "yolo"
    assert request.risk_acknowledged is True


def test_profile_configuration_disables_fallback_without_model_rewriting() -> None:
    commands = build_profile_config_commands(
        mcp_url="http://hermes-terminal-broker:18765/mcp/session-id",
        proxy_token="proxy-token-for-test-00000001",
        mcp_token="session-token-for-test-00000001",
    )
    serialized = json.dumps(commands)
    mcp_command = next(command for command in commands if command[-2] == "mcp_servers")
    mcp_servers = json.loads(mcp_command[-1])

    assert all(command[0] == "/opt/hermes/.venv/bin/hermes" for command in commands)
    assert ["/opt/hermes/.venv/bin/hermes", "config", "unset", "fallback_model"] in commands
    assert "fallback_providers" in serialized
    assert HERMES_MODEL in serialized
    assert [
        "/opt/hermes/.venv/bin/hermes",
        "config",
        "set",
        "--force",
        "display.mouse_tracking",
        "off",
    ] in commands
    assert mcp_servers["open-work-hub"]["trust"] == "full"
    assert "google/gemini" not in serialized
    assert "rewrite" not in serialized.lower()


def test_runner_environment_uses_official_workspace_and_browser_tui_settings() -> None:
    environment = build_runner_environment(proxy_token="proxy-token")

    assert environment["HERMES_WRITE_SAFE_ROOT"] == "/workspace"
    assert environment["HERMES_TUI_DISABLE_MOUSE"] == "1"
    assert environment["OPENROUTER_API_KEY"] == "proxy-token"


def test_profile_export_removes_only_ephemeral_session_credentials() -> None:
    assert build_profile_sanitize_commands() == [
        [
            "/opt/hermes/.venv/bin/hermes",
            "config",
            "unset",
            "OPENROUTER_API_KEY",
        ],
        [
            "/opt/hermes/.venv/bin/hermes",
            "config",
            "unset",
            "MCP_OPEN_WORK_HUB_API_KEY",
        ],
    ]


def test_profile_cli_uses_runner_identity_and_repairs_only_ownership() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    class FakeContainer:
        def exec_run(self, command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(exit_code=0, output=b"ok")

    container = FakeContainer()
    HermesTerminalBrokerRuntime._exec_ok(  # type: ignore[arg-type]
        container,
        ["hermes", "config", "check"],
    )
    HermesTerminalBrokerRuntime._chown_profile_path(  # type: ignore[arg-type]
        container,
        "/opt/data/profiles/terminal",
        recursive=True,
    )

    assert calls == [
        (["hermes", "config", "check"], {"environment": None, "user": "10000:10000"}),
        (
            ["chown", "-R", "10000:10000", "/opt/data/profiles/terminal"],
            {"user": "0:0"},
        ),
    ]


def test_runner_volumes_disable_image_copy_up_and_keep_egress_read_only() -> None:
    mounts = build_runner_mounts(
        profile_volume_name="profile-volume",
        workspace_volume_name="workspace-volume",
        egress_client_volume="egress-volume",
    )

    assert [dict(mount) for mount in mounts] == [
        {
            "Target": "/opt/data",
            "Source": "profile-volume",
            "Type": "volume",
            "ReadOnly": False,
            "VolumeOptions": {"NoCopy": True},
        },
        {
            "Target": "/workspace",
            "Source": "workspace-volume",
            "Type": "volume",
            "ReadOnly": False,
            "VolumeOptions": {"NoCopy": True},
        },
        {
            "Target": "/run/owh-egress",
            "Source": "egress-volume",
            "Type": "volume",
            "ReadOnly": True,
            "VolumeOptions": {"NoCopy": True},
        },
    ]


def test_private_profile_identity_and_paths_are_stable_and_contained() -> None:
    profile = terminal_profile_name("binding-1")
    assert profile == terminal_profile_name("binding-1")
    assert profile != terminal_profile_name("binding-2")
    assert len(profile) <= 63
    assert normalize_relative_path("reports/result.pdf") == "reports/result.pdf"
    for value in ("/etc/passwd", "../secret", "folder/../secret", "folder\\..\\secret"):
        with pytest.raises(ValueError):
            normalize_relative_path(value, allow_root=False)


def test_terminal_mcp_call_ids_are_bounded_and_stable() -> None:
    oversized = "request-" * 100

    normalized = mcp_router._normalized_call_id(oversized)

    assert normalized == mcp_router._normalized_call_id(oversized)
    assert normalized.startswith("sha256:")
    assert len(normalized) <= 256


def test_broker_auth_is_derived_without_exposing_the_root_secret() -> None:
    root_secret = "terminal-test-mcp-secret-00000000000000000001"
    settings = _settings(hermes_mcp_shared_secret=root_secret)
    token = broker_bearer_token(settings)

    assert len(token) == 64
    assert root_secret not in token
    assert token == broker_bearer_token(settings)


def test_terminal_limits_default_to_two_hours_and_thirty_days() -> None:
    settings = _settings()

    assert settings.hermes_terminal_idle_timeout_seconds == 7200
    assert settings.hermes_terminal_artifact_retention_days == 30
    assert settings.hermes_terminal_max_sessions_per_workspace_user == 1
    assert settings.hermes_terminal_max_sessions_per_user == 2


def test_terminal_mcp_socket_is_rooted_independently_of_process_cwd() -> None:
    settings = _settings(
        hermes_terminal_mcp_socket_path=".runtime/hermes-terminal-test.sock"
    )

    path = Path(settings.hermes_terminal_mcp_socket_path)
    assert path.is_absolute()
    assert path.parts[-2:] == (".runtime", "hermes-terminal-test.sock")


def test_terminal_mcp_socket_has_one_owner_and_safe_shared_shutdown(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        socket_path = tmp_path / "hermes-terminal.sock"
        settings = _settings(
            hermes_enabled=True,
            hermes_api_key="test-hermes-api-key",
            hermes_management_token="test-management-token",
            hermes_mcp_server_url="http://127.0.0.1:8642/mcp",
            hermes_mcp_shared_secret="test-mcp-shared-secret-0000000001",
            hermes_terminal_mcp_socket_path=str(socket_path),
        )
        owner = HermesTerminalMcpSocketServer(settings)
        shared = HermesTerminalMcpSocketServer(settings)

        await owner.startup()
        await shared.startup()
        try:
            assert owner._socket_identity is not None
            assert shared._shared_socket is True

            await shared.shutdown()

            assert socket_path.is_socket()
            assert await owner._socket_is_healthy()
        finally:
            await shared.shutdown()
            await owner.shutdown()

        assert not socket_path.exists()

    asyncio.run(exercise())


def test_starting_session_adopts_a_runtime_after_an_ambiguous_create_response(
    monkeypatch,
) -> None:
    row = SimpleNamespace(
        status="starting",
        runtime_handle=None,
        broker_instance_id=None,
        failure_code="hermes_terminal.broker_unavailable",
        archive_target_status=None,
        started_at=None,
        updated_at=None,
    )

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalar(self, _statement):
            return row

        def add(self, _value):
            return None

        def commit(self):
            return None

    db = FakeDb()
    monkeypatch.setattr(lifecycle, "get_session_factory", lambda: lambda: db)

    lifecycle._adopt_terminal_runtime(
        "session-1",
        SimpleNamespace(
            runtime_handle="container-1",
            broker_instance_id="broker-1",
            status="running",
        ),
    )

    assert row.status == "running"
    assert row.runtime_handle == "container-1"
    assert row.broker_instance_id == "broker-1"
    assert row.failure_code is None
    assert row.started_at is not None


def test_archiving_session_recovers_when_an_exited_runtime_restarts(
    monkeypatch,
) -> None:
    ended_at = utcnow_naive()
    row = SimpleNamespace(
        status="archiving",
        runtime_handle="container-old",
        broker_instance_id="broker-old",
        failure_code=None,
        exit_code=0,
        ended_at=ended_at,
        archive_target_status="exited",
        archive_attempts=1,
        archive_started_at=ended_at,
        archive_failure_code="hermes_terminal.archive_failed",
        updated_at=ended_at,
    )

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalar(self, _statement):
            return row

        def add(self, _value):
            return None

        def commit(self):
            return None

    monkeypatch.setattr(lifecycle, "get_session_factory", lambda: lambda: FakeDb())

    lifecycle._adopt_terminal_runtime(
        "session-1",
        SimpleNamespace(
            runtime_handle="container-current",
            broker_instance_id="broker-current",
            status="running",
        ),
    )

    assert row.status == "running"
    assert row.runtime_handle == "container-current"
    assert row.broker_instance_id == "broker-current"
    assert row.exit_code is None
    assert row.ended_at is None
    assert row.archive_target_status is None
    assert row.archive_attempts == 0
    assert row.archive_started_at is None
    assert row.archive_failure_code is None


def test_consumed_write_approval_fails_closed_without_waiting(monkeypatch) -> None:
    approval = SimpleNamespace(
        status="approved",
        consumed_at=object(),
        external_call_id="external-call-1",
        expires_at=object(),
        session_id="session-1",
    )
    session = SimpleNamespace(status="running")

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def scalar(self, _statement):
            return approval

        def get(self, _model, _identifier):
            return session

        def commit(self):
            return None

    db = FakeDb()
    monkeypatch.setattr(mcp_router, "get_session_factory", lambda: lambda: db)

    assert mcp_router._consume_approved_call("approval-1") == (None, "consumed")


def test_approval_state_returns_to_running_only_after_all_pending_calls_close() -> None:
    session = SimpleNamespace(status="awaiting_approval")

    class FakeDb:
        def __init__(self, pending_id):
            self.pending_id = pending_id
            self.added = []

        def scalar(self, _statement):
            return self.pending_id

        def get(self, _model, _identifier):
            return session

        def add(self, value):
            self.added.append(value)

    now = utcnow_naive()
    pending_db = FakeDb("approval-2")
    mcp_router._restore_running_if_no_pending_approval(
        pending_db,  # type: ignore[arg-type]
        session_id="session-1",
        now=now,
    )
    assert session.status == "awaiting_approval"

    closed_db = FakeDb(None)
    mcp_router._restore_running_if_no_pending_approval(
        closed_db,  # type: ignore[arg-type]
        session_id="session-1",
        now=now,
    )
    assert session.status == "running"
    assert closed_db.added == [session]


def test_write_tool_access_is_revalidated_after_approval(monkeypatch) -> None:
    identity = SimpleNamespace(
        session=SimpleNamespace(id="session-1", allowed_app_ids=["tasks"]),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
    )
    tool = SimpleNamespace(
        descriptor=SimpleNamespace(
            name="tasks.create",
            approval_policy="required",
            workspace_app_id="tasks",
        ),
        mcp_tool={"name": "tasks.create"},
    )
    resolve_calls: list[str] = []
    list_calls: list[str] = []
    tool_calls: list[str] = []

    def resolve_identity(_db, *, session_id, authorization):
        assert authorization == "Bearer session-token"
        resolve_calls.append(session_id)
        return identity

    def available_tools(_db, resolved_identity):
        assert resolved_identity is identity
        list_calls.append(resolved_identity.session.id)
        return SimpleNamespace(kind="user"), [tool]

    async def await_approval(_approval_id):
        return "external-call-1", "approved"

    class FakeMcpClient:
        def call_tool(self, _db, **kwargs):
            tool_calls.append(kwargs["tool_name"])
            assert kwargs["externally_approved_call_id"] == "external-call-1"
            return {"ok": True}

    class FakeDb:
        def expire_all(self):
            return None

        def get(self, model, _identifier):
            if model.__name__ == "Workspace":
                return identity.workspace
            if model.__name__ == "User":
                return identity.user
            return None

        def commit(self):
            return None

        def rollback(self):
            raise AssertionError("The successful tool path must not roll back")

    class FakeRequest:
        async def json(self):
            return {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "tasks.create",
                    "arguments": {"title": "Ship"},
                },
            }

    monkeypatch.setattr(mcp_router, "_resolve_identity", resolve_identity)
    monkeypatch.setattr(mcp_router, "_available_tools", available_tools)
    monkeypatch.setattr(
        mcp_router,
        "_approval_for_call",
        lambda *_args, **_kwargs: SimpleNamespace(id="approval-1"),
    )
    monkeypatch.setattr(mcp_router, "_await_approval", await_approval)
    monkeypatch.setattr(mcp_router, "AiMcpClient", FakeMcpClient)

    response = asyncio.run(
        mcp_router.handle_mcp_request(
            FakeRequest(),  # type: ignore[arg-type]
            session="session-1",
            authorization="Bearer session-token",
            mcp_session_id=None,
            db=FakeDb(),  # type: ignore[arg-type]
        )
    )
    payload = json.loads(bytes(response.body))

    assert resolve_calls == ["session-1", "session-1"]
    assert list_calls == ["session-1", "session-1"]
    assert tool_calls == ["tasks.create"]
    assert payload["result"]["isError"] is False


def test_archive_recovery_reclaims_stale_sessions_without_releasing_early(
    application_postgres_dsn: str,
    monkeypatch,
) -> None:
    engine = create_engine(application_postgres_dsn)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(maintenance, "get_session_factory", lambda: session_factory)
    now = utcnow_naive()
    stale = now - timedelta(minutes=15)
    suffix = uuid4().hex
    workspace = Workspace(
        id=str(uuid4()),
        key=f"hermes-terminal-{suffix[:16]}",
        name="Hermes terminal recovery",
    )
    user = User(
        id=str(uuid4()),
        login_id=f"hermes-terminal-{suffix[:16]}",
        email=f"hermes-terminal-{suffix[:16]}@example.test",
        full_name="Hermes Terminal Recovery",
        password_hash="not-used",
    )
    binding = HermesProfileBinding(
        id=str(uuid4()),
        workspace_id=workspace.id,
        user_id=user.id,
        profile_name=f"owh-terminal-{suffix[:24]}",
        status="active",
        provider=HERMES_PROVIDER,
        model=HERMES_MODEL,
    )
    row = HermesTerminalSession(
        id=str(uuid4()),
        profile_binding_id=binding.id,
        workspace_id=workspace.id,
        user_id=user.id,
        title="Recovery session",
        mode="standard",
        status="archiving",
        allowed_app_ids=[],
        runtime_handle=f"runtime-{suffix}",
        broker_instance_id="test-broker",
        mcp_token_digest="a" * 64,
        cols=120,
        rows=32,
        archive_target_status="terminated",
        archive_attempts=1,
        archive_started_at=stale,
        last_activity_at=stale,
        idle_expires_at=stale,
        created_at=stale,
        updated_at=stale,
    )
    row_id = row.id
    user_id = user.id
    runtime_handle = row.runtime_handle
    try:
        with Session(engine) as db:
            db.add_all([workspace, user, binding, row])
            db.commit()

        claimed = maintenance._claim_archive_retries(limit=1)

        assert claimed == [(row_id, "terminated", None, user_id)]
        with Session(engine) as db:
            stored = db.get(HermesTerminalSession, row_id)
            assert stored is not None
            assert stored.status == "archiving"
            assert stored.runtime_handle == runtime_handle
            stored.archive_attempts = 3
            stored.archive_failure_code = maintenance.HERMES_TERMINAL_ARCHIVE_FAILURE
            stored.updated_at = stale
            db.add(stored)
            db.commit()

        assert maintenance._abandon_exhausted_archives(limit=1) == 1
        assert maintenance._runtime_release_candidates(limit=1) == [(row_id, True)]
        with Session(engine) as db:
            stored = db.get(HermesTerminalSession, row_id)
            assert stored is not None
            assert stored.status == "terminated"
            assert stored.archive_failure_code == "hermes_terminal.archive_failed"
    finally:
        engine.dispose()
