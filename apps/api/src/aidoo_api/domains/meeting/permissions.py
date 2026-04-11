from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.access import (
    is_platform_admin_user,
    resolve_team_role,
)
from aidoo_api.domains.auth.models import Team, User
from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.meeting.models import Meeting
from aidoo_api.domains.pms.models import Issue, Project


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


def ensure_issue_readable(db: Session, user: User, issue_id: str) -> Issue:
    """Allow attaching an issue iff the caller has access to the issue's
    owning PMS space. Mirrors ``_ensure_space_access`` in the PMS router so
    the attachable set matches what the user can already see in the PMS UI."""

    issue = db.scalar(select(Issue).where(Issue.id == issue_id))
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found.",
        )

    if is_platform_admin_user(user, db):
        return issue

    project = db.scalar(select(Project).where(Project.id == issue.project_id))
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found.",
        )

    if project.team_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this issue.",
        )

    team = db.scalar(select(Team).where(Team.id == project.team_id))
    if team is None or resolve_team_role(db, user, team) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this issue.",
        )
    return issue


def ensure_doc_readable(db: Session, user: User, doc_id: str) -> NativeDoc:
    """PR1: only the doc owner (or platform admin) can attach a NativeDoc.

    The full Docs share fallback (NativeDocUserShare, link shares, SpaceDoc) is
    deferred — PR1's surface is intentionally narrow."""

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
        return doc

    if doc.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this document.",
        )
    return doc
