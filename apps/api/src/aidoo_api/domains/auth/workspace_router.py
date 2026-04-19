from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import (
    build_workspace_bootstrap,
)
from aidoo_api.domains.auth.dependencies import require_current_user, require_current_workspace
from aidoo_api.domains.auth.models import User, Workspace


class WorkspaceBootstrapWorkspaceResponse(BaseModel):
    id: str
    slug: str
    name: str
    role: str


class WorkspaceBootstrapNavItemResponse(BaseModel):
    id: str
    app_id: str
    title: str
    category: str
    icon_key: str
    link_app_id: str | None = None
    path_suffix: str | None = None
    absolute_path: str | None = None


class WorkspaceBootstrapAppResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    enabled: bool
    nav_items: list[WorkspaceBootstrapNavItemResponse]


class WorkspaceBootstrapResponse(BaseModel):
    workspace: WorkspaceBootstrapWorkspaceResponse
    apps: list[WorkspaceBootstrapAppResponse]
    nav: list[WorkspaceBootstrapNavItemResponse]


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
