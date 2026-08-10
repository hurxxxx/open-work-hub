import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response as FastAPIResponse
from opentelemetry.trace import SpanKind
from starlette.exceptions import HTTPException as StarletteHTTPException

from open_work_hub_api.api_registry import register_api_routers
from open_work_hub_api.client_build import ClientBuildGuardMiddleware, read_frontend_build_id
from open_work_hub_api.core.db import get_session_factory, init_db
from open_work_hub_api.core.i18n import (
    ERROR_CODE_HEADER,
    LocalizedApiMessage,
    select_locale,
    translate_message,
)
from open_work_hub_api.core.logging_security import install_sensitive_http_logging_guard
from open_work_hub_api.core.request_validation_errors import build_request_validation_error_body
from open_work_hub_api.core.runtime_diagnostics import (
    install_stack_dump_signal,
    start_event_loop_lag_watchdog,
)
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import ensure_bucket
from open_work_hub_api.core.telemetry import (
    bootstrap_telemetry,
    current_trace_id,
    extract_trace_context,
    get_tracer,
)
from open_work_hub_api.open_work_hub_desktop_updates import (
    mount_open_work_hub_desktop_update_feeds,
    prepare_open_work_hub_desktop_update_dirs,
)
from open_work_hub_api.frontend import mount_frontend
from open_work_hub_api.domains.ai.runtime.registry_validation import RuntimeRegistryValidationError
from open_work_hub_api.domains.ai.runtime_status import inspect_registered_llm_runtime
from open_work_hub_api.domains.ai.privacy_filter import (
    check_privacy_filter_health,
    prepare_privacy_filter,
)
from open_work_hub_api.domains.rag.runtime import (
    attach_rag_queue_health,
    close_rag_runtime_resources,
    get_rag_runtime_health,
    preload_rag_runtime,
)
from open_work_hub_api.external_runtime import ApiExternalRuntime, ProductionApiExternalRuntime
from open_work_hub_api.openapi_contract import stable_operation_id
from open_work_hub_api.platform_extensions import initialize_platform_extensions
from open_work_hub_api.version import RUNTIME_REVISION, VERSION as APP_VERSION


logger = logging.getLogger(__name__)


def _request_locale(request: Request) -> str:
    return select_locale(
        explicit_locale=request.headers.get("x-open-work-hub-locale"),
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
    locale = _request_locale(request)
    body, error_code = build_request_validation_error_body(exc.errors(), locale)
    return JSONResponse(
        status_code=422,
        content=body,
        headers={ERROR_CODE_HEADER: error_code},
    )


def create_app(
    *,
    initialize_runtime: bool = True,
    external_runtime: ApiExternalRuntime | None = None,
) -> FastAPI:
    install_sensitive_http_logging_guard()
    settings = get_settings()
    frontend_build_id = read_frontend_build_id(settings.frontend_dist_dir)
    open_work_hub_desktop_update_dirs = prepare_open_work_hub_desktop_update_dirs(settings)
    telemetry_enabled = bootstrap_telemetry(
        service_name="open-work-hub-api",
        service_version=APP_VERSION,
        enabled=settings.otel_enabled,
        enable_console_exporter=settings.otel_console_exporter,
        enable_otlp_exporter=settings.otel_otlp_exporter_enabled,
        metrics_export_interval_ms=settings.otel_metrics_export_interval_ms,
    )
    telemetry_tracer = get_tracer("open_work_hub_api.http")
    selected_external_runtime = external_runtime
    if initialize_runtime:
        if selected_external_runtime is None:
            selected_external_runtime = ProductionApiExternalRuntime(
                settings,
                storage_prepare=ensure_bucket,
            )
        install_stack_dump_signal()
        initialize_platform_extensions(settings)
        init_db()
        selected_external_runtime.prepare()
        Path(settings.recording_spool_dir).expanduser().mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not initialize_runtime:
            yield
            return
        assert selected_external_runtime is not None
        try:
            async with selected_external_runtime.activate(app):
                if settings.llm_healthcheck_on_startup:
                    with get_session_factory()() as session:
                        llm_status = inspect_registered_llm_runtime(
                            session,
                            settings=settings,
                            probe="live",
                        )
                    app.state.llm_health = llm_status.pools.public_dict()
                    app.state.llm_effective = llm_status.workloads.public_dict()
                    if settings.llm_required and not llm_status.workloads.ready:
                        logger.warning(
                            "LLM effective readiness check failed: %s",
                            llm_status.workloads.public_dict(),
                        )
                if settings.opf_healthcheck_on_startup:
                    privacy_filter = prepare_privacy_filter(
                        settings=settings,
                        download=settings.opf_download_on_startup,
                    )
                    app.state.privacy_filter_health = privacy_filter
                    if settings.opf_required and not privacy_filter.ready:
                        logger.warning("Privacy Filter readiness check failed: %s", privacy_filter)
                if settings.rag_enabled and settings.rag_preload_on_startup:
                    app.state.rag_preload = preload_rag_runtime(settings)
                loop_lag_watchdog = start_event_loop_lag_watchdog(settings)
                app.state.loop_lag_watchdog = loop_lag_watchdog
                try:
                    yield
                finally:
                    loop_lag_watchdog.cancel()
                    await asyncio.gather(loop_lag_watchdog, return_exceptions=True)
                    app.state.loop_lag_watchdog = None
        finally:
            close_rag_runtime_resources()

    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
        generate_unique_id_function=stable_operation_id,
    )
    app.add_middleware(
        ClientBuildGuardMiddleware,
        expected_build_id=frontend_build_id,
    )
    app.state.frontend_build_id = frontend_build_id
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
        response.headers["X-Open-Work-Hub-Instance-Id"] = settings.instance_id
        trace_id = current_trace_id()
        if trace_id is not None:
            response.headers["X-Open-Work-Hub-Trace-Id"] = trace_id
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
            "version": APP_VERSION,
            "environment": settings.environment,
            "instance_id": settings.instance_id,
            "runtime_revision": RUNTIME_REVISION,
        }

    @app.get("/readyz", tags=["system"])
    def readyz(request: Request, response: Response) -> dict[str, object]:
        with get_session_factory()() as session:
            llm_status = inspect_registered_llm_runtime(
                session,
                settings=settings,
                probe="configured",
            )
        dual = llm_status.pools
        effective = llm_status.workloads
        rag = get_rag_runtime_health()
        if rag.get("enabled"):
            with get_session_factory()() as session:
                rag = attach_rag_queue_health(rag, db=session)
        locale = _request_locale(request)
        ready = effective.ready or not settings.llm_required
        if rag.get("enabled") and not rag.get("ready", False):
            ready = False
        privacy_filter = check_privacy_filter_health(settings=settings)
        if settings.opf_required and not privacy_filter.ready:
            ready = False
        app_realtime = getattr(request.app.state, "app_realtime", None)
        realtime = {
            "redis_available": bool(
                app_realtime is None or getattr(app_realtime, "redis_available", False)
            )
        }
        if not realtime["redis_available"]:
            ready = False
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "ok" if ready else "degraded",
            "version": APP_VERSION,
            "environment": settings.environment,
            "instance_id": settings.instance_id,
            "runtime_revision": RUNTIME_REVISION,
            "llm": dual.public_dict(locale=locale, include_base_url=False),
            "llm_effective": effective.public_dict(locale=locale),
            "privacy_filter": {
                "enabled": privacy_filter.enabled,
                "ready": privacy_filter.ready,
                "status": privacy_filter.status,
                "checkpoint": privacy_filter.checkpoint,
                "device": privacy_filter.device,
                "detail": privacy_filter.detail,
            },
            "rag": rag,
            "realtime": realtime,
        }

    register_api_routers(app, settings)
    mount_open_work_hub_desktop_update_feeds(app, settings, open_work_hub_desktop_update_dirs)
    mount_frontend(app, settings)
    return app
