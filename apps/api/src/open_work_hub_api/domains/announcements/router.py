from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User

from .schemas import (
    AnnouncementCreateRequest,
    AnnouncementOut,
    AnnouncementScope,
    AnnouncementsResponse,
    AnnouncementUpdateRequest,
)
from .service import (
    create_announcement,
    delete_announcement,
    get_announcement,
    list_announcements,
    update_announcement,
)

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("", response_model=AnnouncementsResponse)
def list_announcements_route(
    scope: AnnouncementScope = Query(default="company"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> AnnouncementsResponse:
    return list_announcements(db, scope=scope, limit=limit)


@router.post(
    "",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
)
def create_announcement_route(
    payload: AnnouncementCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> AnnouncementOut:
    return create_announcement(
        db,
        user=current_user,
        payload=payload,
    )


@router.get("/{announcement_id}", response_model=AnnouncementOut)
def get_announcement_route(
    announcement_id: str,
    db: Session = Depends(get_db_session),
) -> AnnouncementOut:
    return get_announcement(db, announcement_id=announcement_id)


@router.patch("/{announcement_id}", response_model=AnnouncementOut)
def update_announcement_route(
    announcement_id: str,
    payload: AnnouncementUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> AnnouncementOut:
    return update_announcement(
        db,
        user=current_user,
        announcement_id=announcement_id,
        payload=payload,
    )


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement_route(
    announcement_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    delete_announcement(
        db,
        user=current_user,
        announcement_id=announcement_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
