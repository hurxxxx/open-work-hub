from __future__ import annotations

from typing import Literal

from open_work_hub_api.domains.content_access.grants import (
    ContentGrantIssuer,
    build_content_grant_url,
    object_identity,
)
from open_work_hub_api.domains.dm import attachment_policy
from open_work_hub_api.domains.dm.models import DmMessageAttachment

DmAttachmentDisposition = Literal["attachment", "inline"]
DM_ATTACHMENT_CONTENT_EXPIRES_SECONDS = 5 * 60


def dm_attachment_object_identity(attachment: DmMessageAttachment) -> str:
    return object_identity(
        attachment.id,
        attachment.conversation_id,
        attachment.storage_key,
        attachment.filename,
        attachment.content_type,
        attachment.size_bytes,
    )


def dm_attachment_version(attachment: DmMessageAttachment) -> str:
    return object_identity(attachment.created_at, attachment.message_id)


def build_dm_attachment_content_url(
    attachment: DmMessageAttachment,
    *,
    issuer: ContentGrantIssuer,
    disposition: DmAttachmentDisposition,
    now: float | None = None,
    expires_seconds: int = DM_ATTACHMENT_CONTENT_EXPIRES_SECONDS,
) -> str:
    return build_content_grant_url(
        resource_kind="dm.attachment",
        resource_id=attachment.id,
        owner_app_id="dm",
        issuer=issuer,
        execution_context_kind="personal",
        route_id=None,
        source_type="dm_conversation",
        source_id=attachment.conversation_id,
        object_identity=dm_attachment_object_identity(attachment),
        resource_version=dm_attachment_version(attachment),
        disposition=disposition,
        expires_seconds=expires_seconds,
        now=now,
    )


def build_dm_attachment_download_url(
    attachment: DmMessageAttachment,
    *,
    issuer: ContentGrantIssuer,
) -> str:
    return build_dm_attachment_content_url(attachment, issuer=issuer, disposition="attachment")


def build_dm_attachment_preview_url(
    attachment: DmMessageAttachment,
    *,
    issuer: ContentGrantIssuer,
) -> str | None:
    if not attachment_policy.is_previewable_image_content_type(attachment.content_type):
        return None
    return build_dm_attachment_content_url(attachment, issuer=issuer, disposition="inline")
