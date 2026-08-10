# ruff: noqa: E402

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
API_SRC = WORKSPACE_ROOT / "apps" / "api" / "src"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

from open_alm_api.core.db import Base
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueRevisionMeetingAttachment,
    LegacyIssueRevisionMeetingAttachmentCleanup,
    LegacyIssueVehicleModuleChecklistAttachmentCleanup,
)


ATTACHMENT_PREFIX = "legacy-issues/vehicle-module-checklists/"


class _FakeMinioClient:
    def __init__(
        self,
        *,
        objects: dict[str, datetime] | None = None,
        fail_once: set[str] | None = None,
    ) -> None:
        self.objects = dict(objects or {})
        self.fail_once = set(fail_once or set())
        self.list_calls: list[tuple[str, str, bool]] = []
        self.remove_calls: list[tuple[str, str]] = []

    def list_objects(self, bucket_name: str, *, prefix: str, recursive: bool):
        self.list_calls.append((bucket_name, prefix, recursive))
        return (
            SimpleNamespace(object_name=storage_key, last_modified=last_modified)
            for storage_key, last_modified in list(self.objects.items())
            if storage_key.startswith(prefix)
        )

    def remove_object(self, bucket_name: str, storage_key: str) -> None:
        self.remove_calls.append((bucket_name, storage_key))
        if storage_key in self.fail_once:
            self.fail_once.remove(storage_key)
            raise RuntimeError("temporary MinIO failure")
        self.objects.pop(storage_key, None)


class _ReferencedStorageKeySession:
    def __init__(self, storage_keys: set[str]) -> None:
        self.storage_keys = storage_keys
        self.scalar_queries = 0

    def scalars(self, _statement):
        self.scalar_queries += 1
        return iter(self.storage_keys)


class _ModelReferencedStorageKeySession:
    def __init__(self, storage_keys_by_model: dict[object, set[str]]) -> None:
        self.storage_keys_by_model = storage_keys_by_model

    def scalars(self, statement):
        entity = statement.column_descriptions[0].get("entity")
        return iter(self.storage_keys_by_model.get(entity, set()))


def _load_tasks(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPEN_ALM_WORKER_QUEUE_GROUP", "default")
    from open_alm_worker.settings import get_settings

    get_settings.cache_clear()
    return importlib.import_module("open_alm_worker.tasks.legacy_issue_attachment_index")


def test_cleanup_task_drains_more_than_100_rows_and_retries_failure_next_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LegacyIssueVehicleModuleChecklistAttachmentCleanup.__table__,
            LegacyIssueRevisionMeetingAttachmentCleanup.__table__,
        ],
    )
    storage_keys = [f"{ATTACHMENT_PREFIX}ws/checklist/attachment-{index}" for index in range(101)]
    failed_storage_key = storage_keys[-1]
    with Session(engine) as session:
        session.add_all(
            LegacyIssueVehicleModuleChecklistAttachmentCleanup(
                id=f"cleanup-{index}",
                workspace_id="workspace-1",
                storage_key=storage_key,
                created_at=datetime(2026, 7, 15, tzinfo=UTC).replace(tzinfo=None),
            )
            for index, storage_key in enumerate(storage_keys)
        )
        session.commit()

    client = _FakeMinioClient(
        objects={storage_key: datetime(2026, 7, 14, tzinfo=UTC) for storage_key in storage_keys},
        fail_once={failed_storage_key},
    )
    monkeypatch.setattr(tasks, "_db_session", lambda: Session(engine))
    monkeypatch.setattr(tasks, "_minio_client", lambda: client)

    assert tasks.cleanup_vehicle_module_checklist_attachment_objects.run() == {
        "deleted": 100,
        "failed": 1,
    }
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(LegacyIssueVehicleModuleChecklistAttachmentCleanup)
            )
            == 1
        )

    assert tasks.cleanup_vehicle_module_checklist_attachment_objects.run() == {
        "deleted": 1,
        "failed": 0,
    }
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(LegacyIssueVehicleModuleChecklistAttachmentCleanup)
            )
            == 0
        )
    assert (
        sum(storage_key == failed_storage_key for _bucket_name, storage_key in client.remove_calls)
        == 2
    )


def test_cleanup_task_also_drains_revision_meeting_attachment_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            LegacyIssueVehicleModuleChecklistAttachmentCleanup.__table__,
            LegacyIssueRevisionMeetingAttachmentCleanup.__table__,
        ],
    )
    storage_key = "legacy-issues/revision-meeting-attachments/ws/history/attachment"
    with Session(engine) as session:
        session.add(
            LegacyIssueRevisionMeetingAttachmentCleanup(
                id="meeting-cleanup-1",
                workspace_id="workspace-1",
                storage_key=storage_key,
                created_at=datetime(2026, 8, 10, tzinfo=UTC).replace(tzinfo=None),
            )
        )
        session.commit()

    client = _FakeMinioClient(
        objects={storage_key: datetime(2026, 8, 9, tzinfo=UTC)},
    )
    monkeypatch.setattr(tasks, "_db_session", lambda: Session(engine))
    monkeypatch.setattr(tasks, "_minio_client", lambda: client)

    assert tasks.cleanup_vehicle_module_checklist_attachment_objects.run() == {
        "deleted": 1,
        "failed": 0,
    }
    with Session(engine) as session:
        assert session.get(LegacyIssueRevisionMeetingAttachmentCleanup, "meeting-cleanup-1") is None
    assert storage_key not in client.objects


def test_orphan_reconciliation_applies_grace_preserves_references_and_retries_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    recent_key = f"{ATTACHMENT_PREFIX}ws/checklist/recent"
    referenced_key = f"{ATTACHMENT_PREFIX}ws/checklist/referenced"
    orphan_key = f"{ATTACHMENT_PREFIX}ws/checklist/orphan"
    retry_key = f"{ATTACHMENT_PREFIX}ws/checklist/retry"
    session = _ReferencedStorageKeySession({referenced_key})
    client = _FakeMinioClient(
        objects={
            recent_key: now - timedelta(minutes=59),
            referenced_key: now - timedelta(hours=2),
            orphan_key: now - timedelta(hours=2),
            retry_key: now - timedelta(hours=2),
        },
        fail_once={retry_key},
    )

    first_result = tasks._reconcile_vehicle_module_checklist_attachment_orphans(
        session,
        client=client,
        bucket_name="attachments",
        now=now,
        delete_limit=100,
    )

    assert first_result == {"scanned": 4, "eligible": 3, "deleted": 1, "failed": 1}
    assert recent_key in client.objects
    assert referenced_key in client.objects
    assert orphan_key not in client.objects
    assert retry_key in client.objects
    assert client.list_calls == [("attachments", ATTACHMENT_PREFIX, True)]
    assert session.scalar_queries == 1

    second_result = tasks._reconcile_vehicle_module_checklist_attachment_orphans(
        session,
        client=client,
        bucket_name="attachments",
        now=now + timedelta(hours=1),
        delete_limit=100,
    )

    assert second_result == {"scanned": 3, "eligible": 3, "deleted": 2, "failed": 0}
    assert referenced_key in client.objects
    assert recent_key not in client.objects
    assert retry_key not in client.objects
    assert client.remove_calls.count(("attachments", retry_key)) == 2


def test_orphan_reconciliation_scopes_meeting_prefix_and_preserves_references_with_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    now = datetime(2026, 8, 10, 12, tzinfo=UTC)
    recent_key = f"{tasks.REVISION_MEETING_ATTACHMENT_PREFIX}ws/history/recent"
    referenced_key = f"{tasks.REVISION_MEETING_ATTACHMENT_PREFIX}ws/history/referenced"
    orphan_key = f"{tasks.REVISION_MEETING_ATTACHMENT_PREFIX}ws/history/orphan"
    unrelated_key = "legacy-issues/revision-notes/ws/history/unrelated"
    session = _ModelReferencedStorageKeySession(
        {LegacyIssueRevisionMeetingAttachment: {referenced_key}}
    )
    client = _FakeMinioClient(
        objects={
            recent_key: now - timedelta(minutes=59),
            referenced_key: now - timedelta(hours=2),
            orphan_key: now - timedelta(hours=2),
            unrelated_key: now - timedelta(hours=2),
        }
    )

    result = tasks._reconcile_legacy_issue_attachment_orphans(
        session,
        client=client,
        bucket_name="attachments",
        now=now,
        delete_limit=100,
    )

    assert result == {"scanned": 3, "eligible": 2, "deleted": 1, "failed": 0}
    assert recent_key in client.objects
    assert referenced_key in client.objects
    assert orphan_key not in client.objects
    assert unrelated_key in client.objects
    assert client.list_calls == [
        ("attachments", tasks.VEHICLE_MODULE_CHECKLIST_ATTACHMENT_PREFIX, True),
        ("attachments", tasks.REVISION_MEETING_ATTACHMENT_PREFIX, True),
    ]


def test_orphan_reconciliation_scans_past_large_referenced_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks = _load_tasks(monkeypatch)
    now = datetime(2026, 7, 15, 12, tzinfo=UTC)
    referenced_keys = {
        f"{ATTACHMENT_PREFIX}ws/checklist/referenced-{index:04d}" for index in range(1001)
    }
    orphan_key = f"{ATTACHMENT_PREFIX}ws/checklist/zzzz-orphan"
    client = _FakeMinioClient(
        objects={
            **{storage_key: now - timedelta(hours=2) for storage_key in sorted(referenced_keys)},
            orphan_key: now - timedelta(hours=2),
        }
    )
    session = _ReferencedStorageKeySession(referenced_keys)

    result = tasks._reconcile_vehicle_module_checklist_attachment_orphans(
        session,
        client=client,
        bucket_name="attachments",
        now=now,
        delete_limit=100,
    )

    assert result == {
        "scanned": 1002,
        "eligible": 1002,
        "deleted": 1,
        "failed": 0,
    }
    assert orphan_key not in client.objects
    assert referenced_keys <= client.objects.keys()
    assert session.scalar_queries == 3
