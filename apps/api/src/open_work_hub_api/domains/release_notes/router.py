from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.release_notes.schemas import (
    CurrentReleaseNoteResponse,
    ReleaseNoteOut,
    ReleaseNotesResponse,
)
from open_work_hub_api.domains.release_notes.service import (
    dismiss_release_note,
    get_current_release_note,
    list_release_notes,
)

router = APIRouter(prefix="/release-notes", tags=["release-notes"])


@router.get("/current", response_model=CurrentReleaseNoteResponse)
def get_current_release_note_route(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> CurrentReleaseNoteResponse:
    return get_current_release_note(db, user=current_user)


@router.get("", response_model=ReleaseNotesResponse)
def list_release_notes_route(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ReleaseNotesResponse:
    return list_release_notes(db, user=current_user, limit=limit)


@router.post("/{release_note_id}/dismiss", response_model=ReleaseNoteOut)
def dismiss_release_note_route(
    release_note_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ReleaseNoteOut:
    return dismiss_release_note(
        db,
        user=current_user,
        release_note_id=release_note_id,
    )
