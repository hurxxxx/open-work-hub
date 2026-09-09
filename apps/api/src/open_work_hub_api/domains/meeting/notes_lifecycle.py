from __future__ import annotations

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs.access_grants import grant_doc_access
from open_work_hub_api.domains.docs.models import NativeDoc, NativeDocPage
from open_work_hub_api.domains.docs.service import create_native_doc_for_user
from open_work_hub_api.domains.meeting.models import Meeting

NotesLifecycleAction = Literal["create_assets", "create_page", "reuse"]


def meeting_notes_doc_title(meeting: Meeting) -> str:
    return f"회의 메모: {meeting.title} ({meeting.start_at:%Y-%m-%d})"


def meeting_notes_page_title() -> str:
    return "회의 메모"


def resolve_notes_lifecycle_action(
    *,
    has_active_doc: bool,
    has_active_page: bool,
) -> NotesLifecycleAction:
    if not has_active_doc:
        return "create_assets"
    if not has_active_page:
        return "create_page"
    return "reuse"


def should_grant_notes_doc_edit(
    *,
    attendee_user_id: str,
    granted_by_user_id: str,
    doc_owner_id: str,
) -> bool:
    return attendee_user_id != granted_by_user_id and attendee_user_id != doc_owner_id


def grant_notes_doc_to_attendee(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
    attendee_user: User,
    granted_by_user_id: str,
) -> None:
    if not should_grant_notes_doc_edit(
        attendee_user_id=attendee_user.id,
        granted_by_user_id=granted_by_user_id,
        doc_owner_id=doc.owner_id,
    ):
        return
    grant_doc_access(
        db,
        doc_id=doc.id,
        user_id=attendee_user.id,
        granted_by_user_id=granted_by_user_id,
        granted_by_meeting_id=meeting.id,
        reason="meeting_notes",
        access_level="edit",
        expires_at=None,
    )


def load_active_native_doc(db: Session, *, doc_id: str | None) -> NativeDoc | None:
    if not doc_id:
        return None
    return db.scalar(
        select(NativeDoc).where(
            NativeDoc.id == doc_id,
            NativeDoc.trashed_at.is_(None),
        )
    )


def load_active_native_doc_page(
    db: Session,
    *,
    doc_id: str,
    page_id: str | None,
) -> NativeDocPage | None:
    if not page_id:
        return None
    return db.scalar(
        select(NativeDocPage).where(
            NativeDocPage.id == page_id,
            NativeDocPage.doc_id == doc_id,
            NativeDocPage.trashed_at.is_(None),
        )
    )


def create_meeting_notes_assets(
    db: Session,
    *,
    meeting: Meeting,
) -> tuple[NativeDoc, NativeDocPage]:
    return create_native_doc_for_user(
        db,
        owner_id=meeting.organizer_id,
        title=meeting_notes_doc_title(meeting),
        first_page_title=meeting_notes_page_title(),
        content_blocks=[],
        ownership_kind="company",
        source_app="meeting",
        source_kind="meeting_notes",
        source_ref=meeting.id,
    )


def sync_notes_doc_access(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
) -> None:
    for attendee in meeting.attendees:
        if attendee.user is None:
            continue
        grant_notes_doc_to_attendee(
            db,
            meeting=meeting,
            doc=doc,
            attendee_user=attendee.user,
            granted_by_user_id=meeting.organizer_id,
        )


def ensure_meeting_notes_state(
    db: Session,
    *,
    meeting: Meeting,
) -> tuple[NativeDoc, NativeDocPage]:
    # Serialize concurrent notes-ensure calls. Without this lock, two
    # simultaneous requests (e.g. the meeting modal opening + the collab
    # session call firing in parallel) would both observe
    # ``meeting.notes_doc_id is None`` and both create assets, leaving one
    # orphan NativeDoc row visible in the user's Docs hub forever.
    db.execute(select(Meeting.id).where(Meeting.id == meeting.id).with_for_update())
    db.refresh(meeting, attribute_names=["notes_doc_id", "notes_page_id"])

    doc = load_active_native_doc(db, doc_id=meeting.notes_doc_id)
    page: NativeDocPage | None = None
    action = resolve_notes_lifecycle_action(
        has_active_doc=doc is not None,
        has_active_page=False,
    )
    if action == "create_assets":
        doc, page = create_meeting_notes_assets(db, meeting=meeting)
    else:
        page = load_active_native_doc_page(db, doc_id=doc.id, page_id=meeting.notes_page_id)
        action = resolve_notes_lifecycle_action(
            has_active_doc=True,
            has_active_page=page is not None,
        )
        if action == "create_page":
            page = NativeDocPage(
                id=new_id(),
                doc_id=doc.id,
                parent_id=None,
                title=meeting_notes_page_title(),
                content_blocks=[],
                sort_order=0,
                created_by_id=meeting.organizer_id,
            )
            db.add(page)
            db.flush()

    if page is None:
        raise RuntimeError("meeting notes lifecycle did not resolve a page")

    meeting.notes_doc_id = doc.id
    meeting.notes_page_id = page.id
    db.add(meeting)
    db.flush()
    sync_notes_doc_access(db, meeting=meeting, doc=doc)
    return doc, page
