"""Pinned v2026.8.31 official environment-provider extension.

DockerEnvironment unconditionally adds host credential/skill/cache bind mounts
and has no switch to disable them. This small BaseEnvironment implementation
supplies only the container transport; native Hermes owns command wrapping,
timeouts, interrupts, environment caching and agent/session lifecycle.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from uuid import uuid4

from agent.terminal_env_provider import TerminalEnvironmentProvider
from tools.environments.base import BaseEnvironment

from .workspace import WORKSPACE_SCRIPT


class WorkspaceEnvironment(BaseEnvironment):
    def __init__(self, *, policy: dict, server: dict, run_id: str, timeout: int):
        super().__init__(cwd="/workspace", timeout=min(timeout, 180))
        self._server, self._run_id = server, run_id
        self._synced_files = {}
        self._container = f"owh-sandbox-{uuid4().hex}"
        self._docker = shutil.which("docker") or "docker"
        self._client_env = {
            "PATH": os.defpath,
            "DOCKER_HOST": "unix:///var/run/docker.sock",
        }
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
            f"--network={policy['network']}",
            "--tmpfs=/workspace:rw,exec,nosuid,size=256m,mode=1777",
            "--tmpfs=/tmp:rw,exec,nosuid,size=256m,mode=1777",
            "--tmpfs=/opt/data:rw,exec,nosuid,size=64m,uid=10000,gid=10000",
            "--tmpfs=/home/hermes:rw,exec,nosuid,size=64m,uid=10000,gid=10000",
            "--mount",
            f"type=volume,src={policy['ca_volume']},dst={ca_path},volume-subpath=ca.crt,readonly",
        ]
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
            subprocess.run(args, check=True, capture_output=True, timeout=120, env=self._client_env)
            self.restore_files()
        except Exception:
            self.cleanup()
            raise

    def _run_bash(self, cmd_string, *, login=False, timeout=120, stdin_data=None):
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
                    "/bin/bash",
                    "-c",
                    cmd_string,
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
                body = self._workspace({"op": "read", "path": row["path"]})
                _rpc(
                    server,
                    run_id,
                    "owh/files/write",
                    {"path": row["path"], "data": body["data"]},
                )
                self._synced_files[row["path"]] = row["sha256"]
        # Keep saved files as history even when the sandbox deletes them.

    def execute(self, command, cwd="", **kwargs):
        from . import runtime_transport

        self._server, self._run_id = runtime_transport()
        self.restore_files()
        result = super().execute(command, cwd, **kwargs)
        try:
            self.save_files()
        except Exception:
            return {
                "returncode": 1,
                "output": "Workspace files could not be saved. Retry before finishing; this operation is not complete.",
            }
        return result

    def cleanup(self, **kwargs):
        if getattr(self, "_container", None):
            subprocess.run(
                [self._docker, "rm", "--force", self._container],
                capture_output=True,
                timeout=30,
                env=self._client_env,
            )
            self._container = None


class OpenWorkHubSandbox(TerminalEnvironmentProvider):
    name = "owh_sandbox"
    session_isolated_when_nonpersistent = True
    skip_container_guards = False

    def is_available(self) -> bool:
        return shutil.which("docker") is not None

    def create_environment(self, *, cwd, timeout, task_id, image=None, container_config=None):
        from . import _rpc, runtime_transport

        server, run_id = runtime_transport()
        context = _rpc(server, run_id, "owh/context", {})
        if not context.get("allow_native_tools"):
            raise RuntimeError("This workload cannot execute code")
        return WorkspaceEnvironment(
            policy=context["sandbox"], server=server, run_id=run_id, timeout=timeout
        )
