from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from open_work_hub_api.core.settings import Settings
from open_work_hub_api.static_serving import (
    STATIC_WEBSOCKET_POLICY_VIOLATION_CLOSE_CODE,
    StaticServingPolicy,
    apply_frontend_cache_control,
    normalize_static_request_path,
)


RESERVED_FRONTEND_PATHS = frozenset(
    {
        "/api",
        "/docs",
        "/redoc",
        "/healthz",
        "/readyz",
        "/openapi.json",
    }
)


class FrontendStaticFiles(StaticFiles):
    def __init__(self, *args: Any, index_path: Path, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.index_path = index_path
        self.policy = StaticServingPolicy(
            reserved_paths=RESERVED_FRONTEND_PATHS,
            not_found_fallback_path="index.html",
            not_found_fallback_excluded_prefixes=frozenset({"/assets"}),
            not_found_fallback_excludes_file_paths=True,
            websocket_close_code=STATIC_WEBSOCKET_POLICY_VIOLATION_CLOSE_CODE,
        )

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Any,
        send: Any,
    ) -> None:
        if scope["type"] == "websocket":
            close_message = self.policy.websocket_close_message()
            if close_message is not None:
                await send(close_message)
            return
        await super().__call__(scope, receive, send)

    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        if not self.policy.allows_path(path):
            raise StarletteHTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
            apply_frontend_cache_control(response, path)
            return response
        except StarletteHTTPException as exc:
            fallback_path = self.policy.fallback_path(exc.status_code, path)
            if fallback_path is None:
                normalized = normalize_static_request_path(path)
                if exc.status_code == 404 and normalized.startswith("/assets/"):
                    raise StarletteHTTPException(
                        status_code=exc.status_code,
                        detail=exc.detail,
                        headers={**(exc.headers or {}), "Cache-Control": "no-store"},
                    ) from exc
                raise
            response = await super().get_response(fallback_path, scope)
            apply_frontend_cache_control(response, path, spa_fallback=True)
            return response


def mount_frontend(app: FastAPI, settings: Settings) -> None:
    if not settings.serve_frontend:
        return

    frontend_dir = Path(settings.frontend_dist_dir).expanduser().resolve()
    index_path = frontend_dir / "index.html"
    if not index_path.is_file():
        raise RuntimeError(f"Frontend index.html not found: {index_path}")

    app.mount(
        "/",
        FrontendStaticFiles(directory=frontend_dir, index_path=index_path),
        name="frontend",
    )
