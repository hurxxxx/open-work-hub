from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id

from .models import PlannerEvent
from .schemas import (
    PlannerEventCreateRequest,
    PlannerEventOut,
    PlannerEventsResponse,
    PlannerEventUpdateRequest,
)


LOCAL_TIMEZONE = ZoneInfo("Asia/Seoul")
MAX_LIST_RANGE_DAYS = 366


def parse_iso_or_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        try:
            only_date = date.fromisoformat(value)
            return datetime.combine(only_date, time.min)
        except ValueError:
            raise exc
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def _to_local_date_string(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.astimezone(LOCAL_TIMEZONE).date().isoformat()


def _parse_event_bounds(
    *,
    all_day: bool,
    start: str,
    end: str,
) -> tuple[datetime, datetime]:
    if all_day:
        try:
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All-day planner events require YYYY-MM-DD start/end.",
            ) from exc
        if end_date <= start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Planner event end must be after start.",
            )
        start_local = datetime.combine(start_date, time.min, tzinfo=LOCAL_TIMEZONE)
        end_local = datetime.combine(end_date, time.min, tzinfo=LOCAL_TIMEZONE)
        return (
            start_local.astimezone(UTC).replace(tzinfo=None),
            end_local.astimezone(UTC).replace(tzinfo=None),
        )

    if "T" not in start or "T" not in end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Timed planner events require ISO datetime start/end.",
        )
    start_at = parse_iso_or_date(start)
    end_at = parse_iso_or_date(end)
    if end_at <= start_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Planner event end must be after start.",
        )
    return start_at, end_at


def _serialize_event(event: PlannerEvent) -> PlannerEventOut:
    return PlannerEventOut(
        id=event.id,
        workspace_id=event.workspace_id,
        owner_id=event.owner_id,
        owner_name=event.owner.full_name if event.owner else event.owner_id,
        title=event.title,
        description=event.description,
        location=event.location,
        visibility=event.visibility,
        all_day=event.all_day,
        start=_to_local_date_string(event.start_at) if event.all_day else _utc_iso(event.start_at),
        end=_to_local_date_string(event.end_at) if event.all_day else _utc_iso(event.end_at),
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


def _load_event(
    db: Session,
    *,
    workspace: Workspace,
    event_id: str,
) -> PlannerEvent:
    event = db.scalar(
        select(PlannerEvent)
        .where(
            PlannerEvent.id == event_id,
            PlannerEvent.workspace_id == workspace.id,
        )
        .options(selectinload(PlannerEvent.owner))
    )
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Planner event not found.",
        )
    return event


def _ensure_owner(user: User, event: PlannerEvent) -> None:
    if event.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the event owner can modify this planner event.",
        )


def create_event(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    payload: PlannerEventCreateRequest,
) -> PlannerEventOut:
    start_at, end_at = _parse_event_bounds(
        all_day=payload.all_day,
        start=payload.start,
        end=payload.end,
    )
    event = PlannerEvent(
        id=new_id(),
        workspace_id=workspace.id,
        owner_id=user.id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        location=payload.location.strip(),
        visibility=payload.visibility,
        all_day=payload.all_day,
        start_at=start_at,
        end_at=end_at,
    )
    db.add(event)
    db.commit()
    fresh = _load_event(db, workspace=workspace, event_id=event.id)
    return _serialize_event(fresh)


def get_event(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    event_id: str,
) -> PlannerEventOut:
    event = _load_event(db, workspace=workspace, event_id=event_id)
    _ensure_owner(user, event)
    return _serialize_event(event)


def list_events(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> PlannerEventsResponse:
    if (from_at is None) != (to_at is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Planner event list requires both 'from' and 'to' together.",
        )
    query = (
        select(PlannerEvent)
        .where(
            PlannerEvent.workspace_id == workspace.id,
            PlannerEvent.owner_id == user.id,
        )
        .options(selectinload(PlannerEvent.owner))
        .order_by(PlannerEvent.start_at.asc())
    )
    if from_at is not None and to_at is not None:
        if to_at <= from_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Range 'to' must be strictly after 'from'.",
            )
        if (to_at - from_at) > timedelta(days=MAX_LIST_RANGE_DAYS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Range exceeds maximum {MAX_LIST_RANGE_DAYS} days.",
            )
        query = query.where(PlannerEvent.end_at > from_at, PlannerEvent.start_at < to_at)
    events = db.scalars(query).all()
    return PlannerEventsResponse(items=[_serialize_event(event) for event in events])


def update_event(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    event_id: str,
    payload: PlannerEventUpdateRequest,
) -> PlannerEventOut:
    event = _load_event(db, workspace=workspace, event_id=event_id)
    _ensure_owner(user, event)

    next_all_day = payload.all_day if payload.all_day is not None else event.all_day
    next_start = payload.start
    next_end = payload.end
    if (next_start is None) != (next_end is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Planner event updates must provide both start and end together.",
        )
    if payload.all_day is not None and next_start is None:
        next_start = _to_local_date_string(event.start_at) if next_all_day else _utc_iso(event.start_at)
        next_end = _to_local_date_string(event.end_at) if next_all_day else _utc_iso(event.end_at)
    if next_start is not None and next_end is not None:
        event.start_at, event.end_at = _parse_event_bounds(
            all_day=next_all_day,
            start=next_start,
            end=next_end,
        )
    event.all_day = next_all_day

    if payload.title is not None:
        event.title = payload.title.strip()
    if payload.description is not None:
        event.description = payload.description.strip()
    if payload.location is not None:
        event.location = payload.location.strip()
    if payload.visibility is not None:
        event.visibility = payload.visibility

    db.add(event)
    db.commit()
    fresh = _load_event(db, workspace=workspace, event_id=event.id)
    return _serialize_event(fresh)


def delete_event(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    event_id: str,
) -> None:
    event = _load_event(db, workspace=workspace, event_id=event_id)
    _ensure_owner(user, event)
    db.delete(event)
    db.commit()

