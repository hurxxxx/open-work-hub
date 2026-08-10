from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.access import (
    resolve_team_role,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from open_work_hub_api.domains.auth.models import Team, User, Workspace
from open_work_hub_api.domains.meeting.models import Meeting
from open_work_hub_api.domains.meeting.permissions import is_organizer, is_participant
from open_work_hub_api.domains.pms.links import pms_space_whiteboards_path, pms_task_list_path
from open_work_hub_api.domains.pms.models import TaskList
from open_work_hub_api.domains.source_access.targets import (
    TargetRef as SourceTargetRef,
    project_target_access as project_source_target_access,
    resolve_target_label as resolve_source_target_label,
)
from open_work_hub_api.domains.whiteboard.models import Whiteboard, WhiteboardTarget


@dataclass(frozen=True)
class TargetRef:
    app: str
    type: str
    id: str


@dataclass(frozen=True)
class TargetAccessProjection:
    can_view: bool
    can_edit: bool
    can_manage: bool


def _empty_projection() -> TargetAccessProjection:
    return TargetAccessProjection(False, False, False)


def _source_ref(ref: TargetRef) -> SourceTargetRef:
    return SourceTargetRef(app=ref.app, type=ref.type, id=ref.id)


def _project_source_target_ref(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: TargetRef,
) -> TargetAccessProjection:
    projection = project_source_target_access(
        db=db,
        user=user,
        workspace=workspace,
        ref=_source_ref(ref),
    )
    return TargetAccessProjection(
        can_view=projection.can_view,
        can_edit=projection.can_edit,
        can_manage=projection.can_manage,
    )


def _project_pms_space_access(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    space_id: str,
) -> TargetAccessProjection:
    return _project_source_target_ref(
        db=db,
        user=user,
        workspace=workspace,
        ref=TargetRef(app="pms", type="space", id=space_id),
    )


def describe_source(
    *,
    workspace: Workspace,
    whiteboard: Whiteboard,
    primary_target: WhiteboardTarget | None,
) -> tuple[str, str | None]:
    label = whiteboard.source_app.replace("_", " ").title()
    if whiteboard.source_app == "whiteboard":
        label = "Whiteboard"
    if whiteboard.source_app == "pms":
        label = "PMS"
    if whiteboard.source_app == "meeting":
        label = "Meeting"
    if primary_target is not None and primary_target.target_app == "pms":
        if primary_target.target_type == "space":
            return (
                label,
                pms_space_whiteboards_path(
                    workspace,
                    primary_target.target_id,
                    whiteboard_id=whiteboard.id,
                ),
            )
        if primary_target.target_type == "task_list":
            return (
                label,
                pms_task_list_path(
                    workspace,
                    primary_target.target_id,
                    query={"tab": "whiteboard"},
                ),
            )
    if primary_target is not None and primary_target.target_app == "meeting":
        return label, f"/w/{workspace.key}/meeting/{primary_target.target_id}"
    return label, f"/w/{workspace.key}/whiteboard/{whiteboard.id}"


def resolve_target_label(
    *,
    db: Session,
    workspace: Workspace,
    target: WhiteboardTarget | None,
) -> str:
    if target is None:
        return "Unfiled"
    ref = TargetRef(
        app=target.target_app,
        type=target.target_type,
        id=target.target_id,
    )
    if ref.app == "whiteboard" and ref.type == "workspace_sidebar" and ref.id == workspace.id:
        return "Workspace Whiteboards"
    if ref.app == "pms" and ref.type == "space":
        return resolve_source_target_label(
            db=db,
            workspace=workspace,
            target=target,
        )
    if ref.app == "pms" and ref.type == "task_list":
        task_list = db.scalar(
            select(TaskList).where(
                TaskList.id == ref.id,
                TaskList.archived.is_(False),
            )
        )
        return task_list.name if task_list is not None else "Unfiled"
    if ref.app == "meeting" and ref.type == "meeting":
        meeting = db.scalar(
            select(Meeting).where(
                Meeting.id == ref.id,
                Meeting.workspace_id == workspace.id,
            )
        )
        return meeting.title if meeting is not None else "Unfiled"
    return f"{ref.app}:{ref.type}"


def project_target_access(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: TargetRef,
) -> TargetAccessProjection:
    if ref.app == "whiteboard" and ref.type == "workspace_sidebar" and ref.id == workspace.id:
        role = resolve_workspace_role(db, user, workspace.id)
        return TargetAccessProjection(
            can_view=role is not None,
            can_edit=workspace_role_allows(role, "member"),
            can_manage=workspace_role_allows(role, "admin"),
        )
    if ref.app == "pms" and ref.type == "space":
        return _project_source_target_ref(
            db=db,
            user=user,
            workspace=workspace,
            ref=ref,
        )
    if ref.app == "pms" and ref.type == "task_list":
        task_list = db.scalar(
            select(TaskList).where(
                TaskList.id == ref.id,
                TaskList.archived.is_(False),
            )
        )
        if task_list is None or task_list.team_id is None:
            return _empty_projection()
        team = db.scalar(
            select(Team).where(
                Team.id == task_list.team_id,
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        if team is None:
            return _empty_projection()
        role = resolve_team_role(db, user, team)
        return TargetAccessProjection(
            can_view=role is not None,
            can_edit=team_role_allows(role, "member"),
            can_manage=team_role_allows(role, "admin"),
        )
    if ref.app == "meeting" and ref.type == "meeting":
        meeting = db.scalar(
            select(Meeting).where(
                Meeting.id == ref.id,
                Meeting.workspace_id == workspace.id,
            )
        )
        if meeting is None:
            return _empty_projection()
        return TargetAccessProjection(
            can_view=is_participant(user, meeting),
            can_edit=is_participant(user, meeting),
            can_manage=is_organizer(user, meeting),
        )
    return _empty_projection()


def target_write_allowed(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: TargetRef,
) -> bool:
    projection = project_target_access(db=db, user=user, workspace=workspace, ref=ref)
    return projection.can_edit or projection.can_manage


def can_read_pms_space(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    space_id: str,
) -> bool:
    return _project_pms_space_access(
        db=db,
        user=user,
        workspace=workspace,
        space_id=space_id,
    ).can_view


def can_edit_pms_space(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    space_id: str,
) -> bool:
    return _project_pms_space_access(
        db=db,
        user=user,
        workspace=workspace,
        space_id=space_id,
    ).can_edit
