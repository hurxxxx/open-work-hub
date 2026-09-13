"""Configure Open Work Hub-managed Hermes profiles before gateway startup.

This runs inside the pinned Hermes image before the gateway starts. Hermes
intentionally scopes provider and API-server credentials per profile, so the
root profile and existing named profiles must receive the same deployment
credentials before multiplexed requests can be authenticated. Model and
fallback behavior is configured through Hermes' public config surface.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from hermes_cli.config import load_config, save_config, save_env_value
from hermes_cli.profiles import list_profiles
from hermes_constants import (
    get_hermes_home,
    reset_hermes_home_override,
    set_hermes_home_override,
)

_MANAGED_PROFILE_PATTERN = re.compile(r"^owh-[0-9a-f]{32}(?:-local)?(?:-jobs)?$")
_COMPRESSION_POLICY = {
    "enabled": True,
    "threshold": 0.50,
    "threshold_tokens": 100_000,
    "target_ratio": 0.20,
    "protect_last_n": 20,
    "proactive_prune_tokens": 48_000,
    "proactive_prune_min_result_chars": 8_000,
    "proactive_prune_min_reclaim_tokens": 4_096,
}


def _is_open_work_hub_profile(profile_name: str) -> bool:
    return profile_name == "default" or bool(_MANAGED_PROFILE_PATTERN.fullmatch(profile_name))


def _apply_runtime_policy(config: dict[str, Any]) -> bool:
    """Bootstrap transport/lifecycle only; administrator DB owns model selection."""
    before = deepcopy(config)
    plugins = config.setdefault("plugins", {})
    plugins["enabled"] = sorted(set(plugins.get("enabled", [])) | {"owh_runtime"})
    plugins["disabled"] = [name for name in plugins.get("disabled", []) if name != "owh_runtime"]
    config.setdefault("gateway", {}).setdefault("api_server", {})["max_concurrent_runs"] = 0
    config["terminal"] = {
        "backend": "owh_sandbox",
        "container_persistent": False,
        "cwd": "/workspace",
    }
    config.setdefault("platform_toolsets", {})["api_server"] = [
        "web",
        "terminal",
        "file",
        "skills",
        "todo",
        "memory",
        "session_search",
        "code_execution",
        "delegation",
        "owh_runtime",
    ]
    config["compression"] = {**config.get("compression", {}), **_COMPRESSION_POLICY}
    config.setdefault("agent", {})["api_max_retries"] = 1
    return before != config


def _reconcile_runtime_config(profile_name: str) -> bool:
    if not _is_open_work_hub_profile(profile_name):
        return False
    config = load_config()
    if not _apply_runtime_policy(config):
        return False
    save_config(config)
    return True


def _required_secret(name: str, *, minimum_length: int = 1) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) < minimum_length:
        raise RuntimeError(f"{name} is missing or too short")
    return value


def _profile_targets(root: Path) -> list[tuple[str, Path]]:
    resolved_root = root.resolve()
    profiles_root = (resolved_root / "profiles").resolve()
    targets = {resolved_root: "default"}
    for profile in list_profiles():
        path = Path(profile.path).resolve()
        if path == resolved_root:
            continue
        if profiles_root in path.parents:
            targets[path] = str(profile.name)
    return sorted(
        ((name, path) for path, name in targets.items()),
        key=lambda item: str(item[1]),
    )


def _reconcile_profile(
    profile_name: str,
    profile_dir: Path,
    secrets: dict[str, str],
) -> bool:
    token = set_hermes_home_override(str(profile_dir))
    try:
        for name, value in secrets.items():
            save_env_value(name, value)
        return _reconcile_runtime_config(profile_name)
    finally:
        reset_hermes_home_override(token)


def main() -> None:
    secrets = {
        "API_SERVER_KEY": _required_secret("API_SERVER_KEY", minimum_length=16),
    }
    targets = _profile_targets(get_hermes_home())
    reconciled = 0
    for profile_name, target in targets:
        reconciled += int(_reconcile_profile(profile_name, target, secrets))
    print(
        "Hermes bootstrap synchronized "
        f"{len(targets)} profile(s); reconciled {reconciled} "
        "Open Work Hub profile(s)."
    )


if __name__ == "__main__":
    main()
