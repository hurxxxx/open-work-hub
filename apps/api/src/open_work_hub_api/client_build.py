from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send


CLIENT_BUILD_FILE_NAME = ".open-work-hub-build-id"
CLIENT_BUILD_HEADER = "X-Open-Work-Hub-Web-Build"
CLIENT_RELOAD_REQUIRED_HEADER = "X-Open-Work-Hub-Reload-Required"
CLIENT_BUILD_WEBSOCKET_QUERY_PARAM = "__open_work_hub_build"
CLIENT_BUILD_WEBSOCKET_CLOSE_CODE = 4409
CLIENT_BUILD_MISMATCH_CODE = "CLIENT_BUILD_MISMATCH"
_VALID_BUILD_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def read_frontend_build_id(frontend_dir: str | Path) -> str | None:
    build_file = Path(frontend_dir).expanduser().resolve() / CLIENT_BUILD_FILE_NAME
    if not build_file.is_file():
        return None
    build_id = build_file.read_text(encoding="utf-8").strip()
    if not _VALID_BUILD_ID.fullmatch(build_id):
        raise RuntimeError(f"Invalid frontend build id in {build_file}")
    return build_id


def _is_api_path(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _origin_matches_host(origin: str | None, host: str | None) -> bool:
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    return parsed.scheme in {"http", "https"} and parsed.netloc == host


def _is_same_origin_browser_request(headers: Headers) -> bool:
    fetch_site = headers.get("sec-fetch-site", "").lower()
    fetch_dest = headers.get("sec-fetch-dest", "").lower()
    fetch_mode = headers.get("sec-fetch-mode", "").lower()
    if fetch_site == "same-origin":
        return fetch_dest == "empty"
    return (
        fetch_dest in {"", "empty"}
        and fetch_mode != "navigate"
        and _origin_matches_host(headers.get("origin"), headers.get("host"))
    )


def _websocket_build_id(scope: Scope) -> str | None:
    query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
    values = query.get(CLIENT_BUILD_WEBSOCKET_QUERY_PARAM)
    if not values:
        return None
    return values[-1]


class ClientBuildGuardMiddleware:
    def __init__(self, app: ASGIApp, *, expected_build_id: str | None) -> None:
        self.app = app
        self.expected_build_id = expected_build_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        expected = self.expected_build_id
        scope_type = scope["type"]
        if (
            not expected
            or scope_type not in {"http", "websocket"}
            or not _is_api_path(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if scope_type == "http":
            if scope.get("method") == "OPTIONS":
                await self.app(scope, receive, send)
                return
            supplied = headers.get(CLIENT_BUILD_HEADER)
            should_reject = supplied != expected and (
                supplied is not None or _is_same_origin_browser_request(headers)
            )
            if not should_reject:
                await self.app(scope, receive, send)
                return
            response = JSONResponse(
                status_code=409,
                content={
                    "code": CLIENT_BUILD_MISMATCH_CODE,
                    "detail": "Client update required.",
                },
                headers={
                    "Cache-Control": "no-store",
                    CLIENT_RELOAD_REQUIRED_HEADER: "1",
                    CLIENT_BUILD_HEADER: expected,
                },
            )
            await response(scope, receive, send)
            return

        supplied = _websocket_build_id(scope)
        should_reject = supplied != expected and (
            supplied is not None
            or _origin_matches_host(headers.get("origin"), headers.get("host"))
        )
        if should_reject:
            accept_message: Message = {"type": "websocket.accept"}
            close_message: Message = {
                "type": "websocket.close",
                "code": CLIENT_BUILD_WEBSOCKET_CLOSE_CODE,
                "reason": CLIENT_BUILD_MISMATCH_CODE,
            }
            await send(accept_message)
            await send(close_message)
            return
        await self.app(scope, receive, send)
