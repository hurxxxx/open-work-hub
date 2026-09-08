from __future__ import annotations

from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.content_access.contracts import ContentStream
from open_work_hub_api.domains.content_access.grants import ContentGrantClaims, InvalidContentGrant
from open_work_hub_api.domains.dm import (
    attachment_links,
    attachment_policy,
    attachment_records,
    attachment_storage,
)
from open_work_hub_api.domains.dm.attachment_links import DmAttachmentDisposition

DM_ATTACHMENT_PROXY_CHUNK_SIZE = 1024 * 1024
DM_ATTACHMENT_CONTENT_CACHE_CONTROL = "private, no-store"


def open_dm_attachment_content_grant(db: Session, *, claims: ContentGrantClaims) -> ContentStream:
    if (
        claims.resource_kind != "dm.attachment"
        or claims.owner_app_id != "dm"
        or claims.execution_context_kind != "personal"
        or claims.source_type != "dm_conversation"
    ):
        raise InvalidContentGrant("binding")
    user = db.get(User, claims.issuer_user_id)
    if user is None:
        raise InvalidContentGrant("principal")
    try:
        attachment = attachment_records.require_attachment_access(
            db,
            current_user=user,
            attachment_id=claims.resource_id,
        )
    except HTTPException as error:
        raise InvalidContentGrant("source_acl") from error
    if (
        claims.source_id != attachment.conversation_id
        or claims.object_identity != attachment_links.dm_attachment_object_identity(attachment)
        or claims.resource_version != attachment_links.dm_attachment_version(attachment)
    ):
        raise InvalidContentGrant("binding")
    if claims.disposition == "inline" and not attachment_policy.is_previewable_image_content_type(
        attachment.content_type
    ):
        raise InvalidContentGrant("disposition")
    try:
        body = attachment_storage.dm_attachment_storage().open_stream(
            storage_key=attachment.storage_key,
            chunk_size=DM_ATTACHMENT_PROXY_CHUNK_SIZE,
        )
    except Exception as error:
        raise localized_http_exception(
            status_code=502, code="dm.attachment_download_failed"
        ) from error
    return ContentStream(
        body=body,
        media_type=attachment.content_type or attachment_policy.DEFAULT_ATTACHMENT_CONTENT_TYPE,
        headers=dm_attachment_content_headers(
            filename=attachment.filename, disposition=claims.disposition
        ),
    )


def dm_attachment_content_headers(
    *, filename: str, disposition: DmAttachmentDisposition
) -> dict[str, str]:
    encoded_filename = quote(filename or "attachment", safe="")
    return {
        "Cache-Control": DM_ATTACHMENT_CONTENT_CACHE_CONTROL,
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}",
        "X-Content-Type-Options": "nosniff",
    }
