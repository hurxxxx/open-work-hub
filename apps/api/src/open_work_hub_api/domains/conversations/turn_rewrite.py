from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

TITLE_AUTO_PREVIEW_LEN = 30


class ConversationTurnLike(Protocol):
    id: str
    seq: int
    role: str
    content: str


@dataclass(frozen=True)
class ReplacementUserTurn:
    id: str
    seq: int
    content: str
    next_title: str | None = None


@dataclass(frozen=True)
class ConversationTailRewritePlan:
    from_seq: int
    replacement_user_turn: ReplacementUserTurn | None = None


class ConversationTailRewriteError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def auto_title_preview(content: str) -> str:
    return content.strip().replace("\n", " ")[:TITLE_AUTO_PREVIEW_LEN]


def plan_conversation_tail_rewrite(
    *,
    turns: Sequence[ConversationTurnLike],
    target_turn_id: str,
    from_seq: int,
    expected_tail_turn_id: str,
    expected_tail_seq: int,
    persist_user_turn: bool,
    replacement_user_content: str | None,
    expected_retry_user_content: str | None,
    current_title: str,
) -> ConversationTailRewritePlan:
    target = next(
        (turn for turn in turns if turn.id == target_turn_id and turn.seq == from_seq),
        None,
    )
    if target is None:
        raise ConversationTailRewriteError("ai.conversation_rewrite_seq_missing")

    tail = turns[-1] if turns else None
    if tail is None or tail.id != expected_tail_turn_id or tail.seq != expected_tail_seq:
        raise ConversationTailRewriteError("ai.conversation_rewrite_tail_mismatch")

    if persist_user_turn:
        if target.role != "user" or not replacement_user_content:
            raise ConversationTailRewriteError("ai.conversation_rewrite_role_mismatch")
        return ConversationTailRewritePlan(
            from_seq=from_seq,
            replacement_user_turn=ReplacementUserTurn(
                id=target_turn_id,
                seq=from_seq,
                content=replacement_user_content,
                next_title=_replacement_title(
                    from_seq=from_seq,
                    current_title=current_title,
                    previous_user_content=target.content,
                    replacement_user_content=replacement_user_content,
                ),
            ),
        )

    previous_turn = next(
        (turn for turn in reversed(turns) if turn.seq < from_seq),
        None,
    )
    if (
        target.role != "assistant"
        or previous_turn is None
        or previous_turn.role != "user"
        or expected_retry_user_content is None
        or previous_turn.content != expected_retry_user_content
    ):
        raise ConversationTailRewriteError("ai.conversation_retry_context_mismatch")

    return ConversationTailRewritePlan(from_seq=from_seq)


def _replacement_title(
    *,
    from_seq: int,
    current_title: str,
    previous_user_content: str,
    replacement_user_content: str,
) -> str | None:
    if from_seq != 0:
        return None
    title = current_title.strip()
    previous_auto_title = auto_title_preview(previous_user_content)
    if title and title != previous_auto_title:
        return None
    return auto_title_preview(replacement_user_content)
