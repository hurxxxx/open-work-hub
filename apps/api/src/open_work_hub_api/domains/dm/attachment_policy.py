from __future__ import annotations

from dataclasses import dataclass
import re


DM_MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024
DM_ATTACHMENT_SNIFF_BYTES = 512
DEFAULT_ATTACHMENT_CONTENT_TYPE = "application/octet-stream"
PREVIEWABLE_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)

_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"|?*/\\]+')
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:+")
_CONTENT_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$")


@dataclass(frozen=True)
class DmAttachmentPayloadSizeDecision:
    size_bytes: int
    max_size_bytes: int
    allowed: bool


@dataclass(frozen=True)
class DmAttachmentRequestSizeDecision:
    request_size_bytes: int
    overhead_bytes: int
    max_size_bytes: int
    allowed: bool

    @property
    def request_limit_bytes(self) -> int:
        return self.max_size_bytes + self.overhead_bytes


@dataclass(frozen=True)
class DmAttachmentUploadDecision:
    filename: str
    declared_content_type: str
    sniffed_content_type: str | None
    content_type: str
    is_previewable_image: bool
    downgraded_untrusted_declared_image: bool


@dataclass(frozen=True)
class PreparedDmAttachment:
    filename: str
    content_type: str
    is_previewable_image: bool


@dataclass(frozen=True)
class DmAttachmentPolicy:
    max_size_bytes: int
    sniff_bytes: int
    default_content_type: str
    previewable_image_content_types: frozenset[str]

    @property
    def size_limit_mb(self) -> int:
        return self.max_size_bytes // (1024 * 1024)

    def decide_payload_size(self, size_bytes: int) -> DmAttachmentPayloadSizeDecision:
        return DmAttachmentPayloadSizeDecision(
            size_bytes=size_bytes,
            max_size_bytes=self.max_size_bytes,
            allowed=0 < size_bytes <= self.max_size_bytes,
        )

    def decide_request_size(
        self,
        request_size: int,
        *,
        overhead_bytes: int,
    ) -> DmAttachmentRequestSizeDecision:
        return DmAttachmentRequestSizeDecision(
            request_size_bytes=request_size,
            overhead_bytes=overhead_bytes,
            max_size_bytes=self.max_size_bytes,
            allowed=request_size <= self.max_size_bytes + overhead_bytes,
        )

    def prepare_upload_decision(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        sniff_bytes: bytes,
    ) -> DmAttachmentUploadDecision:
        normalized_content_type = self.normalize_content_type(content_type)
        sniffed_content_type = self.sniff_content_type(sniff_bytes)
        trusted_content_type = sniffed_content_type or normalized_content_type
        downgraded_untrusted_declared_image = (
            self.is_declared_image_content_type(normalized_content_type)
            and sniffed_content_type is None
        )

        if downgraded_untrusted_declared_image:
            trusted_content_type = self.default_content_type

        return DmAttachmentUploadDecision(
            filename=self.safe_filename(filename),
            declared_content_type=normalized_content_type,
            sniffed_content_type=sniffed_content_type,
            content_type=trusted_content_type,
            is_previewable_image=self.is_previewable_image_content_type(trusted_content_type),
            downgraded_untrusted_declared_image=downgraded_untrusted_declared_image,
        )

    def prepare_upload(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        sniff_bytes: bytes,
    ) -> PreparedDmAttachment:
        decision = self.prepare_upload_decision(
            filename=filename,
            content_type=content_type,
            sniff_bytes=sniff_bytes,
        )
        return PreparedDmAttachment(
            filename=decision.filename,
            content_type=decision.content_type,
            is_previewable_image=decision.is_previewable_image,
        )

    def safe_filename(self, value: str | None) -> str:
        raw = str(value or "unnamed").strip()
        raw = raw.replace("\\", "/")
        filename = raw.rsplit("/", 1)[-1].strip()
        filename = _WINDOWS_DRIVE_PREFIX.sub("", filename).strip()
        filename = _UNSAFE_FILENAME_CHARS.sub("_", filename).strip(" .")
        if not filename or filename in {".", ".."}:
            return "unnamed"
        return filename[:512]

    def normalize_content_type(self, value: str | None) -> str:
        content_type = (value or "").split(";", 1)[0].strip().lower()
        if not content_type or not _CONTENT_TYPE.fullmatch(content_type):
            return self.default_content_type
        return content_type

    def sniff_content_type(self, prefix: bytes) -> str | None:
        if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if prefix.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if prefix.startswith((b"GIF87a", b"GIF89a")):
            return "image/gif"
        if len(prefix) >= 12 and prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP":
            return "image/webp"
        return None

    def is_previewable_image_content_type(self, content_type: str | None) -> bool:
        return self.normalize_content_type(content_type) in self.previewable_image_content_types

    def is_declared_image_content_type(self, content_type: str) -> bool:
        return content_type.startswith("image/")


def current_dm_attachment_policy() -> DmAttachmentPolicy:
    return DmAttachmentPolicy(
        max_size_bytes=DM_MAX_ATTACHMENT_SIZE,
        sniff_bytes=DM_ATTACHMENT_SNIFF_BYTES,
        default_content_type=DEFAULT_ATTACHMENT_CONTENT_TYPE,
        previewable_image_content_types=PREVIEWABLE_IMAGE_CONTENT_TYPES,
    )


def dm_attachment_size_limit_mb() -> int:
    return current_dm_attachment_policy().size_limit_mb


def decide_dm_attachment_size(size_bytes: int) -> DmAttachmentPayloadSizeDecision:
    return current_dm_attachment_policy().decide_payload_size(size_bytes)


def is_dm_attachment_size_allowed(size_bytes: int) -> bool:
    return decide_dm_attachment_size(size_bytes).allowed


def decide_dm_attachment_request_size(
    request_size: int,
    *,
    overhead_bytes: int,
) -> DmAttachmentRequestSizeDecision:
    return current_dm_attachment_policy().decide_request_size(
        request_size,
        overhead_bytes=overhead_bytes,
    )


def is_dm_attachment_request_size_allowed(
    request_size: int,
    *,
    overhead_bytes: int,
) -> bool:
    return decide_dm_attachment_request_size(
        request_size,
        overhead_bytes=overhead_bytes,
    ).allowed


def decide_dm_attachment_upload(
    *,
    filename: str | None,
    content_type: str | None,
    sniff_bytes: bytes,
) -> DmAttachmentUploadDecision:
    return current_dm_attachment_policy().prepare_upload_decision(
        filename=filename,
        content_type=content_type,
        sniff_bytes=sniff_bytes,
    )


def prepare_attachment_upload(
    *,
    filename: str | None,
    content_type: str | None,
    sniff_bytes: bytes,
) -> PreparedDmAttachment:
    return current_dm_attachment_policy().prepare_upload(
        filename=filename,
        content_type=content_type,
        sniff_bytes=sniff_bytes,
    )


def safe_attachment_filename(value: str | None) -> str:
    return current_dm_attachment_policy().safe_filename(value)


def normalize_attachment_content_type(value: str | None) -> str:
    return current_dm_attachment_policy().normalize_content_type(value)


def sniff_attachment_content_type(prefix: bytes) -> str | None:
    return current_dm_attachment_policy().sniff_content_type(prefix)


def is_previewable_image_content_type(content_type: str | None) -> bool:
    return current_dm_attachment_policy().is_previewable_image_content_type(content_type)


def _is_declared_image_content_type(content_type: str) -> bool:
    return current_dm_attachment_policy().is_declared_image_content_type(content_type)
