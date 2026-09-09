from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.bootstrap_schemas import (
    BootstrapAppBarCategoryResponse,
    BootstrapAppResponse,
    BootstrapKeywordSearchResponse,
    BootstrapNavItemResponse,
)
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.launch_catalog import build_launch_catalog
from open_work_hub_api.domains.auth.models import User


class AppsBootstrapPrincipalResponse(BaseModel):
    kind: Literal["user"] = "user"
    source: str
    user_id: str
    session_id: str | None = None


class AppsBootstrapResponse(BaseModel):
    apps: list[BootstrapAppResponse]
    nav: list[BootstrapNavItemResponse]
    app_bar_categories: list[BootstrapAppBarCategoryResponse]
    personal_tool_app_ids: list[str]
    chatbot_app_ids: list[str]
    keyword_search: BootstrapKeywordSearchResponse
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
        build_launch_catalog(
            db,
            user=current_user,
            source="api.apps_bootstrap",
            session_id=getattr(session, "id", None),
        )
    )
