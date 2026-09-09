from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect

from open_work_hub_api.app import create_app
from open_work_hub_api.core.settings import DEFAULT_FRONTEND_DIST_DIR, get_settings


def test_empty_frontend_dist_dir_uses_default(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_API_FRONTEND_DIST_DIR", "")
    get_settings.cache_clear()
    try:
        assert get_settings().frontend_dist_dir == DEFAULT_FRONTEND_DIST_DIR
    finally:
        get_settings.cache_clear()


def test_frontend_serving_returns_static_asset_and_spa_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    frontend_dir = tmp_path / "web"
    assets_dir = frontend_dir / "assets"
    assets_dir.mkdir(parents=True)
    (frontend_dir / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (frontend_dir / "recording-sync-sw.js").write_text("// sw", encoding="utf-8")
    (assets_dir / "app.js").write_text("console.log('ok');", encoding="utf-8")

    monkeypatch.setenv("OPEN_WORK_HUB_API_SERVE_FRONTEND", "1")
    monkeypatch.setenv("OPEN_WORK_HUB_API_FRONTEND_DIST_DIR", str(frontend_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        root_response = client.get("/")
        root_head_response = client.head("/")
        asset_response = client.get("/assets/app.js")
        worker_response = client.get("/recording-sync-sw.js")
        route_response = client.get("/apps/meeting/meetings/example")
    finally:
        get_settings.cache_clear()

    assert root_response.status_code == 200
    assert '<div id="root"></div>' in root_response.text
    assert root_response.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    assert root_head_response.status_code == 200
    assert root_head_response.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    assert asset_response.status_code == 200
    assert "console.log('ok');" in asset_response.text
    assert asset_response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert worker_response.status_code == 200
    assert worker_response.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    assert route_response.status_code == 200
    assert '<div id="root"></div>' in route_response.text
    assert route_response.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"


def test_frontend_serving_does_not_fallback_missing_static_assets(
    monkeypatch,
    tmp_path,
) -> None:
    frontend_dir = tmp_path / "web"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text('<div id="root"></div>', encoding="utf-8")

    monkeypatch.setenv("OPEN_WORK_HUB_API_SERVE_FRONTEND", "1")
    monkeypatch.setenv("OPEN_WORK_HUB_API_FRONTEND_DIST_DIR", str(frontend_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        asset_response = client.get("/assets/PMSView-old.js")
        icon_response = client.get("/missing-icon.png")
    finally:
        get_settings.cache_clear()

    assert asset_response.status_code == 404
    assert asset_response.headers["cache-control"] == "no-store"
    assert '<div id="root"></div>' not in asset_response.text
    assert icon_response.status_code == 404
    assert '<div id="root"></div>' not in icon_response.text


def test_frontend_build_guard_rejects_stale_browser_requests_before_routing(
    monkeypatch,
    tmp_path,
) -> None:
    frontend_dir = tmp_path / "web"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (frontend_dir / ".open-work-hub-build-id").write_text("build-current\n", encoding="utf-8")

    monkeypatch.setenv("OPEN_WORK_HUB_API_SERVE_FRONTEND", "1")
    monkeypatch.setenv("OPEN_WORK_HUB_API_FRONTEND_DIST_DIR", str(frontend_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        stale_response = client.get(
            "/api/not-a-real-route",
            headers={
                "X-Open-Work-Hub-Web-Build": "build-old",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Dest": "empty",
            },
        )
        missing_browser_response = client.get(
            "/api/not-a-real-route",
            headers={
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Dest": "empty",
            },
        )
        current_response = client.get(
            "/api/not-a-real-route",
            headers={
                "X-Open-Work-Hub-Web-Build": "build-current",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Dest": "empty",
            },
        )
        non_browser_response = client.get("/api/not-a-real-route")
        navigation_response = client.get(
            "/api/not-a-real-route",
            headers={
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
            },
        )
    finally:
        get_settings.cache_clear()

    for response in (stale_response, missing_browser_response):
        assert response.status_code == 409
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-open-work-hub-reload-required"] == "1"
        assert response.headers["x-open-work-hub-web-build"] == "build-current"
        assert response.json()["code"] == "CLIENT_BUILD_MISMATCH"
    assert current_response.status_code == 404
    assert non_browser_response.status_code == 404
    assert navigation_response.status_code == 404


def test_frontend_build_guard_rejects_stale_websockets(monkeypatch, tmp_path) -> None:
    frontend_dir = tmp_path / "web"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (frontend_dir / ".open-work-hub-build-id").write_text("build-current\n", encoding="utf-8")

    monkeypatch.setenv("OPEN_WORK_HUB_API_SERVE_FRONTEND", "1")
    monkeypatch.setenv("OPEN_WORK_HUB_API_FRONTEND_DIST_DIR", str(frontend_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        with client.websocket_connect(
            "/api/not-a-real-websocket?__open_work_hub_build=build-old"
        ) as stale_websocket:
            with pytest.raises(WebSocketDisconnect) as stale_exc:
                stale_websocket.receive_text()
        with pytest.raises(WebSocketDisconnect) as current_exc:
            with client.websocket_connect(
                "/api/not-a-real-websocket?__open_work_hub_build=build-current"
            ):
                pass
    finally:
        get_settings.cache_clear()

    assert stale_exc.value.code == 4409
    assert current_exc.value.code == 1008


def test_frontend_serving_does_not_swallow_reserved_api_paths(
    monkeypatch,
    tmp_path,
) -> None:
    frontend_dir = tmp_path / "web"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text('<div id="root"></div>', encoding="utf-8")

    monkeypatch.setenv("OPEN_WORK_HUB_API_SERVE_FRONTEND", "1")
    monkeypatch.setenv("OPEN_WORK_HUB_API_FRONTEND_DIST_DIR", str(frontend_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        response = client.get("/api/not-a-real-route")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 404
    assert '<div id="root"></div>' not in response.text


def test_frontend_serving_closes_unknown_websocket_paths(
    monkeypatch,
    tmp_path,
) -> None:
    frontend_dir = tmp_path / "web"
    frontend_dir.mkdir()
    (frontend_dir / "index.html").write_text('<div id="root"></div>', encoding="utf-8")

    monkeypatch.setenv("OPEN_WORK_HUB_API_SERVE_FRONTEND", "1")
    monkeypatch.setenv("OPEN_WORK_HUB_API_FRONTEND_DIST_DIR", str(frontend_dir))
    get_settings.cache_clear()
    try:
        client = TestClient(create_app(initialize_runtime=False))
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/not-a-real-websocket"):
                pass
    finally:
        get_settings.cache_clear()

    assert exc_info.value.code == 1008
