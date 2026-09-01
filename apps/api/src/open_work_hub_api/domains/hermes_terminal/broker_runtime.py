from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import re
import socket
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container
from docker.types import Mount

from open_work_hub_api.domains.hermes.research_sources import (
    academic_research_environment_hint,
    disabled_research_source_domains,
    normalize_research_source_policy,
)


HERMES_IMAGE = (
    "nousresearch/hermes-agent:v2026.8.31@"
    "sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524"
)
HERMES_PROVIDER = "openrouter"
HERMES_MODEL = "qwen/qwen3.8-flash"
HERMES_FALLBACK_MODEL = "z-ai/glm-5.3-flash"
PROFILE_NAME = "terminal"
SESSION_LABEL = "open-work-hub.hermes-terminal.session-id"
PROFILE_LABEL = "open-work-hub.hermes-terminal.profile-key"
MANAGED_LABEL = "open-work-hub.hermes-terminal.managed"
_PROFILE_KEY = re.compile(r"^[a-z0-9]{8,63}$")
_ACTIVE_DOCKER_STATES = frozenset({"created", "running", "restarting", "paused"})
_HERMES_BIN = "/opt/hermes/.venv/bin/hermes"
_UV_BIN = "/usr/local/bin/uv"
_HERMES_USER = "10000:10000"
_PROFILE_HOME = "/opt/data/profiles/terminal"
_PROFILE_EXPORT_PATH = "/opt/data/.owh-terminal-profile-export.tar.gz"
_PROFILE_UV_CACHE = f"{_PROFILE_HOME}/home/.cache/uv"
_RUNTIME_CACHE_HOME = "/opt/data/cache"
_OPENROUTER_METADATA_HEADERS = {"X-OpenRouter-Metadata": "enabled"}
_EPHEMERAL_PROFILE_SECRET_KEYS = (
    "OPENROUTER_API_KEY",
    "MCP_OPEN_WORK_HUB_API_KEY",
)


def build_profile_config_commands(
    *,
    mcp_url: str,
    proxy_token: str,
    mcp_token: str,
    research_sources: Mapping[str, object] | None = None,
) -> list[list[str]]:
    research_hint = academic_research_environment_hint(research_sources)
    mcp_servers = json.dumps(
        {
            "open-work-hub": {
                "url": mcp_url,
                "headers": {
                    "Authorization": "Bearer ${MCP_OPEN_WORK_HUB_API_KEY}",
                },
                "trust": "full",
                "timeout": 330,
            }
        },
        separators=(",", ":"),
    )
    values = (
        ("model.provider", HERMES_PROVIDER),
        ("model.default", HERMES_MODEL),
        (
            "model.default_headers",
            json.dumps(_OPENROUTER_METADATA_HEADERS, separators=(",", ":")),
        ),
        (
            "fallback_providers",
            json.dumps(
                [
                    {
                        "provider": HERMES_PROVIDER,
                        "model": HERMES_FALLBACK_MODEL,
                    }
                ],
                separators=(",", ":"),
            ),
        ),
        ("agent.api_max_retries", "1"),
        ("compression.enabled", "true"),
        ("compression.threshold", "0.50"),
        ("compression.threshold_tokens", "100000"),
        ("compression.target_ratio", "0.20"),
        ("compression.protect_last_n", "20"),
        ("compression.proactive_prune_tokens", "48000"),
        ("compression.proactive_prune_min_result_chars", "8000"),
        ("compression.proactive_prune_min_reclaim_tokens", "4096"),
        ("provider_routing.sort", "throughput"),
        ("provider_routing.require_parameters", "true"),
        ("auxiliary.free_only", "false"),
        ("auxiliary.openrouter_model", HERMES_MODEL),
        ("display.mouse_tracking", "off"),
        ("OPENROUTER_API_KEY", proxy_token),
        ("MCP_OPEN_WORK_HUB_API_KEY", mcp_token),
        ("mcp_servers", mcp_servers),
    )
    commands = [
        [_HERMES_BIN, "config", "set", "--force", key, value]
        for key, value in values
    ]
    if research_hint:
        commands.append(
            [
                _HERMES_BIN,
                "config",
                "set",
                "--force",
                "agent.environment_hint",
                research_hint,
            ]
        )
    else:
        commands.append(
            [_HERMES_BIN, "config", "unset", "agent.environment_hint"]
        )
    commands.append([_HERMES_BIN, "config", "unset", "fallback_model"])
    commands.append([_HERMES_BIN, "config", "check"])
    return commands


def build_profile_sanitize_commands() -> list[list[str]]:
    return [
        [_HERMES_BIN, "config", "unset", key]
        for key in _EPHEMERAL_PROFILE_SECRET_KEYS
    ]


def build_profile_export_cleanup_commands() -> list[list[str]]:
    """Return official cleanup commands for session-scoped, regenerable data."""

    return [
        [_HERMES_BIN, "checkpoints", "clear", "--force"],
        [
            _UV_BIN,
            "cache",
            "clean",
            "--force",
            "--cache-dir",
            _PROFILE_UV_CACHE,
        ],
    ]


def build_runner_mounts(
    *,
    profile_volume_name: str,
    workspace_volume_name: str,
    egress_client_volume: str,
) -> list[Mount]:
    return [
        Mount(
            target="/opt/data",
            source=profile_volume_name,
            type="volume",
            no_copy=True,
        ),
        Mount(
            target="/workspace",
            source=workspace_volume_name,
            type="volume",
            no_copy=True,
        ),
        Mount(
            target="/run/owh-egress",
            source=egress_client_volume,
            type="volume",
            read_only=True,
            no_copy=True,
        ),
    ]


_LIST_FILES_SCRIPT = r"""
import json
import os
import pathlib
import stat
import sys
from datetime import UTC, datetime

root = pathlib.Path("/workspace").resolve()
relative = sys.argv[1]
target = (root / relative).resolve(strict=True) if relative else root
if target != root and root not in target.parents:
    raise SystemExit(12)
if not target.is_dir():
    raise SystemExit(13)
items = []
for entry in sorted(os.scandir(target), key=lambda row: (not row.is_dir(follow_symlinks=False), row.name.lower())):
    info = entry.stat(follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        continue
    path = pathlib.Path(entry.path).relative_to(root).as_posix()
    is_dir = stat.S_ISDIR(info.st_mode)
    if not is_dir and not stat.S_ISREG(info.st_mode):
        continue
    items.append({
        "relative_path": path,
        "name": entry.name,
        "kind": "directory" if is_dir else "file",
        "size_bytes": None if is_dir else info.st_size,
        "modified_at": datetime.fromtimestamp(info.st_mtime, UTC).isoformat(),
    })
print(json.dumps({"path": relative, "items": items}, separators=(",", ":")))
"""


_FILE_INFO_SCRIPT = r"""
import json
import pathlib
import stat
import sys

root = pathlib.Path("/workspace").resolve()
relative = sys.argv[1]
target = (root / relative).resolve(strict=True)
if root not in target.parents:
    raise SystemExit(12)
info = target.lstat()
if not stat.S_ISREG(info.st_mode):
    raise SystemExit(13)
print(json.dumps({"size": info.st_size}, separators=(",", ":")))
"""


def build_runner_command(mode: str) -> list[str]:
    if mode not in {"standard", "yolo"}:
        raise BrokerRuntimeError("hermes_terminal.mode_invalid")
    command = [
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
    if mode == "yolo":
        command.append("--yolo")
    return command


def build_runner_environment(
    *,
    proxy_token: str,
    research_sources: Mapping[str, object] | None = None,
) -> dict[str, str]:
    no_proxy = ",".join(
        (
            "hermes-terminal-broker",
            *disabled_research_source_domains(research_sources),
        )
    )
    return {
        "HERMES_HOME": _PROFILE_HOME,
        "HERMES_UID": "10000",
        "HERMES_GID": "10000",
        "XDG_CACHE_HOME": _RUNTIME_CACHE_HOME,
        "UV_CACHE_DIR": f"{_RUNTIME_CACHE_HOME}/uv",
        "HERMES_WRITE_SAFE_ROOT": "/workspace",
        "HERMES_TUI_DISABLE_MOUSE": "1",
        "OPENROUTER_API_KEY": proxy_token,
        "HTTP_PROXY": "http://hermes-terminal-egress:19091",
        "HTTPS_PROXY": "http://hermes-terminal-egress:19090",
        "http_proxy": "http://hermes-terminal-egress:19091",
        "https_proxy": "http://hermes-terminal-egress:19090",
        # The runner is attached only to an internal Docker network. Routing
        # disabled sources outside the proxy enforces the administrator policy
        # without weakening enabled public-web access through iron-proxy.
        "NO_PROXY": no_proxy,
        "no_proxy": no_proxy,
        "REQUESTS_CA_BUNDLE": "/run/owh-egress/ca.crt",
        "SSL_CERT_FILE": "/run/owh-egress/ca.crt",
        "NODE_EXTRA_CA_CERTS": "/run/owh-egress/ca.crt",
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
    }


def build_runner_io_options() -> dict[str, bool]:
    return {
        "detach": True,
        "stdin_open": True,
        "tty": True,
    }


class BrokerRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RuntimeSession:
    session_id: str
    profile_key: str
    container_name: str
    profile_volume_name: str
    workspace_volume_name: str


class HermesTerminalBrokerRuntime:
    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException as exc:
            raise BrokerRuntimeError("hermes_terminal.docker_unavailable") from exc
        self.instance_id = os.environ.get("OWH_HERMES_TERMINAL_BROKER_INSTANCE_ID", "").strip()
        if not self.instance_id:
            self.instance_id = f"broker-{socket.gethostname()}"
        self.image = os.environ.get("OWH_HERMES_TERMINAL_IMAGE", HERMES_IMAGE).strip()
        if self.image != HERMES_IMAGE:
            raise BrokerRuntimeError("hermes_terminal.image_not_pinned")
        self.network_name = os.environ.get(
            "OWH_HERMES_TERMINAL_SANDBOX_NETWORK",
            "open-work-hub-hermes-terminal-sandbox",
        ).strip()
        self.egress_client_dir = os.environ.get(
            "OWH_HERMES_TERMINAL_EGRESS_CLIENT_DIR",
            "/run/owh-hermes-terminal-egress",
        ).strip()
        self.egress_client_volume = os.environ.get(
            "OWH_HERMES_TERMINAL_EGRESS_CLIENT_VOLUME",
            "open-work-hub-hermes-terminal-egress-client",
        ).strip()
        self.mcp_relay_base_url = os.environ.get(
            "OWH_HERMES_TERMINAL_MCP_RELAY_BASE_URL",
            "http://hermes-terminal-broker:18765/mcp",
        ).strip().rstrip("/")
        self.profile_archive_max_bytes = int(
            os.environ.get("OWH_HERMES_TERMINAL_PROFILE_ARCHIVE_MAX_BYTES", str(64 * 1024 * 1024))
        )
        self.workspace_archive_max_bytes = int(
            os.environ.get(
                "OWH_HERMES_TERMINAL_WORKSPACE_ARCHIVE_MAX_BYTES",
                str(256 * 1024 * 1024),
            )
        )
        self._lock = RLock()
        self._ensure_dependencies()

    def _ensure_dependencies(self) -> None:
        try:
            self.client.images.get(self.image)
            self.client.networks.get(self.network_name)
            self.client.volumes.get(self.egress_client_volume)
        except NotFound as exc:
            raise BrokerRuntimeError("hermes_terminal.runtime_dependency_missing") from exc
        token_path = os.path.join(self.egress_client_dir, "openrouter.token")
        ca_path = os.path.join(self.egress_client_dir, "ca.crt")
        if not os.path.isfile(token_path) or not os.path.isfile(ca_path):
            raise BrokerRuntimeError("hermes_terminal.egress_not_ready")

    def _proxy_token(self) -> str:
        path = os.path.join(self.egress_client_dir, "openrouter.token")
        try:
            with open(path, encoding="utf-8") as source:
                value = source.read().strip()
        except OSError as exc:
            raise BrokerRuntimeError("hermes_terminal.egress_not_ready") from exc
        if len(value) < 16:
            raise BrokerRuntimeError("hermes_terminal.egress_not_ready")
        return value

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        try:
            return str(UUID(session_id))
        except (TypeError, ValueError) as exc:
            raise BrokerRuntimeError("hermes_terminal.session_id_invalid") from exc

    @staticmethod
    def _validate_profile_key(profile_key: str) -> str:
        if not _PROFILE_KEY.fullmatch(profile_key):
            raise BrokerRuntimeError("hermes_terminal.profile_key_invalid")
        return profile_key

    @staticmethod
    def _volume_name(kind: str, value: str) -> str:
        digest = hashlib.sha256(value.encode()).hexdigest()[:24]
        return f"owh-hermes-terminal-{kind}-{digest}"

    @staticmethod
    def _container_name(session_id: str) -> str:
        return f"owh-hermes-terminal-{session_id.replace('-', '')}"

    def _record_from_container(self, container: Container) -> RuntimeSession:
        labels = container.labels or {}
        session_id = str(labels.get(SESSION_LABEL) or "")
        profile_key = str(labels.get(PROFILE_LABEL) or "")
        self._validate_session_id(session_id)
        self._validate_profile_key(profile_key)
        return RuntimeSession(
            session_id=session_id,
            profile_key=profile_key,
            container_name=container.name,
            profile_volume_name=self._volume_name("profile", profile_key),
            workspace_volume_name=self._volume_name("workspace", session_id),
        )

    def _find_container(self, session_id: str) -> tuple[Container, RuntimeSession]:
        normalized = self._validate_session_id(session_id)
        matches = self.client.containers.list(
            all=True,
            filters={"label": [f"{SESSION_LABEL}={normalized}", f"{MANAGED_LABEL}=true"]},
        )
        if len(matches) != 1:
            raise BrokerRuntimeError("hermes_terminal.session_not_found")
        container = matches[0]
        return container, self._record_from_container(container)

    def _ensure_volume(self, name: str, *, labels: dict[str, str]) -> tuple[Any, bool]:
        try:
            return self.client.volumes.get(name), False
        except NotFound:
            return self.client.volumes.create(name=name, labels=labels), True

    @staticmethod
    def _tar_bytes(name: str, data: bytes, *, mode: int = 0o600) -> bytes:
        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w") as tar:
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = mode
            info.mtime = int(datetime.now(UTC).timestamp())
            tar.addfile(info, io.BytesIO(data))
        return payload.getvalue()

    @staticmethod
    def _read_stream(stream: Any, *, max_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in stream:
            total += len(chunk)
            if total > max_bytes:
                raise BrokerRuntimeError("hermes_terminal.archive_too_large")
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _extract_single_file(archive: bytes, *, basename: str, max_bytes: int) -> bytes:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            candidates = [
                member
                for member in tar
                if member.isfile()
                and not member.issym()
                and not member.islnk()
                and PurePosixPath(member.name).name == basename
            ]
            if len(candidates) != 1 or candidates[0].size > max_bytes:
                raise BrokerRuntimeError("hermes_terminal.archive_invalid")
            source = tar.extractfile(candidates[0])
            if source is None:
                raise BrokerRuntimeError("hermes_terminal.archive_invalid")
            data = source.read(max_bytes + 1)
            if len(data) != candidates[0].size or len(data) > max_bytes:
                raise BrokerRuntimeError("hermes_terminal.archive_invalid")
            return data

    def _utility_container(self, profile_volume_name: str) -> Container:
        name = f"owh-hermes-terminal-init-{uuid4().hex[:16]}"
        try:
            container = self.client.containers.create(
                self.image,
                name=name,
                command=["/bin/sh", "-lc", "sleep 300"],
                environment={
                    "HERMES_HOME": "/opt/data",
                    "HERMES_UID": "10000",
                    "HERMES_GID": "10000",
                },
                volumes={profile_volume_name: {"bind": "/opt/data", "mode": "rw"}},
                network_disabled=True,
                read_only=True,
                tmpfs={
                    "/tmp": "rw,exec,nosuid,nodev,mode=1777",
                    "/run": "rw,exec,nosuid,nodev,mode=0755,size=64m",
                },
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE"],
                pids_limit=256,
                mem_limit="1g",
                labels={MANAGED_LABEL: "true", "open-work-hub.hermes-terminal.utility": "true"},
            )
            container.start()
            return container
        except (APIError, DockerException) as exc:
            raise BrokerRuntimeError("hermes_terminal.profile_utility_failed") from exc

    def _initialize_workspace_volume(self, workspace_volume_name: str) -> None:
        name = f"owh-hermes-terminal-volume-init-{uuid4().hex[:16]}"
        container: Container | None = None
        try:
            container = self.client.containers.create(
                self.image,
                name=name,
                entrypoint=["/bin/sh", "-ec"],
                command=[
                    "chown 0:0 /workspace && chmod 0700 /workspace && "
                    "chown 10000:10000 /workspace"
                ],
                user="0:0",
                volumes={workspace_volume_name: {"bind": "/workspace", "mode": "rw"}},
                network_disabled=True,
                read_only=True,
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                cap_add=["CHOWN"],
                pids_limit=32,
                mem_limit="128m",
                labels={
                    MANAGED_LABEL: "true",
                    "open-work-hub.hermes-terminal.utility": "true",
                },
            )
            container.start()
            result = container.wait(timeout=30)
            if int(result.get("StatusCode", 1)) != 0:
                raise BrokerRuntimeError("hermes_terminal.workspace_initialization_failed")
        except BrokerRuntimeError:
            raise
        except (APIError, DockerException) as exc:
            raise BrokerRuntimeError(
                "hermes_terminal.workspace_initialization_failed"
            ) from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except DockerException:
                    pass

    @staticmethod
    def _exec_ok(
        container: Container,
        command: list[str],
        *,
        environment: dict[str, str] | None = None,
    ) -> bytes:
        result = container.exec_run(
            command,
            environment=environment,
            user=_HERMES_USER,
        )
        if result.exit_code != 0:
            raise BrokerRuntimeError("hermes_terminal.profile_configuration_failed")
        return bytes(result.output or b"")

    @staticmethod
    def _chown_profile_path(
        container: Container,
        path: str,
        *,
        recursive: bool = False,
    ) -> None:
        command = ["chown"]
        if recursive:
            command.append("-R")
        command.extend([_HERMES_USER, path])
        result = container.exec_run(command, user="0:0")
        if result.exit_code != 0:
            raise BrokerRuntimeError("hermes_terminal.profile_configuration_failed")

    def _configure_profile(
        self,
        *,
        profile_volume_name: str,
        profile_archive: bytes | None,
        mcp_url: str,
        mcp_token: str,
        research_sources: Mapping[str, object],
    ) -> None:
        utility = self._utility_container(profile_volume_name)
        try:
            self._chown_profile_path(utility, "/opt/data")
            exists = utility.exec_run(
                ["test", "-d", _PROFILE_HOME],
                user=_HERMES_USER,
            )
            if exists.exit_code != 0:
                if profile_archive is not None:
                    if len(profile_archive) > self.profile_archive_max_bytes:
                        raise BrokerRuntimeError("hermes_terminal.profile_archive_too_large")
                    utility.put_archive(
                        "/tmp",
                        self._tar_bytes("profile.tar.gz", profile_archive),
                    )
                    self._chown_profile_path(utility, "/tmp/profile.tar.gz")
                    self._exec_ok(
                        utility,
                        [
                            "/opt/hermes/.venv/bin/hermes",
                            "profile",
                            "import",
                            "/tmp/profile.tar.gz",
                            "--name",
                            PROFILE_NAME,
                        ],
                    )
                else:
                    self._exec_ok(
                        utility,
                        [
                            "/opt/hermes/.venv/bin/hermes",
                            "profile",
                            "create",
                            PROFILE_NAME,
                            "--no-alias",
                            "--description",
                            "Private Open Work Hub Hermes terminal profile",
                        ],
                    )
            self._chown_profile_path(utility, _PROFILE_HOME, recursive=True)
            profile_environment = {
                "HOME": _PROFILE_HOME,
                "HERMES_HOME": _PROFILE_HOME,
            }
            for command in build_profile_config_commands(
                mcp_url=mcp_url,
                proxy_token=self._proxy_token(),
                mcp_token=mcp_token,
                research_sources=research_sources,
            ):
                result = utility.exec_run(
                    command,
                    environment=profile_environment,
                    user=_HERMES_USER,
                )
                output = bytes(result.output or b"")
                if result.exit_code == 0:
                    continue
                if "unset" in command and b"Config key not set" in output:
                    continue
                raise BrokerRuntimeError("hermes_terminal.profile_configuration_failed")
        finally:
            try:
                utility.remove(force=True)
            except DockerException:
                pass

    def _sanitize_profile_for_export(self, utility: Container) -> None:
        profile_environment = {
            "HOME": _PROFILE_HOME,
            "HERMES_HOME": _PROFILE_HOME,
        }
        for command in build_profile_sanitize_commands():
            result = utility.exec_run(
                command,
                environment=profile_environment,
                user=_HERMES_USER,
            )
            output = bytes(result.output or b"")
            if result.exit_code == 0 or b"Config key not set" in output:
                continue
            raise BrokerRuntimeError("hermes_terminal.profile_configuration_failed")

    @staticmethod
    def _cleanup_profile_for_export(utility: Container) -> None:
        profile_environment = {
            "HOME": _PROFILE_HOME,
            "HERMES_HOME": _PROFILE_HOME,
            "UV_CACHE_DIR": _PROFILE_UV_CACHE,
        }
        for command in build_profile_export_cleanup_commands():
            result = utility.exec_run(
                command,
                environment=profile_environment,
                user=_HERMES_USER,
            )
            if result.exit_code != 0:
                raise BrokerRuntimeError("hermes_terminal.profile_cleanup_failed")

    def create_session(
        self,
        *,
        session_id: str,
        profile_key: str,
        mode: str,
        cols: int,
        rows: int,
        mcp_url: str,
        mcp_token: str,
        research_sources: Mapping[str, object],
        profile_archive_base64: str | None,
    ) -> dict[str, Any]:
        session_id = self._validate_session_id(session_id)
        profile_key = self._validate_profile_key(profile_key)
        if mode not in {"standard", "yolo"}:
            raise BrokerRuntimeError("hermes_terminal.mode_invalid")
        if not (20 <= cols <= 500 and 5 <= rows <= 300):
            raise BrokerRuntimeError("hermes_terminal.size_invalid")
        expected_mcp_url = f"{self.mcp_relay_base_url}/{session_id}"
        if mcp_url != expected_mcp_url or len(mcp_token) < 32:
            raise BrokerRuntimeError("hermes_terminal.mcp_configuration_invalid")
        try:
            normalized_research_sources = normalize_research_source_policy(
                research_sources
            )
        except ValueError as exc:
            raise BrokerRuntimeError(
                "hermes_terminal.research_source_policy_invalid"
            ) from exc
        profile_archive = None
        if profile_archive_base64:
            try:
                profile_archive = base64.b64decode(profile_archive_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise BrokerRuntimeError("hermes_terminal.profile_archive_invalid") from exc
            if len(profile_archive) > self.profile_archive_max_bytes:
                raise BrokerRuntimeError("hermes_terminal.profile_archive_too_large")

        with self._lock:
            existing = self.client.containers.list(
                all=True,
                filters={"label": f"{SESSION_LABEL}={session_id}"},
            )
            if existing:
                raise BrokerRuntimeError("hermes_terminal.session_exists")
            profile_volume_name = self._volume_name("profile", profile_key)
            workspace_volume_name = self._volume_name("workspace", session_id)
            labels = {MANAGED_LABEL: "true", PROFILE_LABEL: profile_key}
            profile_volume_created = False
            try:
                _profile_volume, profile_volume_created = self._ensure_volume(
                    profile_volume_name,
                    labels=labels,
                )
                self._ensure_volume(
                    workspace_volume_name,
                    labels={MANAGED_LABEL: "true", SESSION_LABEL: session_id},
                )
                self._initialize_workspace_volume(workspace_volume_name)
                self._configure_profile(
                    profile_volume_name=profile_volume_name,
                    profile_archive=profile_archive,
                    mcp_url=mcp_url,
                    mcp_token=mcp_token,
                    research_sources=normalized_research_sources,
                )
            except (BrokerRuntimeError, DockerException) as error:
                try:
                    self.client.volumes.get(workspace_volume_name).remove(force=True)
                except DockerException:
                    pass
                if profile_volume_created:
                    try:
                        self.client.volumes.get(profile_volume_name).remove(force=True)
                    except DockerException:
                        pass
                if isinstance(error, BrokerRuntimeError):
                    raise
                raise BrokerRuntimeError(
                    "hermes_terminal.profile_configuration_failed"
                ) from error

            command = build_runner_command(mode)
            container_name = self._container_name(session_id)
            try:
                container = self.client.containers.create(
                    self.image,
                    name=container_name,
                    command=command,
                    environment=build_runner_environment(
                        proxy_token=self._proxy_token(),
                        research_sources=normalized_research_sources,
                    ),
                    mounts=build_runner_mounts(
                        profile_volume_name=profile_volume_name,
                        workspace_volume_name=workspace_volume_name,
                        egress_client_volume=self.egress_client_volume,
                    ),
                    working_dir="/workspace",
                    network=self.network_name,
                    **build_runner_io_options(),
                    read_only=True,
                    tmpfs={
                        "/tmp": "rw,exec,nosuid,nodev,mode=1777,size=512m",
                        "/run": "rw,exec,nosuid,nodev,mode=0755,size=64m",
                    },
                    security_opt=["no-new-privileges:true"],
                    cap_drop=["ALL"],
                    cap_add=["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE"],
                    pids_limit=512,
                    mem_limit="2g",
                    nano_cpus=2_000_000_000,
                    log_config={
                        "type": "json-file",
                        "config": {"max-size": "8m", "max-file": "1"},
                    },
                    labels={
                        MANAGED_LABEL: "true",
                        SESSION_LABEL: session_id,
                        PROFILE_LABEL: profile_key,
                        "open-work-hub.hermes-terminal.mode": mode,
                    },
                )
                container.start()
                container.resize(height=rows, width=cols)
            except (APIError, DockerException) as exc:
                try:
                    self.client.containers.get(container_name).remove(force=True)
                except DockerException:
                    pass
                try:
                    self.client.volumes.get(workspace_volume_name).remove(force=True)
                except DockerException:
                    pass
                raise BrokerRuntimeError("hermes_terminal.runner_start_failed") from exc
            return self.session_status(session_id)

    def session_status(self, session_id: str) -> dict[str, Any]:
        container, record = self._find_container(session_id)
        container.reload()
        state = container.attrs.get("State") or {}
        docker_status = str(state.get("Status") or container.status)
        if docker_status in _ACTIVE_DOCKER_STATES:
            status = "running" if docker_status == "running" else "starting"
            exit_code = None
        else:
            status = "exited" if docker_status == "exited" else "failed"
            exit_code = state.get("ExitCode")
        failure_code = None
        if status == "failed":
            failure_code = "hermes_terminal.runner_failed"
        return {
            "session_id": record.session_id,
            "runtime_handle": container.id,
            "broker_instance_id": self.instance_id,
            "status": status,
            "exit_code": exit_code,
            "failure_code": failure_code,
        }

    def stop_session(self, session_id: str) -> dict[str, Any]:
        container, _record = self._find_container(session_id)
        container.reload()
        if container.status in _ACTIVE_DOCKER_STATES:
            try:
                container.stop(timeout=15)
            except DockerException as exc:
                raise BrokerRuntimeError("hermes_terminal.runner_stop_failed") from exc
        return self.session_status(session_id)

    def forget_session(self, session_id: str) -> None:
        normalized = self._validate_session_id(session_id)
        workspace_volume_name = self._volume_name("workspace", normalized)
        try:
            container, record = self._find_container(normalized)
        except BrokerRuntimeError as error:
            if error.code != "hermes_terminal.session_not_found":
                raise
        else:
            workspace_volume_name = record.workspace_volume_name
            container.reload()
            if container.status in _ACTIVE_DOCKER_STATES:
                raise BrokerRuntimeError("hermes_terminal.session_active")
            try:
                container.remove(force=True)
            except DockerException as exc:
                raise BrokerRuntimeError("hermes_terminal.runner_remove_failed") from exc
        try:
            self.client.volumes.get(workspace_volume_name).remove(force=True)
        except NotFound:
            pass
        except DockerException as exc:
            raise BrokerRuntimeError("hermes_terminal.workspace_remove_failed") from exc

    def resize_session(self, session_id: str, *, cols: int, rows: int) -> None:
        if not (20 <= cols <= 500 and 5 <= rows <= 300):
            raise BrokerRuntimeError("hermes_terminal.size_invalid")
        container, _record = self._find_container(session_id)
        try:
            container.resize(height=rows, width=cols)
        except DockerException as exc:
            raise BrokerRuntimeError("hermes_terminal.resize_failed") from exc

    def list_files(self, session_id: str, *, path: str) -> dict[str, Any]:
        container, _record = self._find_container(session_id)
        container.reload()
        if container.status != "running":
            raise BrokerRuntimeError("hermes_terminal.session_not_running")
        result = container.exec_run(
            ["/opt/hermes/.venv/bin/python", "-c", _LIST_FILES_SCRIPT, path]
        )
        if result.exit_code != 0:
            raise BrokerRuntimeError("hermes_terminal.path_not_found")
        try:
            payload = json.loads(bytes(result.output).decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerRuntimeError("hermes_terminal.file_listing_failed") from exc
        return payload

    def read_file(self, session_id: str, *, path: str) -> bytes:
        container, _record = self._find_container(session_id)
        container.reload()
        if container.status != "running":
            raise BrokerRuntimeError("hermes_terminal.session_not_running")
        result = container.exec_run(
            ["/opt/hermes/.venv/bin/python", "-c", _FILE_INFO_SCRIPT, path]
        )
        if result.exit_code != 0:
            raise BrokerRuntimeError("hermes_terminal.file_not_found")
        try:
            size = int(json.loads(bytes(result.output).decode())["size"])
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BrokerRuntimeError("hermes_terminal.file_read_failed") from exc
        if size > 64 * 1024 * 1024:
            raise BrokerRuntimeError("hermes_terminal.file_too_large")
        stream, _stat = container.get_archive(f"/workspace/{path}")
        archive = self._read_stream(stream, max_bytes=size + 2 * 1024 * 1024)
        return self._extract_single_file(
            archive,
            basename=PurePosixPath(path).name,
            max_bytes=64 * 1024 * 1024,
        )

    def export_workspace(self, session_id: str) -> bytes:
        container, _record = self._find_container(session_id)
        stream, _stat = container.get_archive("/workspace")
        return self._read_stream(
            stream,
            max_bytes=self.workspace_archive_max_bytes + 16 * 1024 * 1024,
        )

    def export_profile(self, session_id: str) -> bytes:
        container, record = self._find_container(session_id)
        container.reload()
        if container.status in _ACTIVE_DOCKER_STATES:
            raise BrokerRuntimeError("hermes_terminal.session_active")
        utility = self._utility_container(record.profile_volume_name)
        try:
            self._cleanup_profile_for_export(utility)
            self._sanitize_profile_for_export(utility)
            self._exec_ok(
                utility,
                [
                    "/opt/hermes/.venv/bin/hermes",
                    "profile",
                    "export",
                    PROFILE_NAME,
                    "--output",
                    _PROFILE_EXPORT_PATH,
                ],
            )
            try:
                stream, _stat = utility.get_archive(_PROFILE_EXPORT_PATH)
                archive = self._read_stream(
                    stream,
                    max_bytes=self.profile_archive_max_bytes + 2 * 1024 * 1024,
                )
                return self._extract_single_file(
                    archive,
                    basename=PurePosixPath(_PROFILE_EXPORT_PATH).name,
                    max_bytes=self.profile_archive_max_bytes,
                )
            except DockerException as exc:
                raise BrokerRuntimeError("hermes_terminal.profile_export_failed") from exc
        finally:
            try:
                utility.exec_run(
                    ["rm", "-f", _PROFILE_EXPORT_PATH],
                    user=_HERMES_USER,
                )
            except DockerException:
                pass
            try:
                utility.remove(force=True)
            except DockerException:
                pass

    def attach_socket(self, session_id: str) -> tuple[Any, Container]:
        container, _record = self._find_container(session_id)
        container.reload()
        if container.status != "running":
            raise BrokerRuntimeError("hermes_terminal.session_not_running")
        try:
            attached = container.attach_socket(
                params={
                    "stdin": 1,
                    "stdout": 1,
                    "stderr": 1,
                    "stream": 1,
                    "logs": 1,
                }
            )
            return attached, container
        except DockerException as exc:
            raise BrokerRuntimeError("hermes_terminal.attach_failed") from exc
