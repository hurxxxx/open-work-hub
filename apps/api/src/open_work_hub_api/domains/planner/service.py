from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.planner.event_access import (
    ensure_planner_principal_user,
    require_planner_user_write_principal,
)
from open_work_hub_api.domains.planner.event_application import (
    PlannerEventCreateCommand,
    PlannerEventUpdateCommand,
    apply_planner_event_update,
    new_planner_event,
)
from open_work_hub_api.domains.planner.event_time import utc_iso
from open_work_hub_api.domains.planner.event_projection import (
    project_deleted_planner_event,
    project_planner_event,
    project_planner_event_for_ai,
)
from open_work_hub_api.domains.retrieval.partitioning import assign_default_partition

from .models import PlannerEvent
from .schemas import PlannerEventOut, PlannerEventsResponse


MAX_LIST_RANGE_DAYS = 366


def _ensure_event_partition(db: Session, event: PlannerEvent) -> None:
    assign_default_partition(
        db,
        target=event,
        source_namespace="planner",
        candidate_scope_kind="personal",
        user_id=event.owner_id,
    )


def _load_event(db: Session, *, user: User, event_id: str) -> PlannerEvent:
    event = db.scalar(
        select(PlannerEvent)
        .where(
            PlannerEvent.id == event_id,
            PlannerEvent.owner_id == user.id,
        )
        .options(selectinload(PlannerEvent.owner))
    )
    if event is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="planner.event_not_found",
        )
    return event


def can_read_planner_event_for_rag(
    db: Session,
    *,
    user: User,
    event_id: str,
    workspace_id: str | None = None,
) -> bool:
    del workspace_id
    return (
        db.scalar(
            select(PlannerEvent.id)
            .where(
                PlannerEvent.id == event_id,
                PlannerEvent.owner_id == user.id,
            )
            .limit(1)
        )
        is not None
    )


def create_event(
    db: Session,
    *,
    user: User,
    command: PlannerEventCreateCommand,
    event_id: str | None = None,
) -> PlannerEventOut:
    if event_id is not None and command.event_id is not None and event_id != command.event_id:
        raise ValueError("event_id and command.event_id must match")
    resolved_command = (
        command
        if event_id is None or command.event_id == event_id
        else PlannerEventCreateCommand(
            title=command.title,
            description=command.description,
            location=command.location,
            all_day=command.all_day,
            start=command.start,
            end=command.end,
            time_zone=command.time_zone,
            event_id=event_id,
        )
    )
    if event_id is not None:
        existing = db.scalar(select(PlannerEvent).where(PlannerEvent.id == event_id))
        if existing is not None:
            authorized_existing = _load_event(db, user=user, event_id=existing.id)
            if authorized_existing.retrieval_partition_id is None:
                _ensure_event_partition(db, authorized_existing)
                db.commit()
            return project_planner_event(
                _load_event(db, user=user, event_id=authorized_existing.id)
            )
    event = new_planner_event(
        owner_id=user.id,
        command=resolved_command,
        id_factory=new_id,
    )
    _ensure_event_partition(db, event)
    db.add(event)
    db.commit()
    return project_planner_event(_load_event(db, user=user, event_id=event.id))


def create_event_for_ai(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    title: str,
    start_at: datetime,
    end_at: datetime,
    scope: str = "personal",
    team_id: str | None = None,
    description: str = "",
    approved_call_id: str | None = None,
) -> dict[str, object]:
    del workspace
    require_planner_user_write_principal(principal)
    ensure_planner_principal_user(principal=principal, user=user)
    normalized_scope = scope.strip().lower()
    if normalized_scope != "personal":
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="planner.team_scope_unsupported",
        )
    if team_id is not None:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="planner.team_id_unsupported",
        )
    command = PlannerEventCreateCommand(
        title=title,
        description=description,
        location="",
        all_day=False,
        start=utc_iso(start_at),
        end=utc_iso(end_at),
        time_zone=user.time_zone,
    )
    result = create_event(
        db,
        user=user,
        command=command,
        event_id=approved_call_id,
    )
    return project_planner_event_for_ai(result)


def get_event(
    db: Session,
    *,
    user: User,
    event_id: str,
    principal: CallerPrincipal | None = None,
) -> PlannerEventOut:
    if principal is not None:
        ensure_planner_principal_user(principal=principal, user=user)
    return project_planner_event(_load_event(db, user=user, event_id=event_id))


def update_event_for_ai(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    event_id: str,
    title: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    description: str | None = None,
    location: str | None = None,
    approved_call_id: str | None = None,
) -> dict[str, object]:
    del approved_call_id, workspace
    require_planner_user_write_principal(principal)
    ensure_planner_principal_user(principal=principal, user=user)
    if (start_at is None) != (end_at is None):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="planner.update_start_at_end_at_required",
        )
    command = PlannerEventUpdateCommand(
        title=title,
        description=description,
        location=location,
        all_day=False if start_at is not None else None,
        start=utc_iso(start_at) if start_at is not None else None,
        end=utc_iso(end_at) if end_at is not None else None,
    )
    result = update_event(db, user=user, event_id=event_id, command=command)
    return project_planner_event_for_ai(result)


def delete_event_for_ai(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    event_id: str,
    approved_call_id: str | None = None,
) -> dict[str, object]:
    del approved_call_id, workspace
    require_planner_user_write_principal(principal)
    ensure_planner_principal_user(principal=principal, user=user)
    delete_event(db, user=user, event_id=event_id)
    return project_deleted_planner_event(event_id)


def list_events(
    db: Session,
    *,
    user: User,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    principal: CallerPrincipal | None = None,
) -> PlannerEventsResponse:
    if principal is not None:
        ensure_planner_principal_user(principal=principal, user=user)
    if (from_at is None) != (to_at is None):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="planner.list_range_required",
        )
    query = (
        select(PlannerEvent)
        .where(PlannerEvent.owner_id == user.id)
        .options(selectinload(PlannerEvent.owner))
        .order_by(PlannerEvent.start_at.asc())
    )
    if from_at is not None and to_at is not None:
        if to_at <= from_at:
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="calendar.range_to_after_from",
            )
        if (to_at - from_at) > timedelta(days=MAX_LIST_RANGE_DAYS):
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="calendar.range_too_large",
                days=MAX_LIST_RANGE_DAYS,
            )
        query = query.where(PlannerEvent.end_at > from_at, PlannerEvent.start_at < to_at)
    events = db.scalars(query).all()
    return PlannerEventsResponse(items=[project_planner_event(event) for event in events])


def update_event(
    db: Session,
    *,
    user: User,
    event_id: str,
    command: PlannerEventUpdateCommand,
) -> PlannerEventOut:
    event = _load_event(db, user=user, event_id=event_id)
    _ensure_event_partition(db, event)
    apply_planner_event_update(event, command)
    db.add(event)
    db.commit()
    return project_planner_event(_load_event(db, user=user, event_id=event.id))


def delete_event(db: Session, *, user: User, event_id: str) -> None:
    event = _load_event(db, user=user, event_id=event_id)
    _ensure_event_partition(db, event)
    db.delete(event)
    db.commit()
