from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import resolve_auth_context_from_token
from open_work_hub_api.domains.docs.access_context import (
    ensure_docs_app_access as _ensure_docs_app_access,
)
from open_work_hub_api.domains.docs.access_context import (
    native_doc_from_item_or_404 as _native_doc_from_item_or_404,
)


@dataclass(frozen=True)
class DocsPagesSubscription:
    doc_id: str
    updated_at: datetime | None


def resolve_docs_pages_subscription(
    payload: dict[str, Any],
    *,
    token: str,
    user_id: str,
) -> DocsPagesSubscription:
    item_id = payload.get("key")
    share_token = payload.get("share_token")
    if not isinstance(item_id, str) or not item_id:
        raise localized_http_exception(status_code=400, code="validation.value_invalid")
    if share_token is not None and (not isinstance(share_token, str) or not share_token):
        raise localized_http_exception(status_code=400, code="validation.value_invalid")

    session_factory = get_session_factory()
    db = session_factory()
    try:
        return resolve_docs_pages_subscription_in_session(
            db,
            item_id=item_id,
            share_token=share_token,
            token=token,
            user_id=user_id,
        )
    finally:
        db.close()


def resolve_docs_pages_subscription_in_session(
    db: Session, *, item_id: str, share_token: str | None, token: str, user_id: str
) -> DocsPagesSubscription:
    auth_context = resolve_auth_context_from_token(db, token, update_last_seen=False)
    if auth_context.user.id != user_id:
        raise localized_http_exception(status_code=401, code="auth.required")
    _ensure_docs_app_access(db, auth_context.user)
    doc, access = _native_doc_from_item_or_404(
        db, item_id, auth_context.user, share_token=share_token
    )
    if not access.can_view:
        raise localized_http_exception(status_code=403, code="docs.doc_access_required")
    return DocsPagesSubscription(doc_id=doc.id, updated_at=doc.updated_at)
