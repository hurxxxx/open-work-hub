from __future__ import annotations

from datetime import UTC, datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import (
    get_current_workspace,
    normalize_team_role,
)
from open_work_hub_api.domains.auth.models import Team, TeamMember, User, Workspace
from open_work_hub_api.domains.auth.roles import team_role_allows_predicate
from open_work_hub_api.domains.auth.workspace_app_gate import is_app_enabled_for_user_context
from open_work_hub_api.domains.pms.models import Task, TaskUserAccess, TaskList
from open_work_hub_api.domains.source_access import can_read_pms_task

SPACE_TEAM_MANAGER_ROLES = {"admin", "owner"}
SPACE_TEAM_EDITOR_ROLES = {"member", "admin", "owner"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _get_pms_workspace(db: Session) -> Workspace:
    workspace = get_current_workspace(db)
    if workspace is None:
        raise localized_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="pms.workspace_context_unavailable",
        )
    return workspace


def _load_active_space(
    db: Session,
    space_id: str | None,
    *,
    include_members: bool = False,
) -> Team | None:
    if space_id is None:
        return None
    workspace = _get_pms_workspace(db)
    query = (
        select(Team)
        .options(joinedload(Team.workspace))
        .where(
            Team.id == space_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
            Team.workspace_id == workspace.id,
        )
    )
    if include_members:
        query = query.options(selectinload(Team.members))
    return db.scalar(query)


def _load_active_team(db: Session, team_id: str | None) -> Team | None:
    return _load_active_space(db, team_id)


def _ensure_space_access(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team = _load_active_space(db, space_id, include_members=True)
    if team is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pms.space_not_found",
        )
    role = resolve_pms_space_role(db, user, team)
    if role is None:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="pms.space_access_required",
        )
    return team, role


def _ensure_space_manager(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)
    if role in SPACE_TEAM_MANAGER_ROLES:
        return team, role
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="pms.space_owner_admin_required",
    )


def _ensure_space_editor(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)
    if role in SPACE_TEAM_EDITOR_ROLES:
        return team, role
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="pms.space_viewer_modify_denied",
    )


def _ensure_space_owner(db: Session, user: User, space_id: str) -> tuple[Team, str]:
    team, role = _ensure_space_access(db, user, space_id)
    if role == "owner":
        return team, role
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="pms.space_owner_required",
    )


def resolve_pms_space_role(db: Session, user: User, team: Team) -> str | None:
    role = db.scalar(
        select(TeamMember.role).where(
            TeamMember.team_id == team.id,
            TeamMember.user_id == user.id,
        )
    )
    return normalize_team_role(role)


def _accessible_space_ids(db: Session, user: User) -> set[str]:
    workspace = _get_pms_workspace(db)
    return set(
        db.scalars(
            select(TeamMember.team_id)
            .join(Team, Team.id == TeamMember.team_id)
            .where(
                TeamMember.user_id == user.id,
                team_role_allows_predicate(TeamMember.role),
                Team.active.is_(True),
                Team.trashed_at.is_(None),
                Team.workspace.has(Workspace.active.is_(True)),
                Team.workspace_id == workspace.id,
            )
        )
    )


def _space_query_for_user(db: Session, user: User):
    workspace = _get_pms_workspace(db)
    return (
        select(Team)
        .options(joinedload(Team.workspace), selectinload(Team.members))
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(
            TeamMember.user_id == user.id,
            team_role_allows_predicate(TeamMember.role),
            Team.active.is_(True),
            Team.trashed_at.is_(None),
            Team.workspace.has(Workspace.active.is_(True)),
            Team.workspace_id == workspace.id,
        )
    )


def _accessible_task_lists_query(db: Session, user: User):
    accessible_space_ids = _accessible_space_ids(db, user)
    if not accessible_space_ids:
        return select(TaskList).where(TaskList.id == "__none__")
    return select(TaskList).where(TaskList.team_id.in_(accessible_space_ids))


def _active_accessible_task_lists_query(db: Session, user: User):
    """Return current-work lists without hiding archived detail/restore access."""

    return _accessible_task_lists_query(db, user).where(TaskList.archived.is_(False))


def _space_member_ids(db: Session, space_id: str) -> set[str]:
    return set(db.scalars(select(TeamMember.user_id).where(TeamMember.team_id == space_id)))


def _load_space_members(db: Session, space_id: str) -> list[TeamMember]:
    return list(
        db.scalars(
            select(TeamMember)
            .options(selectinload(TeamMember.user))
            .where(TeamMember.team_id == space_id)
        )
    )


def _get_space_membership(
    db: Session,
    space_id: str,
    user_id: str,
) -> TeamMember | None:
    return db.scalar(
        select(TeamMember)
        .options(selectinload(TeamMember.user))
        .where(
            TeamMember.team_id == space_id,
            TeamMember.user_id == user_id,
        )
    )


def _validate_space_member_user(db: Session, space_id: str, user_id: str) -> User:
    user = db.scalar(select(User).where(User.id == user_id, User.status == "active"))
    if user is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="auth.user_not_found",
        )
    if user_id in _space_member_ids(db, space_id):
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="pms.user_already_space_member",
        )
    return user


def _ensure_space_owner_survives(
    members: list[TeamMember],
    target_user_id: str,
    *,
    next_role: str | None,
) -> None:
    current_member = next((member for member in members if member.user_id == target_user_id), None)
    if current_member is None or current_member.role != "owner":
        return

    remaining = 0
    for member in members:
        role = next_role if member.user_id == target_user_id else member.role
        if role == "owner":
            remaining += 1

    if remaining < 1:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="pms.space_owner_must_remain",
        )


def _ensure_space_admin_change_allowed(
    db: Session,
    user: User,
    space_id: str,
    *,
    current_role: str | None,
    next_role: str | None,
) -> tuple[Team, str]:
    team, actor_role = _ensure_space_manager(db, user, space_id)
    if actor_role != "owner" and (
        current_role in SPACE_TEAM_MANAGER_ROLES or next_role in SPACE_TEAM_MANAGER_ROLES
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="pms.space_owner_admin_manage_required",
        )
    return team, actor_role


def _load_list(db: Session, list_id: str) -> TaskList | None:
    return db.scalar(
        select(TaskList)
        .options(
            selectinload(TaskList.milestones),
            selectinload(TaskList.statuses),
            selectinload(TaskList.space_statuses),
            joinedload(TaskList.folder),
        )
        .where(TaskList.id == list_id)
    )


def _load_task(db: Session, task_or_id: Task | str) -> Task:
    if isinstance(task_or_id, Task):
        return task_or_id
    task = db.scalar(
        select(Task).options(selectinload(Task.task_list)).where(Task.id == task_or_id)
    )
    if task is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="pms.task_not_found",
        )
    return task


def has_list_access(db: Session, user: User, list_id: str) -> bool:
    task_list = _load_list(db, list_id)
    if task_list is None:
        return False
    if task_list.team_id is None:
        return False
    team = _load_active_team(db, task_list.team_id)
    if team is None:
        return False
    return resolve_pms_space_role(db, user, team) is not None


def _ensure_list_member(db: Session, user: User, list_id: str) -> tuple[TaskList, str]:
    task_list = _load_list(db, list_id)
    if task_list is None:
        raise localized_http_exception(status_code=404, code="pms.task_list_not_found")
    if task_list.team_id is None:
        raise localized_http_exception(status_code=409, code="pms.task_list_space_missing")

    team = _load_active_team(db, task_list.team_id)
    if team is None:
        raise localized_http_exception(status_code=404, code="pms.task_list_not_found")
    role = resolve_pms_space_role(db, user, team)
    if role is None:
        raise localized_http_exception(status_code=403, code="pms.task_list_access_required")
    return task_list, role


def _ensure_list_owner(db: Session, user: User, list_id: str) -> tuple[TaskList, str]:
    task_list, role = _ensure_list_manager(db, user, list_id)
    _ensure_task_list_active(task_list)
    return task_list, role


def _ensure_list_manager(db: Session, user: User, list_id: str) -> tuple[TaskList, str]:
    """Authorize list administration without applying the archived write guard."""

    task_list, role = _ensure_list_member(db, user, list_id)
    if role not in {"owner", "admin"}:
        raise localized_http_exception(status_code=403, code="pms.task_list_owner_admin_required")
    return task_list, role


def _ensure_task_list_active(task_list: TaskList) -> None:
    if task_list.archived:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="pms.task_list_archived_read_only",
        )


def _ensure_list_editor(db: Session, user: User, list_id: str) -> tuple[TaskList, str]:
    task_list, role = _ensure_list_member(db, user, list_id)
    if role == "viewer":
        raise localized_http_exception(status_code=403, code="pms.task_list_viewer_modify_denied")
    _ensure_task_list_active(task_list)
    return task_list, role


def _active_task_grant(db: Session, *, task_id: str, user_id: str) -> TaskUserAccess | None:
    now = _utcnow()
    return db.scalar(
        select(TaskUserAccess).where(
            TaskUserAccess.task_id == task_id,
            TaskUserAccess.user_id == user_id,
            TaskUserAccess.access_level.in_(("read", "edit")),
            TaskUserAccess.revoked_at.is_(None),
            (TaskUserAccess.expires_at.is_(None) | (TaskUserAccess.expires_at > now)),
        )
    )


def _ensure_task_readable(db: Session, user: User, task_or_id: Task | str) -> Task:
    task = _load_task(db, task_or_id)
    task_list = _load_list(db, task.list_id)
    team = _load_active_team(db, task_list.team_id) if task_list is not None else None
    if team is None or not is_app_enabled_for_user_context(
        db, app_id="pms", user_id=user.id, workspace_id=team.workspace_id
    ):
        raise localized_http_exception(status_code=403, code="pms.task_access_required")
    if has_list_access(db, user, task.list_id):
        return task
    if _active_task_grant(db, task_id=task.id, user_id=user.id) is not None:
        return task
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="pms.task_access_required",
    )


def can_read_task_for_rag(db: Session, *, user: User, task_id: str) -> bool:
    return can_read_pms_task(db, user=user, task_id=task_id)


def _ensure_task_writable(db: Session, user: User, task_or_id: Task | str) -> Task:
    task = _load_task(db, task_or_id)
    _ensure_list_editor(db, user, task.list_id)
    return task


def ensure_task_attachable(db: Session, user: User, task_or_id: Task | str) -> Task:
    task = _load_task(db, task_or_id)
    task_list, _role = _ensure_list_member(db, user, task.list_id)
    _ensure_task_list_active(task_list)
    return task
