from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.app_routes import InternalAppLocation, build_app_href
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.meeting.models import Meeting
from open_work_hub_api.domains.meeting.permissions import is_organizer, is_participant
from open_work_hub_api.domains.source_access import can_read_meeting
from open_work_hub_api.domains.pms.access import resolve_pms_space_role
from open_work_hub_api.domains.pms.links import pms_space_whiteboards_path, pms_task_list_path
from open_work_hub_api.domains.pms.models import TaskList
from open_work_hub_api.domains.pms.roles import team_role_allows
from open_work_hub_api.domains.pms.space_models import Team
from open_work_hub_api.domains.source_access.targets import (
    TargetRef as SourceTargetRef,
)
from open_work_hub_api.domains.source_access.targets import (
    project_target_access as project_source_target_access,
)
from open_work_hub_api.domains.source_access.targets import (
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
    ref: TargetRef,
) -> TargetAccessProjection:
    projection = project_source_target_access(
        db=db,
        user=user,
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
    space_id: str,
) -> TargetAccessProjection:
    return _project_source_target_ref(
        db=db,
        user=user,
        ref=TargetRef(app="pms", type="space", id=space_id),
    )


def describe_source(
    *,
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
                    primary_target.target_id,
                    whiteboard_id=whiteboard.id,
                ),
            )
        if primary_target.target_type == "task_list":
            return (
                label,
                pms_task_list_path(
                    primary_target.target_id,
                    query={"tab": "whiteboard"},
                ),
            )
    if primary_target is not None and primary_target.target_app == "meeting":
        return label, build_app_href(
            InternalAppLocation(
                route_id="meeting.detail",
                path_params={"meetingId": primary_target.target_id},
            )
        )
    return label, build_app_href(
        InternalAppLocation(
            route_id="whiteboard.board",
            path_params={"whiteboardId": whiteboard.id},
        )
    )


def resolve_target_label(
    *,
    db: Session,
    target: WhiteboardTarget | None,
    user: User,
) -> str:
    if target is None:
        return "Unfiled"
    ref = TargetRef(
        app=target.target_app,
        type=target.target_type,
        id=target.target_id,
    )
    if not project_target_access(db=db, user=user, ref=ref).can_view:
        return f"{ref.app}:{ref.type}"
    if ref.app == "pms" and ref.type == "space":
        return resolve_source_target_label(
            db=db,
            user=user,
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
            )
        )
        return meeting.title if meeting is not None else "Unfiled"
    return f"{ref.app}:{ref.type}"


def project_target_access(
    *,
    db: Session,
    user: User,
    ref: TargetRef,
) -> TargetAccessProjection:
    if not can_use_app(db, user_id=user.id, app_id=ref.app):
        return _empty_projection()
    if ref.app == "pms" and ref.type == "space":
        return _project_source_target_ref(
            db=db,
            user=user,
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
                Team.active.is_(True),
                Team.trashed_at.is_(None),
            )
        )
        if team is None:
            return _empty_projection()
        role = resolve_pms_space_role(db, user, team)
        return TargetAccessProjection(
            can_view=role is not None,
            can_edit=team_role_allows(role, "member"),
            can_manage=team_role_allows(role, "admin"),
        )
    if ref.app == "meeting" and ref.type == "meeting":
        meeting = db.scalar(
            select(Meeting).where(
                Meeting.id == ref.id,
            )
        )
        if meeting is None:
            return _empty_projection()
        return TargetAccessProjection(
            can_view=can_read_meeting(db, user=user, meeting_id=meeting.id),
            can_edit=is_participant(user, meeting),
            can_manage=is_organizer(user, meeting),
        )
    return _empty_projection()


def target_write_allowed(
    *,
    db: Session,
    user: User,
    ref: TargetRef,
) -> bool:
    projection = project_target_access(db=db, user=user, ref=ref)
    return projection.can_manage


def can_read_pms_space(
    *,
    db: Session,
    user: User,
    space_id: str,
) -> bool:
    return _project_pms_space_access(
        db=db,
        user=user,
        space_id=space_id,
    ).can_view


def can_edit_pms_space(
    *,
    db: Session,
    user: User,
    space_id: str,
) -> bool:
    return _project_pms_space_access(
        db=db,
        user=user,
        space_id=space_id,
    ).can_edit
