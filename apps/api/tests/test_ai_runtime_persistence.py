from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator
from datetime import timedelta
from threading import Event
import time

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.domains.ai import approvals as ai_approvals
from open_work_hub_api.domains.ai.runtime.models import AgentInvocation, AgentRun, AgentTraceEvent
from open_work_hub_api.domains.ai.runtime.persistence import (
    append_trace_event,
)
from open_work_hub_api.domains.ai.runtime.retention import scrub_completed_runtime_records
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.conversations.models import Conversation
from open_work_hub_api.domains.meeting.models import utcnow_naive


@pytest.fixture
def runtime_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    application_postgres_dsn: str,
) -> Iterator[sessionmaker[Session]]:
    monkeypatch.setenv("OPEN_WORK_HUB_POSTGRES_DSN", application_postgres_dsn)
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_HEALTHCHECK_ON_STARTUP", "0")

    from open_work_hub_api.core.db import get_engine, get_session_factory
    from open_work_hub_api.core.settings import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    factory = get_session_factory()
    engine = factory.kw["bind"]
    try:
        yield factory
    finally:
        engine.dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        get_settings.cache_clear()


def _seed_scope(db: Session) -> tuple[User, Conversation]:
    suffix = new_id()[:8]
    user = User(
        id=new_id(),
        login_id=f"runtime-{suffix}",
        email=f"runtime-{suffix}@open-work-hub.local",
        full_name="Runtime Test User",
        password_hash="test",
    )
    db.add_all([user])
    db.flush()
    conversation = Conversation(
        id=new_id(),
        user_id=user.id,
        title="Runtime persistence",
    )
    db.add(conversation)
    db.commit()
    return user, conversation


def _runtime_run(
    *,
    user: User,
    conversation: Conversation,
    status: str = "running",
) -> AgentRun:
    return AgentRun(
        id=new_id(),
        conversation_id=conversation.id,
        requested_by_user_id=user.id,
        status=status,
        runtime_profile="interactive_read",
    )


def _trace_events_by_type(db: Session, run_id: str) -> dict[str, AgentTraceEvent]:
    trace_events = list(
        db.scalars(
            select(AgentTraceEvent)
            .where(AgentTraceEvent.agent_run_id == run_id)
            .order_by(AgentTraceEvent.event_seq)
        )
    )
    return {event.event_type: event for event in trace_events}


def test_agent_run_allows_only_one_live_run_per_conversation(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)

        db.add(_runtime_run(user=user, conversation=conversation))
        db.commit()

        db.add(_runtime_run(user=user, conversation=conversation))
        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()
        db.add(
            _runtime_run(
                user=user,
                conversation=conversation,
                status="completed",
            )
        )
        db.commit()


def test_agent_invocation_allows_only_one_awaiting_approval_per_run(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        run = _runtime_run(user=user, conversation=conversation)
        db.add(run)
        db.commit()

        db.add(
            AgentInvocation(
                id=new_id(),
                agent_run_id=run.id,
                conversation_id=conversation.id,
                invocation_seq=0,
                agent_id="approval.proposal_preview",
                status="awaiting_approval",
                purpose="preview write proposal",
            )
        )
        db.commit()

        db.add(
            AgentInvocation(
                id=new_id(),
                agent_run_id=run.id,
                conversation_id=conversation.id,
                invocation_seq=1,
                agent_id="approval.proposal_preview",
                status="awaiting_approval",
                purpose="preview second proposal",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_agent_invocation_rejects_negative_invocation_seq(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        run = _runtime_run(user=user, conversation=conversation)
        db.add(run)
        db.flush()

        db.add(
            AgentInvocation(
                id=new_id(),
                agent_run_id=run.id,
                conversation_id=conversation.id,
                invocation_seq=-1,
                agent_id="domain.pms",
                status="pending",
                purpose="invalid sequence",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_legacy_approval_allows_only_one_pending_approval_per_snapshot(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        snapshot = ai_approvals.AgentRunSnapshot(
            id=new_id(),
            conversation_id=conversation.id,
            requested_by_user_id=user.id,
            status="awaiting_approval",
            messages_json=[{"role": "user", "content": "create issue"}],
            blocked_call_id="call-1",
        )
        db.add(snapshot)
        db.commit()

        expires_at = utcnow_naive() + timedelta(hours=1)
        db.add(
            ai_approvals.AiToolApproval(
                id=new_id(),
                conversation_id=conversation.id,
                agent_run_id=snapshot.id,
                tool_call_id="call-1",
                tool_name="pms.create_task",
                arguments_json="{}",
                status="pending",
                requested_by_user_id=user.id,
                expires_at=expires_at,
            )
        )
        db.commit()

        db.add(
            ai_approvals.AiToolApproval(
                id=new_id(),
                conversation_id=conversation.id,
                agent_run_id=snapshot.id,
                tool_call_id="call-2",
                tool_name="pms.create_task",
                arguments_json="{}",
                status="pending",
                requested_by_user_id=user.id,
                expires_at=expires_at,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_trace_events_are_uniquely_ordered_per_run(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        run = _runtime_run(user=user, conversation=conversation)
        db.add(run)
        db.commit()

        invocation = AgentInvocation(
            id=new_id(),
            agent_run_id=run.id,
            conversation_id=conversation.id,
            invocation_seq=0,
            agent_id="domain.rag",
            status="completed",
            purpose="collect evidence",
        )
        db.add(invocation)
        db.commit()

        db.add_all(
            [
                AgentTraceEvent(
                    id=new_id(),
                    agent_run_id=run.id,
                    agent_invocation_id=invocation.id,
                    conversation_id=conversation.id,
                    run_seq=0,
                    invocation_seq=0,
                    event_seq=0,
                    event_type="invocation_started",
                    payload_json={"agent_id": "domain.rag"},
                ),
                AgentTraceEvent(
                    id=new_id(),
                    agent_run_id=run.id,
                    agent_invocation_id=invocation.id,
                    conversation_id=conversation.id,
                    run_seq=0,
                    invocation_seq=0,
                    event_seq=1,
                    event_type="invocation_completed",
                    payload_json={"agent_id": "domain.rag"},
                ),
            ]
        )
        db.commit()

        db.add(
            AgentTraceEvent(
                id=new_id(),
                agent_run_id=run.id,
                agent_invocation_id=invocation.id,
                conversation_id=conversation.id,
                run_seq=0,
                invocation_seq=0,
                event_seq=1,
                event_type="duplicate",
                payload_json={},
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize("oversized", [False, True])
def test_append_trace_event_persists_only_scrubbed_or_size_limited_payload(
    runtime_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    oversized: bool,
) -> None:
    from open_work_hub_api.core.settings import get_settings

    monkeypatch.setenv("OPEN_WORK_HUB_AI_RUNTIME_TRACE_PAYLOAD_MAX_BYTES", "1024")
    get_settings.cache_clear()
    payload = {
        "prompt": "must-not-leak",
        "nested": [{"token": "must-not-leak", "count": 2}],
        "result_refs": ["artifact-1"],
    }
    if oversized:
        payload["large"] = "x" * 2048
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        run = _runtime_run(user=user, conversation=conversation)
        db.add(run)
        db.flush()
        event = append_trace_event(
            db,
            agent_run_id=run.id,
            conversation_id=conversation.id,
            event_type="test_payload",
            payload=payload,
        )
        event_id = event.id
        db.commit()

    # A new session prevents the SQLAlchemy identity map from standing in for persistence.
    with runtime_session_factory() as db:
        stored = db.get(AgentTraceEvent, event_id)
        assert stored.event_seq == 0
        assert "must-not-leak" not in str(stored.payload_json)
        if oversized:
            assert set(stored.payload_json) == {"truncated", "reason", "original_size_bytes"}
            assert stored.payload_json["truncated"] is True
            assert stored.payload_json["reason"] == "payload_too_large"
            assert stored.payload_json["original_size_bytes"] > 1024
        else:
            assert stored.payload_json == {
                "prompt": "[redacted]",
                "nested": [{"token": "[redacted]", "count": 2}],
                "result_refs": ["artifact-1"],
            }


def test_trace_event_append_serializes_concurrent_writers(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        run = _runtime_run(user=user, conversation=conversation)
        db.add(run)
        db.commit()
        run_id = run.id
        conversation_id = conversation.id

    first_inserted = Event()
    release_first = Event()

    def append_first() -> int:
        with runtime_session_factory() as db:
            with db.begin():
                event = append_trace_event(
                    db,
                    agent_run_id=run_id,
                    conversation_id=conversation_id,
                    event_type="first",
                    payload={},
                )
                event_seq = event.event_seq
                first_inserted.set()
                assert release_first.wait(timeout=5)
                return event_seq

    def append_second() -> int:
        assert first_inserted.wait(timeout=5)
        with runtime_session_factory() as db:
            with db.begin():
                event = append_trace_event(
                    db,
                    agent_run_id=run_id,
                    conversation_id=conversation_id,
                    event_type="second",
                    payload={},
                )
                return event.event_seq

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(append_first)
        second = executor.submit(append_second)
        time.sleep(0.2)
        release_first.set()
        event_seqs = [first.result(timeout=5), second.result(timeout=5)]

    assert sorted(event_seqs) == [0, 1]


def test_scrub_completed_runtime_records_removes_payloads_from_old_terminal_runs(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        run = _runtime_run(
            user=user,
            conversation=conversation,
            status="completed",
        )
        old_timestamp = utcnow_naive() - timedelta(days=120)
        run.metadata_json = {"prompt": "must-not-leak"}
        run.updated_at = old_timestamp
        db.add(run)
        db.flush()

        invocation = AgentInvocation(
            id=new_id(),
            agent_run_id=run.id,
            conversation_id=conversation.id,
            invocation_seq=0,
            agent_id="domain.rag",
            status="completed",
            purpose="collect evidence",
            usage_json={"tokens": 12},
            error="Authorization: Bearer must-not-leak",
        )
        event = AgentTraceEvent(
            id=new_id(),
            agent_run_id=run.id,
            agent_invocation_id=invocation.id,
            conversation_id=conversation.id,
            run_seq=0,
            invocation_seq=0,
            event_seq=0,
            event_type="completed",
            payload_json={"prompt": "must-not-leak"},
        )
        db.add_all([invocation, event])
        db.commit()

        assert scrub_completed_runtime_records(db, older_than_days=90) == 1
        db.commit()

        assert db.get(AgentRun, run.id).metadata_json is None
        stored_invocation = db.get(AgentInvocation, invocation.id)
        assert stored_invocation.usage_json is None
        assert stored_invocation.error is None
        assert db.get(AgentTraceEvent, event.id).payload_json is None


def test_scrub_completed_runtime_records_keeps_active_and_recent_runs(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        user, conversation = _seed_scope(db)
        active_run = _runtime_run(
            user=user,
            conversation=conversation,
            status="running",
        )
        old_timestamp = utcnow_naive() - timedelta(days=120)
        active_run.metadata_json = {"keep": True}
        active_run.updated_at = old_timestamp
        db.add(active_run)

        recent_conversation = Conversation(
            id=new_id(),
            user_id=user.id,
            title="Recent runtime persistence",
        )
        db.add(recent_conversation)
        db.flush()
        recent_run = _runtime_run(
            user=user,
            conversation=recent_conversation,
            status="completed",
        )
        recent_run.metadata_json = {"keep": True}
        db.add(recent_run)
        db.commit()

        assert scrub_completed_runtime_records(db, older_than_days=90) == 0
        db.commit()

        assert db.get(AgentRun, active_run.id).metadata_json == {"keep": True}
        assert db.get(AgentRun, recent_run.id).metadata_json == {"keep": True}
