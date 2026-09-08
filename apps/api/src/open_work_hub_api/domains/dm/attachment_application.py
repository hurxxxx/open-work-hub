from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer
from open_work_hub_api.domains.dm import (
    attachment_records,
    attachment_upload,
    serialization,
)
from open_work_hub_api.domains.dm.schemas import DmAttachmentUrlResponse, DmMessageAttachmentItem


class DmAttachmentUploadFile(attachment_upload.AsyncAttachmentUploadReader, Protocol):
    filename: str | None
    content_type: str | None


def get_dm_attachment_download_url(
    db: Session,
    *,
    current_user: User,
    attachment_id: str,
    issuer: ContentGrantIssuer,
) -> DmAttachmentUrlResponse:
    return DmAttachmentUrlResponse(
        url=attachment_records.attachment_download_url(
            db,
            current_user=current_user,
            attachment_id=attachment_id,
            issuer=issuer,
        )
    )


def get_dm_attachment_preview_url(
    db: Session,
    *,
    current_user: User,
    attachment_id: str,
    issuer: ContentGrantIssuer,
) -> DmAttachmentUrlResponse:
    return DmAttachmentUrlResponse(
        url=attachment_records.attachment_preview_url(
            db,
            current_user=current_user,
            attachment_id=attachment_id,
            issuer=issuer,
        )
    )


async def upload_dm_attachment(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    file: DmAttachmentUploadFile,
    content_length: str | None,
) -> DmMessageAttachmentItem:
    upload = await attachment_upload.read_dm_attachment_upload(
        file,
        content_length=content_length,
    )
    try:
        row = attachment_records.create_attachment(
            db,
            current_user=current_user,
            conversation_id=conversation_id,
            filename=file.filename,
            content_type=file.content_type,
            content=upload.content,
            size_bytes=upload.size_bytes,
            sniff_bytes=upload.sniff_bytes,
        )
        return serialization.serialize_attachment(row)
    finally:
        upload.content.close()
