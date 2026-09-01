"""Configure Open Work Hub-managed Hermes profiles before gateway startup.

This runs inside the pinned Hermes image before the gateway starts. Hermes
intentionally scopes provider and API-server credentials per profile, so the
root profile and existing named profiles must receive the same deployment
credentials before multiplexed requests can be authenticated. Model and
fallback behavior is configured through Hermes' public config surface.
"""

from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import re
from typing import Any

from hermes_cli.config import load_config, save_config, save_env_value
from hermes_cli.profiles import list_profiles
from hermes_constants import (
    get_hermes_home,
    reset_hermes_home_override,
    set_hermes_home_override,
)


_MANAGED_PROFILE_PATTERN = re.compile(r"^owh-[0-9a-f]{32}(?:-jobs)?$")
_FIXED_PROVIDER = "openrouter"
_FIXED_MODEL = "qwen/qwen3.8-flash"


def _is_open_work_hub_profile(profile_name: str) -> bool:
    return profile_name == "default" or bool(
        _MANAGED_PROFILE_PATTERN.fullmatch(profile_name)
    )


def _apply_fixed_model_policy(config: dict[str, Any]) -> bool:
    """Apply Hermes' official fixed-model and fallback settings.

    Hermes auxiliary tasks have an independent built-in OpenRouter fallback
    model. ``auxiliary.openrouter_model`` replaces that default without
    patching Hermes' runtime. Modern and legacy primary fallback chains are
    disabled separately.
    """

    before = deepcopy(config)
    config["model"] = {
        "provider": _FIXED_PROVIDER,
        "default": _FIXED_MODEL,
    }
    config["fallback_providers"] = []
    config.pop("fallback_model", None)

    auxiliary = config.get("auxiliary")
    if not isinstance(auxiliary, dict):
        auxiliary = {}
        config["auxiliary"] = auxiliary
    auxiliary["free_only"] = False
    auxiliary["openrouter_model"] = _FIXED_MODEL

    return before != config


def _reconcile_fixed_model_config(profile_name: str) -> bool:
    if not _is_open_work_hub_profile(profile_name):
        return False
    config = load_config()
    if not _apply_fixed_model_policy(config):
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
        return _reconcile_fixed_model_config(profile_name)
    finally:
        reset_hermes_home_override(token)


def main() -> None:
    secrets = {
        "API_SERVER_KEY": _required_secret("API_SERVER_KEY", minimum_length=16),
        "OPENROUTER_API_KEY": _required_secret(
            "OPENROUTER_API_KEY",
            minimum_length=16,
        ),
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
