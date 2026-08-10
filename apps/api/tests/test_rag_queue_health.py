from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.rag import queue_health
from open_alm_api.domains.rag.contracts import RagJobStatus, RagSyncLane, RagSyncOperation
from open_alm_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            RagSyncJob.__table__,
            RagVisibilityRecomputeJob.__table__,
        ],
    )
    return engine


def test_rag_queue_health_reports_stale_and_overdue_lanes(monkeypatch) -> None:
    engine = _engine()
    now = datetime.now(UTC).replace(tzinfo=None)
    with Session(engine) as session:
        session.add(
            Workspace(
                id="ws-1",
                key="ws-1",
                name="Workspace 1",
                description="",
                active=True,
            )
        )
        session.add_all(
            [
                RagSyncJob(
                    id="realtime-overdue",
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-overdue",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.REALTIME.value,
                    status=RagJobStatus.PENDING.value,
                    attempts=0,
                    created_at=now - timedelta(hours=2),
                    updated_at=now - timedelta(hours=2),
                ),
                RagSyncJob(
                    id="backfill-stale",
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-stale",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.BACKFILL.value,
                    status=RagJobStatus.PROCESSING.value,
                    attempts=1,
                    created_at=now - timedelta(hours=2),
                    updated_at=now - timedelta(hours=1),
                ),
                RagSyncJob(
                    id="realtime-succeeded",
                    workspace_id="ws-1",
                    resource_type="doc",
                    resource_id="doc-succeeded",
                    operation=RagSyncOperation.UPSERT.value,
                    lane=RagSyncLane.REALTIME.value,
                    status=RagJobStatus.SUCCEEDED.value,
                    attempts=1,
                    created_at=now - timedelta(minutes=30),
                    updated_at=now - timedelta(minutes=20),
                ),
                RagVisibilityRecomputeJob(
                    id="visibility-delayed-retry",
                    workspace_id="ws-1",
                    scope_type="workspace_membership",
                    scope_id="binding-1",
                    status=RagJobStatus.PENDING.value,
                    attempts=1,
                    next_retry_at=now + timedelta(hours=1),
                    created_at=now - timedelta(hours=2),
                    updated_at=now,
                ),
            ]
        )
        session.commit()

        recorded: list[dict[str, object]] = []
        monkeypatch.setattr(
            queue_health,
            "record_sync_queue_health",
            lambda **values: recorded.append(values),
        )
        health = queue_health.get_rag_queue_health(
            session,
            processing_lease_seconds=2100,
        )

    lanes = {lane["lane"]: lane for lane in health["lanes"]}
    assert health["ready"] is False
    assert lanes["realtime"]["pending"] == 1
    assert lanes["realtime"]["overdue_pending"] == 1
    assert lanes["realtime"]["last_succeeded_at"].endswith("Z")
    assert lanes["backfill"]["processing"] == 1
    assert lanes["backfill"]["stale_processing"] == 1
    assert lanes["visibility_recompute"]["pending"] == 1
    assert lanes["visibility_recompute"]["overdue_pending"] == 0
    assert {item["job_lane"] for item in recorded} == {
        "realtime",
        "backfill",
        "visibility_recompute",
    }


def test_rag_queue_health_is_ready_for_empty_queues(monkeypatch) -> None:
    engine = _engine()
    monkeypatch.setattr(queue_health, "record_sync_queue_health", lambda **_: None)
    with Session(engine) as session:
        health = queue_health.get_rag_queue_health(
            session,
            processing_lease_seconds=2100,
        )

    assert health["ready"] is True
    assert len(health["lanes"]) == 3
    assert all(lane["pending"] == 0 for lane in health["lanes"])
    assert all(lane["processing"] == 0 for lane in health["lanes"])
