from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
NETWORK_KEY = "OWH_HERMES_TERMINAL_SANDBOX_NETWORK"
VOLUME_KEY = "OWH_HERMES_TERMINAL_EGRESS_CLIENT_VOLUME"


@pytest.fixture
def sandbox(monkeypatch):
    class BaseEnvironment:
        def __init__(self, **kwargs):
            pass

    class EnvironmentConnectionError(RuntimeError):
        def __init__(self, reason, *, retry_hint=""):
            super().__init__(reason)
            self.reason, self.retry_hint = reason, retry_hint

    for name, members in {
        "agent.terminal_env_provider": {"TerminalEnvironmentProvider": object},
        "tools.environments.base": {
            "BaseEnvironment": BaseEnvironment,
            "EnvironmentConnectionError": EnvironmentConnectionError,
        },
    }.items():
        module = ModuleType(name)
        module.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, module)
    directory = ROOT / "ops/hermes/plugins/owh_runtime"
    package = ModuleType("owh_sandbox_test")
    package.__path__ = [str(directory)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    spec = importlib.util.spec_from_file_location(
        "owh_sandbox_test.sandbox", directory / "sandbox.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv(NETWORK_KEY, "deployment-network")
    monkeypatch.setenv(VOLUME_KEY, "deployment-ca")
    monkeypatch.setattr(module.shutil, "which", lambda _: "/usr/bin/docker")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.WorkspaceEnvironment, "restore_files", lambda _: None)

    def create():
        return module.WorkspaceEnvironment(
            policy={
                "image": "pinned-image",
                "no_proxy": "localhost",
                # Older APIs can still send these during a rolling update.
                "network": "database-namespace-network",
                "ca_volume": "database-namespace-ca",
            },
            server={},
            run_id="synthetic-run",
            timeout=120,
        )

    return SimpleNamespace(
        module=module, create=create, calls=calls, error=EnvironmentConnectionError
    )


@pytest.mark.parametrize("deployment", ["dev", "prod"])
def test_compose_gateway_and_broker_use_the_declared_sandbox_resources(deployment):
    suffix = "infra" if deployment == "dev" else "app"
    compose = yaml.safe_load(
        (ROOT / f"ops/compose/open-work-hub-{deployment}.{suffix}.yml").read_text()
    )
    network = compose["networks"]["open-work-hub-hermes-terminal-sandbox"]
    volume = compose["volumes"][f"open-work-hub-{deployment}-hermes-terminal-egress-client"]
    assert network["internal"] is True
    for service in ("hermes-gateway", "hermes-terminal-broker"):
        environment = compose["services"][service]["environment"]
        assert environment[NETWORK_KEY] == network["name"]
        assert environment[VOLUME_KEY] == volume["name"]


def test_sandbox_uses_deployment_resources_and_checks_before_creation(sandbox):
    environment = sandbox.create()
    try:
        assert sandbox.calls[0][1:] == ["network", "inspect", "deployment-network"]
        assert sandbox.calls[1][1:] == ["volume", "inspect", "deployment-ca"]
        args = next(args for args in sandbox.calls if args[1] == "run")
        assert "--network=deployment-network" in args
        assert (
            "type=volume,src=deployment-ca,dst=/run/owh-egress-ca.crt,volume-subpath=ca.crt,readonly"
            in args
        )
        assert "database-namespace" not in " ".join(args)
        assert "--read-only" in args and "--cap-drop=ALL" in args
        assert "--user=10000:10000" in args
        assert "/var/run/docker.sock" not in " ".join(args)
    finally:
        environment.cleanup()


def test_failed_removal_keeps_exact_container_for_retry_and_closes_execution(sandbox, monkeypatch):
    environment = sandbox.create()
    container = environment._container
    original = sandbox.module.subprocess.run
    monkeypatch.setattr(
        sandbox.module.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 1),
    )
    with pytest.raises(sandbox.error, match="sandbox.cleanup_failed"):
        environment.cleanup()
    assert environment._closed and environment._container == container
    monkeypatch.setattr(sandbox.module.subprocess, "run", original)
    environment.cleanup()
    assert environment._container is None


def test_recreated_sandbox_retries_server_checkpoint_without_new_local_changes(
    sandbox, monkeypatch
):
    package = sys.modules["owh_sandbox_test"]
    attempts = []

    def rpc(server, run_id, method, params):
        if method == "owh/files/list":
            return {"files": [{"relative_path": "app.js", "sha256": "saved"}]}
        assert method == "owh/files/checkpoint"
        attempts.append(run_id)
        if len(attempts) == 1:
            raise OSError("synthetic checkpoint outage")
        return {"created": 1}

    monkeypatch.setattr(package, "_rpc", rpc, raising=False)
    monkeypatch.setattr(package, "runtime_transport", lambda: ({}, "run_current"), raising=False)
    monkeypatch.setattr(
        sandbox.module.WorkspaceEnvironment,
        "_workspace",
        lambda *_args: [
            {"path": "app.js", "sha256": "saved"},
        ],
    )
    first = sandbox.create()
    try:
        with pytest.raises(OSError, match="checkpoint outage"):
            first.save_files()
    finally:
        first.cleanup()
    restored = sandbox.create()
    try:
        restored.save_files()
        assert attempts == ["run_current", "run_current"]
    finally:
        restored.cleanup()


def test_preview_uses_an_offline_container_and_preserves_outer_isolation(sandbox):
    environment = sandbox.module.WorkspaceEnvironment(
        policy={"image": "pinned-image", "no_proxy": "localhost"},
        server={},
        run_id="synthetic-run",
        timeout=30,
        preview=True,
    )
    try:
        args = next(args for args in sandbox.calls if args[1] == "run")
        assert "--network=none" in args
        assert "--cap-drop=ALL" in args and "--security-opt=no-new-privileges" in args
        assert "--read-only" in args and "--user=10000:10000" in args
        assert any(value.endswith("chromium-seccomp.json") for value in args)
        assert not any(
            "unconfined" in value or "--cap-add" in value or "--ipc=host" in value for value in args
        )
    finally:
        environment.cleanup()


@pytest.mark.parametrize("key", [NETWORK_KEY, VOLUME_KEY])
@pytest.mark.parametrize("value", [None, "", "../host", "volume,readonly=false"])
def test_missing_or_invalid_deployment_resources_fail_before_docker(
    sandbox, monkeypatch, key, value
):
    if value is None:
        monkeypatch.delenv(key)
    else:
        monkeypatch.setenv(key, value)
    with pytest.raises(sandbox.error, match="sandbox.configuration_invalid"):
        sandbox.create()
    assert not sandbox.calls


@pytest.mark.parametrize("resource", ["network", "volume"])
def test_missing_resources_never_start_a_container_or_create_a_volume(
    sandbox, monkeypatch, resource
):
    def run(args, **kwargs):
        sandbox.calls.append(args)
        if args[1] == resource:
            raise subprocess.CalledProcessError(1, args, stderr=b"private daemon detail")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(sandbox.module.subprocess, "run", run)
    with pytest.raises(sandbox.error, match=f"sandbox.{resource}_unavailable") as error:
        sandbox.create()
    assert "private" not in str(error.value)
    assert all(args[1] != "run" for args in sandbox.calls)


@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize(
    "failure,code",
    [
        (
            subprocess.CalledProcessError(
                127,
                ["docker", "private-argument"],
                stderr=b"cannot access path /private/ca.crt: no such file or directory",
            ),
            "sandbox.egress_ca_missing",
        ),
        (
            subprocess.CalledProcessError(
                125, ["docker", "private-argument"], stderr=b"private daemon detail"
            ),
            "sandbox.start_failed",
        ),
        (subprocess.TimeoutExpired(["docker", "private-argument"], 120), "sandbox.start_timeout"),
        (FileNotFoundError("private docker path"), "sandbox.docker_unavailable"),
    ],
)
def test_start_failure_is_safe_actionable_and_survives_cleanup_failure(
    sandbox, monkeypatch, failure, code, cleanup_fails
):
    def run(args, **kwargs):
        sandbox.calls.append(args)
        if args[1] == "run":
            raise failure
        if args[1] == "rm" and cleanup_fails:
            raise OSError("private cleanup detail")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(sandbox.module.subprocess, "run", run)
    with pytest.raises(sandbox.error, match=code) as error:
        sandbox.create()
    assert "private" not in str(error.value)
    assert "administrator" in error.value.retry_hint.lower()
    assert any(args[1] == "rm" for args in sandbox.calls)
