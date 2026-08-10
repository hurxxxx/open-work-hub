from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import datetime
from tempfile import SpooledTemporaryFile

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import AuditLog, OrgUnit, User, Workspace, utcnow_naive
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRevisionMeetingAttachment,
    LegacyIssueRevisionMeetingAttachmentCleanup,
    LegacyIssueRevisionOverviewHistory,
)
from open_alm_api.domains.legacy_issues.revision_meeting_attachments import (
    RevisionMeetingAttachmentStorage,
    RevisionMeetingAttachmentUpload,
    can_delete_revision_meeting_attachment,
    can_edit_revision_meeting_attachment,
    delete_revision_meeting_attachment,
    find_existing_revision_meeting_attachment_upload,
    get_revision_meeting_attachment,
    list_revision_meeting_attachments,
    open_revision_meeting_attachment,
    process_pending_revision_meeting_attachment_cleanups,
    read_revision_meeting_attachment_upload,
    update_revision_meeting_attachment_description,
    upload_revision_meeting_attachment,
)
from open_alm_api.domains.legacy_issues.revisioning import (
    ensure_initial_published_revision,
    ensure_published_revision_overview_history,
)


DATASET_KEY = "legacy_issue.common-master.aircon"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            OrgUnit.__table__,
            Workspace.__table__,
            User.__table__,
            AuditLog.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueRevisionOverviewHistory.__table__,
            LegacyIssueRevisionMeetingAttachment.__table__,
            LegacyIssueRevisionMeetingAttachmentCleanup.__table__,
        ],
    )
    return Session(engine)


def _user(user_id: str, *, admin: bool = False) -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@example.com",
        full_name=f"Name {user_id}",
        password_hash="hash",
        status="active",
        is_admin=admin,
    )


def _scope(
    db: Session,
) -> tuple[Workspace, User, User, User, LegacyIssueRevisionOverviewHistory]:
    now = utcnow_naive()
    workspace = Workspace(id="workspace-1", key="workspace-1", name="Workspace 1")
    uploader = _user("uploader")
    other = _user("other")
    admin = _user("admin", admin=True)
    revision = LegacyIssueDataRevision(
        id="revision-1",
        workspace_id=workspace.id,
        dataset_key=DATASET_KEY,
        revision_no=1,
        status="published",
        created_at=now,
        updated_at=now,
        published_at=now,
    )
    history = LegacyIssueRevisionOverviewHistory(
        id="history-1",
        workspace_id=workspace.id,
        dataset_key=DATASET_KEY,
        linked_revision_id=revision.id,
        origin="system",
        revision_no=1,
        revision_label="1",
        sort_order=0,
        created_at=now,
        updated_at=now,
    )
    db.add_all([workspace, uploader, other, admin, revision, history])
    db.commit()
    return workspace, uploader, other, admin, history


def _upload(
    content: bytes,
    *,
    filename: str = "minutes.pdf",
    content_type: str = "application/pdf",
) -> RevisionMeetingAttachmentUpload:
    buffer: SpooledTemporaryFile[bytes] = SpooledTemporaryFile()
    buffer.write(content)
    buffer.seek(0)
    return RevisionMeetingAttachmentUpload(
        content=buffer,
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
    )


def _install_fake_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple["_FakeStorageClient", RevisionMeetingAttachmentStorage]:
    from open_alm_api.domains.legacy_issues import revision_meeting_attachments as service

    client = _FakeStorageClient()
    storage = RevisionMeetingAttachmentStorage(
        bucket_name="test-bucket",
        client=client,
    )
    monkeypatch.setattr(service, "revision_meeting_attachment_storage", lambda: storage)
    monkeypatch.setattr(service, "ensure_bucket", lambda: None)
    monkeypatch.setattr(
        service,
        "is_platform_admin_user",
        lambda user, _db: bool(user.is_admin),
    )
    return client, storage


def test_upload_reader_counts_chunks_normalizes_metadata_and_rejects_invalid_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import revision_meeting_attachments as service

    file = _AsyncUploadFile(
        chunks=[b"abc", b"def"],
        filename=r"C:\unsafe\meeting?.PDF",
        content_type="Application/PDF; charset=binary",
    )
    upload = asyncio.run(read_revision_meeting_attachment_upload(file))
    try:
        assert upload.content.read() == b"abcdef"
        assert upload.filename == "meeting_.PDF"
        assert upload.content_type == "application/pdf"
        assert upload.size_bytes == 6
        assert file.requested_sizes == [1024 * 1024, 1024 * 1024, 1024 * 1024]
    finally:
        upload.content.close()

    with pytest.raises(HTTPException) as empty:
        asyncio.run(
            read_revision_meeting_attachment_upload(
                _AsyncUploadFile(chunks=[], filename="empty.txt", content_type="text/plain")
            )
        )
    assert empty.value.status_code == 422
    assert empty.value.detail.code == "legacy_issues.revision_meeting_attachment_empty"

    monkeypatch.setattr(service, "REVISION_MEETING_ATTACHMENT_MAX_BYTES", 3)
    with pytest.raises(HTTPException) as oversized:
        asyncio.run(
            read_revision_meeting_attachment_upload(
                _AsyncUploadFile(chunks=[b"123", b"4"], filename="large.bin")
            )
        )
    assert oversized.value.status_code == 413
    assert oversized.value.detail.code == "legacy_issues.revision_meeting_attachment_too_large"


def test_attachment_lifecycle_permissions_scope_hidden_rows_and_cleanup_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, uploader, other, admin, history = _scope(db)
        prepared = _upload(b"meeting-result")
        try:
            row = upload_revision_meeting_attachment(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                history_id=history.id,
                user=uploader,
                upload=prepared,
                description="  first result  ",
                client_request_id="request-1",
            ).attachment
            db.commit()
        finally:
            prepared.content.close()

        assert row.description == "first result"
        assert row.client_request_id == "request-1"
        replay_upload = _upload(b"retry-with-different-content")
        try:
            replay = upload_revision_meeting_attachment(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                history_id=history.id,
                user=uploader,
                upload=replay_upload,
                description="retry description is ignored",
                client_request_id="request-1",
            )
            db.commit()
        finally:
            replay_upload.content.close()
        assert replay.created is False
        assert replay.attachment.id == row.id
        assert replay.attachment.description == "first result"
        assert len(client.put_calls) == 1
        assert list_revision_meeting_attachments(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
        ) == [row]
        assert can_edit_revision_meeting_attachment(db, user=uploader, attachment=row)
        assert not can_edit_revision_meeting_attachment(db, user=other, attachment=row)
        assert can_delete_revision_meeting_attachment(db, user=admin)
        assert not can_delete_revision_meeting_attachment(db, user=uploader)

        content = open_revision_meeting_attachment(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
            attachment_id=row.id,
        )
        assert content.media_type == "application/octet-stream"
        assert content.headers["Cache-Control"] == "no-store"
        assert content.headers["X-Content-Type-Options"] == "nosniff"
        assert content.headers["Content-Disposition"].startswith("attachment;")
        assert b"".join(content.body) == b"meeting-result"

        with pytest.raises(HTTPException) as forbidden_edit:
            update_revision_meeting_attachment_description(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                attachment_id=row.id,
                user=other,
                description="not allowed",
            )
        assert forbidden_edit.value.status_code == 403
        assert (
            forbidden_edit.value.detail.code
            == "legacy_issues.revision_meeting_attachment_edit_forbidden"
        )

        updated = update_revision_meeting_attachment_description(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
            attachment_id=row.id,
            user=uploader,
            description=" updated result ",
        )
        db.commit()
        assert updated.description == "updated result"

        with pytest.raises(HTTPException) as member_delete:
            delete_revision_meeting_attachment(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                attachment_id=row.id,
                user=uploader,
            )
        assert member_delete.value.status_code == 403
        assert member_delete.value.detail.code == "admin.platform_admin_required"

        other_workspace = Workspace(id="workspace-2", key="workspace-2", name="Workspace 2")
        db.add(other_workspace)
        db.commit()
        with pytest.raises(HTTPException) as cross_workspace:
            get_revision_meeting_attachment(
                db,
                workspace=other_workspace,
                dataset_key=DATASET_KEY,
                attachment_id=row.id,
            )
        assert cross_workspace.value.status_code == 404
        with pytest.raises(HTTPException) as cross_workspace_replay:
            find_existing_revision_meeting_attachment_upload(
                db,
                workspace=other_workspace,
                dataset_key=DATASET_KEY,
                history_id=history.id,
                user=uploader,
                client_request_id="request-1",
            )
        assert cross_workspace_replay.value.status_code == 404

        history.deleted_at = datetime(2026, 8, 10)
        db.commit()
        assert (
            list_revision_meeting_attachments(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
            )
            == []
        )
        with pytest.raises(HTTPException) as hidden_download:
            open_revision_meeting_attachment(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                attachment_id=row.id,
            )
        assert hidden_download.value.status_code == 404
        with pytest.raises(HTTPException) as hidden_replay:
            find_existing_revision_meeting_attachment_upload(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                history_id=history.id,
                user=uploader,
                client_request_id="request-1",
            )
        assert hidden_replay.value.status_code == 404
        assert row.storage_key in client.objects

        history.deleted_at = None
        db.commit()
        storage_key = row.storage_key
        client.remove_failures[storage_key] = 1
        cleanup = delete_revision_meeting_attachment(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
            attachment_id=row.id,
            user=admin,
        )
        db.commit()
        assert db.get(LegacyIssueRevisionMeetingAttachment, row.id) is None
        assert db.get(LegacyIssueRevisionMeetingAttachmentCleanup, cleanup.id) is not None
        assert storage_key in client.objects

        assert process_pending_revision_meeting_attachment_cleanups(
            db,
            workspace=workspace,
        ) == (0, 1)
        pending = db.get(LegacyIssueRevisionMeetingAttachmentCleanup, cleanup.id)
        assert pending is not None
        assert pending.attempt_count == 1
        assert process_pending_revision_meeting_attachment_cleanups(
            db,
            workspace=workspace,
        ) == (1, 0)
        assert db.get(LegacyIssueRevisionMeetingAttachmentCleanup, cleanup.id) is None
        assert storage_key not in client.objects

        audit_actions = list(db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)))
        assert audit_actions == [
            "legacy_issues.revision_meeting_attachment.upload",
            "legacy_issues.revision_meeting_attachment.description_update",
            "legacy_issues.revision_meeting_attachment.delete",
        ]


def test_list_attachments_optionally_filters_and_validates_visible_history() -> None:
    with _session() as db:
        workspace, uploader, _other, _admin, history = _scope(db)
        now = utcnow_naive()
        second_history = LegacyIssueRevisionOverviewHistory(
            id="history-2",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            linked_revision_id=None,
            origin="manual",
            revision_no=None,
            revision_label="manual",
            sort_order=1,
            created_at=now,
            updated_at=now,
        )
        first_attachment = LegacyIssueRevisionMeetingAttachment(
            id="attachment-history-1",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            overview_history_id=history.id,
            filename="first.pdf",
            content_type="application/pdf",
            size_bytes=1,
            description=None,
            storage_key="revision-meeting/first",
            uploaded_by_id=uploader.id,
            client_request_id="list-first",
            created_at=now,
            updated_at=now,
        )
        second_attachment = LegacyIssueRevisionMeetingAttachment(
            id="attachment-history-2",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            overview_history_id=second_history.id,
            filename="second.pdf",
            content_type="application/pdf",
            size_bytes=1,
            description=None,
            storage_key="revision-meeting/second",
            uploaded_by_id=uploader.id,
            client_request_id="list-second",
            created_at=now,
            updated_at=now,
        )
        db.add_all([second_history, first_attachment, second_attachment])
        db.commit()

        all_rows = list_revision_meeting_attachments(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
        )
        assert {row.id for row in all_rows} == {
            first_attachment.id,
            second_attachment.id,
        }
        assert list_revision_meeting_attachments(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
            history_id=history.id,
        ) == [first_attachment]
        assert list_revision_meeting_attachments(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
            history_id=second_history.id,
        ) == [second_attachment]

        with pytest.raises(HTTPException) as missing:
            list_revision_meeting_attachments(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                history_id="missing-history",
            )
        assert missing.value.status_code == 404
        assert missing.value.detail.code == "legacy_issues.revision_not_found"

        other_workspace = Workspace(
            id="workspace-filter-other",
            key="workspace-filter-other",
            name="Other workspace",
        )
        db.add(other_workspace)
        db.commit()
        with pytest.raises(HTTPException) as cross_scope:
            list_revision_meeting_attachments(
                db,
                workspace=other_workspace,
                dataset_key=DATASET_KEY,
                history_id=history.id,
            )
        assert cross_scope.value.status_code == 404
        assert cross_scope.value.detail.code == "legacy_issues.revision_not_found"

        history.deleted_at = now
        db.commit()
        with pytest.raises(HTTPException) as hidden:
            list_revision_meeting_attachments(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                history_id=history.id,
            )
        assert hidden.value.status_code == 404
        assert hidden.value.detail.code == "legacy_issues.revision_not_found"
        assert list_revision_meeting_attachments(
            db,
            workspace=workspace,
            dataset_key=DATASET_KEY,
        ) == [second_attachment]


def test_upload_flush_failure_queues_cleanup_when_object_removal_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import revision_meeting_attachments as service

    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, uploader, _other, _admin, history = _scope(db)
        workspace_id = workspace.id
        independent_sessions = sessionmaker(bind=db.get_bind())
        monkeypatch.setattr(service, "get_session_factory", lambda: independent_sessions)
        client.fail_all_removes = True
        original_flush = db.flush

        def fail_flush(*_args, **_kwargs) -> None:
            if client.put_calls:
                raise RuntimeError("database unavailable")
            original_flush(*_args, **_kwargs)

        monkeypatch.setattr(db, "flush", fail_flush)
        prepared = _upload(b"compensate")
        try:
            with pytest.raises(RuntimeError, match="database unavailable"):
                upload_revision_meeting_attachment(
                    db,
                    workspace=workspace,
                    dataset_key=DATASET_KEY,
                    history_id=history.id,
                    user=uploader,
                    upload=prepared,
                    description=None,
                    client_request_id="flush-failure",
                )
        finally:
            prepared.content.close()
        assert len(client.put_calls) == 1
        storage_key = client.put_calls[0][0]
        assert storage_key in client.remove_calls
        assert storage_key in client.objects
        with independent_sessions() as verification_db:
            cleanup = verification_db.scalar(
                select(LegacyIssueRevisionMeetingAttachmentCleanup).where(
                    LegacyIssueRevisionMeetingAttachmentCleanup.storage_key == storage_key
                )
            )
        assert cleanup is not None
        assert cleanup.workspace_id == workspace_id


def test_upload_refresh_failure_rolls_back_and_compensates_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, uploader, _other, _admin, history = _scope(db)
        original_refresh = db.refresh

        def fail_attachment_refresh(instance, *args, **kwargs) -> None:
            if isinstance(instance, LegacyIssueRevisionMeetingAttachment):
                raise RuntimeError("post-flush refresh failed")
            original_refresh(instance, *args, **kwargs)

        monkeypatch.setattr(db, "refresh", fail_attachment_refresh)
        prepared = _upload(b"refresh compensation")
        try:
            with pytest.raises(RuntimeError, match="refresh failed"):
                upload_revision_meeting_attachment(
                    db,
                    workspace=workspace,
                    dataset_key=DATASET_KEY,
                    history_id=history.id,
                    user=uploader,
                    upload=prepared,
                    description=None,
                    client_request_id="refresh-failure",
                )
        finally:
            prepared.content.close()

        storage_key = client.put_calls[0][0]
        assert storage_key in client.remove_calls
        assert storage_key not in client.objects
        assert list(db.scalars(select(LegacyIssueRevisionMeetingAttachment))) == []
        assert list(db.scalars(select(AuditLog))) == []


def test_upload_idempotency_unique_conflict_compensates_losing_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import revision_meeting_attachments as service

    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, uploader, _other, _admin, history = _scope(db)
        independent_sessions = sessionmaker(bind=db.get_bind())
        monkeypatch.setattr(service, "get_session_factory", lambda: independent_sessions)
        client.fail_all_removes = True
        now = utcnow_naive()
        existing = LegacyIssueRevisionMeetingAttachment(
            id="attachment-winner",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            overview_history_id=history.id,
            filename="winner.pdf",
            content_type="application/pdf",
            size_bytes=6,
            description="winner",
            storage_key="revision-meeting/winner",
            uploaded_by_id=uploader.id,
            client_request_id="concurrent-request",
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
        db.commit()
        client.objects[existing.storage_key] = b"winner"

        original_find = service._find_idempotent_revision_meeting_attachment
        lookup_count = 0

        def miss_preflight_once(*args, **kwargs):
            nonlocal lookup_count
            lookup_count += 1
            if lookup_count == 1:
                return None
            return original_find(*args, **kwargs)

        monkeypatch.setattr(
            service,
            "_find_idempotent_revision_meeting_attachment",
            miss_preflight_once,
        )

        prepared = _upload(b"losing upload")
        try:
            result = upload_revision_meeting_attachment(
                db,
                workspace=workspace,
                dataset_key=DATASET_KEY,
                history_id=history.id,
                user=uploader,
                upload=prepared,
                description="loser",
                client_request_id="concurrent-request",
            )
            db.commit()
        finally:
            prepared.content.close()

        assert result.created is False
        assert result.attachment.id == existing.id
        assert len(client.put_calls) == 1
        losing_storage_key = client.put_calls[0][0]
        assert losing_storage_key in client.remove_calls
        assert losing_storage_key in client.objects
        assert client.objects[existing.storage_key] == b"winner"
        assert [row.id for row in db.scalars(select(LegacyIssueRevisionMeetingAttachment))] == [
            existing.id
        ]
        assert list(db.scalars(select(AuditLog.action))) == []
        cleanup = db.scalar(
            select(LegacyIssueRevisionMeetingAttachmentCleanup).where(
                LegacyIssueRevisionMeetingAttachmentCleanup.storage_key == losing_storage_key
            )
        )
        assert cleanup is not None
        assert cleanup.workspace_id == workspace.id


def test_router_contract_requires_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import router as legacy_router

    route_methods = {
        (route.path, method)
        for route in legacy_router.router.routes
        for method in (route.methods or set())
    }
    assert (
        "/legacy-issues/datasets/{dataset_key}/revisions/meeting-attachments",
        "GET",
    ) in route_methods
    assert (
        "/legacy-issues/datasets/{dataset_key}/revisions/overview-history/"
        "{history_id}/meeting-attachments",
        "POST",
    ) in route_methods
    assert (
        "/legacy-issues/datasets/{dataset_key}/revisions/meeting-attachments/{attachment_id}",
        "PATCH",
    ) in route_methods
    assert (
        "/legacy-issues/datasets/{dataset_key}/revisions/meeting-attachments/{attachment_id}/file",
        "GET",
    ) in route_methods
    assert (
        "/legacy-issues/datasets/{dataset_key}/revisions/meeting-attachments/{attachment_id}",
        "DELETE",
    ) in route_methods

    upload_route = next(
        route
        for route in legacy_router.router.routes
        if route.path.endswith("/revisions/overview-history/{history_id}/meeting-attachments")
    )
    upload_body_model = upload_route.body_field.field_info.annotation
    request_id_field = upload_body_model.model_fields["client_request_id"]
    assert request_id_field.is_required()
    assert any(getattr(metadata, "min_length", None) == 1 for metadata in request_id_field.metadata)
    assert any(
        getattr(metadata, "max_length", None) == 64 for metadata in request_id_field.metadata
    )

    captured: dict[str, str] = {}

    def resolve_revision(_db, *, workspace, dataset_key):
        captured["resolved_workspace_id"] = workspace.id
        captured["resolved_dataset_key"] = dataset_key

    def list_attachments(_db, *, workspace, dataset_key, history_id=None):
        captured["listed_workspace_id"] = workspace.id
        captured["listed_dataset_key"] = dataset_key
        captured["history_id"] = history_id
        return []

    monkeypatch.setattr(legacy_router, "resolve_read_revision", resolve_revision)
    monkeypatch.setattr(
        legacy_router,
        "list_revision_meeting_attachments",
        list_attachments,
    )
    monkeypatch.setattr(
        legacy_router,
        "can_delete_revision_meeting_attachment",
        lambda _db, *, user: bool(user.is_admin),
    )
    workspace = Workspace(
        id="router-workspace",
        key="router-workspace",
        name="Router workspace",
    )

    class RouterDb:
        @staticmethod
        def commit() -> None:
            return None

    response = legacy_router.list_legacy_issue_revision_meeting_attachments(
        "common-master",
        view_key="aircon",
        history_id="history / 1",
        db=RouterDb(),
        current_user=_user("router-user"),
        current_workspace=workspace,
    )
    assert response.items == []
    assert response.can_upload is True
    assert captured == {
        "resolved_workspace_id": workspace.id,
        "resolved_dataset_key": DATASET_KEY,
        "listed_workspace_id": workspace.id,
        "listed_dataset_key": DATASET_KEY,
        "history_id": "history / 1",
    }


def test_router_confirmed_precommit_failure_removes_unreferenced_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import revision_meeting_attachments as service
    from open_alm_api.domains.legacy_issues import router as legacy_router

    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, uploader, _other, _admin, history = _scope(db)
        independent_sessions = sessionmaker(bind=db.get_bind())
        monkeypatch.setattr(service, "get_session_factory", lambda: independent_sessions)
        prepared = _upload(b"confirmed precommit failure")

        async def prepared_upload(_file):
            return prepared

        monkeypatch.setattr(
            legacy_router,
            "read_revision_meeting_attachment_upload",
            prepared_upload,
        )

        def fail_before_commit() -> None:
            raise IntegrityError(
                "COMMIT",
                {},
                RuntimeError("precommit failure"),
            )

        monkeypatch.setattr(db, "commit", fail_before_commit)

        with pytest.raises(IntegrityError, match="precommit failure"):
            asyncio.run(
                legacy_router.upload_legacy_issue_revision_meeting_attachment(
                    "common-master",
                    history.id,
                    view_key="aircon",
                    file=object(),
                    description=None,
                    client_request_id="precommit-request",
                    db=db,
                    current_user=uploader,
                    current_workspace=workspace,
                )
            )

        storage_key = client.put_calls[0][0]
        assert storage_key in client.remove_calls
        assert storage_key not in client.objects
        assert prepared.content.closed is True
        with independent_sessions() as verification_db:
            assert (
                verification_db.scalar(
                    select(func.count()).select_from(LegacyIssueRevisionMeetingAttachment)
                )
                == 0
            )
            assert (
                verification_db.scalar(
                    select(func.count()).select_from(LegacyIssueRevisionMeetingAttachmentCleanup)
                )
                == 0
            )


def test_router_commit_ack_loss_preserves_committed_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import revision_meeting_attachments as service
    from open_alm_api.domains.legacy_issues import router as legacy_router

    client, _storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, uploader, _other, _admin, history = _scope(db)
        independent_sessions = sessionmaker(bind=db.get_bind())
        monkeypatch.setattr(service, "get_session_factory", lambda: independent_sessions)
        prepared = _upload(b"committed despite lost acknowledgement")

        async def prepared_upload(_file):
            return prepared

        monkeypatch.setattr(
            legacy_router,
            "read_revision_meeting_attachment_upload",
            prepared_upload,
        )
        original_commit = db.commit

        def commit_then_lose_ack() -> None:
            original_commit()
            raise RuntimeError("commit acknowledgement lost")

        monkeypatch.setattr(db, "commit", commit_then_lose_ack)

        with pytest.raises(RuntimeError, match="acknowledgement lost"):
            asyncio.run(
                legacy_router.upload_legacy_issue_revision_meeting_attachment(
                    "common-master",
                    history.id,
                    view_key="aircon",
                    file=object(),
                    description=None,
                    client_request_id="ack-loss-request",
                    db=db,
                    current_user=uploader,
                    current_workspace=workspace,
                )
            )

        storage_key = client.put_calls[0][0]
        assert client.remove_calls == []
        assert client.objects[storage_key] == b"committed despite lost acknowledgement"
        assert prepared.content.closed is True
        with independent_sessions() as verification_db:
            attachment = verification_db.scalar(
                select(LegacyIssueRevisionMeetingAttachment).where(
                    LegacyIssueRevisionMeetingAttachment.storage_key == storage_key
                )
            )
            assert attachment is not None
            assert attachment.client_request_id == "ack-loss-request"
            assert (
                verification_db.scalar(
                    select(func.count()).select_from(LegacyIssueRevisionMeetingAttachmentCleanup)
                )
                == 0
            )


def test_unresolved_dbapi_commit_failure_preserves_object_for_orphan_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import revision_meeting_attachments as service

    client, storage = _install_fake_storage(monkeypatch)
    with _session() as db:
        workspace, _uploader, _other, _admin, history = _scope(db)
        independent_sessions = sessionmaker(bind=db.get_bind())
        storage_key = "legacy-issues/revision-meeting-attachments/ws/history/unknown"
        client.objects[storage_key] = b"possibly committed"
        commit_error = OperationalError(
            "COMMIT",
            {},
            RuntimeError("connection lost"),
            connection_invalidated=True,
        )

        result = service.recover_revision_meeting_attachment_upload_commit(
            commit_error=commit_error,
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            history_id=history.id,
            attachment_id="unknown-attachment",
            storage_key=storage_key,
            session_factory=independent_sessions,
            storage=storage,
        )

        assert result == "unknown"
        assert client.remove_calls == []
        assert storage_key in client.objects
        with independent_sessions() as verification_db:
            assert (
                verification_db.scalar(
                    select(func.count()).select_from(LegacyIssueRevisionMeetingAttachmentCleanup)
                )
                == 0
            )


def test_ensure_published_overview_links_active_and_never_reexposes_hidden() -> None:
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace-1", name="Workspace")
        now = utcnow_naive()
        active_revision = LegacyIssueDataRevision(
            id="revision-active",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            revision_no=1,
            status="published",
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        hidden_revision = LegacyIssueDataRevision(
            id="revision-hidden",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            revision_no=2,
            status="published",
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        unlinked_hidden_revision = LegacyIssueDataRevision(
            id="revision-unlinked-hidden",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            revision_no=3,
            status="published",
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        occupied_number_revision = LegacyIssueDataRevision(
            id="revision-occupied-number-owner",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            revision_no=10,
            status="published",
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        fallback_revision = LegacyIssueDataRevision(
            id="revision-number-fallback",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            revision_no=4,
            status="published",
            created_at=now,
            updated_at=now,
            published_at=now,
        )
        active_history = LegacyIssueRevisionOverviewHistory(
            id="history-active",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            origin="manual",
            revision_no=1,
            revision_label="1",
            sort_order=0,
            created_at=now,
            updated_at=now,
        )
        hidden_history = LegacyIssueRevisionOverviewHistory(
            id="history-hidden",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            linked_revision_id=hidden_revision.id,
            origin="manual",
            revision_no=2,
            revision_label="2",
            sort_order=1,
            deleted_at=now,
            created_at=now,
            updated_at=now,
        )
        unlinked_hidden_history = LegacyIssueRevisionOverviewHistory(
            id="history-unlinked-hidden",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            origin="manual",
            revision_no=3,
            revision_label="3",
            sort_order=2,
            deleted_at=now,
            created_at=now,
            updated_at=now,
        )
        occupied_number_history = LegacyIssueRevisionOverviewHistory(
            id="history-occupied-number",
            workspace_id=workspace.id,
            dataset_key=DATASET_KEY,
            linked_revision_id=occupied_number_revision.id,
            origin="manual",
            revision_no=4,
            revision_label="4",
            sort_order=3,
            created_at=now,
            updated_at=now,
        )
        db.add_all(
            [
                workspace,
                active_revision,
                hidden_revision,
                unlinked_hidden_revision,
                occupied_number_revision,
                fallback_revision,
                active_history,
                hidden_history,
                unlinked_hidden_history,
                occupied_number_history,
            ]
        )
        db.commit()

        assert (
            ensure_published_revision_overview_history(
                db,
                workspace=workspace,
                revision=active_revision,
            ).id
            == active_history.id
        )
        assert active_history.linked_revision_id == active_revision.id
        assert (
            ensure_published_revision_overview_history(
                db,
                workspace=workspace,
                revision=hidden_revision,
            ).id
            == hidden_history.id
        )
        assert hidden_history.deleted_at is not None
        created_for_unlinked_hidden = ensure_published_revision_overview_history(
            db,
            workspace=workspace,
            revision=unlinked_hidden_revision,
        )
        assert created_for_unlinked_hidden.id != unlinked_hidden_history.id
        assert created_for_unlinked_hidden.origin == "system"
        assert created_for_unlinked_hidden.deleted_at is None
        assert created_for_unlinked_hidden.linked_revision_id == unlinked_hidden_revision.id
        fallback = ensure_published_revision_overview_history(
            db,
            workspace=workspace,
            revision=fallback_revision,
        )
        assert fallback.linked_revision_id == fallback_revision.id
        assert fallback.revision_no is None
        assert fallback.revision_label == "4"


def test_generic_and_internal_revision_reads_do_not_create_meeting_overview_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import revisioning

    monkeypatch.setattr(revisioning, "ensure_revision_partition", lambda *_args: "partition")
    with _session() as db:
        workspace = Workspace(id="workspace-1", key="workspace-1", name="Workspace")
        now = utcnow_naive()
        revisions = [
            LegacyIssueDataRevision(
                id="aggregate-revision",
                workspace_id=workspace.id,
                dataset_key="legacy_issue.common-master",
                revision_no=1,
                status="published",
                created_at=now,
                updated_at=now,
                published_at=now,
            ),
            LegacyIssueDataRevision(
                id="checklist-source-revision",
                workspace_id=workspace.id,
                dataset_key="legacy_issue.checklist-source.abc123",
                revision_no=1,
                status="published",
                created_at=now,
                updated_at=now,
                published_at=now,
            ),
        ]
        db.add_all([workspace, *revisions])
        db.commit()

        for revision in revisions:
            assert (
                ensure_initial_published_revision(
                    db,
                    workspace=workspace,
                    dataset_key=revision.dataset_key,
                ).id
                == revision.id
            )

        assert list(db.scalars(select(LegacyIssueRevisionOverviewHistory))) == []


class _AsyncUploadFile:
    def __init__(
        self,
        *,
        chunks: list[bytes],
        filename: str | None,
        content_type: str | None = None,
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
        self.put_calls: list[tuple[str, bytes, str]] = []
        self.remove_calls: list[str] = []
        self.remove_failures: dict[str, int] = {}
        self.fail_all_removes = False

    def put_object(
        self,
        _bucket_name: str,
        object_name: str,
        data,
        *,
        length: int,
        content_type: str,
    ) -> None:
        content = data.read(length)
        self.objects[object_name] = content
        self.put_calls.append((object_name, content, content_type))

    def get_object(self, _bucket_name: str, object_name: str) -> _FakeStorageObject:
        if object_name not in self.objects:
            raise KeyError(object_name)
        return _FakeStorageObject(self.objects[object_name])

    def remove_object(self, _bucket_name: str, object_name: str) -> None:
        self.remove_calls.append(object_name)
        if self.fail_all_removes:
            raise RuntimeError("persistent storage failure")
        failures = self.remove_failures.get(object_name, 0)
        if failures:
            self.remove_failures[object_name] = failures - 1
            raise RuntimeError("temporary storage failure")
        self.objects.pop(object_name, None)
