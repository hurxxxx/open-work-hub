"""Service layer for personal learning notes.

Core invariants:
  * Each (owner, course_slug, lesson_id) produces at most one NativeDoc.
  * Visibility is encoded in ``NativeDoc.source_kind`` —
    ``lesson_note_public`` or ``lesson_note_private``.
  * ``private`` notes are readable only by their owner. No role —
    including platform admin — bypasses this rule. Private absence is
    hidden via 404, never 403, to avoid leaking existence.

All write endpoints operate on the caller's own note.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.docs.collab import sync_collab_record_from_rest_patch
from ai_do_api.domains.docs.models import NativeDoc, NativeDocPage
from ai_do_api.domains.rag.source_registry import RAG_SCOPE_PERSONAL
from ai_do_api.domains.retrieval.partitioning import assign_default_partition

from .note_document import (
    PAGE_TITLE,
    SOURCE_APP,
    SOURCE_KIND_PRIVATE,
    SOURCE_KIND_PUBLIC,
    SOURCE_KINDS_ALL,
    build_source_ref,
    compose_title as _compose_title,
    kind_for_visibility as _kind_for_visibility,
    serialize_detail as _serialize_detail,
    serialize_list_item as _serialize_list_item,
    validate_content_blocks as _validate_content_blocks,
)
from .schemas import Visibility

SYSTEM_WORKSPACE_KEY = "system-learning-notes"
SYSTEM_WORKSPACE_NAME = "Learning Notes (system)"
SYSTEM_WORKSPACE_DESCRIPTION = (
    "System-owned workspace backing /api/v1/learning/notes. "
    "Has no human members — access is enforced by the learning_notes router."
)


def get_or_create_system_workspace(db: Session) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.key == SYSTEM_WORKSPACE_KEY))
    if workspace is not None:
        if not workspace.active:
            workspace.active = True
            db.add(workspace)
            db.flush()
        return workspace

    workspace = Workspace(
        id=new_id(),
        key=SYSTEM_WORKSPACE_KEY,
        name=SYSTEM_WORKSPACE_NAME,
        description=SYSTEM_WORKSPACE_DESCRIPTION,
        active=True,
    )
    db.add(workspace)
    db.flush()
    return workspace


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _active_page(doc: NativeDoc) -> NativeDocPage | None:
    pages = sorted(
        (page for page in doc.pages if page.trashed_at is None),
        key=lambda page: page.sort_order,
    )
    return pages[0] if pages else None


def _load_doc_by_id(db: Session, doc_id: str) -> NativeDoc | None:
    return db.scalar(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.owner),
        )
        .where(
            NativeDoc.id == doc_id,
            NativeDoc.source_app == SOURCE_APP,
            NativeDoc.source_kind.in_(SOURCE_KINDS_ALL),
        )
    )


def _load_user_doc(
    db: Session, *, owner_id: str, course_slug: str, lesson_id: str
) -> NativeDoc | None:
    source_ref = build_source_ref(course_slug, lesson_id)
    return db.scalar(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.owner),
        )
        .where(
            NativeDoc.source_app == SOURCE_APP,
            NativeDoc.source_kind.in_(SOURCE_KINDS_ALL),
            NativeDoc.source_ref == source_ref,
            NativeDoc.owner_id == owner_id,
        )
    )


def list_page_notes(
    db: Session, *, viewer: User, course_slug: str, lesson_id: str
) -> list[dict[str, Any]]:
    """Return the notes visible to ``viewer`` on this lesson.

    Visibility policy:
      * public notes from anyone
      * the viewer's own private note (if any)
      * nothing else
    """
    source_ref = build_source_ref(course_slug, lesson_id)
    rows = db.scalars(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.owner),
        )
        .where(
            NativeDoc.source_app == SOURCE_APP,
            NativeDoc.source_kind.in_(SOURCE_KINDS_ALL),
            NativeDoc.source_ref == source_ref,
            NativeDoc.trashed_at.is_(None),
            or_(
                NativeDoc.source_kind == SOURCE_KIND_PUBLIC,
                NativeDoc.owner_id == viewer.id,
            ),
        )
        .order_by(
            # own note bubbles to the top, then newest updates first
            (NativeDoc.owner_id == viewer.id).desc(),
            NativeDoc.updated_at.desc(),
        )
    ).all()
    return [_serialize_list_item(doc, viewer_id=viewer.id) for doc in rows]


def _raise_not_found() -> None:
    raise localized_http_exception(status_code=404, code="learning.note_not_found")


def get_my_page_note(
    db: Session, *, user: User, course_slug: str, lesson_id: str
) -> dict[str, Any] | None:
    doc = _load_user_doc(db, owner_id=user.id, course_slug=course_slug, lesson_id=lesson_id)
    if doc is None or doc.trashed_at is not None:
        return None
    page = _active_page(doc)
    if page is None:
        return None
    return _serialize_detail(doc, page, viewer_id=user.id)


def get_page_note_detail(db: Session, *, viewer: User, doc_id: str) -> dict[str, Any]:
    doc = _load_doc_by_id(db, doc_id)
    if doc is None or doc.trashed_at is not None:
        _raise_not_found()
    assert doc is not None  # for type checkers
    # Access gate: either public or viewer is owner. Private notes of
    # others are 404, matching the list endpoint's exclusion semantics.
    if doc.source_kind == SOURCE_KIND_PRIVATE and doc.owner_id != viewer.id:
        _raise_not_found()
    page = _active_page(doc)
    if page is None:
        _raise_not_found()
    assert page is not None
    return _serialize_detail(doc, page, viewer_id=viewer.id)


def upsert_my_page_note(
    db: Session,
    *,
    user: User,
    course_slug: str,
    lesson_id: str,
    lesson_title: str,
    visibility: Visibility,
    content_blocks: list[dict],
) -> dict[str, Any]:
    validated_blocks = _validate_content_blocks(content_blocks)
    workspace = get_or_create_system_workspace(db)
    source_ref = build_source_ref(course_slug, lesson_id)
    kind = _kind_for_visibility(visibility)
    note_title = _compose_title(lesson_title=lesson_title, user=user)

    existing = _load_user_doc(db, owner_id=user.id, course_slug=course_slug, lesson_id=lesson_id)
    if existing is None:
        doc = NativeDoc(
            id=new_id(),
            workspace_id=workspace.id,
            owner_id=user.id,
            title=note_title,
            source_app=SOURCE_APP,
            source_kind=kind,
            source_ref=source_ref,
            generation_kind="human",
            rag_scope=RAG_SCOPE_PERSONAL,
        )
        db.add(doc)
        db.flush()
        page = NativeDocPage(
            id=new_id(),
            doc_id=doc.id,
            parent_id=None,
            title=PAGE_TITLE,
            content_blocks=validated_blocks,
            sort_order=0,
            created_by_id=user.id,
        )
        db.add(page)
        db.flush()
    else:
        doc = existing
        doc.title = note_title
        doc.source_kind = kind
        doc.rag_scope = RAG_SCOPE_PERSONAL
        doc.trashed_at = None
        db.add(doc)
        active_pages = sorted(
            (page for page in doc.pages if page.trashed_at is None),
            key=lambda page: page.sort_order,
        )
        if active_pages:
            page = active_pages[0]
            page.title = PAGE_TITLE
            page.content_blocks = validated_blocks
            db.add(page)
        else:
            page = NativeDocPage(
                id=new_id(),
                doc_id=doc.id,
                parent_id=None,
                title=PAGE_TITLE,
                content_blocks=validated_blocks,
                sort_order=0,
                created_by_id=user.id,
            )
            db.add(page)
        db.flush()

    assign_default_partition(
        db,
        target=doc,
        source_namespace="docs",
        candidate_scope_kind="personal",
        user_id=user.id,
    )

    sync_collab_record_from_rest_patch(
        db,
        source_type="native_doc_page",
        source_page_id=page.id,
        snapshot_content_blocks=validated_blocks,
    )
    db.commit()
    db.refresh(doc)
    db.refresh(page)
    return _serialize_detail(doc, page, viewer_id=user.id)


def archive_my_page_note(db: Session, *, user: User, doc_id: str) -> dict[str, Any]:
    doc = _load_doc_by_id(db, doc_id)
    # Ownership check uses the same 404-hide-existence rule as detail.
    if doc is None or doc.owner_id != user.id:
        _raise_not_found()
    assert doc is not None
    if doc.trashed_at is None:
        now = _utcnow_naive()
        doc.trashed_at = now
        db.add(doc)
        for page in doc.pages:
            if page.trashed_at is None:
                page.trashed_at = now
                db.add(page)
        db.commit()
        db.refresh(doc)
    page = _active_page(doc) or doc.pages[0] if doc.pages else None
    if page is None:
        # Should be unreachable because upsert always creates a page.
        raise localized_http_exception(
            status_code=500,
            code="learning.note_page_missing",
        )
    return _serialize_detail(doc, page, viewer_id=user.id)


def restore_my_page_note(db: Session, *, user: User, doc_id: str) -> dict[str, Any]:
    doc = _load_doc_by_id(db, doc_id)
    if doc is None or doc.owner_id != user.id:
        _raise_not_found()
    assert doc is not None
    doc.trashed_at = None
    db.add(doc)
    for page in doc.pages:
        if page.trashed_at is not None:
            page.trashed_at = None
            db.add(page)
    db.commit()
    db.refresh(doc)
    page = _active_page(doc)
    if page is None:
        raise localized_http_exception(
            status_code=409,
            code="learning.note_active_page_missing",
        )
    return _serialize_detail(doc, page, viewer_id=user.id)
