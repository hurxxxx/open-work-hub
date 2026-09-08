from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import resolve_auth_context_from_token
from open_work_hub_api.domains.whiteboard.access import (
    ensure_whiteboard_app_access,
    load_whiteboard_for_share_token_or_404,
    load_whiteboard_for_user_or_404,
)


def resolve_whiteboard_access_subscription(
    payload: dict[str, Any], *, token: str, user_id: str
) -> str:
    board_id = payload.get("key")
    share_token = payload.get("share_token")
    if not isinstance(board_id, str) or not board_id:
        raise localized_http_exception(status_code=400, code="validation.value_invalid")
    if share_token is not None and (not isinstance(share_token, str) or not share_token):
        raise localized_http_exception(status_code=400, code="validation.value_invalid")
    with get_session_factory()() as db:
        return resolve_whiteboard_access_subscription_in_session(
            db, board_id=board_id, share_token=share_token, token=token, user_id=user_id
        )


def resolve_whiteboard_access_subscription_in_session(
    db: Session, *, board_id: str, share_token: str | None, token: str, user_id: str
) -> str:
    auth_context = resolve_auth_context_from_token(db, token, update_last_seen=False)
    if auth_context.user.id != user_id:
        raise localized_http_exception(status_code=401, code="auth.required")
    ensure_whiteboard_app_access(db, auth_context.user)
    if share_token is not None:
        context = load_whiteboard_for_share_token_or_404(db, share_token, auth_context.user)
    else:
        context = load_whiteboard_for_user_or_404(db, board_id, auth_context.user)
    if context.whiteboard.id != board_id or not context.access.can_view:
        raise localized_http_exception(status_code=404, code="whiteboard.not_found")
    return context.whiteboard.id
