from fastapi.testclient import TestClient

from ai_do_api.app import create_app
from ai_do_api.core.settings import get_settings


def test_ai_do_desktop_update_feed_is_public_static_path(monkeypatch, tmp_path) -> None:
    update_dir = tmp_path / "updates"
    update_dir.mkdir()
    (update_dir / "latest.yml").write_text(
        "version: 0.1.2\npath: AI-DO Desktop Setup 0.1.2.exe\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("AI_DO_DESKTOP_UPDATE_WIN_DIR", str(update_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        response = client.get("/api/v1/ai-do-desktop/updates/win/latest.yml")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert "version: 0.1.2" in response.text


def test_ai_do_desktop_linux_deb_download_uses_attachment_headers(monkeypatch, tmp_path) -> None:
    linux_dir = tmp_path / "linux"
    linux_dir.mkdir()
    (linux_dir / "AI-DO-Desktop-latest.deb").write_bytes(b"!<arch>\n")

    monkeypatch.setenv("AI_DO_DESKTOP_UPDATE_LINUX_DIR", str(linux_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        response = client.get("/api/v1/ai-do-desktop/updates/linux/AI-DO-Desktop-latest.deb")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.debian.binary-package"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "AI-DO-Desktop-latest.deb" in response.headers["content-disposition"]


def test_ai_do_desktop_update_feed_rejects_non_artifact_files(monkeypatch, tmp_path) -> None:
    update_dir = tmp_path / "updates"
    nested_dir = update_dir / "nested"
    nested_dir.mkdir(parents=True)
    (update_dir / "notes.txt").write_text("internal note", encoding="utf-8")
    (nested_dir / "latest.yml").write_text("version: 0.1.2\n", encoding="utf-8")

    monkeypatch.setenv("AI_DO_DESKTOP_UPDATE_WIN_DIR", str(update_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        notes_response = client.get("/api/v1/ai-do-desktop/updates/win/notes.txt")
        nested_response = client.get("/api/v1/ai-do-desktop/updates/win/nested/latest.yml")
    finally:
        get_settings.cache_clear()

    assert notes_response.status_code == 404
    assert nested_response.status_code == 404
