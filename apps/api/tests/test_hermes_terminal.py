from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import tarfile
import threading
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from docker.errors import DockerException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.app_contracts_generated import APP_CONTRACT_BY_ID
from open_work_hub_api.core.settings import (
    HERMES_FALLBACK_MODEL,
    HERMES_MODEL,
    HERMES_PROVIDER,
    Settings,
)
from open_work_hub_api.domains.auth.models import User, Workspace, utcnow_naive
from open_work_hub_api.domains.hermes.models import HermesProfileBinding
from open_work_hub_api.domains.hermes.research_sources import (
    DEFAULT_RESEARCH_SOURCE_POLICY,
)
from open_work_hub_api.domains.hermes_terminal.app_catalog import HERMES_TERMINAL_APP
from open_work_hub_api.domains.hermes_terminal import (
    broker_app,
    lifecycle,
    maintenance,
    mcp_router,
    storage,
)
from open_work_hub_api.domains.hermes_terminal.broker_runtime import (
    BrokerRuntimeError,
    HermesTerminalBrokerRuntime,
    RuntimeSession,
    build_profile_config_commands,
    build_profile_export_cleanup_commands,
    build_profile_sanitize_commands,
    build_runner_command,
    build_runner_environment,
    build_runner_io_options,
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


def test_broker_image_packages_research_source_policy_module() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    dockerfile = (repository_root / "ops/hermes-terminal-broker/Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "domains/hermes/__init__.py" in dockerfile
    assert "domains/hermes/research_sources.py" in dockerfile


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


def test_broker_rejects_invalid_numeric_runtime_settings(monkeypatch) -> None:
    monkeypatch.setenv("OWH_HERMES_TERMINAL_WORKSPACE_LIVE_MAX_BYTES", "invalid")

    with pytest.raises(BrokerRuntimeError, match="runtime_setting_invalid"):
        HermesTerminalBrokerRuntime._environment_int(
            "OWH_HERMES_TERMINAL_WORKSPACE_LIVE_MAX_BYTES",
            1024,
        )


def test_broker_dependency_api_failure_is_reported_as_unavailable() -> None:
    class FailingImages:
        def get(self, _image: str):
            raise DockerException("daemon unavailable")

    runtime = object.__new__(HermesTerminalBrokerRuntime)
    runtime.image = "pinned-image"
    runtime.network_name = "sandbox"
    runtime.egress_client_volume = "egress"
    runtime.egress_client_dir = "/not-used"
    runtime.client = SimpleNamespace(
        images=FailingImages(),
        networks=SimpleNamespace(),
        volumes=SimpleNamespace(),
    )

    with pytest.raises(BrokerRuntimeError, match="docker_unavailable"):
        runtime._ensure_dependencies()


def test_broker_normalizes_reload_failures_and_naive_resource_timestamps() -> None:
    class MissingContainer:
        def reload(self):
            raise DockerException("daemon unavailable")

    with pytest.raises(BrokerRuntimeError, match="docker_unavailable"):
        HermesTerminalBrokerRuntime._reload_container(MissingContainer())  # type: ignore[arg-type]

    created_at = HermesTerminalBrokerRuntime._created_at(
        SimpleNamespace(attrs={"Created": "2026-09-02T01:02:03"})
    )
    assert created_at is not None
    assert created_at.tzinfo is UTC


def test_forgetting_a_session_clears_forced_failure_state() -> None:
    session_id = str(uuid4())

    class FakeContainer:
        status = "exited"

        def reload(self):
            return None

        def remove(self, *, force: bool):
            assert force is True

    class FakeVolume:
        def remove(self, *, force: bool):
            assert force is True

    runtime = object.__new__(HermesTerminalBrokerRuntime)
    runtime.resource_namespace = "dev"
    runtime._forced_failure_codes = {session_id: "hermes_terminal.workspace_quota_exceeded"}
    runtime._find_container = lambda _session_id: (
        FakeContainer(),
        SimpleNamespace(workspace_volume_name="workspace-volume"),
    )
    runtime.client = SimpleNamespace(volumes=SimpleNamespace(get=lambda _name: FakeVolume()))

    runtime.forget_session(session_id)

    assert session_id not in runtime._forced_failure_codes


def test_partial_archive_upload_removes_every_ambiguous_attempt_object(
    monkeypatch,
) -> None:
    attempted: list[str] = []
    removed: list[str] = []
    monkeypatch.setattr(
        lifecycle,
        "collect_workspace_artifacts",
        lambda *_args, **_kwargs: SimpleNamespace(
            items=[
                ("first.txt", b"first", "text/plain", "a" * 64),
                ("second.txt", b"second", "text/plain", "b" * 64),
            ],
            archived_bytes=11,
            omitted_count=0,
        ),
    )

    def put(*, key: str, **_kwargs) -> None:
        attempted.append(key)
        if len(attempted) == 3:
            raise OSError("ambiguous object-store failure")

    monkeypatch.setattr(lifecycle, "put_object", put)
    monkeypatch.setattr(lifecycle, "remove_object", removed.append)

    with pytest.raises(OSError, match="ambiguous object-store failure"):
        lifecycle._persist_archive_objects(
            workspace_id="workspace-1",
            user_id="user-1",
            session_id="session-1",
            profile_archive=b"profile",
            workspace_archive=b"workspace",
            workspace_archive_max_bytes=1024,
            attempt_id="attempt-1",
        )

    assert len(attempted) == 3
    assert removed == attempted


def test_workspace_artifact_scan_reports_every_unsupported_or_duplicate_file() -> None:
    payload = BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:

        def add_file(path: str, data: bytes) -> None:
            info = tarfile.TarInfo(path)
            info.size = len(data)
            archive.addfile(info, BytesIO(data))

        add_file("workspace/result.txt", b"result")
        add_file("workspace/.owh-runtime/private", b"internal")
        link = tarfile.TarInfo("workspace/link.txt")
        link.type = tarfile.SYMTYPE
        link.linkname = "result.txt"
        archive.addfile(link)
        fifo = tarfile.TarInfo("workspace/pipe")
        fifo.type = tarfile.FIFOTYPE
        archive.addfile(fifo)
        add_file("workspace/../escape.txt", b"escape")
        add_file("workspace/result.txt", b"duplicate")

    scan = storage.collect_workspace_artifacts(
        payload.getvalue(),
        max_total_bytes=1024,
    )

    assert [item[0] for item in scan.items] == ["result.txt"]
    assert scan.archived_bytes == len(b"result")
    assert scan.omitted_count == 5


def test_workspace_artifact_scan_bounds_zero_byte_file_count(monkeypatch) -> None:
    payload = BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        for name in ("first.txt", "second.txt"):
            info = tarfile.TarInfo(f"workspace/{name}")
            info.size = 0
            archive.addfile(info, BytesIO())
    monkeypatch.setattr(storage, "MAX_ARTIFACT_FILES", 1)

    scan = storage.collect_workspace_artifacts(
        payload.getvalue(),
        max_total_bytes=1024,
    )

    assert [item[0] for item in scan.items] == ["first.txt"]
    assert scan.omitted_count == 1


def test_terminal_maintenance_serializes_archive_capable_operations() -> None:
    active = 0
    maximum_active = 0

    async def operation(value: int) -> int:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0)
        active -= 1
        return value

    results = asyncio.run(maintenance._gather_bounded([1, 2, 3], operation))

    assert results == [1, 2, 3]
    assert maximum_active == 1


def test_yolo_requires_a_fresh_explicit_acknowledgement() -> None:
    assert HermesTerminalSessionCreateRequest().mode == "standard"
    with pytest.raises(ValidationError, match="explicit risk acknowledgement"):
        HermesTerminalSessionCreateRequest(mode="yolo")
    request = HermesTerminalSessionCreateRequest(mode="yolo", risk_acknowledged=True)
    assert request.mode == "yolo"
    assert request.risk_acknowledged is True


def test_profile_configuration_applies_managed_resilience_policy() -> None:
    commands = build_profile_config_commands(
        mcp_url="http://hermes-terminal-broker:18765/mcp/session-id",
        proxy_token="proxy-token-for-test-00000001",
        mcp_token="session-token-for-test-00000001",
    )
    serialized = json.dumps(commands)
    values = {
        command[-2]: command[-1]
        for command in commands
        if command[1:4] == ["config", "set", "--force"]
    }
    mcp_command = next(command for command in commands if command[-2] == "mcp_servers")
    mcp_servers = json.loads(mcp_command[-1])

    assert all(command[0] == "/opt/hermes/.venv/bin/hermes" for command in commands)
    assert ["/opt/hermes/.venv/bin/hermes", "config", "unset", "fallback_model"] in commands
    assert "fallback_providers" in serialized
    assert HERMES_MODEL in serialized
    assert json.loads(values["fallback_providers"]) == [
        {"provider": HERMES_PROVIDER, "model": HERMES_FALLBACK_MODEL}
    ]
    assert json.loads(values["model.default_headers"]) == {"X-OpenRouter-Metadata": "enabled"}
    assert values["agent.api_max_retries"] == "1"
    assert "Semantic Scholar is disabled" in values["agent.environment_hint"]
    assert values["compression.threshold_tokens"] == "100000"
    assert values["compression.proactive_prune_tokens"] == "48000"
    assert values["provider_routing.sort"] == "throughput"
    assert values["provider_routing.require_parameters"] == "true"
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
    assert environment["XDG_CACHE_HOME"] == "/opt/data/cache"
    assert environment["UV_CACHE_DIR"] == "/opt/data/cache/uv"
    assert environment["OPENROUTER_API_KEY"] == "proxy-token"
    assert "semanticscholar.org" in environment["NO_PROXY"]
    assert environment["no_proxy"] == environment["NO_PROXY"]


def test_research_sources_are_individually_enabled_and_disabled() -> None:
    policy = dict(DEFAULT_RESEARCH_SOURCE_POLICY)
    policy["semantic_scholar"] = True
    policy["arxiv"] = False
    policy["crossref"] = False

    commands = build_profile_config_commands(
        mcp_url="http://hermes-terminal-broker:18765/mcp/session-id",
        proxy_token="proxy-token-for-test-00000001",
        mcp_token="session-token-for-test-00000001",
        research_sources=policy,
    )
    values = {
        command[-2]: command[-1]
        for command in commands
        if command[1:4] == ["config", "set", "--force"]
    }
    environment = build_runner_environment(
        proxy_token="proxy-token",
        research_sources=policy,
    )

    assert "arXiv, Crossref are disabled" in values["agent.environment_hint"]
    assert "Semantic Scholar, OpenAlex" in values["agent.environment_hint"]
    assert "arxiv.org" in environment["NO_PROXY"]
    assert "crossref.org" in environment["NO_PROXY"]
    assert "semanticscholar.org" not in environment["NO_PROXY"]
    assert "openalex.org" not in environment["NO_PROXY"]


def test_all_enabled_research_sources_remove_the_managed_hint() -> None:
    policy = {source_id: True for source_id in DEFAULT_RESEARCH_SOURCE_POLICY}
    commands = build_profile_config_commands(
        mcp_url="http://hermes-terminal-broker:18765/mcp/session-id",
        proxy_token="proxy-token-for-test-00000001",
        mcp_token="session-token-for-test-00000001",
        research_sources=policy,
    )

    assert [
        "/opt/hermes/.venv/bin/hermes",
        "config",
        "unset",
        "agent.environment_hint",
    ] in commands
    assert (
        build_runner_environment(
            proxy_token="proxy-token",
            research_sources=policy,
        )["NO_PROXY"]
        == "hermes-terminal-broker"
    )


def test_runner_keeps_a_reusable_detached_tty() -> None:
    assert build_runner_io_options() == {
        "detach": True,
        "stdin_open": True,
        "tty": True,
    }


@pytest.mark.parametrize(
    ("state", "expected_status", "expected_failure"),
    [
        ({"Status": "exited", "ExitCode": 0}, "exited", None),
        ({"Status": "exited", "ExitCode": 130}, "exited", None),
        (
            {"Status": "exited", "ExitCode": 137, "OOMKilled": True},
            "failed",
            "hermes_terminal.runner_oom",
        ),
        (
            {"Status": "dead", "ExitCode": 255},
            "failed",
            "hermes_terminal.runner_dead",
        ),
        (
            {"Status": "exited", "ExitCode": 2, "Error": "runtime error"},
            "failed",
            "hermes_terminal.runner_state_error",
        ),
    ],
)
def test_broker_classifies_terminal_exit_edges(
    state: dict[str, object],
    expected_status: str,
    expected_failure: str | None,
) -> None:
    container = SimpleNamespace(
        id="container-1",
        status=state["Status"],
        attrs={"State": state},
        reload=lambda: None,
    )
    record = RuntimeSession(
        session_id=str(uuid4()),
        profile_key="profilekey1234",
        container_name="runner",
        profile_volume_name="profile-volume",
        workspace_volume_name="workspace-volume",
        namespace="dev",
    )
    runtime = object.__new__(HermesTerminalBrokerRuntime)
    runtime.instance_id = "broker-test"
    runtime.resource_namespace = "dev"
    runtime._forced_failure_codes = {}
    runtime._find_container = lambda _session_id: (container, record)

    result = runtime.session_status(record.session_id)

    assert result["status"] == expected_status
    assert result["failure_code"] == expected_failure


def test_broker_reconciles_only_old_namespaced_orphan_workspaces() -> None:
    old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    class FakeVolume:
        name = "owh-hermes-terminal-dev-workspace-orphan"
        attrs = {
            "CreatedAt": old,
            "Labels": {
                "open-work-hub.hermes-terminal.managed": "true",
                "open-work-hub.hermes-terminal.namespace": "dev",
                "open-work-hub.hermes-terminal.resource-kind": "workspace",
                "open-work-hub.hermes-terminal.session-id": str(uuid4()),
            },
        }

        def __init__(self) -> None:
            self.removed = False

        def remove(self, *, force: bool) -> None:
            assert force is True
            self.removed = True

    volume = FakeVolume()
    runtime = object.__new__(HermesTerminalBrokerRuntime)
    runtime.resource_namespace = "dev"
    runtime._forced_failure_codes = {}
    runtime.client = SimpleNamespace(
        containers=SimpleNamespace(list=lambda **_kwargs: []),
        volumes=SimpleNamespace(list=lambda **_kwargs: [volume]),
    )

    result = runtime.reconcile_resources(known_session_ids=set())

    assert result == {
        "removed_runners": 0,
        "removed_workspaces": 1,
        "removed_utilities": 0,
    }
    assert volume.removed is True


def test_broker_reconciles_old_namespaced_orphan_runner_and_workspace() -> None:
    session_id = str(uuid4())
    old = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    class FakeVolume:
        name = "owh-hermes-terminal-dev-workspace-orphan-runner"
        attrs = {
            "CreatedAt": old,
            "Labels": {
                "open-work-hub.hermes-terminal.managed": "true",
                "open-work-hub.hermes-terminal.namespace": "dev",
                "open-work-hub.hermes-terminal.resource-kind": "workspace",
                "open-work-hub.hermes-terminal.session-id": session_id,
            },
        }

        def __init__(self) -> None:
            self.removed = False

        def remove(self, *, force: bool) -> None:
            assert force is True
            self.removed = True

    class FakeContainer:
        id = "orphan-runner"
        name = "owh-hermes-terminal-dev-orphan"
        status = "exited"
        labels = {
            "open-work-hub.hermes-terminal.managed": "true",
            "open-work-hub.hermes-terminal.namespace": "dev",
            "open-work-hub.hermes-terminal.resource-kind": "runner",
            "open-work-hub.hermes-terminal.session-id": session_id,
        }
        attrs = {
            "Created": old,
            "Mounts": [
                {
                    "Destination": "/workspace",
                    "Name": "owh-hermes-terminal-dev-workspace-orphan-runner",
                }
            ],
        }

        def __init__(self) -> None:
            self.removed = False

        def remove(self, *, force: bool) -> None:
            assert force is True
            self.removed = True

    volume = FakeVolume()
    container = FakeContainer()
    runtime = object.__new__(HermesTerminalBrokerRuntime)
    runtime.resource_namespace = "dev"
    runtime._forced_failure_codes = {}
    runtime.client = SimpleNamespace(
        containers=SimpleNamespace(list=lambda **_kwargs: [container]),
        volumes=SimpleNamespace(
            get=lambda name: volume if name == volume.name else None,
            list=lambda **_kwargs: [] if volume.removed else [volume],
        ),
    )

    result = runtime.reconcile_resources(known_session_ids=set())

    assert result == {
        "removed_runners": 1,
        "removed_workspaces": 1,
        "removed_utilities": 0,
    }
    assert container.removed is True
    assert volume.removed is True


def test_broker_websocket_disconnect_closes_the_raw_docker_socket(
    monkeypatch,
) -> None:
    root_secret = "terminal-test-mcp-secret-00000000000000000001"
    monkeypatch.setenv("OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET", root_secret)

    class FakeAttached:
        def __init__(self) -> None:
            self._sock, self.peer = socket.socketpair()
            self.wrapper_closed = threading.Event()

        def close(self) -> None:
            self.wrapper_closed.set()

    class FakeContainer:
        status = "running"
        attrs = {"State": {}}

        def reload(self) -> None:
            return None

    class FakeRuntime:
        instance_id = "test-broker"

        def __init__(self) -> None:
            self.attachments: list[FakeAttached] = []

        def attach_socket(self, _session_id: str):
            attached = FakeAttached()
            self.attachments.append(attached)
            return attached, FakeContainer()

    fake_runtime = FakeRuntime()
    monkeypatch.setattr(broker_app, "runtime", lambda: fake_runtime)
    session_id = str(uuid4())
    headers = {"authorization": f"Bearer {broker_app._broker_token()}"}

    with TestClient(broker_app.app) as client:
        with client.websocket_connect(
            f"/v1/sessions/{session_id}/attach",
            headers=headers,
        ) as websocket:
            assert websocket.receive_json() == {"type": "ready", "active": True}
            attached = fake_runtime.attachments[-1]
            attached.peer.sendall(b"terminal output")
            output = websocket.receive_json()
            assert output["type"] == "output"
            assert base64.b64decode(output["data"]) == b"terminal output"

            websocket.send_json(
                {
                    "type": "input",
                    "data": base64.b64encode(b"terminal input").decode("ascii"),
                }
            )
            attached.peer.settimeout(1)
            assert attached.peer.recv(1024) == b"terminal input"

            websocket.close()
            assert attached.wrapper_closed.wait(timeout=1)

        assert attached._sock.fileno() == -1
        attached.peer.close()

        with client.websocket_connect(
            f"/v1/sessions/{session_id}/attach",
            headers=headers,
        ) as websocket:
            assert websocket.receive_json() == {"type": "ready", "active": True}
            reattached = fake_runtime.attachments[-1]

            websocket.close()
            assert reattached.wrapper_closed.wait(timeout=1)

        assert reattached._sock.fileno() == -1
        reattached.peer.close()


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


def test_profile_export_cleans_regenerable_state_with_official_commands() -> None:
    assert build_profile_export_cleanup_commands() == [
        [
            "/opt/hermes/.venv/bin/hermes",
            "checkpoints",
            "clear",
            "--force",
        ],
        [
            "/usr/local/bin/uv",
            "cache",
            "clean",
            "--force",
            "--cache-dir",
            "/opt/data/profiles/terminal/home/.cache/uv",
        ],
    ]


def test_profile_export_cleanup_uses_the_private_profile_identity() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    class FakeContainer:
        def exec_run(self, command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(exit_code=0, output=b"")

    HermesTerminalBrokerRuntime._cleanup_profile_for_export(  # type: ignore[arg-type]
        FakeContainer(),
    )

    expected_environment = {
        "HOME": "/opt/data/profiles/terminal",
        "HERMES_HOME": "/opt/data/profiles/terminal",
        "UV_CACHE_DIR": "/opt/data/profiles/terminal/home/.cache/uv",
    }
    assert calls == [
        (
            command,
            {
                "environment": expected_environment,
                "user": "10000:10000",
            },
        )
        for command in build_profile_export_cleanup_commands()
    ]


def test_profile_export_stages_on_the_private_volume_for_docker_copy() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    archive_paths: list[str] = []

    class FakeRunner:
        status = "exited"

        def reload(self) -> None:
            return None

    class FakeUtility:
        def exec_run(self, command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(exit_code=0, output=b"")

        def get_archive(self, path):
            archive_paths.append(path)
            return iter([b"docker archive"]), {}

        def remove(self, *, force):
            assert force is True

    runtime = object.__new__(HermesTerminalBrokerRuntime)
    runtime.profile_archive_max_bytes = 64 * 1024 * 1024
    runtime._find_container = lambda _session_id: (  # type: ignore[method-assign]
        FakeRunner(),
        SimpleNamespace(profile_volume_name="private-profile-volume"),
    )
    utility = FakeUtility()
    runtime._utility_container = lambda _volume_name: utility  # type: ignore[method-assign]
    runtime._extract_single_file = (  # type: ignore[method-assign]
        lambda _archive, *, basename, max_bytes: (
            b"profile archive"
            if basename == ".owh-terminal-profile-export.tar.gz" and max_bytes == 64 * 1024 * 1024
            else b"unexpected"
        )
    )

    assert runtime.export_profile("session-1") == b"profile archive"
    assert archive_paths == ["/opt/data/.owh-terminal-profile-export.tar.gz"]
    assert (
        ["rm", "-f", "/opt/data/.owh-terminal-profile-export.tar.gz"],
        {"user": "10000:10000"},
    ) in calls


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
    settings = _settings(hermes_terminal_mcp_socket_path=".runtime/hermes-terminal-test.sock")

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
        archive_claim_token="stale-claim",
        archive_claim_expires_at=ended_at,
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
    assert row.archive_claim_token is None
    assert row.archive_claim_expires_at is None
    assert row.archive_failure_code is None


def test_manual_archive_recovery_stops_a_restarted_runtime(monkeypatch) -> None:
    stopped: list[str] = []

    class FakeBrokerClient:
        async def get_session(self, session_id: str):
            assert session_id == "session-1"
            return SimpleNamespace(status="running")

        async def stop_session(self, session_id: str):
            stopped.append(session_id)
            return SimpleNamespace(status="exited", exit_code=130)

    monkeypatch.setattr(lifecycle, "HermesTerminalBrokerClient", FakeBrokerClient)
    row = SimpleNamespace(
        id="session-1",
        status="archiving",
        archive_target_status="terminated",
        user_id="user-1",
    )

    asyncio.run(lifecycle.reconcile_terminal_session_if_finished(row))

    assert stopped == ["session-1"]
    assert "archiving" in maintenance._RECONCILE_STATUSES


def test_missing_live_runtime_quarantines_workspace_instead_of_deleting_it(
    monkeypatch,
) -> None:
    row = SimpleNamespace(
        id="session-1",
        status="running",
        mode="standard",
        user_id="user-1",
        failure_code=None,
        archive_target_status=None,
        archive_started_at=None,
        archive_claim_token=None,
        archive_claim_expires_at=None,
        workspace_retained=False,
        quarantine_reason=None,
        ended_at=None,
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

    class UnexpectedBrokerClient:
        async def forget_session(self, _session_id: str):
            raise AssertionError("A quarantined workspace must not be deleted")

    monkeypatch.setattr(lifecycle, "get_session_factory", lambda: lambda: FakeDb())
    monkeypatch.setattr(lifecycle, "record_audit_log", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        lifecycle,
        "HermesTerminalBrokerClient",
        UnexpectedBrokerClient,
    )

    changed = asyncio.run(
        lifecycle.fail_missing_terminal_runtime(
            "session-1",
            actor_user_id=None,
        )
    )

    assert changed is True
    assert row.status == "failed"
    assert row.failure_code == "hermes_terminal.runtime_missing"
    assert row.workspace_retained is True
    assert row.quarantine_reason == "hermes_terminal.runtime_missing"


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

        assert len(claimed) == 1
        assert claimed[0][:4] == (row_id, "terminated", None, user_id)
        assert len(claimed[0][4]) == 32
        with Session(engine) as db:
            stored = db.get(HermesTerminalSession, row_id)
            assert stored is not None
            assert stored.status == "archiving"
            assert stored.runtime_handle == runtime_handle
            assert stored.archive_claim_token == claimed[0][4]
            assert stored.archive_claim_expires_at is not None

        assert maintenance._claim_archive_retries(limit=1) == []
        with Session(engine) as db:
            stored = db.get(HermesTerminalSession, row_id)
            assert stored is not None
            stored.archive_attempts = 3
            stored.archive_failure_code = maintenance.HERMES_TERMINAL_ARCHIVE_FAILURE
            stored.updated_at = stale
            db.add(stored)
            db.commit()

        assert maintenance._abandon_exhausted_archives(limit=1) == 0
        with Session(engine) as db:
            stored = db.get(HermesTerminalSession, row_id)
            assert stored is not None
            stored.archive_claim_expires_at = stale
            stored.updated_at = stale - timedelta(seconds=1)
            db.add(stored)
            db.commit()

        assert maintenance._abandon_exhausted_archives(limit=1) == 1
        assert maintenance._runtime_release_candidates(limit=1) == []
        with Session(engine) as db:
            stored = db.get(HermesTerminalSession, row_id)
            assert stored is not None
            assert stored.status == "terminated"
            assert stored.archive_failure_code == "hermes_terminal.archive_failed"
            assert stored.workspace_retained is True
            assert stored.quarantine_reason == "hermes_terminal.archive_exhausted"
    finally:
        engine.dispose()
