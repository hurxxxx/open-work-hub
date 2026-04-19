"""Service layer for conversations + turns persistence.

All queries scope by ``workspace_id + user_id`` — conversations are private
to the creating user within a workspace. Soft-deleted rows (``deleted_at
IS NOT NULL``) are excluded from list/get but remain on disk; no automatic
cleanup runs today.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.meeting.models import utcnow_naive

from .models import Conversation, ConversationTurn


TITLE_MAX_LEN = 200
TITLE_AUTO_PREVIEW_LEN = 30


def _generate_id() -> str:
    return str(uuid.uuid4())


def create_conversation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    title: str = "",
) -> Conversation:
    """Insert a new empty conversation. Title may be filled in later by the
    first user turn via ``autotitle_from_turn``."""
    now = utcnow_naive()
    conversation = Conversation(
        id=_generate_id(),
        workspace_id=workspace.id,
        user_id=user.id,
        title=(title or "").strip()[:TITLE_MAX_LEN],
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


_CURSOR_SEPARATOR = "|"


def _encode_cursor(conversation: Conversation) -> str:
    return f"{conversation.updated_at.isoformat()}{_CURSOR_SEPARATOR}{conversation.id}"


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    # Cursor carries both the timestamp AND the row id so ties on updated_at
    # don't silently drop rows. The ordering below must stay in lockstep with
    # ``ORDER BY updated_at DESC, id DESC``.
    if _CURSOR_SEPARATOR not in cursor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor: missing id component.",
        )
    ts_part, id_part = cursor.split(_CURSOR_SEPARATOR, 1)
    if not ts_part or not id_part:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor: empty component.",
        )
    try:
        ts = datetime.fromisoformat(ts_part)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cursor timestamp: {exc}",
        ) from exc
    return ts, id_part


def list_conversations(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[Conversation], str | None]:
    """Return the user's conversations in this workspace, newest first.

    Pagination uses a compound ``(updated_at, id)`` cursor — required to stay
    stable when two rows share the same ``updated_at`` tick (bulk creates,
    seed scripts, or concurrent edits). Over-fetches one row to determine
    whether another page exists.
    """
    effective_limit = max(1, min(limit, 100))
    stmt = (
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace.id,
            Conversation.user_id == user.id,
            Conversation.deleted_at.is_(None),
        )
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(effective_limit + 1)
    )
    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        # `(updated_at, id) < (cursor_ts, cursor_id)` expressed in SQL — matches
        # the compound DESC ordering so no row between pages is skipped or
        # repeated.
        stmt = stmt.where(
            or_(
                Conversation.updated_at < cursor_ts,
                and_(
                    Conversation.updated_at == cursor_ts,
                    Conversation.id < cursor_id,
                ),
            )
        )

    rows = list(db.execute(stmt).scalars())
    next_cursor: str | None = None
    if len(rows) > effective_limit:
        last = rows[effective_limit - 1]
        rows = rows[:effective_limit]
        next_cursor = _encode_cursor(last)
    return rows, next_cursor


def get_conversation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str,
) -> Conversation:
    """Load a conversation + its ordered turns. Scoped to the owner only."""
    conversation = db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.workspace_id != workspace.id
        or conversation.user_id != user.id
        or conversation.deleted_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return conversation


def rename_conversation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str,
    title: str,
) -> Conversation:
    conversation = get_conversation(
        db, workspace=workspace, user=user, conversation_id=conversation_id
    )
    normalized = (title or "").strip()[:TITLE_MAX_LEN]
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Title must not be empty.",
        )
    conversation.title = normalized
    db.commit()
    db.refresh(conversation)
    return conversation


def soft_delete_conversation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str,
) -> None:
    """Mark the conversation as deleted so it disappears from list views.

    Turns are retained on disk — no automatic cleanup job exists yet, so
    deletions are fully recoverable by an admin until we add one.
    """
    conversation = get_conversation(
        db, workspace=workspace, user=user, conversation_id=conversation_id
    )
    conversation.deleted_at = utcnow_naive()
    db.commit()


_MAX_APPEND_RETRIES = 3


def append_turn(
    db: Session,
    *,
    conversation: Conversation,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
) -> ConversationTurn:
    """Append a turn to an existing conversation.

    Sequence numbers are computed from ``MAX(seq) + 1`` in SQL rather than the
    ORM collection length so concurrent appends (two tabs, a retry arriving
    before the first commit) don't both compute the same stale seq. The
    ``(conversation_id, seq)`` unique constraint serializes the race — if a
    concurrent transaction wins, we retry up to a few times before surfacing
    the integrity error to the caller.
    """
    last_error: IntegrityError | None = None
    for _attempt in range(_MAX_APPEND_RETRIES):
        next_seq = db.execute(
            select(func.coalesce(func.max(ConversationTurn.seq), -1) + 1).where(
                ConversationTurn.conversation_id == conversation.id
            )
        ).scalar_one()
        turn = ConversationTurn(
            id=_generate_id(),
            conversation_id=conversation.id,
            seq=int(next_seq),
            role=role,
            content=content,
            meta=meta,
        )
        db.add(turn)
        conversation.updated_at = utcnow_naive()
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            continue
        db.refresh(turn)
        return turn
    # Exhausted retries — propagate the underlying DB error so the caller can
    # surface it. This is rare and indicates heavy write contention.
    assert last_error is not None
    raise last_error


def autotitle_from_turn(
    db: Session,
    *,
    conversation: Conversation,
    first_user_content: str,
) -> None:
    """Fill in a placeholder title from the first user message.

    No-op if the conversation already has a non-empty title. Runs inline on
    the first user turn so the sidebar doesn't need a second pass to show a
    meaningful label; subsequent user turns keep the original title.
    """
    if conversation.title.strip():
        return
    snippet = first_user_content.strip().replace("\n", " ")
    if not snippet:
        return
    conversation.title = snippet[:TITLE_AUTO_PREVIEW_LEN]
    db.commit()
