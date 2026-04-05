from fastapi import FastAPI

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.documents.router import router as documents_router
from aidoo_api.domains.drafts.router import router as drafts_router
from aidoo_api.domains.ocr.router import router as ocr_router
from aidoo_api.domains.plm.router import router as plm_router
from aidoo_api.domains.wiki_pms.router import router as wiki_pms_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(documents_router, prefix=settings.api_prefix)
    app.include_router(plm_router, prefix=settings.api_prefix)
    app.include_router(drafts_router, prefix=settings.api_prefix)
    app.include_router(ocr_router, prefix=settings.api_prefix)
    app.include_router(wiki_pms_router, prefix=settings.api_prefix)
    return app
