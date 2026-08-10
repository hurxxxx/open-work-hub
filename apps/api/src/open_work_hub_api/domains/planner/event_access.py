from __future__ import annotations

from fastapi import status

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.auth.models import User


def ensure_planner_principal_user(*, principal: CallerPrincipal, user: User) -> None:
    if principal.kind == "user" and principal.user_id not in {None, user.id}:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="planner.principal_user_mismatch",
        )


def require_planner_user_write_principal(principal: CallerPrincipal) -> None:
    if principal.kind != "user":
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="planner.write_user_principal_required",
        )
