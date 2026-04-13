from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.access import (
    is_platform_admin_user,
)
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.meeting.models import Meeting


def is_organizer(user: User, meeting: Meeting) -> bool:
    return meeting.organizer_id == user.id


def is_participant(user: User, meeting: Meeting) -> bool:
    """Organizer or any active attendee."""
    if meeting.organizer_id == user.id:
        return True
    return any(att.user_id == user.id for att in meeting.attendees)


def ensure_meeting_organizer(db: Session, user: User, meeting: Meeting) -> None:
    if is_platform_admin_user(user, db):
        return
    if not is_organizer(user, meeting):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting organizer can perform this action.",
        )


def ensure_meeting_participant(db: Session, user: User, meeting: Meeting) -> None:
    """Allow the action if the caller is the organizer, an attendee, or a
    platform admin. Used for adding attachments (tasks/docs/files) where any
    meeting participant should be able to upload prep material before the
    meeting starts."""
    if is_platform_admin_user(user, db):
        return
    if not is_participant(user, meeting):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only meeting participants can perform this action.",
        )


def ensure_link_remover(
    db: Session, user: User, meeting: Meeting, added_by_id: str
) -> None:
    """Allow removing an attachment only if the caller is the organizer,
    a platform admin, or the original adder. Attendees cannot delete each
    other's attachments."""
    if is_platform_admin_user(user, db):
        return
    if meeting.organizer_id == user.id:
        return
    if added_by_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only the meeting organizer or the user who added the attachment can remove it.",
    )


def ensure_doc_attachable(
    db: Session,
    user: User,
    doc_id: str,
    *,
    workspace: Workspace,
) -> NativeDoc:
    """Meeting attachments keep the existing doc attach authority boundary.

    Meeting-origin read grants are intentionally excluded here so an attendee
    who can open a doc via a meeting cannot reattach it to a different meeting.
    """
    doc = db.scalar(
        select(NativeDoc).where(
            NativeDoc.id == doc_id,
            NativeDoc.trashed_at.is_(None),
        )
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    if is_platform_admin_user(user, db):
        if doc.workspace_id != workspace.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this document.",
            )
        return doc

    if doc.workspace_id != workspace.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )
    if doc.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )
    return doc
