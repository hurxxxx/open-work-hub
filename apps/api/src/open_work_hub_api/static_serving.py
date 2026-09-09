from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from fastapi.responses import Response

STATIC_WEBSOCKET_POLICY_VIOLATION_CLOSE_CODE = 1008
FRONTEND_HTML_CACHE_CONTROL = "no-cache, max-age=0, must-revalidate"
FRONTEND_IMMUTABLE_ASSET_CACHE_CONTROL = "public, max-age=31536000, immutable"


class StaticResponseHeaderValues(Protocol):
    content_disposition: str
    content_type: str


@dataclass(frozen=True)
class StaticServingPolicy:
    reserved_paths: frozenset[str] = frozenset()
    not_found_fallback_path: str | None = None
    not_found_fallback_excluded_prefixes: frozenset[str] = frozenset()
    not_found_fallback_excludes_file_paths: bool = False
    websocket_close_code: int | None = None

    def allows_path(self, path: str) -> bool:
        normalized = normalize_static_request_path(path)
        return not any(
            normalized == reserved or normalized.startswith(f"{reserved}/")
            for reserved in self.reserved_paths
        )

    def fallback_path(self, status_code: int, request_path: str | None = None) -> str | None:
        if status_code == 404:
            if request_path is not None and self.excludes_not_found_fallback(request_path):
                return None
            return self.not_found_fallback_path
        return None

    def excludes_not_found_fallback(self, path: str) -> bool:
        normalized = normalize_static_request_path(path)
        if any(
            normalized == prefix or normalized.startswith(f"{prefix}/")
            for prefix in self.not_found_fallback_excluded_prefixes
        ):
            return True
        return self.not_found_fallback_excludes_file_paths and is_file_like_static_path(normalized)

    def websocket_close_message(self) -> dict[str, int | str] | None:
        if self.websocket_close_code is None:
            return None
        return {
            "type": "websocket.close",
            "code": self.websocket_close_code,
        }


def normalize_static_request_path(path: str) -> str:
    if path in {"", ".", "/."}:
        return "/"
    return "/" + path.lstrip("/")


def is_file_like_static_path(path: str) -> bool:
    basename = normalize_static_request_path(path).rsplit("/", 1)[-1]
    return "." in basename


def is_successful_static_response(response: Response) -> bool:
    return response.status_code < 400


def apply_static_response_headers(
    response: Response,
    headers: StaticResponseHeaderValues | None,
) -> None:
    if not is_successful_static_response(response) or headers is None:
        return
    response.headers["Content-Disposition"] = headers.content_disposition
    response.headers["Content-Type"] = headers.content_type


def frontend_cache_control_for_path(path: str, *, spa_fallback: bool = False) -> str:
    if spa_fallback:
        return FRONTEND_HTML_CACHE_CONTROL

    normalized = normalize_static_request_path(path)
    if normalized in {"/", "/index.html"}:
        return FRONTEND_HTML_CACHE_CONTROL
    if normalized.startswith("/assets/"):
        return FRONTEND_IMMUTABLE_ASSET_CACHE_CONTROL
    return FRONTEND_HTML_CACHE_CONTROL


def apply_frontend_cache_control(
    response: Response,
    path: str,
    *,
    spa_fallback: bool = False,
) -> None:
    if not is_successful_static_response(response):
        return
    response.headers["Cache-Control"] = frontend_cache_control_for_path(
        path,
        spa_fallback=spa_fallback,
    )
