from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.planner.app_catalog import PLANNER_APP
from open_work_hub_api.domains.planner.event_application import (
    PlannerEventCreateCommand,
    PlannerEventUpdateCommand,
)
from open_work_hub_api.domains.planner.event_time import parse_iso_or_date

from .schemas import (
    PlannerEventCreateRequest,
    PlannerEventOut,
    PlannerEventsResponse,
    PlannerEventUpdateRequest,
)
from .service import create_event, delete_event, get_event, list_events, update_event

require_planner_app_enabled = require_app_access(
    PLANNER_APP.app_id,
    error_code="platform.app_disabled",
)

router = APIRouter(
    prefix="/planner",
    tags=["planner"],
    dependencies=[Depends(require_planner_app_enabled)],
)


@router.get("/events", response_model=PlannerEventsResponse)
def list_planner_events(
    from_param: str | None = Query(default=None, alias="from"),
    to_param: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PlannerEventsResponse:
    try:
        from_at = (
            parse_iso_or_date(from_param, current_user.time_zone)
            if from_param is not None
            else None
        )
        to_at = (
            parse_iso_or_date(to_param, current_user.time_zone) if to_param is not None else None
        )
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="calendar.invalid_iso_datetime",
            error=str(exc),
        ) from exc
    return list_events(db, user=current_user, from_at=from_at, to_at=to_at)


@router.post("/events", response_model=PlannerEventOut, status_code=status.HTTP_201_CREATED)
def create_planner_event(
    payload: PlannerEventCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PlannerEventOut:
    return create_event(
        db,
        user=current_user,
        command=PlannerEventCreateCommand(
            title=payload.title,
            description=payload.description,
            location=payload.location,
            all_day=payload.all_day,
            start=payload.start,
            end=payload.end,
            time_zone=current_user.time_zone,
        ),
    )


@router.get("/events/{event_id}", response_model=PlannerEventOut)
def get_planner_event(
    event_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PlannerEventOut:
    return get_event(db, user=current_user, event_id=event_id)


@router.patch("/events/{event_id}", response_model=PlannerEventOut)
def update_planner_event(
    event_id: str,
    payload: PlannerEventUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> PlannerEventOut:
    return update_event(
        db,
        user=current_user,
        event_id=event_id,
        command=PlannerEventUpdateCommand(
            title=payload.title,
            description=payload.description,
            location=payload.location,
            all_day=payload.all_day,
            start=payload.start,
            end=payload.end,
        ),
    )


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_planner_event(
    event_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    delete_event(db, user=current_user, event_id=event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
