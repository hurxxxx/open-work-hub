"""Non-inference smoke check in the development gateway; see the Hermes owner doc.

Uses the pinned native provider/BaseEnvironment and real disposable Docker
sandboxes. Only the file RPC is replaced with synthetic per-conversation test
fixtures in this short-lived process. No application data or model is used.
"""

import base64
import hashlib
import json
import subprocess
import sys
from contextvars import ContextVar
from unittest.mock import patch

sys.path.insert(0, "/opt/hermes/plugins")
import owh_runtime
from owh_runtime.sandbox import WorkspaceEnvironment

image = sys.argv[1]
current = ContextVar("sandbox_check_conversation", default="first")
snapshots = {"first": {}, "second": {}}
containers = []


def transport():
    return {"fixture": current.get()}, "run_synthetic_sandbox_check"


def rpc(server, run_id, method, params):
    assert run_id == "run_synthetic_sandbox_check"
    files = snapshots[server["fixture"]]
    if method == "owh/files/list":
        return {"files": list(files.values())}
    if method == "owh/files/read":
        return files[params["id"]]
    if method == "owh/files/write":
        path = params["path"]
        files[path] = {
            "id": path,
            "relative_path": path,
            "sha256": hashlib.sha256(base64.b64decode(params["data"])).hexdigest(),
            "data": params["data"],
        }
        return {}
    raise AssertionError("Unexpected synthetic file operation")


def create(conversation):
    current.set(conversation)
    server, run_id = transport()
    environment = WorkspaceEnvironment(
        policy={"image": image, "no_proxy": "localhost,127.0.0.1,::1"},
        server=server,
        run_id=run_id,
        timeout=30,
    )
    containers.append(environment)
    return environment


def execute(environment, conversation, command):
    current.set(conversation)
    result = environment.execute(command)
    assert result["returncode"] == 0, "Synthetic sandbox command failed"
    return result["output"]


with (
    patch.object(owh_runtime, "_rpc", rpc),
    patch.object(owh_runtime, "runtime_transport", transport),
):
    try:
        first, second = create("first"), create("second")
        assert first._container != second._container
        for environment in (first, second):
            details = json.loads(
                subprocess.check_output(
                    [environment._docker, "inspect", environment._container],
                    env=environment._client_env,
                )
            )[0]
            host = details["HostConfig"]
            assert host["ReadonlyRootfs"] and host["CapDrop"] == ["ALL"]
            assert "no-new-privileges" in host["SecurityOpt"]
            assert details["Config"]["User"] == "10000:10000"
            assert (
                host["Memory"] == 2 * 1024**3 and host["MemorySwap"] == host["Memory"]
            )
            assert host["NanoCpus"] == 2 * 10**9 and host["PidsLimit"] == 512
            assert all(mount["Type"] != "bind" for mount in details["Mounts"])
            volumes = [
                mount for mount in details["Mounts"] if mount["Type"] == "volume"
            ]
            assert len(volumes) == 1 and not volumes[0]["RW"]
            assert volumes[0]["Destination"] == "/run/owh-egress-ca.crt"

        execute(
            first,
            "first",
            'test ! -e /var/run/docker.sock && test -r /run/owh-egress-ca.crt && test -z "$OPENROUTER_API_KEY$API_SERVER_KEY"',
        )
        execute(first, "first", "printf sandbox-check-content > proof.txt")
        execute(second, "second", "test ! -e /workspace/proof.txt")
        assert "proof.txt" in snapshots["first"] and not snapshots["second"]
        first.cleanup()
        restored = create("first")
        assert "sandbox-check-content" in execute(
            restored, "first", "cat /workspace/proof.txt"
        )
        print(
            "PASS: two isolated sandboxes, security limits, CA access, file save/restore"
        )
    finally:
        for environment in containers:
            environment.cleanup()
