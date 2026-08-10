from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import BinaryIO, Literal

from sqlalchemy import delete, event, func, select
from sqlalchemy.orm import Session, SessionTransaction

from open_work_hub_api.domains.auth.models import Team, User, Workspace
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files import storage_adapter as file_storage
from open_work_hub_api.domains.files.archive_planner import safe_filename
from open_work_hub_api.domains.files.external_access import is_current_platform_admin
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileAccessGrant,
    FileManagerFileSourceMetadata,
)
from open_work_hub_api.domains.files.rag_sync import enqueue_file_retrieval_sync
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.retrieval.models import RetrievalPartition, RetrievalPartitionState


ExternalFileGrantType = Literal["company", "workspace", "user", "team"]
EXTERNAL_FILE_GRANT_TYPES = frozenset({"company", "workspace", "user", "team"})
_CONTENT_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_RAW_METADATA_BYTES = 64 * 1024
_PENDING_STORAGE_COMPENSATIONS_KEY = "files_external_storage_compensations"


class ExternalFileLifecycleError(RuntimeError):
    pass


class ExternalFileContractError(ExternalFileLifecycleError):
    pass


class ExternalFileAccessDenied(ExternalFileLifecycleError):
    pass


class ExternalFileCorpusConflict(ExternalFileLifecycleError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalFileGrant:
    grant_type: ExternalFileGrantType | str
    target_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExternalFileUpsertResult:
    file: FileManagerFile
    created: bool
    changed: bool
    acl_resolved: bool
    obsolete_storage_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExternalFileDeleteResult:
    file_id: str | None
    changed: bool
    obsolete_storage_keys: tuple[str, ...] = ()


@dataclass(slots=True)
class _StorageCompensationState:
    storage_keys_by_transaction: dict[SessionTransaction, set[str]]
    committed_transactions: set[SessionTransaction]


def upsert_external_file(
    db: Session,
    *,
    actor: User,
    corpus_id: str,
    external_id: str,
    source_kind: str,
    source_id: str,
    expected_file_id: str | None = None,
    filename: str | None,
    content_type: str | None,
    content: BinaryIO,
    size_bytes: int,
    grants: Sequence[ExternalFileGrant],
    acl_resolved: bool = True,
    source_version: str | None = None,
    source_uri: str | None = None,
    source_updated_at: datetime | None = None,
    title: str | None = None,
    author: str | None = None,
    authored_at: datetime | None = None,
    department: str | None = None,
    document_type: str | None = None,
    raw_metadata: Mapping[str, object] | None = None,
) -> ExternalFileUpsertResult:
    """Create or replace one externally managed file and stage retrieval sync.

    Success joins the caller's transaction. A storage or outbox failure rolls
    back that joined unit of work and compensates any newly written object. A
    newly written object also remains compensatable until the caller's outer
    transaction commits successfully.
    Replaced objects are recorded in the existing durable Files cleanup queue
    in the same transaction; ``obsolete_storage_keys`` is diagnostic and
    requires no caller cleanup.
    """

    normalized_external_id = _required_text(external_id, field="external_id", limit=1024)
    normalized_source_kind = _required_text(source_kind, field="source_kind", limit=80)
    normalized_source_id = _required_text(source_id, field="source_id", limit=1024)
    normalized_expected_file_id = _optional_text(expected_file_id, limit=36)
    external_id_sha256 = _identity_sha256(normalized_external_id)
    source_id_sha256 = _identity_sha256(normalized_source_id)
    normalized_source_version = _optional_text(source_version, limit=4096)
    normalized_source_uri = _optional_text(source_uri, limit=2048)
    normalized_title = _optional_text(title, limit=1024)
    normalized_author = _optional_text(author, limit=512)
    normalized_department = _optional_text(department, limit=512)
    normalized_document_type = _optional_text(document_type, limit=255)
    normalized_filename = safe_filename(filename)
    normalized_content_type = str(content_type or "application/octet-stream").strip()
    if not normalized_content_type or len(normalized_content_type) > 160:
        raise ExternalFileContractError("content_type must be between 1 and 160 characters")
    normalized_size = int(size_bytes)
    if normalized_size < 0 or normalized_size > files_service.MAX_FILE_UPLOAD_SIZE:
        raise ExternalFileContractError("size_bytes is outside the supported range")
    content_checksum = _hash_and_rewind(content, expected_size=normalized_size)
    normalized_grants = _normalize_grants(grants)
    normalized_raw_metadata = _bounded_raw_metadata(raw_metadata)

    corpus = _require_source_managed_corpus(db, corpus_id=corpus_id, actor=actor)
    resolved_grants, effective_acl_resolved = _resolve_grants(
        db,
        normalized_grants,
        declared_resolved=bool(acl_resolved),
        workspace_id=corpus.managed_workspace_id,
    )
    matching_source_metadata = list(
        db.scalars(
            select(FileManagerFileSourceMetadata)
            .where(
                FileManagerFileSourceMetadata.corpus_id == corpus.id,
                (
                    (FileManagerFileSourceMetadata.external_id_sha256 == external_id_sha256)
                    | (
                        (FileManagerFileSourceMetadata.source_kind == normalized_source_kind)
                        & (FileManagerFileSourceMetadata.source_id_sha256 == source_id_sha256)
                    )
                ),
            )
            .with_for_update()
        ).all()
    )
    if len(matching_source_metadata) > 1:
        raise ExternalFileCorpusConflict(
            "external and source identities resolve to different files"
        )
    source_metadata = matching_source_metadata[0] if matching_source_metadata else None
    if source_metadata is not None and (
        source_metadata.external_id != normalized_external_id
        or source_metadata.source_kind != normalized_source_kind
        or source_metadata.source_id != normalized_source_id
    ):
        raise ExternalFileCorpusConflict("external source identity is immutable")
    row = db.get(FileManagerFile, source_metadata.file_id) if source_metadata else None
    if source_metadata is not None and row is None:
        raise ExternalFileCorpusConflict("external source metadata references a missing file")
    if row is not None and row.corpus_id != corpus.id:
        raise ExternalFileCorpusConflict("external file identity belongs to another corpus")
    if normalized_expected_file_id is not None and (
        row is None or row.id != normalized_expected_file_id
    ):
        raise ExternalFileCorpusConflict("external file identity changed")

    created = row is None
    was_deleted = bool(row is not None and row.deleted_at is not None)
    file_id = row.id if row is not None else new_id()
    previous_storage_key = row.storage_key if row is not None else None
    previous_content_type = row.content_type if row is not None else None
    content_changed = bool(
        row is None
        or was_deleted
        or source_metadata is None
        or source_metadata.content_checksum != content_checksum
        or previous_content_type != normalized_content_type
    )
    storage_key = (
        f"files/{file_id}/source/{content_checksum}/{new_id()}/{normalized_filename}"
        if content_changed
        else row.storage_key
    )
    previous_grants = _stored_grants(db, file_id) if row is not None else ()
    desired_grants = tuple((grant.grant_type, grant.target_id) for grant in resolved_grants)
    source_bookkeeping_changed = bool(
        source_metadata is None
        or source_metadata.source_version != normalized_source_version
        or source_metadata.content_checksum != content_checksum
        or source_metadata.raw_metadata != normalized_raw_metadata
    )
    typed_metadata_changed = bool(
        source_metadata is None
        or source_metadata.source_uri != normalized_source_uri
        or source_metadata.title != normalized_title
        or source_metadata.author != normalized_author
        or source_metadata.authored_at != authored_at
        or source_metadata.department != normalized_department
        or source_metadata.document_type != normalized_document_type
        or source_metadata.source_updated_at != source_updated_at
        or (row is not None and row.filename != normalized_filename)
    )
    acl_changed = bool(
        source_metadata is None
        or source_metadata.acl_resolved is not effective_acl_resolved
        or previous_grants != desired_grants
    )
    file_changed = bool(
        row is None
        or was_deleted
        or row.filename != normalized_filename
        or row.content_type != normalized_content_type
        or row.size_bytes != normalized_size
        or row.storage_key != storage_key
    )
    changed = file_changed or source_bookkeeping_changed or typed_metadata_changed or acl_changed
    if row is not None and not changed:
        return ExternalFileUpsertResult(
            file=row,
            created=False,
            changed=False,
            acl_resolved=effective_acl_resolved,
        )

    object_write_attempted = False
    object_written = False
    try:
        if row is None:
            row = FileManagerFile(
                id=file_id,
                workspace_id=corpus.managed_workspace_id,
                retrieval_partition_id=corpus.retrieval_partition_id,
                corpus_id=corpus.id,
                folder_id=None,
                owner_id=actor.id,
                filename=normalized_filename,
                content_type=normalized_content_type,
                size_bytes=normalized_size,
                storage_key=storage_key,
                visibility="workspace",
            )
            db.add(row)
            db.flush()
        else:
            row.workspace_id = corpus.managed_workspace_id
            row.retrieval_partition_id = corpus.retrieval_partition_id
            row.folder_id = None
            row.filename = normalized_filename
            row.content_type = normalized_content_type
            row.size_bytes = normalized_size
            row.storage_key = storage_key
            row.visibility = "workspace"
            row.deleted_at = None
            db.add(row)

        if content_changed:
            files_service.purge_file_retrieval_artifact(row)

        if source_metadata is None:
            source_metadata = FileManagerFileSourceMetadata(
                file_id=row.id,
                corpus_id=corpus.id,
                external_id=normalized_external_id,
                external_id_sha256=external_id_sha256,
                source_kind=normalized_source_kind,
                source_id=normalized_source_id,
                source_id_sha256=source_id_sha256,
                content_checksum=content_checksum,
            )
        source_metadata.source_version = normalized_source_version
        source_metadata.source_uri = normalized_source_uri
        source_metadata.source_updated_at = source_updated_at
        source_metadata.title = normalized_title
        source_metadata.author = normalized_author
        source_metadata.authored_at = authored_at
        source_metadata.department = normalized_department
        source_metadata.document_type = normalized_document_type
        source_metadata.content_checksum = content_checksum
        source_metadata.raw_metadata = normalized_raw_metadata
        source_metadata.acl_resolved = effective_acl_resolved
        db.add(source_metadata)

        db.execute(
            delete(FileManagerFileAccessGrant).where(FileManagerFileAccessGrant.file_id == row.id)
        )
        for grant in resolved_grants:
            db.add(
                FileManagerFileAccessGrant(
                    id=new_id(),
                    file_id=row.id,
                    grant_type=grant.grant_type,
                    target_id=grant.target_id,
                    grant_key=_grant_key(grant),
                )
            )
        db.flush()

        if content_changed:
            object_write_attempted = True
            content.seek(0)
            file_storage.put_file_object(
                storage_key=storage_key,
                content=content,
                size_bytes=normalized_size,
                content_type=normalized_content_type,
            )
            object_written = True
        if previous_storage_key is not None and previous_storage_key != storage_key:
            files_service.enqueue_storage_cleanup_job(
                db,
                previous_storage_key,
                error="external_source_replaced",
            )
        if content_changed or typed_metadata_changed:
            enqueue_file_retrieval_sync(db, file=row, operation=RagSyncOperation.UPSERT)
        elif acl_changed:
            enqueue_file_retrieval_sync(
                db,
                file=row,
                operation=RagSyncOperation.VISIBILITY_UPDATE,
            )
    except Exception as error:
        db.rollback()
        if object_write_attempted:
            files_service.remove_storage_object_immediately(storage_key)
        if isinstance(error, ExternalFileLifecycleError):
            raise
        raise ExternalFileLifecycleError("external file upsert failed") from error

    if object_written:
        try:
            _register_storage_compensation(db, storage_key)
        except Exception as error:
            db.rollback()
            files_service.remove_storage_object_immediately(storage_key)
            if isinstance(error, ExternalFileLifecycleError):
                raise
            raise ExternalFileLifecycleError("external file upsert failed") from error

    obsolete_keys = (
        (previous_storage_key,)
        if previous_storage_key is not None and previous_storage_key != storage_key
        else ()
    )
    return ExternalFileUpsertResult(
        file=row,
        created=created,
        changed=True,
        acl_resolved=effective_acl_resolved,
        obsolete_storage_keys=obsolete_keys,
    )


def delete_external_file(
    db: Session,
    *,
    actor: User,
    corpus_id: str,
    external_id: str | None = None,
    file_id: str | None = None,
) -> ExternalFileDeleteResult:
    """Soft-delete an external file idempotently and stage retrieval deletion."""

    corpus = _require_source_managed_corpus(db, corpus_id=corpus_id, actor=actor)
    source_metadata = _lock_source_metadata(
        db,
        corpus_id=corpus.id,
        external_id=external_id,
        file_id=file_id,
    )
    if source_metadata is None:
        return ExternalFileDeleteResult(file_id=None, changed=False)
    row = db.scalar(
        select(FileManagerFile)
        .where(FileManagerFile.id == source_metadata.file_id)
        .with_for_update()
    )
    if row is None or row.corpus_id != corpus.id:
        raise ExternalFileCorpusConflict("external source metadata references an invalid file")
    if row.deleted_at is not None:
        return ExternalFileDeleteResult(file_id=row.id, changed=False)

    row.deleted_at = files_service.utcnow_naive()
    files_service.purge_file_retrieval_artifact(row)
    db.add(row)
    enqueue_file_retrieval_sync(db, file=row, operation=RagSyncOperation.DELETE)
    files_service.enqueue_storage_cleanup_job(
        db,
        row.storage_key,
        error="external_source_deleted",
    )
    return ExternalFileDeleteResult(
        file_id=row.id,
        changed=True,
        obsolete_storage_keys=(row.storage_key,),
    )


def quarantine_external_file(
    db: Session,
    *,
    actor: User,
    corpus_id: str,
    external_id: str | None = None,
    file_id: str | None = None,
) -> bool:
    """Fail one current file closed while its upstream ACL cannot be resolved."""

    corpus = _require_source_managed_corpus(db, corpus_id=corpus_id, actor=actor)
    source_metadata = _lock_source_metadata(
        db,
        corpus_id=corpus.id,
        external_id=external_id,
        file_id=file_id,
    )
    if source_metadata is None:
        return False
    row = db.scalar(
        select(FileManagerFile)
        .where(FileManagerFile.id == source_metadata.file_id)
        .with_for_update()
    )
    if row is None or row.corpus_id != corpus.id:
        raise ExternalFileCorpusConflict("external source metadata references an invalid file")
    grant_count = int(
        db.scalar(
            select(func.count(FileManagerFileAccessGrant.id)).where(
                FileManagerFileAccessGrant.file_id == row.id
            )
        )
        or 0
    )
    if not source_metadata.acl_resolved and grant_count == 0:
        return False
    source_metadata.acl_resolved = False
    db.add(source_metadata)
    db.execute(
        delete(FileManagerFileAccessGrant).where(FileManagerFileAccessGrant.file_id == row.id)
    )
    enqueue_file_retrieval_sync(
        db,
        file=row,
        operation=RagSyncOperation.VISIBILITY_UPDATE,
    )
    return True


def _register_storage_compensation(db: Session, storage_key: str) -> None:
    # Bind the object to the active savepoint when present so a savepoint
    # rollback compensates only objects written inside that savepoint.
    transaction = db.get_nested_transaction() or db.get_transaction()
    if transaction is None:
        raise ExternalFileLifecycleError(
            "external file storage compensation requires an active transaction"
        )
    state = db.info.get(_PENDING_STORAGE_COMPENSATIONS_KEY)
    if not isinstance(state, _StorageCompensationState):
        state = _StorageCompensationState(
            storage_keys_by_transaction={},
            committed_transactions=set(),
        )
        db.info[_PENDING_STORAGE_COMPENSATIONS_KEY] = state
    state.storage_keys_by_transaction.setdefault(transaction, set()).add(storage_key)


@event.listens_for(Session, "after_commit")
def _mark_storage_compensation_transaction_committed(session: Session) -> None:
    state = session.info.get(_PENDING_STORAGE_COMPENSATIONS_KEY)
    if not isinstance(state, _StorageCompensationState):
        return
    transaction = session.get_nested_transaction() or session.get_transaction()
    if transaction is not None:
        state.committed_transactions.add(transaction)


@event.listens_for(Session, "after_transaction_end")
def _settle_storage_compensations(
    session: Session,
    transaction: SessionTransaction,
) -> None:
    state = session.info.get(_PENDING_STORAGE_COMPENSATIONS_KEY)
    if not isinstance(state, _StorageCompensationState):
        return

    # ``after_transaction_end`` also runs when a failed commit is subsequently
    # rolled back or the Session is closed. Only ``after_commit`` proves that a
    # transaction completed successfully.
    storage_keys = state.storage_keys_by_transaction.pop(transaction, set())
    committed = transaction in state.committed_transactions
    state.committed_transactions.discard(transaction)
    if committed and transaction.parent is not None:
        # A released savepoint still depends on its outer transaction.
        state.storage_keys_by_transaction.setdefault(transaction.parent, set()).update(storage_keys)
    elif not committed:
        for storage_key in sorted(storage_keys):
            files_service.remove_storage_object_immediately(storage_key)

    if not state.storage_keys_by_transaction and not state.committed_transactions:
        session.info.pop(_PENDING_STORAGE_COMPENSATIONS_KEY, None)


def _require_source_managed_corpus(
    db: Session,
    *,
    corpus_id: str,
    actor: User,
) -> FileManagerCorpus:
    if not is_current_platform_admin(db, actor.id):
        raise ExternalFileAccessDenied("external source mutation requires platform admin")
    corpus = db.scalar(
        select(FileManagerCorpus).where(FileManagerCorpus.id == corpus_id).with_for_update()
    )
    if (
        corpus is None
        or not corpus.source_managed
        or corpus.authorization_mode != "explicit_grants"
    ):
        raise ExternalFileCorpusConflict("source-managed file corpus was not found")
    partition = db.get(RetrievalPartition, corpus.retrieval_partition_id)
    expected_workspace_id = (
        corpus.managed_workspace_id if corpus.access_scope_kind == "workspace" else None
    )
    if (
        partition is None
        or partition.source_namespace != "files"
        or partition.is_default_ingest
        or partition.state != RetrievalPartitionState.ACTIVE.value
        or partition.managed_workspace_id != corpus.managed_workspace_id
        or partition.candidate_scope_kind != corpus.access_scope_kind
        or partition.candidate_workspace_id != expected_workspace_id
        or partition.candidate_user_id is not None
    ):
        raise ExternalFileCorpusConflict("file corpus partition metadata is invalid")
    return corpus


def _normalize_grants(grants: Sequence[ExternalFileGrant]) -> tuple[ExternalFileGrant, ...]:
    normalized: dict[str, ExternalFileGrant] = {}
    for grant in grants:
        grant_type = str(grant.grant_type or "").strip().lower()
        if grant_type not in EXTERNAL_FILE_GRANT_TYPES:
            raise ExternalFileContractError(f"unsupported grant type: {grant_type or '<empty>'}")
        target_id = str(grant.target_id or "").strip() or None
        if grant_type == "company":
            if target_id is not None:
                raise ExternalFileContractError("company grants must not have a target_id")
        elif target_id is None:
            raise ExternalFileContractError(f"{grant_type} grants require target_id")
        elif len(target_id) > 36:
            raise ExternalFileContractError(f"{grant_type} target_id must not exceed 36 characters")
        normalized_grant = ExternalFileGrant(grant_type=grant_type, target_id=target_id)
        normalized[_grant_key(normalized_grant)] = normalized_grant
    return tuple(normalized[key] for key in sorted(normalized))


def _resolve_grants(
    db: Session,
    grants: tuple[ExternalFileGrant, ...],
    *,
    declared_resolved: bool,
    workspace_id: str,
) -> tuple[tuple[ExternalFileGrant, ...], bool]:
    if not declared_resolved:
        return (), False
    targets_by_type: dict[str, set[str]] = {}
    for grant in grants:
        if grant.target_id is not None:
            targets_by_type.setdefault(str(grant.grant_type), set()).add(grant.target_id)

    resolved_by_type: dict[str, set[str]] = {}
    if targets := targets_by_type.get("workspace"):
        resolved_by_type["workspace"] = set(
            db.scalars(
                select(Workspace.id).where(Workspace.id.in_(targets), Workspace.active.is_(True))
            ).all()
        )
    if targets := targets_by_type.get("user"):
        resolved_by_type["user"] = set(
            db.scalars(
                select(User.id).where(
                    User.id.in_(targets),
                    User.status == "active",
                    User.login_blocked.is_(False),
                )
            ).all()
        )
    if targets := targets_by_type.get("team"):
        resolved_by_type["team"] = set(
            db.scalars(
                select(Team.id).where(
                    Team.id.in_(targets),
                    Team.workspace_id == workspace_id,
                    Team.active.is_(True),
                    Team.trashed_at.is_(None),
                )
            ).all()
        )

    for grant in grants:
        if grant.grant_type == "company":
            continue
        if grant.target_id not in resolved_by_type.get(str(grant.grant_type), set()):
            # Never persist a partial ACL: one unresolved principal closes the file.
            return (), False
    return grants, True


def _stored_grants(db: Session, file_id: str) -> tuple[tuple[str, str | None], ...]:
    return tuple(
        db.execute(
            select(
                FileManagerFileAccessGrant.grant_type,
                FileManagerFileAccessGrant.target_id,
            )
            .where(FileManagerFileAccessGrant.file_id == file_id)
            .order_by(FileManagerFileAccessGrant.grant_key.asc())
        ).all()
    )


def _lock_source_metadata(
    db: Session,
    *,
    corpus_id: str,
    external_id: str | None,
    file_id: str | None,
) -> FileManagerFileSourceMetadata | None:
    normalized_external_id = str(external_id or "").strip() or None
    normalized_file_id = str(file_id or "").strip() or None
    if (normalized_external_id is None) == (normalized_file_id is None):
        raise ExternalFileContractError("exactly one of external_id or file_id is required")
    statement = select(FileManagerFileSourceMetadata).where(
        FileManagerFileSourceMetadata.corpus_id == corpus_id
    )
    if normalized_external_id is not None:
        normalized_external_id = _required_text(
            normalized_external_id,
            field="external_id",
            limit=1024,
        )
        statement = statement.where(
            FileManagerFileSourceMetadata.external_id_sha256
            == _identity_sha256(normalized_external_id)
        )
    else:
        normalized_file_id = _required_text(
            normalized_file_id or "",
            field="file_id",
            limit=36,
        )
        statement = statement.where(FileManagerFileSourceMetadata.file_id == normalized_file_id)
    source_metadata = db.scalar(statement.with_for_update())
    if (
        source_metadata is not None
        and normalized_external_id is not None
        and source_metadata.external_id != normalized_external_id
    ):
        raise ExternalFileCorpusConflict("external source identity hash collision")
    return source_metadata


def _grant_key(grant: ExternalFileGrant) -> str:
    return f"{grant.grant_type}:{grant.target_id or '*'}"


def _identity_sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _hash_and_rewind(content: BinaryIO, *, expected_size: int) -> str:
    digest = sha256()
    actual_size = 0
    try:
        content.seek(0)
        while chunk := content.read(_CONTENT_HASH_CHUNK_BYTES):
            actual_size += len(chunk)
            if actual_size > files_service.MAX_FILE_UPLOAD_SIZE:
                raise ExternalFileContractError("content exceeds the supported size")
            digest.update(chunk)
        content.seek(0)
    except ExternalFileLifecycleError:
        raise
    except Exception as error:
        raise ExternalFileContractError("content must be a seekable binary stream") from error
    if actual_size != expected_size:
        raise ExternalFileContractError(
            f"size_bytes does not match content length ({expected_size} != {actual_size})"
        )
    return digest.hexdigest()


def _required_text(value: str, *, field: str, limit: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > limit:
        raise ExternalFileContractError(f"{field} must be between 1 and {limit} characters")
    return normalized


def _optional_text(value: str | None, *, limit: int) -> str | None:
    normalized = str(value or "").strip() or None
    if normalized is not None and len(normalized) > limit:
        raise ExternalFileContractError(f"value must not exceed {limit} characters")
    return normalized


def _bounded_raw_metadata(raw_metadata: Mapping[str, object] | None) -> dict[str, object]:
    normalized = dict(raw_metadata or {})
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ExternalFileContractError("raw_metadata must be JSON serializable") from error
    if len(encoded) > _MAX_RAW_METADATA_BYTES:
        raise ExternalFileContractError("raw_metadata must not exceed 64 KiB")
    return normalized


__all__ = [
    "ExternalFileAccessDenied",
    "ExternalFileContractError",
    "ExternalFileCorpusConflict",
    "ExternalFileDeleteResult",
    "ExternalFileGrant",
    "ExternalFileLifecycleError",
    "ExternalFileUpsertResult",
    "delete_external_file",
    "quarantine_external_file",
    "upsert_external_file",
]
