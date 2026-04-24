"""HTTP router for personal learning notes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.dependencies import require_current_user
from aidoo_api.domains.auth.models import User

from .schemas import (
    LearningPageNoteDetail,
    LearningPageNoteListResponse,
    LearningPageNoteUpsertRequest,
)
from .service import (
    archive_my_page_note,
    get_my_page_note,
    get_page_note_detail,
    list_page_notes,
    restore_my_page_note,
    upsert_my_page_note,
)


router = APIRouter(prefix="/learning/notes", tags=["learning-notes"])


@router.get("", response_model=LearningPageNoteListResponse)
def list_notes(
    course_slug: str = Query(..., min_length=1, max_length=64),
    lesson_id: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LearningPageNoteListResponse:
    items = list_page_notes(
        db, viewer=current_user, course_slug=course_slug, lesson_id=lesson_id
    )
    return LearningPageNoteListResponse(items=items)


@router.get("/me", response_model=LearningPageNoteDetail)
def get_my_note(
    course_slug: str = Query(..., min_length=1, max_length=64),
    lesson_id: str = Query(..., min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LearningPageNoteDetail:
    note = get_my_page_note(
        db, user=current_user, course_slug=course_slug, lesson_id=lesson_id
    )
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="My learning note not found.",
        )
    return LearningPageNoteDetail(**note)


@router.put("/me", response_model=LearningPageNoteDetail)
def upsert_my_note(
    payload: LearningPageNoteUpsertRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LearningPageNoteDetail:
    note = upsert_my_page_note(
        db,
        user=current_user,
        course_slug=payload.course_slug,
        lesson_id=payload.lesson_id,
        lesson_title=payload.lesson_title,
        visibility=payload.visibility,
        content_blocks=payload.content_blocks,
    )
    return LearningPageNoteDetail(**note)


@router.get("/{doc_id}", response_model=LearningPageNoteDetail)
def get_note_detail(
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LearningPageNoteDetail:
    if not doc_id:
        raise HTTPException(status_code=404, detail="Learning note not found.")
    note = get_page_note_detail(db, viewer=current_user, doc_id=doc_id)
    return LearningPageNoteDetail(**note)


@router.post("/{doc_id}/archive", response_model=LearningPageNoteDetail)
def archive_note(
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LearningPageNoteDetail:
    if not doc_id:
        raise HTTPException(status_code=404, detail="Learning note not found.")
    note = archive_my_page_note(db, user=current_user, doc_id=doc_id)
    return LearningPageNoteDetail(**note)


@router.post("/{doc_id}/restore", response_model=LearningPageNoteDetail)
def restore_note(
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> LearningPageNoteDetail:
    if not doc_id:
        raise HTTPException(status_code=404, detail="Learning note not found.")
    note = restore_my_page_note(db, user=current_user, doc_id=doc_id)
    return LearningPageNoteDetail(**note)
