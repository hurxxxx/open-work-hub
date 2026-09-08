# ruff: noqa: E402

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.files.models import FileManagerStorageCleanupJob


class _MissingObjectError(RuntimeError):
    code = "NoSuchKey"


class _FakeMinioClient:
    def __init__(self, *, failures: list[Exception] | None = None) -> None:
        self.failures = list(failures or [])
        self.calls: list[tuple[str, str]] = []

    def remove_object(self, bucket_name: str, storage_key: str) -> None:
        self.calls.append((bucket_name, storage_key))
        if self.failures:
            raise self.failures.pop(0)


def _load_tasks(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPEN_WORK_HUB_WORKER_QUEUE_GROUP", "default")
    from open_work_hub_worker.settings import get_settings

    get_settings.cache_clear()
    return importlib.import_module("open_work_hub_worker.tasks.file_storage_cleanup")


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[FileManagerStorageCleanupJob.__table__])
    return engine


def _add_job(
    engine,
    *,
    job_id: str = "cleanup-job-1",
    storage_key: str = "files/recording-fixture/private-object.txt",
    attempts: int = 1,
    next_retry_at: datetime | None = None,
) -> None:
    now = datetime(2026, 7, 29, 12, tzinfo=UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            FileManagerStorageCleanupJob(
                id=job_id,
                storage_key=storage_key,
                status="pending",
                attempts=attempts,
                created_at=now,
                updated_at=now,
                next_retry_at=next_retry_at or now,
            )
        )
        session.commit()


def _configure_task_dependencies(monkeypatch, tasks, *, engine, client) -> None:
    monkeypatch.setattr(tasks, "_db_session", lambda: Session(engine))
    monkeypatch.setattr(tasks, "_minio_client", lambda: client)
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(minio_bucket="files"))


def test_cleanup_failure_is_durably_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tasks = _load_tasks(monkeypatch)
    engine = _engine()
    storage_key = "files/recording-fixture/do-not-log-this-key.txt"
    _add_job(engine, storage_key=storage_key)
    client = _FakeMinioClient(failures=[RuntimeError(f"failed to delete {storage_key}")])
    _configure_task_dependencies(monkeypatch, tasks, engine=engine, client=client)

    assert tasks.cleanup_file_storage_object.run("cleanup-job-1") == "retry_scheduled"
    with Session(engine) as session:
        job = session.get(FileManagerStorageCleanupJob, "cleanup-job-1")
        assert job is not None
        assert job.status == "pending"
        assert job.attempts == 2
        assert job.last_error == "minio_delete:RuntimeError"
        assert job.next_retry_at is not None
        job.next_retry_at = datetime(2026, 7, 29, 11, tzinfo=UTC).replace(tzinfo=None)
        session.add(job)
        session.commit()

    assert tasks.cleanup_file_storage_object.run("cleanup-job-1") == "succeeded"
    with Session(engine) as session:
        job = session.get(FileManagerStorageCleanupJob, "cleanup-job-1")
        assert job is not None
        assert job.status == "succeeded"
        assert job.attempts == 3
        assert job.last_error is None
        assert job.next_retry_at is None

    assert client.calls == [("files", storage_key), ("files", storage_key)]
    assert storage_key not in caplog.text


def test_cleanup_treats_already_deleted_object_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    engine = _engine()
    _add_job(engine)
    client = _FakeMinioClient(failures=[_MissingObjectError("object is already absent")])
    _configure_task_dependencies(monkeypatch, tasks, engine=engine, client=client)

    assert tasks.cleanup_file_storage_object.run("cleanup-job-1") == "succeeded"
    with Session(engine) as session:
        job = session.get(FileManagerStorageCleanupJob, "cleanup-job-1")
        assert job is not None
        assert job.status == "succeeded"
        assert job.next_retry_at is None


def test_cleanup_dead_letters_after_bounded_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    engine = _engine()
    _add_job(engine, attempts=tasks.MAX_ATTEMPTS - 1)
    client = _FakeMinioClient(failures=[RuntimeError("MinIO unavailable")])
    _configure_task_dependencies(monkeypatch, tasks, engine=engine, client=client)

    assert tasks.cleanup_file_storage_object.run("cleanup-job-1") == "dead_letter"
    with Session(engine) as session:
        job = session.get(FileManagerStorageCleanupJob, "cleanup-job-1")
        assert job is not None
        assert job.status == "failed"
        assert job.attempts == tasks.MAX_ATTEMPTS
        assert job.last_error == "dead_letter:minio_delete:RuntimeError"
        assert job.next_retry_at is None


def test_republisher_includes_expired_leases_and_skips_live_leases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    engine = _engine()
    now = datetime(2026, 7, 29, 12, tzinfo=UTC).replace(tzinfo=None)
    _add_job(engine, job_id="expired", next_retry_at=now - timedelta(seconds=1))
    _add_job(engine, job_id="leased", next_retry_at=now + timedelta(seconds=1))
    published: list[str] = []
    monkeypatch.setattr(tasks, "_db_session", lambda: Session(engine))
    monkeypatch.setattr(tasks, "_utcnow", lambda: now)
    monkeypatch.setattr(tasks, "_publish_cleanup_job", published.append)

    assert tasks.republish_file_storage_cleanup_jobs.run() == 1
    assert published == ["expired"]
