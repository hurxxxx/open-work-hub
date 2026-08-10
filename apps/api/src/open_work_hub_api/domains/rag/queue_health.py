from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.rag.contracts import RagJobStatus, RagSyncLane
from open_work_hub_api.domains.rag.metrics import record_sync_queue_health
from open_work_hub_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob


def get_rag_queue_health(
    db: Session,
    *,
    processing_lease_seconds: int,
) -> dict[str, object]:
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=processing_lease_seconds)
    sync_rows = db.execute(
        select(
            RagSyncJob.lane,
            func.sum(case((RagSyncJob.status == RagJobStatus.PENDING.value, 1), else_=0)),
            func.sum(case((RagSyncJob.status == RagJobStatus.PROCESSING.value, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            RagSyncJob.status == RagJobStatus.PROCESSING.value,
                            RagSyncJob.updated_at <= lease_cutoff,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        and_(
                            RagSyncJob.status == RagJobStatus.PENDING.value,
                            or_(
                                RagSyncJob.next_retry_at.is_(None),
                                RagSyncJob.next_retry_at <= now,
                            ),
                            RagSyncJob.created_at <= lease_cutoff,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.min(
                case((RagSyncJob.status == RagJobStatus.PENDING.value, RagSyncJob.created_at))
            ),
        )
        .where(RagSyncJob.status.in_((RagJobStatus.PENDING.value, RagJobStatus.PROCESSING.value)))
        .group_by(RagSyncJob.lane)
    ).all()
    rows_by_lane = {str(row[0]): row for row in sync_rows}
    last_sync_success_by_lane = {
        str(row[0]): row[1]
        for row in db.execute(
            select(RagSyncJob.lane, func.max(RagSyncJob.updated_at))
            .where(RagSyncJob.status == RagJobStatus.SUCCEEDED.value)
            .group_by(RagSyncJob.lane)
        ).all()
    }
    lanes: list[dict[str, object]] = []
    for lane in (RagSyncLane.REALTIME, RagSyncLane.BACKFILL):
        row = rows_by_lane.get(lane.value)
        lanes.append(
            _queue_lane_snapshot(
                lane=lane.value,
                job_kind="resource_sync",
                pending=row[1] if row is not None else 0,
                processing=row[2] if row is not None else 0,
                stale_processing=row[3] if row is not None else 0,
                overdue_pending=row[4] if row is not None else 0,
                oldest_pending_at=row[5] if row is not None else None,
                last_succeeded_at=last_sync_success_by_lane.get(lane.value),
                now=now,
            )
        )

    visibility_row = db.execute(
        select(
            func.sum(
                case(
                    (RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value, 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (RagVisibilityRecomputeJob.status == RagJobStatus.PROCESSING.value, 1),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        and_(
                            RagVisibilityRecomputeJob.status == RagJobStatus.PROCESSING.value,
                            RagVisibilityRecomputeJob.updated_at <= lease_cutoff,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(
                case(
                    (
                        and_(
                            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
                            or_(
                                RagVisibilityRecomputeJob.next_retry_at.is_(None),
                                RagVisibilityRecomputeJob.next_retry_at <= now,
                            ),
                            RagVisibilityRecomputeJob.created_at <= lease_cutoff,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.min(
                case(
                    (
                        RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
                        RagVisibilityRecomputeJob.created_at,
                    )
                )
            ),
        ).where(
            RagVisibilityRecomputeJob.status.in_(
                (RagJobStatus.PENDING.value, RagJobStatus.PROCESSING.value)
            )
        )
    ).one()
    last_visibility_success = db.scalar(
        select(func.max(RagVisibilityRecomputeJob.updated_at)).where(
            RagVisibilityRecomputeJob.status == RagJobStatus.SUCCEEDED.value
        )
    )
    lanes.append(
        _queue_lane_snapshot(
            lane="visibility_recompute",
            job_kind="visibility_recompute",
            pending=visibility_row[0],
            processing=visibility_row[1],
            stale_processing=visibility_row[2],
            overdue_pending=visibility_row[3],
            oldest_pending_at=visibility_row[4],
            last_succeeded_at=last_visibility_success,
            now=now,
        )
    )
    ready = all(lane["stale_processing"] == 0 and lane["overdue_pending"] == 0 for lane in lanes)
    return {
        "observed": True,
        "ready": ready,
        "processing_lease_seconds": processing_lease_seconds,
        "lanes": lanes,
    }


def _queue_lane_snapshot(
    *,
    lane: str,
    job_kind: str,
    pending: object,
    processing: object,
    stale_processing: object,
    overdue_pending: object,
    oldest_pending_at: object | None,
    last_succeeded_at: object | None,
    now: datetime,
) -> dict[str, object]:
    pending_count = int(pending or 0)
    processing_count = int(processing or 0)
    stale_processing_count = int(stale_processing or 0)
    overdue_pending_count = int(overdue_pending or 0)
    oldest_pending_age_seconds = _age_seconds(now, oldest_pending_at)
    record_sync_queue_health(
        oldest_pending_age_ms=oldest_pending_age_seconds * 1000,
        stale_processing_jobs=stale_processing_count,
        overdue_pending_jobs=overdue_pending_count,
        job_lane=lane,
        job_kind=job_kind,
    )
    return {
        "lane": lane,
        "pending": pending_count,
        "processing": processing_count,
        "stale_processing": stale_processing_count,
        "overdue_pending": overdue_pending_count,
        "oldest_pending_age_seconds": oldest_pending_age_seconds,
        "last_succeeded_at": _utc_iso(last_succeeded_at),
    }


def _age_seconds(now: datetime, value: object | None) -> int:
    if not isinstance(value, datetime):
        return 0
    return max(int((now - value).total_seconds()), 0)


def _utc_iso(value: object | None) -> str | None:
    if not isinstance(value, datetime):
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")
