import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi import Response, status
from fastapi.responses import Response as FastAPIResponse

from aidoo_api.core.db import get_session_factory, init_db
from aidoo_api.core.llm import (
    check_all_pools_health,
    check_effective_llm_readiness,
)
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import ensure_bucket
from aidoo_api.domains.ai.registry import initialize_ai_capability_registry
from aidoo_api.domains.ai.router import router as ai_router
from aidoo_api.domains.admin.router import router as admin_router
from aidoo_api.domains.calendar.router import router as calendar_router
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_legacy_workspace_membership,
    require_workspace_membership,
)
from aidoo_api.domains.auth.router import router as auth_router
from aidoo_api.domains.auth.workspace_router import router as workspace_router
from aidoo_api.domains.docs.collab import DocsCollabHub
from aidoo_api.domains.conversations.router import router as conversations_router
from aidoo_api.domains.docs.router import router as docs_router
from aidoo_api.domains.docs.router import ws_router as docs_ws_router
from aidoo_api.domains.documents.router import router as documents_router
from aidoo_api.domains.drafts.router import router as drafts_router
from aidoo_api.domains.media.router import router as media_router
from aidoo_api.domains.meeting.router import router as meeting_router
from aidoo_api.domains.ocr.router import router as ocr_router
from aidoo_api.domains.pms.router import router as pms_router
from aidoo_api.domains.planner.router import router as planner_router
from aidoo_api.domains.plm.router import router as plm_router
from aidoo_api.domains.wiki_pms.router import router as wiki_pms_router


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    initialize_ai_capability_registry()
    init_db()
    ensure_bucket()
    Path(settings.recording_spool_dir).expanduser().mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.docs_collab = DocsCollabHub()
        await app.state.docs_collab.startup()
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
        await app.state.docs_collab.shutdown()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def add_instance_headers(request, call_next) -> FastAPIResponse:
        response = await call_next(request)
        response.headers["X-Doowon-Instance-Id"] = settings.instance_id
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
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "ok" if ready else "degraded",
            "environment": settings.environment,
            "instance_id": settings.instance_id,
            "llm": dual.public_dict(),
            "llm_effective": effective.public_dict(),
        }

    app.include_router(auth_router, prefix=settings.api_prefix)
    protected_dependencies = [Depends(require_current_user)]
    app.include_router(
        workspace_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        ai_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        ai_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        admin_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    app.include_router(
        documents_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        documents_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        docs_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    app.include_router(
        docs_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        docs_ws_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
    )
    app.include_router(
        plm_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        plm_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        drafts_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        drafts_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        ocr_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        ocr_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        wiki_pms_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        wiki_pms_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        pms_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        pms_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        meeting_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        meeting_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        calendar_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        calendar_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        planner_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_legacy_workspace_membership()),
        ],
    )
    app.include_router(
        planner_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    # Conversations are a new workspace-scoped feature with no pre-scoped
    # clients, so we intentionally mount only the /workspaces/:slug/ shape.
    # The legacy /api/v1/conversations mount would auto-bind to whichever
    # workspace `require_legacy_workspace_membership()` returned first, which
    # silently hides conversations from a user's other workspaces.
    app.include_router(
        conversations_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_membership()),
        ],
    )
    app.include_router(
        media_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    return app
