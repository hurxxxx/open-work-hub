from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Literal
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.content_access.ownership import record_ownership_transition
from open_work_hub_api.domains.files import storage_adapter as file_storage
from open_work_hub_api.domains.files.archive_planner import (
    ArchivePlanFile,
    ArchivePlanFolder,
    ensure_directory_path,
    plan_archive_entries,
    safe_filename,
)
from open_work_hub_api.domains.files.external_access import (
    authorize_explicit_file_ids,
    is_current_platform_admin,
)
from open_work_hub_api.domains.files.models import (
    FileManagerBulkIngestRun,
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFolder,
    FileManagerStorageCleanupJob,
)
from open_work_hub_api.domains.files.rag_sync import enqueue_file_retrieval_sync
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.retrieval.models import RetrievalPartition, RetrievalPartitionState
from open_work_hub_api.domains.retrieval.partitioning import (
    create_managed_partition,
    ensure_default_partition,
)

FILE_VISIBILITIES = frozenset({"private", "company"})
FILE_CORPUS_ACCESS_SCOPE_KINDS = frozenset({"company"})
MAX_FILE_UPLOAD_SIZE = 250 * 1024 * 1024
ARCHIVE_SPOOL_LIMIT_BYTES = 64 * 1024 * 1024
ARCHIVE_CHUNK_BYTES = 1024 * 1024
MAX_ARCHIVE_FILE_COUNT = 500
MAX_ARCHIVE_TOTAL_SIZE = 512 * 1024 * 1024

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileArchiveEntry:
    archive_path: str
    file: FileManagerFile | None


@dataclass(frozen=True)
class _FileDeleteScope:
    folder_ids: tuple[str, ...]
    file_ids: tuple[str, ...]
    corpus_ids: tuple[str, ...]
    standalone_partition_ids: tuple[str, ...]


FileCorpusLockMode = Literal["shared", "exclusive"]
FileChildLockMode = Literal["shared", "exclusive"]


class FileCorpusError(RuntimeError):
    pass


class FileCorpusNotFound(FileCorpusError):
    pass


class FileCorpusAccessDenied(FileCorpusError):
    pass


class FileCorpusConflict(FileCorpusError):
    pass


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def is_corpus_admin(db: Session, *, user: User) -> bool:
    return is_current_platform_admin(db, user.id) and can_use_app(
        db, user_id=user.id, app_id="files"
    )


def normalize_visibility(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in FILE_VISIBILITIES:
        raise localized_http_exception(status_code=422, code="files.invalid_visibility")
    return normalized


def create_file_corpus(
    db: Session,
    *,
    user: User,
    name: str,
) -> FileManagerCorpus:
    """Create a company corpus with its own stable partition."""

    if not is_corpus_admin(db, user=user):
        raise FileCorpusAccessDenied("file corpus creation requires platform admin")
    partition = create_managed_partition(
        db,
        source_namespace="files",
        candidate_scope_kind="company",
    )
    corpus = FileManagerCorpus(
        id=new_id(),
        name=_normalize_name(name),
        access_scope_kind="company",
        retrieval_partition_id=partition.id,
        created_by_id=user.id,
        metadata_version=1,
    )
    db.add(corpus)
    db.flush()
    return corpus


def list_managed_file_corpora(
    db: Session,
    *,
    user: User,
) -> list[FileManagerCorpus]:
    if not is_corpus_admin(db, user=user):
        raise FileCorpusAccessDenied("file corpus listing requires platform admin")
    return list(
        db.scalars(
            select(FileManagerCorpus)
            .where()
            .order_by(FileManagerCorpus.created_at.asc(), FileManagerCorpus.id.asc())
        ).all()
    )


def require_managed_file_corpus(
    db: Session,
    *,
    user: User,
    corpus_id: str,
) -> FileManagerCorpus:
    if not is_corpus_admin(db, user=user):
        raise FileCorpusAccessDenied("file corpus management requires platform admin")
    corpus = db.scalar(
        select(FileManagerCorpus).where(
            FileManagerCorpus.id == corpus_id,
        )
    )
    if corpus is None:
        raise FileCorpusNotFound(corpus_id)
    return corpus


def list_accessible_folders(
    db: Session,
    *,
    user: User,
) -> list[FileManagerFolder]:
    is_admin = is_corpus_admin(db, user=user)
    folders = list(
        db.scalars(
            select(FileManagerFolder)
            .options(joinedload(FileManagerFolder.owner))
            .where(
                FileManagerFolder.deleted_at.is_(None),
            )
            .order_by(FileManagerFolder.name.asc(), FileManagerFolder.created_at.asc())
        )
    )
    folder_by_id = {folder.id: folder for folder in folders}
    accessible_ids: set[str] = set()
    changed = True
    while changed:
        changed = False
        for folder in folders:
            if folder.id in accessible_ids:
                continue
            if not _record_visible(
                folder.visibility, folder.owner_id, user=user, is_admin=is_admin
            ):
                continue
            if folder.parent_id is not None:
                if folder.parent_id not in folder_by_id:
                    continue
                if folder.parent_id not in accessible_ids:
                    continue
            accessible_ids.add(folder.id)
            changed = True
    return [folder for folder in folders if folder.id in accessible_ids]


def list_accessible_files(
    db: Session,
    *,
    user: User,
    accessible_folder_ids: set[str],
) -> list[FileManagerFile]:
    is_admin = is_corpus_admin(db, user=user)
    files = list(
        db.scalars(
            select(FileManagerFile)
            .options(joinedload(FileManagerFile.owner))
            .where(
                FileManagerFile.deleted_at.is_(None),
            )
            .order_by(FileManagerFile.filename.asc(), FileManagerFile.created_at.asc())
        )
    )
    corpus_ids = {file.corpus_id for file in files if file.corpus_id is not None}
    corpora = (
        {
            corpus.id: corpus
            for corpus in db.scalars(
                select(FileManagerCorpus).where(FileManagerCorpus.id.in_(corpus_ids))
            )
        }
        if corpus_ids
        else {}
    )
    explicit_file_ids = [
        file.id
        for file in files
        if file.corpus_id is not None
        and (corpus := corpora.get(file.corpus_id)) is not None
        and corpus.authorization_mode == "explicit_grants"
    ]
    explicit_allowed = authorize_explicit_file_ids(
        db,
        file_ids=explicit_file_ids,
        user_id=user.id,
    )
    accessible: list[FileManagerFile] = []
    for file in files:
        if file.corpus_id is not None:
            corpus = corpora.get(file.corpus_id)
            if corpus is None:
                continue
            scope_allowed = corpus.access_scope_kind == "company"
            if not scope_allowed:
                continue
            if corpus.authorization_mode == "explicit_grants" and file.id not in explicit_allowed:
                continue
            accessible.append(file)
            continue
        if _record_visible(file.visibility, file.owner_id, user=user, is_admin=is_admin) and (
            file.folder_id is None or file.folder_id in accessible_folder_ids
        ):
            accessible.append(file)
    return accessible


def require_folder_access(
    db: Session,
    *,
    user: User,
    folder_id: str | None,
) -> FileManagerFolder | None:
    if folder_id is None:
        return None
    accessible = {folder.id: folder for folder in list_accessible_folders(db, user=user)}
    folder = accessible.get(folder_id)
    if folder is None:
        raise localized_http_exception(status_code=404, code="files.folder_not_found")
    return folder


def create_folder(
    db: Session,
    *,
    user: User,
    name: str,
    parent_id: str | None,
    visibility: str,
    company_admin_read_acknowledged: bool = False,
    corpus_id: str | None = None,
    operator_ingest_run_id: str | None = None,
) -> FileManagerFolder:
    parent, corpus, retrieval_partition_id = _prepare_file_corpus_ingress(
        db,
        user=user,
        requested_corpus_id=corpus_id,
        parent_id=parent_id,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if parent is not None:
        _ensure_can_manage_record(
            db,
            user=user,
            owner_id=parent.owner_id,
            error_code="files.parent_manage_access_required",
        )
    if corpus is not None:
        effective_visibility = "company"
    elif parent is not None:
        effective_visibility = parent.visibility
    else:
        effective_visibility = normalize_visibility(visibility)
    folder = FileManagerFolder(
        id=new_id(),
        corpus_id=corpus.id if corpus is not None else None,
        parent_id=parent.id if parent else None,
        owner_id=user.id,
        name=_normalize_name(name),
        visibility=effective_visibility,
        retrieval_partition_id=retrieval_partition_id,
    )
    if effective_visibility == "company":
        record_ownership_transition(
            db,
            actor_user_id=user.id,
            resource_kind="file_folder",
            resource_id=folder.id,
            current_kind="personal",
            next_kind="company",
            company_admin_read_acknowledged=company_admin_read_acknowledged,
        )
    db.add(folder)
    db.flush()
    return folder


def update_folder(
    db: Session,
    *,
    user: User,
    folder_id: str,
    name: str | None = None,
    visibility: str | None = None,
) -> FileManagerFolder:
    locked_corpora, locked_standalone_partitions = _lock_corpora_for_children(
        db,
        folder_ids=(folder_id,),
        lock_mode="shared",
    )
    folder = _load_folder(
        db,
        folder_id=folder_id,
        lock_mode="exclusive",
    )
    _validate_locked_child_corpus(
        folder,
        locked_corpora,
        locked_standalone_partitions=locked_standalone_partitions,
    )
    _ensure_can_manage_record(db, user=user, owner_id=folder.owner_id)
    if name is not None:
        folder.name = _normalize_name(name)
    if visibility is not None:
        next_visibility = normalize_visibility(visibility)
        if next_visibility != folder.visibility:
            raise localized_http_exception(
                status_code=422,
                code="files.visibility_change_not_allowed",
            )
    db.add(folder)
    db.flush()
    return folder


def delete_folder(
    db: Session,
    *,
    user: User,
    folder_id: str,
) -> list[str]:
    folders, files = _lock_tree_delete_scope(
        db,
        selected_folder_ids=(folder_id,),
        selected_file_ids=(),
    )
    _require_current_mutation_context(
        db,
        user_id=user.id,
    )
    if any(item.owner_id != user.id for item in folders) or any(
        item.owner_id != user.id for item in files
    ):
        raise localized_http_exception(status_code=403, code="files.delete_access_required")

    deleted_at = utcnow_naive()
    for row in [*folders, *files]:
        row.deleted_at = deleted_at
        db.add(row)
    for file in files:
        purge_file_retrieval_artifact(file)
        enqueue_file_retrieval_sync(db, file=file, operation=RagSyncOperation.DELETE)
    return [file.storage_key for file in files]


def upload_file(
    db: Session,
    *,
    user: User,
    filename: str | None,
    content_type: str | None,
    content: BinaryIO,
    size_bytes: int,
    folder_id: str | None,
    visibility: str,
    company_admin_read_acknowledged: bool = False,
    corpus_id: str | None = None,
    operator_ingest_run_id: str | None = None,
    reserved_file_id: str | None = None,
) -> FileManagerFile:
    if size_bytes > MAX_FILE_UPLOAD_SIZE:
        raise localized_http_exception(
            status_code=413,
            code="files.file_size_limit_exceeded",
            limit_mb=MAX_FILE_UPLOAD_SIZE // (1024 * 1024),
        )
    folder, corpus, retrieval_partition_id = _prepare_file_corpus_ingress(
        db,
        user=user,
        requested_corpus_id=corpus_id,
        parent_id=folder_id,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if folder is not None:
        _ensure_can_manage_record(
            db,
            user=user,
            owner_id=folder.owner_id,
            error_code="files.parent_manage_access_required",
        )
    if corpus is not None:
        effective_visibility = "company"
    elif folder is not None:
        effective_visibility = folder.visibility
    else:
        effective_visibility = normalize_visibility(visibility)
    if reserved_file_id is not None and operator_ingest_run_id is None:
        raise FileCorpusAccessDenied("reserved file IDs require an operator ingest run")
    file_id = str(reserved_file_id or "").strip() or new_id()
    stored_name = safe_filename(filename)
    storage_key = f"files/{file_id}/{stored_name}"
    row = FileManagerFile(
        id=file_id,
        corpus_id=corpus.id if corpus is not None else None,
        folder_id=folder.id if folder else None,
        owner_id=user.id,
        filename=stored_name,
        content_type=content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_key=storage_key,
        visibility=effective_visibility,
        retrieval_partition_id=retrieval_partition_id,
    )
    if effective_visibility == "company":
        record_ownership_transition(
            db,
            actor_user_id=user.id,
            resource_kind="file",
            resource_id=row.id,
            current_kind="personal",
            next_kind="company",
            company_admin_read_acknowledged=company_admin_read_acknowledged,
        )
    db.add(row)
    db.flush()

    try:
        content.seek(0)
        file_storage.put_file_object(
            storage_key=storage_key,
            content=content,
            size_bytes=size_bytes,
            content_type=row.content_type,
        )
        enqueue_file_retrieval_sync(db, file=row, operation=RagSyncOperation.UPSERT)
    except Exception as exc:
        db.rollback()
        remove_storage_object_immediately(storage_key)
        raise localized_http_exception(status_code=502, code="files.storage_upload_failed") from exc
    return row


def delete_file(
    db: Session,
    *,
    user: User,
    file_id: str,
) -> str:
    locked_corpora, locked_standalone_partitions = _lock_corpora_for_children(
        db,
        file_ids=(file_id,),
        lock_mode="shared",
    )
    file = _load_file(
        db,
        file_id=file_id,
        lock_mode="exclusive",
    )
    _validate_locked_child_corpus(
        file,
        locked_corpora,
        locked_standalone_partitions=locked_standalone_partitions,
    )
    _ensure_can_manage_record(db, user=user, owner_id=file.owner_id)
    file.deleted_at = utcnow_naive()
    purge_file_retrieval_artifact(file)
    db.add(file)
    enqueue_file_retrieval_sync(db, file=file, operation=RagSyncOperation.DELETE)
    return file.storage_key


def delete_items(
    db: Session,
    *,
    user: User,
    file_ids: Iterable[str],
    folder_ids: Iterable[str],
) -> list[str]:
    selected_file_ids = set(file_ids)
    selected_folder_ids = set(folder_ids)
    if not selected_file_ids and not selected_folder_ids:
        raise localized_http_exception(status_code=422, code="files.selection_required")

    if selected_folder_ids:
        folders_to_delete, files_to_delete = _lock_tree_delete_scope(
            db,
            selected_folder_ids=selected_folder_ids,
            selected_file_ids=selected_file_ids,
        )
    else:
        folders_to_delete = []
        files_to_delete = _lock_leaf_files_for_delete(
            db,
            selected_file_ids=selected_file_ids,
        )

    _require_current_mutation_context(
        db,
        user_id=user.id,
    )
    if any(folder.owner_id != user.id for folder in folders_to_delete) or any(
        file.owner_id != user.id for file in files_to_delete
    ):
        raise localized_http_exception(status_code=403, code="files.delete_access_required")

    deleted_at = utcnow_naive()
    for row in [*folders_to_delete, *files_to_delete]:
        row.deleted_at = deleted_at
        db.add(row)
    for file in files_to_delete:
        purge_file_retrieval_artifact(file)
        enqueue_file_retrieval_sync(db, file=file, operation=RagSyncOperation.DELETE)
    return [file.storage_key for file in files_to_delete]


def purge_file_retrieval_artifact(file: FileManagerFile) -> None:
    """Remove derived searchable content as part of the soft-delete transaction."""

    file.extraction_status = "pending"
    file.extraction_content_checksum = None
    file.extraction_text = None
    file.extraction_blocks = []
    file.extraction_metadata = {}
    file.extraction_error_code = None
    file.extracted_at = None


def build_archive(
    db: Session,
    *,
    user: User,
    file_ids: Iterable[str],
    folder_ids: Iterable[str],
) -> SpooledTemporaryFile[bytes]:
    entries = list_archive_entries(
        db,
        user=user,
        file_ids=file_ids,
        folder_ids=folder_ids,
    )
    _ensure_archive_within_limits(entries)
    archive_file: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(
        max_size=ARCHIVE_SPOOL_LIMIT_BYTES
    )
    try:
        with ZipFile(archive_file, mode="w", compression=ZIP_DEFLATED, allowZip64=True) as archive:
            for entry in entries:
                if entry.file is None:
                    archive.writestr(ensure_directory_path(entry.archive_path), b"")
                    continue
                obj = file_storage.open_file_object(entry.file.storage_key)
                try:
                    with archive.open(entry.archive_path, mode="w") as target:
                        for chunk in obj.stream(ARCHIVE_CHUNK_BYTES):
                            target.write(chunk)
                finally:
                    obj.close()
                    obj.release_conn()
        archive_file.seek(0)
        return archive_file
    except Exception as exc:
        archive_file.close()
        raise localized_http_exception(
            status_code=502, code="files.storage_download_failed"
        ) from exc


def list_archive_entries(
    db: Session,
    *,
    user: User,
    file_ids: Iterable[str],
    folder_ids: Iterable[str],
) -> list[FileArchiveEntry]:
    selected_file_ids = _ordered_unique_ids(file_ids)
    selected_folder_ids = set(folder_ids)
    if not selected_file_ids and not selected_folder_ids:
        raise localized_http_exception(status_code=422, code="files.selection_required")

    accessible_folders = list_accessible_folders(db, user=user)
    accessible_folder_by_id = {folder.id: folder for folder in accessible_folders}
    for folder_id in selected_folder_ids:
        if folder_id not in accessible_folder_by_id:
            raise localized_http_exception(status_code=404, code="files.folder_not_found")

    accessible_plan_folders = [
        ArchivePlanFolder(id=folder.id, parent_id=folder.parent_id, name=folder.name)
        for folder in accessible_folders
    ]
    accessible_plan_files: list[ArchivePlanFile] = []

    accessible_files: list[FileManagerFile] = []
    if selected_folder_ids:
        accessible_files = list_accessible_files(
            db,
            user=user,
            accessible_folder_ids=set(accessible_folder_by_id),
        )
        accessible_plan_files = [
            ArchivePlanFile(id=file.id, folder_id=file.folder_id, filename=file.filename)
            for file in accessible_files
        ]

    selected_files: list[FileManagerFile] = []
    for file_id in selected_file_ids:
        file = require_file_access(db, user=user, file_id=file_id)
        selected_files.append(file)

    file_by_id = {file.id: file for file in selected_files}
    if selected_folder_ids:
        file_by_id.update({file.id: file for file in accessible_files})

    planned_entries = plan_archive_entries(
        selected_folder_ids=selected_folder_ids,
        folders=accessible_plan_folders,
        folder_files=accessible_plan_files,
        selected_files=[
            ArchivePlanFile(id=file.id, folder_id=file.folder_id, filename=file.filename)
            for file in selected_files
        ],
    )
    entries = [
        FileArchiveEntry(entry.archive_path, file_by_id[entry.file_id] if entry.file_id else None)
        for entry in planned_entries
    ]

    if not entries:
        raise localized_http_exception(status_code=404, code="files.file_not_found")
    return entries


def _ordered_unique_ids(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _ensure_archive_within_limits(entries: list[FileArchiveEntry]) -> None:
    file_entries = [entry for entry in entries if entry.file is not None]
    total_size = sum(entry.file.size_bytes for entry in file_entries if entry.file is not None)
    if len(file_entries) > MAX_ARCHIVE_FILE_COUNT or total_size > MAX_ARCHIVE_TOTAL_SIZE:
        raise localized_http_exception(
            status_code=413,
            code="files.archive_limit_exceeded",
            limit_files=MAX_ARCHIVE_FILE_COUNT,
            limit_mb=MAX_ARCHIVE_TOTAL_SIZE // (1024 * 1024),
        )


def remove_storage_objects(db: Session, storage_keys: Iterable[str]) -> None:
    keys = list(storage_keys)
    if not keys:
        return
    for failure in file_storage.remove_file_objects(keys):
        logger.warning(
            "file_manager_storage_cleanup_failed",
            extra={"error_type": type(failure.exc).__name__},
        )
        enqueue_storage_cleanup_job(
            db,
            failure.storage_key,
            error=f"initial_delete:{type(failure.exc).__name__}",
        )


def remove_storage_object_immediately(storage_key: str) -> None:
    try:
        file_storage.remove_file_object(storage_key)
    except Exception as error:
        logger.warning(
            "file_manager_storage_cleanup_failed_after_upload_rollback",
            extra={"error_type": type(error).__name__},
        )


def enqueue_storage_cleanup_job(db: Session, storage_key: str, *, error: str | None = None) -> None:
    db.add(
        FileManagerStorageCleanupJob(
            id=new_id(),
            storage_key=storage_key,
            status="pending",
            attempts=1,
            last_error=error[:2000] if error else None,
            next_retry_at=utcnow_naive(),
        )
    )


def require_file_access(
    db: Session,
    *,
    user: User,
    file_id: str,
) -> FileManagerFile:
    file = db.scalar(
        select(FileManagerFile)
        .options(joinedload(FileManagerFile.owner))
        .where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    if file is None:
        raise localized_http_exception(status_code=404, code="files.file_not_found")
    if file.corpus_id is not None:
        corpus = db.get(FileManagerCorpus, file.corpus_id)
        if corpus is None:
            raise localized_http_exception(status_code=403, code="files.file_access_required")
        scope_allowed = corpus.access_scope_kind == "company"
        if not scope_allowed:
            raise localized_http_exception(status_code=403, code="files.file_access_required")
        if corpus.authorization_mode == "explicit_grants" and file.id not in (
            authorize_explicit_file_ids(
                db,
                file_ids=(file.id,),
                user_id=user.id,
            )
        ):
            raise localized_http_exception(status_code=403, code="files.file_access_required")
        return file
    is_admin = is_corpus_admin(db, user=user)
    if not _record_visible(file.visibility, file.owner_id, user=user, is_admin=is_admin):
        raise localized_http_exception(status_code=403, code="files.file_access_required")
    if file.folder_id is not None:
        accessible_folder_ids = {folder.id for folder in list_accessible_folders(db, user=user)}
        if file.folder_id not in accessible_folder_ids:
            raise localized_http_exception(status_code=403, code="files.file_access_required")
    return file


def _resolve_file_corpus_for_ingest(
    db: Session,
    *,
    user: User,
    requested_corpus_id: str | None,
    parent: FileManagerFolder | None,
    locked_corpora: dict[str, FileManagerCorpus],
    operator_ingest_run_id: str | None,
) -> FileManagerCorpus | None:
    normalized_requested_id = str(requested_corpus_id or "").strip() or None
    parent_corpus_id = parent.corpus_id if parent is not None else None
    if parent is not None and normalized_requested_id is not None:
        if parent_corpus_id is None or parent_corpus_id != normalized_requested_id:
            raise FileCorpusConflict("file corpus must match the parent folder corpus")
    effective_corpus_id = normalized_requested_id or parent_corpus_id
    if effective_corpus_id is None:
        return None
    corpus = locked_corpora.get(effective_corpus_id)
    if corpus is None:
        raise FileCorpusNotFound(effective_corpus_id)
    partition = db.scalar(
        select(RetrievalPartition)
        .where(RetrievalPartition.id == corpus.retrieval_partition_id)
        .execution_options(populate_existing=True)
    )
    if partition is None:
        raise FileCorpusConflict("file corpus partition is missing")
    _validate_file_corpus_partition(corpus, partition)
    if corpus.source_managed:
        raise FileCorpusAccessDenied(
            "source-managed file corpus requires the external source lifecycle"
        )
    if corpus.access_scope_kind == "company" and not _is_current_platform_admin(db, user.id):
        raise FileCorpusAccessDenied("company file corpus ingestion requires platform admin")
    _validate_operator_managed_ingress(
        db,
        corpus=corpus,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if parent is not None and parent.retrieval_partition_id != corpus.retrieval_partition_id:
        raise FileCorpusConflict("parent folder partition does not match file corpus")
    return corpus


def _prepare_file_corpus_ingress(
    db: Session,
    *,
    user: User,
    requested_corpus_id: str | None,
    parent_id: str | None,
    operator_ingest_run_id: str | None = None,
) -> tuple[FileManagerFolder | None, FileManagerCorpus | None, str]:
    """Lock aggregate gates before the parent row, matching tree deletion lock order."""
    _require_current_mutation_context(db, user_id=user.id)
    requested = str(requested_corpus_id or "").strip() or None
    parent_binding = (
        db.execute(
            select(FileManagerFolder.corpus_id, FileManagerFolder.retrieval_partition_id).where(
                FileManagerFolder.id == parent_id, FileManagerFolder.deleted_at.is_(None)
            )
        ).one_or_none()
        if parent_id
        else None
    )
    if parent_id and parent_binding is None:
        raise localized_http_exception(status_code=404, code="files.folder_not_found")
    locked_corpora = _lock_file_corpora(
        db, (requested, parent_binding.corpus_id if parent_binding else None), lock_mode="shared"
    )
    standalone_partition = None
    if not requested and (parent_binding is None or parent_binding.corpus_id is None):
        standalone_partition = ensure_default_partition(
            db, source_namespace="files", candidate_scope_kind="company"
        )
    gate_ids = (
        [parent_binding.retrieval_partition_id]
        if parent_binding and parent_binding.corpus_id is None
        else ([standalone_partition.id] if standalone_partition else [])
    )
    locked_partitions = _lock_retrieval_partitions(db, gate_ids, lock_mode="shared")
    parent = None
    if parent_id:
        parent = _load_folder(db, folder_id=parent_id, lock_mode="shared")
        _ensure_can_manage_record(
            db,
            user=user,
            owner_id=parent.owner_id,
            error_code="files.parent_manage_access_required",
        )
        _validate_locked_child_corpus(
            parent, locked_corpora, locked_standalone_partitions=locked_partitions
        )
    corpus = _resolve_file_corpus_for_ingest(
        db,
        user=user,
        requested_corpus_id=requested,
        parent=parent,
        locked_corpora=locked_corpora,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if corpus:
        return parent, corpus, corpus.retrieval_partition_id
    bound_id = (
        parent.retrieval_partition_id
        if parent
        else (standalone_partition.id if standalone_partition else None)
    )
    return (
        parent,
        None,
        _require_locked_default_file_partition(locked_partitions, bound_partition_id=bound_id).id,
    )


def _validate_operator_managed_ingress(
    db: Session,
    *,
    corpus: FileManagerCorpus,
    operator_ingest_run_id: str | None,
) -> None:
    normalized_run_id = str(operator_ingest_run_id or "").strip() or None
    if not corpus.operator_managed:
        if normalized_run_id is not None:
            raise FileCorpusConflict("operator ingest run requires an operator-managed corpus")
        return
    if normalized_run_id is None:
        raise FileCorpusAccessDenied("operator-managed corpus requires an ingest run")
    run = db.scalar(
        select(FileManagerBulkIngestRun).where(
            FileManagerBulkIngestRun.id == normalized_run_id,
            FileManagerBulkIngestRun.corpus_id == corpus.id,
        )
    )
    if run is None:
        raise FileCorpusAccessDenied("operator ingest run does not match the corpus")
    if run.status != "ingesting":
        raise FileCorpusConflict("operator ingest run is not ingesting")


def _lock_file_corpora(
    db: Session,
    corpus_ids: Iterable[str | None],
    *,
    lock_mode: FileCorpusLockMode,
) -> dict[str, FileManagerCorpus]:
    """Acquire corpus locks in one global order for the surrounding transaction."""

    normalized_ids = sorted(
        {normalized for corpus_id in corpus_ids if (normalized := str(corpus_id or "").strip())}
    )
    locked: dict[str, FileManagerCorpus] = {}
    for corpus_id in normalized_ids:
        statement = select(FileManagerCorpus).where(FileManagerCorpus.id == corpus_id)
        statement = statement.with_for_update(read=lock_mode == "shared")
        corpus = db.scalar(statement.execution_options(populate_existing=True))
        if corpus is None:
            raise FileCorpusNotFound(corpus_id)
        locked[corpus_id] = corpus
    return locked


def _lock_retrieval_partitions(
    db: Session,
    partition_ids: Iterable[str | None],
    *,
    lock_mode: FileCorpusLockMode,
) -> dict[str, RetrievalPartition]:
    """Lock legacy/default Files partition gates after corpus locks."""

    normalized_ids = sorted(
        {
            normalized
            for partition_id in partition_ids
            if (normalized := str(partition_id or "").strip())
        }
    )
    locked: dict[str, RetrievalPartition] = {}
    for partition_id in normalized_ids:
        statement = select(RetrievalPartition).where(
            RetrievalPartition.id == partition_id,
            RetrievalPartition.source_namespace == "files",
        )
        statement = statement.with_for_update(read=lock_mode == "shared")
        partition = db.scalar(statement.execution_options(populate_existing=True))
        if partition is None:
            raise FileCorpusConflict("file retrieval partition gate is missing")
        locked[partition_id] = partition
    return locked


def _resolve_standalone_partition_gate_ids(
    db: Session, bindings: Iterable[tuple[str | None, str | None]]
) -> list[str]:
    partition_ids: list[str] = []
    for corpus_id, partition_id in bindings:
        if corpus_id is not None:
            continue
        if not partition_id:
            raise FileCorpusConflict("standalone file partition binding is missing")
        partition_ids.append(partition_id)
    return partition_ids


def _validate_default_file_partition(partition: RetrievalPartition) -> None:
    if (
        partition.source_namespace != "files"
        or not partition.is_default_ingest
        or partition.state != RetrievalPartitionState.ACTIVE.value
        or partition.candidate_scope_kind != "company"
        or partition.candidate_user_id is not None
    ):
        raise FileCorpusConflict("invalid standalone Files partition")


def _require_locked_default_file_partition(
    locked_partitions: dict[str, RetrievalPartition], *, bound_partition_id: str | None
) -> RetrievalPartition:
    if not bound_partition_id or bound_partition_id not in locked_partitions:
        raise FileCorpusConflict("standalone Files partition was not locked")
    partition = locked_partitions[bound_partition_id]
    _validate_default_file_partition(partition)
    return partition


def _lock_corpora_for_children(
    db: Session,
    *,
    folder_ids: Iterable[str] = (),
    file_ids: Iterable[str] = (),
    lock_mode: FileCorpusLockMode,
) -> tuple[dict[str, FileManagerCorpus], dict[str, RetrievalPartition]]:
    """Discover immutable child bindings, then lock their corpora before reloading children."""

    normalized_folder_ids = tuple(sorted(set(folder_ids)))
    normalized_file_ids = tuple(sorted(set(file_ids)))
    bindings: list[tuple[str | None, str | None]] = []
    if normalized_folder_ids:
        bindings.extend(
            db.execute(
                select(
                    FileManagerFolder.corpus_id,
                    FileManagerFolder.retrieval_partition_id,
                ).where(
                    FileManagerFolder.id.in_(normalized_folder_ids),
                    FileManagerFolder.deleted_at.is_(None),
                )
            ).all()
        )
    if normalized_file_ids:
        bindings.extend(
            db.execute(
                select(
                    FileManagerFile.corpus_id,
                    FileManagerFile.retrieval_partition_id,
                ).where(
                    FileManagerFile.id.in_(normalized_file_ids),
                    FileManagerFile.deleted_at.is_(None),
                )
            ).all()
        )
    corpus_ids = [corpus_id for corpus_id, _partition_id in bindings if corpus_id]
    locked_corpora = _lock_file_corpora(db, corpus_ids, lock_mode=lock_mode)
    standalone_partition_ids = _resolve_standalone_partition_gate_ids(db, bindings)
    locked_standalone_partitions = _lock_retrieval_partitions(
        db,
        standalone_partition_ids,
        lock_mode=lock_mode,
    )
    return locked_corpora, locked_standalone_partitions


def _validate_locked_child_corpus(
    child: FileManagerFolder | FileManagerFile,
    locked_corpora: dict[str, FileManagerCorpus],
    *,
    locked_standalone_partitions: dict[str, RetrievalPartition] | None = None,
) -> None:
    if child.corpus_id is None:
        if locked_standalone_partitions is None:
            raise FileCorpusConflict("legacy file partition gates were not provided")
        _require_locked_default_file_partition(
            locked_standalone_partitions,
            bound_partition_id=child.retrieval_partition_id,
        )
        return
    corpus = locked_corpora.get(child.corpus_id)
    if corpus is None:
        raise FileCorpusConflict("file child corpus was not locked before mutation")
    if corpus.source_managed:
        raise FileCorpusAccessDenied(
            "source-managed file corpus requires the external source lifecycle"
        )
    if child.retrieval_partition_id != corpus.retrieval_partition_id:
        raise FileCorpusConflict("file child does not match its current corpus metadata")


def _validate_file_corpus_partition(
    corpus: FileManagerCorpus, partition: RetrievalPartition
) -> None:
    if (
        partition.source_namespace != "files"
        or partition.is_default_ingest
        or partition.state != RetrievalPartitionState.ACTIVE.value
        or corpus.access_scope_kind != "company"
        or partition.candidate_scope_kind != "company"
        or partition.candidate_user_id is not None
        or partition.metadata_version != corpus.metadata_version
    ):
        raise FileCorpusConflict("file corpus partition metadata does not match its source")


def _is_current_active_user(db: Session, user_id: str) -> bool:
    return (
        db.scalar(
            select(User.id).where(
                User.id == user_id,
                User.status == "active",
                User.login_blocked.is_(False),
            )
        )
        is not None
    )


def _require_current_active_user(db: Session, user_id: str) -> None:
    if not _is_current_active_user(db, user_id):
        raise FileCorpusAccessDenied("active, unblocked file actor is required")


def _require_current_mutation_context(db: Session, *, user_id: str) -> None:
    _require_current_active_user(db, user_id)
    if not can_use_app(db, user_id=user_id, app_id="files"):
        raise FileCorpusAccessDenied("current Files app access is required")


def _is_current_corpus_admin(db: Session, *, user_id: str) -> bool:
    return is_current_platform_admin(db, user_id) and can_use_app(
        db, user_id=user_id, app_id="files"
    )


def _is_current_platform_admin(db: Session, user_id: str) -> bool:
    return is_current_platform_admin(db, user_id)


def _load_folder(
    db: Session,
    *,
    folder_id: str,
    lock_mode: FileChildLockMode | None = None,
) -> FileManagerFolder:
    statement = select(FileManagerFolder)
    if lock_mode is None:
        statement = statement.options(joinedload(FileManagerFolder.owner))
    statement = statement.where(
        FileManagerFolder.id == folder_id,
        FileManagerFolder.deleted_at.is_(None),
    )
    if lock_mode is not None:
        statement = statement.with_for_update(read=lock_mode == "shared").execution_options(
            populate_existing=True
        )
    folder = db.scalar(statement)
    if folder is None:
        raise localized_http_exception(status_code=404, code="files.folder_not_found")
    return folder


def _load_file(
    db: Session,
    *,
    file_id: str,
    lock_mode: FileChildLockMode | None = None,
) -> FileManagerFile:
    statement = select(FileManagerFile)
    if lock_mode is None:
        statement = statement.options(joinedload(FileManagerFile.owner))
    statement = statement.where(
        FileManagerFile.id == file_id,
        FileManagerFile.deleted_at.is_(None),
    )
    if lock_mode is not None:
        statement = statement.with_for_update(read=lock_mode == "shared").execution_options(
            populate_existing=True
        )
    file = db.scalar(statement)
    if file is None:
        raise localized_http_exception(status_code=404, code="files.file_not_found")
    return file


def _discover_file_delete_scope(
    db: Session,
    *,
    selected_folder_ids: Iterable[str],
    selected_file_ids: Iterable[str],
) -> _FileDeleteScope:
    requested_folder_ids = set(selected_folder_ids)
    requested_file_ids = set(selected_file_ids)
    root_rows = (
        db.execute(
            select(
                FileManagerFolder.id,
                FileManagerFolder.corpus_id,
                FileManagerFolder.retrieval_partition_id,
            )
            .where(
                FileManagerFolder.id.in_(requested_folder_ids),
                FileManagerFolder.deleted_at.is_(None),
            )
            .order_by(FileManagerFolder.id.asc())
        ).all()
        if requested_folder_ids
        else []
    )
    if {row.id for row in root_rows} != requested_folder_ids:
        raise localized_http_exception(status_code=404, code="files.folder_not_found")

    discovered_folder_ids = {row.id for row in root_rows}
    corpus_ids = {row.corpus_id for row in root_rows if row.corpus_id is not None}
    standalone_partition_ids: set[str] = set()
    for row in root_rows:
        if row.corpus_id is not None:
            continue
        if row.retrieval_partition_id is None:
            continue
        standalone_partition_ids.add(row.retrieval_partition_id)
    frontier = set(discovered_folder_ids)
    while frontier:
        child_rows = db.execute(
            select(
                FileManagerFolder.id,
                FileManagerFolder.corpus_id,
                FileManagerFolder.retrieval_partition_id,
            )
            .where(
                FileManagerFolder.parent_id.in_(frontier),
                FileManagerFolder.deleted_at.is_(None),
            )
            .order_by(FileManagerFolder.id.asc())
        ).all()
        next_frontier = {row.id for row in child_rows} - discovered_folder_ids
        corpus_ids.update(row.corpus_id for row in child_rows if row.corpus_id is not None)
        for row in child_rows:
            if row.corpus_id is not None:
                continue
            if row.retrieval_partition_id is None:
                continue
            standalone_partition_ids.add(row.retrieval_partition_id)
        discovered_folder_ids.update(next_frontier)
        frontier = next_frontier

    file_predicates = []
    if requested_file_ids:
        file_predicates.append(FileManagerFile.id.in_(requested_file_ids))
    if discovered_folder_ids:
        file_predicates.append(FileManagerFile.folder_id.in_(discovered_folder_ids))
    file_rows = (
        db.execute(
            select(
                FileManagerFile.id,
                FileManagerFile.corpus_id,
                FileManagerFile.retrieval_partition_id,
            )
            .where(
                FileManagerFile.deleted_at.is_(None),
                or_(*file_predicates),
            )
            .order_by(FileManagerFile.id.asc())
        ).all()
        if file_predicates
        else []
    )
    discovered_file_ids = {row.id for row in file_rows}
    if not requested_file_ids.issubset(discovered_file_ids):
        raise localized_http_exception(status_code=404, code="files.file_not_found")
    corpus_ids.update(row.corpus_id for row in file_rows if row.corpus_id is not None)
    for row in file_rows:
        if row.corpus_id is not None:
            continue
        if row.retrieval_partition_id is None:
            continue
        standalone_partition_ids.add(row.retrieval_partition_id)
    return _FileDeleteScope(
        folder_ids=tuple(sorted(discovered_folder_ids)),
        file_ids=tuple(sorted(discovered_file_ids)),
        corpus_ids=tuple(sorted(corpus_ids)),
        standalone_partition_ids=tuple(sorted(standalone_partition_ids)),
    )


def _lock_tree_delete_scope(
    db: Session,
    *,
    selected_folder_ids: Iterable[str],
    selected_file_ids: Iterable[str],
) -> tuple[list[FileManagerFolder], list[FileManagerFile]]:
    """Lock corpora, then the actual folder/file tree in one global order."""

    initial_scope = _discover_file_delete_scope(
        db,
        selected_folder_ids=selected_folder_ids,
        selected_file_ids=selected_file_ids,
    )
    locked_corpora = _lock_file_corpora(
        db,
        initial_scope.corpus_ids,
        lock_mode="exclusive",
    )
    initial_standalone_partition_ids = initial_scope.standalone_partition_ids
    locked_standalone_partitions = _lock_retrieval_partitions(
        db,
        initial_standalone_partition_ids,
        lock_mode="exclusive",
    )
    current_scope = _discover_file_delete_scope(
        db,
        selected_folder_ids=selected_folder_ids,
        selected_file_ids=selected_file_ids,
    )
    unlocked_corpus_ids = set(current_scope.corpus_ids) - set(locked_corpora)
    if unlocked_corpus_ids:
        raise FileCorpusConflict("file delete scope gained an unlocked corpus")
    current_standalone_partition_ids = set(current_scope.standalone_partition_ids)
    unlocked_standalone_partition_ids = current_standalone_partition_ids - set(
        locked_standalone_partitions
    )
    if unlocked_standalone_partition_ids:
        raise FileCorpusConflict("file delete scope gained an unlocked legacy partition")

    folders = list(
        db.scalars(
            select(FileManagerFolder)
            .where(
                FileManagerFolder.id.in_(current_scope.folder_ids),
                FileManagerFolder.deleted_at.is_(None),
            )
            .order_by(FileManagerFolder.id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if {folder.id for folder in folders} != set(current_scope.folder_ids):
        raise localized_http_exception(status_code=404, code="files.folder_not_found")

    files = list(
        db.scalars(
            select(FileManagerFile)
            .where(
                FileManagerFile.id.in_(current_scope.file_ids),
                FileManagerFile.deleted_at.is_(None),
            )
            .order_by(FileManagerFile.id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if {file.id for file in files} != set(current_scope.file_ids):
        raise localized_http_exception(status_code=404, code="files.file_not_found")

    for child in [*folders, *files]:
        _validate_locked_child_corpus(
            child,
            locked_corpora,
            locked_standalone_partitions=locked_standalone_partitions,
        )
    return folders, files


def _lock_leaf_files_for_delete(
    db: Session,
    *,
    selected_file_ids: Iterable[str],
) -> list[FileManagerFile]:
    """Use shared corpus locks for leaf-only deletes and sorted exclusive row locks."""

    initial_scope = _discover_file_delete_scope(
        db,
        selected_folder_ids=(),
        selected_file_ids=selected_file_ids,
    )
    locked_corpora = _lock_file_corpora(
        db,
        initial_scope.corpus_ids,
        lock_mode="shared",
    )
    initial_standalone_partition_ids = initial_scope.standalone_partition_ids
    locked_standalone_partitions = _lock_retrieval_partitions(
        db,
        initial_standalone_partition_ids,
        lock_mode="shared",
    )
    files = list(
        db.scalars(
            select(FileManagerFile)
            .where(
                FileManagerFile.id.in_(initial_scope.file_ids),
                FileManagerFile.deleted_at.is_(None),
            )
            .order_by(FileManagerFile.id.asc())
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    if {file.id for file in files} != set(initial_scope.file_ids):
        raise localized_http_exception(status_code=404, code="files.file_not_found")
    for file in files:
        _validate_locked_child_corpus(
            file,
            locked_corpora,
            locked_standalone_partitions=locked_standalone_partitions,
        )
    return files


def _record_visible(
    visibility: str,
    owner_id: str,
    *,
    user: User,
    is_admin: bool,
) -> bool:
    return owner_id == user.id or visibility == "company"


def _ensure_can_manage_record(
    db: Session,
    *,
    user: User,
    owner_id: str,
    error_code: str = "files.delete_access_required",
) -> None:
    _require_current_mutation_context(
        db,
        user_id=user.id,
    )
    if owner_id == user.id:
        return
    raise localized_http_exception(status_code=403, code=error_code)


def _normalize_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise localized_http_exception(status_code=422, code="files.name_required")
    return name[:255]
