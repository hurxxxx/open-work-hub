from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.domains.auth.access import build_apps_bootstrap
from ai_do_api.domains.auth.dependencies import require_current_user
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.auth.workspace_bootstrap_schemas import (
    WorkspaceBootstrapAppBarCategoryResponse,
)


class AppsBootstrapAppResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    icon_key: str
    availability_scope: Literal["platform"] = "platform"
    enabled: bool
    coming_soon: bool = False


class AppsBootstrapPrincipalResponse(BaseModel):
    kind: Literal["user"] = "user"
    scope: Literal["personal"] = "personal"
    workspace_id: None = None
    source: str
    user_id: str
    session_id: str | None = None


class AppsBootstrapResponse(BaseModel):
    apps: list[AppsBootstrapAppResponse] = Field(default_factory=list)
    app_bar_categories: list[WorkspaceBootstrapAppBarCategoryResponse] = Field(default_factory=list)
    personal_tools: list[AppsBootstrapAppResponse] = Field(default_factory=list)
    platform_enabled_app_ids: list[str] = Field(default_factory=list)
    principal: AppsBootstrapPrincipalResponse


router = APIRouter(prefix="/apps", tags=["apps"])


@router.get("/bootstrap", response_model=AppsBootstrapResponse)
def get_apps_bootstrap(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> AppsBootstrapResponse:
    auth_context = getattr(request.state, "auth_context", None)
    session = getattr(auth_context, "session", None)
    return AppsBootstrapResponse.model_validate(
        build_apps_bootstrap(
            db,
            user=current_user,
            source="api.apps_bootstrap",
            session_id=getattr(session, "id", None),
        )
    )
