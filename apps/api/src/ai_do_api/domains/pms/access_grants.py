from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.pms.models import IssueUserAccess
from ai_do_api.domains.pms.rag_sync import (
    enqueue_issue_rag_sync_by_id,
    enqueue_meeting_issue_visibility_recompute,
)
from ai_do_api.domains.rag.contracts import RagSyncOperation


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load_active_issue_grant(
    db: Session,
    *,
    issue_id: str,
    user_id: str,
    granted_by_meeting_id: str | None,
) -> IssueUserAccess | None:
    return db.scalar(
        select(IssueUserAccess).where(
            IssueUserAccess.issue_id == issue_id,
            IssueUserAccess.user_id == user_id,
            IssueUserAccess.granted_by_meeting_id == granted_by_meeting_id,
            IssueUserAccess.revoked_at.is_(None),
        )
    )


def grant_issue_access(
    db: Session,
    *,
    issue_id: str,
    user_id: str,
    granted_by_user_id: str,
    granted_by_meeting_id: str | None,
    reason: str,
    access_level: str = "read",
    expires_at: datetime | None = None,
) -> IssueUserAccess:
    existing = _load_active_issue_grant(
        db,
        issue_id=issue_id,
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
        if granted_by_meeting_id is not None:
            enqueue_meeting_issue_visibility_recompute(
                db,
                meeting_id=granted_by_meeting_id,
                issue_ids=[issue_id],
            )
        else:
            enqueue_issue_rag_sync_by_id(
                db,
                issue_id=issue_id,
                operation=RagSyncOperation.VISIBILITY_UPDATE,
            )
        return existing

    access = IssueUserAccess(
        id=new_id(),
        issue_id=issue_id,
        user_id=user_id,
        access_level=access_level,
        granted_by_meeting_id=granted_by_meeting_id,
        granted_by_user_id=granted_by_user_id,
        reason=reason,
        expires_at=expires_at,
    )
    db.add(access)
    db.flush()
    if granted_by_meeting_id is not None:
        enqueue_meeting_issue_visibility_recompute(
            db,
            meeting_id=granted_by_meeting_id,
            issue_ids=[issue_id],
        )
    else:
        enqueue_issue_rag_sync_by_id(
            db,
            issue_id=issue_id,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
    return access


def revoke_issue_access(
    db: Session,
    *,
    issue_id: str,
    user_id: str,
    revoked_by_user_id: str,
    reason: str,
    granted_by_meeting_id: str | None = None,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(IssueUserAccess).where(
                IssueUserAccess.issue_id == issue_id,
                IssueUserAccess.user_id == user_id,
                IssueUserAccess.granted_by_meeting_id == granted_by_meeting_id,
                IssueUserAccess.revoked_at.is_(None),
            )
        )
    )
    for grant in grants:
        grant.revoked_at = now
        grant.revoked_by_user_id = revoked_by_user_id
        grant.revoke_reason = reason
        grant.updated_at = now
        db.add(grant)
    db.flush()
    if not grants:
        return 0
    if granted_by_meeting_id is not None:
        enqueue_meeting_issue_visibility_recompute(
            db,
            meeting_id=granted_by_meeting_id,
            issue_ids=[issue_id],
        )
    else:
        enqueue_issue_rag_sync_by_id(
            db,
            issue_id=issue_id,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
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
            select(IssueUserAccess).where(
                IssueUserAccess.granted_by_meeting_id == meeting_id,
                IssueUserAccess.user_id == user_id,
                IssueUserAccess.revoked_at.is_(None),
            )
        )
    )
    for grant in grants:
        grant.revoked_at = now
        grant.revoked_by_user_id = revoked_by_user_id
        grant.revoke_reason = reason
        grant.updated_at = now
        db.add(grant)
    db.flush()
    enqueue_meeting_issue_visibility_recompute(
        db,
        meeting_id=meeting_id,
        issue_ids=[grant.issue_id for grant in grants],
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
            select(IssueUserAccess).where(
                IssueUserAccess.granted_by_meeting_id == meeting_id,
                IssueUserAccess.revoked_at.is_(None),
            )
        )
    )
    for grant in grants:
        grant.revoked_at = now
        grant.revoked_by_user_id = revoked_by_user_id
        grant.revoke_reason = reason
        grant.updated_at = now
        db.add(grant)
    db.flush()
    enqueue_meeting_issue_visibility_recompute(
        db,
        meeting_id=meeting_id,
        issue_ids=[grant.issue_id for grant in grants],
    )
    return len(grants)


def revoke_grants_for_issue_attachment(
    db: Session,
    *,
    meeting_id: str,
    issue_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(IssueUserAccess).where(
                IssueUserAccess.granted_by_meeting_id == meeting_id,
                IssueUserAccess.issue_id == issue_id,
                IssueUserAccess.revoked_at.is_(None),
            )
        )
    )
    for grant in grants:
        grant.revoked_at = now
        grant.revoked_by_user_id = revoked_by_user_id
        grant.revoke_reason = reason
        grant.updated_at = now
        db.add(grant)
    db.flush()
    enqueue_meeting_issue_visibility_recompute(
        db,
        meeting_id=meeting_id,
        issue_ids=[grant.issue_id for grant in grants],
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
            select(IssueUserAccess).where(
                IssueUserAccess.granted_by_meeting_id == meeting_id,
                IssueUserAccess.revoked_at.is_(None),
            )
        )
    )
    for grant in grants:
        grant.expires_at = expires_at
        grant.updated_at = _utcnow()
        db.add(grant)
    db.flush()
    enqueue_meeting_issue_visibility_recompute(
        db,
        meeting_id=meeting_id,
        issue_ids=[grant.issue_id for grant in grants],
    )
    return len(grants)
