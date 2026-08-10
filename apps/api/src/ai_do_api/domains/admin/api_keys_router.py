from __future__ import annotations

from datetime import datetime
from typing import NoReturn

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import record_audit_log
from ai_do_api.domains.auth.dependencies import AuthContext, require_permission
from ai_do_api.domains.auth.models import PlatformApiKey, User
from ai_do_api.domains.auth.platform_api_keys import (
    PLATFORM_API_KEY_SCOPE_REGISTRY,
    PlatformApiKeyServiceError,
    issue_platform_api_key,
    list_platform_api_keys,
    reveal_platform_api_key,
    revoke_platform_api_key,
)


router = APIRouter(prefix="/admin/api-keys", tags=["admin"])


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


class PlatformApiKeyItemResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    created_by_name: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class PlatformApiKeyListResponse(BaseModel):
    available_scopes: list[str]
    items: list[PlatformApiKeyItemResponse]


class PlatformApiKeyIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(min_length=1, max_length=64)


class PlatformApiKeyIssueResponse(BaseModel):
    item: PlatformApiKeyItemResponse
    api_key: str


def _serialize_platform_api_key(
    row: PlatformApiKey,
    *,
    created_by_name: str,
) -> PlatformApiKeyItemResponse:
    return PlatformApiKeyItemResponse(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=list(row.scopes),
        created_by_name=created_by_name,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


def _platform_api_key_creator_names(
    db: Session,
    rows: list[PlatformApiKey],
) -> dict[str, str]:
    user_ids = {row.created_by_user_id for row in rows if row.created_by_user_id is not None}
    if not user_ids:
        return {}
    return {
        user_id: (display_name or full_name)
        for user_id, display_name, full_name in db.execute(
            select(User.id, User.display_name, User.full_name).where(User.id.in_(user_ids))
        ).all()
    }


def _raise_platform_api_key_error(
    db: Session,
    error: PlatformApiKeyServiceError,
) -> NoReturn:
    db.rollback()
    status_by_code = {
        "admin.platform_api_key_not_found": status.HTTP_404_NOT_FOUND,
        "admin.platform_api_key_inactive": status.HTTP_409_CONFLICT,
        "admin.platform_api_key_encryption_unavailable": (status.HTTP_503_SERVICE_UNAVAILABLE),
        "admin.platform_api_key_issue_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
        "admin.platform_api_key_name_required": status.HTTP_400_BAD_REQUEST,
        "admin.platform_api_key_name_invalid": status.HTTP_400_BAD_REQUEST,
        "admin.platform_api_key_scope_invalid": status.HTTP_400_BAD_REQUEST,
    }
    raise localized_http_exception(
        status_code=status_by_code.get(error.code, status.HTTP_400_BAD_REQUEST),
        code=error.code,
    ) from error


@router.get("", response_model=PlatformApiKeyListResponse)
def get_platform_api_keys(
    response: Response,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeyListResponse:
    rows = list_platform_api_keys(db)
    creator_names = _platform_api_key_creator_names(db, rows)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.platform_api_key.list",
        entity_kind="platform_api_key",
        entity_id=None,
        summary="Listed platform API keys",
        payload={"result_count": len(rows)},
    )
    db.commit()
    _set_no_store_headers(response)
    return PlatformApiKeyListResponse(
        available_scopes=list(PLATFORM_API_KEY_SCOPE_REGISTRY),
        items=[
            _serialize_platform_api_key(
                row,
                created_by_name=creator_names.get(row.created_by_user_id or "", "-"),
            )
            for row in rows
        ],
    )


@router.post(
    "",
    response_model=PlatformApiKeyIssueResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_platform_api_key(
    payload: PlatformApiKeyIssueRequest,
    response: Response,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeyIssueResponse:
    try:
        issued = issue_platform_api_key(
            db,
            name=payload.name,
            scopes=payload.scopes,
            actor_user_id=context.user.id,
        )
    except PlatformApiKeyServiceError as error:
        _raise_platform_api_key_error(db, error)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.platform_api_key.issue",
        entity_kind="platform_api_key",
        entity_id=issued.row.id,
        summary="Issued platform API key",
        payload={"scopes": issued.row.scopes},
    )
    db.commit()
    _set_no_store_headers(response)
    return PlatformApiKeyIssueResponse(
        item=_serialize_platform_api_key(
            issued.row,
            created_by_name=context.user.display_name or context.user.full_name,
        ),
        api_key=issued.secret.get_secret_value(),
    )


@router.post(
    "/{key_id}/reveal",
    response_model=PlatformApiKeyIssueResponse,
)
def post_platform_api_key_reveal(
    key_id: str,
    response: Response,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeyIssueResponse:
    try:
        secret = reveal_platform_api_key(db, key_id)
        row = db.get(PlatformApiKey, key_id)
        assert row is not None
    except PlatformApiKeyServiceError as error:
        _raise_platform_api_key_error(db, error)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.platform_api_key.reveal",
        entity_kind="platform_api_key",
        entity_id=key_id,
        summary="Revealed platform API key",
        payload={},
    )
    db.commit()
    _set_no_store_headers(response)
    creator_names = _platform_api_key_creator_names(db, [row])
    return PlatformApiKeyIssueResponse(
        item=_serialize_platform_api_key(
            row,
            created_by_name=creator_names.get(row.created_by_user_id or "", "-"),
        ),
        api_key=secret.get_secret_value(),
    )


@router.post(
    "/{key_id}/revoke",
    response_model=PlatformApiKeyItemResponse,
)
def post_platform_api_key_revoke(
    key_id: str,
    response: Response,
    context: AuthContext = Depends(require_permission("admin.access")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeyItemResponse:
    try:
        row = revoke_platform_api_key(
            db,
            key_id=key_id,
            actor_user_id=context.user.id,
        )
    except PlatformApiKeyServiceError as error:
        _raise_platform_api_key_error(db, error)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.platform_api_key.revoke",
        entity_kind="platform_api_key",
        entity_id=key_id,
        summary="Revoked platform API key",
        payload={},
    )
    db.commit()
    _set_no_store_headers(response)
    creator_names = _platform_api_key_creator_names(db, [row])
    return _serialize_platform_api_key(
        row,
        created_by_name=creator_names.get(row.created_by_user_id or "", "-"),
    )


__all__ = ["router"]
