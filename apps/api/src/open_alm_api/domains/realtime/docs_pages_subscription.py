from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import (
    bind_current_workspace,
    load_active_workspace_by_key,
    resolve_workspace_role,
    workspace_role_allows,
)
from open_alm_api.domains.auth.dependencies import resolve_auth_context_from_token
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.docs.access_context import (
    ensure_docs_workspace_access as _ensure_docs_workspace_access,
    native_doc_from_item_or_404 as _native_doc_from_item_or_404,
    share_token_allows_item_without_docs_access as _share_token_allows_item_without_docs_access,
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
    workspace_slug = payload.get("workspace_slug")
    share_token = payload.get("share_token")
    if not isinstance(item_id, str) or not item_id:
        raise localized_http_exception(status_code=400, code="validation.value_invalid")
    if not isinstance(workspace_slug, str) or not workspace_slug:
        workspace_slug = None
    if not isinstance(share_token, str) or not share_token:
        share_token = None

    session_factory = get_session_factory()
    db = session_factory()
    try:
        return resolve_docs_pages_subscription_in_session(
            db,
            item_id=item_id,
            workspace_slug=workspace_slug,
            share_token=share_token,
            token=token,
            user_id=user_id,
        )
    finally:
        db.close()


def resolve_docs_pages_subscription_in_session(
    db: Session,
    *,
    item_id: str,
    workspace_slug: str | None,
    share_token: str | None,
    token: str,
    user_id: str,
) -> DocsPagesSubscription:
    auth_context = resolve_auth_context_from_token(db, token, update_last_seen=False)
    if auth_context.user.id != user_id:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.required",
        )
    user = db.get(User, user_id)
    if user is None:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.user_not_found",
        )

    requires_workspace_access = (
        share_token is None or not _share_token_allows_item_without_docs_access(item_id)
    )
    if workspace_slug is not None:
        workspace = load_active_workspace_by_key(db, workspace_slug)
        if workspace is None:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="workspace.not_found",
            )
        bind_current_workspace(db, workspace)
        if requires_workspace_access:
            role = resolve_workspace_role(db, user, workspace.id)
            if not workspace_role_allows(role, "member"):
                raise localized_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="workspace.membership_required",
                    workspace=workspace.key,
                )

    if requires_workspace_access:
        _ensure_docs_workspace_access(db, user)
    doc, access = _native_doc_from_item_or_404(
        db,
        item_id,
        user,
        share_token=share_token,
    )
    if not access.can_view:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.doc_access_required",
        )
    return DocsPagesSubscription(doc_id=doc.id, updated_at=doc.updated_at)
