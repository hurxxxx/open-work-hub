from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import (
    bearer_scheme,
    resolve_auth_context_from_token,
)
from open_work_hub_api.domains.content_access.contracts import ContentStream
from open_work_hub_api.domains.content_access.grants import (
    ContentGrantClaims,
    InvalidContentGrant,
    decode_content_grant,
    require_matching_issuer,
)

router = APIRouter(tags=["content"])


class ContentStreamingResponse(StreamingResponse):
    media_type = "application/octet-stream"


def _open_content(db: Session, claims: ContentGrantClaims) -> ContentStream:
    if claims.resource_kind == "files.file":
        from open_work_hub_api.domains.files.content_access import open_file_content_grant

        return open_file_content_grant(db, claims=claims)
    if claims.resource_kind == "pms.attachment":
        from open_work_hub_api.domains.pms.attachments import open_task_attachment_content_grant

        return open_task_attachment_content_grant(db, claims=claims)
    if claims.resource_kind == "meeting.attachment":
        from open_work_hub_api.domains.meeting.service import open_file_attachment_content_grant

        return open_file_attachment_content_grant(db, claims=claims)
    if claims.resource_kind == "dm.attachment":
        from open_work_hub_api.domains.dm.attachment_content import open_dm_attachment_content_grant

        return open_dm_attachment_content_grant(db, claims=claims)
    if claims.resource_kind == "media.file":
        from open_work_hub_api.domains.media.content_access import open_media_content_grant

        return open_media_content_grant(db, claims=claims)
    raise InvalidContentGrant("resource_kind")


@router.get(
    "/content",
    response_class=ContentStreamingResponse,
    responses={
        403: {
            "description": "Content capability denied.",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                }
            },
        },
    },
)
def proxy_content(
    request: Request,
    grant: str | None = Header(
        default=None,
        alias="X-Open-Work-Hub-Content-Grant",
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> StreamingResponse:
    try:
        if not grant:
            raise InvalidContentGrant("missing")
        claims = decode_content_grant(grant)
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise InvalidContentGrant("issuer")
        try:
            auth = resolve_auth_context_from_token(db, credentials.credentials)
        except HTTPException as error:
            raise InvalidContentGrant("issuer") from error
        require_matching_issuer(
            claims,
            current_user_id=auth.user.id,
            current_session_id=auth.session.id,
        )
        request.state.auth_context = auth
        content = _open_content(db, claims)
    except InvalidContentGrant as error:
        raise localized_http_exception(
            status_code=403,
            code="content.grant_invalid",
        ) from error
    return ContentStreamingResponse(
        content.body,
        media_type=content.media_type,
        headers={
            **content.headers,
            "Referrer-Policy": "no-referrer",
        },
    )


__all__ = ["ContentStream", "router"]
