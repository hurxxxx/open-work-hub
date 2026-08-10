from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.domains.auth.access import (
    build_workspace_bootstrap,
)
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.workspace_bootstrap_schemas import (
    WorkspaceBootstrapAppBarCategoryItemResponse,
    WorkspaceBootstrapAppBarCategoryResponse,
    WorkspaceBootstrapAppResponse,
    WorkspaceBootstrapNavItemResponse,
    WorkspaceBootstrapResponse,
    WorkspaceBootstrapWorkspaceResponse,
)

__all__ = [
    "WorkspaceBootstrapAppBarCategoryItemResponse",
    "WorkspaceBootstrapAppBarCategoryResponse",
    "WorkspaceBootstrapAppResponse",
    "WorkspaceBootstrapNavItemResponse",
    "WorkspaceBootstrapResponse",
    "WorkspaceBootstrapWorkspaceResponse",
    "router",
]


router = APIRouter(prefix="/workspaces/{workspace_slug}", tags=["workspaces"])


@router.get("/bootstrap", response_model=WorkspaceBootstrapResponse)
def get_workspace_bootstrap(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> WorkspaceBootstrapResponse:
    return WorkspaceBootstrapResponse.model_validate(
        build_workspace_bootstrap(
            db,
            user=current_user,
            workspace=current_workspace,
            source="api.workspace_bootstrap",
            session_id=getattr(getattr(request.state, "auth_context", None), "session", None).id
            if getattr(request.state, "auth_context", None) is not None
            else None,
        )
    )
