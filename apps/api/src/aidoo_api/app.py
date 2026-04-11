import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi import Response, status

from aidoo_api.core.db import init_db
from aidoo_api.core.llm import check_llm_stack_health
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import ensure_bucket
from aidoo_api.domains.ai.router import router as ai_router
from aidoo_api.domains.admin.router import router as admin_router
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_workspace_app_enabled,
    require_workspace_feature_access,
)
from aidoo_api.domains.auth.router import router as auth_router
from aidoo_api.domains.docs.router import router as docs_router
from aidoo_api.domains.documents.router import router as documents_router
from aidoo_api.domains.drafts.router import router as drafts_router
from aidoo_api.domains.media.router import router as media_router
from aidoo_api.domains.meeting.router import router as meeting_router
from aidoo_api.domains.ocr.router import router as ocr_router
from aidoo_api.domains.pms.router import router as pms_router
from aidoo_api.domains.plm.router import router as plm_router
from aidoo_api.domains.wiki_pms.router import router as wiki_pms_router


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    ensure_bucket()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.llm_healthcheck_on_startup:
            llm_health = check_llm_stack_health(settings)
            app.state.llm_health = llm_health.public_dict()
            if settings.llm_required and not llm_health.ready:
                logger.warning("LLM readiness check failed: %s", llm_health.public_dict())
        yield

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    @app.get("/readyz", tags=["system"])
    def readyz(response: Response) -> dict[str, object]:
        llm_health = check_llm_stack_health(settings)
        ready = llm_health.ready or not settings.llm_required
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "ok" if ready else "degraded",
            "environment": settings.environment,
            "llm": llm_health.public_dict(),
        }

    app.include_router(auth_router, prefix=settings.api_prefix)
    protected_dependencies = [Depends(require_current_user)]
    app.include_router(
        ai_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("ai", "nav.ai")),
        ],
    )
    app.include_router(
        ai_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("ai")),
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
            Depends(require_workspace_feature_access("docs", "nav.docs")),
        ],
    )
    app.include_router(
        documents_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("docs")),
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
            Depends(require_workspace_app_enabled("docs")),
        ],
    )
    app.include_router(
        plm_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("ai", "nav.ai")),
        ],
    )
    app.include_router(
        plm_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("ai")),
        ],
    )
    app.include_router(
        drafts_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("docs", "nav.docs")),
        ],
    )
    app.include_router(
        drafts_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("docs")),
        ],
    )
    app.include_router(
        ocr_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("ai", "nav.ai")),
        ],
    )
    app.include_router(
        ocr_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("ai")),
        ],
    )
    app.include_router(
        wiki_pms_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("docs", "nav.docs")),
        ],
    )
    app.include_router(
        wiki_pms_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("docs")),
        ],
    )
    app.include_router(
        pms_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("pms", "nav.pms")),
        ],
    )
    app.include_router(
        pms_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("pms")),
        ],
    )
    app.include_router(
        meeting_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("meeting", "nav.meeting")),
        ],
    )
    app.include_router(
        meeting_router,
        prefix=f"{settings.api_prefix}/workspaces/{{workspace_slug}}",
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_app_enabled("meeting")),
        ],
    )
    app.include_router(
        media_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    return app
