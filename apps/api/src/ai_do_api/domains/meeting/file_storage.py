from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
from typing import Protocol

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import get_minio_client


DEFAULT_ATTACHMENT_CONTENT_TYPE = "application/octet-stream"


class MeetingAttachmentStorageObject(Protocol):
    def stream(self, chunk_size: int) -> Iterable[bytes]: ...
    def close(self) -> None: ...
    def release_conn(self) -> None: ...


def attachment_storage_key(*, meeting_id: str, attachment_id: str, filename: str) -> str:
    return f"meeting/{meeting_id}/{attachment_id}/{filename or 'unnamed'}"


def put_attachment_object(*, storage_key: str, data: bytes, content_type: str | None) -> None:
    get_minio_client().put_object(
        get_settings().minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type or DEFAULT_ATTACHMENT_CONTENT_TYPE,
    )


def remove_attachment_object(storage_key: str) -> None:
    get_minio_client().remove_object(get_settings().minio_bucket, storage_key)


def open_attachment_object(*, storage_key: str, chunk_size: int) -> Iterable[bytes]:
    obj = get_minio_client().get_object(get_settings().minio_bucket, storage_key)
    try:
        yield from obj.stream(chunk_size)
    finally:
        try:
            obj.close()
        finally:
            obj.release_conn()
