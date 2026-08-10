from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.dm import attachment_storage
from open_alm_api.domains.dm.models import DmMessageAttachment


class DmAttachmentPersistenceSession(Protocol):
    def add(self, row: DmMessageAttachment) -> None: ...
    def flush(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def refresh(self, row: DmMessageAttachment) -> None: ...


class DmAttachmentObjectStorage(Protocol):
    def put(
        self,
        *,
        storage_key: str,
        content: BinaryIO,
        size_bytes: int,
        content_type: str,
    ) -> None: ...

    def remove(self, *, storage_key: str) -> None: ...


@dataclass(frozen=True)
class DmAttachmentObjectWrite:
    storage_key: str
    content: BinaryIO
    size_bytes: int
    content_type: str


def persist_created_attachment(
    db: DmAttachmentPersistenceSession,
    *,
    row: DmMessageAttachment,
    object_write: DmAttachmentObjectWrite,
    object_storage: DmAttachmentObjectStorage | None = None,
) -> DmMessageAttachment:
    db.add(row)
    db.flush()
    storage = object_storage
    if storage is None:
        storage = attachment_storage.dm_attachment_storage()

    try:
        storage.put(
            storage_key=object_write.storage_key,
            content=object_write.content,
            size_bytes=object_write.size_bytes,
            content_type=object_write.content_type,
        )
    except Exception as exc:
        db.rollback()
        raise localized_http_exception(status_code=502, code="dm.attachment_upload_failed") from exc

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        _remove_uploaded_object(storage, storage_key=object_write.storage_key)
        raise localized_http_exception(status_code=500, code="dm.attachment_save_failed") from exc

    db.refresh(row)
    return row


def _remove_uploaded_object(
    storage: DmAttachmentObjectStorage,
    *,
    storage_key: str,
) -> None:
    try:
        storage.remove(storage_key=storage_key)
    except Exception:
        pass
