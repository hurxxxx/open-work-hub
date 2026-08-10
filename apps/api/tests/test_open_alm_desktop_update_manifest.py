import copy

import pytest

from open_alm_api.open_alm_desktop_update_manifest import (
    AiDoDesktopUpdateManifestError,
    open_alm_desktop_update_dir_values,
    validate_open_alm_desktop_update_manifest,
)


def test_open_alm_desktop_update_manifest_rejects_unsafe_paths_and_files() -> None:
    manifest = _manifest_fixture()
    manifest["feedPathPrefix"] = "/api/v1/open-alm-desktop/updates/"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="absolute path prefix"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["updateBaseUrlEnv"] = "OPEN_ALM_UPDATE_BASE_URL"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="updateBaseUrlEnv is invalid"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["defaultDir"] = "../updates"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="relative POSIX path"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["stableCopies"][0]["to"] = "../installer.exe"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="safe file name"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["installerUrlEnv"] = "OPEN_ALM_DESKTOP_INSTALLER_URL_WIN"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="installerUrlEnv is invalid"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["servedArtifactSuffixes"] = [".exe", "blockmap"]

    with pytest.raises(AiDoDesktopUpdateManifestError, match="servedArtifactSuffixes"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["servedArtifactContentTypes"][".exe"] = "not-a-content-type"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="servedArtifactContentTypes"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    del manifest["servedArtifactContentTypes"][".exe"]

    with pytest.raises(AiDoDesktopUpdateManifestError, match="servedArtifactContentTypes is missing"):
        validate_open_alm_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["installerStableCopy"] = "missing.exe"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="installerStableCopy must reference"):
        validate_open_alm_desktop_update_manifest(manifest)


def test_open_alm_desktop_update_dir_values_reject_unsafe_env_paths() -> None:
    with pytest.raises(AiDoDesktopUpdateManifestError, match="must not be empty"):
        open_alm_desktop_update_dir_values({"OPEN_ALM_DESKTOP_UPDATE_WIN_DIR": "   "})

    with pytest.raises(AiDoDesktopUpdateManifestError, match="clean relative path"):
        open_alm_desktop_update_dir_values({"OPEN_ALM_DESKTOP_UPDATE_WIN_DIR": "../outside"})


def _manifest_fixture() -> dict[str, object]:
    return copy.deepcopy(
        {
            "feedPathPrefix": "/api/v1/open-alm-desktop/updates",
            "updateBaseUrlEnv": "OPEN_ALM_DESKTOP_UPDATE_BASE_URL",
            "trustedUpdateOriginsEnv": "OPEN_ALM_DESKTOP_TRUSTED_UPDATE_ORIGINS",
            "servedArtifactContentTypes": {
                ".blockmap": "application/octet-stream",
                ".exe": "application/octet-stream",
            },
            "platformOrder": ["win"],
            "platforms": {
                "win": {
                    "packageName": "open-alm-desktop-win",
                    "installerUrlEnv": "VITE_OPEN_ALM_DESKTOP_INSTALLER_URL_WIN",
                    "installerStableCopy": "Open ALM-Desktop-Setup-latest.exe",
                    "updateDirEnv": "OPEN_ALM_DESKTOP_UPDATE_WIN_DIR",
                    "defaultDir": ".open-alm-desktop-updates/win",
                    "updateFile": "latest.yml",
                    "servedArtifactSuffixes": [".exe", ".blockmap"],
                    "packagedArtifacts": [
                        {"template": "Open ALM Desktop Setup ${version}.exe"},
                    ],
                    "stableCopies": [
                        {
                            "template": "Open ALM Desktop Setup ${version}.exe",
                            "to": "Open ALM-Desktop-Setup-latest.exe",
                        },
                    ],
                },
            },
        }
    )
