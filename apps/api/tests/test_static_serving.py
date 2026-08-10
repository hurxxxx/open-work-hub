from __future__ import annotations

from types import SimpleNamespace

from fastapi.responses import Response

from ai_do_api.static_serving import (
    STATIC_WEBSOCKET_POLICY_VIOLATION_CLOSE_CODE,
    StaticServingPolicy,
    apply_static_response_headers,
    is_file_like_static_path,
    normalize_static_request_path,
)


def test_static_serving_policy_blocks_reserved_paths_and_descendants() -> None:
    policy = StaticServingPolicy(reserved_paths=frozenset({"/api", "/healthz"}))

    assert policy.allows_path("assets/app.js") is True
    assert policy.allows_path("/api") is False
    assert policy.allows_path("api/v1/users") is False
    assert policy.allows_path("/healthz") is False
    assert policy.allows_path("/healthz-extra") is True


def test_static_serving_policy_fallbacks_only_on_404() -> None:
    policy = StaticServingPolicy(not_found_fallback_path="index.html")

    assert policy.fallback_path(404) == "index.html"
    assert policy.fallback_path(403) is None
    assert policy.fallback_path(500) is None


def test_static_serving_policy_can_exclude_static_assets_from_fallback() -> None:
    policy = StaticServingPolicy(
        not_found_fallback_path="index.html",
        not_found_fallback_excluded_prefixes=frozenset({"/assets"}),
        not_found_fallback_excludes_file_paths=True,
    )

    assert policy.fallback_path(404, "/w/hq/pms") == "index.html"
    assert policy.fallback_path(404, "/assets/missing.js") is None
    assert policy.fallback_path(404, "/favicon.ico") is None


def test_static_serving_policy_treats_directory_root_as_spa_route() -> None:
    policy = StaticServingPolicy(
        not_found_fallback_path="index.html",
        not_found_fallback_excludes_file_paths=True,
    )

    assert policy.fallback_path(404, ".") == "index.html"
    assert policy.fallback_path(404, "/.") == "index.html"


def test_static_serving_policy_builds_websocket_close_message() -> None:
    policy = StaticServingPolicy(
        websocket_close_code=STATIC_WEBSOCKET_POLICY_VIOLATION_CLOSE_CODE,
    )

    assert policy.websocket_close_message() == {
        "type": "websocket.close",
        "code": 1008,
    }
    assert StaticServingPolicy().websocket_close_message() is None


def test_apply_static_response_headers_only_mutates_successful_responses() -> None:
    headers = SimpleNamespace(
        content_disposition='attachment; filename="AI-DO.deb"',
        content_type="application/vnd.debian.binary-package",
    )
    response = Response(status_code=200)
    missing = Response(status_code=404)

    apply_static_response_headers(response, headers)
    apply_static_response_headers(missing, headers)

    assert response.headers["content-disposition"] == 'attachment; filename="AI-DO.deb"'
    assert response.headers["content-type"] == "application/vnd.debian.binary-package"
    assert "content-disposition" not in missing.headers


def test_normalize_static_request_path() -> None:
    assert normalize_static_request_path(".") == "/"
    assert normalize_static_request_path("/.") == "/"
    assert normalize_static_request_path("") == "/"
    assert normalize_static_request_path("api/v1") == "/api/v1"
    assert normalize_static_request_path("/api/v1") == "/api/v1"


def test_is_file_like_static_path() -> None:
    assert is_file_like_static_path("/assets/app.js") is True
    assert is_file_like_static_path("favicon.ico") is True
    assert is_file_like_static_path("/w/hq/pms") is False
