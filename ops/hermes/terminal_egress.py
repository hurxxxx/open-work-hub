"""Run Hermes' official iron-proxy for isolated terminal sessions.

The real OpenRouter credential stays in this trusted proxy container. Terminal
containers receive only the official proxy token and the public interception
CA certificate through a separate read-only volume.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import time

from agent.proxy_sources.iron_proxy import (
    build_proxy_config,
    discover_provider_mappings,
    ensure_audit_log,
    ensure_ca_cert,
    find_iron_proxy,
    get_status,
    load_mappings,
    merge_mappings,
    start_proxy,
    stop_proxy,
    write_mappings,
    write_proxy_config,
)


_TUNNEL_PORT = 19090
_CLIENT_DIR = Path(os.environ.get("OWH_HERMES_TERMINAL_EGRESS_CLIENT_DIR", "/opt/data/home/egress-client"))
_stop_requested = False


def _handle_stop(_signum: int, _frame: object) -> None:
    global _stop_requested
    _stop_requested = True


def _required_openrouter_key() -> str:
    value = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if len(value) < 16:
        raise RuntimeError("OPENROUTER_API_KEY is missing or too short")
    return value


def _write_client_file(name: str, data: str, *, mode: int) -> None:
    _CLIENT_DIR.mkdir(parents=True, exist_ok=True)
    target = _CLIENT_DIR / name
    temporary = _CLIENT_DIR / f".{name}.tmp"
    temporary.write_text(data, encoding="utf-8")
    temporary.chmod(mode)
    temporary.replace(target)


def main() -> None:
    _required_openrouter_key()
    binary = find_iron_proxy(install_if_missing=True)
    if binary is None:
        raise RuntimeError("Hermes could not install the pinned iron-proxy binary")
    ca_cert, ca_key = ensure_ca_cert()
    discovered = [
        mapping
        for mapping in discover_provider_mappings(
            available_env_names=["OPENROUTER_API_KEY"]
        )
        if mapping.real_env_name == "OPENROUTER_API_KEY"
    ]
    mappings = merge_mappings(existing=load_mappings(), discovered=discovered)
    if len(mappings) != 1:
        raise RuntimeError("Hermes did not create the OpenRouter proxy-token mapping")
    write_mappings(mappings)
    audit_log = ca_cert.parent / "audit.log"
    ensure_audit_log(audit_log)
    config = build_proxy_config(
        mappings=mappings,
        ca_cert=ca_cert,
        ca_key=ca_key,
        tunnel_port=_TUNNEL_PORT,
        audit_log=audit_log,
        allowed_hosts=["*"],
        # None selects Hermes' official loopback/link-local/RFC1918/metadata
        # deny list. Public internet remains available through the wildcard.
        upstream_deny_cidrs=None,
        # This bind is container-internal on a non-published network. It is
        # never exposed on a host/LAN interface.
        http_listen=[f"0.0.0.0:{_TUNNEL_PORT}"],
    )
    # v0.39 evaluates this setting on CONNECT before origin headers exist.
    config["transforms"][1]["config"]["secrets"][0]["replace"]["require"] = False
    config_path = write_proxy_config(config)
    _write_client_file("openrouter.token", mappings[0].proxy_token + "\n", mode=0o600)
    _CLIENT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ca_cert, _CLIENT_DIR / "ca.crt")
    (_CLIENT_DIR / "ca.crt").chmod(0o644)

    start_proxy(
        binary=binary,
        config_path=config_path,
        extra_env={"OPENROUTER_API_KEY": _required_openrouter_key()},
        install_if_missing=False,
    )
    status = get_status()
    if not status.listening:
        raise RuntimeError("Hermes iron-proxy did not start listening")
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signal_number, _handle_stop)
    while not _stop_requested:
        current = get_status()
        if not current.listening:
            raise RuntimeError("Hermes iron-proxy stopped unexpectedly")
        time.sleep(2)
    stop_proxy()


if __name__ == "__main__":
    main()
