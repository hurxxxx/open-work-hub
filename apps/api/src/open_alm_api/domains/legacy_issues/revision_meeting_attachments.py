from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import logging
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Literal, Protocol
from urllib.parse import quote

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import get_settings
from open_alm_api.core.storage import ensure_bucket, get_minio_client
from open_alm_api.domains.auth.access import is_platform_admin_user, record_audit_log
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueRevisionMeetingAttachment,
    LegacyIssueRevisionMeetingAttachmentCleanup,
    LegacyIssueRevisionOverviewHistory,
)
from open_alm_api.domains.legacy_issues.vehicle_module_checklist_attachments import (
    normalize_attachment_content_type,
    safe_attachment_filename,
)


logger = logging.getLogger(__name__)

REVISION_MEETING_ATTACHMENT_MAX_BYTES = 1024 * 1024 * 1024
REVISION_MEETING_ATTACHMENT_CHUNK_SIZE = 1024 * 1024
REVISION_MEETING_ATTACHMENT_SPOOL_MAX_BYTES = 16 * 1024 * 1024
REVISION_MEETING_ATTACHMENT_DESCRIPTION_MAX_LENGTH = 500
REVISION_MEETING_ATTACHMENT_CLIENT_REQUEST_ID_MAX_LENGTH = 64
REVISION_MEETING_ATTACHMENT_DOWNLOAD_CONTENT_TYPE = "application/octet-stream"


class RevisionMeetingAttachmentUploadFile(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


class RevisionMeetingAttachmentStorageObject(Protocol):
    def stream(self, chunk_size: int) -> Iterable[bytes]: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class RevisionMeetingAttachmentStorageClient(Protocol):
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
    ) -> RevisionMeetingAttachmentStorageObject: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...


@dataclass(frozen=True)
class RevisionMeetingAttachmentUpload:
    content: SpooledTemporaryFile[bytes]
    filename: str
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class RevisionMeetingAttachmentUploadResult:
    attachment: LegacyIssueRevisionMeetingAttachment
    created: bool


@dataclass(frozen=True)
class RevisionMeetingAttachmentContent:
    body: Iterable[bytes]
    media_type: str
    headers: dict[str, str]


@dataclass(frozen=True)
class RevisionMeetingAttachmentCleanupRef:
    id: str
    storage_key: str


RevisionMeetingAttachmentCompensationResult = Literal[
    "committed",
    "removed",
    "queued",
    "unknown",
    "untracked",
]


@dataclass(frozen=True)
class RevisionMeetingAttachmentStorage:
    bucket_name: str
    client: RevisionMeetingAttachmentStorageClient

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
        return _stream_storage_object(self.client.get_object(self.bucket_name, storage_key))

    def remove(self, *, storage_key: str) -> None:
        self.client.remove_object(self.bucket_name, storage_key)


def revision_meeting_attachment_storage() -> RevisionMeetingAttachmentStorage:
    settings = get_settings()
    return RevisionMeetingAttachmentStorage(
        bucket_name=settings.minio_bucket,
        client=get_minio_client(),
    )


async def read_revision_meeting_attachment_upload(
    file: RevisionMeetingAttachmentUploadFile,
) -> RevisionMeetingAttachmentUpload:
    content: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(
        max_size=REVISION_MEETING_ATTACHMENT_SPOOL_MAX_BYTES,
    )
    size_bytes = 0
    try:
        while chunk := await file.read(REVISION_MEETING_ATTACHMENT_CHUNK_SIZE):
            size_bytes += len(chunk)
            if size_bytes > REVISION_MEETING_ATTACHMENT_MAX_BYTES:
                raise localized_http_exception(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    code="legacy_issues.revision_meeting_attachment_too_large",
                )
            content.write(chunk)
        if size_bytes == 0:
            raise localized_http_exception(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="legacy_issues.revision_meeting_attachment_empty",
            )
        content.seek(0)
        return RevisionMeetingAttachmentUpload(
            content=content,
            filename=safe_attachment_filename(file.filename),
            content_type=normalize_attachment_content_type(file.content_type),
            size_bytes=size_bytes,
        )
    except Exception:
        content.close()
        raise


def normalize_revision_meeting_attachment_description(value: str | None) -> str | None:
    description = value.strip() if isinstance(value, str) else None
    if not description:
        return None
    if len(description) > REVISION_MEETING_ATTACHMENT_DESCRIPTION_MAX_LENGTH:
        raise localized_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="legacy_issues.revision_meeting_attachment_description_too_long",
        )
    return description


def list_revision_meeting_attachments(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    history_id: str | None = None,
) -> list[LegacyIssueRevisionMeetingAttachment]:
    if history_id is not None:
        _get_visible_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=history_id,
        )
    statement = (
        select(LegacyIssueRevisionMeetingAttachment)
        .join(
            LegacyIssueRevisionOverviewHistory,
            LegacyIssueRevisionOverviewHistory.id
            == LegacyIssueRevisionMeetingAttachment.overview_history_id,
        )
        .options(selectinload(LegacyIssueRevisionMeetingAttachment.uploaded_by))
        .where(
            LegacyIssueRevisionMeetingAttachment.workspace_id == workspace.id,
            LegacyIssueRevisionMeetingAttachment.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
        .order_by(
            LegacyIssueRevisionMeetingAttachment.created_at.desc(),
            LegacyIssueRevisionMeetingAttachment.id.desc(),
        )
    )
    if history_id is not None:
        statement = statement.where(
            LegacyIssueRevisionMeetingAttachment.overview_history_id == history_id
        )
    return list(db.scalars(statement))


def find_existing_revision_meeting_attachment_upload(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    history_id: str,
    user: User,
    client_request_id: str,
) -> LegacyIssueRevisionMeetingAttachment | None:
    request_id = _validate_client_request_id(client_request_id)
    history = _get_visible_overview_history(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        history_id=history_id,
    )
    return _find_idempotent_revision_meeting_attachment(
        db,
        workspace_id=workspace.id,
        dataset_key=dataset_key,
        history_id=history.id,
        user_id=user.id,
        client_request_id=request_id,
    )


def upload_revision_meeting_attachment(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    history_id: str,
    user: User,
    upload: RevisionMeetingAttachmentUpload,
    description: str | None,
    client_request_id: str,
) -> RevisionMeetingAttachmentUploadResult:
    request_id = _validate_client_request_id(client_request_id)
    workspace_id = workspace.id
    user_id = user.id
    history = _get_visible_overview_history(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        history_id=history_id,
    )
    existing = _find_idempotent_revision_meeting_attachment(
        db,
        workspace_id=workspace_id,
        dataset_key=dataset_key,
        history_id=history.id,
        user_id=user_id,
        client_request_id=request_id,
    )
    if existing is not None:
        return RevisionMeetingAttachmentUploadResult(
            attachment=existing,
            created=False,
        )

    attachment_id = new_id()
    storage_key = (
        "legacy-issues/revision-meeting-attachments/"
        f"{workspace_id}/{history.id}/{attachment_id}/{upload.filename}"
    )
    storage = revision_meeting_attachment_storage()
    try:
        ensure_bucket()
        storage.put(
            storage_key=storage_key,
            content=upload.content,
            size_bytes=upload.size_bytes,
            content_type=upload.content_type,
        )
    except Exception as error:
        _rollback_upload_transaction(db)
        compensate_revision_meeting_attachment_upload(
            workspace_id=workspace_id,
            storage_key=storage_key,
            storage=storage,
        )
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="legacy_issues.revision_meeting_attachment_upload_failed",
        ) from error

    try:
        now = utcnow_naive()
        row = LegacyIssueRevisionMeetingAttachment(
            id=attachment_id,
            workspace_id=workspace_id,
            dataset_key=dataset_key,
            overview_history_id=history.id,
            filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=upload.size_bytes,
            description=normalize_revision_meeting_attachment_description(description),
            storage_key=storage_key,
            uploaded_by_id=user_id,
            client_request_id=request_id,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        record_audit_log(
            db,
            action="legacy_issues.revision_meeting_attachment.upload",
            entity_kind="legacy_issue_revision_meeting_attachment",
            entity_id=row.id,
            actor_user_id=user_id,
            summary="Uploaded a legacy issue revision meeting attachment.",
            payload=_audit_payload(row),
        )
        db.flush()
        db.refresh(row)
    except IntegrityError:
        rollback_succeeded = _rollback_upload_transaction(db)
        compensate_revision_meeting_attachment_upload(
            workspace_id=workspace_id,
            storage_key=storage_key,
            storage=storage,
        )
        if not rollback_succeeded:
            raise
        visible_history = _get_visible_overview_history(
            db,
            workspace=workspace,
            dataset_key=dataset_key,
            history_id=history_id,
        )
        existing = _find_idempotent_revision_meeting_attachment(
            db,
            workspace_id=workspace_id,
            dataset_key=dataset_key,
            history_id=visible_history.id,
            user_id=user_id,
            client_request_id=request_id,
        )
        if existing is not None:
            return RevisionMeetingAttachmentUploadResult(
                attachment=existing,
                created=False,
            )
        raise
    except Exception:
        _rollback_upload_transaction(db)
        compensate_revision_meeting_attachment_upload(
            workspace_id=workspace_id,
            storage_key=storage_key,
            storage=storage,
        )
        raise
    return RevisionMeetingAttachmentUploadResult(
        attachment=row,
        created=True,
    )


def update_revision_meeting_attachment_description(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    attachment_id: str,
    user: User,
    description: str | None,
) -> LegacyIssueRevisionMeetingAttachment:
    row = get_revision_meeting_attachment(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        attachment_id=attachment_id,
        for_update=True,
    )
    if row.uploaded_by_id != user.id and not is_platform_admin_user(user, db):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="legacy_issues.revision_meeting_attachment_edit_forbidden",
        )
    previous_description = row.description
    row.description = normalize_revision_meeting_attachment_description(description)
    row.updated_at = utcnow_naive()
    db.add(row)
    record_audit_log(
        db,
        action="legacy_issues.revision_meeting_attachment.description_update",
        entity_kind="legacy_issue_revision_meeting_attachment",
        entity_id=row.id,
        actor_user_id=user.id,
        summary="Updated a legacy issue revision meeting attachment description.",
        payload={
            **_audit_payload(row),
            "previous_description": previous_description,
            "updated_description": row.description,
        },
    )
    db.flush()
    db.refresh(row)
    return row


def get_revision_meeting_attachment(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    attachment_id: str,
    for_update: bool = False,
) -> LegacyIssueRevisionMeetingAttachment:
    statement = (
        select(LegacyIssueRevisionMeetingAttachment)
        .join(
            LegacyIssueRevisionOverviewHistory,
            LegacyIssueRevisionOverviewHistory.id
            == LegacyIssueRevisionMeetingAttachment.overview_history_id,
        )
        .options(selectinload(LegacyIssueRevisionMeetingAttachment.uploaded_by))
        .where(
            LegacyIssueRevisionMeetingAttachment.id == attachment_id,
            LegacyIssueRevisionMeetingAttachment.workspace_id == workspace.id,
            LegacyIssueRevisionMeetingAttachment.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
    )
    if for_update:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.revision_meeting_attachment_not_found",
        )
    return row


def open_revision_meeting_attachment(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    attachment_id: str,
) -> RevisionMeetingAttachmentContent:
    row = get_revision_meeting_attachment(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        attachment_id=attachment_id,
    )
    try:
        body = revision_meeting_attachment_storage().open_stream(storage_key=row.storage_key)
    except Exception as error:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.revision_meeting_attachment_not_found",
        ) from error
    encoded_filename = quote(row.filename or "attachment", safe="")
    return RevisionMeetingAttachmentContent(
        body=body,
        media_type=REVISION_MEETING_ATTACHMENT_DOWNLOAD_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def delete_revision_meeting_attachment(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    attachment_id: str,
    user: User,
) -> RevisionMeetingAttachmentCleanupRef:
    row = get_revision_meeting_attachment(
        db,
        workspace=workspace,
        dataset_key=dataset_key,
        attachment_id=attachment_id,
        for_update=True,
    )
    if not is_platform_admin_user(user, db):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="admin.platform_admin_required",
        )
    cleanup = _queue_attachment_cleanup(
        db,
        workspace=workspace,
        storage_key=row.storage_key,
    )
    record_audit_log(
        db,
        action="legacy_issues.revision_meeting_attachment.delete",
        entity_kind="legacy_issue_revision_meeting_attachment",
        entity_id=row.id,
        actor_user_id=user.id,
        summary="Deleted a legacy issue revision meeting attachment.",
        payload=_audit_payload(row),
    )
    db.delete(row)
    db.flush()
    return cleanup


def process_pending_revision_meeting_attachment_cleanups(
    db: Session,
    *,
    workspace: Workspace,
    limit: int = 100,
) -> tuple[int, int]:
    try:
        return _process_pending_revision_meeting_attachment_cleanups(
            db,
            workspace_id=workspace.id,
            limit=limit,
        )
    except Exception:  # pragma: no cover - cleanup must not fail the logical delete
        db.rollback()
        logger.exception(
            "Failed to persist revision meeting attachment cleanup progress",
            extra={"workspace_id": workspace.id},
        )
        return 0, 1


def process_all_pending_revision_meeting_attachment_cleanups(
    db: Session,
    *,
    limit: int = 1000,
    storage: RevisionMeetingAttachmentStorage | None = None,
) -> tuple[int, int]:
    try:
        return _process_pending_revision_meeting_attachment_cleanups(
            db,
            workspace_id=None,
            limit=limit,
            storage=storage,
        )
    except Exception:  # pragma: no cover - periodic task retries on its next run
        db.rollback()
        logger.exception("Failed to persist periodic revision meeting attachment cleanup progress")
        return 0, 1


def _process_pending_revision_meeting_attachment_cleanups(
    db: Session,
    *,
    workspace_id: str | None,
    limit: int,
    storage: RevisionMeetingAttachmentStorage | None = None,
) -> tuple[int, int]:
    statement = select(LegacyIssueRevisionMeetingAttachmentCleanup)
    if workspace_id is not None:
        statement = statement.where(
            LegacyIssueRevisionMeetingAttachmentCleanup.workspace_id == workspace_id
        )
    rows = list(
        db.scalars(
            statement.order_by(LegacyIssueRevisionMeetingAttachmentCleanup.created_at.asc())
            .limit(max(1, limit))
            .with_for_update(skip_locked=True)
        )
    )
    if not rows:
        return 0, 0
    active_storage = storage or revision_meeting_attachment_storage()
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
                "Failed to process revision meeting attachment cleanup",
                extra={"cleanup_id": row.id},
            )
        else:
            removed_ids.append(row.id)
    if removed_ids:
        db.execute(
            delete(LegacyIssueRevisionMeetingAttachmentCleanup).where(
                LegacyIssueRevisionMeetingAttachmentCleanup.id.in_(removed_ids)
            )
        )
    db.commit()
    return len(removed_ids), failed


def recover_revision_meeting_attachment_upload_commit(
    *,
    commit_error: Exception,
    workspace_id: str,
    dataset_key: str,
    history_id: str,
    attachment_id: str,
    storage_key: str,
    session_factory: Callable[[], Session] | None = None,
    storage: RevisionMeetingAttachmentStorage | None = None,
) -> RevisionMeetingAttachmentCompensationResult:
    """Resolve a failed commit without deleting an object that may be referenced."""

    active_session_factory = session_factory or get_session_factory()
    try:
        with active_session_factory() as verification_db:
            committed = (
                verification_db.scalar(
                    select(LegacyIssueRevisionMeetingAttachment.id).where(
                        LegacyIssueRevisionMeetingAttachment.id == attachment_id,
                        LegacyIssueRevisionMeetingAttachment.workspace_id == workspace_id,
                        LegacyIssueRevisionMeetingAttachment.dataset_key == dataset_key,
                        LegacyIssueRevisionMeetingAttachment.overview_history_id == history_id,
                        LegacyIssueRevisionMeetingAttachment.storage_key == storage_key,
                    )
                )
                is not None
            )
    except Exception:
        logger.exception(
            "Could not verify revision meeting attachment commit outcome; preserving object",
            extra={"attachment_id": attachment_id, "storage_key": storage_key},
        )
        return "unknown"

    if committed:
        return "committed"
    if _commit_failure_may_be_ambiguous(commit_error):
        logger.warning(
            "Revision meeting attachment commit remains ambiguous; preserving object for "
            "reference-aware orphan reconciliation",
            extra={"attachment_id": attachment_id, "storage_key": storage_key},
        )
        return "unknown"
    return compensate_revision_meeting_attachment_upload(
        workspace_id=workspace_id,
        storage_key=storage_key,
        session_factory=active_session_factory,
        storage=storage,
    )


def compensate_revision_meeting_attachment_upload(
    *,
    workspace_id: str,
    storage_key: str,
    session_factory: Callable[[], Session] | None = None,
    storage: RevisionMeetingAttachmentStorage | None = None,
) -> RevisionMeetingAttachmentCompensationResult:
    """Remove an unreferenced upload or durably queue removal for the worker."""

    active_storage = storage or revision_meeting_attachment_storage()
    try:
        active_storage.remove(storage_key=storage_key)
    except Exception:
        logger.exception(
            "Failed to compensate revision meeting attachment upload",
            extra={"storage_key": storage_key},
        )
        if _persist_attachment_cleanup(
            workspace_id=workspace_id,
            storage_key=storage_key,
            session_factory=session_factory,
        ):
            return "queued"
        return "untracked"
    return "removed"


def can_edit_revision_meeting_attachment(
    db: Session,
    *,
    user: User,
    attachment: LegacyIssueRevisionMeetingAttachment,
) -> bool:
    return attachment.uploaded_by_id == user.id or is_platform_admin_user(user, db)


def can_delete_revision_meeting_attachment(db: Session, *, user: User) -> bool:
    return is_platform_admin_user(user, db)


def _get_visible_overview_history(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    history_id: str,
) -> LegacyIssueRevisionOverviewHistory:
    row = db.scalar(
        select(LegacyIssueRevisionOverviewHistory).where(
            LegacyIssueRevisionOverviewHistory.id == history_id,
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace.id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
    )
    if row is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="legacy_issues.revision_not_found",
        )
    return row


def _find_idempotent_revision_meeting_attachment(
    db: Session,
    *,
    workspace_id: str,
    dataset_key: str,
    history_id: str,
    user_id: str,
    client_request_id: str,
) -> LegacyIssueRevisionMeetingAttachment | None:
    return db.scalar(
        select(LegacyIssueRevisionMeetingAttachment)
        .join(
            LegacyIssueRevisionOverviewHistory,
            LegacyIssueRevisionOverviewHistory.id
            == LegacyIssueRevisionMeetingAttachment.overview_history_id,
        )
        .options(selectinload(LegacyIssueRevisionMeetingAttachment.uploaded_by))
        .where(
            LegacyIssueRevisionMeetingAttachment.workspace_id == workspace_id,
            LegacyIssueRevisionMeetingAttachment.dataset_key == dataset_key,
            LegacyIssueRevisionMeetingAttachment.overview_history_id == history_id,
            LegacyIssueRevisionMeetingAttachment.uploaded_by_id == user_id,
            LegacyIssueRevisionMeetingAttachment.client_request_id == client_request_id,
            LegacyIssueRevisionOverviewHistory.id == history_id,
            LegacyIssueRevisionOverviewHistory.workspace_id == workspace_id,
            LegacyIssueRevisionOverviewHistory.dataset_key == dataset_key,
            LegacyIssueRevisionOverviewHistory.deleted_at.is_(None),
        )
    )


def _validate_client_request_id(value: str) -> str:
    if not isinstance(value, str) or not (
        1 <= len(value) <= REVISION_MEETING_ATTACHMENT_CLIENT_REQUEST_ID_MAX_LENGTH
    ):
        raise ValueError("client_request_id must contain between 1 and 64 characters")
    return value


def _queue_attachment_cleanup(
    db: Session,
    *,
    workspace: Workspace,
    storage_key: str,
) -> RevisionMeetingAttachmentCleanupRef:
    cleanup = LegacyIssueRevisionMeetingAttachmentCleanup(
        id=new_id(),
        workspace_id=workspace.id,
        storage_key=storage_key,
        created_at=utcnow_naive(),
    )
    db.add(cleanup)
    return RevisionMeetingAttachmentCleanupRef(
        id=cleanup.id,
        storage_key=cleanup.storage_key,
    )


def _persist_attachment_cleanup(
    *,
    workspace_id: str,
    storage_key: str,
    session_factory: Callable[[], Session] | None,
) -> bool:
    active_session_factory = session_factory or get_session_factory()
    for attempt in range(2):
        try:
            with active_session_factory() as cleanup_db:
                existing_id = cleanup_db.scalar(
                    select(LegacyIssueRevisionMeetingAttachmentCleanup.id).where(
                        LegacyIssueRevisionMeetingAttachmentCleanup.storage_key == storage_key
                    )
                )
                if existing_id is not None:
                    return True
                cleanup_db.add(
                    LegacyIssueRevisionMeetingAttachmentCleanup(
                        id=new_id(),
                        workspace_id=workspace_id,
                        storage_key=storage_key,
                        created_at=utcnow_naive(),
                    )
                )
                try:
                    cleanup_db.commit()
                except IntegrityError:
                    cleanup_db.rollback()
                    if (
                        cleanup_db.scalar(
                            select(LegacyIssueRevisionMeetingAttachmentCleanup.id).where(
                                LegacyIssueRevisionMeetingAttachmentCleanup.storage_key
                                == storage_key
                            )
                        )
                        is None
                    ):
                        raise
                return True
        except Exception:
            if attempt == 0:
                continue
            logger.exception(
                "Failed to durably queue revision meeting attachment upload cleanup",
                extra={"workspace_id": workspace_id, "storage_key": storage_key},
            )
            return False
    return False


def _rollback_upload_transaction(db: Session) -> bool:
    try:
        db.rollback()
    except Exception:
        logger.exception("Failed to roll back revision meeting attachment upload transaction")
        return False
    return True


def _commit_failure_may_be_ambiguous(error: Exception) -> bool:
    return not isinstance(error, IntegrityError)


def _stream_storage_object(
    storage_object: RevisionMeetingAttachmentStorageObject,
) -> Iterable[bytes]:
    try:
        yield from storage_object.stream(REVISION_MEETING_ATTACHMENT_CHUNK_SIZE)
    finally:
        try:
            storage_object.close()
        finally:
            storage_object.release_conn()


def _audit_payload(row: LegacyIssueRevisionMeetingAttachment) -> dict[str, object]:
    return {
        "workspace_id": row.workspace_id,
        "dataset_key": row.dataset_key,
        "overview_history_id": row.overview_history_id,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "description": row.description,
        "uploaded_by_id": row.uploaded_by_id,
        "client_request_id": row.client_request_id,
    }


__all__ = [
    "REVISION_MEETING_ATTACHMENT_MAX_BYTES",
    "RevisionMeetingAttachmentContent",
    "RevisionMeetingAttachmentStorage",
    "RevisionMeetingAttachmentUpload",
    "RevisionMeetingAttachmentUploadResult",
    "compensate_revision_meeting_attachment_upload",
    "can_delete_revision_meeting_attachment",
    "can_edit_revision_meeting_attachment",
    "delete_revision_meeting_attachment",
    "find_existing_revision_meeting_attachment_upload",
    "get_revision_meeting_attachment",
    "list_revision_meeting_attachments",
    "normalize_revision_meeting_attachment_description",
    "open_revision_meeting_attachment",
    "process_all_pending_revision_meeting_attachment_cleanups",
    "process_pending_revision_meeting_attachment_cleanups",
    "read_revision_meeting_attachment_upload",
    "recover_revision_meeting_attachment_upload_commit",
    "revision_meeting_attachment_storage",
    "update_revision_meeting_attachment_description",
    "upload_revision_meeting_attachment",
]
