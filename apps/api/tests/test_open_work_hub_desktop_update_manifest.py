import copy

import pytest

from open_work_hub_api.open_work_hub_desktop_update_manifest import (
    OpenWorkHubDesktopUpdateManifestError,
    open_work_hub_desktop_update_dir_values,
    validate_open_work_hub_desktop_update_manifest,
)


def test_open_work_hub_desktop_update_manifest_rejects_unsafe_paths_and_files() -> None:
    manifest = _manifest_fixture()
    manifest["feedPathPrefix"] = "/api/v1/open-work-hub-desktop/updates/"

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="absolute path prefix"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["updateBaseUrlEnv"] = "OPEN_WORK_HUB_UPDATE_BASE_URL"

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="updateBaseUrlEnv is invalid"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["defaultDir"] = "../updates"

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="relative POSIX path"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["stableCopies"][0]["to"] = "../installer.exe"

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="safe file name"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["installerUrlEnv"] = "OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_WIN"

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="installerUrlEnv is invalid"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["servedArtifactSuffixes"] = [".exe", "blockmap"]

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="servedArtifactSuffixes"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["servedArtifactContentTypes"][".exe"] = "not-a-content-type"

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="servedArtifactContentTypes"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    del manifest["servedArtifactContentTypes"][".exe"]

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="servedArtifactContentTypes is missing"):
        validate_open_work_hub_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["installerStableCopy"] = "missing.exe"

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="installerStableCopy must reference"):
        validate_open_work_hub_desktop_update_manifest(manifest)


def test_open_work_hub_desktop_update_dir_values_reject_unsafe_env_paths() -> None:
    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="must not be empty"):
        open_work_hub_desktop_update_dir_values({"OPEN_WORK_HUB_DESKTOP_UPDATE_WIN_DIR": "   "})

    with pytest.raises(OpenWorkHubDesktopUpdateManifestError, match="clean relative path"):
        open_work_hub_desktop_update_dir_values({"OPEN_WORK_HUB_DESKTOP_UPDATE_WIN_DIR": "../outside"})


def _manifest_fixture() -> dict[str, object]:
    return copy.deepcopy(
        {
            "feedPathPrefix": "/api/v1/open-work-hub-desktop/updates",
            "updateBaseUrlEnv": "OPEN_WORK_HUB_DESKTOP_UPDATE_BASE_URL",
            "trustedUpdateOriginsEnv": "OPEN_WORK_HUB_DESKTOP_TRUSTED_UPDATE_ORIGINS",
            "servedArtifactContentTypes": {
                ".blockmap": "application/octet-stream",
                ".exe": "application/octet-stream",
            },
            "platformOrder": ["win"],
            "platforms": {
                "win": {
                    "packageName": "open-work-hub-desktop-win",
                    "installerUrlEnv": "VITE_OPEN_WORK_HUB_DESKTOP_INSTALLER_URL_WIN",
                    "installerStableCopy": "Open Work Hub-Desktop-Setup-latest.exe",
                    "updateDirEnv": "OPEN_WORK_HUB_DESKTOP_UPDATE_WIN_DIR",
                    "defaultDir": ".open-work-hub-desktop-updates/win",
                    "updateFile": "latest.yml",
                    "servedArtifactSuffixes": [".exe", ".blockmap"],
                    "packagedArtifacts": [
                        {"template": "Open Work Hub Desktop Setup ${version}.exe"},
                    ],
                    "stableCopies": [
                        {
                            "template": "Open Work Hub Desktop Setup ${version}.exe",
                            "to": "Open Work Hub-Desktop-Setup-latest.exe",
                        },
                    ],
                },
            },
        }
    )
