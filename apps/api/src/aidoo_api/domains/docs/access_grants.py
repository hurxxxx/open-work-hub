from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync_by_id
from aidoo_api.domains.docs.models import DocMeetingAccess
from aidoo_api.domains.rag.contracts import RagSyncOperation


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _load_active_doc_grant(
    db: Session,
    *,
    doc_id: str,
    user_id: str,
    granted_by_meeting_id: str | None,
) -> DocMeetingAccess | None:
    return db.scalar(
        select(DocMeetingAccess).where(
            DocMeetingAccess.doc_id == doc_id,
            DocMeetingAccess.user_id == user_id,
            DocMeetingAccess.granted_by_meeting_id == granted_by_meeting_id,
            DocMeetingAccess.revoked_at.is_(None),
        )
    )


def grant_doc_access(
    db: Session,
    *,
    doc_id: str,
    user_id: str,
    granted_by_user_id: str,
    granted_by_meeting_id: str | None,
    reason: str,
    access_level: str = "read",
    expires_at: datetime | None = None,
) -> DocMeetingAccess:
    existing = _load_active_doc_grant(
        db,
        doc_id=doc_id,
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
        enqueue_native_doc_rag_sync_by_id(
            db,
            doc_id=doc_id,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
        return existing

    access = DocMeetingAccess(
        id=new_id(),
        doc_id=doc_id,
        user_id=user_id,
        access_level=access_level,
        granted_by_meeting_id=granted_by_meeting_id,
        granted_by_user_id=granted_by_user_id,
        reason=reason,
        expires_at=expires_at,
    )
    db.add(access)
    db.flush()
    enqueue_native_doc_rag_sync_by_id(
        db,
        doc_id=doc_id,
        operation=RagSyncOperation.VISIBILITY_UPDATE,
    )
    return access


def revoke_doc_grants_for_meeting_attendee(
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
            select(DocMeetingAccess).where(
                DocMeetingAccess.granted_by_meeting_id == meeting_id,
                DocMeetingAccess.user_id == user_id,
                DocMeetingAccess.revoked_at.is_(None),
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
    for doc_id in {grant.doc_id for grant in grants}:
        enqueue_native_doc_rag_sync_by_id(
            db,
            doc_id=doc_id,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
    return len(grants)


def revoke_doc_grants_for_meeting(
    db: Session,
    *,
    meeting_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(DocMeetingAccess).where(
                DocMeetingAccess.granted_by_meeting_id == meeting_id,
                DocMeetingAccess.revoked_at.is_(None),
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
    for doc_id in {grant.doc_id for grant in grants}:
        enqueue_native_doc_rag_sync_by_id(
            db,
            doc_id=doc_id,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
    return len(grants)


def revoke_doc_grants_for_attachment(
    db: Session,
    *,
    meeting_id: str,
    doc_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> int:
    now = _utcnow()
    grants = list(
        db.scalars(
            select(DocMeetingAccess).where(
                DocMeetingAccess.granted_by_meeting_id == meeting_id,
                DocMeetingAccess.doc_id == doc_id,
                DocMeetingAccess.revoked_at.is_(None),
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
    for affected_doc_id in {grant.doc_id for grant in grants}:
        enqueue_native_doc_rag_sync_by_id(
            db,
            doc_id=affected_doc_id,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
    return len(grants)


def bump_doc_grant_expiry_for_meeting(
    db: Session,
    *,
    meeting_id: str,
    new_end_at: datetime,
) -> int:
    expires_at = new_end_at + timedelta(days=7)
    grants = list(
        db.scalars(
            select(DocMeetingAccess).where(
                DocMeetingAccess.granted_by_meeting_id == meeting_id,
                DocMeetingAccess.revoked_at.is_(None),
            )
        )
    )
    for grant in grants:
        grant.expires_at = expires_at
        grant.updated_at = _utcnow()
        db.add(grant)
    db.flush()
    for doc_id in {grant.doc_id for grant in grants}:
        enqueue_native_doc_rag_sync_by_id(
            db,
            doc_id=doc_id,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
        )
    return len(grants)
