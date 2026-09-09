from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.files import rag_sync as files_rag_sync
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.rag_projection import (
    FileExtractionRuntime,
    load_file_rag_projection,
)
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.rag.providers.base import (
    OcrClient,
    RagProviderConfigurationError,
)
from open_work_hub_api.domains.retrieval.models import RetrievalProjectionHead
from open_work_hub_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)


@dataclass(frozen=True, slots=True)
class FileExtractionBootstrapBatch:
    next_file_id: str | None
    scanned_files: int
    ready_files: int
    unsupported_files: int
    failed_files: int
    recorded_events: int
    complete: bool


class OcrOnlyFileExtractionRuntime:
    """Minimal parser/OCR runtime with no vector or keyword mutation surface."""

    def __init__(self, ocr_client: OcrClient | None) -> None:
        self._ocr_client = ocr_client

    @property
    def ocr_provider_name(self) -> str | None:
        if self._ocr_client is None:
            return None
        return str(getattr(self._ocr_client, "provider_name", self._ocr_client.__class__.__name__))

    def extract_text(
        self,
        *,
        content: bytes,
        content_type: str | None = None,
        resource_type: str | None = None,
        source_kind: str | None = None,
    ) -> str:
        del resource_type, source_kind
        if self._ocr_client is None:
            raise RagProviderConfigurationError("OCR client is not configured")
        return self._ocr_client.extract_text(content=content, content_type=content_type)

    def close(self) -> None:
        close = getattr(self._ocr_client, "close", None)
        if callable(close):
            close()


def bootstrap_file_extraction_artifacts(
    db: Session,
    *,
    after_file_id: str | None,
    limit: int,
    extraction_runtime: FileExtractionRuntime,
) -> FileExtractionBootstrapBatch:
    """Persist Files extraction artifacts without touching retrieval backends.

    This operator workflow is intentionally available only while the Files
    retrieval gate is closed. It advances the canonical source fence after a
    successful extraction (or unsupported tombstone), so the later generation
    materializer sees an immutable artifact checksum at its fixed watermark.
    """

    if files_rag_sync.FILES_RETRIEVAL_ACTIVE:
        raise ValueError("Files extraction bootstrap requires a disabled gate")
    batch_limit = int(limit)
    if batch_limit < 1 or batch_limit > 1_000:
        raise ValueError("limit must be between 1 and 1000")
    cursor = str(after_file_id or "").strip() or None
    statement = (
        select(FileManagerFile.id)
        .where(FileManagerFile.deleted_at.is_(None))
        .order_by(FileManagerFile.id.asc())
        .limit(batch_limit + 1)
        .with_for_update(skip_locked=True)
    )
    if cursor is not None:
        statement = statement.where(FileManagerFile.id > cursor)
    candidates = list(db.scalars(statement))
    has_more = len(candidates) > batch_limit
    file_ids = [str(file_id) for file_id in candidates[:batch_limit]]
    ready_files = 0
    unsupported_files = 0
    failed_files = 0
    recorded_events = 0

    for file_id in file_ids:
        source = db.get(FileManagerFile, file_id, populate_existing=True)
        if source is None or source.deleted_at is not None:
            continue
        if source.extraction_status == "unsupported":
            unsupported_files += 1
            if _projection_fence_needs_update(file=source, desired_state="deleted"):
                files_rag_sync.enqueue_file_retrieval_sync(
                    db,
                    file=source,
                    operation=RagSyncOperation.DELETE,
                )
                recorded_events += 1
            continue
        try:
            load_file_rag_projection(
                db,
                file_id=file_id,
                rag_service=extraction_runtime,
            )
        except Exception as error:  # noqa: BLE001 - persist a retryable operator result
            files_rag_sync.mark_file_projection_failed(
                db,
                file_id=file_id,
                error=error.__class__.__name__,
                phase="extraction",
            )
            failed_files += 1
            continue

        file = db.get(FileManagerFile, file_id, populate_existing=True)
        if file is None or file.deleted_at is not None:
            continue
        if file.extraction_status == "unsupported":
            unsupported_files += 1
            if _projection_fence_needs_update(file=file, desired_state="deleted"):
                files_rag_sync.enqueue_file_retrieval_sync(
                    db,
                    file=file,
                    operation=RagSyncOperation.DELETE,
                )
                recorded_events += 1
            continue
        if file.extraction_status != "ready" or not file.extraction_content_checksum:
            failed_files += 1
            continue
        ready_files += 1
        if _projection_fence_needs_update(file=file, desired_state="active"):
            files_rag_sync.enqueue_file_retrieval_sync(
                db,
                file=file,
                operation=RagSyncOperation.UPSERT,
            )
            recorded_events += 1

    return FileExtractionBootstrapBatch(
        next_file_id=file_ids[-1] if file_ids else cursor,
        scanned_files=len(file_ids),
        ready_files=ready_files,
        unsupported_files=unsupported_files,
        failed_files=failed_files,
        recorded_events=recorded_events,
        complete=not has_more,
    )


def _projection_fence_needs_update(
    *,
    file: FileManagerFile,
    desired_state: str,
) -> bool:
    db = Session.object_session(file)
    if db is None:
        raise RuntimeError("Files extraction bootstrap source is detached")
    head = db.get(
        RetrievalProjectionHead,
        (FILE_MANAGER_FILE_RESOURCE_TYPE, file.id),
        populate_existing=True,
    )
    expected_checksum = file.extraction_content_checksum if desired_state == "active" else None
    return bool(
        head is None
        or str(head.retrieval_partition_id) != str(file.retrieval_partition_id)
        or head.desired_state != desired_state
        or head.content_checksum != expected_checksum
    )


__all__ = [
    "FileExtractionBootstrapBatch",
    "OcrOnlyFileExtractionRuntime",
    "bootstrap_file_extraction_artifacts",
]
