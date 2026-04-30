from fastapi import Depends, FastAPI

from aidoo_api.core.settings import Settings
from aidoo_api.domains.ai.router import router as ai_router
from aidoo_api.domains.admin.router import router as admin_router
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_legacy_workspace_membership,
    require_workspace_membership,
)
from aidoo_api.domains.auth.router import router as auth_router
from aidoo_api.domains.auth.workspace_router import router as workspace_router
from aidoo_api.domains.calendar.router import router as calendar_router
from aidoo_api.domains.conversations.router import router as conversations_router
from aidoo_api.domains.docs.router import router as docs_router
from aidoo_api.domains.docs.router import ws_router as docs_ws_router
from aidoo_api.domains.documents.router import router as documents_router
from aidoo_api.domains.drafts.router import router as drafts_router
from aidoo_api.domains.learning_notes.router import router as learning_notes_router
from aidoo_api.domains.media.router import router as media_router
from aidoo_api.domains.meeting.router import router as meeting_router
from aidoo_api.domains.ocr.router import router as ocr_router
from aidoo_api.domains.planner.router import router as planner_router
from aidoo_api.domains.plm.router import router as plm_router
from aidoo_api.domains.pms.router import router as pms_router
from aidoo_api.domains.rag.router import router as rag_router
from aidoo_api.domains.search.router import router as search_router
from aidoo_api.domains.wiki_pms.router import router as wiki_pms_router


def register_api_routers(app: FastAPI, settings: Settings) -> None:
    app.include_router(auth_router, prefix=settings.api_prefix)
    protected_dependencies = [Depends(require_current_user)]
    workspace_dependencies = [
        *protected_dependencies,
        Depends(require_workspace_membership()),
    ]
    legacy_workspace_dependencies = [
        *protected_dependencies,
        Depends(require_legacy_workspace_membership()),
    ]
    workspace_prefix = f"{settings.api_prefix}/workspaces/{{workspace_slug}}"

    app.include_router(
        workspace_router,
        prefix=settings.api_prefix,
        dependencies=workspace_dependencies,
    )
    app.include_router(ai_router, prefix=settings.api_prefix, dependencies=legacy_workspace_dependencies)
    app.include_router(ai_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(admin_router, prefix=settings.api_prefix, dependencies=protected_dependencies)
    app.include_router(
        documents_router,
        prefix=settings.api_prefix,
        dependencies=legacy_workspace_dependencies,
    )
    app.include_router(documents_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(docs_router, prefix=settings.api_prefix, dependencies=protected_dependencies)
    app.include_router(docs_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(docs_ws_router, prefix=workspace_prefix)
    app.include_router(plm_router, prefix=settings.api_prefix, dependencies=legacy_workspace_dependencies)
    app.include_router(plm_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(drafts_router, prefix=settings.api_prefix, dependencies=legacy_workspace_dependencies)
    app.include_router(drafts_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(ocr_router, prefix=settings.api_prefix, dependencies=legacy_workspace_dependencies)
    app.include_router(ocr_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(
        wiki_pms_router,
        prefix=settings.api_prefix,
        dependencies=legacy_workspace_dependencies,
    )
    app.include_router(wiki_pms_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(pms_router, prefix=settings.api_prefix, dependencies=legacy_workspace_dependencies)
    app.include_router(pms_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(
        meeting_router,
        prefix=settings.api_prefix,
        dependencies=legacy_workspace_dependencies,
    )
    app.include_router(meeting_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(
        calendar_router,
        prefix=settings.api_prefix,
        dependencies=legacy_workspace_dependencies,
    )
    app.include_router(calendar_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(
        planner_router,
        prefix=settings.api_prefix,
        dependencies=legacy_workspace_dependencies,
    )
    app.include_router(planner_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(rag_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    app.include_router(search_router, prefix=workspace_prefix, dependencies=workspace_dependencies)
    # Conversations are a new workspace-scoped feature with no pre-scoped
    # clients, so we intentionally mount only the /workspaces/:slug/ shape.
    # The legacy /api/v1/conversations mount would auto-bind to whichever
    # workspace `require_legacy_workspace_membership()` returned first, which
    # silently hides conversations from a user's other workspaces.
    app.include_router(
        conversations_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    app.include_router(media_router, prefix=settings.api_prefix, dependencies=protected_dependencies)
    # Learning page notes: global content, gated by the router's own permission
    # checks instead of workspace membership.
    app.include_router(
        learning_notes_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
