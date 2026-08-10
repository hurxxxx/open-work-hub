from __future__ import annotations

import asyncio
from collections.abc import Iterator
from io import BytesIO
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import OrgUnit, User, Workspace, utcnow_naive
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRecordHistory,
    LegacyIssueVehicleModel,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleModuleChecklistAttachment,
    LegacyIssueVehicleModuleChecklistAttachmentCleanup,
    LegacyIssueVehicleModuleChecklistRecord,
    LegacyIssueVehicleStage,
)
from ai_do_api.domains.legacy_issues.vehicle_module_checklist_attachments import (
    VehicleModuleChecklistAttachmentStorage,
    VehicleModuleChecklistAttachmentUpload,
    delete_vehicle_module_checklist_attachment,
    get_vehicle_module_checklist_attachment,
    list_vehicle_module_checklist_attachments_for_records,
    normalize_attachment_content_type,
    open_vehicle_module_checklist_attachment,
    process_all_pending_vehicle_module_checklist_attachment_cleanups,
    process_pending_vehicle_module_checklist_attachment_cleanups,
    read_vehicle_module_checklist_attachment_upload,
    safe_attachment_filename,
    upload_vehicle_module_checklist_attachment,
)
from ai_do_api.domains.legacy_issues.vehicle_module_checklists import (
    delete_vehicle_module_checklist,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            OrgUnit.__table__,
            Workspace.__table__,
            User.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueRecordHistory.__table__,
            LegacyIssueVehicleModel.__table__,
            LegacyIssueVehicleStage.__table__,
            LegacyIssueVehicleModuleChecklist.__table__,
            LegacyIssueVehicleModuleChecklistRecord.__table__,
            LegacyIssueVehicleModuleChecklistAttachment.__table__,
            LegacyIssueVehicleModuleChecklistAttachmentCleanup.__table__,
        ],
    )
    return Session(engine)


def _checklist_scope(
    db: Session,
) -> tuple[
    Workspace,
    User,
    LegacyIssueVehicleModuleChecklist,
    LegacyIssueVehicleModuleChecklistRecord,
]:
    now = utcnow_naive()
    workspace = Workspace(id="workspace-1", key="workspace-1", name="Workspace 1")
    user = User(
        id="user-1",
        login_id="user-1",
        email="user-1@example.com",
        full_name="User 1",
        password_hash="hash",
        status="active",
    )
    revision = LegacyIssueDataRevision(
        id="revision-1",
        workspace_id=workspace.id,
        dataset_key="legacy_issue.module.aircon",
        revision_no=1,
        status="published",
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    vehicle = LegacyIssueVehicleModel(
        id="vehicle-1",
        workspace_id=workspace.id,
        vehicle_code="CAR-1",
        vehicle_code_normalized="car-1",
        active=True,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    stage = LegacyIssueVehicleStage(
        id="stage-1",
        workspace_id=workspace.id,
        vehicle_model_id=vehicle.id,
        name="P0",
        name_normalized="p0",
        sequence_no=1,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    checklist = LegacyIssueVehicleModuleChecklist(
        id="checklist-1",
        workspace_id=workspace.id,
        vehicle_model_id=vehicle.id,
        vehicle_stage_id=stage.id,
        module_key="aircon",
        status="draft",
        source_dataset_key="common-master",
        source_master_revision_id=revision.id,
        source_master_revision_no=1,
        definition_snapshot={},
        row_count=1,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    record = LegacyIssueVehicleModuleChecklistRecord(
        id="record-1",
        workspace_id=workspace.id,
        checklist_id=checklist.id,
        source_record_id="master-record-1",
        source_stable_record_id="master-stable-record-1",
        sort_order=1,
        field_values={"check_plan": "verify"},
        created_at=now,
        updated_at=now,
    )
    db.add_all([workspace, user, revision, vehicle, stage, checklist, record])
    db.commit()
    return workspace, user, checklist, record


def _prepared_upload(
    content: bytes,
    *,
    filename: str = "evidence.pdf",
    content_type: str = "application/pdf",
) -> VehicleModuleChecklistAttachmentUpload:
    buffer: SpooledTemporaryFile[bytes] = SpooledTemporaryFile()
    buffer.write(content)
    buffer.seek(0)
    return VehicleModuleChecklistAttachmentUpload(
        content=buffer,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
    )


def _install_fake_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple["_FakeStorageClient", VehicleModuleChecklistAttachmentStorage]:
    from ai_do_api.domains.legacy_issues import (
        vehicle_module_checklist_attachments as attachment_service,
    )

    client = _FakeStorageClient()
    storage = VehicleModuleChecklistAttachmentStorage(
        bucket_name="test-bucket",
        client=client,
    )
    monkeypatch.setattr(
        attachment_service,
        "vehicle_module_checklist_attachment_storage",
        lambda: storage,
    )
    monkeypatch.setattr(attachment_service, "ensure_bucket", lambda: None)
    return client, storage


def test_attachment_upload_reader_counts_chunks_and_rejects_empty_and_oversize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_do_api.domains.legacy_issues import (
        vehicle_module_checklist_attachments as attachment_service,
    )

    file = _AsyncUploadFile(
        chunks=[b"abc", b"def"],
        filename="../unsafe/ evidence?.PDF ",
        content_type="Application/PDF; charset=binary",
    )
    upload = asyncio.run(read_vehicle_module_checklist_attachment_upload(file))
    try:
        assert upload.content.read() == b"abcdef"
        assert upload.size_bytes == 6
        assert upload.filename == "evidence_.PDF"
        assert upload.content_type == "application/pdf"
        assert file.requested_sizes == [1024 * 1024, 1024 * 1024, 1024 * 1024]
    finally:
        upload.content.close()

    with pytest.raises(HTTPException) as empty:
        asyncio.run(
            read_vehicle_module_checklist_attachment_upload(
                _AsyncUploadFile(chunks=[], filename="empty.txt", content_type="text/plain")
            )
        )
    assert empty.value.status_code == 422
    assert empty.value.detail.code == "legacy_issues.vehicle_module_checklist_attachment_empty"

    monkeypatch.setattr(
        attachment_service,
        "VEHICLE_MODULE_CHECKLIST_ATTACHMENT_MAX_BYTES",
        3,
    )
    with pytest.raises(HTTPException) as oversized:
        asyncio.run(
            read_vehicle_module_checklist_attachment_upload(
                _AsyncUploadFile(
                    chunks=[b"123", b"4"],
                    filename="large.bin",
                    content_type=None,
                )
            )
        )
    assert oversized.value.status_code == 413
    assert (
        oversized.value.detail.code == "legacy_issues.vehicle_module_checklist_attachment_too_large"
    )


def test_attachment_filename_and_content_type_are_normalized() -> None:
    assert safe_attachment_filename(r"C:\folder\bad<>name?.txt") == "bad_name_.txt"
    assert safe_attachment_filename("../") == "unnamed"
    assert normalize_attachment_content_type(" text/plain; charset=UTF-8 ") == "text/plain"
    assert normalize_attachment_content_type("bad\r\ntype") == "application/octet-stream"


def test_checklist_record_supports_multiple_attachments_and_completed_read_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, user, checklist, record = _checklist_scope(db)
        uploads = [
            _prepared_upload(b"one", filename="one.txt", content_type="text/plain"),
            _prepared_upload(b"two", filename="two.pdf"),
        ]
        try:
            rows = [
                upload_vehicle_module_checklist_attachment(
                    db,
                    workspace=workspace,
                    user=user,
                    checklist=checklist,
                    record_id=record.id,
                    upload=upload,
                )
                for upload in uploads
            ]
            db.commit()
        finally:
            for upload in uploads:
                upload.content.close()

        grouped = list_vehicle_module_checklist_attachments_for_records(
            db,
            workspace=workspace,
            checklist=checklist,
            record_ids=[record.id],
        )
        assert {item.filename for item in grouped[record.id]} == {"one.txt", "two.pdf"}
        assert len(client.put_calls) == 2

        content = open_vehicle_module_checklist_attachment(
            db,
            workspace=workspace,
            checklist=checklist,
            attachment_id=rows[0].id,
        )
        assert b"".join(content.body) == b"one"
        assert content.headers["Cache-Control"] == "no-store"
        assert content.headers["X-Content-Type-Options"] == "nosniff"
        assert "filename*=UTF-8''one.txt" in content.headers["Content-Disposition"]

        checklist.status = "completed"
        db.commit()
        completed_content = open_vehicle_module_checklist_attachment(
            db,
            workspace=workspace,
            checklist=checklist,
            attachment_id=rows[1].id,
        )
        assert b"".join(completed_content.body) == b"two"

        blocked_upload = _prepared_upload(b"blocked")
        try:
            with pytest.raises(HTTPException) as upload_error:
                upload_vehicle_module_checklist_attachment(
                    db,
                    workspace=workspace,
                    user=user,
                    checklist=checklist,
                    record_id=record.id,
                    upload=blocked_upload,
                )
        finally:
            blocked_upload.content.close()
        assert upload_error.value.status_code == 409

        with pytest.raises(HTTPException) as delete_error:
            delete_vehicle_module_checklist_attachment(
                db,
                workspace=workspace,
                user=user,
                checklist=checklist,
                attachment_id=rows[0].id,
            )
        assert delete_error.value.status_code == 409


def test_attachment_scope_delete_history_and_hard_checklist_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, user, checklist, record = _checklist_scope(db)
        upload = _prepared_upload(b"delete-me")
        try:
            row = upload_vehicle_module_checklist_attachment(
                db,
                workspace=workspace,
                user=user,
                checklist=checklist,
                record_id=record.id,
                upload=upload,
            )
            db.commit()
        finally:
            upload.content.close()

        other_checklist = _other_checklist(db, workspace=workspace, user=user)
        with pytest.raises(HTTPException) as cross_checklist:
            get_vehicle_module_checklist_attachment(
                db,
                workspace=workspace,
                checklist=other_checklist,
                attachment_id=row.id,
            )
        assert cross_checklist.value.status_code == 404

        other_workspace = Workspace(
            id="workspace-2",
            key="workspace-2",
            name="Workspace 2",
        )
        db.add(other_workspace)
        db.commit()
        with pytest.raises(HTTPException) as cross_workspace:
            get_vehicle_module_checklist_attachment(
                db,
                workspace=other_workspace,
                checklist=checklist,
                attachment_id=row.id,
            )
        assert cross_workspace.value.status_code == 404

        row_id = row.id
        storage_key = row.storage_key
        cleanup = delete_vehicle_module_checklist_attachment(
            db,
            workspace=workspace,
            user=user,
            checklist=checklist,
            attachment_id=row_id,
        )
        assert db.get(LegacyIssueVehicleModuleChecklistAttachment, row_id) is None
        assert db.get(LegacyIssueVehicleModuleChecklistAttachmentCleanup, cleanup.id) is not None
        assert storage_key in client.objects
        assert storage_key not in client.remove_calls
        db.commit()
        assert storage_key in client.objects

        removed, failed = process_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            workspace=workspace,
        )
        assert (removed, failed) == (1, 0)
        assert db.get(LegacyIssueVehicleModuleChecklistAttachmentCleanup, cleanup.id) is None
        assert storage_key not in client.objects
        assert storage_key in client.remove_calls
        actions = list(
            db.scalars(
                select(LegacyIssueRecordHistory.action).where(
                    LegacyIssueRecordHistory.record_id == record.id
                )
            )
        )
        assert actions == ["attachment_upload", "attachment_delete"]

        second_upload = _prepared_upload(b"hard-delete")
        try:
            second = upload_vehicle_module_checklist_attachment(
                db,
                workspace=workspace,
                user=user,
                checklist=checklist,
                record_id=record.id,
                upload=second_upload,
            )
            db.commit()
        finally:
            second_upload.content.close()
        second_id = second.id
        second_storage_key = second.storage_key
        cleanups = delete_vehicle_module_checklist(
            db,
            workspace=workspace,
            checklist_id=checklist.id,
        )
        assert len(cleanups) == 1
        assert db.get(LegacyIssueVehicleModuleChecklistAttachment, second_id) is None
        assert second_storage_key in client.objects
        assert second_storage_key not in client.remove_calls
        db.commit()
        removed, failed = process_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            workspace=workspace,
        )
        assert (removed, failed) == (1, 0)
        assert db.get(LegacyIssueVehicleModuleChecklistAttachment, second_id) is None
        assert second_storage_key not in client.objects
        assert second_storage_key in client.remove_calls


def test_attachment_delete_rollback_preserves_metadata_object_and_discards_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, user, checklist, record = _checklist_scope(db)
        upload = _prepared_upload(b"rollback-safe")
        try:
            row = upload_vehicle_module_checklist_attachment(
                db,
                workspace=workspace,
                user=user,
                checklist=checklist,
                record_id=record.id,
                upload=upload,
            )
            db.commit()
        finally:
            upload.content.close()
        row_id = row.id
        storage_key = row.storage_key

        cleanup = delete_vehicle_module_checklist_attachment(
            db,
            workspace=workspace,
            user=user,
            checklist=checklist,
            attachment_id=row_id,
        )
        assert db.get(LegacyIssueVehicleModuleChecklistAttachment, row_id) is None
        assert db.get(LegacyIssueVehicleModuleChecklistAttachmentCleanup, cleanup.id) is not None
        assert storage_key in client.objects

        db.rollback()

        assert db.get(LegacyIssueVehicleModuleChecklistAttachment, row_id) is not None
        assert db.get(LegacyIssueVehicleModuleChecklistAttachmentCleanup, cleanup.id) is None
        assert storage_key in client.objects
        assert storage_key not in client.remove_calls


def test_attachment_cleanup_failure_is_durable_and_retried_until_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, user, checklist, record = _checklist_scope(db)
        upload = _prepared_upload(b"retry-cleanup")
        try:
            row = upload_vehicle_module_checklist_attachment(
                db,
                workspace=workspace,
                user=user,
                checklist=checklist,
                record_id=record.id,
                upload=upload,
            )
            db.commit()
        finally:
            upload.content.close()
        storage_key = row.storage_key
        client.remove_failures[storage_key] = 1

        cleanup = delete_vehicle_module_checklist_attachment(
            db,
            workspace=workspace,
            user=user,
            checklist=checklist,
            attachment_id=row.id,
        )
        db.commit()

        removed, failed = process_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            workspace=workspace,
        )
        assert (removed, failed) == (0, 1)
        pending = db.get(LegacyIssueVehicleModuleChecklistAttachmentCleanup, cleanup.id)
        assert pending is not None
        assert pending.attempt_count == 1
        assert pending.last_error == "RuntimeError"
        assert pending.last_attempted_at is not None
        assert storage_key in client.objects

        removed, failed = process_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            workspace=workspace,
        )
        assert (removed, failed) == (1, 0)
        assert db.get(LegacyIssueVehicleModuleChecklistAttachmentCleanup, cleanup.id) is None
        assert storage_key not in client.objects
        assert client.remove_calls.count(storage_key) == 2


def test_periodic_cleanup_drains_more_than_request_limit_across_workspaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, _user, _checklist, _record = _checklist_scope(db)
        other_workspace = Workspace(
            id="workspace-2",
            key="workspace-2",
            name="Workspace 2",
        )
        db.add(other_workspace)
        rows = [
            LegacyIssueVehicleModuleChecklistAttachmentCleanup(
                id=f"cleanup-{index}",
                workspace_id=(workspace.id if index % 2 == 0 else other_workspace.id),
                storage_key=f"checklists/orphan-{index}",
                created_at=utcnow_naive(),
            )
            for index in range(105)
        ]
        db.add_all(rows)
        for row in rows:
            client.objects[row.storage_key] = b"orphan"
        db.commit()

        removed, failed = process_all_pending_vehicle_module_checklist_attachment_cleanups(
            db,
            limit=1000,
            storage=storage,
        )

        assert (removed, failed) == (105, 0)
        assert client.objects == {}
        assert list(db.scalars(select(LegacyIssueVehicleModuleChecklistAttachmentCleanup.id))) == []


def test_attachment_upload_flush_failure_removes_written_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, user, checklist, record = _checklist_scope(db)
        original_flush = db.flush

        def fail_flush(*_args, **_kwargs) -> None:
            if client.put_calls:
                raise RuntimeError("database unavailable")
            original_flush(*_args, **_kwargs)

        monkeypatch.setattr(db, "flush", fail_flush)
        upload = _prepared_upload(b"orphan-guard")
        try:
            with pytest.raises(RuntimeError, match="database unavailable"):
                upload_vehicle_module_checklist_attachment(
                    db,
                    workspace=workspace,
                    user=user,
                    checklist=checklist,
                    record_id=record.id,
                    upload=upload,
                )
        finally:
            upload.content.close()
        assert len(client.put_calls) == 1
        assert client.put_calls[0][0] in client.remove_calls


def test_attachment_upload_database_and_compensation_failure_leaves_stale_orphan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, user, checklist, record = _checklist_scope(db)
        original_flush = db.flush

        def fail_flush(*_args, **_kwargs) -> None:
            if client.put_calls:
                client.remove_failures[client.put_calls[0][0]] = 1
                raise RuntimeError("database unavailable")
            original_flush(*_args, **_kwargs)

        monkeypatch.setattr(db, "flush", fail_flush)
        upload = _prepared_upload(b"periodic-orphan-guard")
        try:
            with pytest.raises(RuntimeError, match="database unavailable"):
                upload_vehicle_module_checklist_attachment(
                    db,
                    workspace=workspace,
                    user=user,
                    checklist=checklist,
                    record_id=record.id,
                    upload=upload,
                )
        finally:
            upload.content.close()

        storage_key = client.put_calls[0][0]
        monkeypatch.setattr(db, "flush", original_flush)
        db.rollback()
        assert storage_key in client.objects
        assert storage_key in client.remove_calls
        assert (
            db.scalar(
                select(LegacyIssueVehicleModuleChecklistAttachment.id).where(
                    LegacyIssueVehicleModuleChecklistAttachment.storage_key == storage_key
                )
            )
            is None
        )


def test_attachment_upload_commit_failure_rolls_back_and_removes_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_do_api.domains.legacy_issues import router as legacy_router

    upload = _prepared_upload(b"commit-orphan-guard")
    row = SimpleNamespace(storage_key="checklists/orphan-guard", id="attachment-1")
    events: list[str] = []

    class FailingDb:
        def commit(self) -> None:
            events.append("commit")
            raise RuntimeError("commit failed")

        def rollback(self) -> None:
            events.append("rollback")

    async def prepared_upload(_file):
        return upload

    monkeypatch.setattr(
        legacy_router,
        "read_vehicle_module_checklist_attachment_upload",
        prepared_upload,
    )
    monkeypatch.setattr(
        legacy_router,
        "get_vehicle_module_checklist",
        lambda *_args, **_kwargs: SimpleNamespace(id="checklist-1"),
    )
    monkeypatch.setattr(
        legacy_router,
        "upload_vehicle_module_checklist_attachment",
        lambda *_args, **_kwargs: row,
    )
    monkeypatch.setattr(
        legacy_router,
        "remove_uploaded_vehicle_module_checklist_attachment",
        lambda storage_key: events.append(f"remove:{storage_key}"),
    )
    monkeypatch.setattr(legacy_router, "_enabled_module_keys", lambda: frozenset({"aircon"}))

    with pytest.raises(RuntimeError, match="commit failed"):
        asyncio.run(
            legacy_router.upload_legacy_issue_vehicle_module_checklist_attachment(
                "checklist-1",
                "record-1",
                file=SimpleNamespace(),
                db=FailingDb(),
                current_user=SimpleNamespace(id="user-1"),
                current_workspace=SimpleNamespace(id="workspace-1"),
            )
        )

    assert events == ["commit", "rollback", "remove:checklists/orphan-guard"]
    assert upload.content.closed is True


def _other_checklist(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
) -> LegacyIssueVehicleModuleChecklist:
    now = utcnow_naive()
    vehicle = LegacyIssueVehicleModel(
        id="vehicle-2",
        workspace_id=workspace.id,
        vehicle_code="CAR-2",
        vehicle_code_normalized="car-2",
        active=True,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    stage = LegacyIssueVehicleStage(
        id="stage-2",
        workspace_id=workspace.id,
        vehicle_model_id=vehicle.id,
        name="P0",
        name_normalized="p0",
        sequence_no=1,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    checklist = LegacyIssueVehicleModuleChecklist(
        id="checklist-2",
        workspace_id=workspace.id,
        vehicle_model_id=vehicle.id,
        vehicle_stage_id=stage.id,
        module_key="aircon",
        status="draft",
        source_dataset_key="common-master",
        source_master_revision_id="revision-1",
        source_master_revision_no=1,
        definition_snapshot={},
        row_count=0,
        created_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add_all([vehicle, stage, checklist])
    db.commit()
    return checklist


class _AsyncUploadFile:
    def __init__(
        self,
        *,
        chunks: list[bytes],
        filename: str | None,
        content_type: str | None,
    ) -> None:
        self.chunks = list(chunks)
        self.filename = filename
        self.content_type = content_type
        self.requested_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return self.chunks.pop(0) if self.chunks else b""


class _FakeStorageObject:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.closed = False
        self.released = False

    def stream(self, chunk_size: int) -> Iterator[bytes]:
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeStorageClient:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.put_calls: list[tuple[str, bytes, int, str]] = []
        self.remove_calls: list[str] = []
        self.remove_failures: dict[str, int] = {}

    def put_object(
        self,
        _bucket_name: str,
        object_name: str,
        data: BytesIO,
        *,
        length: int,
        content_type: str,
    ) -> None:
        content = data.read()
        assert len(content) == length
        self.objects[object_name] = content
        self.put_calls.append((object_name, content, length, content_type))

    def get_object(self, _bucket_name: str, object_name: str) -> _FakeStorageObject:
        return _FakeStorageObject(self.objects[object_name])

    def remove_object(self, _bucket_name: str, object_name: str) -> None:
        self.remove_calls.append(object_name)
        remaining_failures = self.remove_failures.get(object_name, 0)
        if remaining_failures:
            self.remove_failures[object_name] = remaining_failures - 1
            raise RuntimeError("storage unavailable")
        self.objects.pop(object_name, None)
