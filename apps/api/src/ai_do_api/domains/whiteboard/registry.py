from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.access import (
    resolve_team_role,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from ai_do_api.domains.auth.models import Team, User, Workspace
from ai_do_api.domains.docs.registry import (
    ContainerRef as DocsContainerRef,
    project_container_access as project_docs_container_access,
)
from ai_do_api.domains.meeting.models import Meeting
from ai_do_api.domains.meeting.permissions import is_organizer, is_participant
from ai_do_api.domains.pms.models import TaskList
from ai_do_api.domains.whiteboard.models import Whiteboard, WhiteboardContainer


@dataclass(frozen=True)
class ContainerRef:
    app: str
    type: str
    id: str


@dataclass(frozen=True)
class ContainerAccessProjection:
    can_view: bool
    can_edit: bool
    can_manage: bool


def describe_source(
    *,
    workspace: Workspace,
    whiteboard: Whiteboard,
    primary_container: WhiteboardContainer | None,
) -> tuple[str, str | None]:
    label = whiteboard.source_app.replace("_", " ").title()
    if whiteboard.source_app == "whiteboard":
        label = "Whiteboard"
    if whiteboard.source_app == "pms":
        label = "PMS"
    if whiteboard.source_app == "meeting":
        label = "Meeting"
    if primary_container is not None and primary_container.container_app == "pms":
        if primary_container.container_type == "space":
            return label, f"/tool/pms-space-{primary_container.container_id}-whiteboards/{whiteboard.id}?workspace={workspace.key}"
        if primary_container.container_type == "task_list":
            return label, f"/tool/pms-list-{primary_container.container_id}?workspace={workspace.key}&tab=whiteboard"
    if primary_container is not None and primary_container.container_app == "meeting":
        return label, f"/w/{workspace.key}/meeting/{primary_container.container_id}"
    return label, f"/w/{workspace.key}/whiteboard/{whiteboard.id}"


def resolve_container_label(
    *,
    db: Session,
    workspace: Workspace,
    container: WhiteboardContainer | None,
) -> str:
    if container is None:
        return "Unfiled"
    ref = ContainerRef(
        app=container.container_app,
        type=container.container_type,
        id=container.container_id,
    )
    if ref.app == "whiteboard" and ref.type == "workspace_sidebar" and ref.id == workspace.id:
        return "Workspace Whiteboards"
    if ref.app == "pms" and ref.type == "space":
        team = db.scalar(
            select(Team).where(
                Team.id == ref.id,
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        return team.name if team is not None else "Unfiled"
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


def project_container_access(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: ContainerRef,
) -> ContainerAccessProjection:
    if ref.app == "whiteboard" and ref.type == "workspace_sidebar" and ref.id == workspace.id:
        role = resolve_workspace_role(db, user, workspace.id)
        return ContainerAccessProjection(
            can_view=role is not None,
            can_edit=workspace_role_allows(role, "member"),
            can_manage=workspace_role_allows(role, "admin"),
        )
    if ref.app == "pms" and ref.type == "space":
        projection = project_docs_container_access(
            db=db,
            user=user,
            workspace=workspace,
            ref=DocsContainerRef(app=ref.app, type=ref.type, id=ref.id),
        )
        return ContainerAccessProjection(
            can_view=projection.can_view,
            can_edit=projection.can_edit,
            can_manage=projection.can_manage,
        )
    if ref.app == "pms" and ref.type == "task_list":
        task_list = db.scalar(
            select(TaskList).where(
                TaskList.id == ref.id,
                TaskList.archived.is_(False),
            )
        )
        if task_list is None or task_list.team_id is None:
            return ContainerAccessProjection(False, False, False)
        team = db.scalar(
            select(Team).where(
                Team.id == task_list.team_id,
                Team.workspace_id == workspace.id,
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        if team is None:
            return ContainerAccessProjection(False, False, False)
        role = resolve_team_role(db, user, team)
        return ContainerAccessProjection(
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
            return ContainerAccessProjection(False, False, False)
        return ContainerAccessProjection(
            can_view=is_participant(user, meeting),
            can_edit=is_participant(user, meeting),
            can_manage=is_organizer(user, meeting),
        )
    return ContainerAccessProjection(False, False, False)


def container_write_allowed(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    ref: ContainerRef,
) -> bool:
    projection = project_container_access(db=db, user=user, workspace=workspace, ref=ref)
    return projection.can_edit or projection.can_manage


def can_read_pms_space(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    space_id: str,
) -> bool:
    team = db.scalar(
        select(Team).where(
            Team.id == space_id,
            Team.workspace_id == workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    )
    if team is None:
        return False
    return resolve_team_role(db, user, team) is not None


def can_edit_pms_space(
    *,
    db: Session,
    user: User,
    workspace: Workspace,
    space_id: str,
) -> bool:
    team = db.scalar(
        select(Team).where(
            Team.id == space_id,
            Team.workspace_id == workspace.id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    )
    if team is None:
        return False
    role = resolve_team_role(db, user, team)
    return team_role_allows(role, "member")
