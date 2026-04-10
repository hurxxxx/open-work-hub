from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.access import is_platform_admin_user
from aidoo_api.domains.auth.models import User
from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.meeting.models import Meeting
from aidoo_api.domains.pms.models import Issue, Project, ProjectMember


def is_organizer(user: User, meeting: Meeting) -> bool:
    return meeting.organizer_id == user.id


def ensure_meeting_organizer(db: Session, user: User, meeting: Meeting) -> None:
    if is_platform_admin_user(user, db):
        return
    if not is_organizer(user, meeting):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting organizer can perform this action.",
        )


def ensure_issue_readable(db: Session, user: User, issue_id: str) -> Issue:
    """PR1 fallback rule: organizer must be a project member of the issue's project.

    PR2 will introduce ``IssueUserAccess``; until then this is a hard 403 if the
    user is not a project member (or platform/org admin)."""

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

    membership = db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
        )
    )
    if membership is None:
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
