from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_engine
from open_alm_api.domains.ai.runtime.models import (
    AgentInvocation,
    AgentRun,
    AgentTraceEvent,
)
from open_alm_api.domains.auth.models import AuditLog, User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.conversations.models import Conversation
from open_alm_api.domains.meeting.models import utcnow_naive
from test_meeting import _auth_headers, _bootstrap_admin_session


def test_admin_ai_runtime_retention_scrub_endpoint(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    run_id, invocation_id, trace_event_id = _seed_old_terminal_runtime_payload(
        admin["user"]["id"]
    )

    response = client.post(
        "/api/v1/admin/ai/runtime/retention/scrub?older_than_days=90",
        headers=_auth_headers(admin["token"]),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"scrubbed_run_count": 1, "older_than_days": 90}

    with Session(get_engine()) as db:
        assert db.get(AgentRun, run_id).metadata_json is None
        stored_invocation = db.get(AgentInvocation, invocation_id)
        assert stored_invocation.usage_json is None
        assert stored_invocation.error is None
        assert db.get(AgentTraceEvent, trace_event_id).payload_json is None

        audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "admin.ai_runtime.retention.scrub")
            .order_by(AuditLog.created_at.desc())
        )
        assert audit is not None
        assert audit.payload == {"older_than_days": 90, "scrubbed_run_count": 1}


def _seed_old_terminal_runtime_payload(admin_user_id: str) -> tuple[str, str, str]:
    old_timestamp = utcnow_naive() - timedelta(days=120)
    with Session(get_engine()) as db:
        admin_user = db.get(User, admin_user_id)
        workspace = db.scalar(select(Workspace).order_by(Workspace.created_at.asc()))
        assert admin_user is not None
        assert workspace is not None

        conversation = Conversation(
            id=new_id(),
            workspace_id=workspace.id,
            user_id=admin_user.id,
            title="Runtime retention",
            created_at=old_timestamp,
            updated_at=old_timestamp,
        )
        run = AgentRun(
            id=new_id(),
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            requested_by_user_id=admin_user.id,
            status="completed",
            runtime_profile="grounded_report",
            graph_enabled=True,
            metadata_json={"prompt": "must-not-leak"},
            created_at=old_timestamp,
            updated_at=old_timestamp,
        )
        db.add(conversation)
        db.flush()
        db.add(run)
        db.flush()

        invocation = AgentInvocation(
            id=new_id(),
            agent_run_id=run.id,
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            invocation_seq=0,
            agent_id="graph.adapter.node_runner",
            status="completed",
            purpose="retention test",
            usage_json={"tokens": 12},
            error="Authorization: Bearer must-not-leak",
            created_at=old_timestamp,
            updated_at=old_timestamp,
        )
        db.add(invocation)
        db.flush()

        trace_event = AgentTraceEvent(
            id=new_id(),
            agent_run_id=run.id,
            agent_invocation_id=invocation.id,
            workspace_id=workspace.id,
            conversation_id=conversation.id,
            run_seq=0,
            invocation_seq=0,
            event_seq=0,
            event_type="run_completed",
            payload_json={"prompt": "must-not-leak"},
            created_at=old_timestamp,
        )
        db.add(trace_event)
        db.commit()
        return run.id, invocation.id, trace_event.id
