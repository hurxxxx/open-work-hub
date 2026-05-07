from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.principal import user_principal
from ai_do_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from ai_do_api.domains.auth.models import User, Workspace

from .schemas import (
    PlannerEventCreateRequest,
    PlannerEventOut,
    PlannerEventsResponse,
    PlannerEventUpdateRequest,
)
from .service import (
    create_event,
    delete_event,
    get_event,
    list_events,
    parse_iso_or_date,
    update_event,
)


router = APIRouter(prefix="/planner", tags=["planner"])


@router.get("/events", response_model=PlannerEventsResponse)
def list_planner_events(
    from_param: str | None = Query(default=None, alias="from"),
    to_param: str | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PlannerEventsResponse:
    try:
        from_at = parse_iso_or_date(from_param) if from_param is not None else None
        to_at = parse_iso_or_date(to_param) if to_param is not None else None
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="calendar.invalid_iso_datetime",
            error=str(exc),
        ) from exc
    return list_events(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.planner.list_events",
        ),
        user=current_user,
        from_at=from_at,
        to_at=to_at,
    )


@router.post("/events", response_model=PlannerEventOut, status_code=status.HTTP_201_CREATED)
def create_planner_event(
    payload: PlannerEventCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PlannerEventOut:
    return create_event(db, workspace=workspace, user=current_user, payload=payload)


@router.get("/events/{event_id}", response_model=PlannerEventOut)
def get_planner_event(
    event_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PlannerEventOut:
    return get_event(
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.planner.get_event",
        ),
        user=current_user,
        event_id=event_id,
    )


@router.patch("/events/{event_id}", response_model=PlannerEventOut)
def update_planner_event(
    event_id: str,
    payload: PlannerEventUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PlannerEventOut:
    return update_event(
        db,
        workspace=workspace,
        user=current_user,
        event_id=event_id,
        payload=payload,
    )


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_planner_event(
    event_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    delete_event(db, workspace=workspace, user=current_user, event_id=event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
