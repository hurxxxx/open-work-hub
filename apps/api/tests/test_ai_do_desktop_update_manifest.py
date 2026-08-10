import copy

import pytest

from ai_do_api.ai_do_desktop_update_manifest import (
    AiDoDesktopUpdateManifestError,
    ai_do_desktop_update_dir_values,
    validate_ai_do_desktop_update_manifest,
)


def test_ai_do_desktop_update_manifest_rejects_unsafe_paths_and_files() -> None:
    manifest = _manifest_fixture()
    manifest["feedPathPrefix"] = "/api/v1/ai-do-desktop/updates/"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="absolute path prefix"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["updateBaseUrlEnv"] = "AI_DO_UPDATE_BASE_URL"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="updateBaseUrlEnv is invalid"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["defaultDir"] = "../updates"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="relative POSIX path"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["stableCopies"][0]["to"] = "../installer.exe"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="safe file name"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["installerUrlEnv"] = "AI_DO_DESKTOP_INSTALLER_URL_WIN"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="installerUrlEnv is invalid"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["servedArtifactSuffixes"] = [".exe", "blockmap"]

    with pytest.raises(AiDoDesktopUpdateManifestError, match="servedArtifactSuffixes"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["servedArtifactContentTypes"][".exe"] = "not-a-content-type"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="servedArtifactContentTypes"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    del manifest["servedArtifactContentTypes"][".exe"]

    with pytest.raises(AiDoDesktopUpdateManifestError, match="servedArtifactContentTypes is missing"):
        validate_ai_do_desktop_update_manifest(manifest)

    manifest = _manifest_fixture()
    manifest["platforms"]["win"]["installerStableCopy"] = "missing.exe"

    with pytest.raises(AiDoDesktopUpdateManifestError, match="installerStableCopy must reference"):
        validate_ai_do_desktop_update_manifest(manifest)


def test_ai_do_desktop_update_dir_values_reject_unsafe_env_paths() -> None:
    with pytest.raises(AiDoDesktopUpdateManifestError, match="must not be empty"):
        ai_do_desktop_update_dir_values({"AI_DO_DESKTOP_UPDATE_WIN_DIR": "   "})

    with pytest.raises(AiDoDesktopUpdateManifestError, match="clean relative path"):
        ai_do_desktop_update_dir_values({"AI_DO_DESKTOP_UPDATE_WIN_DIR": "../outside"})


def _manifest_fixture() -> dict[str, object]:
    return copy.deepcopy(
        {
            "feedPathPrefix": "/api/v1/ai-do-desktop/updates",
            "updateBaseUrlEnv": "AI_DO_DESKTOP_UPDATE_BASE_URL",
            "trustedUpdateOriginsEnv": "AI_DO_DESKTOP_TRUSTED_UPDATE_ORIGINS",
            "servedArtifactContentTypes": {
                ".blockmap": "application/octet-stream",
                ".exe": "application/octet-stream",
            },
            "platformOrder": ["win"],
            "platforms": {
                "win": {
                    "packageName": "ai-do-desktop-win",
                    "installerUrlEnv": "VITE_AI_DO_DESKTOP_INSTALLER_URL_WIN",
                    "installerStableCopy": "AI-DO-Desktop-Setup-latest.exe",
                    "updateDirEnv": "AI_DO_DESKTOP_UPDATE_WIN_DIR",
                    "defaultDir": ".ai-do-desktop-updates/win",
                    "updateFile": "latest.yml",
                    "servedArtifactSuffixes": [".exe", ".blockmap"],
                    "packagedArtifacts": [
                        {"template": "AI-DO Desktop Setup ${version}.exe"},
                    ],
                    "stableCopies": [
                        {
                            "template": "AI-DO Desktop Setup ${version}.exe",
                            "to": "AI-DO-Desktop-Setup-latest.exe",
                        },
                    ],
                },
            },
        }
    )
