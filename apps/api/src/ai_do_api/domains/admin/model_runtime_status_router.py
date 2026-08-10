from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.admin.model_runtime_status_schemas import (
    AdminModelRuntimeStatusResponse,
)
from ai_do_api.domains.admin.model_runtime_status_service import (
    collect_model_runtime_status,
)
from ai_do_api.domains.auth.access import is_platform_admin_user
from ai_do_api.domains.auth.dependencies import AuthContext, require_permission


router = APIRouter(prefix="/admin/model-runtime-status", tags=["admin"])


@router.get("", response_model=AdminModelRuntimeStatusResponse)
async def get_admin_model_runtime_status(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AdminModelRuntimeStatusResponse:
    if not is_platform_admin_user(context.user, db):
        raise localized_http_exception(
            status_code=403,
            code="admin.platform_admin_required",
        )
    return await collect_model_runtime_status(db=db)


__all__ = ["router"]
