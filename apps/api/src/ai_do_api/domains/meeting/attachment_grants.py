from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import User
from ai_do_api.domains.docs.access_grants import (
    bump_doc_grant_expiry_for_meeting,
    grant_doc_access,
    revoke_doc_grants_for_attachment,
    revoke_doc_grants_for_meeting,
    revoke_doc_grants_for_meeting_attendee,
)
from ai_do_api.domains.docs.models import DocMeetingAccess, NativeDoc
from ai_do_api.domains.meeting.models import Meeting
from ai_do_api.domains.pms.access import has_list_access
from ai_do_api.domains.pms.access_grants import (
    bump_grant_expiry_for_meeting,
    grant_task_access,
    revoke_grants_for_meeting,
    revoke_grants_for_meeting_attendee,
    revoke_grants_for_task_attachment,
)
from ai_do_api.domains.pms.models import Task, TaskUserAccess


def meeting_attachment_grant_expires_at(meeting: Meeting) -> datetime:
    return meeting.end_at + timedelta(days=7)


def grant_task_attachment_to_attendees(
    db: Session,
    *,
    meeting: Meeting,
    task: Task,
    added_by_id: str,
) -> None:
    for attendee in meeting.attendees:
        if attendee.user is None:
            continue
        _grant_task_to_attendee(
            db,
            meeting=meeting,
            task=task,
            attendee_user=attendee.user,
            granted_by_user_id=added_by_id,
        )


def grant_doc_attachment_to_attendees(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
    added_by_id: str,
) -> None:
    for attendee in meeting.attendees:
        if attendee.user is None:
            continue
        _grant_doc_to_attendee(
            db,
            meeting=meeting,
            doc=doc,
            attendee_user=attendee.user,
            granted_by_user_id=added_by_id,
        )


def grant_existing_attachments_to_new_attendees(
    db: Session,
    *,
    meeting: Meeting,
    attendee_user_ids: Iterable[str],
    granted_by_user_id: str,
) -> None:
    added_user_ids = set(attendee_user_ids)
    if not added_user_ids:
        return
    tasks_by_id = {
        task.id: task
        for task in db.scalars(
            select(Task).where(
                Task.id.in_([link.task_id for link in meeting.task_links] or ["__none__"])
            )
        )
    }
    docs_by_id = {
        doc.id: doc
        for doc in db.scalars(
            select(NativeDoc).where(
                NativeDoc.id.in_([link.doc_id for link in meeting.doc_links] or ["__none__"])
            )
        )
    }
    for attendee in meeting.attendees:
        if attendee.user_id not in added_user_ids or attendee.user is None:
            continue
        for link in meeting.task_links:
            task = tasks_by_id.get(link.task_id)
            if task is not None:
                _grant_task_to_attendee(
                    db,
                    meeting=meeting,
                    task=task,
                    attendee_user=attendee.user,
                    granted_by_user_id=granted_by_user_id,
                )
        for link in meeting.doc_links:
            doc = docs_by_id.get(link.doc_id)
            if doc is not None:
                _grant_doc_to_attendee(
                    db,
                    meeting=meeting,
                    doc=doc,
                    attendee_user=attendee.user,
                    granted_by_user_id=granted_by_user_id,
                )


def revoke_attachment_grants_for_removed_attendee(
    db: Session,
    *,
    meeting_id: str,
    user_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> None:
    revoke_grants_for_meeting_attendee(
        db,
        meeting_id=meeting_id,
        user_id=user_id,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
    )
    revoke_doc_grants_for_meeting_attendee(
        db,
        meeting_id=meeting_id,
        user_id=user_id,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
    )


def bump_attachment_grant_expiry_for_meeting(
    db: Session,
    *,
    meeting_id: str,
    new_end_at: datetime,
) -> None:
    bump_grant_expiry_for_meeting(
        db,
        meeting_id=meeting_id,
        new_end_at=new_end_at,
    )
    bump_doc_grant_expiry_for_meeting(
        db,
        meeting_id=meeting_id,
        new_end_at=new_end_at,
    )


def revoke_attachment_grants_for_deleted_meeting(
    db: Session,
    *,
    meeting_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> None:
    revoke_grants_for_meeting(
        db,
        meeting_id=meeting_id,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
    )
    revoke_doc_grants_for_meeting(
        db,
        meeting_id=meeting_id,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
    )


def revoke_task_attachment_grants(
    db: Session,
    *,
    meeting_id: str,
    task_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> None:
    revoke_grants_for_task_attachment(
        db,
        meeting_id=meeting_id,
        task_id=task_id,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
    )


def revoke_doc_attachment_grants(
    db: Session,
    *,
    meeting_id: str,
    doc_id: str,
    revoked_by_user_id: str,
    reason: str,
) -> None:
    revoke_doc_grants_for_attachment(
        db,
        meeting_id=meeting_id,
        doc_id=doc_id,
        revoked_by_user_id=revoked_by_user_id,
        reason=reason,
    )


def detach_deleted_meeting_grant_fks(db: Session, *, meeting_id: str) -> None:
    for grant in db.scalars(
        select(TaskUserAccess).where(TaskUserAccess.granted_by_meeting_id == meeting_id)
    ):
        grant.granted_by_meeting_id = None
        db.add(grant)
    for grant in db.scalars(
        select(DocMeetingAccess).where(DocMeetingAccess.granted_by_meeting_id == meeting_id)
    ):
        grant.granted_by_meeting_id = None
        db.add(grant)


def _grant_task_to_attendee(
    db: Session,
    *,
    meeting: Meeting,
    task: Task,
    attendee_user: User,
    granted_by_user_id: str,
) -> None:
    if attendee_user.id == granted_by_user_id:
        return
    if has_list_access(db, attendee_user, task.list_id):
        return
    grant_task_access(
        db,
        task_id=task.id,
        user_id=attendee_user.id,
        granted_by_user_id=granted_by_user_id,
        granted_by_meeting_id=meeting.id,
        reason="meeting_attendee",
        expires_at=meeting_attachment_grant_expires_at(meeting),
    )


def _grant_doc_to_attendee(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
    attendee_user: User,
    granted_by_user_id: str,
) -> None:
    if attendee_user.id == granted_by_user_id:
        return
    if attendee_user.id == doc.owner_id:
        return
    grant_doc_access(
        db,
        doc_id=doc.id,
        user_id=attendee_user.id,
        granted_by_user_id=granted_by_user_id,
        granted_by_meeting_id=meeting.id,
        reason="meeting_attendee",
        expires_at=meeting_attachment_grant_expires_at(meeting),
    )
