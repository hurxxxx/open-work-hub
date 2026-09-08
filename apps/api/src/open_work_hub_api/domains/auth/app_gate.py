from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.auth.app_access import allowed_app_ids, can_use_app
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User


def is_app_enabled_for_principal(db: Session, principal: CallerPrincipal, app_id: str) -> bool:
    return (
        principal.kind == "user"
        and principal.user_id is not None
        and can_use_app(db, user_id=principal.user_id, app_id=app_id)
    )


def require_app_access(
    app_id: str, *, error_code: str = "platform.app_disabled"
) -> Callable[..., None]:
    def dependency(
        db: Session = Depends(get_db_session),
        user: User = Depends(require_current_user),
    ) -> None:
        if not can_use_app(db, user_id=user.id, app_id=app_id):
            raise localized_http_exception(status_code=403, code=error_code)

    return dependency


__all__ = ["allowed_app_ids", "can_use_app", "is_app_enabled_for_principal", "require_app_access"]
