from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_alm_api.domains.spec_compare import service
from open_alm_api.domains.spec_compare.artifacts import (
    SpecCompareArtifactRef,
    SpecCompareInputArtifacts,
)
from open_alm_api.domains.spec_compare.models import SpecCompareJob


class FakeDb:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0

    def add(self, row: object) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, row: object) -> None:
        raise AssertionError("dispatch failure should not refresh the job")


def test_create_job_marks_row_failed_when_dispatch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeArtifactStore:
        def upload_inputs(self, **_kwargs) -> SpecCompareInputArtifacts:
            return SpecCompareInputArtifacts(
                base=SpecCompareArtifactRef(
                    filename="base.pptx",
                    mime_type="application/pptx",
                    size_bytes=10,
                    storage_key="base-key",
                ),
                target=SpecCompareArtifactRef(
                    filename="target.pptx",
                    mime_type="application/pptx",
                    size_bytes=12,
                    storage_key="target-key",
                ),
            )

    class FailingDispatcher:
        def dispatch(self, _job_id: str) -> str | None:
            raise RuntimeError("broker unavailable")

    monkeypatch.setattr(service, "_new_id", lambda: "job-1")
    monkeypatch.setattr(service, "spec_compare_artifact_store", lambda: FakeArtifactStore())
    monkeypatch.setattr(service, "spec_compare_job_dispatcher", lambda: FailingDispatcher())
    db = FakeDb()

    with pytest.raises(HTTPException) as exc_info:
        service.create_job(
            db,  # type: ignore[arg-type]
            workspace=SimpleNamespace(id="workspace-1"),
            user=SimpleNamespace(id="user-1"),
            title="Compare",
            base_filename="base.pptx",
            base_mime_type="application/pptx",
            base_content=b"base bytes",
            target_filename="target.pptx",
            target_mime_type="application/pptx",
            target_content=b"target bytes",
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail.code == "spec_compare.dispatch_failed"
    assert db.commit_count == 2
    row = next(item for item in db.added if isinstance(item, SpecCompareJob))
    assert row.id == "job-1"
    assert row.status == "failed"
    assert row.progress == 100
    assert row.failure_reason == "Dispatch failed"


def _stored_job() -> SpecCompareJob:
    return SpecCompareJob(
        id="job-1",
        workspace_id="workspace-1",
        owner_id="user-1",
        title="비교",
        status="succeeded",
        progress=100,
        status_message="succeeded",
        base_file_name="base.pptx",
        base_mime_type="application/pptx",
        base_size_bytes=1,
        base_storage_key="base-key",
        target_file_name="target.pdf",
        target_mime_type="application/pdf",
        target_size_bytes=1,
        target_storage_key="target-key",
        result_json_storage_key="result-key",
        report_markdown_storage_key="markdown-key",
    )


class FakeDeleteDb:
    def __init__(self, row: SpecCompareJob | None) -> None:
        self.row = row
        self.executed: list[object] = []
        self.deleted: list[object] = []
        self.commit_count = 0

    def get(self, _model: type, _job_id: str) -> SpecCompareJob | None:
        return self.row

    def execute(self, statement: object) -> None:
        self.executed.append(statement)

    def delete(self, row: object) -> None:
        self.deleted.append(row)

    def commit(self) -> None:
        self.commit_count += 1


def test_delete_job_removes_row_spec_items_and_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    removed_keys: list[str | None] = []

    class FakeStore:
        def remove_job_artifacts(self, *, storage_keys: list[str | None]) -> None:
            removed_keys.extend(storage_keys)

    monkeypatch.setattr(service, "spec_compare_artifact_store", lambda: FakeStore())
    row = _stored_job()
    db = FakeDeleteDb(row)

    service.delete_job(
        db,  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        job_id="job-1",
    )

    assert db.deleted == [row]
    assert len(db.executed) == 1  # spec-item cleanup delete()
    assert db.commit_count == 1
    assert removed_keys == ["base-key", "target-key", "result-key", "markdown-key"]


def test_delete_job_survives_artifact_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingStore:
        def remove_job_artifacts(self, **_kwargs) -> None:
            raise RuntimeError("minio unavailable")

    monkeypatch.setattr(service, "spec_compare_artifact_store", lambda: FailingStore())
    db = FakeDeleteDb(_stored_job())

    # The DB row is already gone; storage cleanup is best-effort and must not 500.
    service.delete_job(
        db,  # type: ignore[arg-type]
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        job_id="job-1",
    )

    assert db.commit_count == 1


def test_delete_job_enforces_workspace_and_owner() -> None:
    db = FakeDeleteDb(_stored_job())

    with pytest.raises(HTTPException) as other_workspace:
        service.delete_job(
            db,  # type: ignore[arg-type]
            workspace=SimpleNamespace(id="workspace-2"),
            user=SimpleNamespace(id="user-1"),
            job_id="job-1",
        )
    assert other_workspace.value.status_code == 404

    with pytest.raises(HTTPException) as other_user:
        service.delete_job(
            db,  # type: ignore[arg-type]
            workspace=SimpleNamespace(id="workspace-1"),
            user=SimpleNamespace(id="user-2"),
            job_id="job-1",
        )
    assert other_user.value.status_code == 403
    assert db.deleted == []
    assert db.commit_count == 0


def test_mark_failed_rolls_back_before_committing_failure_state() -> None:
    row = SimpleNamespace(
        status="running",
        progress=45,
        status_message="comparing",
        failure_reason=None,
        celery_task_id="task-1",
        updated_at=None,
    )

    class FakeSession:
        def __init__(self) -> None:
            self.events: list[str] = []

        def rollback(self) -> None:
            self.events.append("rollback")

        def add(self, value) -> None:
            self.events.append("add")
            assert value is row

        def commit(self) -> None:
            self.events.append("commit")

    db = FakeSession()

    service.mark_failed(db, row, "comparison failed")  # type: ignore[arg-type]

    assert db.events == ["rollback", "add", "commit"]
    assert row.status == "failed"
    assert row.progress == 100
    assert row.status_message == "failed"
    assert row.failure_reason == "comparison failed"
    assert row.celery_task_id is None
