from __future__ import annotations

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.release_notes.models import ReleaseNote, ReleaseNoteRead, utcnow_naive
from ai_do_api.domains.release_notes.schemas import (
    CurrentReleaseNoteResponse,
    ReleaseNoteOut,
    ReleaseNotesResponse,
)


PUBLISHED_STATUS = "published"
DEFAULT_RELEASE_NOTES_LIMIT = 20
MAX_RELEASE_NOTES_LIMIT = 100


def _project(note: ReleaseNote, read: ReleaseNoteRead | None = None) -> ReleaseNoteOut:
    return ReleaseNoteOut(
        id=note.id,
        release_key=note.release_key,
        title=note.title,
        summary=note.summary,
        body=note.body,
        published_at=note.published_at,
        dismissed_at=read.dismissed_at if read is not None else None,
    )


def _published_notes_query():
    return select(ReleaseNote).where(ReleaseNote.status == PUBLISHED_STATUS)


def _load_published_note(db: Session, release_note_id: str) -> ReleaseNote:
    note = db.scalar(_published_notes_query().where(ReleaseNote.id == release_note_id))
    if note is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="release_notes.not_found",
        )
    return note


def _read_for_user(
    db: Session,
    *,
    user: User,
    release_note_id: str,
) -> ReleaseNoteRead | None:
    return db.scalar(
        select(ReleaseNoteRead).where(
            ReleaseNoteRead.release_note_id == release_note_id,
            ReleaseNoteRead.user_id == user.id,
        )
    )


def get_current_release_note(
    db: Session,
    *,
    user: User,
) -> CurrentReleaseNoteResponse:
    read_exists = (
        select(ReleaseNoteRead.release_note_id)
        .where(
            ReleaseNoteRead.release_note_id == ReleaseNote.id,
            ReleaseNoteRead.user_id == user.id,
        )
        .exists()
    )
    note = db.scalar(
        _published_notes_query()
        .where(~read_exists)
        .order_by(ReleaseNote.published_at.desc(), ReleaseNote.created_at.desc())
        .limit(1)
    )
    return CurrentReleaseNoteResponse(item=_project(note) if note is not None else None)


def list_release_notes(
    db: Session,
    *,
    user: User,
    limit: int = DEFAULT_RELEASE_NOTES_LIMIT,
) -> ReleaseNotesResponse:
    bounded = max(1, min(limit, MAX_RELEASE_NOTES_LIMIT))
    notes = db.scalars(
        _published_notes_query()
        .order_by(ReleaseNote.published_at.desc(), ReleaseNote.created_at.desc())
        .limit(bounded)
    ).all()
    if not notes:
        return ReleaseNotesResponse(items=[])

    reads = db.scalars(
        select(ReleaseNoteRead).where(
            ReleaseNoteRead.user_id == user.id,
            ReleaseNoteRead.release_note_id.in_([note.id for note in notes]),
        )
    ).all()
    reads_by_note_id = {read.release_note_id: read for read in reads}
    return ReleaseNotesResponse(
        items=[_project(note, reads_by_note_id.get(note.id)) for note in notes]
    )


def dismiss_release_note(
    db: Session,
    *,
    user: User,
    release_note_id: str,
) -> ReleaseNoteOut:
    note = _load_published_note(db, release_note_id)
    read = _read_for_user(db, user=user, release_note_id=note.id)
    if read is None:
        read = ReleaseNoteRead(
            release_note_id=note.id,
            user_id=user.id,
            dismissed_at=utcnow_naive(),
        )
        db.add(read)
    else:
        read.dismissed_at = utcnow_naive()
    db.commit()
    db.refresh(read)
    return _project(note, read)
