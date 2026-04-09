from fastapi import Depends, FastAPI

from aidoo_api.core.db import init_db
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import ensure_bucket
from aidoo_api.domains.admin.router import router as admin_router
from aidoo_api.domains.auth.dependencies import require_current_user, require_workspace_feature_access
from aidoo_api.domains.auth.router import router as auth_router
from aidoo_api.domains.documents.router import router as documents_router
from aidoo_api.domains.drafts.router import router as drafts_router
from aidoo_api.domains.media.router import router as media_router
from aidoo_api.domains.ocr.router import router as ocr_router
from aidoo_api.domains.pms.router import router as pms_router
from aidoo_api.domains.plm.router import router as plm_router
from aidoo_api.domains.wiki_pms.router import router as wiki_pms_router


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()
    ensure_bucket()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(auth_router, prefix=settings.api_prefix)
    protected_dependencies = [Depends(require_current_user)]
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
        plm_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("ai", "nav.ai")),
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
        ocr_router,
        prefix=settings.api_prefix,
        dependencies=[
            *protected_dependencies,
            Depends(require_workspace_feature_access("ai", "nav.ai")),
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
        pms_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    app.include_router(
        media_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    return app
