from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.files.rag_sync import (
    adopt_legacy_file_retrieval_heads,
    capture_file_retrieval_event_watermark,
    inspect_file_retrieval_reconciliation,
    stage_file_retrieval_reconciliation,
)
from open_work_hub_api.domains.files import rag_sync as files_rag_sync
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFolder,
)
from open_work_hub_api.domains.organization.models import OrganizationUnit
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.retrieval.models import (
    RetrievalPartition,
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.projection_fencing import record_projection_event
from open_work_hub_api.domains.retrieval.projection_fencing import ProjectionEventRef
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


_PARTITION_ID = "6fa05b2e-8f30-4388-af56-c229636fa6c9"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(
        engine,
        tables=[
            OrganizationUnit.__table__,
            User.__table__,
            RetrievalPartition.__table__,
            FileManagerCorpus.__table__,
            FileManagerFolder.__table__,
            FileManagerFile.__table__,
            RetrievalProjectionHead.__table__,
            RetrievalProjectionEvent.__table__,
            SearchIndexJob.__table__,
            RagSyncJob.__table__,
        ],
    )
    session = Session(engine)
    session.add_all(
        [
            User(
                id="user-1",
                login_id="user-1",
                email="user-1@example.com",
                full_name="User 1",
                password_hash="hash",
            ),
            RetrievalPartition(
                id=_PARTITION_ID,
                source_namespace="files",
                candidate_scope_kind="company",
                is_default_ingest=False,
            ),
        ]
    )
    session.flush()
    return session


def _legacy_file(
    *,
    file_id: str,
    checksum: str | None,
    deleted: bool = False,
) -> FileManagerFile:
    return FileManagerFile(
        id=file_id,
        retrieval_partition_id=_PARTITION_ID,
        owner_id="user-1",
        filename=f"{file_id}.txt",
        content_type="text/plain",
        size_bytes=100,
        storage_key=f"files/workspace-1/{file_id}.txt",
        visibility="company",
        extraction_status="ready" if checksum is not None else "pending",
        extraction_content_checksum=checksum,
        extraction_text="cached extracted text" if checksum is not None else None,
        extraction_blocks=[],
        extraction_metadata={},
        deleted_at=(datetime.now(UTC).replace(tzinfo=None) if deleted else None),
    )


def test_legacy_adoption_records_idempotent_repair_heads_without_backend_jobs() -> None:
    db = _session()
    try:
        db.add_all(
            [
                _legacy_file(file_id="file-active", checksum="a" * 64),
                _legacy_file(file_id="file-deleted", checksum=None, deleted=True),
            ]
        )
        db.flush()

        first = adopt_legacy_file_retrieval_heads(db, after_file_id=None, limit=1)
        second = adopt_legacy_file_retrieval_heads(
            db,
            after_file_id=first.next_file_id,
            limit=1,
        )
        repeated = adopt_legacy_file_retrieval_heads(db, after_file_id=None, limit=100)

        assert first.complete is False
        assert first.scanned_files == first.recorded_events == 1
        assert second.complete is True
        assert second.scanned_files == second.recorded_events == 1
        assert repeated.complete is True
        assert repeated.scanned_files == repeated.recorded_events == 0
        assert second.event_watermark == capture_file_retrieval_event_watermark(db)
        events = list(
            db.scalars(
                select(RetrievalProjectionEvent).order_by(
                    RetrievalProjectionEvent.resource_id.asc()
                )
            )
        )
        assert [(row.resource_id, row.change_kind, row.desired_state) for row in events] == [
            ("file-active", "repair", "active"),
            ("file-deleted", "repair", "deleted"),
        ]
        assert events[0].content_checksum == "a" * 64
        assert db.scalar(select(SearchIndexJob)) is None
        assert db.scalar(select(RagSyncJob)) is None
    finally:
        db.close()


def test_legacy_adoption_tombstones_unsupported_and_rejects_unready_active_rows() -> None:
    db = _session()
    try:
        unsupported = _legacy_file(file_id="file-unsupported", checksum=None)
        unsupported.extraction_status = "unsupported"
        db.add(unsupported)
        db.flush()

        adopted = adopt_legacy_file_retrieval_heads(db, after_file_id=None, limit=100)

        assert adopted.recorded_events == 1
        event_row = db.scalar(select(RetrievalProjectionEvent))
        assert event_row is not None
        assert event_row.change_kind == "repair"
        assert event_row.desired_state == "deleted"
        assert event_row.content_checksum is None
    finally:
        db.close()

    db = _session()
    try:
        db.add(_legacy_file(file_id="file-pending", checksum=None))
        db.flush()

        with pytest.raises(ValueError, match="source is not ready"):
            adopt_legacy_file_retrieval_heads(db, after_file_id=None, limit=100)
        assert db.scalar(select(RetrievalProjectionHead)) is None
    finally:
        db.close()


def test_disabled_gate_records_source_head_but_does_not_stage_backend_jobs(
    monkeypatch,
) -> None:
    db = _session()
    try:
        file = _legacy_file(file_id="file-disabled-change", checksum="c" * 64)
        db.add(file)
        db.flush()
        monkeypatch.setattr(files_rag_sync, "FILES_RETRIEVAL_ACTIVE", False)

        files_rag_sync.enqueue_file_retrieval_sync(
            db,
            file=file,
            operation=RagSyncOperation.UPSERT,
        )

        head = db.get(
            RetrievalProjectionHead,
            (FILE_MANAGER_FILE_RESOURCE_TYPE, file.id),
        )
        assert head is not None
        assert head.projection_version == 1
        assert head.desired_state == "active"
        assert head.content_checksum == "c" * 64
        assert capture_file_retrieval_event_watermark(db) > 0
        assert db.scalar(select(SearchIndexJob)) is None
        assert db.scalar(select(RagSyncJob)) is None
    finally:
        db.close()


def test_extraction_completion_refreshes_cached_row_and_advances_head(
    monkeypatch,
) -> None:
    db = _session()
    try:
        file = _legacy_file(file_id="file-extracted-later", checksum=None)
        db.add(file)
        db.flush()
        monkeypatch.setattr(files_rag_sync, "FILES_RETRIEVAL_ACTIVE", False)
        files_rag_sync.enqueue_file_retrieval_sync(
            db,
            file=file,
            operation=RagSyncOperation.UPSERT,
        )
        first = db.scalar(
            select(RetrievalProjectionEvent).where(RetrievalProjectionEvent.resource_id == file.id)
        )
        assert first is not None and first.content_checksum is None
        stale_ref = ProjectionEventRef(
            event_sequence=first.event_sequence,
            resource_type=first.resource_type,
            resource_id=first.resource_id,
            projection_version=first.projection_version,
            retrieval_partition_id=first.retrieval_partition_id,
            change_kind=first.change_kind,
            desired_state=first.desired_state,
            content_checksum=first.content_checksum,
            visibility_checksum=first.visibility_checksum,
        )
        db.execute(
            update(FileManagerFile)
            .where(FileManagerFile.id == file.id)
            .values(
                extraction_status="ready",
                extraction_content_checksum="e" * 64,
                extraction_text="cached extraction",
                extraction_blocks=[{"text": "cached extraction"}],
            )
            .execution_options(synchronize_session=False)
        )
        assert file.extraction_content_checksum is None
        monkeypatch.setattr(files_rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
        monkeypatch.setattr(
            files_rag_sync,
            "get_settings",
            lambda: SimpleNamespace(rag_enabled=True),
        )

        files_rag_sync.mark_file_projection_prepared(
            db,
            file_id=file.id,
            projection_event=stale_ref,
        )

        head = db.get(
            RetrievalProjectionHead,
            (FILE_MANAGER_FILE_RESOURCE_TYPE, file.id),
            populate_existing=True,
        )
        assert head is not None
        assert head.projection_version == 2
        assert head.content_checksum == "e" * 64
        rag_job = db.scalar(select(RagSyncJob))
        assert rag_job is not None
        assert rag_job.projection_version == 2
        assert rag_job.content_checksum == "e" * 64
        assert db.scalar(select(SearchIndexJob)) is None
    finally:
        db.close()


def test_reconciliation_stages_only_latest_file_head_through_captured_watermark() -> None:
    db = _session()
    try:
        record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id="file-1",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            content_checksum="a" * 64,
        )
        latest = record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id="file-1",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="delete",
            desired_state="deleted",
        )
        watermark = capture_file_retrieval_event_watermark(db)

        result = stage_file_retrieval_reconciliation(
            db,
            after_event_sequence=0,
            through_event_sequence=watermark,
            limit=100,
        )

        assert result.complete is True
        assert result.target_event_sequence == watermark == latest.event_sequence
        assert result.next_event_sequence == watermark
        assert result.scanned_events == 2
        assert result.staged_resources == 1
        search_jobs = list(db.scalars(select(SearchIndexJob)))
        rag_jobs = list(db.scalars(select(RagSyncJob)))
        assert len(search_jobs) == len(rag_jobs) == 1
        assert search_jobs[0].projection_event_sequence == latest.event_sequence
        assert search_jobs[0].projection_version == latest.projection_version
        assert search_jobs[0].operation == "delete"
        assert rag_jobs[0].projection_event_sequence == latest.event_sequence
        assert rag_jobs[0].projection_version == latest.projection_version
        assert rag_jobs[0].operation == "delete"
    finally:
        db.close()


def test_reconciliation_preserves_company_scope_with_workspace_diagnostic_identity() -> None:
    db = _session()
    try:
        partition = db.get(RetrievalPartition, _PARTITION_ID)
        assert partition is not None
        partition.candidate_scope_kind = "company"
        db.flush()
        event_ref = record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id="file-company",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="visibility",
            desired_state="active",
            content_checksum="d" * 64,
        )

        stage_file_retrieval_reconciliation(
            db,
            after_event_sequence=0,
            through_event_sequence=event_ref.event_sequence,
        )

        search_job = db.scalar(select(SearchIndexJob))
        rag_job = db.scalar(select(RagSyncJob))
        assert search_job is not None and rag_job is not None
        assert not hasattr(search_job, "workspace_id")
        assert search_job.operation == "upsert"
        assert rag_job.scope_kind == "company"
        assert not hasattr(rag_job, "workspace_id")
        assert rag_job.operation == "visibility_update"
    finally:
        db.close()


def test_reconciliation_uses_current_source_workspace_after_no_reindex_move() -> None:
    db = _session()
    try:
        file = _legacy_file(file_id="file-moved", checksum="f" * 64)
        db.add(file)
        db.flush()
        event_ref = record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=file.id,
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            content_checksum="f" * 64,
        )
        db.flush()
        partition = db.get(RetrievalPartition, _PARTITION_ID)
        assert partition is not None
        db.flush()

        stage_file_retrieval_reconciliation(
            db,
            after_event_sequence=0,
            through_event_sequence=event_ref.event_sequence,
        )

        search_job = db.scalar(select(SearchIndexJob))
        rag_job = db.scalar(select(RagSyncJob))
        assert search_job is not None and rag_job is not None
        assert not hasattr(search_job, "workspace_id")
        assert rag_job.scope_kind == "company"
        assert not hasattr(rag_job, "workspace_id")
        assert search_job.retrieval_partition_id == rag_job.retrieval_partition_id == _PARTITION_ID
        assert search_job.projection_version == rag_job.projection_version == 1
    finally:
        db.close()


def test_reactivation_watermark_requires_both_backends_and_no_newer_file_event() -> None:
    db = _session()
    try:
        event_ref = record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id="file-1",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="delete",
            desired_state="deleted",
        )
        watermark = capture_file_retrieval_event_watermark(db)
        stage_file_retrieval_reconciliation(
            db,
            after_event_sequence=0,
            through_event_sequence=watermark,
        )

        pending = inspect_file_retrieval_reconciliation(
            db,
            through_event_sequence=watermark,
        )

        assert pending.caught_up is False
        assert pending.current_event_sequence == watermark
        assert pending.keyword_remaining == 1
        assert pending.vector_remaining == 1

        search_job = db.scalar(select(SearchIndexJob))
        rag_job = db.scalar(select(RagSyncJob))
        assert search_job is not None and rag_job is not None
        search_job.status = "succeeded"
        rag_job.status = "succeeded"
        db.flush()

        complete = inspect_file_retrieval_reconciliation(
            db,
            through_event_sequence=watermark,
        )
        assert complete.caught_up is True
        assert complete.keyword_remaining == 0
        assert complete.vector_remaining == 0

        newer = record_projection_event(
            db,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id="file-1",
            retrieval_partition_id=_PARTITION_ID,
            change_kind="content",
            desired_state="active",
            content_checksum="b" * 64,
        )
        assert newer.event_sequence > event_ref.event_sequence
        drifted = inspect_file_retrieval_reconciliation(
            db,
            through_event_sequence=watermark,
        )
        assert drifted.caught_up is False
        assert drifted.current_event_sequence == newer.event_sequence
    finally:
        db.close()
