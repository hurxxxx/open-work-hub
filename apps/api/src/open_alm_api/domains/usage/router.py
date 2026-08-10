from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.dependencies import require_current_user
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.usage.service import (
    ALLOWED_USAGE_EVENT_TYPES,
    record_usage_event,
)

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_id: str = Field(..., min_length=1, max_length=64)
    event_type: str = Field(..., min_length=1, max_length=64)
    workspace_id: str | None = Field(default=None, max_length=36)
    content_kind: str | None = Field(default=None, max_length=64)
    content_id: str | None = Field(default=None, max_length=512)
    content_title: str | None = Field(default=None, max_length=300)
    route_path: str | None = Field(default=None, max_length=240)
    source: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] | None = None
    dedupe_minutes: int = Field(default=30, ge=1, le=1440)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        if value not in ALLOWED_USAGE_EVENT_TYPES:
            raise ValueError("Unsupported usage event type.")
        return value


class UsageEventResponse(BaseModel):
    ok: bool = True


@router.post("/events", response_model=UsageEventResponse)
def create_usage_event(
    payload: UsageEventRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> UsageEventResponse:
    try:
        record_usage_event(
            db,
            actor_user_id=current_user.id,
            workspace_id=payload.workspace_id,
            app_id=payload.app_id,
            event_type=payload.event_type,
            content_kind=payload.content_kind,
            content_id=payload.content_id,
            content_title=payload.content_title,
            route_path=payload.route_path,
            source=payload.source,
            metadata=payload.metadata,
            dedupe_minutes=payload.dedupe_minutes,
        )
    except ValueError as error:
        raise localized_http_exception(status_code=400, code="usage.invalid_event") from error
    db.commit()
    return UsageEventResponse()
