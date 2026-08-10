from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import utcnow_naive
from open_alm_api.domains.mcloudoc.contracts import (
    CompleteIngestRun,
    McloudocChange,
    StartIngestRun,
)
from open_alm_api.domains.mcloudoc.models import (
    McloudocDocument,
    McloudocIngestRun,
    McloudocSource,
)
from open_alm_api.domains.mcloudoc.ports import FilesIngressPort, FilesUpsertCommand


MAX_RECORDED_RUN_ERRORS = 100


class McloudocCoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ApplyChangeResult:
    document_id: str
    outcome: str
    file_id: str | None
    idempotent: bool = False


def create_source(
    db: Session,
    *,
    name: str,
    scope_type: str,
    scope_id: str,
    corpus_id: str,
    ingest_owner_id: str,
) -> McloudocSource:
    normalized_name = name.strip()
    if not normalized_name or len(normalized_name) > 255:
        raise McloudocCoreError("source_name_invalid")
    if scope_type not in {"workspace", "company"}:
        raise McloudocCoreError("source_scope_type_invalid")
    if not scope_id or not corpus_id or not ingest_owner_id:
        raise McloudocCoreError("source_binding_invalid")

    source = McloudocSource(
        id=str(uuid4()),
        name=normalized_name,
        scope_type=scope_type,
        scope_id=scope_id,
        corpus_id=corpus_id,
        ingest_owner_id=ingest_owner_id,
        enabled=False,
    )
    db.add(source)
    db.flush()
    return source


def start_ingest_run(db: Session, *, request: StartIngestRun) -> McloudocIngestRun:
    source = _lock_source(db, request.source_id)
    delivery_hash = _identity_hash(request.delivery_id)
    existing = db.scalar(
        select(McloudocIngestRun).where(
            McloudocIngestRun.source_id == source.id,
            McloudocIngestRun.delivery_id_sha256 == delivery_hash,
        )
    )
    if existing is not None:
        if (
            existing.delivery_id != request.delivery_id
            or existing.mode != request.mode
            or existing.continuation_from != request.continuation
        ):
            raise McloudocCoreError("delivery_idempotency_conflict")
        return existing

    if not source.enabled:
        raise McloudocCoreError("source_inactive")
    if source.active_run_id is not None:
        raise McloudocCoreError("source_ingest_already_running")
    if source.current_continuation != request.continuation:
        raise McloudocCoreError("continuation_conflict")

    run = McloudocIngestRun(
        id=str(uuid4()),
        source_id=source.id,
        mode=request.mode,
        delivery_id=request.delivery_id,
        delivery_id_sha256=delivery_hash,
        status="running",
        continuation_from=request.continuation,
        errors=[],
    )
    db.add(run)
    source.active_run_id = run.id
    db.flush()
    return run


def apply_change(
    db: Session,
    *,
    run_id: str,
    change: McloudocChange,
    files: FilesIngressPort,
) -> ApplyChangeResult:
    run = _lock_run(db, run_id)
    source = _lock_source(db, run.source_id)
    _require_active_run(source, run)
    if change.delivery_id != run.delivery_id:
        raise McloudocCoreError("change_delivery_id_mismatch")

    document = _lock_or_create_document(db, source_id=source.id, external_id=change.external_id)
    fingerprint = _delivery_fingerprint(change)
    if document.last_delivery_id == change.delivery_id:
        if document.last_delivery_fingerprint != fingerprint:
            raise McloudocCoreError("delivery_payload_conflict")
        return ApplyChangeResult(
            document_id=document.id,
            outcome="unchanged",
            file_id=document.file_id,
            idempotent=True,
        )

    if change.operation == "delete":
        document.opaque_revision = change.opaque_revision
        document.opaque_checksum = change.checksum
        outcome = _apply_delete(document, files=files, reason="source_delete")
    else:
        outcome = _apply_upsert(source, document, change=change, files=files)

    document.last_delivery_id = change.delivery_id
    document.last_delivery_fingerprint = fingerprint
    document.last_seen_run_id = run.id
    run.received_count += 1
    if outcome == "upserted":
        run.upserted_count += 1
    elif outcome == "deleted":
        run.deleted_count += 1
    elif outcome == "quarantined":
        run.quarantined_count += 1
    else:
        run.unchanged_count += 1
    db.flush()
    return ApplyChangeResult(
        document_id=document.id,
        outcome=outcome,
        file_id=document.file_id,
    )


def complete_ingest_run(
    db: Session,
    *,
    run_id: str,
    request: CompleteIngestRun,
    files: FilesIngressPort,
) -> McloudocIngestRun:
    run = _lock_run(db, run_id)
    source = _lock_source(db, run.source_id)
    if run.mode == "incremental" and request.complete_snapshot:
        raise McloudocCoreError("incremental_run_cannot_complete_snapshot")

    requested_is_complete = run.mode == "incremental" or request.complete_snapshot
    if run.status == "completed":
        if (
            run.continuation_to != request.continuation
            or run.is_complete != requested_is_complete
        ):
            raise McloudocCoreError("completion_idempotency_conflict")
        return run

    _require_active_run(source, run)
    run.continuation_to = request.continuation
    run.is_complete = requested_is_complete
    if run.mode == "snapshot" and request.complete_snapshot:
        missing_documents = tuple(
            db.scalars(
                select(McloudocDocument)
                .where(
                    McloudocDocument.source_id == source.id,
                    McloudocDocument.status != "deleted",
                    or_(
                        McloudocDocument.last_seen_run_id.is_(None),
                        McloudocDocument.last_seen_run_id != run.id,
                    ),
                )
                .with_for_update()
            )
        )
        for document in missing_documents:
            outcome = _apply_delete(document, files=files, reason="complete_snapshot_missing")
            if outcome == "deleted":
                run.deleted_count += 1

    if run.is_complete:
        source.current_continuation = request.continuation
    run.status = "completed"
    run.completed_at = utcnow_naive()
    source.active_run_id = None
    db.flush()
    return run


def fail_ingest_run(
    db: Session,
    *,
    run_id: str,
    code: str,
    detail: str | None = None,
) -> McloudocIngestRun:
    run = _lock_run(db, run_id)
    source = _lock_source(db, run.source_id)
    _require_active_run(source, run)
    errors = list(run.errors)
    if len(errors) < MAX_RECORDED_RUN_ERRORS:
        errors.append(
            {
                "code": str(code)[:80],
                "detail": str(detail)[:512] if detail is not None else None,
            }
        )
    run.errors = errors
    run.failed_count += 1
    run.status = "failed"
    run.completed_at = utcnow_naive()
    source.active_run_id = None
    db.flush()
    return run


def _apply_upsert(
    source: McloudocSource,
    document: McloudocDocument,
    *,
    change: McloudocChange,
    files: FilesIngressPort,
) -> str:
    _copy_change_metadata(document, change)
    quarantine_code: str | None = None
    if change.raw_acl is None:
        quarantine_code = "acl_missing"
    elif not change.acl_resolution_complete:
        quarantine_code = "acl_unresolved"

    if quarantine_code is not None:
        if document.file_id is not None:
            files.quarantine(file_id=document.file_id, reason=quarantine_code)
        document.status = "quarantined"
        document.quarantine_code = quarantine_code
        document.quarantine_detail = "source ACL is not safe to enforce"
        document.deleted_at = None
        return "quarantined"

    assert change.checksum is not None
    assert change.filename is not None
    assert change.content_type is not None
    assert change.searchable_content is not None
    result = files.upsert(
        FilesUpsertCommand(
            source_id=source.id,
            document_id=document.id,
            existing_file_id=document.file_id,
            scope_type=source.scope_type,
            scope_id=source.scope_id,
            corpus_id=source.corpus_id,
            ingest_owner_id=source.ingest_owner_id,
            external_id=document.external_id,
            opaque_revision=change.opaque_revision,
            checksum=change.checksum,
            filename=change.filename,
            content_type=change.content_type,
            content=change.searchable_content,
            title=change.title,
            author=change.author,
            authored_at=_naive_utc(change.authored_at),
            department=change.department,
            document_type=change.document_type,
            source_updated_at=_naive_utc(change.source_updated_at),
            source_uri=change.source_uri,
            raw_metadata=dict(change.raw_metadata),
            resolved_grants=change.resolved_grants,
        )
    )
    if not result.file_id:
        raise McloudocCoreError("files_resource_id_missing")
    if document.file_id is not None and document.file_id != result.file_id:
        raise McloudocCoreError("files_resource_identity_changed")

    if not result.acl_resolved:
        document.file_id = result.file_id
        document.status = "quarantined"
        document.quarantine_code = "acl_principal_unresolved"
        document.quarantine_detail = "one or more resolved principals are no longer current"
        document.deleted_at = None
        return "quarantined"

    was_active = document.status == "active"
    document.file_id = result.file_id
    document.status = "active"
    document.quarantine_code = None
    document.quarantine_detail = None
    document.deleted_at = None
    return "unchanged" if was_active and not result.changed else "upserted"


def _apply_delete(
    document: McloudocDocument,
    *,
    files: FilesIngressPort,
    reason: str,
) -> str:
    if document.status == "deleted":
        return "unchanged"
    if document.file_id is not None:
        files.delete(file_id=document.file_id, reason=reason)
    document.status = "deleted"
    document.quarantine_code = None
    document.quarantine_detail = None
    document.deleted_at = utcnow_naive()
    return "deleted"


def _copy_change_metadata(document: McloudocDocument, change: McloudocChange) -> None:
    document.opaque_revision = change.opaque_revision
    document.opaque_checksum = change.checksum
    document.filename = change.filename
    document.content_type = change.content_type
    document.size_bytes = change.size_bytes
    document.title = change.title
    document.author = change.author
    document.authored_at = _naive_utc(change.authored_at)
    document.department = change.department
    document.document_type = change.document_type
    document.source_updated_at = _naive_utc(change.source_updated_at)
    document.source_uri = change.source_uri
    document.raw_metadata = _json_copy(change.raw_metadata)
    document.raw_acl = _json_copy(change.raw_acl)
    document.resolved_grants = [grant.model_dump(mode="json") for grant in change.resolved_grants]


def _lock_source(db: Session, source_id: str) -> McloudocSource:
    source = db.scalar(
        select(McloudocSource).where(McloudocSource.id == source_id).with_for_update()
    )
    if source is None:
        raise McloudocCoreError("source_not_found")
    return source


def _lock_run(db: Session, run_id: str) -> McloudocIngestRun:
    run = db.scalar(
        select(McloudocIngestRun).where(McloudocIngestRun.id == run_id).with_for_update()
    )
    if run is None:
        raise McloudocCoreError("ingest_run_not_found")
    return run


def _require_active_run(source: McloudocSource, run: McloudocIngestRun) -> None:
    if run.status != "running" or source.active_run_id != run.id:
        raise McloudocCoreError("ingest_run_not_active")


def _lock_or_create_document(
    db: Session,
    *,
    source_id: str,
    external_id: str,
) -> McloudocDocument:
    external_id_hash = _identity_hash(external_id)
    document = db.scalar(
        select(McloudocDocument)
        .where(
            McloudocDocument.source_id == source_id,
            McloudocDocument.external_id_sha256 == external_id_hash,
        )
        .with_for_update()
    )
    if document is not None:
        if document.external_id != external_id:
            raise McloudocCoreError("external_id_hash_collision")
        return document

    document = McloudocDocument(
        id=str(uuid4()),
        source_id=source_id,
        external_id=external_id,
        external_id_sha256=external_id_hash,
        status="quarantined",
        raw_metadata={},
        raw_acl=None,
        resolved_grants=[],
    )
    db.add(document)
    db.flush()
    return document


def _delivery_fingerprint(change: McloudocChange) -> str:
    payload = change.model_dump(mode="json", exclude={"searchable_content"})
    payload["searchable_content_sha256"] = (
        sha256(change.searchable_content).hexdigest()
        if change.searchable_content is not None
        else None
    )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _identity_hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _json_copy(value):
    if value is None:
        return None
    return json.loads(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
