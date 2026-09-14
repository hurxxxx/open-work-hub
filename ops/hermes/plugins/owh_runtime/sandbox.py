"""Pinned v2026.8.31 official environment-provider extension.

DockerEnvironment unconditionally adds host credential/skill/cache bind mounts
and has no switch to disable them. This small BaseEnvironment implementation
supplies only the container transport; native Hermes owns command wrapping,
timeouts, interrupts, environment caching and agent/session lifecycle.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

from agent.terminal_env_provider import TerminalEnvironmentProvider
from tools.environments.base import BaseEnvironment, EnvironmentConnectionError

from .workspace import WORKSPACE_SCRIPT

_RETRY_HINT = (
    "Ask an administrator to check the gateway's sandbox resource configuration, "
    "Docker access and egress certificate service, then retry the command."
)


def _infrastructure_error(reason: str) -> EnvironmentConnectionError:
    return EnvironmentConnectionError(reason, retry_hint=_RETRY_HINT)


def _deployment_resource(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,254}", value):
        raise _infrastructure_error(
            "Sandbox resources are not configured correctly (sandbox.configuration_invalid)."
        )
    return value


class WorkspaceEnvironment(BaseEnvironment):
    def __init__(self, *, policy: dict, server: dict, run_id: str, timeout: int,
                 preview: bool = False):
        # Compose owns physical resources. A database/runner namespace is not
        # a Docker network or volume name, including during database cutovers.
        network = _deployment_resource("OWH_HERMES_TERMINAL_SANDBOX_NETWORK")
        ca_volume = _deployment_resource("OWH_HERMES_TERMINAL_EGRESS_CLIENT_VOLUME")
        super().__init__(cwd="/workspace", timeout=min(timeout, 180))
        self._server, self._run_id = server, run_id
        self._cleanup_lock = threading.Lock()
        self._recovery_lock = threading.Lock()
        self._closed = False
        self._synced_files = {}
        self._checkpoint_pending = False
        self._container = f"owh-sandbox-{uuid4().hex}"
        self._docker = shutil.which("docker") or "docker"
        self._client_env = {
            "PATH": os.defpath,
            "DOCKER_HOST": "unix:///var/run/docker.sock",
        }
        # docker run would silently create an empty volume on a name mismatch.
        for kind, name in (("network", network), ("volume", ca_volume)):
            try:
                subprocess.run(
                    [self._docker, kind, "inspect", name],
                    check=True,
                    capture_output=True,
                    timeout=15,
                    env=self._client_env,
                )
            except (subprocess.SubprocessError, OSError):
                raise _infrastructure_error(
                    f"Sandbox {kind} could not be verified (sandbox.{kind}_unavailable)."
                ) from None
        ca_path = "/run/owh-egress-ca.crt"
        args = [
            self._docker,
            "run",
            "--detach",
            "--rm",
            "--name",
            self._container,
            "--label",
            "open-work-hub.hermes-sandbox=1",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=512",
            "--cpus=2",
            "--memory=2g",
            "--memory-swap=2g",
            "--shm-size=64m",
            "--user=10000:10000",
            "--workdir=/workspace",
            "--entrypoint=/bin/sleep",
            f"--network={'none' if preview else network}",
            "--tmpfs=/workspace:rw,exec,nosuid,size=256m,mode=1777",
            "--tmpfs=/tmp:rw,exec,nosuid,size=256m,mode=1777",
            "--tmpfs=/opt/data:rw,exec,nosuid,size=64m,uid=10000,gid=10000",
            "--tmpfs=/home/hermes:rw,exec,nosuid,size=64m,uid=10000,gid=10000",
            "--mount",
            f"type=volume,src={ca_volume},dst={ca_path},volume-subpath=ca.crt,readonly",
        ]
        if preview:
            # Chromium keeps its own user/PID/network namespace and seccomp
            # sandbox. No extra Linux capability or host IPC is granted.
            args.extend(["--security-opt", f"seccomp={Path(__file__).with_name('chromium-seccomp.json')}"])
        environment = {
            "HOME": "/home/hermes",
            "HTTP_PROXY": "http://hermes-terminal-egress:19091",
            "HTTPS_PROXY": "http://hermes-terminal-egress:19090",
            "NO_PROXY": policy["no_proxy"],
            "no_proxy": policy["no_proxy"],
            "REQUESTS_CA_BUNDLE": ca_path,
            "SSL_CERT_FILE": ca_path,
            "NODE_EXTRA_CA_CERTS": ca_path,
        }
        for key, value in environment.items():
            args.extend(["--env", f"{key}={value}"])
        # A lost gateway cannot leave an unbounded orphan or background process.
        args.extend([policy["image"], "3600"])
        try:
            try:
                subprocess.run(
                    args,
                    check=True,
                    capture_output=True,
                    timeout=120,
                    env=self._client_env,
                )
            except subprocess.CalledProcessError as error:
                # Return only known categories, never Docker argv/stderr or
                # host paths. Native Hermes renders this as a degraded backend.
                stderr = error.stderr or b""
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", errors="replace")
                if "ca.crt" in stderr and "no such file or directory" in stderr.lower():
                    reason = "Sandbox egress certificate is missing (sandbox.egress_ca_missing)."
                else:
                    reason = f"Sandbox could not start (sandbox.start_failed; Docker exit {error.returncode})."
                raise _infrastructure_error(reason) from None
            except subprocess.TimeoutExpired:
                raise _infrastructure_error(
                    "Sandbox startup timed out (sandbox.start_timeout)."
                ) from None
            except OSError:
                raise _infrastructure_error(
                    "Sandbox Docker client is unavailable (sandbox.docker_unavailable)."
                ) from None
            self.restore_files()
        except Exception:
            try:
                self.cleanup()
            except (subprocess.SubprocessError, OSError, EnvironmentConnectionError):
                # Preserve the actionable original failure; the one-hour
                # deadline still bounds a container if Docker is unreachable.
                pass
            raise

    def _run_bash(self, cmd_string, *, login=False, timeout=120, stdin_data=None):
        from .file_write_boundary import FILE_WRITE_SCRIPT
        from .native_execution import file_write_environment

        shell = ["/bin/bash", "-c", cmd_string]
        if file_write_environment.get() is self:
            shell = [
                "/opt/hermes/.venv/bin/python", "-I", "-c", FILE_WRITE_SCRIPT, cmd_string
            ]
        # A regular anonymous file avoids a pipe writer thread/deadlock for
        # large stdin. It is private transport scratch, never authoritative.
        with tempfile.TemporaryFile(mode="w+t") as source:
            if stdin_data is not None:
                source.write(stdin_data)
                source.seek(0)
            return subprocess.Popen(
                [
                    self._docker,
                    "exec",
                    "-i",
                    self._container,
                    "/usr/bin/timeout",
                    "--kill-after=5",
                    str(min(timeout, 180)),
                    *shell,
                ],
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._client_env,
            )

    def _workspace(self, request):
        completed = subprocess.run(
            [
                self._docker,
                "exec",
                "-i",
                self._container,
                "/opt/hermes/.venv/bin/python",
                "-I",
                "-c",
                WORKSPACE_SCRIPT,
            ],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=90,
            env=self._client_env,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError("Workspace transfer failed")
        return json.loads(completed.stdout)

    def restore_files(self):
        from . import _rpc

        for row in _rpc(self._server, self._run_id, "owh/files/list", {})["files"]:
            if self._synced_files.get(row["relative_path"]) == row["sha256"]:
                continue
            body = _rpc(self._server, self._run_id, "owh/files/read", {"id": row["id"]})
            self._workspace(
                {
                    "op": "write",
                    "path": row["relative_path"],
                    "data": body["data"],
                    "sha256": row["sha256"],
                }
            )
            self._synced_files[row["relative_path"]] = row["sha256"]

    def save_files(self):
        from . import _rpc, runtime_transport

        # Reused conversation environments must use the CURRENT native run.
        server, run_id = runtime_transport()
        remote = {
            row["relative_path"]: row["sha256"]
            for row in _rpc(server, run_id, "owh/files/list", {})["files"]
        }
        local = self._workspace({"op": "list"})
        for row in local:
            if remote.get(row["path"]) != row["sha256"]:
                self._checkpoint_pending = True
                body = self._workspace({"op": "read", "path": row["path"]})
                _rpc(
                    server,
                    run_id,
                    "owh/files/write",
                    {"path": row["path"], "data": body["data"]},
                )
                self._synced_files[row["path"]] = row["sha256"]
        if self._checkpoint_pending:
            _rpc(server, run_id, "owh/files/checkpoint", {})
            self._checkpoint_pending = False
        # Keep saved files as history even when the sandbox deletes them.

    def execute(self, command, cwd="", **kwargs):
        from tools.interrupt import is_interrupted

        from . import runtime_transport

        if is_interrupted():
            self.cleanup()
        if self._closed or not self._container:
            # Native remote-kernel polling retries exceptions; an explicit
            # non-JSON response ends that protocol promptly on cancellation.
            return {"returncode": 130, "output": "OWH sandbox execution ended"}
        self._server, self._run_id = runtime_transport()
        self.restore_files()
        result = super().execute(command, cwd, **kwargs)
        if result.get("returncode") in {124, 130}:
            self.cleanup()
        if not self._container:
            return result
        try:
            self.save_files()
        except Exception:
            return {
                "returncode": 1,
                "output": "Workspace files could not be saved. Retry before finishing; this operation is not complete.",
            }
        return result

    def _kill_process(self, proc):
        # Killing only the Docker client leaves detached code/children alive.
        try:
            self.cleanup()
        finally:
            proc.kill()

    def cleanup(self, **kwargs):
        with self._cleanup_lock:
            self._closed = True
            if getattr(self, "_container", None):
                result = subprocess.run(
                    [self._docker, "rm", "--force", self._container],
                    capture_output=True,
                    timeout=30,
                    env=self._client_env,
                    check=False,
                )
                if result.returncode:
                    probe = subprocess.run(
                        [
                            self._docker, "ps", "--all", "--filter",
                            f"name=^{self._container}$", "--format", "{{.ID}}",
                        ],
                        capture_output=True, timeout=15, env=self._client_env, check=False,
                    )
                    if probe.returncode or (probe.stdout or b"").strip():
                        raise _infrastructure_error(
                            "Sandbox removal was not confirmed (sandbox.cleanup_failed)."
                        )
                self._container = None


class OpenWorkHubSandbox(TerminalEnvironmentProvider):
    name = "owh_sandbox"
    session_isolated_when_nonpersistent = True
    skip_container_guards = False

    def is_available(self) -> bool:
        return shutil.which("docker") is not None

    def create_environment(
        self, *, cwd, timeout, task_id, image=None, container_config=None
    ):
        from . import _rpc, runtime_transport

        server, run_id = runtime_transport()
        context = _rpc(server, run_id, "owh/context", {})
        if not context.get("allow_native_tools"):
            raise RuntimeError("This workload cannot execute code")
        environment = WorkspaceEnvironment(
            policy=context["sandbox"], server=server, run_id=run_id, timeout=timeout
        )
        environment._task_id = task_id
        return environment
