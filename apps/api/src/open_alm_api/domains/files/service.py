from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Literal
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, joinedload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import (
    User,
    Workspace,
    WorkspaceUserBinding,
)
from open_alm_api.domains.auth.roles import workspace_role_allows
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.files import storage_adapter as file_storage
from open_alm_api.domains.files.external_access import (
    authorize_explicit_file_ids,
    is_current_platform_admin,
)
from open_alm_api.domains.files.archive_planner import (
    ArchivePlanFile,
    ArchivePlanFolder,
    ensure_directory_path,
    plan_archive_entries,
    safe_filename,
)
from open_alm_api.domains.files.models import (
    FileManagerBulkIngestRun,
    FileManagerCorpus,
    FileManagerCorpusTransitionAudit,
    FileManagerFile,
    FileManagerFolder,
    FileManagerStorageCleanupJob,
)
from open_alm_api.domains.files.rag_sync import enqueue_file_retrieval_sync
from open_alm_api.domains.rag.contracts import RagSyncOperation
from open_alm_api.domains.retrieval.models import RetrievalPartition, RetrievalPartitionState
from open_alm_api.domains.retrieval.partitioning import (
    create_managed_partition,
    ensure_default_partition,
)


FILE_VISIBILITIES = frozenset({"private", "workspace"})
FILE_CORPUS_ACCESS_SCOPE_KINDS = frozenset({"workspace", "company"})
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
    legacy_partition_ids: tuple[str, ...]
    legacy_workspace_ids: tuple[str, ...]


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


def is_workspace_admin(db: Session, *, workspace: Workspace, user: User) -> bool:
    if not _is_current_active_user(db, user.id) or not _is_current_active_workspace(
        db, workspace.id
    ):
        return False
    return _is_current_workspace_admin(db, user_id=user.id, workspace_id=workspace.id)


def normalize_visibility(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in FILE_VISIBILITIES:
        raise localized_http_exception(status_code=422, code="files.invalid_visibility")
    return normalized


def create_file_corpus(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    name: str,
) -> FileManagerCorpus:
    """Create a workspace-managed corpus with its own stable partition."""

    if not is_workspace_admin(db, workspace=workspace, user=user):
        raise FileCorpusAccessDenied("file corpus creation requires workspace admin")
    partition = create_managed_partition(
        db,
        source_namespace="files",
        managed_workspace_id=workspace.id,
        candidate_scope_kind="workspace",
        workspace_id=workspace.id,
    )
    corpus = FileManagerCorpus(
        id=new_id(),
        name=_normalize_name(name),
        managed_workspace_id=workspace.id,
        access_scope_kind="workspace",
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
    workspace: Workspace,
    user: User,
) -> list[FileManagerCorpus]:
    if not is_workspace_admin(db, workspace=workspace, user=user):
        raise FileCorpusAccessDenied("file corpus listing requires workspace admin")
    return list(
        db.scalars(
            select(FileManagerCorpus)
            .where(FileManagerCorpus.managed_workspace_id == workspace.id)
            .order_by(FileManagerCorpus.created_at.asc(), FileManagerCorpus.id.asc())
        ).all()
    )


def require_managed_file_corpus(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    corpus_id: str,
) -> FileManagerCorpus:
    if not is_workspace_admin(db, workspace=workspace, user=user):
        raise FileCorpusAccessDenied("file corpus management requires workspace admin")
    corpus = db.scalar(
        select(FileManagerCorpus).where(
            FileManagerCorpus.id == corpus_id,
            FileManagerCorpus.managed_workspace_id == workspace.id,
        )
    )
    if corpus is None:
        raise FileCorpusNotFound(corpus_id)
    return corpus


def transition_file_corpus(
    db: Session,
    *,
    corpus_id: str,
    actor: User,
    expected_metadata_version: int,
    access_scope_kind: str,
    reason: str,
    target_workspace_id: str | None = None,
    request_id: str | None = None,
) -> FileManagerCorpus:
    """Move a corpus ACL envelope without touching derived or stored content."""

    target_scope = _normalize_corpus_access_scope(access_scope_kind)
    normalized_reason = _normalize_corpus_transition_reason(reason)
    normalized_request_id = str(request_id or "").strip()[:128] or None
    corpus = _lock_file_corpora(db, (corpus_id,), lock_mode="exclusive")[corpus_id]
    _require_current_active_user(db, actor.id)
    partition = db.scalar(
        select(RetrievalPartition)
        .where(RetrievalPartition.id == corpus.retrieval_partition_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if partition is None:
        raise FileCorpusConflict("file corpus partition is missing")
    _validate_file_corpus_partition(corpus, partition)
    if (
        corpus.metadata_version != expected_metadata_version
        or partition.metadata_version != expected_metadata_version
    ):
        raise FileCorpusConflict("file corpus metadata version does not match")
    if corpus.source_managed:
        raise FileCorpusConflict(
            "source-managed corpus scope is immutable outside its source binding"
        )

    source_workspace = _load_active_workspace(db, corpus.managed_workspace_id)
    if target_scope == "company":
        if target_workspace_id is not None:
            raise FileCorpusConflict("company corpus cannot declare target workspace")
        target_workspace = source_workspace
    else:
        if target_workspace_id is None:
            raise FileCorpusConflict("workspace corpus requires target workspace")
        target_workspace = _load_active_workspace(db, target_workspace_id)

    _authorize_file_corpus_transition(
        db,
        corpus=corpus,
        actor=actor,
        source_workspace=source_workspace,
        target_workspace=target_workspace,
        target_scope=target_scope,
    )
    if (
        corpus.access_scope_kind == target_scope
        and corpus.managed_workspace_id == target_workspace.id
    ):
        return corpus

    from_scope = corpus.access_scope_kind
    from_workspace_id = corpus.managed_workspace_id
    next_version = corpus.metadata_version + 1
    partition.managed_workspace_id = target_workspace.id
    partition.candidate_scope_kind = target_scope
    partition.candidate_workspace_id = target_workspace.id if target_scope == "workspace" else None
    partition.candidate_user_id = None
    partition.metadata_version = next_version
    corpus.managed_workspace_id = target_workspace.id
    corpus.access_scope_kind = target_scope
    corpus.metadata_version = next_version
    audit = FileManagerCorpusTransitionAudit(
        id=new_id(),
        corpus_id=corpus.id,
        actor_id=actor.id,
        reason=normalized_reason,
        request_id=normalized_request_id,
        from_access_scope_kind=from_scope,
        to_access_scope_kind=target_scope,
        from_managed_workspace_id=from_workspace_id,
        to_managed_workspace_id=target_workspace.id,
        from_metadata_version=expected_metadata_version,
        to_metadata_version=next_version,
    )
    db.add_all([partition, corpus, audit])
    db.flush()

    if source_workspace.id != target_workspace.id:
        changed_at = utcnow_naive()
        db.execute(
            update(FileManagerFolder)
            .where(FileManagerFolder.corpus_id == corpus.id)
            .values(workspace_id=target_workspace.id, updated_at=changed_at)
        )
        db.execute(
            update(FileManagerFile)
            .where(FileManagerFile.corpus_id == corpus.id)
            .values(workspace_id=target_workspace.id, updated_at=changed_at)
        )
    db.flush()
    return corpus


def list_accessible_folders(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
) -> list[FileManagerFolder]:
    is_admin = is_workspace_admin(db, workspace=workspace, user=user)
    folders = list(
        db.scalars(
            select(FileManagerFolder)
            .options(joinedload(FileManagerFolder.owner))
            .where(
                FileManagerFolder.workspace_id == workspace.id,
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
    workspace: Workspace,
    user: User,
    accessible_folder_ids: set[str],
) -> list[FileManagerFile]:
    is_admin = is_workspace_admin(db, workspace=workspace, user=user)
    files = list(
        db.scalars(
            select(FileManagerFile)
            .options(joinedload(FileManagerFile.owner))
            .where(
                FileManagerFile.workspace_id == workspace.id,
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
        workspace_id=workspace.id,
    )
    accessible: list[FileManagerFile] = []
    for file in files:
        if file.corpus_id is not None:
            corpus = corpora.get(file.corpus_id)
            if corpus is None:
                continue
            scope_allowed = corpus.access_scope_kind == "company" or (
                corpus.access_scope_kind == "workspace"
                and corpus.managed_workspace_id == workspace.id
            )
            if not scope_allowed:
                continue
            # The Files browser remains workspace-local because the source query
            # above is workspace-bound. Company corpora managed elsewhere remain
            # discoverable through company retrieval, not this workspace listing.
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
    workspace: Workspace,
    user: User,
    folder_id: str | None,
) -> FileManagerFolder | None:
    if folder_id is None:
        return None
    accessible = {
        folder.id: folder for folder in list_accessible_folders(db, workspace=workspace, user=user)
    }
    folder = accessible.get(folder_id)
    if folder is None:
        raise localized_http_exception(status_code=404, code="files.folder_not_found")
    return folder


def create_folder(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    name: str,
    parent_id: str | None,
    visibility: str,
    corpus_id: str | None = None,
    operator_ingest_run_id: str | None = None,
) -> FileManagerFolder:
    parent, corpus, retrieval_partition_id = _prepare_file_corpus_ingress(
        db,
        workspace=workspace,
        user=user,
        requested_corpus_id=corpus_id,
        parent_id=parent_id,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if parent is not None:
        _ensure_can_manage_record(
            db,
            workspace=workspace,
            user=user,
            owner_id=parent.owner_id,
            error_code="files.parent_manage_access_required",
        )
    if corpus is not None:
        effective_visibility = "workspace"
    elif parent is not None:
        effective_visibility = parent.visibility
    else:
        effective_visibility = normalize_visibility(visibility)
    folder = FileManagerFolder(
        id=new_id(),
        workspace_id=workspace.id,
        corpus_id=corpus.id if corpus is not None else None,
        parent_id=parent.id if parent else None,
        owner_id=user.id,
        name=_normalize_name(name),
        visibility=effective_visibility,
        retrieval_partition_id=retrieval_partition_id,
    )
    db.add(folder)
    db.flush()
    return folder


def update_folder(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    folder_id: str,
    name: str | None = None,
    visibility: str | None = None,
) -> FileManagerFolder:
    locked_corpora, locked_legacy_partitions = _lock_corpora_for_children(
        db,
        workspace_id=workspace.id,
        folder_ids=(folder_id,),
        lock_mode="shared",
    )
    folder = _load_folder_for_workspace(
        db,
        workspace=workspace,
        folder_id=folder_id,
        lock_mode="exclusive",
    )
    _validate_locked_child_corpus(
        folder,
        locked_corpora,
        locked_legacy_partitions=locked_legacy_partitions,
    )
    _ensure_can_manage_record(db, workspace=workspace, user=user, owner_id=folder.owner_id)
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
    workspace: Workspace,
    user: User,
    folder_id: str,
) -> list[str]:
    folders, files = _lock_tree_delete_scope(
        db,
        workspace_id=workspace.id,
        selected_folder_ids=(folder_id,),
        selected_file_ids=(),
    )
    _require_current_mutation_context(db, user_id=user.id, workspace_id=workspace.id)
    is_admin = _is_current_workspace_admin(
        db,
        user_id=user.id,
        workspace_id=workspace.id,
    )
    if not is_admin and (
        any(item.owner_id != user.id for item in folders)
        or any(item.owner_id != user.id for item in files)
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
    workspace: Workspace,
    user: User,
    filename: str | None,
    content_type: str | None,
    content: BinaryIO,
    size_bytes: int,
    folder_id: str | None,
    visibility: str,
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
        workspace=workspace,
        user=user,
        requested_corpus_id=corpus_id,
        parent_id=folder_id,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if folder is not None:
        _ensure_can_manage_record(
            db,
            workspace=workspace,
            user=user,
            owner_id=folder.owner_id,
            error_code="files.parent_manage_access_required",
        )
    if corpus is not None:
        effective_visibility = "workspace"
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
        workspace_id=workspace.id,
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
    workspace: Workspace,
    user: User,
    file_id: str,
) -> str:
    locked_corpora, locked_legacy_partitions = _lock_corpora_for_children(
        db,
        workspace_id=workspace.id,
        file_ids=(file_id,),
        lock_mode="shared",
    )
    file = _load_file_for_workspace(
        db,
        workspace=workspace,
        file_id=file_id,
        lock_mode="exclusive",
    )
    _validate_locked_child_corpus(
        file,
        locked_corpora,
        locked_legacy_partitions=locked_legacy_partitions,
    )
    _ensure_can_manage_record(db, workspace=workspace, user=user, owner_id=file.owner_id)
    file.deleted_at = utcnow_naive()
    purge_file_retrieval_artifact(file)
    db.add(file)
    enqueue_file_retrieval_sync(db, file=file, operation=RagSyncOperation.DELETE)
    return file.storage_key


def delete_items(
    db: Session,
    *,
    workspace: Workspace,
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
            workspace_id=workspace.id,
            selected_folder_ids=selected_folder_ids,
            selected_file_ids=selected_file_ids,
        )
    else:
        folders_to_delete = []
        files_to_delete = _lock_leaf_files_for_delete(
            db,
            workspace_id=workspace.id,
            selected_file_ids=selected_file_ids,
        )

    _require_current_mutation_context(db, user_id=user.id, workspace_id=workspace.id)
    is_admin = _is_current_workspace_admin(
        db,
        user_id=user.id,
        workspace_id=workspace.id,
    )
    if not is_admin and (
        any(folder.owner_id != user.id for folder in folders_to_delete)
        or any(file.owner_id != user.id for file in files_to_delete)
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
    workspace: Workspace,
    user: User,
    file_ids: Iterable[str],
    folder_ids: Iterable[str],
) -> SpooledTemporaryFile[bytes]:
    entries = list_archive_entries(
        db,
        workspace=workspace,
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
    workspace: Workspace,
    user: User,
    file_ids: Iterable[str],
    folder_ids: Iterable[str],
) -> list[FileArchiveEntry]:
    selected_file_ids = _ordered_unique_ids(file_ids)
    selected_folder_ids = set(folder_ids)
    if not selected_file_ids and not selected_folder_ids:
        raise localized_http_exception(status_code=422, code="files.selection_required")

    accessible_folders = list_accessible_folders(db, workspace=workspace, user=user)
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
            workspace=workspace,
            user=user,
            accessible_folder_ids=set(accessible_folder_by_id),
        )
        accessible_plan_files = [
            ArchivePlanFile(id=file.id, folder_id=file.folder_id, filename=file.filename)
            for file in accessible_files
        ]

    selected_files: list[FileManagerFile] = []
    for file_id in selected_file_ids:
        file = require_file_access(db, workspace=workspace, user=user, file_id=file_id)
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
    workspace: Workspace,
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
        scope_allowed = corpus.access_scope_kind == "company" or (
            corpus.access_scope_kind == "workspace" and corpus.managed_workspace_id == workspace.id
        )
        if not scope_allowed:
            raise localized_http_exception(status_code=403, code="files.file_access_required")
        if corpus.authorization_mode == "explicit_grants" and file.id not in (
            authorize_explicit_file_ids(
                db,
                file_ids=(file.id,),
                user_id=user.id,
                workspace_id=workspace.id,
            )
        ):
            raise localized_http_exception(status_code=403, code="files.file_access_required")
        return file
    if file.workspace_id != workspace.id:
        raise localized_http_exception(status_code=404, code="files.file_not_found")
    is_admin = is_workspace_admin(db, workspace=workspace, user=user)
    if not _record_visible(file.visibility, file.owner_id, user=user, is_admin=is_admin):
        raise localized_http_exception(status_code=403, code="files.file_access_required")
    if file.folder_id is not None:
        accessible_folder_ids = {
            folder.id for folder in list_accessible_folders(db, workspace=workspace, user=user)
        }
        if file.folder_id not in accessible_folder_ids:
            raise localized_http_exception(status_code=403, code="files.file_access_required")
    return file


def _resolve_file_corpus_for_ingest(
    db: Session,
    *,
    workspace: Workspace,
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
    if corpus is None or corpus.managed_workspace_id != workspace.id:
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
        workspace_id=workspace.id,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if parent is not None and parent.retrieval_partition_id != corpus.retrieval_partition_id:
        raise FileCorpusConflict("parent folder partition does not match file corpus")
    return corpus


def _prepare_file_corpus_ingress(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    requested_corpus_id: str | None,
    parent_id: str | None,
    operator_ingest_run_id: str | None = None,
) -> tuple[FileManagerFolder | None, FileManagerCorpus | None, str]:
    """Lock ingress gates before reloading and authorizing the prospective parent."""

    normalized_requested_id = str(requested_corpus_id or "").strip() or None
    discovered_parent_corpus_id = None
    discovered_parent_partition_id = None
    parent_binding = None
    if parent_id is not None:
        parent_binding = db.execute(
            select(
                FileManagerFolder.corpus_id,
                FileManagerFolder.retrieval_partition_id,
            ).where(
                FileManagerFolder.id == parent_id,
                FileManagerFolder.workspace_id == workspace.id,
                FileManagerFolder.deleted_at.is_(None),
            )
        ).one_or_none()
        if parent_binding is not None:
            discovered_parent_corpus_id = parent_binding.corpus_id
            discovered_parent_partition_id = parent_binding.retrieval_partition_id

    locked_corpora = _lock_file_corpora(
        db,
        (normalized_requested_id, discovered_parent_corpus_id),
        lock_mode="shared",
    )
    legacy_bindings: list[tuple[str | None, str | None, str]] = []
    if parent_binding is not None and discovered_parent_corpus_id is None:
        legacy_bindings.append(
            (
                None,
                discovered_parent_partition_id,
                workspace.id,
            )
        )
    elif parent_id is None and normalized_requested_id is None:
        legacy_bindings.append((None, None, workspace.id))
    legacy_partition_ids = _resolve_legacy_partition_gate_ids(db, legacy_bindings)
    locked_legacy_partitions = _lock_retrieval_partitions(
        db,
        legacy_partition_ids,
        lock_mode="shared",
    )

    parent = None
    if parent_id is not None:
        _load_folder_for_workspace(
            db,
            workspace=workspace,
            folder_id=parent_id,
            lock_mode="shared",
        )
    _require_current_mutation_context(db, user_id=user.id, workspace_id=workspace.id)
    if parent_id is not None:
        parent = require_folder_access(
            db,
            workspace=workspace,
            user=user,
            folder_id=parent_id,
        )
        if parent.corpus_id is not None and parent.corpus_id not in locked_corpora:
            raise FileCorpusConflict("parent folder corpus changed during authorization")
        _validate_locked_child_corpus(
            parent,
            locked_corpora,
            locked_legacy_partitions=locked_legacy_partitions,
        )

    corpus = _resolve_file_corpus_for_ingest(
        db,
        workspace=workspace,
        user=user,
        requested_corpus_id=normalized_requested_id,
        parent=parent,
        locked_corpora=locked_corpora,
        operator_ingest_run_id=operator_ingest_run_id,
    )
    if corpus is not None:
        retrieval_partition_id = corpus.retrieval_partition_id
    else:
        bound_partition_id = parent.retrieval_partition_id if parent is not None else None
        retrieval_partition_id = _require_locked_default_file_partition(
            locked_legacy_partitions,
            workspace_id=workspace.id,
            bound_partition_id=bound_partition_id,
        ).id
    return parent, corpus, retrieval_partition_id


def _validate_operator_managed_ingress(
    db: Session,
    *,
    corpus: FileManagerCorpus,
    workspace_id: str,
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
            FileManagerBulkIngestRun.workspace_id == workspace_id,
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


def _resolve_legacy_partition_gate_ids(
    db: Session,
    bindings: Iterable[tuple[str | None, str | None, str]],
) -> list[str]:
    """Resolve logical default gates for legacy rows without writing their bindings."""

    partition_ids: list[str] = []
    for corpus_id, partition_id, workspace_id in bindings:
        if corpus_id is not None:
            continue
        default_partition = ensure_default_partition(
            db,
            source_namespace="files",
            candidate_scope_kind="workspace",
            workspace_id=workspace_id,
        )
        normalized_partition_id = str(partition_id or "").strip()
        if normalized_partition_id and normalized_partition_id != default_partition.id:
            raise FileCorpusConflict(
                "legacy file partition binding does not match its workspace default"
            )
        partition_ids.append(default_partition.id)
    return partition_ids


def _validate_default_file_partition(
    partition: RetrievalPartition,
    *,
    workspace_id: str,
) -> None:
    if (
        partition.source_namespace != "files"
        or not partition.is_default_ingest
        or partition.state != RetrievalPartitionState.ACTIVE.value
        or partition.managed_workspace_id != workspace_id
        or partition.candidate_scope_kind != "workspace"
        or partition.candidate_workspace_id != workspace_id
        or partition.candidate_user_id is not None
    ):
        raise FileCorpusConflict("legacy file partition gate does not match its workspace")


def _require_locked_default_file_partition(
    locked_partitions: dict[str, RetrievalPartition],
    *,
    workspace_id: str,
    bound_partition_id: str | None,
) -> RetrievalPartition:
    normalized_bound_id = str(bound_partition_id or "").strip()
    if normalized_bound_id:
        partition = locked_partitions.get(normalized_bound_id)
        if partition is None:
            raise FileCorpusConflict("legacy file partition gate was not locked")
        _validate_default_file_partition(partition, workspace_id=workspace_id)
        return partition

    matches = [
        partition
        for partition in locked_partitions.values()
        if partition.source_namespace == "files"
        and partition.is_default_ingest
        and partition.state == RetrievalPartitionState.ACTIVE.value
        and partition.managed_workspace_id == workspace_id
        and partition.candidate_scope_kind == "workspace"
        and partition.candidate_workspace_id == workspace_id
        and partition.candidate_user_id is None
    ]
    if len(matches) != 1:
        raise FileCorpusConflict("legacy file default partition gate was not locked")
    return matches[0]


def _lock_corpora_for_children(
    db: Session,
    *,
    workspace_id: str,
    folder_ids: Iterable[str] = (),
    file_ids: Iterable[str] = (),
    lock_mode: FileCorpusLockMode,
) -> tuple[dict[str, FileManagerCorpus], dict[str, RetrievalPartition]]:
    """Discover immutable child bindings, then lock their corpora before reloading children."""

    normalized_folder_ids = tuple(sorted(set(folder_ids)))
    normalized_file_ids = tuple(sorted(set(file_ids)))
    bindings: list[tuple[str | None, str | None, str]] = []
    if normalized_folder_ids:
        bindings.extend(
            db.execute(
                select(
                    FileManagerFolder.corpus_id,
                    FileManagerFolder.retrieval_partition_id,
                    FileManagerFolder.workspace_id,
                ).where(
                    FileManagerFolder.id.in_(normalized_folder_ids),
                    FileManagerFolder.workspace_id == workspace_id,
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
                    FileManagerFile.workspace_id,
                ).where(
                    FileManagerFile.id.in_(normalized_file_ids),
                    FileManagerFile.workspace_id == workspace_id,
                    FileManagerFile.deleted_at.is_(None),
                )
            ).all()
        )
    corpus_ids = [corpus_id for corpus_id, _partition_id, _workspace_id in bindings if corpus_id]
    locked_corpora = _lock_file_corpora(db, corpus_ids, lock_mode=lock_mode)
    legacy_partition_ids = _resolve_legacy_partition_gate_ids(db, bindings)
    locked_legacy_partitions = _lock_retrieval_partitions(
        db,
        legacy_partition_ids,
        lock_mode=lock_mode,
    )
    return locked_corpora, locked_legacy_partitions


def _validate_locked_child_corpus(
    child: FileManagerFolder | FileManagerFile,
    locked_corpora: dict[str, FileManagerCorpus],
    *,
    locked_legacy_partitions: dict[str, RetrievalPartition] | None = None,
) -> None:
    if child.corpus_id is None:
        if locked_legacy_partitions is None:
            raise FileCorpusConflict("legacy file partition gates were not provided")
        _require_locked_default_file_partition(
            locked_legacy_partitions,
            workspace_id=child.workspace_id,
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
    if (
        child.workspace_id != corpus.managed_workspace_id
        or child.retrieval_partition_id != corpus.retrieval_partition_id
    ):
        raise FileCorpusConflict("file child does not match its current corpus metadata")


def _validate_file_corpus_partition(
    corpus: FileManagerCorpus,
    partition: RetrievalPartition,
) -> None:
    expected_workspace_id = (
        corpus.managed_workspace_id if corpus.access_scope_kind == "workspace" else None
    )
    if (
        partition.source_namespace != "files"
        or partition.is_default_ingest
        or partition.state != RetrievalPartitionState.ACTIVE.value
        or partition.managed_workspace_id != corpus.managed_workspace_id
        or partition.candidate_scope_kind != corpus.access_scope_kind
        or partition.candidate_workspace_id != expected_workspace_id
        or partition.candidate_user_id is not None
    ):
        raise FileCorpusConflict("file corpus partition metadata does not match source ACL")


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


def _is_current_active_workspace(db: Session, workspace_id: str) -> bool:
    return (
        db.scalar(
            select(Workspace.id).where(
                Workspace.id == workspace_id,
                Workspace.active.is_(True),
            )
        )
        is not None
    )


def _require_current_mutation_context(
    db: Session,
    *,
    user_id: str,
    workspace_id: str,
) -> None:
    _require_current_active_user(db, user_id)
    if not _is_current_active_workspace(db, workspace_id):
        raise FileCorpusAccessDenied("active file workspace is required")
    has_workspace_membership = workspace_role_allows(
        _current_workspace_role(db, user_id=user_id, workspace_id=workspace_id),
        "member",
    )
    if not has_workspace_membership and not _is_current_platform_admin(db, user_id):
        raise FileCorpusAccessDenied("current file workspace membership is required")


def _current_workspace_role(
    db: Session,
    *,
    user_id: str,
    workspace_id: str,
) -> str | None:
    return db.scalar(
        select(WorkspaceUserBinding.role).where(
            WorkspaceUserBinding.user_id == user_id,
            WorkspaceUserBinding.workspace_id == workspace_id,
        )
    )


def _is_current_workspace_admin(
    db: Session,
    *,
    user_id: str,
    workspace_id: str,
) -> bool:
    return workspace_role_allows(
        _current_workspace_role(db, user_id=user_id, workspace_id=workspace_id),
        "admin",
    )


def _is_current_platform_admin(db: Session, user_id: str) -> bool:
    return is_current_platform_admin(db, user_id)


def _authorize_file_corpus_transition(
    db: Session,
    *,
    corpus: FileManagerCorpus,
    actor: User,
    source_workspace: Workspace,
    target_workspace: Workspace,
    target_scope: str,
) -> None:
    touches_company_scope = corpus.access_scope_kind == "company" or target_scope == "company"
    if touches_company_scope and not _is_current_platform_admin(db, actor.id):
        raise FileCorpusAccessDenied("company corpus transition requires platform admin")
    if source_workspace.id != target_workspace.id:
        if not is_workspace_admin(db, workspace=source_workspace, user=actor):
            raise FileCorpusAccessDenied("file corpus transfer requires source workspace admin")
        if not is_workspace_admin(db, workspace=target_workspace, user=actor):
            raise FileCorpusAccessDenied("file corpus transfer requires target workspace admin")
        return
    if not touches_company_scope and not is_workspace_admin(
        db,
        workspace=source_workspace,
        user=actor,
    ):
        raise FileCorpusAccessDenied("file corpus transition requires workspace admin")


def _load_active_workspace(db: Session, workspace_id: str) -> Workspace:
    workspace = db.scalar(
        select(Workspace)
        .where(
            Workspace.id == workspace_id,
            Workspace.active.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    if workspace is None:
        raise FileCorpusNotFound(f"workspace:{workspace_id}")
    return workspace


def _normalize_corpus_access_scope(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in FILE_CORPUS_ACCESS_SCOPE_KINDS:
        raise FileCorpusConflict(f"unsupported file corpus access scope: {value}")
    return normalized


def _normalize_corpus_transition_reason(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise FileCorpusConflict("file corpus transition requires reason")
    return normalized[:2000]


def _load_folder_for_workspace(
    db: Session,
    *,
    workspace: Workspace,
    folder_id: str,
    lock_mode: FileChildLockMode | None = None,
) -> FileManagerFolder:
    statement = select(FileManagerFolder)
    if lock_mode is None:
        statement = statement.options(joinedload(FileManagerFolder.owner))
    statement = statement.where(
        FileManagerFolder.workspace_id == workspace.id,
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


def _load_file_for_workspace(
    db: Session,
    *,
    workspace: Workspace,
    file_id: str,
    lock_mode: FileChildLockMode | None = None,
) -> FileManagerFile:
    statement = select(FileManagerFile)
    if lock_mode is None:
        statement = statement.options(joinedload(FileManagerFile.owner))
    statement = statement.where(
        FileManagerFile.workspace_id == workspace.id,
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
    workspace_id: str,
    selected_folder_ids: Iterable[str],
    selected_file_ids: Iterable[str],
) -> _FileDeleteScope:
    requested_folder_ids = set(selected_folder_ids)
    requested_file_ids = set(selected_file_ids)
    root_rows = (
        db.execute(
            select(
                FileManagerFolder.id,
                FileManagerFolder.workspace_id,
                FileManagerFolder.corpus_id,
                FileManagerFolder.retrieval_partition_id,
            )
            .where(
                FileManagerFolder.workspace_id == workspace_id,
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
    legacy_partition_ids: set[str] = set()
    legacy_workspace_ids: set[str] = set()
    for row in root_rows:
        if row.corpus_id is not None:
            continue
        legacy_workspace_ids.add(row.workspace_id)
        if row.retrieval_partition_id is None:
            continue
        legacy_partition_ids.add(row.retrieval_partition_id)
    frontier = set(discovered_folder_ids)
    while frontier:
        child_rows = db.execute(
            select(
                FileManagerFolder.id,
                FileManagerFolder.workspace_id,
                FileManagerFolder.corpus_id,
                FileManagerFolder.retrieval_partition_id,
            )
            .where(
                FileManagerFolder.workspace_id == workspace_id,
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
            legacy_workspace_ids.add(row.workspace_id)
            if row.retrieval_partition_id is None:
                continue
            legacy_partition_ids.add(row.retrieval_partition_id)
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
                FileManagerFile.workspace_id,
                FileManagerFile.corpus_id,
                FileManagerFile.retrieval_partition_id,
            )
            .where(
                FileManagerFile.workspace_id == workspace_id,
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
        legacy_workspace_ids.add(row.workspace_id)
        if row.retrieval_partition_id is None:
            continue
        legacy_partition_ids.add(row.retrieval_partition_id)
    return _FileDeleteScope(
        folder_ids=tuple(sorted(discovered_folder_ids)),
        file_ids=tuple(sorted(discovered_file_ids)),
        corpus_ids=tuple(sorted(corpus_ids)),
        legacy_partition_ids=tuple(sorted(legacy_partition_ids)),
        legacy_workspace_ids=tuple(sorted(legacy_workspace_ids)),
    )


def _lock_tree_delete_scope(
    db: Session,
    *,
    workspace_id: str,
    selected_folder_ids: Iterable[str],
    selected_file_ids: Iterable[str],
) -> tuple[list[FileManagerFolder], list[FileManagerFile]]:
    """Lock corpora, then the actual folder/file tree in one global order."""

    initial_scope = _discover_file_delete_scope(
        db,
        workspace_id=workspace_id,
        selected_folder_ids=selected_folder_ids,
        selected_file_ids=selected_file_ids,
    )
    locked_corpora = _lock_file_corpora(
        db,
        initial_scope.corpus_ids,
        lock_mode="exclusive",
    )
    initial_legacy_partition_ids = _resolve_legacy_partition_gate_ids(
        db,
        (
            (None, None, legacy_workspace_id)
            for legacy_workspace_id in initial_scope.legacy_workspace_ids
        ),
    )
    if set(initial_scope.legacy_partition_ids) - set(initial_legacy_partition_ids):
        raise FileCorpusConflict(
            "legacy file partition binding does not match its workspace default"
        )
    locked_legacy_partitions = _lock_retrieval_partitions(
        db,
        initial_legacy_partition_ids,
        lock_mode="exclusive",
    )
    current_scope = _discover_file_delete_scope(
        db,
        workspace_id=workspace_id,
        selected_folder_ids=selected_folder_ids,
        selected_file_ids=selected_file_ids,
    )
    unlocked_corpus_ids = set(current_scope.corpus_ids) - set(locked_corpora)
    if unlocked_corpus_ids:
        raise FileCorpusConflict("file delete scope gained an unlocked corpus")
    current_legacy_partition_ids = set(current_scope.legacy_partition_ids)
    for legacy_workspace_id in current_scope.legacy_workspace_ids:
        current_legacy_partition_ids.add(
            _require_locked_default_file_partition(
                locked_legacy_partitions,
                workspace_id=legacy_workspace_id,
                bound_partition_id=None,
            ).id
        )
    unlocked_legacy_partition_ids = current_legacy_partition_ids - set(locked_legacy_partitions)
    if unlocked_legacy_partition_ids:
        raise FileCorpusConflict("file delete scope gained an unlocked legacy partition")

    folders = list(
        db.scalars(
            select(FileManagerFolder)
            .where(
                FileManagerFolder.workspace_id == workspace_id,
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
                FileManagerFile.workspace_id == workspace_id,
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
            locked_legacy_partitions=locked_legacy_partitions,
        )
    return folders, files


def _lock_leaf_files_for_delete(
    db: Session,
    *,
    workspace_id: str,
    selected_file_ids: Iterable[str],
) -> list[FileManagerFile]:
    """Use shared corpus locks for leaf-only deletes and sorted exclusive row locks."""

    initial_scope = _discover_file_delete_scope(
        db,
        workspace_id=workspace_id,
        selected_folder_ids=(),
        selected_file_ids=selected_file_ids,
    )
    locked_corpora = _lock_file_corpora(
        db,
        initial_scope.corpus_ids,
        lock_mode="shared",
    )
    initial_legacy_partition_ids = _resolve_legacy_partition_gate_ids(
        db,
        (
            (None, None, legacy_workspace_id)
            for legacy_workspace_id in initial_scope.legacy_workspace_ids
        ),
    )
    if set(initial_scope.legacy_partition_ids) - set(initial_legacy_partition_ids):
        raise FileCorpusConflict(
            "legacy file partition binding does not match its workspace default"
        )
    locked_legacy_partitions = _lock_retrieval_partitions(
        db,
        initial_legacy_partition_ids,
        lock_mode="shared",
    )
    files = list(
        db.scalars(
            select(FileManagerFile)
            .where(
                FileManagerFile.workspace_id == workspace_id,
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
            locked_legacy_partitions=locked_legacy_partitions,
        )
    return files


def _record_visible(
    visibility: str,
    owner_id: str,
    *,
    user: User,
    is_admin: bool,
) -> bool:
    return is_admin or owner_id == user.id or visibility == "workspace"


def _ensure_can_manage_record(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    owner_id: str,
    error_code: str = "files.delete_access_required",
) -> None:
    _require_current_mutation_context(db, user_id=user.id, workspace_id=workspace.id)
    if owner_id == user.id or is_workspace_admin(db, workspace=workspace, user=user):
        return
    raise localized_http_exception(status_code=403, code=error_code)


def _normalize_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise localized_http_exception(status_code=422, code="files.name_required")
    return name[:255]
