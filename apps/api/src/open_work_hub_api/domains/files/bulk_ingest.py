from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from open_work_hub_api.domains.auth.roles import workspace_role_allows
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.models import (
    FileManagerBulkIngestEntry,
    FileManagerBulkIngestRun,
    FileManagerFile,
    FileManagerFolder,
    FileManagerStorageCleanupJob,
)
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.retrieval.models import RetrievalProjectionHead
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


RUN_STATES = frozenset(
    {"planned", "ingesting", "paused", "completed", "purging", "purged", "failed"}
)
ENTRY_STATES = frozenset({"planned", "uploaded", "failed", "purged"})
PURGE_BATCH_LIMIT = 100
INGEST_BATCH_LIMIT = 100


class FilesBulkIngestError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    source_path: str
    size_bytes: int
    content_sha256: str
    content_type: str


@dataclass(frozen=True, slots=True)
class BulkIngestRunStatus:
    run_id: str
    state: str
    total: int
    planned: int
    uploaded: int
    failed: int
    purged: int
    total_bytes: int

    def status_line(self) -> str:
        return (
            f"status=ok run_id={self.run_id} state={self.state} total={self.total} "
            f"planned={self.planned} uploaded={self.uploaded} failed={self.failed} "
            f"purged={self.purged} total_bytes={self.total_bytes}"
        )


@dataclass(frozen=True, slots=True)
class PurgeBatchResult:
    run_id: str
    state: str
    processed: int
    storage_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CleanVerification:
    run_id: str
    clean: bool
    active_files: int
    extraction_artifacts: int
    storage_objects: int
    pending_storage_cleanup_jobs: int
    active_projection_heads: int
    nonterminal_search_jobs: int
    nonterminal_rag_jobs: int
    opensearch_documents: int
    qdrant_points: int

    def status_line(self) -> str:
        return (
            f"status={'ok' if self.clean else 'failed'} run_id={self.run_id} "
            f"clean={int(self.clean)} active_files={self.active_files} "
            f"extraction_artifacts={self.extraction_artifacts} "
            f"storage_objects={self.storage_objects} "
            f"pending_storage_cleanup_jobs={self.pending_storage_cleanup_jobs} "
            f"active_projection_heads={self.active_projection_heads} "
            f"nonterminal_search_jobs={self.nonterminal_search_jobs} "
            f"nonterminal_rag_jobs={self.nonterminal_rag_jobs} "
            f"opensearch_documents={self.opensearch_documents} "
            f"qdrant_points={self.qdrant_points}"
        )


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def source_root_identity(source_root: Path) -> str:
    return hashlib.sha256(str(source_root.resolve()).encode("utf-8")).hexdigest()


def source_path_identity(source_path: str) -> str:
    return hashlib.sha256(normalize_source_path(source_path).encode("utf-8")).hexdigest()


def normalize_source_path(source_path: str) -> str:
    normalized = str(source_path or "").replace("\\", "/").strip()
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or normalized in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise FilesBulkIngestError("manifest_source_path_invalid")
    return path.as_posix()


def create_run(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    owner: User | None = None,
    corpus_name: str,
    root_folder_name: str,
    idempotency_key: str,
    manifest_sha256: str,
    source_root_sha256: str,
    entries: list[ManifestEntry],
) -> FileManagerBulkIngestRun:
    normalized_manifest_sha256 = _normalize_sha256(manifest_sha256, code="manifest_sha256_invalid")
    normalized_source_root_sha256 = _normalize_sha256(
        source_root_sha256, code="source_root_sha256_invalid"
    )
    idempotency_key_sha256 = _idempotency_key_sha256(idempotency_key)
    run_id = _stable_id(f"{workspace.id}:{idempotency_key_sha256}")
    existing = db.get(FileManagerBulkIngestRun, run_id)
    if existing is not None:
        _require_manifest_identity(
            existing,
            manifest_sha256=normalized_manifest_sha256,
            source_root_sha256=normalized_source_root_sha256,
        )
        return existing

    effective_owner = owner or actor
    _require_run_owner(db, workspace=workspace, owner=effective_owner)
    normalized_entries = _normalize_manifest_entries(entries)
    try:
        corpus = files_service.create_file_corpus(
            db,
            workspace=workspace,
            user=actor,
            name=corpus_name,
        )
    except files_service.FileCorpusAccessDenied as error:
        raise FilesBulkIngestError("control_plane_actor_workspace_admin_required") from error
    corpus.operator_managed = True
    root = FileManagerFolder(
        id=_stable_id(f"{run_id}:root"),
        workspace_id=workspace.id,
        retrieval_partition_id=corpus.retrieval_partition_id,
        corpus_id=corpus.id,
        parent_id=None,
        owner_id=effective_owner.id,
        name=_normalize_name(root_folder_name),
        visibility="workspace",
    )
    run = FileManagerBulkIngestRun(
        id=run_id,
        workspace_id=workspace.id,
        corpus_id=corpus.id,
        root_folder_id=root.id,
        created_by_id=actor.id,
        idempotency_key_sha256=idempotency_key_sha256,
        manifest_sha256=normalized_manifest_sha256,
        source_root_sha256=normalized_source_root_sha256,
        manifest_entry_count=len(normalized_entries),
        manifest_total_bytes=sum(entry.size_bytes for entry in normalized_entries),
        status="planned",
    )
    db.add_all([corpus, root, run])
    db.flush()
    for entry in normalized_entries:
        path_sha256 = source_path_identity(entry.source_path)
        db.add(
            FileManagerBulkIngestEntry(
                id=_stable_id(f"{run_id}:entry:{path_sha256}"),
                run_id=run.id,
                source_path=entry.source_path,
                source_path_sha256=path_sha256,
                content_sha256=entry.content_sha256,
                size_bytes=entry.size_bytes,
                content_type=entry.content_type,
                target_file_id=_stable_id(f"{run_id}:file:{path_sha256}"),
                status="planned",
            )
        )
    db.flush()
    return run


def _require_run_owner(
    db: Session,
    *,
    workspace: Workspace,
    owner: User,
) -> None:
    role = db.scalar(
        select(WorkspaceUserBinding.role).where(
            WorkspaceUserBinding.user_id == owner.id,
            WorkspaceUserBinding.workspace_id == workspace.id,
        )
    )
    if (
        owner.status != "active"
        or owner.login_blocked
        or not workspace_role_allows(role, "member")
    ):
        raise FilesBulkIngestError("run_owner_workspace_member_required")


def start_or_resume_run(
    db: Session,
    *,
    run_id: str,
    manifest_sha256: str,
    source_root_sha256: str,
) -> FileManagerBulkIngestRun:
    run = _lock_run(db, run_id)
    _require_manifest_identity(
        run,
        manifest_sha256=manifest_sha256,
        source_root_sha256=source_root_sha256,
    )
    if run.status in {"purging", "purged"}:
        raise FilesBulkIngestError("run_not_ingestable")
    if run.status == "completed":
        return run
    run.status = "ingesting"
    run.last_error_code = None
    db.add(run)
    db.flush()
    return run


def list_ingest_candidates(
    db: Session,
    *,
    run_id: str,
    limit: int = INGEST_BATCH_LIMIT,
) -> list[FileManagerBulkIngestEntry]:
    batch_limit = _batch_limit(limit, maximum=INGEST_BATCH_LIMIT)
    run = _lock_run(db, run_id)
    if run.status == "completed":
        return []
    if run.status != "ingesting":
        raise FilesBulkIngestError("run_not_ingesting")
    return list(
        db.scalars(
            select(FileManagerBulkIngestEntry)
            .where(
                FileManagerBulkIngestEntry.run_id == run.id,
                FileManagerBulkIngestEntry.status.in_(("planned", "failed")),
            )
            .order_by(FileManagerBulkIngestEntry.target_file_id.asc())
            .limit(batch_limit)
        )
    )


def ingest_entry(
    db: Session,
    *,
    run_id: str,
    entry_id: str,
    source_root: Path,
    actor: User,
) -> bool:
    run = _lock_run(db, run_id)
    if run.status != "ingesting":
        raise FilesBulkIngestError("run_not_ingesting")
    if source_root_identity(source_root) != run.source_root_sha256:
        raise FilesBulkIngestError("source_root_identity_mismatch")
    entry = db.scalar(
        select(FileManagerBulkIngestEntry)
        .where(
            FileManagerBulkIngestEntry.id == entry_id,
            FileManagerBulkIngestEntry.run_id == run.id,
        )
        .with_for_update()
    )
    if entry is None:
        raise FilesBulkIngestError("entry_not_found")
    if entry.status == "uploaded":
        return False
    if entry.status not in {"planned", "failed"}:
        raise FilesBulkIngestError("entry_not_ingestable")

    existing_file = db.get(FileManagerFile, entry.target_file_id)
    if existing_file is not None:
        if (
            existing_file.corpus_id != run.corpus_id
            or existing_file.workspace_id != run.workspace_id
            or existing_file.deleted_at is not None
        ):
            raise FilesBulkIngestError("reserved_file_id_conflict")
        entry.status = "uploaded"
        entry.error_code = None
        entry.uploaded_at = entry.uploaded_at or utcnow_naive()
        db.add(entry)
        return False

    source_file = _resolve_source_file(source_root, entry.source_path)
    _verify_source_file(source_file, entry=entry)
    folder = _ensure_run_folder_path(
        db,
        run=run,
        actor=actor,
        relative_parent=PurePosixPath(entry.source_path).parent,
    )
    entry.attempt_count += 1
    with source_file.open("rb") as content:
        files_service.upload_file(
            db,
            workspace=_require_workspace(db, run.workspace_id),
            user=actor,
            filename=PurePosixPath(entry.source_path).name,
            content_type=entry.content_type,
            content=content,
            size_bytes=entry.size_bytes,
            folder_id=folder.id,
            visibility="workspace",
            corpus_id=run.corpus_id,
            operator_ingest_run_id=run.id,
            reserved_file_id=entry.target_file_id,
        )
    entry.status = "uploaded"
    entry.error_code = None
    entry.uploaded_at = utcnow_naive()
    db.add(entry)
    db.flush()
    return True


def mark_ingest_failure(
    db: Session,
    *,
    run_id: str,
    entry_id: str,
    error_code: str,
) -> None:
    run = _lock_run(db, run_id)
    entry = db.scalar(
        select(FileManagerBulkIngestEntry)
        .where(
            FileManagerBulkIngestEntry.id == entry_id,
            FileManagerBulkIngestEntry.run_id == run.id,
        )
        .with_for_update()
    )
    if entry is None:
        raise FilesBulkIngestError("entry_not_found")
    if entry.status != "uploaded":
        entry.status = "failed"
        entry.attempt_count += 1
        entry.error_code = _normalize_error_code(error_code)
        db.add(entry)
    run.status = "failed"
    run.last_error_code = _normalize_error_code(error_code)
    db.add(run)
    db.flush()


def finish_ingest_batch(db: Session, *, run_id: str) -> FileManagerBulkIngestRun:
    run = _lock_run(db, run_id)
    remaining = int(
        db.scalar(
            select(func.count(FileManagerBulkIngestEntry.id)).where(
                FileManagerBulkIngestEntry.run_id == run.id,
                FileManagerBulkIngestEntry.status.in_(("planned", "failed")),
            )
        )
        or 0
    )
    if remaining == 0:
        run.status = "completed"
        run.completed_at = utcnow_naive()
        run.last_error_code = None
        db.add(run)
        db.flush()
    return run


def pause_run(db: Session, *, run_id: str) -> FileManagerBulkIngestRun:
    run = _lock_run(db, run_id)
    if run.status == "purged":
        return run
    if run.status in {"completed", "purging"}:
        raise FilesBulkIngestError("run_not_pauseable")
    run.status = "paused"
    db.add(run)
    db.flush()
    return run


def begin_purge(db: Session, *, run_id: str) -> FileManagerBulkIngestRun:
    run = _lock_run(db, run_id)
    if run.status == "purged":
        return run
    if run.status == "ingesting":
        raise FilesBulkIngestError("pause_run_before_purge")
    run.status = "purging"
    run.last_error_code = None
    db.add(run)
    db.flush()
    return run


def purge_batch(
    db: Session,
    *,
    run_id: str,
    actor: User,
    limit: int = PURGE_BATCH_LIMIT,
) -> PurgeBatchResult:
    batch_limit = _batch_limit(limit, maximum=PURGE_BATCH_LIMIT)
    run = _lock_run(db, run_id)
    if run.status == "purged":
        return PurgeBatchResult(run.id, run.status, 0, ())
    if run.status != "purging":
        raise FilesBulkIngestError("run_not_purging")
    statement = select(FileManagerBulkIngestEntry).where(
        FileManagerBulkIngestEntry.run_id == run.id,
        FileManagerBulkIngestEntry.status == "uploaded",
    )
    if run.purge_after_file_id is not None:
        statement = statement.where(
            FileManagerBulkIngestEntry.target_file_id > run.purge_after_file_id
        )
    entries = list(
        db.scalars(
            statement.order_by(FileManagerBulkIngestEntry.target_file_id.asc())
            .limit(batch_limit)
            .with_for_update()
        )
    )
    workspace = _require_workspace(db, run.workspace_id)
    storage_keys: list[str] = []
    for entry in entries:
        file = db.get(FileManagerFile, entry.target_file_id)
        if file is not None and file.deleted_at is None:
            storage_keys.append(
                files_service.delete_file(
                    db,
                    workspace=workspace,
                    user=actor,
                    file_id=file.id,
                )
            )
        entry.status = "purged"
        entry.purged_at = utcnow_naive()
        entry.error_code = None
        run.purge_after_file_id = entry.target_file_id
        db.add(entry)

    # Production sessions disable autoflush. Persist the current batch before
    # deciding whether it was the final batch so exact batch-size multiples do
    # not require a separate empty purge call to finalize the run.
    db.flush()
    remaining = int(
        db.scalar(
            select(func.count(FileManagerBulkIngestEntry.id)).where(
                FileManagerBulkIngestEntry.run_id == run.id,
                FileManagerBulkIngestEntry.status == "uploaded",
            )
        )
        or 0
    )
    if remaining == 0:
        root = db.get(FileManagerFolder, run.root_folder_id)
        if root is not None and root.deleted_at is None:
            storage_keys.extend(
                files_service.delete_folder(
                    db,
                    workspace=workspace,
                    user=actor,
                    folder_id=root.id,
                )
            )
        run.status = "purged"
        run.purged_at = utcnow_naive()
    for storage_key in storage_keys:
        files_service.enqueue_storage_cleanup_job(
            db,
            storage_key,
            error="bulk_purge_requested",
        )
    db.add(run)
    db.flush()
    return PurgeBatchResult(run.id, run.status, len(entries), tuple(storage_keys))


def load_status(db: Session, *, run_id: str) -> BulkIngestRunStatus:
    run = _require_run(db, run_id)
    counts = db.execute(
        select(
            func.count(FileManagerBulkIngestEntry.id),
            func.sum(case((FileManagerBulkIngestEntry.status == "planned", 1), else_=0)),
            func.sum(case((FileManagerBulkIngestEntry.status == "uploaded", 1), else_=0)),
            func.sum(case((FileManagerBulkIngestEntry.status == "failed", 1), else_=0)),
            func.sum(case((FileManagerBulkIngestEntry.status == "purged", 1), else_=0)),
        ).where(FileManagerBulkIngestEntry.run_id == run.id)
    ).one()
    return BulkIngestRunStatus(
        run_id=run.id,
        state=run.status,
        total=int(counts[0] or 0),
        planned=int(counts[1] or 0),
        uploaded=int(counts[2] or 0),
        failed=int(counts[3] or 0),
        purged=int(counts[4] or 0),
        total_bytes=run.manifest_total_bytes,
    )


def verify_clean(
    db: Session,
    *,
    run_id: str,
    storage_objects: int,
    opensearch_documents: int,
    qdrant_points: int,
) -> CleanVerification:
    run = _require_run(db, run_id)
    target_ids = select(FileManagerBulkIngestEntry.target_file_id).where(
        FileManagerBulkIngestEntry.run_id == run.id
    )
    storage_keys = select(FileManagerFile.storage_key).where(FileManagerFile.id.in_(target_ids))
    active_files = _count(
        db,
        select(func.count(FileManagerFile.id)).where(
            FileManagerFile.id.in_(target_ids),
            FileManagerFile.deleted_at.is_(None),
        ),
    )
    extraction_artifacts = _count(
        db,
        select(func.count(FileManagerFile.id)).where(
            FileManagerFile.id.in_(target_ids),
            or_(
                FileManagerFile.extraction_text.is_not(None),
                FileManagerFile.extraction_content_checksum.is_not(None),
                FileManagerFile.extracted_at.is_not(None),
            ),
        ),
    )
    pending_storage_cleanup_jobs = _count(
        db,
        select(func.count(FileManagerStorageCleanupJob.id)).where(
            FileManagerStorageCleanupJob.storage_key.in_(storage_keys),
            FileManagerStorageCleanupJob.status != "succeeded",
        ),
    )
    active_projection_heads = _count(
        db,
        select(func.count())
        .select_from(RetrievalProjectionHead)
        .where(
            RetrievalProjectionHead.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            RetrievalProjectionHead.resource_id.in_(target_ids),
            RetrievalProjectionHead.desired_state != "deleted",
        ),
    )
    nonterminal_search_jobs = _count(
        db,
        select(func.count(SearchIndexJob.id)).where(
            SearchIndexJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            SearchIndexJob.entity_id.in_(target_ids),
            SearchIndexJob.status.in_(("pending", "processing")),
        ),
    )
    nonterminal_rag_jobs = _count(
        db,
        select(func.count(RagSyncJob.id)).where(
            RagSyncJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            RagSyncJob.resource_id.in_(target_ids),
            RagSyncJob.status.in_(("pending", "processing")),
        ),
    )
    clean = (
        run.status == "purged"
        and active_files == 0
        and extraction_artifacts == 0
        and storage_objects == 0
        and pending_storage_cleanup_jobs == 0
        and active_projection_heads == 0
        and nonterminal_search_jobs == 0
        and nonterminal_rag_jobs == 0
        and opensearch_documents == 0
        and qdrant_points == 0
    )
    return CleanVerification(
        run_id=run.id,
        clean=clean,
        active_files=active_files,
        extraction_artifacts=extraction_artifacts,
        storage_objects=storage_objects,
        pending_storage_cleanup_jobs=pending_storage_cleanup_jobs,
        active_projection_heads=active_projection_heads,
        nonterminal_search_jobs=nonterminal_search_jobs,
        nonterminal_rag_jobs=nonterminal_rag_jobs,
        opensearch_documents=opensearch_documents,
        qdrant_points=qdrant_points,
    )


def _normalize_manifest_entries(entries: list[ManifestEntry]) -> list[ManifestEntry]:
    normalized: list[ManifestEntry] = []
    seen_paths: set[str] = set()
    for entry in entries:
        source_path = normalize_source_path(entry.source_path)
        if source_path in seen_paths:
            raise FilesBulkIngestError("manifest_source_path_duplicate")
        seen_paths.add(source_path)
        size_bytes = int(entry.size_bytes)
        if size_bytes < 0 or size_bytes > files_service.MAX_FILE_UPLOAD_SIZE:
            raise FilesBulkIngestError("manifest_file_size_invalid")
        content_type = str(entry.content_type or "").strip()[:160]
        if not content_type:
            raise FilesBulkIngestError("manifest_content_type_invalid")
        normalized.append(
            ManifestEntry(
                source_path=source_path,
                size_bytes=size_bytes,
                content_sha256=_normalize_sha256(
                    entry.content_sha256, code="manifest_content_sha256_invalid"
                ),
                content_type=content_type,
            )
        )
    return sorted(normalized, key=lambda entry: entry.source_path)


def _require_manifest_identity(
    run: FileManagerBulkIngestRun,
    *,
    manifest_sha256: str,
    source_root_sha256: str,
) -> None:
    if run.manifest_sha256 != _normalize_sha256(manifest_sha256, code="manifest_sha256_invalid"):
        raise FilesBulkIngestError("manifest_identity_mismatch")
    if run.source_root_sha256 != _normalize_sha256(
        source_root_sha256, code="source_root_sha256_invalid"
    ):
        raise FilesBulkIngestError("source_root_identity_mismatch")


def _resolve_source_file(source_root: Path, source_path: str) -> Path:
    root = source_root.resolve(strict=True)
    candidate = (root / normalize_source_path(source_path)).resolve(strict=True)
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise FilesBulkIngestError("source_file_unavailable")
    return candidate


def _verify_source_file(
    source_file: Path,
    *,
    entry: FileManagerBulkIngestEntry,
) -> None:
    if source_file.stat().st_size != entry.size_bytes:
        raise FilesBulkIngestError("source_file_size_mismatch")
    digest = hashlib.sha256()
    with source_file.open("rb") as content:
        while chunk := content.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != entry.content_sha256:
        raise FilesBulkIngestError("source_file_content_mismatch")


def _ensure_run_folder_path(
    db: Session,
    *,
    run: FileManagerBulkIngestRun,
    actor: User,
    relative_parent: PurePosixPath,
) -> FileManagerFolder:
    root = db.get(FileManagerFolder, run.root_folder_id)
    if root is None or root.deleted_at is not None:
        raise FilesBulkIngestError("run_root_folder_unavailable")
    parent = root
    if relative_parent.as_posix() == ".":
        return parent
    workspace = _require_workspace(db, run.workspace_id)
    for name in relative_parent.parts:
        folder = db.scalar(
            select(FileManagerFolder).where(
                FileManagerFolder.corpus_id == run.corpus_id,
                FileManagerFolder.parent_id == parent.id,
                FileManagerFolder.name == name,
                FileManagerFolder.deleted_at.is_(None),
            )
        )
        if folder is None:
            folder = files_service.create_folder(
                db,
                workspace=workspace,
                user=actor,
                name=name,
                parent_id=parent.id,
                visibility="workspace",
                corpus_id=run.corpus_id,
                operator_ingest_run_id=run.id,
            )
        parent = folder
    return parent


def _require_run(db: Session, run_id: str) -> FileManagerBulkIngestRun:
    run = db.get(FileManagerBulkIngestRun, str(run_id or "").strip())
    if run is None:
        raise FilesBulkIngestError("run_not_found")
    return run


def _lock_run(db: Session, run_id: str) -> FileManagerBulkIngestRun:
    run = db.scalar(
        select(FileManagerBulkIngestRun)
        .where(FileManagerBulkIngestRun.id == str(run_id or "").strip())
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None:
        raise FilesBulkIngestError("run_not_found")
    return run


def _require_workspace(db: Session, workspace_id: str) -> Workspace:
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.active.is_(True),
        )
    )
    if workspace is None:
        raise FilesBulkIngestError("workspace_unavailable")
    return workspace


def _normalize_sha256(value: str, *, code: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise FilesBulkIngestError(code)
    return normalized


def _normalize_name(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 255:
        raise FilesBulkIngestError("name_invalid")
    return normalized


def _normalize_error_code(value: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    return normalized[:120] or "bulk_ingest_failed"


def _idempotency_key_sha256(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > 200:
        raise FilesBulkIngestError("idempotency_key_invalid")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _stable_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"open-work-hub:files-bulk-ingest:{value}"))


def _batch_limit(value: int, *, maximum: int) -> int:
    normalized = int(value)
    if normalized < 1 or normalized > maximum:
        raise FilesBulkIngestError("batch_limit_invalid")
    return normalized


def _count(db: Session, statement) -> int:
    return int(db.scalar(statement) or 0)


__all__ = [
    "BulkIngestRunStatus",
    "CleanVerification",
    "ENTRY_STATES",
    "FilesBulkIngestError",
    "INGEST_BATCH_LIMIT",
    "ManifestEntry",
    "PURGE_BATCH_LIMIT",
    "PurgeBatchResult",
    "RUN_STATES",
    "begin_purge",
    "create_run",
    "finish_ingest_batch",
    "ingest_entry",
    "list_ingest_candidates",
    "load_status",
    "mark_ingest_failure",
    "normalize_source_path",
    "pause_run",
    "purge_batch",
    "source_path_identity",
    "source_root_identity",
    "start_or_resume_run",
    "verify_clean",
]
