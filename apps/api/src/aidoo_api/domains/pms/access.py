from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.domains.auth.access import (
    get_current_workspace,
    is_platform_admin_user,
    resolve_team_role,
)
from aidoo_api.domains.auth.models import Team, User, Workspace
from aidoo_api.domains.pms.models import Issue, IssueUserAccess, Project


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get_pms_workspace(db: Session) -> Workspace:
    workspace = get_current_workspace(db)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PMS workspace context is not available.",
        )
    return workspace


def _load_active_team(db: Session, team_id: str | None) -> Team | None:
    if team_id is None:
        return None
    workspace = _get_pms_workspace(db)
    query = (
        select(Team)
        .options(joinedload(Team.workspace))
        .where(
            Team.id == team_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
        )
    )
    if workspace is not None:
        query = query.where(Team.workspace_id == workspace.id)
    return db.scalar(query)


def _load_list(db: Session, list_id: str) -> Project | None:
    return db.scalar(
        select(Project)
        .options(
            selectinload(Project.milestones),
            selectinload(Project.statuses),
            joinedload(Project.folder),
        )
        .where(Project.id == list_id)
    )


def _load_issue(db: Session, issue_or_id: Issue | str) -> Issue:
    if isinstance(issue_or_id, Issue):
        return issue_or_id
    issue = db.scalar(select(Issue).options(selectinload(Issue.project)).where(Issue.id == issue_or_id))
    if issue is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue not found.",
        )
    return issue


def has_list_access(db: Session, user: User, list_id: str) -> bool:
    project = _load_list(db, list_id)
    if project is None:
        return False
    if project.team_id is None:
        return False
    team = _load_active_team(db, project.team_id)
    if team is None:
        return False
    if is_platform_admin_user(user, db):
        return True
    return resolve_team_role(db, user, team) is not None


def _ensure_list_member(db: Session, user: User, list_id: str) -> tuple[Project, str]:
    project = _load_list(db, list_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.team_id is None:
        raise HTTPException(status_code=409, detail="Project space is not set.")

    team = _load_active_team(db, project.team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    if is_platform_admin_user(user, db):
        return project, "owner"

    role = resolve_team_role(db, user, team)
    if role is None:
        raise HTTPException(status_code=403, detail="Project access required.")
    return project, role


def _ensure_list_owner(db: Session, user: User, list_id: str) -> tuple[Project, str]:
    project, role = _ensure_list_member(db, user, list_id)
    if not is_platform_admin_user(user, db) and role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Project owner/admin access required.")
    return project, role


def _ensure_list_editor(db: Session, user: User, list_id: str) -> tuple[Project, str]:
    project, role = _ensure_list_member(db, user, list_id)
    if not is_platform_admin_user(user, db) and role == "viewer":
        raise HTTPException(status_code=403, detail="Viewer role cannot modify project data.")
    return project, role


def _active_issue_grant(db: Session, *, issue_id: str, user_id: str) -> IssueUserAccess | None:
    now = _utcnow()
    return db.scalar(
        select(IssueUserAccess).where(
            IssueUserAccess.issue_id == issue_id,
            IssueUserAccess.user_id == user_id,
            IssueUserAccess.revoked_at.is_(None),
            (IssueUserAccess.expires_at.is_(None) | (IssueUserAccess.expires_at > now)),
        )
    )


def _ensure_issue_readable(db: Session, user: User, issue_or_id: Issue | str) -> Issue:
    issue = _load_issue(db, issue_or_id)
    if has_list_access(db, user, issue.list_id):
        return issue
    if _active_issue_grant(db, issue_id=issue.id, user_id=user.id) is not None:
        return issue
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this issue.",
    )


def _ensure_issue_writable(db: Session, user: User, issue_or_id: Issue | str) -> Issue:
    issue = _load_issue(db, issue_or_id)
    _ensure_list_editor(db, user, issue.list_id)
    return issue


def ensure_issue_attachable(db: Session, user: User, issue_or_id: Issue | str) -> Issue:
    issue = _load_issue(db, issue_or_id)
    _ensure_list_member(db, user, issue.list_id)
    return issue
