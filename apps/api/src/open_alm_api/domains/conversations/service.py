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

from fastapi import status
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import User, Workspace, utcnow_naive
from open_alm_api.domains.conversations.default_scope_adapters import (
    is_supported_conversation_scope_ref,
)
from open_alm_api.domains.conversations.scope_contract import (
    SCOPE_REF_MAX_LEN,
    SCOPE_RESOURCE_ID_MAX_LEN,
)

from .models import Conversation, ConversationTurn
from .turn_rewrite import (
    ConversationTailRewriteError,
    auto_title_preview,
    plan_conversation_tail_rewrite,
)


TITLE_MAX_LEN = 200


def _generate_id() -> str:
    return str(uuid.uuid4())


def create_conversation(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    title: str = "",
    scope_ref: str | None = None,
    scope_resource_id: str | None = None,
) -> Conversation:
    """Insert a new empty conversation. Title may be filled in later by the
    first user turn via ``autotitle_from_turn``."""
    normalized_title = (title or "").strip()[:TITLE_MAX_LEN]
    normalized_scope_ref = (scope_ref or "").strip() or None
    normalized_scope_resource_id = (scope_resource_id or "").strip() or None
    if (normalized_scope_ref is None) != (normalized_scope_resource_id is None):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="conversations.scope_pair_required",
        )
    if normalized_scope_ref is not None and not is_supported_conversation_scope_ref(
        normalized_scope_ref
    ):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="conversations.unsupported_scope",
            scope_ref=normalized_scope_ref,
        )
    _validate_scope_lengths(
        scope_ref=normalized_scope_ref,
        scope_resource_id=normalized_scope_resource_id,
    )
    if normalized_scope_ref is not None and not normalized_title:
        reusable = db.scalar(
            select(Conversation)
            .where(
                Conversation.workspace_id == workspace.id,
                Conversation.user_id == user.id,
                Conversation.deleted_at.is_(None),
                Conversation.scope_ref == normalized_scope_ref,
                Conversation.scope_resource_id == normalized_scope_resource_id,
                Conversation.title == "",
                ~Conversation.turns.any(),
            )
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(1)
        )
        if reusable is not None:
            return reusable
    now = utcnow_naive()
    conversation = Conversation(
        id=_generate_id(),
        workspace_id=workspace.id,
        user_id=user.id,
        title=normalized_title,
        scope_ref=normalized_scope_ref,
        scope_resource_id=normalized_scope_resource_id,
        created_at=now,
        updated_at=now,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _validate_scope_lengths(
    *,
    scope_ref: str | None,
    scope_resource_id: str | None,
) -> None:
    if scope_ref is not None and len(scope_ref) > SCOPE_REF_MAX_LEN:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation.value_invalid",
            field="scope_ref",
            max_length=SCOPE_REF_MAX_LEN,
        )
    if scope_resource_id is not None and len(scope_resource_id) > SCOPE_RESOURCE_ID_MAX_LEN:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="validation.value_invalid",
            field="scope_resource_id",
            max_length=SCOPE_RESOURCE_ID_MAX_LEN,
        )


_CURSOR_SEPARATOR = "|"


def _encode_cursor(conversation: Conversation) -> str:
    return f"{conversation.updated_at.isoformat()}{_CURSOR_SEPARATOR}{conversation.id}"


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    # Cursor carries both the timestamp AND the row id so ties on updated_at
    # don't silently drop rows. The ordering below must stay in lockstep with
    # ``ORDER BY updated_at DESC, id DESC``.
    if _CURSOR_SEPARATOR not in cursor:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="conversations.cursor_missing_id",
        )
    ts_part, id_part = cursor.split(_CURSOR_SEPARATOR, 1)
    if not ts_part or not id_part:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="conversations.cursor_empty_component",
        )
    try:
        ts = datetime.fromisoformat(ts_part)
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="conversations.cursor_invalid_timestamp",
            error=str(exc),
        ) from exc
    return ts, id_part


def list_conversations(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    limit: int = 20,
    cursor: str | None = None,
    scope_ref: str | None = None,
    scope_resource_id: str | None = None,
    allowed_scope_refs: frozenset[str] | None = None,
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
    normalized_scope_ref = (scope_ref or "").strip() or None
    normalized_scope_resource_id = (scope_resource_id or "").strip() or None
    if normalized_scope_resource_id is not None and normalized_scope_ref is None:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="conversations.scope_pair_required",
        )
    if normalized_scope_ref is not None:
        if not is_supported_conversation_scope_ref(normalized_scope_ref):
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="conversations.unsupported_scope",
                scope_ref=normalized_scope_ref,
            )
        stmt = stmt.where(Conversation.scope_ref == normalized_scope_ref)
        if normalized_scope_resource_id is not None:
            stmt = stmt.where(Conversation.scope_resource_id == normalized_scope_resource_id)
    elif allowed_scope_refs is not None:
        stmt = stmt.where(
            or_(
                Conversation.scope_ref.is_(None),
                Conversation.scope_ref.in_(allowed_scope_refs),
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
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="conversations.not_found",
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
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="conversations.title_empty",
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


def truncate_turns_from_seq(
    db: Session,
    *,
    conversation: Conversation,
    from_seq: int,
) -> int:
    """Delete every turn at or after ``from_seq`` in one conversation."""
    result = db.execute(
        delete(ConversationTurn).where(
            ConversationTurn.conversation_id == conversation.id,
            ConversationTurn.seq >= from_seq,
        )
    )
    deleted_count = int(result.rowcount or 0)
    if deleted_count > 0:
        conversation.updated_at = utcnow_naive()
    db.commit()
    db.expire(conversation, ["turns"])
    db.refresh(conversation)
    return deleted_count


def rewrite_turns_from_target(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    conversation_id: str,
    target_turn_id: str,
    from_seq: int,
    expected_tail_turn_id: str,
    expected_tail_seq: int,
    persist_user_turn: bool,
    replacement_user_content: str | None,
    expected_retry_user_content: str | None,
) -> Conversation:
    """Atomically rewrite a conversation tail from a specific persisted turn.

    The target id + seq pair acts as an optimistic version check: if another
    tab already rewrote the tail, the target row disappears or moves and this
    request must fail before appending a duplicate assistant turn.
    """
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace.id,
            Conversation.user_id == user.id,
            Conversation.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if conversation is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="conversations.not_found",
        )

    turns = list(
        db.scalars(
            select(ConversationTurn)
            .where(ConversationTurn.conversation_id == conversation.id)
            .order_by(ConversationTurn.seq.asc())
            .with_for_update()
        )
    )
    try:
        rewrite_plan = plan_conversation_tail_rewrite(
            turns=turns,
            target_turn_id=target_turn_id,
            from_seq=from_seq,
            expected_tail_turn_id=expected_tail_turn_id,
            expected_tail_seq=expected_tail_seq,
            persist_user_turn=persist_user_turn,
            replacement_user_content=replacement_user_content,
            expected_retry_user_content=expected_retry_user_content,
            current_title=conversation.title,
        )
    except ConversationTailRewriteError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=exc.code,
        ) from exc

    result = db.execute(
        delete(ConversationTurn).where(
            ConversationTurn.conversation_id == conversation.id,
            ConversationTurn.seq >= rewrite_plan.from_seq,
        )
    )
    if int(result.rowcount or 0) <= 0:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.conversation_rewrite_seq_missing",
        )

    now = utcnow_naive()
    if rewrite_plan.replacement_user_turn is not None:
        replacement = rewrite_plan.replacement_user_turn
        db.add(
            ConversationTurn(
                id=replacement.id,
                conversation_id=conversation.id,
                seq=replacement.seq,
                role="user",
                content=replacement.content,
            )
        )
        if replacement.next_title is not None:
            conversation.title = replacement.next_title
    conversation.updated_at = now
    db.commit()
    db.expire(conversation, ["turns"])
    db.refresh(conversation)
    return conversation


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


def stage_turn(
    db: Session,
    *,
    conversation: Conversation,
    role: str,
    content: str,
    meta: dict[str, Any] | None = None,
    turn_id: str | None = None,
) -> ConversationTurn:
    """Stage a turn without committing the surrounding transaction.

    This is reserved for workflows that must atomically create a conversation
    placeholder together with their durable run/outbox records. Callers must
    already hold the conversation live-run lock and own commit/rollback.
    """

    db.execute(
        select(Conversation.id)
        .where(Conversation.id == conversation.id)
        .with_for_update()
    ).scalar_one()
    next_seq = db.execute(
        select(func.coalesce(func.max(ConversationTurn.seq), -1) + 1).where(
            ConversationTurn.conversation_id == conversation.id
        )
    ).scalar_one()
    turn = ConversationTurn(
        id=turn_id or _generate_id(),
        conversation_id=conversation.id,
        seq=int(next_seq),
        role=role,
        content=content,
        meta=meta,
    )
    db.add(turn)
    conversation.updated_at = utcnow_naive()
    db.add(conversation)
    db.flush()
    return turn


def update_staged_or_persisted_turn(
    db: Session,
    *,
    turn_id: str,
    content: str,
    meta: dict[str, Any] | None,
) -> ConversationTurn:
    """Update the server-owned placeholder for a durable background run."""

    turn = db.scalar(
        select(ConversationTurn)
        .where(ConversationTurn.id == turn_id)
        .with_for_update()
    )
    if turn is None or turn.role != "assistant":
        raise LookupError(f"assistant conversation turn not found: {turn_id}")
    turn.content = content
    turn.meta = meta
    conversation = db.get(Conversation, turn.conversation_id)
    if conversation is not None:
        conversation.updated_at = utcnow_naive()
        db.add(conversation)
    db.add(turn)
    db.flush()
    return turn


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
    snippet = auto_title_preview(first_user_content)
    if not snippet:
        return
    conversation.title = snippet
    db.commit()
