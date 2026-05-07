from collections.abc import Sequence

from fastapi import APIRouter, Depends, FastAPI
from fastapi.params import Depends as DependsParam

from ai_do_api.core.settings import Settings
from ai_do_api.domains.ai.router import router as ai_router
from ai_do_api.domains.admin.router import router as admin_router
from ai_do_api.domains.auth.dependencies import (
    require_current_user,
    require_workspace_membership,
)
from ai_do_api.domains.auth.router import router as auth_router
from ai_do_api.domains.auth.workspace_router import router as workspace_router
from ai_do_api.domains.calendar.router import router as calendar_router
from ai_do_api.domains.conversations.router import router as conversations_router
from ai_do_api.domains.docs.router import public_router as docs_public_router
from ai_do_api.domains.docs.router import router as docs_router
from ai_do_api.domains.docs.router import ws_router as docs_ws_router
from ai_do_api.domains.documents.router import router as documents_router
from ai_do_api.domains.drafts.router import router as drafts_router
from ai_do_api.domains.images.router import router as images_router
from ai_do_api.domains.learning_notes.router import router as learning_notes_router
from ai_do_api.domains.media.router import router as media_router
from ai_do_api.domains.meeting.router import router as meeting_router
from ai_do_api.domains.ocr.router import router as ocr_router
from ai_do_api.domains.planner.router import router as planner_router
from ai_do_api.domains.plm.router import router as plm_router
from ai_do_api.domains.pms.router import router as pms_router
from ai_do_api.domains.rag.router import router as rag_router
from ai_do_api.domains.recording.router import router as recording_router
from ai_do_api.domains.search.router import router as search_router
from ai_do_api.domains.whiteboard.router import public_router as whiteboard_public_router
from ai_do_api.domains.whiteboard.router import router as whiteboard_router
from ai_do_api.domains.whiteboard.router import ws_router as whiteboard_ws_router
from ai_do_api.domains.wiki_pms.router import router as wiki_pms_router
from ai_do_api.openapi_contract import PROTECTED_ERROR_RESPONSES


def _include_protected_router(
    app: FastAPI,
    router: APIRouter,
    *,
    prefix: str,
    dependencies: Sequence[DependsParam],
) -> None:
    app.include_router(
        router,
        prefix=prefix,
        dependencies=dependencies,
        responses=PROTECTED_ERROR_RESPONSES,
    )


def register_api_routers(app: FastAPI, settings: Settings) -> None:
    app.include_router(auth_router, prefix=settings.api_prefix)
    protected_dependencies = [Depends(require_current_user)]
    workspace_dependencies = [
        *protected_dependencies,
        Depends(require_workspace_membership()),
    ]
    workspace_prefix = f"{settings.api_prefix}/workspaces/{{workspace_slug}}"

    _include_protected_router(
        app,
        workspace_router,
        prefix=settings.api_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        ai_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        admin_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    _include_protected_router(
        app,
        documents_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        docs_public_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    _include_protected_router(
        app,
        docs_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        whiteboard_public_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    _include_protected_router(
        app,
        whiteboard_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    app.include_router(docs_ws_router, prefix=workspace_prefix)
    app.include_router(whiteboard_ws_router, prefix=workspace_prefix)
    _include_protected_router(
        app,
        plm_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        drafts_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        ocr_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        wiki_pms_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        pms_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        meeting_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        recording_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        images_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        calendar_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        planner_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        rag_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        search_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    # Conversations are a new workspace-scoped feature with no pre-scoped
    # clients, so we intentionally mount only the /workspaces/:slug/ shape.
    # The legacy /api/v1/conversations mount would auto-bind to whichever
    # workspace `require_legacy_workspace_membership()` returned first, which
    # silently hides conversations from a user's other workspaces.
    _include_protected_router(
        app,
        conversations_router,
        prefix=workspace_prefix,
        dependencies=workspace_dependencies,
    )
    _include_protected_router(
        app,
        media_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
    # Learning page notes: global content, gated by the router's own permission
    # checks instead of workspace membership.
    _include_protected_router(
        app,
        learning_notes_router,
        prefix=settings.api_prefix,
        dependencies=protected_dependencies,
    )
