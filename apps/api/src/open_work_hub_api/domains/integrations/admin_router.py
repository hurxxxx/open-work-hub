from __future__ import annotations

from datetime import datetime
from typing import NoReturn
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import record_audit_log
from open_work_hub_api.domains.auth.dependencies import AuthContext, require_permission
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.integrations.models import PlatformApiKey
from open_work_hub_api.domains.integrations.platform_api_keys import (
    PLATFORM_API_KEY_SCOPE_OPENAPI_EXTENSION,
    PLATFORM_API_KEY_SCOPE_REGISTRY,
    PlatformApiKeyServiceError,
    issue_platform_api_key,
    list_platform_api_keys,
    reveal_platform_api_key,
    revoke_platform_api_key,
)

router = APIRouter(prefix="/admin/platform-api-keys", tags=["admin-platform-api-keys"])
_OPENAPI_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")


class PlatformApiKeyItemResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    status: str
    created_by_name: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class PlatformApiScopeOperationResponse(BaseModel):
    method: str
    path: str
    operation_id: str
    summary: str | None = None
    swagger_path: str
    redoc_path: str


class PlatformApiScopeSpecResponse(BaseModel):
    scope: str
    operations: list[PlatformApiScopeOperationResponse]


class PlatformApiDocumentationResponse(BaseModel):
    swagger_path: str
    redoc_path: str
    openapi_path: str


class PlatformApiKeyListResponse(BaseModel):
    available_scopes: list[str]
    documentation: PlatformApiDocumentationResponse
    scope_specs: list[PlatformApiScopeSpecResponse]
    items: list[PlatformApiKeyItemResponse]


class PlatformApiKeyIssueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(min_length=1, max_length=2)


class PlatformApiKeySecretResponse(BaseModel):
    item: PlatformApiKeyItemResponse
    api_key: str


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


def _creator_names(db: Session, rows: list[PlatformApiKey]) -> dict[str, str]:
    user_ids = {row.created_by_user_id for row in rows if row.created_by_user_id is not None}
    if not user_ids:
        return {}
    return {
        user_id: (display_name or full_name)
        for user_id, display_name, full_name in db.execute(
            select(User.id, User.display_name, User.full_name).where(User.id.in_(user_ids))
        ).all()
    }


def _serialize_key(
    row: PlatformApiKey,
    *,
    created_by_name: str,
) -> PlatformApiKeyItemResponse:
    return PlatformApiKeyItemResponse(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        scopes=list(row.scopes),
        status=row.status,
        created_by_name=created_by_name,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
    )


def _scope_specs(request: Request) -> list[PlatformApiScopeSpecResponse]:
    operations_by_scope: dict[str, list[PlatformApiScopeOperationResponse]] = {
        scope: [] for scope in PLATFORM_API_KEY_SCOPE_REGISTRY
    }
    for path, path_item in sorted(request.app.openapi().get("paths", {}).items()):
        if not isinstance(path_item, dict):
            continue
        for method in _OPENAPI_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            scopes = operation.get(PLATFORM_API_KEY_SCOPE_OPENAPI_EXTENSION)
            operation_id = operation.get("operationId")
            if not isinstance(scopes, list) or not isinstance(operation_id, str):
                continue
            tags = operation.get("tags")
            tag = tags[0] if isinstance(tags, list) and tags else "default"
            if not isinstance(tag, str):
                tag = "default"
            item = PlatformApiScopeOperationResponse(
                method=method.upper(),
                path=path,
                operation_id=operation_id,
                summary=operation.get("summary")
                if isinstance(operation.get("summary"), str)
                else None,
                swagger_path=f"/docs#/{quote(tag, safe='')}/{quote(operation_id, safe='')}",
                redoc_path=f"/redoc#tag/{quote(tag, safe='')}/operation/{quote(operation_id, safe='')}",
            )
            for scope in scopes:
                if isinstance(scope, str) and scope in operations_by_scope:
                    operations_by_scope[scope].append(item)
    return [
        PlatformApiScopeSpecResponse(scope=scope, operations=operations_by_scope[scope])
        for scope in PLATFORM_API_KEY_SCOPE_REGISTRY
    ]


def _raise_key_error(db: Session, error: PlatformApiKeyServiceError) -> NoReturn:
    db.rollback()
    status_by_code = {
        "platform_api_key.not_found": status.HTTP_404_NOT_FOUND,
        "platform_api_key.inactive": status.HTTP_409_CONFLICT,
        "platform_api_key.encryption_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
        "platform_api_key.issue_failed": status.HTTP_503_SERVICE_UNAVAILABLE,
        "platform_api_key.name_required": status.HTTP_400_BAD_REQUEST,
        "platform_api_key.name_invalid": status.HTTP_400_BAD_REQUEST,
        "platform_api_key.scope_invalid": status.HTTP_400_BAD_REQUEST,
    }
    raise localized_http_exception(
        status_code=status_by_code.get(error.code, status.HTTP_400_BAD_REQUEST),
        code=error.code,
    ) from error


@router.get("", response_model=PlatformApiKeyListResponse)
def get_platform_api_keys(
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_permission("platform_api_key.read")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeyListResponse:
    rows = list_platform_api_keys(db)
    names = _creator_names(db, rows)
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
        documentation=PlatformApiDocumentationResponse(
            swagger_path="/docs",
            redoc_path="/redoc",
            openapi_path="/openapi.json",
        ),
        scope_specs=_scope_specs(request),
        items=[
            _serialize_key(
                row,
                created_by_name=names.get(row.created_by_user_id or "", "-"),
            )
            for row in rows
        ],
    )


@router.post("", response_model=PlatformApiKeySecretResponse, status_code=status.HTTP_201_CREATED)
def post_platform_api_key(
    payload: PlatformApiKeyIssueRequest,
    response: Response,
    context: AuthContext = Depends(require_permission("platform_api_key.write")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeySecretResponse:
    try:
        issued = issue_platform_api_key(
            db,
            name=payload.name,
            scopes=payload.scopes,
            actor_user_id=context.user.id,
        )
    except PlatformApiKeyServiceError as error:
        _raise_key_error(db, error)
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
    return PlatformApiKeySecretResponse(
        item=_serialize_key(
            issued.row,
            created_by_name=context.user.display_name or context.user.full_name,
        ),
        api_key=issued.secret.get_secret_value(),
    )


@router.post("/{key_id}/reveal", response_model=PlatformApiKeySecretResponse)
def post_platform_api_key_reveal(
    key_id: str,
    response: Response,
    context: AuthContext = Depends(require_permission("platform_api_key.reveal")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeySecretResponse:
    try:
        secret = reveal_platform_api_key(db, key_id)
        row = db.get(PlatformApiKey, key_id)
        assert row is not None
    except PlatformApiKeyServiceError as error:
        _raise_key_error(db, error)
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
    names = _creator_names(db, [row])
    return PlatformApiKeySecretResponse(
        item=_serialize_key(
            row,
            created_by_name=names.get(row.created_by_user_id or "", "-"),
        ),
        api_key=secret.get_secret_value(),
    )


@router.post("/{key_id}/revoke", response_model=PlatformApiKeyItemResponse)
def post_platform_api_key_revoke(
    key_id: str,
    response: Response,
    context: AuthContext = Depends(require_permission("platform_api_key.write")),
    db: Session = Depends(get_db_session),
) -> PlatformApiKeyItemResponse:
    try:
        row = revoke_platform_api_key(
            db,
            key_id=key_id,
            actor_user_id=context.user.id,
        )
    except PlatformApiKeyServiceError as error:
        _raise_key_error(db, error)
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
    names = _creator_names(db, [row])
    return _serialize_key(
        row,
        created_by_name=names.get(row.created_by_user_id or "", "-"),
    )
