from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.app_workspace_preferences import (
    set_app_workspace_preference,
)
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.launch_catalog import (
    build_launch_catalog,
    query_eligible_workspaces_for_app,
)
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.workspace_bootstrap_schemas import (
    WorkspaceBootstrapAppBarCategoryResponse,
)


class EligibleWorkspaceResponse(BaseModel):
    id: str
    slug: str
    name: str


class _AppsBootstrapAppBaseResponse(BaseModel):
    app_id: str
    title: str
    route_base: str
    entry_route_id: str
    icon_key: str
    execution_context_kind: Literal["personal", "company", "workspace"]
    resource_scope: Literal["personal", "company", "workspace", "hybrid"]
    coming_soon: bool = False


class PlatformAppsBootstrapAppResponse(_AppsBootstrapAppBaseResponse):
    availability_scope: Literal["platform"]
    eligible_workspace_count: Literal[0] = 0
    preferred_workspace: None = None
    single_eligible_workspace: None = None


class WorkspaceAppsBootstrapAppResponse(_AppsBootstrapAppBaseResponse):
    availability_scope: Literal["workspace"]
    eligible_workspace_count: int = Field(ge=0)
    preferred_workspace: EligibleWorkspaceResponse | None = None
    single_eligible_workspace: EligibleWorkspaceResponse | None = None


AppsBootstrapAppResponse = Annotated[
    PlatformAppsBootstrapAppResponse | WorkspaceAppsBootstrapAppResponse,
    Field(discriminator="availability_scope"),
]


class AppsBootstrapPrincipalResponse(BaseModel):
    kind: Literal["user"] = "user"
    scope: Literal["personal"] = "personal"
    workspace_id: None = None
    source: str
    user_id: str
    session_id: str | None = None


class AppsBootstrapResponse(BaseModel):
    apps: list[AppsBootstrapAppResponse]
    global_route_app_ids: list[str]
    app_bar_categories: list[WorkspaceBootstrapAppBarCategoryResponse]
    personal_tool_app_ids: list[str]
    principal: AppsBootstrapPrincipalResponse


class EligibleWorkspacesResponse(BaseModel):
    app_id: str
    items: list[EligibleWorkspaceResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class AppWorkspacePreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, max_length=36)


class AppWorkspacePreferenceResponse(BaseModel):
    app_id: str
    workspace_id: str
    updated_at: datetime


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
        build_launch_catalog(
            db,
            user=current_user,
            source="api.apps_bootstrap",
            session_id=getattr(session, "id", None),
        )
    )


@router.get(
    "/{app_id}/eligible-workspaces",
    response_model=EligibleWorkspacesResponse,
)
def get_eligible_workspaces(
    app_id: str,
    q: str | None = Query(default=None, max_length=120),
    slug: str | None = Query(default=None, min_length=1, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> EligibleWorkspacesResponse:
    app, workspaces, total = query_eligible_workspaces_for_app(
        db,
        user=current_user,
        app_id=app_id,
        query=q or "",
        slug=slug or "",
        page=page,
        page_size=page_size,
    )
    if app is None:
        raise localized_http_exception(status_code=404, code="app.not_found")
    if app.availability_scope != "workspace":
        raise localized_http_exception(
            status_code=400,
            code="app.workspace_context_unsupported",
        )
    return EligibleWorkspacesResponse(
        app_id=app_id,
        items=[
            EligibleWorkspaceResponse(
                id=str(workspace["id"]),
                slug=str(workspace["slug"]),
                name=str(workspace["name"]),
            )
            for workspace in workspaces
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.put(
    "/{app_id}/workspace-preference",
    response_model=AppWorkspacePreferenceResponse,
)
def update_app_workspace_preference(
    app_id: str,
    payload: AppWorkspacePreferenceRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> AppWorkspacePreferenceResponse:
    preference = set_app_workspace_preference(
        db,
        user=current_user,
        app_id=app_id,
        workspace_id=payload.workspace_id,
    )
    db.commit()
    return AppWorkspacePreferenceResponse(
        app_id=preference.app_id,
        workspace_id=preference.workspace_id,
        updated_at=preference.updated_at,
    )
