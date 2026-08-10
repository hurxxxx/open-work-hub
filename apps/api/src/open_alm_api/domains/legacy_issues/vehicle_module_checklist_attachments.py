from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import logging
import re
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Protocol
from urllib.parse import quote

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import get_settings
from open_alm_api.core.storage import ensure_bucket, get_minio_client
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.legacy_issues.dataset_records import COMMON_MASTER_DATASET_KEY
from open_alm_api.domains.legacy_issues.history import add_attachment_history_entry
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleModuleChecklistAttachment,
    LegacyIssueVehicleModuleChecklistAttachmentCleanup,
    LegacyIssueVehicleModuleChecklistRecord,
)
from open_alm_api.domains.legacy_issues.vehicle_checklists import (
    VEHICLE_CHECKLIST_STATUS_DRAFT,
)


logger = logging.getLogger(__name__)

VEHICLE_MODULE_CHECKLIST_ATTACHMENT_MAX_BYTES = 1024 * 1024 * 1024
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_CHUNK_SIZE = 1024 * 1024
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_SPOOL_MAX_BYTES = 16 * 1024 * 1024
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_RECORD_KIND = "legacy_issue_module_checklist"
DEFAULT_ATTACHMENT_CONTENT_TYPE = "application/octet-stream"

_UNSAFE_FILENAME_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"|?*/\\]+')
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:+")
_CONTENT_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$")


class VehicleModuleChecklistAttachmentUploadFile(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


class VehicleModuleChecklistAttachmentStorageObject(Protocol):
    def stream(self, chunk_size: int) -> Iterable[bytes]: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class VehicleModuleChecklistAttachmentStorageClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        *,
        length: int,
        content_type: str,
    ) -> None: ...

    def get_object(
        self,
        bucket_name: str,
        object_name: str,
    ) -> VehicleModuleChecklistAttachmentStorageObject: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...


@dataclass(frozen=True)
class VehicleModuleChecklistAttachmentUpload:
    content: SpooledTemporaryFile[bytes]
    filename: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class VehicleModuleChecklistAttachmentContent:
    body: Iterable[bytes]
    media_type: str
    headers: dict[str, str]


@dataclass(frozen=True)
class VehicleModuleChecklistAttachmentCleanupRef:
    id: str
    storage_key: str


@dataclass(frozen=True)
class VehicleModuleChecklistAttachmentStorage:
    bucket_name: str
    client: VehicleModuleChecklistAttachmentStorageClient

    def put(
        self,
        *,
        storage_key: str,
        content: BinaryIO,
        size_bytes: int,
        content_type: str,
    ) -> None:
        content.seek(0)
        self.client.put_object(
            self.bucket_name,
            storage_key,
            content,
            length=size_bytes,
            content_type=content_type,
        )

    def open_stream(self, *, storage_key: str) -> Iterable[bytes]:
        storage_object = self.client.get_object(self.bucket_name, storage_key)
        return _stream_storage_object(storage_object)

    def remove(self, *, storage_key: str) -> None:
        self.client.remove_object(self.bucket_name, storage_key)


def vehicle_module_checklist_attachment_storage() -> VehicleModuleChecklistAttachmentStorage:
    settings = get_settings()
    return VehicleModuleChecklistAttachmentStorage(
        bucket_name=settings.minio_bucket,
        client=get_minio_client(),
    )


async def read_vehicle_module_checklist_attachment_upload(
    file: VehicleModuleChecklistAttachmentUploadFile,
) -> VehicleModuleChecklistAttachmentUpload:
    content: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(
        max_size=VEHICLE_MODULE_CHECKLIST_ATTACHMENT_SPOOL_MAX_BYTES,
    )
    size_bytes = 0
    try:
        while chunk := await file.read(VEHICLE_MODULE_CHECKLIST_ATTACHMENT_CHUNK_SIZE):
            size_bytes += len(chunk)
            if size_bytes > VEHICLE_MODULE_CHECKLIST_ATTACHMENT_MAX_BYTES:
                raise localized_http_exception(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    code="legacy_issues.vehicle_module_checklist_attachment_too_large",
                )
            content.write(chunk)
        if size_bytes == 0:
            raise localized_http_exception(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="legacy_issues.vehicle_module_checklist_attachment_empty",
            )
        content.seek(0)
        return VehicleModuleChecklistAttachmentUpload(
            content=content,
            filename=safe_attachment_filename(file.filename),
            content_type=normalize_attachment_content_type(file.content_type),
            size_bytes=size_bytes,
        )
    except Exception:
        content.close()
        raise


def list_vehicle_module_checklist_attachments_for_records(
    db: Session,
    *,
    workspace: Workspace,
    checklist: LegacyIssueVehicleModuleChecklist,
    record_ids: Iterable[str],
) -> dict[str, list[LegacyIssueVehicleModuleChecklistAttachment]]:
    scoped_record_ids = tuple(dict.fromkeys(item for item in record_ids if item))
    if not scoped_record_ids:
        return {}
    rows = list(
        db.scalars(
            select(LegacyIssueVehicleModuleChecklistAttachment)
            .where(
                LegacyIssueVehicleModuleChecklistAttachment.workspace_id == workspace.id,
                LegacyIssueVehicleModuleChecklistAttachment.checklist_id == checklist.id,
                LegacyIssueVehicleModuleChecklistAttachment.record_id.in_(scoped_record_ids),
            )
            .order_by(
                LegacyIssueVehicleModuleChecklistAttachment.record_id.asc(),
                LegacyIssueVehicleModuleChecklistAttachment.created_at.desc(),
            )
        )
    )
    grouped: dict[str, list[LegacyIssueVehicleModuleChecklistAttachment]] = {}
    for row in rows:
        grouped.setdefault(row.record_id, []).append(row)
    return grouped


def upload_vehicle_module_checklist_attachment(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    checklist: LegacyIssueVehicleModuleChecklist,
    record_id: str,
    upload: VehicleModuleChecklistAttachmentUpload,
) -> LegacyIssueVehicleModuleChecklistAttachment:
    _require_draft_checklist(checklist)
    record = _get_checklist_record(
        db,
        workspace=workspace,
        checklist=checklist,
        record_id=record_id,
    )
    attachment_id = new_id()
    storage_key = (
        "legacy-issues/vehicle-module-checklists/"
        f"{workspace.id}/{checklist.id}/{record.id}/{attachment_id}/{upload.filename}"
    )
    storage = vehicle_module_checklist_attachment_storage()
    try:
        ensure_bucket()
        storage.put(
            storage_key=storage_key,
            content=upload.content,
            size_bytes=upload.size_bytes,
            content_type=upload.content_type,
        )
    except Exception as error:
        _remove_uploaded_object_best_effort(storage, storage_key=storage_key)
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="legacy_issues.vehicle_module_checklist_attachment_upload_failed",
        ) from error

    try:
        row = LegacyIssueVehicleModuleChecklistAttachment(
            id=attachment_id,
            workspace_id=workspace.id,
            checklist_id=checklist.id,
            record_id=record.id,
            filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=upload.size_bytes,
            storage_key=storage_key,
            uploaded_by_id=user.id,
            created_at=utcnow_naive(),
        )
        db.add(row)
        add_attachment_history_entry(
            db,
            workspace=workspace,
            user=user,
            record_kind=VEHICLE_MODULE_CHECKLIST_ATTACHMENT_RECORD_KIND,
            dataset_key=COMMON_MASTER_DATASET_KEY,
            record_id=record.id,
            action="attachment_upload",
            field_label="첨부파일",
            old_value=None,
            new_value=row.filename,
            details=_history_details(checklist=checklist, attachment=row),
        )
        db.flush()
    except Exception:
        _remove_uploaded_object_best_effort(storage, storage_key=storage_key)
        raise
    db.refresh(row)
    return row


def get_vehicle_module_checklist_attachment(
    db: Session,
    *,
    workspace: Workspace,
    checklist: LegacyIssueVehicleModuleChecklist,
    attachment_id: str,
) -> LegacyIssueVehicleModuleChecklistAttachment:
    row = db.scalar(
        select(LegacyIssueVehicleModuleChecklistAttachment).where(
            LegacyIssueVehicleModuleChecklistAttachment.id == attachment_id,
            LegacyIssueVehicleModuleChecklistAttachment.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklistAttachment.checklist_id == checklist.id,
        )
    )
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_module_checklist_attachment_not_found",
        )
    return row


def open_vehicle_module_checklist_attachment(
    db: Session,
    *,
    workspace: Workspace,
    checklist: LegacyIssueVehicleModuleChecklist,
    attachment_id: str,
) -> VehicleModuleChecklistAttachmentContent:
    row = get_vehicle_module_checklist_attachment(
        db,
        workspace=workspace,
        checklist=checklist,
        attachment_id=attachment_id,
    )
    try:
        body = vehicle_module_checklist_attachment_storage().open_stream(
            storage_key=row.storage_key
        )
    except Exception as error:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.vehicle_module_checklist_attachment_download_failed",
        ) from error
    encoded_filename = quote(row.filename or "attachment", safe="")
    return VehicleModuleChecklistAttachmentContent(
        body=body,
        media_type=row.content_type or DEFAULT_ATTACHMENT_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def delete_vehicle_module_checklist_attachment(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    checklist: LegacyIssueVehicleModuleChecklist,
    attachment_id: str,
) -> VehicleModuleChecklistAttachmentCleanupRef:
    _require_draft_checklist(checklist)
    row = get_vehicle_module_checklist_attachment(
        db,
        workspace=workspace,
        checklist=checklist,
        attachment_id=attachment_id,
    )
    cleanup = _queue_attachment_cleanup(
        db,
        workspace=workspace,
        storage_key=row.storage_key,
    )
    add_attachment_history_entry(
        db,
        workspace=workspace,
        user=user,
        record_kind=VEHICLE_MODULE_CHECKLIST_ATTACHMENT_RECORD_KIND,
        dataset_key=COMMON_MASTER_DATASET_KEY,
        record_id=row.record_id,
        action="attachment_delete",
        field_label="첨부파일",
        old_value=row.filename,
        new_value=None,
        details=_history_details(checklist=checklist, attachment=row),
    )
    db.delete(row)
    db.flush()
    return cleanup


def delete_vehicle_module_checklist_attachment_rows(
    db: Session,
    *,
    workspace: Workspace,
    checklist: LegacyIssueVehicleModuleChecklist,
) -> list[VehicleModuleChecklistAttachmentCleanupRef]:
    rows = list(
        db.scalars(
            select(LegacyIssueVehicleModuleChecklistAttachment).where(
                LegacyIssueVehicleModuleChecklistAttachment.workspace_id == workspace.id,
                LegacyIssueVehicleModuleChecklistAttachment.checklist_id == checklist.id,
            )
        )
    )
    cleanups = [
        _queue_attachment_cleanup(
            db,
            workspace=workspace,
            storage_key=row.storage_key,
        )
        for row in rows
    ]
    db.execute(
        delete(LegacyIssueVehicleModuleChecklistAttachment).where(
            LegacyIssueVehicleModuleChecklistAttachment.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklistAttachment.checklist_id == checklist.id,
        )
    )
    return cleanups


def process_pending_vehicle_module_checklist_attachment_cleanups(
    db: Session,
    *,
    workspace: Workspace,
    limit: int = 100,
) -> tuple[int, int]:
    """Best-effort committed outbox processing; failures stay durable for retry."""

    try:
        return _process_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            workspace_id=workspace.id,
            limit=limit,
        )
    except Exception:  # pragma: no cover - cleanup must not fail the logical delete
        db.rollback()
        logger.exception(
            "Failed to persist vehicle module checklist attachment cleanup progress",
            extra={"workspace_id": workspace.id},
        )
        return 0, 1


def process_all_pending_vehicle_module_checklist_attachment_cleanups(
    db: Session,
    *,
    limit: int = 1000,
    storage: VehicleModuleChecklistAttachmentStorage | None = None,
) -> tuple[int, int]:
    """Drain cleanup rows across workspaces for the periodic worker."""

    try:
        return _process_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            workspace_id=None,
            limit=limit,
            storage=storage,
        )
    except Exception:  # pragma: no cover - periodic task retries on its next run
        db.rollback()
        logger.exception(
            "Failed to persist periodic vehicle module checklist attachment cleanup progress"
        )
        return 0, 1


def _process_pending_vehicle_module_checklist_attachment_cleanups(
    db: Session,
    *,
    workspace_id: str | None,
    limit: int,
    storage: VehicleModuleChecklistAttachmentStorage | None = None,
) -> tuple[int, int]:
    statement = select(LegacyIssueVehicleModuleChecklistAttachmentCleanup)
    if workspace_id is not None:
        statement = statement.where(
            LegacyIssueVehicleModuleChecklistAttachmentCleanup.workspace_id == workspace_id
        )
    rows = list(
        db.scalars(
            statement.order_by(LegacyIssueVehicleModuleChecklistAttachmentCleanup.created_at.asc())
            .limit(max(1, limit))
            .with_for_update(skip_locked=True)
        )
    )
    if not rows:
        return 0, 0
    active_storage = storage or vehicle_module_checklist_attachment_storage()
    removed_ids: list[str] = []
    failed = 0
    now = utcnow_naive()
    for row in rows:
        try:
            active_storage.remove(storage_key=row.storage_key)
        except Exception as error:  # pragma: no cover - defensive object-store wrapper
            failed += 1
            row.attempt_count += 1
            row.last_error = type(error).__name__[:160]
            row.last_attempted_at = now
            db.add(row)
            logger.exception(
                "Failed to process vehicle module checklist attachment cleanup",
                extra={"cleanup_id": row.id},
            )
        else:
            removed_ids.append(row.id)
    if removed_ids:
        db.execute(
            delete(LegacyIssueVehicleModuleChecklistAttachmentCleanup).where(
                LegacyIssueVehicleModuleChecklistAttachmentCleanup.id.in_(removed_ids),
            )
        )
    db.commit()
    return len(removed_ids), failed


def remove_uploaded_vehicle_module_checklist_attachment(storage_key: str) -> None:
    storage = vehicle_module_checklist_attachment_storage()
    _remove_uploaded_object_best_effort(storage, storage_key=storage_key)


def _queue_attachment_cleanup(
    db: Session,
    *,
    workspace: Workspace,
    storage_key: str,
) -> VehicleModuleChecklistAttachmentCleanupRef:
    cleanup = LegacyIssueVehicleModuleChecklistAttachmentCleanup(
        id=new_id(),
        workspace_id=workspace.id,
        storage_key=storage_key,
        created_at=utcnow_naive(),
    )
    db.add(cleanup)
    return VehicleModuleChecklistAttachmentCleanupRef(
        id=cleanup.id,
        storage_key=cleanup.storage_key,
    )


def safe_attachment_filename(value: str | None) -> str:
    raw = str(value or "unnamed").strip().replace("\\", "/")
    filename = raw.rsplit("/", 1)[-1].strip()
    filename = _WINDOWS_DRIVE_PREFIX.sub("", filename).strip()
    filename = _UNSAFE_FILENAME_CHARS.sub("_", filename).strip(" .")
    if not filename or filename in {".", ".."}:
        return "unnamed"
    return filename[:512]


def normalize_attachment_content_type(value: str | None) -> str:
    content_type = (value or "").split(";", 1)[0].strip().lower()
    if not content_type or not _CONTENT_TYPE.fullmatch(content_type):
        return DEFAULT_ATTACHMENT_CONTENT_TYPE
    return content_type[:160]


def _get_checklist_record(
    db: Session,
    *,
    workspace: Workspace,
    checklist: LegacyIssueVehicleModuleChecklist,
    record_id: str,
) -> LegacyIssueVehicleModuleChecklistRecord:
    record = db.scalar(
        select(LegacyIssueVehicleModuleChecklistRecord).where(
            LegacyIssueVehicleModuleChecklistRecord.id == record_id,
            LegacyIssueVehicleModuleChecklistRecord.workspace_id == workspace.id,
            LegacyIssueVehicleModuleChecklistRecord.checklist_id == checklist.id,
        )
    )
    if record is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.dataset_record_not_found",
        )
    return record


def _require_draft_checklist(checklist: LegacyIssueVehicleModuleChecklist) -> None:
    if checklist.status != VEHICLE_CHECKLIST_STATUS_DRAFT:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="legacy_issues.vehicle_module_checklist_completed",
        )


def _stream_storage_object(
    storage_object: VehicleModuleChecklistAttachmentStorageObject,
) -> Iterable[bytes]:
    try:
        yield from storage_object.stream(VEHICLE_MODULE_CHECKLIST_ATTACHMENT_CHUNK_SIZE)
    finally:
        try:
            storage_object.close()
        finally:
            storage_object.release_conn()


def _remove_uploaded_object_best_effort(
    storage: VehicleModuleChecklistAttachmentStorage,
    *,
    storage_key: str,
) -> None:
    try:
        storage.remove(storage_key=storage_key)
    except Exception:  # pragma: no cover - original upload/transaction error wins
        logger.exception(
            "Failed to compensate vehicle module checklist attachment upload",
            extra={"storage_key": storage_key},
        )


def _history_details(
    *,
    checklist: LegacyIssueVehicleModuleChecklist,
    attachment: LegacyIssueVehicleModuleChecklistAttachment,
) -> dict[str, object]:
    return {
        "vehicle_module_checklist_id": checklist.id,
        "vehicle_model_id": checklist.vehicle_model_id,
        "module_key": checklist.module_key,
        "source_master_revision_id": checklist.source_master_revision_id,
        "source_master_revision_no": checklist.source_master_revision_no,
        "attachment_id": attachment.id,
    }
