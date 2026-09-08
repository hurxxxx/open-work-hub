import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


def _workspace_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[4]


WORKSPACE_ROOT = _workspace_root()
OPEN_WORK_HUB_DESKTOP_UPDATE_MANIFEST_PATH = (
    WORKSPACE_ROOT / "packages" / "contracts" / "open-work-hub-desktop-update-feed.manifest.json"
)


class OpenWorkHubDesktopUpdateManifestError(ValueError):
    pass


@dataclass(frozen=True)
class DesktopUpdatePlatformManifest:
    platform: str
    package_name: str
    installer_url_env: str
    installer_stable_copy: str
    update_dir_env: str
    default_dir: str
    update_file: str
    served_artifact_suffixes: frozenset[str]

    @property
    def attachment_suffixes(self) -> frozenset[str]:
        return frozenset(
            suffix for suffix in self.served_artifact_suffixes if suffix != ".blockmap"
        )


@dataclass(frozen=True)
class DesktopUpdateManifestProjection:
    platforms: tuple[str, ...]
    feed_path_prefix: str
    update_base_url_env: str
    trusted_update_origins_env: str
    served_artifact_content_types: Mapping[str, str]
    platform_configs: Mapping[str, DesktopUpdatePlatformManifest]

    def platform_config(self, platform: str) -> DesktopUpdatePlatformManifest:
        config = self.platform_configs.get(platform)
        if config is None:
            raise KeyError(f"Unsupported Open Work Hub desktop update platform: {platform}")
        return config

    @property
    def metadata_files(self) -> dict[str, str]:
        return {platform: self.platform_config(platform).update_file for platform in self.platforms}

    @property
    def artifact_suffixes(self) -> dict[str, frozenset[str]]:
        return {
            platform: self.platform_config(platform).served_artifact_suffixes
            for platform in self.platforms
        }

    @property
    def attachment_suffixes(self) -> dict[str, frozenset[str]]:
        return {
            platform: self.platform_config(platform).attachment_suffixes
            for platform in self.platforms
        }


@lru_cache(maxsize=1)
def open_work_hub_desktop_update_manifest() -> dict[str, Any]:
    return validate_open_work_hub_desktop_update_manifest(
        json.loads(OPEN_WORK_HUB_DESKTOP_UPDATE_MANIFEST_PATH.read_text(encoding="utf-8"))
    )


@lru_cache(maxsize=1)
def open_work_hub_desktop_update_manifest_projection() -> DesktopUpdateManifestProjection:
    return project_open_work_hub_desktop_update_manifest(open_work_hub_desktop_update_manifest())


def validate_open_work_hub_desktop_update_manifest(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OpenWorkHubDesktopUpdateManifestError(
            "Open Work Hub desktop update manifest must be an object."
        )

    platform_order = value.get("platformOrder")
    platforms = value.get("platforms")
    _manifest_feed_path_prefix(value, "feedPathPrefix")
    _manifest_env_name(value, "updateBaseUrlEnv", platform="manifest")
    _manifest_env_name(value, "trustedUpdateOriginsEnv", platform="manifest")
    served_artifact_content_types = _manifest_content_type_map(
        value.get("servedArtifactContentTypes"),
        "servedArtifactContentTypes",
    )
    if not isinstance(platform_order, list) or not platform_order:
        raise OpenWorkHubDesktopUpdateManifestError(
            "Open Work Hub desktop update manifest platformOrder is invalid."
        )
    if not isinstance(platforms, dict):
        raise OpenWorkHubDesktopUpdateManifestError(
            "Open Work Hub desktop update manifest platforms is invalid."
        )

    seen: set[str] = set()
    for platform in platform_order:
        if not isinstance(platform, str) or not platform:
            raise OpenWorkHubDesktopUpdateManifestError(
                "Open Work Hub desktop update platform name is invalid."
            )
        if platform in seen:
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop update platform is duplicated: {platform}."
            )
        seen.add(platform)
        config = platforms.get(platform)
        if not isinstance(config, dict):
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop update platform config is missing: {platform}."
            )
        _validate_platform_config(platform, config, served_artifact_content_types)
    return value


def project_open_work_hub_desktop_update_manifest(
    manifest: Mapping[str, Any],
) -> DesktopUpdateManifestProjection:
    platform_names = tuple(str(platform) for platform in manifest["platformOrder"])
    platform_configs = {
        platform: _project_platform_manifest(
            platform,
            manifest["platforms"][platform],
        )
        for platform in platform_names
    }
    return DesktopUpdateManifestProjection(
        platforms=platform_names,
        feed_path_prefix=str(manifest["feedPathPrefix"]),
        update_base_url_env=str(manifest["updateBaseUrlEnv"]),
        trusted_update_origins_env=str(manifest["trustedUpdateOriginsEnv"]),
        served_artifact_content_types={
            str(suffix): str(content_type)
            for suffix, content_type in manifest["servedArtifactContentTypes"].items()
        },
        platform_configs=platform_configs,
    )


def _project_platform_manifest(
    platform: str,
    config: Mapping[str, Any],
) -> DesktopUpdatePlatformManifest:
    return DesktopUpdatePlatformManifest(
        platform=platform,
        package_name=str(config["packageName"]),
        installer_url_env=str(config["installerUrlEnv"]),
        installer_stable_copy=str(config["installerStableCopy"]),
        update_dir_env=str(config["updateDirEnv"]),
        default_dir=str(config["defaultDir"]),
        update_file=str(config["updateFile"]),
        served_artifact_suffixes=frozenset(
            str(suffix) for suffix in config["servedArtifactSuffixes"]
        ),
    )


def _validate_platform_config(
    platform: str,
    config: Mapping[str, object],
    served_artifact_content_types: Mapping[str, str],
) -> None:
    _manifest_string(config, "packageName", platform=platform)
    _manifest_env_name(
        config,
        "installerUrlEnv",
        platform=platform,
        prefix="VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_",
    )
    _manifest_file_name(config, "installerStableCopy", platform=platform)
    _manifest_env_name(
        config,
        "updateDirEnv",
        platform=platform,
        prefix="OPEN_WORK_HUB_DESKTOP_UPDATE_",
    )
    _manifest_relative_path(config, "defaultDir", platform=platform)
    _manifest_file_name(config, "updateFile", platform=platform)
    _manifest_suffix_list(
        config.get("servedArtifactSuffixes"),
        "servedArtifactSuffixes",
        platform,
    )
    _validate_served_artifact_content_types(
        config,
        platform,
        served_artifact_content_types,
    )
    _validate_manifest_rules(config.get("packagedArtifacts"), "packagedArtifacts", platform)
    _validate_manifest_rules(
        config.get("stableCopies"),
        "stableCopies",
        platform,
        require_target=True,
    )
    stable_copies = config.get("stableCopies")
    installer_stable_copy = config.get("installerStableCopy")
    if not isinstance(stable_copies, list) or not any(
        isinstance(rule, dict) and rule.get("to") == installer_stable_copy for rule in stable_copies
    ):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop installerStableCopy must reference a stable copy target for {platform}."
        )


def _validate_manifest_rules(
    value: object,
    field: str,
    platform: str,
    *,
    require_target: bool = False,
) -> None:
    if not isinstance(value, list):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be a list for {platform}."
        )
    for index, rule in enumerate(value):
        if not isinstance(rule, dict):
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop {field}[{index}] must be an object for {platform}."
            )
        has_template = "template" in rule
        has_prefix = "prefixTemplate" in rule
        if has_template == has_prefix:
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop {field}[{index}] must define one matcher for {platform}."
            )
        if has_template:
            _manifest_template(rule, "template", platform=platform)
        if has_prefix:
            _manifest_template(rule, "prefixTemplate", platform=platform)
        if "suffix" in rule:
            suffix = _manifest_string(rule, "suffix", platform=platform)
            if not suffix.startswith("."):
                raise OpenWorkHubDesktopUpdateManifestError(
                    f"Open Work Hub desktop suffix is invalid for {platform}: {suffix}."
                )
        if require_target:
            _manifest_file_name(rule, "to", platform=platform)


def _manifest_string(config: Mapping[str, object], field: str, *, platform: str) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value:
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} is invalid for {platform}."
        )
    return value


def _manifest_env_name(
    config: Mapping[str, object],
    field: str,
    *,
    platform: str,
    prefix: str = "OPEN_WORK_HUB_DESKTOP_",
) -> str:
    value = _manifest_string(config, field, platform=platform)
    if not value.startswith(prefix):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} is invalid for {platform}: {value}."
        )
    return value


def _manifest_relative_path(config: Mapping[str, object], field: str, *, platform: str) -> str:
    value = _manifest_string(config, field, platform=platform)
    if "\\" in value or value.startswith("/") or value.startswith("~"):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be a relative POSIX path for {platform}."
        )
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be a relative POSIX path for {platform}."
        )
    return value


def _manifest_feed_path_prefix(config: Mapping[str, object], field: str) -> str:
    value = config.get(field)
    if not isinstance(value, str) or not value.startswith("/") or value.startswith("//"):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be an absolute path prefix."
        )
    if "\\" in value or "?" in value or "#" in value or value.endswith("/"):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be a clean absolute path prefix."
        )
    parts = value.split("/")[1:]
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be a clean absolute path prefix."
        )
    return value


def _manifest_file_name(config: Mapping[str, object], field: str, *, platform: str) -> str:
    value = _manifest_string(config, field, platform=platform)
    _assert_manifest_file_name(value, field, platform=platform)
    return value


def _manifest_template(config: Mapping[str, object], field: str, *, platform: str) -> str:
    value = _manifest_string(config, field, platform=platform)
    _assert_manifest_file_name(value.replace("${version}", "0.0.0"), field, platform=platform)
    return value


def _manifest_suffix_list(value: object, field: str, platform: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be a non-empty list for {platform}."
        )
    suffixes: list[str] = []
    seen: set[str] = set()
    for index, suffix in enumerate(value):
        if (
            not isinstance(suffix, str)
            or not suffix.startswith(".")
            or len(suffix) < 2
            or "/" in suffix
            or "\\" in suffix
            or any(ord(character) < 32 or ord(character) == 127 for character in suffix)
        ):
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop {field}[{index}] is invalid for {platform}."
            )
        normalized = suffix.lower()
        if suffix != normalized or normalized in seen:
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop {field}[{index}] is invalid for {platform}."
            )
        seen.add(normalized)
        suffixes.append(normalized)
    return tuple(suffixes)


def _manifest_content_type_map(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be an object."
        )
    content_types: dict[str, str] = {}
    for suffix, content_type in value.items():
        if (
            not isinstance(suffix, str)
            or not _is_manifest_suffix(suffix)
            or suffix != suffix.lower()
        ):
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop {field} suffix is invalid: {suffix}."
            )
        if not isinstance(content_type, str) or not re.fullmatch(
            (
                r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/"
                r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*"
            ),
            content_type,
        ):
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop {field} content type is invalid for {suffix}."
            )
        content_types[suffix] = content_type
    return content_types


def _validate_served_artifact_content_types(
    config: Mapping[str, object],
    platform: str,
    served_artifact_content_types: Mapping[str, str],
) -> None:
    suffixes = config.get("servedArtifactSuffixes")
    if not isinstance(suffixes, list):
        return
    for suffix in suffixes:
        if suffix == ".blockmap":
            continue
        if not isinstance(suffix, str) or suffix not in served_artifact_content_types:
            raise OpenWorkHubDesktopUpdateManifestError(
                f"Open Work Hub desktop servedArtifactContentTypes is missing {suffix} for {platform}."
            )


def _is_manifest_suffix(value: str) -> bool:
    return (
        value.startswith(".")
        and len(value) >= 2
        and "/" not in value
        and "\\" not in value
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _assert_manifest_file_name(value: str, field: str, *, platform: str) -> None:
    if (
        "/" in value
        or "\\" in value
        or value in {"", ".", ".."}
        or value.startswith(".")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"Open Work Hub desktop {field} must be a safe file name for {platform}."
        )


def open_work_hub_desktop_update_platforms() -> tuple[str, ...]:
    return open_work_hub_desktop_update_manifest_projection().platforms


def open_work_hub_desktop_update_platform_config(platform: str) -> DesktopUpdatePlatformManifest:
    return open_work_hub_desktop_update_manifest_projection().platform_config(platform)


def open_work_hub_desktop_update_metadata_files() -> dict[str, str]:
    return open_work_hub_desktop_update_manifest_projection().metadata_files


def open_work_hub_desktop_update_artifact_suffixes() -> dict[str, frozenset[str]]:
    return open_work_hub_desktop_update_manifest_projection().artifact_suffixes


def open_work_hub_desktop_update_attachment_suffixes() -> dict[str, frozenset[str]]:
    return open_work_hub_desktop_update_manifest_projection().attachment_suffixes


def open_work_hub_desktop_update_content_types() -> dict[str, str]:
    return dict(open_work_hub_desktop_update_manifest_projection().served_artifact_content_types)


def open_work_hub_desktop_update_feed_path_prefix() -> str:
    return open_work_hub_desktop_update_manifest_projection().feed_path_prefix


def open_work_hub_desktop_update_base_url_env_name() -> str:
    return open_work_hub_desktop_update_manifest_projection().update_base_url_env


def open_work_hub_desktop_trusted_update_origins_env_name() -> str:
    return open_work_hub_desktop_update_manifest_projection().trusted_update_origins_env


def open_work_hub_desktop_update_default_dir(platform: str) -> str:
    default_dir = open_work_hub_desktop_update_platform_config(platform).default_dir
    return str(WORKSPACE_ROOT / default_dir)


def open_work_hub_desktop_update_dir_env_name(platform: str) -> str:
    return open_work_hub_desktop_update_platform_config(platform).update_dir_env


def open_work_hub_desktop_update_dir_values(
    env: Mapping[str, str | None] | None = None,
) -> dict[str, str]:
    env_values = env or {}
    return {
        platform: _open_work_hub_desktop_update_dir_value(platform, env_values)
        for platform in open_work_hub_desktop_update_platforms()
    }


def _open_work_hub_desktop_update_dir_value(
    platform: str,
    env: Mapping[str, str | None],
) -> str:
    env_name = open_work_hub_desktop_update_dir_env_name(platform)
    configured = env.get(env_name)
    if configured is None:
        return open_work_hub_desktop_update_default_dir(platform)
    return _workspace_update_dir(str(configured), env_name)


def _workspace_update_dir(value: str, env_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise OpenWorkHubDesktopUpdateManifestError(f"{env_name} must not be empty.")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"{env_name} contains an unsafe path character."
        )

    path = Path(normalized).expanduser()
    if path.is_absolute():
        return str(path)

    parts = re.split(r"[\\/]+", normalized)
    if normalized.startswith("~") or any(part in {"", ".", ".."} for part in parts):
        raise OpenWorkHubDesktopUpdateManifestError(
            f"{env_name} must be an absolute path or a clean relative path."
        )
    return str(WORKSPACE_ROOT / normalized)


def open_work_hub_desktop_installer_url_env_name(platform: str) -> str:
    return open_work_hub_desktop_update_platform_config(platform).installer_url_env


def open_work_hub_desktop_installer_stable_copy(platform: str) -> str:
    return open_work_hub_desktop_update_platform_config(platform).installer_stable_copy
