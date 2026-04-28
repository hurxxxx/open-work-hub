from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator
from datetime import timedelta
from threading import Event
import time

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from aidoo_api.domains.ai import approvals as ai_approvals
from aidoo_api.domains.ai.runtime.models import (
    AgentInvocation,
    AgentRun,
    AgentTraceEvent,
)
from aidoo_api.domains.ai.runtime.persistence import append_trace_event
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.conversations.models import Conversation
from aidoo_api.domains.meeting.models import utcnow_naive


@pytest.fixture
def runtime_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
) -> Iterator[sessionmaker[Session]]:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", postgres_dsn)
    monkeypatch.setenv("DOOWON_LLM_HEALTHCHECK_ON_STARTUP", "0")

    from aidoo_api.core.db import _alembic_config, get_engine, get_session_factory
    from aidoo_api.core.settings import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    engine = create_engine(postgres_dsn)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    engine.dispose()

    command.upgrade(_alembic_config(), "head")
    yield get_session_factory()

    get_session_factory.cache_clear()
    get_engine.cache_clear()
    get_settings.cache_clear()


def _seed_scope(db: Session) -> tuple[Workspace, User, Conversation]:
    suffix = new_id()[:8]
    workspace = Workspace(
        id=new_id(),
        key=f"runtime-{suffix}",
        name="Runtime Test",
        description="",
    )
    user = User(
        id=new_id(),
        email=f"runtime-{suffix}@aidoo.local",
        full_name="Runtime Test User",
        password_hash="test",
    )
    db.add_all([workspace, user])
    db.flush()
    conversation = Conversation(
        id=new_id(),
        workspace_id=workspace.id,
        user_id=user.id,
        title="Runtime persistence",
    )
    db.add(conversation)
    db.commit()
    return workspace, user, conversation


def _runtime_run(
    *,
    workspace: Workspace,
    user: User,
    conversation: Conversation,
    status: str = "running",
) -> AgentRun:
    return AgentRun(
        id=new_id(),
        workspace_id=workspace.id,
        conversation_id=conversation.id,
        requested_by_user_id=user.id,
        status=status,
        runtime_profile="interactive_read",
    )


def test_runtime_migration_creates_kernel_tables(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    engine = runtime_session_factory.kw["bind"]
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    assert {
        "ai_agent_runs",
        "ai_agent_invocations",
        "ai_agent_trace_events",
    }.issubset(table_names)


def test_runtime_migration_downgrade_upgrade_round_trip(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    from aidoo_api.core.db import _alembic_config

    command.downgrade(_alembic_config(), "-1")
    command.upgrade(_alembic_config(), "head")

    engine = runtime_session_factory.kw["bind"]
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert "ai_agent_runs" in table_names
    assert "ai_agent_trace_events" in table_names


def test_agent_run_allows_only_one_live_run_per_conversation(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        workspace, user, conversation = _seed_scope(db)

        db.add(_runtime_run(workspace=workspace, user=user, conversation=conversation))
        db.commit()

        db.add(_runtime_run(workspace=workspace, user=user, conversation=conversation))
        with pytest.raises(IntegrityError):
            db.commit()

        db.rollback()
        db.add(
            _runtime_run(
                workspace=workspace,
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
        workspace, user, conversation = _seed_scope(db)
        run = _runtime_run(workspace=workspace, user=user, conversation=conversation)
        db.add(run)
        db.commit()

        db.add(
            AgentInvocation(
                id=new_id(),
                agent_run_id=run.id,
                workspace_id=workspace.id,
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
                workspace_id=workspace.id,
                conversation_id=conversation.id,
                invocation_seq=1,
                agent_id="approval.proposal_preview",
                status="awaiting_approval",
                purpose="preview second proposal",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_legacy_approval_allows_only_one_pending_approval_per_snapshot(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        workspace, user, conversation = _seed_scope(db)
        snapshot = ai_approvals.AgentRunSnapshot(
            id=new_id(),
            conversation_id=conversation.id,
            workspace_id=workspace.id,
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
                workspace_id=workspace.id,
                conversation_id=conversation.id,
                agent_run_id=snapshot.id,
                tool_call_id="call-1",
                tool_name="pms.create_issue",
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
                workspace_id=workspace.id,
                conversation_id=conversation.id,
                agent_run_id=snapshot.id,
                tool_call_id="call-2",
                tool_name="pms.create_issue",
                arguments_json="{}",
                status="pending",
                requested_by_user_id=user.id,
                expires_at=expires_at,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_legacy_snapshot_status_update_tolerates_missing_runtime_shadow(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        workspace, user, conversation = _seed_scope(db)
        snapshot = ai_approvals.AgentRunSnapshot(
            id=new_id(),
            conversation_id=conversation.id,
            workspace_id=workspace.id,
            requested_by_user_id=user.id,
            status="awaiting_approval",
            messages_json=[{"role": "user", "content": "legacy pending approval"}],
            blocked_call_id="call-legacy",
        )
        db.add(snapshot)
        db.commit()

        ai_approvals.mark_snapshot_resumed(db, snapshot)
        db.commit()
        ai_approvals.mark_snapshot_completed(db, snapshot)
        db.commit()

        assert db.get(AgentRun, snapshot.id) is None


def test_snapshot_shadow_uses_runtime_profile_from_model_meta(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        workspace, user, conversation = _seed_scope(db)

        snapshot = ai_approvals.persist_snapshot_on_halt(
            db,
            workspace=workspace,
            conversation=conversation,
            requested_by_user=user,
            messages_json=[{"role": "user", "content": "보고서 작성"}],
            blocked_call_id="call-profile",
            model_meta={
                "model": "qwen/qwen3.6-35b-a3b",
                "runtime_profile": "grounded_report",
                "runtime_routing_reason_codes": ["grounded_report_signal"],
            },
        )
        db.commit()

        runtime_run = db.get(AgentRun, snapshot.id)
        assert runtime_run is not None
        assert runtime_run.runtime_profile == "grounded_report"


def test_trace_events_are_uniquely_ordered_per_run(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        workspace, user, conversation = _seed_scope(db)
        run = _runtime_run(workspace=workspace, user=user, conversation=conversation)
        db.add(run)
        db.commit()

        invocation = AgentInvocation(
            id=new_id(),
            agent_run_id=run.id,
            workspace_id=workspace.id,
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
                    workspace_id=workspace.id,
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
                    workspace_id=workspace.id,
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
                workspace_id=workspace.id,
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


def test_trace_event_append_serializes_concurrent_writers(
    runtime_session_factory: sessionmaker[Session],
) -> None:
    with runtime_session_factory() as db:
        workspace, user, conversation = _seed_scope(db)
        run = _runtime_run(workspace=workspace, user=user, conversation=conversation)
        db.add(run)
        db.commit()
        run_id = run.id
        workspace_id = workspace.id
        conversation_id = conversation.id

    first_inserted = Event()
    release_first = Event()

    def append_first() -> int:
        with runtime_session_factory() as db:
            with db.begin():
                event = append_trace_event(
                    db,
                    agent_run_id=run_id,
                    workspace_id=workspace_id,
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
                    workspace_id=workspace_id,
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
