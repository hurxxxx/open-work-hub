from __future__ import annotations

from dataclasses import dataclass

import pytest

from open_work_hub_api.domains.conversations.turn_rewrite import (
    ConversationTailRewriteError,
    auto_title_preview,
    plan_conversation_tail_rewrite,
)


@dataclass(frozen=True)
class Turn:
    id: str
    seq: int
    role: str
    content: str


def test_plan_user_turn_rewrite_replaces_auto_title() -> None:
    plan = plan_conversation_tail_rewrite(
        turns=[
            Turn(id="user-0", seq=0, role="user", content="old question"),
            Turn(id="assistant-1", seq=1, role="assistant", content="old answer"),
        ],
        target_turn_id="user-0",
        from_seq=0,
        expected_tail_turn_id="assistant-1",
        expected_tail_seq=1,
        persist_user_turn=True,
        replacement_user_content="new\nquestion",
        expected_retry_user_content="new\nquestion",
        current_title=auto_title_preview("old question"),
    )

    assert plan.from_seq == 0
    assert plan.replacement_user_turn is not None
    assert plan.replacement_user_turn.id == "user-0"
    assert plan.replacement_user_turn.seq == 0
    assert plan.replacement_user_turn.content == "new\nquestion"
    assert plan.replacement_user_turn.next_title == "new question"


def test_plan_user_turn_rewrite_keeps_custom_title() -> None:
    plan = plan_conversation_tail_rewrite(
        turns=[
            Turn(id="user-0", seq=0, role="user", content="old question"),
            Turn(id="assistant-1", seq=1, role="assistant", content="old answer"),
        ],
        target_turn_id="user-0",
        from_seq=0,
        expected_tail_turn_id="assistant-1",
        expected_tail_seq=1,
        persist_user_turn=True,
        replacement_user_content="new question",
        expected_retry_user_content="new question",
        current_title="Custom title",
    )

    assert plan.replacement_user_turn is not None
    assert plan.replacement_user_turn.next_title is None


def test_plan_assistant_retry_requires_previous_user_content() -> None:
    plan = plan_conversation_tail_rewrite(
        turns=[
            Turn(id="user-0", seq=0, role="user", content="retry this"),
            Turn(id="assistant-1", seq=1, role="assistant", content="old answer"),
        ],
        target_turn_id="assistant-1",
        from_seq=1,
        expected_tail_turn_id="assistant-1",
        expected_tail_seq=1,
        persist_user_turn=False,
        replacement_user_content=None,
        expected_retry_user_content="retry this",
        current_title="retry this",
    )

    assert plan.from_seq == 1
    assert plan.replacement_user_turn is None


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        (
            {
                "target_turn_id": "missing",
                "from_seq": 0,
                "expected_tail_turn_id": "assistant-1",
                "expected_tail_seq": 1,
                "persist_user_turn": True,
                "replacement_user_content": "new",
                "expected_retry_user_content": "new",
            },
            "ai.conversation_rewrite_seq_missing",
        ),
        (
            {
                "target_turn_id": "user-0",
                "from_seq": 0,
                "expected_tail_turn_id": "stale-tail",
                "expected_tail_seq": 1,
                "persist_user_turn": True,
                "replacement_user_content": "new",
                "expected_retry_user_content": "new",
            },
            "ai.conversation_rewrite_tail_mismatch",
        ),
        (
            {
                "target_turn_id": "assistant-1",
                "from_seq": 1,
                "expected_tail_turn_id": "assistant-1",
                "expected_tail_seq": 1,
                "persist_user_turn": True,
                "replacement_user_content": "new",
                "expected_retry_user_content": "new",
            },
            "ai.conversation_rewrite_role_mismatch",
        ),
        (
            {
                "target_turn_id": "assistant-1",
                "from_seq": 1,
                "expected_tail_turn_id": "assistant-1",
                "expected_tail_seq": 1,
                "persist_user_turn": False,
                "replacement_user_content": None,
                "expected_retry_user_content": "different",
            },
            "ai.conversation_retry_context_mismatch",
        ),
    ],
)
def test_plan_rejects_stale_or_invalid_rewrites(kwargs: dict[str, object], code: str) -> None:
    with pytest.raises(ConversationTailRewriteError) as exc_info:
        plan_conversation_tail_rewrite(
            turns=[
                Turn(id="user-0", seq=0, role="user", content="old"),
                Turn(id="assistant-1", seq=1, role="assistant", content="answer"),
            ],
            current_title="old",
            **kwargs,
        )

    assert exc_info.value.code == code
