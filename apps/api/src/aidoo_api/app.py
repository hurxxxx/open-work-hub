import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response as FastAPIResponse
from opentelemetry.trace import SpanKind
from starlette.exceptions import HTTPException as StarletteHTTPException

from aidoo_api.api_registry import register_api_routers
from aidoo_api.core.db import get_session_factory, init_db
from aidoo_api.core.i18n import (
    ERROR_CODE_HEADER,
    LocalizedApiMessage,
    select_locale,
    translate_message,
)
from aidoo_api.core.llm import (
    check_all_pools_health,
    check_effective_llm_readiness,
)
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import ensure_bucket
from aidoo_api.core.telemetry import (
    bootstrap_telemetry,
    current_trace_id,
    extract_trace_context,
    get_tracer,
)
from aidoo_api.domains.ai.registry import initialize_ai_capability_registry
from aidoo_api.domains.ai.runtime.registry_validation import RuntimeRegistryValidationError
from aidoo_api.domains.docs.collab import DocsCollabHub
from aidoo_api.domains.rag.runtime import close_rag_runtime_resources, get_rag_runtime_health
from aidoo_api.domains.whiteboard.collab import WhiteboardCollabHub
from aidoo_api.openapi_contract import stable_operation_id


logger = logging.getLogger(__name__)
LOCALIZED_VALIDATION_ERROR_TYPES = frozenset({"ai.unknown_workspace_app"})


def _request_locale(request: Request) -> str:
    return select_locale(
        explicit_locale=request.headers.get("x-aidoo-locale"),
        accept_language=request.headers.get("accept-language"),
    )


async def runtime_registry_validation_exception_handler(
    request: Request,
    exc: RuntimeRegistryValidationError,
) -> JSONResponse:
    del request
    return JSONResponse(status_code=422, content={"detail": str(exc)})


async def localized_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    if not isinstance(exc.detail, LocalizedApiMessage):
        return await http_exception_handler(request, exc)

    locale = _request_locale(request)
    body: dict[str, object] = {
        "detail": translate_message(exc.detail, locale),
        "code": exc.detail.code,
    }
    if exc.detail.params:
        body["params"] = exc.detail.params
    return JSONResponse(
        status_code=exc.status_code,
        content=body,
        headers=exc.headers,
    )


async def localized_request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    for error in exc.errors():
        error_type = error.get("type")
        if not isinstance(error_type, str) or error_type not in LOCALIZED_VALIDATION_ERROR_TYPES:
            continue
        params = error.get("ctx") if isinstance(error.get("ctx"), dict) else {}
        message = LocalizedApiMessage(code=error_type, params=dict(params))
        body: dict[str, object] = {
            "detail": translate_message(message, _request_locale(request)),
            "code": error_type,
            "params": message.params,
            "validation": [
                {
                    "loc": list(error.get("loc", ())),
                    "type": error_type,
                }
            ],
        }
        return JSONResponse(
            status_code=422,
            content=body,
            headers={ERROR_CODE_HEADER: error_type},
        )

    return await request_validation_exception_handler(request, exc)


def create_app(*, initialize_runtime: bool = True) -> FastAPI:
    settings = get_settings()
    telemetry_enabled = bootstrap_telemetry(
        service_name="aidoo-api",
        enabled=settings.otel_enabled,
        enable_console_exporter=settings.otel_console_exporter,
        enable_otlp_exporter=settings.otel_otlp_exporter_enabled,
        metrics_export_interval_ms=settings.otel_metrics_export_interval_ms,
    )
    telemetry_tracer = get_tracer("aidoo_api.http")
    if initialize_runtime:
        initialize_ai_capability_registry()
        init_db()
        ensure_bucket()
        Path(settings.recording_spool_dir).expanduser().mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not initialize_runtime:
            yield
            return
        app.state.docs_collab = DocsCollabHub()
        await app.state.docs_collab.startup()
        app.state.whiteboard_collab = WhiteboardCollabHub()
        await app.state.whiteboard_collab.startup()
        if settings.llm_healthcheck_on_startup:
            dual = check_all_pools_health(settings)
            with get_session_factory()() as session:
                effective = check_effective_llm_readiness(session, settings)
            app.state.llm_health = dual.public_dict()
            app.state.llm_effective = effective.public_dict()
            if settings.llm_required and not effective.ready:
                logger.warning(
                    "LLM effective readiness check failed: %s", effective.public_dict()
                )
        yield
        await app.state.whiteboard_collab.shutdown()
        await app.state.docs_collab.shutdown()
        close_rag_runtime_resources()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        generate_unique_id_function=stable_operation_id,
    )
    app.state.telemetry_enabled = telemetry_enabled
    app.add_exception_handler(
        RuntimeRegistryValidationError,
        runtime_registry_validation_exception_handler,
    )
    app.add_exception_handler(StarletteHTTPException, localized_http_exception_handler)
    app.add_exception_handler(
        RequestValidationError,
        localized_request_validation_exception_handler,
    )

    @app.middleware("http")
    async def add_instance_headers(request, call_next) -> FastAPIResponse:
        response = await call_next(request)
        response.headers["X-Doowon-Instance-Id"] = settings.instance_id
        trace_id = current_trace_id()
        if trace_id is not None:
            response.headers["X-Doowon-Trace-Id"] = trace_id
        return response

    @app.middleware("http")
    async def telemetry_middleware(request, call_next) -> FastAPIResponse:
        if not app.state.telemetry_enabled:
            return await call_next(request)

        span_name = f"HTTP {request.method}"
        with telemetry_tracer.start_as_current_span(
            span_name,
            context=extract_trace_context(request.headers),
            kind=SpanKind.SERVER,
            attributes={
                "http.request.method": request.method,
                "url.path": request.url.path,
                "url.scheme": request.url.scheme,
            },
        ) as span:
            response = await call_next(request)
            route = request.scope.get("route")
            route_path = getattr(route, "path", None)
            if isinstance(route_path, str) and route_path:
                span.set_attribute("http.route", route_path)
            span.set_attribute("http.response.status_code", response.status_code)
            return response

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "environment": settings.environment,
            "instance_id": settings.instance_id,
        }

    @app.get("/readyz", tags=["system"])
    def readyz(response: Response) -> dict[str, object]:
        dual = check_all_pools_health(settings)
        with get_session_factory()() as session:
            effective = check_effective_llm_readiness(session, settings)
        ready = effective.ready or not settings.llm_required
        rag = get_rag_runtime_health()
        if rag.get("enabled") and not rag.get("ready", False):
            ready = False
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "ok" if ready else "degraded",
            "environment": settings.environment,
            "instance_id": settings.instance_id,
            "llm": dual.public_dict(),
            "llm_effective": effective.public_dict(),
            "rag": rag,
        }

    register_api_routers(app, settings)
    return app
