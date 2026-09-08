from __future__ import annotations

from dataclasses import dataclass
from tempfile import SpooledTemporaryFile
from typing import Protocol

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.dm import attachment_policy

DM_ATTACHMENT_UPLOAD_CHUNK_SIZE = 1024 * 1024
DM_ATTACHMENT_UPLOAD_SPOOL_MAX_SIZE = 16 * 1024 * 1024
DM_ATTACHMENT_MULTIPART_OVERHEAD_BYTES = 1024 * 1024


class AsyncAttachmentUploadReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class DmAttachmentUpload:
    content: SpooledTemporaryFile[bytes]
    size_bytes: int
    sniff_bytes: bytes


async def read_dm_attachment_upload(
    file: AsyncAttachmentUploadReader,
    *,
    content_length: str | None,
) -> DmAttachmentUpload:
    policy = attachment_policy.current_dm_attachment_policy()
    _validate_attachment_upload_content_length(content_length, policy=policy)
    buffer: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(
        max_size=DM_ATTACHMENT_UPLOAD_SPOOL_MAX_SIZE,
    )
    size_bytes = 0
    sniff_bytes = bytearray()
    try:
        while chunk := await file.read(DM_ATTACHMENT_UPLOAD_CHUNK_SIZE):
            size_bytes += len(chunk)
            _validate_attachment_upload_size(size_bytes, policy=policy)
            _append_attachment_sniff_prefix(
                sniff_bytes,
                chunk,
                limit_bytes=policy.sniff_bytes,
            )
            buffer.write(chunk)
        buffer.seek(0)
        return DmAttachmentUpload(
            content=buffer,
            size_bytes=size_bytes,
            sniff_bytes=bytes(sniff_bytes),
        )
    except Exception:
        buffer.close()
        raise


def _validate_attachment_upload_content_length(
    content_length: str | None,
    *,
    policy: attachment_policy.DmAttachmentPolicy,
) -> None:
    decision = _attachment_upload_content_length_decision(
        content_length,
        policy=policy,
    )
    if decision is not None and not decision.allowed:
        _raise_attachment_size_limit_exceeded(policy=policy)


def _attachment_upload_content_length_decision(
    content_length: str | None,
    *,
    policy: attachment_policy.DmAttachmentPolicy,
) -> attachment_policy.DmAttachmentRequestSizeDecision | None:
    if content_length is None:
        return None
    try:
        request_size = int(content_length)
    except ValueError:
        return None
    return policy.decide_request_size(
        request_size,
        overhead_bytes=DM_ATTACHMENT_MULTIPART_OVERHEAD_BYTES,
    )


def _validate_attachment_upload_size(
    size_bytes: int,
    *,
    policy: attachment_policy.DmAttachmentPolicy,
) -> None:
    decision = policy.decide_payload_size(size_bytes)
    if size_bytes > 0 and not decision.allowed:
        _raise_attachment_size_limit_exceeded(policy=policy)


def _append_attachment_sniff_prefix(
    sniff_bytes: bytearray,
    chunk: bytes,
    *,
    limit_bytes: int,
) -> None:
    if len(sniff_bytes) >= limit_bytes:
        return
    remaining = limit_bytes - len(sniff_bytes)
    sniff_bytes.extend(chunk[:remaining])


def _raise_attachment_size_limit_exceeded(
    *,
    policy: attachment_policy.DmAttachmentPolicy,
) -> None:
    raise localized_http_exception(
        status_code=413,
        code="dm.attachment_size_limit_exceeded",
        limit_mb=policy.size_limit_mb,
    )
