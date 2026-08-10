from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import quote

from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.dm import attachment_links, attachment_policy, attachment_storage
from open_work_hub_api.domains.dm.attachment_links import DmAttachmentDisposition
from open_work_hub_api.domains.dm.models import DmMessageAttachment


DM_ATTACHMENT_PROXY_CHUNK_SIZE = 1024 * 1024
DM_ATTACHMENT_CONTENT_CACHE_CONTROL = "private, max-age=300"


@dataclass(frozen=True)
class DmAttachmentContent:
    body: Iterable[bytes]
    media_type: str
    headers: dict[str, str]


@dataclass(frozen=True)
class DmAttachmentContentRequest:
    attachment: DmMessageAttachment
    expires: int
    signature: str
    disposition: DmAttachmentDisposition


@dataclass(frozen=True)
class DmAttachmentContentAccessPolicy:
    chunk_size: int = DM_ATTACHMENT_PROXY_CHUNK_SIZE

    def validate_request(self, request: DmAttachmentContentRequest) -> None:
        if (
            request.disposition == "inline"
            and not attachment_policy.is_previewable_image_content_type(
                request.attachment.content_type
            )
        ):
            raise localized_http_exception(
                status_code=415,
                code="dm.attachment_preview_unsupported",
            )
        if not attachment_links.validate_dm_attachment_content_signature(
            request.attachment,
            expires=request.expires,
            disposition=request.disposition,
            signature=request.signature,
        ):
            raise localized_http_exception(
                status_code=403,
                code="dm.attachment_proxy_url_invalid",
            )

    def open_stream(self, attachment: DmMessageAttachment) -> Iterable[bytes]:
        try:
            return attachment_storage.dm_attachment_storage().open_stream(
                storage_key=attachment.storage_key,
                chunk_size=self.chunk_size,
            )
        except Exception as exc:
            raise localized_http_exception(
                status_code=502,
                code="dm.attachment_download_failed",
            ) from exc


@dataclass(frozen=True)
class DmAttachmentContentResponseBuilder:
    cache_control: str = DM_ATTACHMENT_CONTENT_CACHE_CONTROL

    def build(
        self,
        *,
        attachment: DmMessageAttachment,
        body: Iterable[bytes],
        disposition: DmAttachmentDisposition,
    ) -> DmAttachmentContent:
        return DmAttachmentContent(
            body=body,
            media_type=(
                attachment.content_type or attachment_policy.DEFAULT_ATTACHMENT_CONTENT_TYPE
            ),
            headers=self.headers(
                filename=attachment.filename,
                disposition=disposition,
            ),
        )

    def headers(
        self,
        *,
        filename: str,
        disposition: DmAttachmentDisposition,
    ) -> dict[str, str]:
        encoded_filename = quote(filename or "attachment", safe="")
        return {
            "Cache-Control": self.cache_control,
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        }


def _dm_attachment_content_access_policy() -> DmAttachmentContentAccessPolicy:
    return DmAttachmentContentAccessPolicy(chunk_size=DM_ATTACHMENT_PROXY_CHUNK_SIZE)


def _dm_attachment_content_response_builder() -> DmAttachmentContentResponseBuilder:
    return DmAttachmentContentResponseBuilder(
        cache_control=DM_ATTACHMENT_CONTENT_CACHE_CONTROL,
    )


def open_dm_attachment_content(
    db: Session,
    *,
    attachment_id: str,
    expires: int,
    signature: str,
    disposition: DmAttachmentDisposition,
) -> DmAttachmentContent:
    attachment = db.get(DmMessageAttachment, attachment_id)
    if attachment is None:
        raise localized_http_exception(status_code=404, code="dm.attachment_not_found")

    request = DmAttachmentContentRequest(
        attachment=attachment,
        expires=expires,
        signature=signature,
        disposition=disposition,
    )
    policy = _dm_attachment_content_access_policy()
    policy.validate_request(request)
    body = policy.open_stream(attachment)
    return _dm_attachment_content_response_builder().build(
        attachment=attachment,
        body=body,
        disposition=disposition,
    )


def validate_dm_attachment_content_request(
    attachment: DmMessageAttachment,
    *,
    expires: int,
    signature: str,
    disposition: DmAttachmentDisposition,
) -> None:
    _dm_attachment_content_access_policy().validate_request(
        DmAttachmentContentRequest(
            attachment=attachment,
            expires=expires,
            signature=signature,
            disposition=disposition,
        )
    )


def dm_attachment_content_headers(
    *,
    filename: str,
    disposition: DmAttachmentDisposition,
) -> dict[str, str]:
    return _dm_attachment_content_response_builder().headers(
        filename=filename,
        disposition=disposition,
    )
