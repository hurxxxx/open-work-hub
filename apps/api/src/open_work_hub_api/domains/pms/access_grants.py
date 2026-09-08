from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.pms.models import TaskUserAccess
from open_work_hub_api.domains.pms.rag_sync import (
    enqueue_meeting_task_visibility_recompute,
    enqueue_task_rag_sync_by_id,
)
from open_work_hub_api.domains.rag.contracts import RagSyncOperation


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load_active_task_grant(
    db: Session,
    *,
    task_id: str,
    user_id: str,
    granted_by_meeting_id: str | None,
) -> TaskUserAccess | None:
    return db.scalar(
        select(TaskUserAccess).where(
            TaskUserAccess.task_id == task_id,
            TaskUserAccess.user_id == user_id,
            TaskUserAccess.granted_by_meeting_id == granted_by_meeting_id,
            TaskUserAccess.revoked_at.is_(None),
        )
    )


def _enqueue_task_grant_visibility_recompute(
    db: Session,
    *,
    task_id: str,
    granted_by_meeting_id: str | None,
) -> None:
    if granted_by_meeting_id is not None:
        enqueue_meeting_task_visibility_recompute(
            db,
            meeting_id=granted_by_meeting_id,
            task_ids=[task_id],
        )
        return
    enqueue_task_rag_sync_by_id(
        db,
        task_id=task_id,
        operation=RagSyncOperation.VISIBILITY_UPDATE,
    )


def _enqueue_meeting_grants_visibility_recompute(
    db: Session,
    *,
    meeting_id: str,
    grants: list[TaskUserAccess],
) -> None:
    enqueue_meeting_task_visibility_recompute(
        db,
        meeting_id=meeting_id,
        task_ids=[grant.task_id for grant in grants],
    )


def _mark_grants_revoked(
    db: Session,
    *,
    grants: list[TaskUserAccess],
    revoked_by_user_id: str,
    reason: str,
    now: datetime,
) -> None:
    for grant in grants:
        grant.revoked_at = now
        grant.revoked_by_user_id = revoked_by_user_id
        grant.revoke_reason = reason
        grant.updated_at = now
        db.add(grant)
    db.flush()


def grant_task_access(
    db: Session,
    *,
    task_id: str,
    user_id: str,
    granted_by_user_id: str,
    granted_by_meeting_id: str | None,
    reason: str,
    access_level: str = "read",
    expires_at: datetime | None = None,
) -> TaskUserAccess:
    existing = _load_active_task_grant(
        db,
        task_id=task_id,
        user_id=user_id,
        granted_by_meeting_id=granted_by_meeting_id,
    )
    if existing is not None:
        existing.access_level = access_level
        existing.expires_at = expires_at
        existing.reason = reason
        existing.granted_by_user_id = granted_by_user_id
        existing.updated_at = _utcnow()
        db.add(existing)
        db.flush()
        _enqueue_task_grant_visibility_recompute(
            db,
            task_id=task_id,
            granted_by_meeting_id=granted_by_meeting_id,
        )
        return existing

    access = TaskUserAccess(
        id=new_id(),
        task_id=task_id,
        user_id=user_id,
        access_level=access_level,
        granted_by_meeting_id=granted_by_meeting_id,
        granted_by_user_id=granted_by_user_id,
        reason=reason,
        expires_at=expires_at,
    )
    db.add(access)
    db.flush()
    _enqueue_task_grant_visibility_recompute(
        db,
        task_id=task_id,
        granted_by_meeting_id=granted_by_meeting_id,
    )
    return access


def revoke_task_access(
    db: Session,
    *,
    task_id: str,
    user_id: str,
    revoked_by_user_id: str,
    reason: str,
    granted_by_meeting_id: str | None = None,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(TaskUserAccess).where(
                TaskUserAccess.task_id == task_id,
                TaskUserAccess.user_id == user_id,
                TaskUserAccess.granted_by_meeting_id == granted_by_meeting_id,
                TaskUserAccess.revoked_at.is_(None),
            )
        )
    )
    _mark_grants_revoked(
        db,
        grants=grants,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
        now=now,
    )
    if not grants:
        return 0
    _enqueue_task_grant_visibility_recompute(
        db,
        task_id=task_id,
        granted_by_meeting_id=granted_by_meeting_id,
    )
    return len(grants)


def revoke_grants_for_meeting_attendee(
    db: Session,
    *,
    meeting_id: str,
    user_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(TaskUserAccess).where(
                TaskUserAccess.granted_by_meeting_id == meeting_id,
                TaskUserAccess.user_id == user_id,
                TaskUserAccess.revoked_at.is_(None),
            )
        )
    )
    _mark_grants_revoked(
        db,
        grants=grants,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
        now=now,
    )
    _enqueue_meeting_grants_visibility_recompute(
        db,
        meeting_id=meeting_id,
        grants=grants,
    )
    return len(grants)


def revoke_grants_for_meeting(
    db: Session,
    *,
    meeting_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(TaskUserAccess).where(
                TaskUserAccess.granted_by_meeting_id == meeting_id,
                TaskUserAccess.revoked_at.is_(None),
            )
        )
    )
    _mark_grants_revoked(
        db,
        grants=grants,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
        now=now,
    )
    _enqueue_meeting_grants_visibility_recompute(
        db,
        meeting_id=meeting_id,
        grants=grants,
    )
    return len(grants)


def revoke_grants_for_task_attachment(
    db: Session,
    *,
    meeting_id: str,
    task_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(TaskUserAccess).where(
                TaskUserAccess.granted_by_meeting_id == meeting_id,
                TaskUserAccess.task_id == task_id,
                TaskUserAccess.revoked_at.is_(None),
            )
        )
    )
    _mark_grants_revoked(
        db,
        grants=grants,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
        now=now,
    )
    _enqueue_meeting_grants_visibility_recompute(
        db,
        meeting_id=meeting_id,
        grants=grants,
    )
    return len(grants)


def bump_grant_expiry_for_meeting(
    db: Session,
    *,
    meeting_id: str,
    new_end_at: datetime,
) -> int:
    expires_at = new_end_at + timedelta(days=7)
    grants = list(
        db.scalars(
            select(TaskUserAccess).where(
                TaskUserAccess.granted_by_meeting_id == meeting_id,
                TaskUserAccess.revoked_at.is_(None),
            )
        )
    )
    for grant in grants:
        grant.expires_at = expires_at
        grant.updated_at = _utcnow()
        db.add(grant)
    db.flush()
    _enqueue_meeting_grants_visibility_recompute(
        db,
        meeting_id=meeting_id,
        grants=grants,
    )
    return len(grants)
