from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import hmac
import time
from typing import Literal

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.dm import attachment_policy
from ai_do_api.domains.dm.models import DmMessageAttachment


DmAttachmentDisposition = Literal["attachment", "inline"]
DM_ATTACHMENT_PROXY_EXPIRES_SECONDS = 60 * 60


def _current_time() -> float:
    return time.time()


@dataclass(frozen=True)
class DmAttachmentContentSigningPayload:
    attachment_id: str
    conversation_id: str
    storage_key: str
    expires: int
    disposition: DmAttachmentDisposition

    @classmethod
    def from_attachment(
        cls,
        attachment: DmMessageAttachment,
        *,
        expires: int,
        disposition: DmAttachmentDisposition,
    ) -> DmAttachmentContentSigningPayload:
        return cls(
            attachment_id=attachment.id,
            conversation_id=attachment.conversation_id,
            storage_key=attachment.storage_key,
            expires=expires,
            disposition=disposition,
        )

    def encode(self) -> bytes:
        return (
            f"v1:{self.attachment_id}:{self.conversation_id}:{self.storage_key}:"
            f"{self.expires}:{self.disposition}"
        ).encode("utf-8")


@dataclass(frozen=True)
class DmAttachmentContentSigner:
    signing_key: str

    def signing_payload(
        self,
        attachment: DmMessageAttachment,
        *,
        expires: int,
        disposition: DmAttachmentDisposition,
    ) -> DmAttachmentContentSigningPayload:
        return DmAttachmentContentSigningPayload.from_attachment(
            attachment,
            expires=expires,
            disposition=disposition,
        )

    def sign(
        self,
        attachment: DmMessageAttachment,
        *,
        expires: int,
        disposition: DmAttachmentDisposition,
    ) -> str:
        payload = self.signing_payload(
            attachment,
            expires=expires,
            disposition=disposition,
        )
        return self.encode_signature(payload)

    def validate(
        self,
        attachment: DmMessageAttachment,
        *,
        expires: int,
        disposition: DmAttachmentDisposition,
        signature: str,
    ) -> bool:
        expected = self.sign(
            attachment,
            expires=expires,
            disposition=disposition,
        )
        return hmac.compare_digest(signature, expected)

    def encode_signature(self, payload: DmAttachmentContentSigningPayload) -> str:
        secret = self.signing_key.encode("utf-8")
        digest = hmac.new(secret, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class DmAttachmentContentUrlPolicy:
    disposition: DmAttachmentDisposition
    api_prefix: str
    expires_seconds: int = DM_ATTACHMENT_PROXY_EXPIRES_SECONDS
    time_source: Callable[[], float] = _current_time

    def current_timestamp(self) -> int:
        return int(self.time_source())

    def expires_at(self) -> int:
        return self.current_timestamp() + self.expires_seconds

    def is_expired(self, expires: int) -> bool:
        return expires < self.current_timestamp()

    def content_path(self, attachment: DmMessageAttachment) -> str:
        return f"{self.api_prefix}/dm/attachments/{attachment.id}/content"

    def build_url(
        self,
        attachment: DmMessageAttachment,
        *,
        signer: DmAttachmentContentSigner,
    ) -> str:
        expires = self.expires_at()
        signature = signer.sign(
            attachment,
            expires=expires,
            disposition=self.disposition,
        )
        return (
            f"{self.content_path(attachment)}"
            f"?expires={expires}&signature={signature}&disposition={self.disposition}"
        )


def current_dm_attachment_content_signer() -> DmAttachmentContentSigner:
    return DmAttachmentContentSigner(
        signing_key=get_settings().dm_attachment_signing_key,
    )


def current_dm_attachment_content_url_policy(
    *,
    disposition: DmAttachmentDisposition,
) -> DmAttachmentContentUrlPolicy:
    return DmAttachmentContentUrlPolicy(
        disposition=disposition,
        api_prefix=get_settings().api_prefix,
    )


def build_dm_attachment_download_url(attachment: DmMessageAttachment) -> str:
    return build_dm_attachment_content_url(attachment, disposition="attachment")


def build_dm_attachment_preview_url(attachment: DmMessageAttachment) -> str | None:
    if not attachment_policy.is_previewable_image_content_type(attachment.content_type):
        return None
    return build_dm_attachment_content_url(attachment, disposition="inline")


def build_dm_attachment_content_url(
    attachment: DmMessageAttachment,
    *,
    disposition: DmAttachmentDisposition,
) -> str:
    policy = current_dm_attachment_content_url_policy(
        disposition=disposition,
    )
    return policy.build_url(
        attachment,
        signer=current_dm_attachment_content_signer(),
    )


def validate_dm_attachment_content_signature(
    attachment: DmMessageAttachment,
    *,
    expires: int,
    disposition: DmAttachmentDisposition,
    signature: str,
) -> bool:
    policy = current_dm_attachment_content_url_policy(
        disposition=disposition,
    )
    if policy.is_expired(expires):
        return False

    return current_dm_attachment_content_signer().validate(
        attachment,
        expires=expires,
        disposition=disposition,
        signature=signature,
    )


def _sign_dm_attachment_content_url(
    attachment: DmMessageAttachment,
    *,
    expires: int,
    disposition: DmAttachmentDisposition,
) -> str:
    return current_dm_attachment_content_signer().sign(
        attachment,
        expires=expires,
        disposition=disposition,
    )
