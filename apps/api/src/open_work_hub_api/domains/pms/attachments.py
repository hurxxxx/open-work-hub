from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from io import BytesIO
from datetime import datetime
from typing import Literal, Protocol
from urllib.parse import quote

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import get_minio_client
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.auth.workspace_app_gate import is_app_enabled_for_user_context
from open_work_hub_api.domains.content_access.grants import (
    ContentGrantClaims,
    ContentGrantIssuer,
    InvalidContentGrant,
    build_content_grant_url,
    object_identity,
)
from open_work_hub_api.domains.content_access.contracts import ContentStream
from open_work_hub_api.domains.pms.access import (
    _ensure_list_editor,
    _ensure_task_writable,
)
from open_work_hub_api.domains.pms.models import Attachment, Task, TaskActivityLog
from open_work_hub_api.domains.pms.projections import task_reference
from open_work_hub_api.domains.pms.source_access import resolve_pms_task_workspace_id
from open_work_hub_api.domains.source_access import can_read_pms_task


MAX_TASK_ATTACHMENT_UPLOAD_SIZE = 50 * 1024 * 1024
DEFAULT_TASK_ATTACHMENT_FILENAME = "unnamed"
DEFAULT_TASK_ATTACHMENT_CONTENT_TYPE = "application/octet-stream"
TASK_ATTACHMENT_CONTENT_URL_EXPIRES_SECONDS = 5 * 60
TASK_ATTACHMENT_CONTENT_CHUNK_SIZE = 1024 * 1024
TaskAttachmentDisposition = Literal["attachment", "inline"]


class TaskAttachmentStorageObject(Protocol):
    def stream(self, chunk_size: int) -> Iterable[bytes]: ...
    def close(self) -> None: ...
    def release_conn(self) -> None: ...


class TaskAttachmentObjectStore(Protocol):
    def put(
        self,
        *,
        storage_key: str,
        content: bytes,
        content_type: str,
    ) -> None: ...

    def remove(self, *, storage_key: str) -> None: ...

    def open_stream(self, *, storage_key: str, chunk_size: int) -> Iterable[bytes]: ...


@dataclass(frozen=True)
class TaskAttachmentUpload:
    filename: str | None
    content_type: str | None
    content: bytes


@dataclass(frozen=True)
class TaskAttachmentMetadata:
    id: str
    task_id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by_id: str
    uploaded_by_name: str
    created_at: datetime


@dataclass(frozen=True)
class TaskAttachmentItem(TaskAttachmentMetadata):
    download_url: str


class MinioTaskAttachmentObjectStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = get_minio_client()

    def put(
        self,
        *,
        storage_key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        self.client.put_object(
            self.settings.minio_bucket,
            storage_key,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )

    def remove(self, *, storage_key: str) -> None:
        self.client.remove_object(self.settings.minio_bucket, storage_key)

    def open_stream(self, *, storage_key: str, chunk_size: int) -> Iterable[bytes]:
        obj = self.client.get_object(self.settings.minio_bucket, storage_key)
        return stream_task_attachment_storage_object(obj, chunk_size=chunk_size)


def task_attachment_object_store() -> TaskAttachmentObjectStore:
    return MinioTaskAttachmentObjectStore()


def upload_task_attachment(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    task_id: str,
    upload: TaskAttachmentUpload,
    content_grant_issuer: ContentGrantIssuer,
    store: TaskAttachmentObjectStore | None = None,
) -> TaskAttachmentItem:
    task = _ensure_task_writable(db, user, task_id)
    filename = normalize_task_attachment_filename(upload.filename)
    content_type = upload.content_type or DEFAULT_TASK_ATTACHMENT_CONTENT_TYPE
    size_bytes = len(upload.content)
    if size_bytes > MAX_TASK_ATTACHMENT_UPLOAD_SIZE:
        raise localized_http_exception(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="pms.file_size_limit_exceeded",
            limit_mb=50,
        )

    attachment_id = new_id()
    storage_key = f"pms/{task.task_list.id}/{task.id}/{attachment_id}/{filename}"
    resolved_store = store or task_attachment_object_store()
    resolved_store.put(
        storage_key=storage_key,
        content=upload.content,
        content_type=content_type,
    )

    attachment = Attachment(
        id=attachment_id,
        task_id=task.id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=storage_key,
        uploaded_by_id=user.id,
    )
    db.add(attachment)
    db.flush()
    _log_task_attachment_activity(
        db,
        task=task,
        user=user,
        action="attachment_added",
        filename=filename,
    )
    db.commit()
    db.refresh(attachment)
    return serialize_task_attachment(
        db,
        user=user,
        attachment=attachment,
        content_grant_issuer=content_grant_issuer,
    )


def delete_task_attachment(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    attachment_id: str,
    store: TaskAttachmentObjectStore | None = None,
) -> None:
    attachment = db.scalar(
        select(Attachment)
        .options(selectinload(Attachment.task).selectinload(Task.task_list))
        .where(Attachment.id == attachment_id)
    )
    if attachment is None:
        raise localized_http_exception(status_code=404, code="pms.attachment_not_found")
    _ensure_list_editor(db, user, attachment.task.list_id)
    try:
        (store or task_attachment_object_store()).remove(storage_key=attachment.storage_key)
    except Exception:
        pass

    _log_task_attachment_activity(
        db,
        task=attachment.task,
        user=user,
        action="attachment_removed",
        filename=attachment.filename,
    )
    db.delete(attachment)
    db.commit()


def serialize_task_attachment(
    db: Session,
    *,
    user: User,
    attachment: Attachment,
    content_grant_issuer: ContentGrantIssuer,
) -> TaskAttachmentItem:
    metadata = serialize_task_attachment_metadata(attachment)
    return TaskAttachmentItem(
        **asdict(metadata),
        download_url=build_task_attachment_download_url(
            db,
            user=user,
            attachment=attachment,
            content_grant_issuer=content_grant_issuer,
        ),
    )


def serialize_task_attachment_metadata(
    attachment: Attachment,
) -> TaskAttachmentMetadata:
    return TaskAttachmentMetadata(
        id=attachment.id,
        task_id=attachment.task_id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        uploaded_by_id=attachment.uploaded_by_id,
        uploaded_by_name=attachment.uploaded_by.full_name,
        created_at=attachment.created_at,
    )


def build_task_attachment_download_url(
    db: Session,
    *,
    user: User,
    attachment: Attachment,
    content_grant_issuer: ContentGrantIssuer,
    disposition: TaskAttachmentDisposition = "attachment",
    now: float | None = None,
    expires_seconds: int = TASK_ATTACHMENT_CONTENT_URL_EXPIRES_SECONDS,
) -> str:
    workspace_id = resolve_pms_task_workspace_id(db, task_id=attachment.task_id)
    if workspace_id is None or content_grant_issuer.user_id != user.id:
        raise ValueError("PMS attachment grants require matching workspace/user context")
    return build_content_grant_url(
        resource_kind="pms.attachment",
        resource_id=attachment.id,
        owner_app_id="pms",
        issuer=content_grant_issuer,
        execution_context_kind="workspace",
        execution_workspace_id=workspace_id,
        route_id=None,
        source_type="pms_task",
        source_id=attachment.task_id,
        object_identity=object_identity(
            attachment.id,
            attachment.task_id,
            attachment.storage_key,
            attachment.size_bytes,
        ),
        resource_version=attachment.created_at.isoformat(timespec="microseconds"),
        disposition=disposition,
        expires_seconds=expires_seconds,
        now=now,
    )


def open_task_attachment_content_grant(
    db: Session,
    *,
    claims: ContentGrantClaims,
    store: TaskAttachmentObjectStore | None = None,
) -> ContentStream:
    attachment = db.scalar(select(Attachment).where(Attachment.id == claims.resource_id))
    if attachment is None:
        raise InvalidContentGrant("resource")
    workspace_id = resolve_pms_task_workspace_id(db, task_id=attachment.task_id)
    if (
        claims.owner_app_id != "pms"
        or claims.execution_context_kind != "workspace"
        or claims.execution_workspace_id != workspace_id
        or claims.source_type != "pms_task"
        or claims.source_id != attachment.task_id
        or claims.object_identity
        != object_identity(
            attachment.id,
            attachment.task_id,
            attachment.storage_key,
            attachment.size_bytes,
        )
        or claims.resource_version
        != attachment.created_at.isoformat(timespec="microseconds")
    ):
        raise InvalidContentGrant("binding")
    if not is_app_enabled_for_user_context(
        db,
        app_id="pms",
        user_id=claims.issuer_user_id,
        workspace_id=workspace_id,
    ):
        raise InvalidContentGrant("app")
    user = db.get(User, claims.issuer_user_id)
    if user is None:
        raise InvalidContentGrant("principal")
    if not can_read_pms_task(db, user=user, task_id=attachment.task_id):
        raise InvalidContentGrant("source_acl")

    try:
        body = (store or task_attachment_object_store()).open_stream(
            storage_key=attachment.storage_key,
            chunk_size=TASK_ATTACHMENT_CONTENT_CHUNK_SIZE,
        )
    except Exception as exc:
        raise localized_http_exception(
            status_code=502,
            code="pms.attachment_download_failed",
        ) from exc
    encoded_filename = quote(attachment.filename or DEFAULT_TASK_ATTACHMENT_FILENAME, safe="")
    return ContentStream(
        body=body,
        media_type=attachment.content_type or DEFAULT_TASK_ATTACHMENT_CONTENT_TYPE,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": (
                f"{claims.disposition}; filename*=UTF-8''{encoded_filename}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


def stream_task_attachment_storage_object(
    obj: TaskAttachmentStorageObject,
    *,
    chunk_size: int,
) -> Iterable[bytes]:
    try:
        yield from obj.stream(chunk_size)
    finally:
        try:
            obj.close()
        finally:
            obj.release_conn()


def normalize_task_attachment_filename(filename: str | None) -> str:
    normalized = (filename or "").strip()
    return normalized or DEFAULT_TASK_ATTACHMENT_FILENAME


def _log_task_attachment_activity(
    db: Session,
    *,
    task: Task,
    user: User,
    action: str,
    filename: str,
) -> None:
    verb = "attached" if action == "attachment_added" else "removed"
    preposition = "to" if action == "attachment_added" else "from"
    db.add(
        TaskActivityLog(
            id=new_id(),
            task_id=task.id,
            actor_id=user.id,
            action=action,
            message=f"{user.full_name} {verb} {filename} {preposition} {task_reference(task)}.",
        )
    )
