from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.access import (
    resolve_team_role,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from aidoo_api.domains.auth.models import Team, User, Workspace
from aidoo_api.domains.docs.registry import (
    ContainerRef as DocsContainerRef,
    project_container_access as project_docs_container_access,
)
from aidoo_api.domains.whiteboard.models import Whiteboard, WhiteboardContainer


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
    del primary_container
    label = whiteboard.source_app.replace("_", " ").title()
    if whiteboard.source_app == "whiteboard":
        label = "Whiteboard"
    if whiteboard.source_app == "pms":
        label = "PMS"
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

